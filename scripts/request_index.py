"""
Google Indexing API へ URL_UPDATED リクエストを送信する。

動作:
  1. git diff HEAD~1..HEAD で新規・更新記事のURLを最大 MAX_NEW 件取得（優先枠）
  2. rewrite_priority.json のスコア上位から残り枠を補充
  3. 合計 MAX_PER_RUN(=10) 件にハードキャップして送信
  4. 429 / 403 はキャッチしてログ出力後に正常終了（ワークフローを赤にしない）

環境変数:
  INDEXING_SERVICE_ACCOUNT_KEY  サービスアカウント JSON 文字列（必須）
  SITE_URL                      サイト URL（デフォルト: https://errorlog.jp）

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

MAX_PER_RUN    = 10   # 1回の実行で送信する絶対上限
MAX_NEW        = 3    # git diff 由来（新規/更新）URLの優先枠

SITE_URL       = os.getenv("SITE_URL", "https://errorlog.jp").rstrip("/")
INDEXING_EP    = "https://indexing.googleapis.com/v3/urlNotifications:publish"
INDEXING_SCOPE = "https://www.googleapis.com/auth/indexing"

BASE          = Path(__file__).resolve().parent.parent
POSTS_DIR     = BASE / "content" / "posts"
PRIORITY_FILE = BASE / "scripts" / "rewrite_priority.json"


# ── 認証 ──────────────────────────────────────────────────────────────────────

def _credentials():
    sa_key = os.environ.get("INDEXING_SERVICE_ACCOUNT_KEY", "").strip()
    if not sa_key:
        print("[request_index] SKIP: INDEXING_SERVICE_ACCOUNT_KEY が未設定です。インデックスリクエストをスキップします。")
        sys.exit(0)
    try:
        from google.oauth2.service_account import Credentials
        return Credentials.from_service_account_info(
            json.loads(sa_key), scopes=[INDEXING_SCOPE]
        )
    except Exception as e:
        print(f"[request_index] WARN: サービスアカウント認証の初期化に失敗しました: {e}")
        sys.exit(0)


# ── URL 解決 ──────────────────────────────────────────────────────────────────

def _slug_to_url(slug: str) -> str:
    return f"{SITE_URL}/posts/{slug}/"


def _path_to_url(path: str) -> str | None:
    """content/posts/foo_bar.md → https://errorlog.jp/posts/foo_bar/"""
    p = Path(path)
    if p.suffix != ".md":
        return None
    return _slug_to_url(p.stem)


def _new_urls_from_git() -> list[str]:
    """直前コミットで追加・変更されたポスト記事の URL を返す（最大 MAX_NEW 件）。"""
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
    """title → stem のマップを content/posts/ 全体から構築する。"""
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


def _priority_urls(exclude: set[str], budget: int) -> list[str]:
    """rewrite_priority.json のスコア上位エントリを URL に変換して返す。"""
    if budget <= 0 or not PRIORITY_FILE.exists():
        return []
    try:
        entries: list[dict] = json.loads(PRIORITY_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[request_index] WARN: rewrite_priority.json の読み込みに失敗しました: {e}")
        return []

    title_map = _title_to_stem_map()
    urls: list[str] = []
    for entry in entries:  # critical→高スコア順に並んでいる前提
        if len(urls) >= budget:
            break
        stem = title_map.get(entry.get("title", ""))
        if not stem:
            continue
        url = _slug_to_url(stem)
        if url not in exclude:
            urls.append(url)
    return urls


# ── Indexing API 呼び出し ────────────────────────────────────────────────────

def _notify_one(creds, url: str) -> tuple[bool, int, str]:
    """(success, http_status, body) を返す。例外はすべて吸収する。"""
    try:
        import google.auth.transport.requests as ga_transport
        creds.refresh(ga_transport.Request())
    except Exception as e:
        return False, 0, f"トークンリフレッシュ失敗: {e}"

    payload = json.dumps({"url": url, "type": "URL_UPDATED"}).encode()
    req = urllib.request.Request(
        INDEXING_EP,
        data=payload,
        headers={
            "Authorization": f"Bearer {creds.token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return True, resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode()
        except Exception:
            pass
        return False, e.code, body
    except Exception as e:
        return False, 0, str(e)


def _send(urls: list[str]) -> None:
    if not urls:
        print("[request_index] 送信対象の URL がありません。処理をスキップします。")
        return

    creds = _credentials()
    ok = warn = 0

    for url in urls:
        success, code, body = _notify_one(creds, url)
        if success:
            print(f"  [OK ]  {url}")
            ok += 1
        else:
            snippet = body[:300].replace("\n", " ")
            if code == 429:
                print(f"  [429]  {url}  — クォータ超過。本日の残枠が不足しています。({snippet})")
            elif code == 403:
                print(f"  [403]  {url}  — 権限エラー。サービスアカウントの Indexing API 権限を確認してください。({snippet})")
            else:
                print(f"  [ERR]  {url}  — HTTP {code}: {snippet}")
            warn += 1

    print(f"\n[request_index] 完了: 成功 {ok} 件 / 警告 {warn} 件 / 計 {len(urls)} 件")


# ── メイン ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Google Indexing API へ URL_UPDATED リクエストを送信する")
    parser.add_argument(
        "--urls", nargs="*", default=[],
        help="送信するURLを明示指定する（省略時は git diff から自動検出）",
    )
    args = parser.parse_args()

    # 1. 新規・更新 URL（優先枠 MAX_NEW 件）
    if args.urls:
        new_urls = list(dict.fromkeys(args.urls))[:MAX_NEW]
        print(f"[request_index] 引数指定URL: {len(new_urls)} 件")
    else:
        new_urls = _new_urls_from_git()
        print(f"[request_index] git diff 検出URL: {len(new_urls)} 件")
    for u in new_urls:
        print(f"  {u}")

    # 2. 優先度リストから残り枠を補充
    budget = MAX_PER_RUN - len(new_urls)
    priority_urls = _priority_urls(exclude=set(new_urls), budget=budget)
    print(f"[request_index] 優先度リストURL: {len(priority_urls)} 件")
    for u in priority_urls:
        print(f"  {u}")

    # 3. 統合・ハードキャップ・送信
    all_urls = (new_urls + priority_urls)[:MAX_PER_RUN]
    print(f"[request_index] 送信対象 合計: {len(all_urls)} 件（上限 {MAX_PER_RUN} 件）")
    print()

    _send(all_urls)


if __name__ == "__main__":
    main()
