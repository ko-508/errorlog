"""
GA4 週次分析・Gemini改善提案エンジン

必要な環境変数（GitHub Secrets）:
  GA4_PROPERTY_ID          GA4プロパティID（数字のみ）
  GA4_OAUTH_CLIENT_ID      OAuthクライアントID
  GA4_OAUTH_CLIENT_SECRET  OAuthクライアントシークレット
  GA4_OAUTH_REFRESH_TOKEN  OAuthリフレッシュトークン
  GEMINI_API_KEY           Gemini API キー

実行:
  python scripts/ga4_analyzer.py
"""

import os
import sys
from datetime import date, timedelta
from pathlib import Path

# ── 出力先 ────────────────────────────────────────────────────────────────────
BASE        = Path(__file__).parent.parent
REPORTS_DIR = BASE / "reports" / "ga4"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

TODAY       = date.today()
REPORT_PATH = REPORTS_DIR / f"report_{TODAY.strftime('%Y%m%d')}.md"

# ── 設定 ──────────────────────────────────────────────────────────────────────
PROPERTY_ID   = os.environ.get("GA4_PROPERTY_ID", "").strip()
CLIENT_ID     = os.environ.get("GA4_OAUTH_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("GA4_OAUTH_CLIENT_SECRET", "").strip()
REFRESH_TOKEN = os.environ.get("GA4_OAUTH_REFRESH_TOKEN", "").strip()
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
TOP_PAGES     = 20
TOP_CITIES    = 15

# ── ノイズフィルタ設定 ─────────────────────────────────────────────────────────
NOISE_COUNTRY        = os.environ.get("NOISE_COUNTRY", "Singapore")
NOISE_TIME_THRESHOLD = float(os.environ.get("NOISE_TIME_THRESHOLD", "5.0"))  # 秒
TOP_COUNTRIES        = 15


# ── OAuth2 認証 ───────────────────────────────────────────────────────────────

def _build_credentials():
    from google.oauth2.credentials import Credentials
    return Credentials(
        token=None,
        refresh_token=REFRESH_TOKEN,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/analytics.readonly"],
    )


def _ga4_client():
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    creds = _build_credentials()
    return BetaAnalyticsDataClient(credentials=creds)


# ── GA4 データ取得 ────────────────────────────────────────────────────────────

def _run_report(client, dimensions: list, metrics: list, days: int = 7) -> list[dict]:
    from google.analytics.data_v1beta.types import (
        DateRange, Dimension, Metric, RunReportRequest,
    )
    end   = TODAY.strftime("%Y-%m-%d")
    start = (TODAY - timedelta(days=days - 1)).strftime("%Y-%m-%d")

    req = RunReportRequest(
        property=f"properties/{PROPERTY_ID}",
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metrics],
        date_ranges=[DateRange(start_date=start, end_date=end)],
    )
    response = client.run_report(req)
    dim_names = [h.name for h in response.dimension_headers]
    met_names = [h.name for h in response.metric_headers]

    rows = []
    for row in response.rows:
        r = {}
        for i, v in enumerate(row.dimension_values):
            r[dim_names[i]] = v.value
        for i, v in enumerate(row.metric_values):
            try:
                r[met_names[i]] = float(v.value)
            except (ValueError, TypeError):
                r[met_names[i]] = 0.0
        rows.append(r)
    return rows


# ── ノイズフィルタ ─────────────────────────────────────────────────────────────

def _drop_noise(
    rows: list[dict],
    *,
    country_col: str = "country",
    time_col: str    = "averageSessionDuration",
) -> list[dict]:
    """
    country == NOISE_COUNTRY かつ engagement_time < NOISE_TIME_THRESHOLD の行を除去する。
    対象カラムが存在しない場合は安全にスキップする（KeyError でクラッシュしない）。
    """
    if not rows:
        return rows

    sample       = rows[0]
    has_country  = country_col in sample
    has_time     = time_col    in sample

    if not has_country or not has_time:
        missing = [c for c, ok in [(country_col, has_country), (time_col, has_time)] if not ok]
        print(f"  [noise_filter] カラム {missing} が存在しないためスキップします。")
        return rows

    clean: list[dict]   = []
    dropped: list[dict] = []
    for r in rows:
        if r.get(country_col, "") == NOISE_COUNTRY and r.get(time_col, 0.0) < NOISE_TIME_THRESHOLD:
            dropped.append(r)
        else:
            clean.append(r)

    if dropped:
        noise_users = sum(int(r.get("activeUsers", 0)) for r in dropped)
        print(
            f"  [noise_filter] 除外されたノイズ: {len(dropped)} 行 "
            f"(国={NOISE_COUNTRY}, エンゲージ時間<{NOISE_TIME_THRESHOLD}s, "
            f"影響ユーザー数={noise_users})"
        )
    else:
        print(
            f"  [noise_filter] ノイズなし "
            f"({NOISE_COUNTRY} の短時間セッションは検出されませんでした)"
        )

    return clean


def fetch_ga4_data(client) -> dict:
    print("GA4データ取得中...")

    daily = _run_report(client, ["date"], ["activeUsers", "newUsers", "sessions"])
    daily.sort(key=lambda r: r.get("date", ""))

    pages = _run_report(
        client,
        ["pagePath", "pageTitle"],
        ["screenPageViews", "averageSessionDuration", "engagementRate"],
    )
    pages.sort(key=lambda r: -r.get("screenPageViews", 0))
    pages = pages[:TOP_PAGES]

    cities = _run_report(client, ["city"], ["activeUsers"])
    cities.sort(key=lambda r: -r.get("activeUsers", 0))
    cities = cities[:TOP_CITIES]

    # 国別データ（country + averageSessionDuration）を取得してノイズ除去
    print("  国別データのノイズフィルタリング...")
    countries = _run_report(
        client,
        ["country"],
        ["activeUsers", "averageSessionDuration"],
    )
    countries = _drop_noise(countries)
    countries.sort(key=lambda r: -r.get("activeUsers", 0))
    countries = countries[:TOP_COUNTRIES]

    print(
        f"  日別:{len(daily)}件 / ページ:{len(pages)}件 "
        f"/ 都市:{len(cities)}件 / 国別(フィルタ済):{len(countries)}件"
    )
    return {"daily": daily, "pages": pages, "cities": cities, "countries": countries}


# ── データ整形 ────────────────────────────────────────────────────────────────

def _totals(daily: list[dict]) -> dict:
    if not daily:
        return {"active": 0, "new": 0, "sessions": 0}
    return {
        "active":   sum(int(r.get("activeUsers", 0)) for r in daily),
        "new":      sum(int(r.get("newUsers",    0)) for r in daily),
        "sessions": sum(int(r.get("sessions",    0)) for r in daily),
    }


def _fmt_daily(daily):
    lines = ["日付,アクティブUU,新規UU,セッション"]
    for r in daily:
        lines.append(
            f"{r.get('date','')},{int(r.get('activeUsers',0))},"
            f"{int(r.get('newUsers',0))},{int(r.get('sessions',0))}"
        )
    return "\n".join(lines)


def _fmt_pages(pages):
    lines = ["ページパス,PV,エンゲージ時間(秒),エンゲージ率"]
    for r in pages:
        lines.append(
            f"{r.get('pagePath','')},{int(r.get('screenPageViews',0))},"
            f"{r.get('averageSessionDuration',0):.1f},"
            f"{r.get('engagementRate',0):.2f}"
        )
    return "\n".join(lines)


def _fmt_cities(cities):
    lines = ["都市,アクティブUU"]
    for r in cities:
        lines.append(f"{r.get('city','')},{int(r.get('activeUsers',0))}")
    return "\n".join(lines)


def _fmt_countries(countries):
    lines = ["国,アクティブUU,平均エンゲージ時間(秒)"]
    for r in countries:
        lines.append(
            f"{r.get('country','')},{int(r.get('activeUsers',0))},"
            f"{r.get('averageSessionDuration',0):.1f}"
        )
    return "\n".join(lines)


# ── Gemini 分析 ───────────────────────────────────────────────────────────────

def analyze_with_gemini(data: dict) -> str:
    if not ANTHROPIC_KEY:
        return "（ANTHROPIC_API_KEY 未設定のため AI 分析をスキップ）"

    import anthropic

    client  = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    totals  = _totals(data["daily"])
    period  = f"{TODAY - timedelta(days=6)} 〜 {TODAY}"

    prompt = f"""以下はerrorlog.jp（技術エラーコード解説ブログ）の過去7日間（{period}）のGA4実績データです。
このデータのみを根拠として、以下3つの観点で構造化分析を行ってください。

=== 集計サマリー ===
アクティブユーザー合計: {totals['active']}
新規ユーザー合計: {totals['new']}
セッション合計: {totals['sessions']}

=== 日別推移（CSV）===
{_fmt_daily(data['daily'])}

=== ページ別パフォーマンス（上位{TOP_PAGES}件）===
{_fmt_pages(data['pages'])}

=== 都市別ユーザー（上位{TOP_CITIES}件）===
{_fmt_cities(data['cities'])}

=== 国別ユーザー（ノイズ除去済・上位{TOP_COUNTRIES}件）===
{_fmt_countries(data['countries'])}

## 出力要件（Markdown形式、##見出し使用）

### 1. アクセス分析：伸びた記事と原因の因果関係
PV上位3記事を特定し、アクセスが集まった理由をデータから論理的に推論する。
地域データと組み合わせて流入特性も分析する。

### 2. エンゲージメント改善：離脱リスクページの特定と具体策
エンゲージメント時間が短いページ（下位3件）を特定する。
errorlog.jpの記事規格（生ログ例・Before/Afterコード対比）に沿った具体的な改善案を提示する。

### 3. コンテンツ戦略：次に書くべき高価値記事の提案
現在のページ構成から手薄なツール・エラーコードを特定する。
次の1週間で優先的に書くべき記事テーマを3件、根拠とともに提案する。

### 4. 最重要アクション（1文）
上記分析全体で最も優先度が高い改善アクションを1文で出力する。
"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=(
            "あなたはWebメディアのグロースアナリストです。"
            "提供されたGA4データのみを根拠に分析し、ソースにない情報は推測しないこと。"
            "出力はMarkdown形式で、見出しは##を使用すること。"
        ),
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


# ── レポート生成 ──────────────────────────────────────────────────────────────

def build_report(data: dict, analysis: str) -> str:
    totals = _totals(data["daily"])
    period = f"{TODAY - timedelta(days=6)} 〜 {TODAY}"

    lines = [
        f"# GA4 週次分析レポート {TODAY.strftime('%Y-%m-%d')}",
        f"\n**集計期間:** {period}  ",
        f"**アクティブユーザー:** {totals['active']}  ",
        f"**新規ユーザー:** {totals['new']}  ",
        f"**セッション数:** {totals['sessions']}",
        "\n---\n",
        "## 生データ：日別ユーザー推移\n",
        "| 日付 | アクティブUU | 新規UU | セッション |",
        "|------|------------|-------|----------|",
    ]
    for r in data["daily"]:
        lines.append(
            f"| {r.get('date','')} | {int(r.get('activeUsers',0))} "
            f"| {int(r.get('newUsers',0))} | {int(r.get('sessions',0))} |"
        )

    lines += [
        "\n## 生データ：ページ別パフォーマンス（上位10件）\n",
        "| ページ | PV | エンゲージ時間(秒) | エンゲージ率 |",
        "|--------|-----|----------------|------------|",
    ]
    for r in data["pages"][:10]:
        path = r.get("pagePath", "")[:50]
        lines.append(
            f"| {path} | {int(r.get('screenPageViews',0))} "
            f"| {r.get('averageSessionDuration',0):.1f} "
            f"| {r.get('engagementRate',0):.2f} |"
        )

    lines += [
        "\n## 生データ：都市別ユーザー\n",
        "| 都市 | アクティブUU |",
        "|------|------------|",
    ]
    for r in data["cities"]:
        lines.append(f"| {r.get('city','')} | {int(r.get('activeUsers',0))} |")

    lines += [
        f"\n## 生データ：国別ユーザー（ノイズ除去済 / {NOISE_COUNTRY}・{NOISE_TIME_THRESHOLD}s未満を除外）\n",
        "| 国 | アクティブUU | 平均エンゲージ時間(秒) |",
        "|----|------------|---------------------|",
    ]
    for r in data["countries"]:
        lines.append(
            f"| {r.get('country','')} | {int(r.get('activeUsers',0))} "
            f"| {r.get('averageSessionDuration',0):.1f} |"
        )

    lines += ["\n---\n", "## AI分析レポート（Gemini）\n", analysis]
    return "\n".join(lines)


# ── エントリポイント ───────────────────────────────────────────────────────────

def main():
    missing = [k for k, v in {
        "GA4_PROPERTY_ID": PROPERTY_ID,
        "GA4_OAUTH_CLIENT_ID": CLIENT_ID,
        "GA4_OAUTH_CLIENT_SECRET": CLIENT_SECRET,
        "GA4_OAUTH_REFRESH_TOKEN": REFRESH_TOKEN,
    }.items() if not v]
    if missing:
        print(f"[ERROR] 未設定の環境変数: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    client   = _ga4_client()
    data     = fetch_ga4_data(client)

    print("Claude分析中...")
    analysis = analyze_with_gemini(data)

    report = build_report(data, analysis)
    REPORT_PATH.write_text(report, encoding="utf-8")

    import re
    m = re.search(r"#{2,4}\s*4[^\n]*\n+[-・*]?\s*(.+)", analysis)
    top_action = m.group(1).strip() if m else analysis.split("\n")[-1].strip() or "（抽出できませんでした）"

    print(f"\n✅ レポート保存: {REPORT_PATH.relative_to(BASE)}")
    print(f"🎯 最重要アクション: {top_action}\n")


if __name__ == "__main__":
    main()
