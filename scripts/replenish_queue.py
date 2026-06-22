"""
queue.csv 自動補充スクリプト。

動作:
  1. content/posts/ と queue.csv からカバー済み (tool, code) を確認
  2. SEO API（スタブ）+ Gemini でトレンドキーワードを自律収集
  3. 未カバーの組み合わせをトレンド優先でソートして ADD_COUNT 件選択
  4. Gemini + Google検索で原因・解決策をリサーチ
  5. queue.csv に追記

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

from google import genai as google_genai
from google.genai import types as genai_types

ADD_COUNT = int(os.getenv("ADD_COUNT", "90"))

BASE       = Path(__file__).parent
POSTS_DIR  = BASE.parent / "content" / "posts"
QUEUE_PATH = BASE / "queue.csv"
TOOLS_PATH = BASE / "tools.json"

FIELDNAMES = ["tool", "status_code", "official_meaning", "causes", "solutions",
              "source_urls", "reported_versions", "actual_error_messages", "alternatives"]

# 対象エラーコード
ERROR_CODES = [
    "400", "401", "402", "403", "404", "405",
    "408", "409", "410", "422", "429",
    "500", "502", "503", "504",
]


# ─── SEO API インターフェース（DataForSEO / Ahrefs MCP 統合用） ────────────
#
# 日本市場パラメータ（全リクエストで強制適用・変更禁止）
SEO_LANGUAGE_CODE = "ja"
SEO_LOCATION_CODE = 2392  # Japan（ISO 3166-1 numeric）


class SEOApiClient:
    """外部 SEO ツール API ラッパー。

    DataForSEO MCP / Ahrefs Remote MCP 等との接続インターフェース。
    現在はスタブ（Gemini フォールバックを使用）。外部 API 接続時は
    各メソッドを実装するか、サブクラスでオーバーライドすること。

    全リクエストに SEO_LANGUAGE_CODE / SEO_LOCATION_CODE が強制付与される。
    """

    def __init__(self) -> None:
        self.language_code = SEO_LANGUAGE_CODE
        self.location_code = SEO_LOCATION_CODE
        self._base_params  = {
            "language_code": self.language_code,
            "location_code": self.location_code,
        }

    def get_search_volume(self, keyword: str) -> dict | None:
        """キーワードの月間検索ボリュームを取得する。

        DataForSEO 実装例:
            POST /v3/keywords_data/google_ads/search_volume/live
            body = {**self._base_params, "keywords": [keyword]}

        Ahrefs 実装例:
            POST /v3/keywords-explorer/overview
            body = {**self._base_params, "keyword": keyword}

        Returns:
            {"keyword": str, "volume": int, "competition": float} | None
        """
        # TODO: 外部 API 実装時にここを置き換える
        return None

    def get_trending_error_keywords(self, tool: str) -> list[dict]:
        """ツールに関連するトレンドエラーキーワードを取得する。

        DataForSEO 実装例:
            POST /v3/keywords_data/google_trends/explore/live
            body = {**self._base_params, "keywords": [f"{tool} error"]}

        Returns:
            [{"tool": str, "error_code": str, "volume": int, "trend": str}, ...]
        """
        # TODO: 外部 API 実装時にここを置き換える
        return []

    def get_rising_queries(self, technology: str) -> list[str]:
        """急上昇中の検索クエリを取得する（Google Trends 相当）。

        DataForSEO 実装例:
            POST /v3/keywords_data/google_trends/explore/live
            body = {**self._base_params, "keywords": [technology],
                    "type": "web_search", "category_code": 5}

        Returns:
            ["query1", "query2", ...]
        """
        # TODO: 外部 API 実装時にここを置き換える
        return []


# ─── トレンドキーワード収集 ──────────────────────────────────────────────────

# Gemini フォールバック対象のモダンテクノロジーリスト
_TREND_TECH = [
    "Next.js", "Podman", "Bun", "Deno", "Hono", "Astro", "Remix",
    "Turborepo", "Vite", "Prisma", "Supabase", "Vercel", "Cloudflare Workers",
]


def _collect_trending_with_gemini(
    gemini_client,
    tools: list[str],
    covered: set[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Gemini + Google Search で日本市場のトレンドエラーを自律収集する。

    SEO_LANGUAGE_CODE="ja" / SEO_LOCATION_CODE=2392 に対応する日本語クエリで検索。
    """
    trend_tools = [t for t in tools if t in _TREND_TECH] or tools[:5]
    results: list[tuple[str, str]] = []

    for tool in trend_tools[:4]:  # レート制限を考慮して上位4件のみ
        prompt = f"""日本のエンジニア（言語: ja / 地域: Japan）が最近「{tool}」で遭遇している
HTTPエラーコードを調べてください。

対象: Zenn, Qiita, Stack Overflow Japan, GitHub Issues, X（旧Twitter）での報告

以下のJSONのみ返してください（前置き不要）:
{{"trending_codes": ["404", "429"]}}

候補エラーコード: 400 401 402 403 404 405 408 409 410 422 429 500 502 503 504"""

        try:
            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())]
                ),
            )
            m = re.search(r'"trending_codes"\s*:\s*\[([^\]]*)\]', response.text)
            if not m:
                continue
            codes = [
                c.strip().strip('"').strip("'")
                for c in m.group(1).split(",")
                if c.strip().strip('"').strip("'")
            ]
            slug = tool_to_slug(tool)
            for code in codes:
                if code in ERROR_CODES and (slug, code) not in covered:
                    results.append((tool, code))
                    print(f"    トレンド検出: {tool} {code} (ja/Japan)")
        except Exception as e:
            print(f"    [WARN] トレンド収集失敗 ({tool}): {e}")

    return results


def collect_trending_keywords(
    seo_client: SEOApiClient,
    gemini_client,
    tools: list[str],
    covered: set[tuple[str, str]],
) -> list[tuple[str, str]]:
    """SEO API（実装済み時）+ Gemini でトレンドキーワードを収集する。

    Args:
        seo_client: SEOApiClient（スタブまたは実装済みクライアント）
        gemini_client: Gemini クライアント（フォールバック用）
        tools: ツールリスト
        covered: カバー済みペアのセット

    Returns:
        トレンドの (tool, error_code) タプルリスト（優先度順）
    """
    results: list[tuple[str, str]] = []

    # SEO API 経由でトレンド取得（API 実装済みの場合）
    for tool in tools[:20]:
        api_rows = seo_client.get_trending_error_keywords(tool)
        for row in api_rows:
            code = row.get("error_code", "")
            slug = tool_to_slug(tool)
            if code in ERROR_CODES and (slug, code) not in covered:
                results.append((tool, code))
                print(f"    SEO API トレンド: {tool} {code} (vol={row.get('volume', '?')})")

    # SEO API が空の場合は Gemini でフォールバック
    if not results:
        print("  SEO API スタブ中 — Gemini フォールバックでトレンド収集")
        results = _collect_trending_with_gemini(gemini_client, tools, covered)

    return results


# ─── ユーティリティ ──────────────────────────────────────────────────────────

def load_tools() -> list[str]:
    """tools.json からツールリストを読み込む。"""
    return json.loads(TOOLS_PATH.read_text(encoding="utf-8"))["tools"]


def tool_to_slug(tool: str) -> str:
    """ツール名をファイル名スラグに変換する。"""
    return tool.lower().replace(" ", "_")


def get_covered_pairs() -> set[tuple[str, str]]:
    """既存記事と queue.csv からカバー済みの (slug, code) ペアを返す。"""
    covered: set[tuple[str, str]] = set()

    for md in POSTS_DIR.glob("*.md"):
        stem = md.stem
        for code in ERROR_CODES:
            if stem.endswith(f"_{code}"):
                slug = stem[: -(len(code) + 1)]
                covered.add((slug, code))

    if QUEUE_PATH.exists() and QUEUE_PATH.stat().st_size > 0:
        with open(QUEUE_PATH, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                slug = tool_to_slug(row["tool"].strip())
                code = row["status_code"].strip()
                covered.add((slug, code))

    return covered


# ─── Gemini でリサーチ ───────────────────────────────────────────────────────

def research_with_gemini(
    gemini_client,
    tool: str,
    code: str,
) -> dict | None:
    """Gemini + Google検索で (tool, code) のエラー情報をリサーチする。

    日本市場パラメータ（SEO_LANGUAGE_CODE="ja", SEO_LOCATION_CODE=2392）に
    対応する日本語クエリを使用する。

    Returns:
        queue.csv の 1 行分の dict | None（需要なし・取得失敗時）
    """
    prompt = f"""GitHub Issues, Stack Overflow, Zenn, Qiita で「{tool} {code}」に関する
実際の問題報告を検索してください（対象地域: 日本 language=ja）。

## 需要フィルタリング
実際の問題報告が日本語・英語合わせて3件以上確認できない場合は
{{"skip": true}} のみ返してください。

## 確認できた場合の出力
以下の JSON のみ返してください（前置き・説明不要）:
{{
  "official_meaning": "{tool} における {code} の意味を1文（日本語）",
  "causes": [
    "{tool} 固有の原因1（実際の報告から）",
    "{tool} 固有の原因2（実際の報告から）",
    "{tool} 固有の原因3（実際の報告から）"
  ],
  "solutions": [
    "具体的な解決策1（コマンドや設定値を含む）",
    "具体的な解決策2",
    "具体的な解決策3"
  ],
  "source_urls": [
    "https://github.com/...",
    "https://stackoverflow.com/..."
  ],
  "alternatives": [
    "{tool} の代替となるツール名1（英語の正式名称で）",
    "{tool} の代替となるツール名2"
  ],
  "reported_versions": [
    "{tool} v2.3.1",
    "{tool} v3.0"
  ],
  "actual_error_messages": [
    "実際のエラーメッセージ文字列1（verbatim）",
    "実際のエラーメッセージ文字列2"
  ]
}}

source_urls は実在する URL のみ記載すること。見つからなければ空配列。
alternatives は {tool} の代替となる主要ツールを1〜3件。見つからなければ空配列。
actual_error_messages はログ・レスポンスボディ・コンソール出力の実文字列のみ。
架空のメッセージを生成しないこと。"""

    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())]
            ),
        )
        text = response.text.strip()

        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            print(f"    JSON が見つかりません: {text[:80]}")
            return None

        data = json.loads(m.group(0))

        if data.get("skip"):
            print("    需要なし（問題報告が確認できないためスキップ）")
            return None

        causes    = "|".join(str(c).strip() for c in data.get("causes",    [])[:5] if c)
        solutions = "|".join(str(s).strip() for s in data.get("solutions", [])[:5] if s)
        meaning   = str(data.get("official_meaning", "")).strip()

        if not (meaning and causes and solutions):
            print("    データ不足のためスキップ")
            return None

        return {
            "tool":                   tool,
            "status_code":            code,
            "official_meaning":       meaning,
            "causes":                 causes,
            "solutions":              solutions,
            "source_urls":            "|".join(str(u).strip() for u in data.get("source_urls", [])[:5] if u),
            "reported_versions":      "|".join(str(v).strip() for v in data.get("reported_versions", [])[:5] if v),
            "actual_error_messages":  "|".join(str(m).strip() for m in data.get("actual_error_messages", [])[:3] if m),
            "alternatives":           "|".join(str(a).strip() for a in data.get("alternatives", [])[:3] if a),
        }

    except json.JSONDecodeError as e:
        print(f"    JSON パースエラー: {e}")
        return None
    except Exception as e:
        print(f"    Gemini エラー: {e}")
        return None


# ─── メイン ─────────────────────────────────────────────────────────────────

def main() -> None:
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        print("エラー: GEMINI_API_KEY が設定されていません。")
        return

    gemini_client = google_genai.Client(api_key=gemini_key)
    seo_client    = SEOApiClient()

    tools   = load_tools()
    covered = get_covered_pairs()
    print(f"ツール数: {len(tools)} / カバー済み: {len(covered)} 件")
    print(f"SEO パラメータ: language={seo_client.language_code}, location={seo_client.location_code}")

    # トレンド優先のキーワード収集
    print("\nトレンドキーワードを収集中...")
    trending = collect_trending_keywords(seo_client, gemini_client, tools, covered)
    trending_set = {(tool_to_slug(t), c) for t, c in trending}
    print(f"トレンド候補: {len(trending)} 件\n")

    # 未カバーペアを列挙（トレンド以外）
    uncovered: list[tuple[str, str]] = []
    for tool in tools:
        slug = tool_to_slug(tool)
        for code in ERROR_CODES:
            if (slug, code) not in covered and (slug, code) not in trending_set:
                uncovered.append((tool, code))

    print(f"未カバー（トレンド除く）: {len(uncovered)} 件")

    if not uncovered and not trending:
        print("全ての組み合わせがカバー済みです。")
        return

    # トレンドを先頭に、残りをシャッフルして ADD_COUNT 件
    random.shuffle(uncovered)
    targets = (trending + uncovered)[:ADD_COUNT]

    print(f"\n{len(targets)} 件をリサーチします "
          f"（トレンド: {len(trending)} 件 / その他: {len(targets) - len(trending)} 件）...\n")

    results: list[dict] = []
    for i, (tool, code) in enumerate(targets, 1):
        print(f"  [{i:2d}/{len(targets)}] {tool} {code}")
        row = research_with_gemini(gemini_client, tool, code)
        if row:
            results.append(row)
            print(f"         → {row['official_meaning'][:50]}")
        else:
            print("         → スキップ")

    if not results:
        print("\n追加するデータがありません。")
        return

    # queue.csv に追記
    write_header = not (QUEUE_PATH.exists() and QUEUE_PATH.stat().st_size > 0)
    with open(QUEUE_PATH, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerows(results)

    print(f"\n完了: {len(results)} 件を queue.csv に追加しました。")


if __name__ == "__main__":
    main()
