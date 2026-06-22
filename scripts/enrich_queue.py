"""queue.csv の既存行に source_urls / alternatives を補完する。

source_urls が空の行は、Gemini 2.5 Flash + Google Search で実際の問題報告 URL を探し、
GET で実在確認できた URL だけを書き戻す。
alternatives が空の行には、Gemini 2.5 Flash で代替ツール候補を補完する。
"""

import argparse
import csv
import json
import os
import re
import time

import requests
from google import genai as google_genai
from google.genai import types as genai_types

from replenish_queue import FIELDNAMES, QUEUE_PATH

DEFAULT_BATCH_SIZE = int(os.getenv("BATCH_SIZE", "20"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="queue.csv の source_urls 空欄を実報告URLで補完する"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="処理する最大行数。未指定時は BATCH_SIZE または 20。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="queue.csv に書き戻さず、取得結果だけ表示する。",
    )
    return parser.parse_args()


def verify_url(url: str) -> bool:
    try:
        r = requests.get(
            url,
            timeout=8,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if r.status_code >= 400:
            return False
        if "reddit.com" in url and r.url.rstrip("/") in (
            "https://www.reddit.com",
            "https://reddit.com",
        ):
            return False
        if "github.com" in url and "/login" in r.url:
            return False
        return True
    except Exception:
        return False


def _extract_json(text: str) -> dict | None:
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    return json.loads(m.group(0))


def research_source_urls(gemini_client, tool: str, code: str) -> list[str]:
    prompt = f"""GitHub Issues, Stack Overflow, Reddit, Zenn, Qiita で「{tool} {code}」に関する
実際の問題報告を検索してください（対象地域: 日本 language=ja）。

## 需要フィルタリング
実際の問題報告が日本語・英語合わせて3件以上確認できない場合は
{{"skip": true}} のみ返してください。

## 優先して探す報告
- GitHub Issues / Stack Overflow / Reddit / Zenn / Qiita を優先
- 「公式解決策が効かなかった」報告
- OS・バージョン・クラウドプロバイダーなど、環境固有の問題報告

## 確認できた場合の出力
以下の JSON のみ返してください（前置き・説明不要）:
{{
  "source_urls": [
    "https://github.com/...",
    "https://stackoverflow.com/..."
  ]
}}

source_urls は実在する URL のみ記載すること。見つからなければ空配列。
架空URLは禁止です。"""

    response = gemini_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())]
        ),
    )
    data = _extract_json(response.text.strip())
    if not data or data.get("skip"):
        return []

    urls: list[str] = []
    seen: set[str] = set()
    for raw_url in data.get("source_urls", []):
        url = str(raw_url).strip()
        if not url or url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def research_alternatives(gemini_client, tool: str) -> list[str]:
    prompt = f"""{tool} の代替となる主要ツールを1〜3件教えてください。

以下のJSONのみ返してください（前置き不要）:
{{"alternatives": ["{tool}の代替ツール名1", "{tool}の代替ツール名2"]}}

見つからない場合: {{"alternatives": []}}"""

    response = gemini_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    data = _extract_json(response.text.strip())
    if not data:
        return []
    return [str(a).strip() for a in data.get("alternatives", [])[:3] if a]


def _normalise_row(row: dict) -> dict:
    return {field: row.get(field, "") for field in FIELDNAMES}


def load_queue() -> list[dict]:
    with open(QUEUE_PATH, encoding="utf-8", newline="") as f:
        return [_normalise_row(row) for row in csv.DictReader(f)]


def write_queue(rows: list[dict]) -> None:
    with open(QUEUE_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        raise SystemExit("エラー: GEMINI_API_KEY が設定されていません。")

    rows = load_queue()
    targets = [
        (idx, row)
        for idx, row in enumerate(rows)
        if not row.get("source_urls", "").strip()
        or not row.get("alternatives", "").strip()
    ][: args.batch_size]

    if not targets:
        print("source_urls / alternatives が空の行はありません。")
        return

    gemini_client = google_genai.Client(api_key=gemini_key)
    updated = 0

    for pos, (idx, row) in enumerate(targets, 1):
        tool = row["tool"].strip()
        code = row["status_code"].strip()
        print(f"[{pos}/{len(targets)}] {tool} {code}")

        row_updated = False

        if not row.get("source_urls", "").strip():
            try:
                candidate_urls = research_source_urls(gemini_client, tool, code)
            except Exception as e:
                print(f"  source_urls Gemini エラー: {type(e).__name__}: {e}")
                candidate_urls = []

            verified_urls = [url for url in candidate_urls if verify_url(url)]
            if verified_urls:
                rows[idx]["source_urls"] = "|".join(verified_urls[:5])
                row_updated = True
                print("  source_urls OK: " + rows[idx]["source_urls"])
            else:
                print("  source_urls なし")

        if not row.get("alternatives", "").strip():
            try:
                alts = research_alternatives(gemini_client, tool)
            except Exception as e:
                print(f"  alternatives Gemini エラー: {type(e).__name__}: {e}")
                alts = []

            if alts:
                rows[idx]["alternatives"] = "|".join(alts)
                row_updated = True
                print("  alternatives OK: " + rows[idx]["alternatives"])
            else:
                print("  alternatives なし")

        if row_updated:
            updated += 1

        time.sleep(2)

    if args.dry_run:
        print(f"\ndry-run: {updated} 行に source_urls / alternatives を設定予定です。")
        return

    write_queue(rows)
    print(f"\n完了: {updated} 行の source_urls / alternatives を更新しました。")


if __name__ == "__main__":
    main()
