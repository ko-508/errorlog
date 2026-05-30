"""
GA4 週次分析・Gemini改善提案エンジン

必要な環境変数:
  GA4_PROPERTY_ID       GA4プロパティID（数字のみ。例: 123456789）
  GA4_CREDENTIALS_JSON  サービスアカウントキーのJSON文字列
  GEMINI_API_KEY        Gemini API キー

実行:
  python scripts/ga4_analyzer.py
"""

import json
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

# ── 出力先 ────────────────────────────────────────────────────────────────────
BASE        = Path(__file__).parent.parent
REPORTS_DIR = BASE / "reports" / "ga4"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

TODAY      = date.today()
REPORT_PATH = REPORTS_DIR / f"report_{TODAY.strftime('%Y%m%d')}.md"

# ── 設定 ──────────────────────────────────────────────────────────────────────
PROPERTY_ID   = os.environ.get("GA4_PROPERTY_ID", "").strip()
CREDENTIALS   = os.environ.get("GA4_CREDENTIALS_JSON", "").strip()
GEMINI_KEY    = os.environ.get("GEMINI_API_KEY", "").strip()
TOP_PAGES     = 20   # ページ別レポートの上限件数
TOP_CITIES    = 15   # 都市別レポートの上限件数


# ── GA4 認証セットアップ ───────────────────────────────────────────────────────

def _setup_credentials() -> str | None:
    """サービスアカウントJSONを一時ファイルに書き出し、パスを返す。"""
    if not CREDENTIALS:
        return None
    try:
        json.loads(CREDENTIALS)  # 壊れたJSONを早期検出
    except json.JSONDecodeError as e:
        print(f"[ERROR] GA4_CREDENTIALS_JSON のJSONが不正です: {e}", file=sys.stderr)
        sys.exit(1)
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    tmp.write(CREDENTIALS)
    tmp.flush()
    return tmp.name


# ── GA4 データ取得 ────────────────────────────────────────────────────────────

def _ga4_client(cred_path: str | None):
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    if cred_path:
        return BetaAnalyticsDataClient.from_service_account_file(cred_path)
    return BetaAnalyticsDataClient()  # Application Default Credentials


def _run_report(client, property_id: str, dimensions: list, metrics: list,
                date_range_days: int = 7) -> list[dict]:
    from google.analytics.data_v1beta.types import (
        DateRange, Dimension, Metric, RunReportRequest,
    )
    end   = TODAY.strftime("%Y-%m-%d")
    start = (TODAY - timedelta(days=date_range_days - 1)).strftime("%Y-%m-%d")

    req = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metrics],
        date_ranges=[DateRange(start_date=start, end_date=end)],
    )
    response = client.run_report(req)

    dim_names  = [h.name for h in response.dimension_headers]
    met_names  = [h.name for h in response.metric_headers]
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


def fetch_ga4_data(client, pid: str) -> dict:
    print("GA4データ取得中...")

    # 1. 日別ユーザー推移
    daily = _run_report(
        client, pid,
        dimensions=["date"],
        metrics=["activeUsers", "newUsers", "sessions"],
    )
    daily.sort(key=lambda r: r.get("date", ""))

    # 2. ページ別PV・エンゲージメント
    pages = _run_report(
        client, pid,
        dimensions=["pagePath", "pageTitle"],
        metrics=["screenPageViews", "averageSessionDuration", "engagementRate"],
    )
    pages.sort(key=lambda r: -r.get("screenPageViews", 0))
    pages = pages[:TOP_PAGES]

    # 3. 都市別ユーザー
    cities = _run_report(
        client, pid,
        dimensions=["city"],
        metrics=["activeUsers"],
    )
    cities.sort(key=lambda r: -r.get("activeUsers", 0))
    cities = cities[:TOP_CITIES]

    return {"daily": daily, "pages": pages, "cities": cities}


# ── データ → テキストブロック ──────────────────────────────────────────────────

def _fmt_daily(daily: list[dict]) -> str:
    lines = ["日付,アクティブユーザー,新規ユーザー,セッション数"]
    for r in daily:
        lines.append(
            f"{r.get('date','')},{int(r.get('activeUsers',0))},"
            f"{int(r.get('newUsers',0))},{int(r.get('sessions',0))}"
        )
    return "\n".join(lines)


def _fmt_pages(pages: list[dict]) -> str:
    lines = ["ページパス,PV数,平均エンゲージメント時間(秒),エンゲージメント率"]
    for r in pages:
        lines.append(
            f"{r.get('pagePath','')},{int(r.get('screenPageViews',0))},"
            f"{r.get('averageSessionDuration',0):.1f},"
            f"{r.get('engagementRate',0):.2f}"
        )
    return "\n".join(lines)


def _fmt_cities(cities: list[dict]) -> str:
    lines = ["都市,アクティブユーザー"]
    for r in cities:
        lines.append(f"{r.get('city','')},{int(r.get('activeUsers',0))}")
    return "\n".join(lines)


def _totals(daily: list[dict]) -> dict:
    if not daily:
        return {"active": 0, "new": 0, "sessions": 0}
    return {
        "active":   sum(int(r.get("activeUsers", 0)) for r in daily),
        "new":      sum(int(r.get("newUsers",    0)) for r in daily),
        "sessions": sum(int(r.get("sessions",    0)) for r in daily),
    }


# ── Gemini 分析 ───────────────────────────────────────────────────────────────

_SYSTEM = (
    "あなたはWebメディアのグロースアナリストです。"
    "提供されたGA4の生データのみを根拠に分析し、ソースにない情報は推測しないこと。"
    "出力はMarkdown形式で、見出しは##を使用すること。"
)


def analyze_with_gemini(data: dict) -> str:
    if not GEMINI_KEY:
        return "（GEMINI_API_KEY 未設定のため AI 分析をスキップ）"

    from google import genai
    from google.genai import types

    client  = genai.Client(api_key=GEMINI_KEY)
    totals  = _totals(data["daily"])
    period  = f"{TODAY - timedelta(days=6)} 〜 {TODAY}"

    prompt = f"""以下はerrorlog.jp（技術エラーコード解説ブログ）の過去7日間（{period}）のGA4実績データです。
このデータのみを根拠として、以下3つの観点で構造化分析を行ってください。

=== 集計サマリー ===
期間合計アクティブユーザー: {totals['active']}
期間合計新規ユーザー: {totals['new']}
期間合計セッション数: {totals['sessions']}

=== 日別ユーザー推移（CSV）===
{_fmt_daily(data['daily'])}

=== ページ別パフォーマンス（上位{TOP_PAGES}件、CSV）===
{_fmt_pages(data['pages'])}

=== 都市別ユーザー（上位{TOP_CITIES}件、CSV）===
{_fmt_cities(data['cities'])}

## 出力要件（厳守）

### 1. アクセス分析：伸びた記事と原因の因果関係
- PV上位3記事を特定し、アクセスが集まった理由をデータから論理的に推論する
- 地域分布データと組み合わせて流入特性を分析する

### 2. エンゲージメント改善：離脱リスクページの特定と具体策
- 平均エンゲージメント時間が短いページ（下位3件）を特定する
- errorlog.jp の記事規格（生のログ例・Before/Afterコード対比）に沿った具体的な改善案を提示する

### 3. コンテンツ戦略：次に狙うべき高価値キーワード配分の最適化案
- 現在のページ構成から手薄なツール・エラーコードを特定する
- 次の1週間で優先的に書くべき記事テーマを3件、根拠とともに提案する

### 4. 最重要アクション（1行）
- 上記分析全体で最も優先度が高い改善アクションを1文で出力する
"""

    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM,
            temperature=0.3,
            max_output_tokens=4096,
        ),
    )
    return response.text


# ── レポート生成 ──────────────────────────────────────────────────────────────

def build_report(data: dict, analysis: str) -> str:
    totals = _totals(data["daily"])
    period = f"{TODAY - timedelta(days=6)} 〜 {TODAY}"

    sections = [
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
        sections.append(
            f"| {r.get('date','')} | {int(r.get('activeUsers',0))} "
            f"| {int(r.get('newUsers',0))} | {int(r.get('sessions',0))} |"
        )

    sections += [
        "\n## 生データ：ページ別パフォーマンス（上位）\n",
        "| ページ | PV | エンゲージ時間(秒) | エンゲージ率 |",
        "|--------|-----|----------------|------------|",
    ]
    for r in data["pages"][:10]:
        path = r.get("pagePath", "")[:50]
        sections.append(
            f"| {path} | {int(r.get('screenPageViews',0))} "
            f"| {r.get('averageSessionDuration',0):.1f} "
            f"| {r.get('engagementRate',0):.2f} |"
        )

    sections += [
        "\n## 生データ：都市別ユーザー\n",
        "| 都市 | アクティブUU |",
        "|------|------------|",
    ]
    for r in data["cities"]:
        sections.append(f"| {r.get('city','')} | {int(r.get('activeUsers',0))} |")

    sections += [
        "\n---\n",
        "## AI分析レポート（Gemini）\n",
        analysis,
    ]
    return "\n".join(sections)


# ── エントリポイント ───────────────────────────────────────────────────────────

def main():
    if not PROPERTY_ID:
        print("[ERROR] GA4_PROPERTY_ID が未設定です。", file=sys.stderr)
        sys.exit(1)

    cred_path = _setup_credentials()
    try:
        client   = _ga4_client(cred_path)
        data     = fetch_ga4_data(client, PROPERTY_ID)
        print(f"  日別: {len(data['daily'])}件 / ページ: {len(data['pages'])}件 / 都市: {len(data['cities'])}件")

        print("Gemini分析中...")
        analysis = analyze_with_gemini(data)

        report = build_report(data, analysis)
        REPORT_PATH.write_text(report, encoding="utf-8")

        # 最重要アクションを抽出してターミナルに表示
        import re
        m = re.search(r"### 4[^\n]*\n+[-・]?\s*(.+)", analysis)
        top_action = m.group(1).strip() if m else "（抽出できませんでした）"

        print(f"\n✅ レポート保存: {REPORT_PATH.relative_to(BASE)}")
        print(f"🎯 最重要アクション: {top_action}\n")

    finally:
        if cred_path:
            import os as _os
            _os.unlink(cred_path)


if __name__ == "__main__":
    main()
