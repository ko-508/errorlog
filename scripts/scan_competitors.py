"""
競合サイトの見出し構造を自動スクレイピングするスクリプト。

動作:
  1. rewrite_priority.json からスコア上位の top_query を取得
  2. Google 検索 (https://www.google.com/search?q=...) で上位 TOP_N_RESULTS 件の URL を抽出
  3. 各 URL をスクレイピングし title / H2 / H3 アウトラインを取得
  4. scripts/competitor_analysis.json に保存
  5. weekly_report.py が読み込めるフォーマットで出力

制約:
  - リクエスト間隔 DELAY_SECS 以上を保持（DoS 防止）
  - 403 / タイムアウト / JS 専用サイト等はスキップして空データで継続
  - beautifulsoup4 未インストール時は空データで正常終了

環境変数:
  COMPETITOR_TOP_N  分析クエリ数（デフォルト 5）
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

SCRIPTS_DIR      = Path(__file__).parent
PRIORITY_FILE    = SCRIPTS_DIR / "rewrite_priority.json"
COMPETITOR_FILE  = SCRIPTS_DIR / "competitor_analysis.json"

TOP_N_QUERIES    = int(os.getenv("COMPETITOR_TOP_N", "5"))
TOP_N_RESULTS    = 3
DELAY_SECS       = 1.5   # 最低 1 秒以上の礼儀的ディレイ
REQUEST_TIMEOUT  = 12

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent":      _UA,
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept":          "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
}

# beautifulsoup4 の有無を事前チェック
try:
    import requests
    from bs4 import BeautifulSoup
    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False


# ── クエリ取得 ────────────────────────────────────────────────────────────────

def _load_priority_queries(n: int) -> list[str]:
    """rewrite_priority.json の top_query フィールドをスコア上位 n 件返す。"""
    if not PRIORITY_FILE.exists():
        print("  [scan] rewrite_priority.json が存在しません。")
        return []
    try:
        entries: list[dict] = json.loads(PRIORITY_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [scan] rewrite_priority.json 読み込みエラー: {e}")
        return []

    queries: list[str] = []
    for entry in entries:
        q = (entry.get("top_query") or "").strip()
        if q and q not in queries:
            queries.append(q)
            if len(queries) >= n:
                break
    return queries


# ── Google 検索 → URL 抽出 ────────────────────────────────────────────────────

def _google_search(query: str) -> list[str]:
    """Google 検索から上位 TOP_N_RESULTS 件の外部 URL を返す。失敗時は空リスト。"""
    if not _HAS_BS4:
        return []
    try:
        encoded = urllib.parse.quote(query)
        url     = f"https://www.google.com/search?q={encoded}&num=10&hl=ja&gl=jp"

        resp = requests.get(url, headers=_HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            print(f"    [search] HTTP {resp.status_code} — スキップ")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        urls: list[str] = []

        for a in soup.find_all("a", href=True):
            href = a["href"]
            # Google が /url?q=ACTUAL_URL&sa=... 形式でラップしている
            if href.startswith("/url?q="):
                actual = urllib.parse.unquote(href[7:].split("&")[0])
            elif href.startswith("http"):
                actual = href
            else:
                continue

            if not actual.startswith("http"):
                continue
            # Google 自身・Youtube・同一ドメインは除外
            skip_domains = ("google.", "youtube.com", "googleapis.com",
                            "gstatic.com", "googletagmanager.com")
            if any(d in actual for d in skip_domains):
                continue
            if actual not in urls:
                urls.append(actual)
            if len(urls) >= TOP_N_RESULTS:
                break

        time.sleep(DELAY_SECS)
        return urls

    except Exception as e:
        print(f"    [search] Google 検索エラー: {e}")
        return []


# ── 競合ページのアウトライン抽出 ──────────────────────────────────────────────

def _scrape_outline(url: str) -> dict:
    """URL から title / H2 / H3 テキストを抽出する。エラー時は error フィールドを設定。"""
    result: dict = {"url": url, "title": "", "h2": [], "h3": [], "error": None}
    if not _HAS_BS4:
        result["error"] = "beautifulsoup4 unavailable"
        return result
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=REQUEST_TIMEOUT,
                            allow_redirects=True)
        if resp.status_code == 403:
            result["error"] = "403 Forbidden"
            return result
        if resp.status_code != 200:
            result["error"] = f"HTTP {resp.status_code}"
            return result

        # Content-Type が HTML 以外はスキップ
        ct = resp.headers.get("Content-Type", "")
        if "html" not in ct.lower():
            result["error"] = f"non-HTML ({ct})"
            return result

        soup = BeautifulSoup(resp.text, "html.parser")

        title_tag = soup.find("title")
        result["title"] = title_tag.get_text(strip=True)[:120] if title_tag else ""

        result["h2"] = [
            h.get_text(strip=True)[:100]
            for h in soup.find_all("h2")
            if h.get_text(strip=True)
        ][:10]

        result["h3"] = [
            h.get_text(strip=True)[:100]
            for h in soup.find_all("h3")
            if h.get_text(strip=True)
        ][:20]

        time.sleep(DELAY_SECS)
        return result

    except requests.exceptions.Timeout:
        result["error"] = "timeout"
        return result
    except Exception as e:
        result["error"] = str(e)[:120]
        return result


# ── 1 クエリ分の競合分析 ─────────────────────────────────────────────────────

def analyze_keyword(query: str) -> dict:
    """1 キーワードの競合調査（検索 + スクレイピング）を実行する。"""
    print(f"  クエリ: {query}")
    urls = _google_search(query)
    print(f"    検索結果: {len(urls)} 件")

    competitors: list[dict] = []
    for i, url in enumerate(urls, 1):
        print(f"    [{i}/{len(urls)}] {url[:70]}...")
        outline = _scrape_outline(url)
        if outline["error"]:
            print(f"      → エラー: {outline['error']}")
        else:
            print(f"      → H2: {len(outline['h2'])} 件 / H3: {len(outline['h3'])} 件")
        competitors.append(outline)

    return {"query": query, "competitors": competitors}


# ── Issue 用 Markdown ─────────────────────────────────────────────────────────

def format_for_report(results: list[dict]) -> str:
    """競合データを weekly_report.py の Issue 追記用 Markdown に変換する。"""
    if not results:
        return ""

    lines = ["", "---", "", "### 3. 競合構成分析（自動スクレイピング）", ""]
    for r in results:
        query = r.get("query", "")
        lines.append(f"#### クエリ: `{query}`")
        lines.append("")
        competitors = r.get("competitors", [])
        if not competitors:
            lines.append("_検索結果が取得できませんでした。_")
            lines.append("")
            continue
        for i, c in enumerate(competitors, 1):
            if c.get("error"):
                lines.append(f"**競合{i}** `{c['url'][:70]}` — {c['error']}")
            else:
                label = c.get("title") or c["url"][:70]
                lines.append(f"**競合{i}** {label}")
                if c.get("h2"):
                    lines.append("- H2: " + " / ".join(c["h2"][:5]))
                if c.get("h3"):
                    lines.append("- H3: " + " / ".join(c["h3"][:5]))
            lines.append("")

    return "\n".join(lines)


# ── エントリポイント ──────────────────────────────────────────────────────────

def main() -> None:
    today = date.today().isoformat()

    if not _HAS_BS4:
        print("[WARN] beautifulsoup4 が未インストールのため、競合分析をスキップします。")
        COMPETITOR_FILE.write_text(
            json.dumps({"generated_at": today, "results": [], "skipped": True},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return

    queries = _load_priority_queries(TOP_N_QUERIES)
    if not queries:
        print("競合分析対象のクエリがありません（rewrite_priority.json に top_query が未設定）。")
        COMPETITOR_FILE.write_text(
            json.dumps({"generated_at": today, "results": []},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return

    print(f"競合分析: {len(queries)} クエリ / 各 {TOP_N_RESULTS} サイトを調査")

    results: list[dict] = []
    for query in queries:
        try:
            results.append(analyze_keyword(query))
        except Exception as e:
            print(f"  [WARN] '{query}' の分析に失敗（スキップ）: {e}")

    output = {"generated_at": today, "results": results}
    COMPETITOR_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n保存: {COMPETITOR_FILE.name} ({len(results)} クエリ完了)")


if __name__ == "__main__":
    main()
