"""
IndexNow へ URL 更新通知を送信する。

動作:
  1. git diff HEAD~1..HEAD で新規・更新記事の URL を取得（優先枠）
  2. rewrite_priority.json のスコア上位から残り枠を補充
  3. https://api.indexnow.org/indexnow へ JSON バッチ POST
  4. 非 200 はログ出力後に正常終了（ワークフローを赤にしない）

環境変数:
  INDEXNOW_KEY   IndexNow APIキー（必須）。static/{key}.txt と同じ値
  SITE_URL       サイト URL（デフォルト: https://errorlog.jp）

使用方法:
  python scripts/request_index.py                   # git diff から自動検出
  python scripts/request_index.py --urls URL1 URL2  # URL を明示指定
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

SITE_URL      = os.getenv("SITE_URL", "https://errorlog.jp").rstrip("/")
INDEXNOW_EP   = "https://api.indexnow.org/indexnow"
MAX_NEW       = 3  # git diff 由来 URL の優先枠

BASE          = Path(__file__).resolve().parent.parent
POSTS_DIR     = BASE / "content" / "posts"
PRIORITY_FILE = BASE / "scripts" / "rewrite_priority.json"


# ── URL 解決 ──────────────────────────────────────────────────────────────────

def _slug_to_url(slug: str) -> str:
    return f"{SITE_URL}/posts/{slug}/"


def _path_to_url(path: str) -> str | None:
    p = Path(path)
    if p.suffix != ".md":
        return None
    return _slug_to_url(p.stem)


def _new_urls_from_git() -> list[str]:
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1..HEAD", "--", "content/posts/"],
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"[request_index] WARN: git diff に失敗しました: {e}")
        return []

    urls = []
    for line in result.stdout.splitlines():
        path = line.strip()
        if not path:
            continue
        url = _path_to_url(path)
        if url:
            urls.append(url)
    return list(dict.fromkeys(urls))[:MAX_NEW]


def _title_to_stem_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for md in POSTS_DIR.glob("*.md"):
        try:
            text = md.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        m = re.search(r'^title:\s*"?([^"\n]+)"?\s*$', text, re.MULTILINE)
        if m:
            mapping[m.group(1).strip()] = md.stem
    return mapping


def _priority_urls(exclude: set[str]) -> list[str]:
    if not PRIORITY_FILE.exists():
        return []
    try:
        entries: list[dict] = json.loads(PRIORITY_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[request_index] WARN: rewrite_priority.json の読み込みに失敗しました: {e}")
        return []

    title_map = _title_to_stem_map()
    urls: list[str] = []
    for entry in entries:
        stem = title_map.get(entry.get("title", ""))
        if not stem:
            continue
        url = _slug_to_url(stem)
        if url not in exclude:
            urls.append(url)
    return urls


# ── IndexNow 送信 ─────────────────────────────────────────────────────────────

def _send(urls: list[str]) -> None:
    if not urls:
        print("[request_index] 送信対象の URL がありません。処理をスキップします。")
        return

    key = os.environ.get("INDEXNOW_KEY", "").strip()
    if not key:
        print("[request_index] SKIP: INDEXNOW_KEY が未設定です。インデックスリクエストをスキップします。")
        return

    host         = SITE_URL.removeprefix("https://").removeprefix("http://")
    key_location = f"{SITE_URL}/{key}.txt"
    payload = json.dumps({
        "host":        host,
        "key":         key,
        "keyLocation": key_location,
        "urlList":     urls,
    }).encode("utf-8")

    req = urllib.request.Request(
        INDEXNOW_EP,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            code = resp.status
            body = resp.read().decode()
    except urllib.error.HTTPError as e:
        code = e.code
        try:
            body = e.read().decode()
        except Exception:
            body = ""
    except Exception as e:
        print(f"[request_index] ERR: リクエスト失敗 — {e}")
        return

    if 200 <= code < 300:
        print(f"[request_index] OK ({code}): {len(urls)} URL を送信しました")
        for u in urls:
            print(f"  {u}")
    else:
        snippet = body[:300].replace("\n", " ")
        print(f"[request_index] WARN: HTTP {code} — {snippet}")
        print(f"  ※ インデックスリクエストは失敗しましたが処理を続行します")


# ── メイン ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="IndexNow へ URL 更新通知を送信する")
    parser.add_argument(
        "--urls", nargs="*", default=[],
        help="送信するURLを明示指定する（省略時は git diff から自動検出）",
    )
    args = parser.parse_args()

    if args.urls:
        new_urls = list(dict.fromkeys(args.urls))[:MAX_NEW]
        print(f"[request_index] 引数指定URL: {len(new_urls)} 件")
    else:
        new_urls = _new_urls_from_git()
        print(f"[request_index] git diff 検出URL: {len(new_urls)} 件")
    for u in new_urls:
        print(f"  {u}")

    priority_urls = _priority_urls(exclude=set(new_urls))
    print(f"[request_index] 優先度リストURL: {len(priority_urls)} 件")

    all_urls = list(dict.fromkeys(new_urls + priority_urls))
    print(f"[request_index] 送信対象 合計: {len(all_urls)} 件\n")

    _send(all_urls)


if __name__ == "__main__":
    main()
