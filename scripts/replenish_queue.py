"""
queue.csv 自動補充スクリプト。

動作:
  1. content/posts/ と queue.csv からカバー済み (tool, code) を確認
  2. 未カバーの組み合わせをシャッフルして ADD_COUNT 件選択
  3. Gemini + Google検索で原因・解決策をリサーチ
  4. queue.csv に追記

実行:
  python scripts/replenish_queue.py
  ADD_COUNT=30 python scripts/replenish_queue.py
"""

import csv
import json
import os
import random
import re
from pathlib import Path


import google.generativeai as genai
from google.generativeai.types import Tool

ADD_COUNT = int(os.getenv("ADD_COUNT", "180"))

BASE       = Path(__file__).parent
POSTS_DIR  = BASE.parent / "content" / "posts"
QUEUE_PATH = BASE / "queue.csv"
TOOLS_PATH = BASE / "tools.json"

FIELDNAMES = ["tool", "status_code", "official_meaning", "causes", "solutions"]


def load_tools() -> list[str]:
    """tools.json からツールリストを読み込む。"""
    return json.loads(TOOLS_PATH.read_text(encoding="utf-8"))["tools"]

# 対象エラーコード
ERROR_CODES = [
    "400", "401", "402", "403", "404", "405",
    "408", "409", "410", "422", "429",
    "500", "502", "503", "504",
]


def tool_to_slug(tool: str) -> str:
    """ツール名をファイル名スラグに変換する。"""
    return tool.lower().replace(" ", "_")


def get_covered_pairs() -> set[tuple[str, str]]:
    """既存記事と queue.csv からカバー済みの (slug, code) ペアを返す。"""
    covered: set[tuple[str, str]] = set()

    # 既存記事のファイル名から抽出
    for md in POSTS_DIR.glob("*.md"):
        stem = md.stem
        for code in ERROR_CODES:
            if stem.endswith(f"_{code}"):
                slug = stem[: -(len(code) + 1)]
                covered.add((slug, code))

    # queue.csv から抽出
    if QUEUE_PATH.exists() and QUEUE_PATH.stat().st_size > 0:
        with open(QUEUE_PATH, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                slug = tool_to_slug(row["tool"].strip())
                code = row["status_code"].strip()
                covered.add((slug, code))

    return covered


def research_with_gemini(
    model,
    tool: str,
    code: str,
) -> dict | None:
    """
    Gemini + Google検索で (tool, code) のエラー情報をリサーチする。
    戻り値: queue.csv の 1 行分の dict、失敗時は None。
    """
    prompt = f"""{tool} で HTTP ステータスコード {code} が発生するケースについて調べてください。

以下の形式で JSON のみ返してください（前置き・説明不要）:
{{
  "official_meaning": "このエラーコードの意味を {tool} の文脈で1文（日本語）",
  "causes": [
    "{tool} 固有の原因1",
    "{tool} 固有の原因2",
    "{tool} 固有の原因3",
    "{tool} 固有の原因4"
  ],
  "solutions": [
    "具体的な解決策1（コマンドや設定値を含む）",
    "具体的な解決策2",
    "具体的な解決策3",
    "具体的な解決策4"
  ]
}}"""

    try:
        response = model.generate_content(
            prompt,
            tools=[Tool(google_search={})],
        )
        text = response.text.strip()

        # レスポンスから JSON を抽出
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            print(f"    JSON が見つかりません: {text[:80]}")
            return None

        data = json.loads(m.group(0))
        causes    = "|".join(str(c).strip() for c in data.get("causes", [])[:5] if c)
        solutions = "|".join(str(s).strip() for s in data.get("solutions", [])[:5] if s)
        meaning   = str(data.get("official_meaning", "")).strip()

        if not (meaning and causes and solutions):
            print(f"    データ不足のためスキップ")
            return None

        return {
            "tool": tool,
            "status_code": code,
            "official_meaning": meaning,
            "causes": causes,
            "solutions": solutions,
        }

    except json.JSONDecodeError as e:
        print(f"    JSON パースエラー: {e}")
        return None
    except Exception as e:
        print(f"    Gemini エラー: {e}")
        return None


def main() -> None:
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        print("エラー: GEMINI_API_KEY が設定されていません。")
        return

    genai.configure(api_key=gemini_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    tools = load_tools()
    covered = get_covered_pairs()
    print(f"ツール数: {len(tools)} / カバー済み: {len(covered)} 件")

    # 未カバーの (tool, code) を列挙
    uncovered: list[tuple[str, str]] = []
    for tool in tools:
        slug = tool_to_slug(tool)
        for code in ERROR_CODES:
            if (slug, code) not in covered:
                uncovered.append((tool, code))

    print(f"未カバー: {len(uncovered)} 件")

    if not uncovered:
        print("全ての組み合わせがカバー済みです。")
        return

    # ランダムにシャッフルして ADD_COUNT 件選択（特定ツールへの偏りを防ぐ）
    random.shuffle(uncovered)
    targets = uncovered[:ADD_COUNT]

    print(f"\n{len(targets)} 件をリサーチします...\n")

    results: list[dict] = []
    for i, (tool, code) in enumerate(targets, 1):
        print(f"  [{i:2d}/{len(targets)}] {tool} {code}")
        row = research_with_gemini(model, tool, code)
        if row:
            results.append(row)
            print(f"         → {row['official_meaning'][:50]}")
        else:
            print(f"         → スキップ")

    if not results:
        print("\n追加するデータがありません。")
        return

    # queue.csv に追記（ファイルが空なら header も書く）
    write_header = not (QUEUE_PATH.exists() and QUEUE_PATH.stat().st_size > 0)
    with open(QUEUE_PATH, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerows(results)

    print(f"\n完了: {len(results)} 件を queue.csv に追加しました。")
    print(f"キュー残数: {len(results)} 件追加（既存分含む）")


if __name__ == "__main__":
    main()
