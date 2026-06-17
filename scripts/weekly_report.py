"""
週次統合レポート生成スクリプト
GA4 トラフィック指標 + GSC サイト全体サマリー + GSC ボトルネック → GitHub Issue 用 Markdown

出力: reports/ga4/weekly_report_YYYYMMDD.json
  { "generated_at": "...", "issue_title": "...", "issue_body": "..." }

環境変数:
  GA4_PROPERTY_ID          GA4プロパティID
  GA4_SERVICE_ACCOUNT_KEY  サービスアカウントJSON（優先）
  GA4_OAUTH_CLIENT_ID      OAuthフォールバック
  GA4_OAUTH_CLIENT_SECRET
  GA4_OAUTH_REFRESH_TOKEN
  GSC_SITE_URL             Search ConsoleサイトURL
  GSC_SERVICE_ACCOUNT_KEY  SAキー（優先）
  GSC_OAUTH_REFRESH_TOKEN  OAuthフォールバック
"""

import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

BASE        = Path(__file__).parent.parent
REPORTS_DIR = BASE / "reports" / "ga4"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

TODAY       = date.today()
PROPERTY_ID = os.environ.get("GA4_PROPERTY_ID", "").strip()
SITE_URL    = os.environ.get("GSC_SITE_URL", "https://errorlog.jp/")
REPORT_FILE = REPORTS_DIR / f"weekly_report_{TODAY.strftime('%Y%m%d')}.json"

# ── GSC thresholds ────────────────────────────────────────────────────────────
CTR_IMP_THRESHOLD = int(os.getenv("CTR_IMP_THRESHOLD", "10"))
CTR_THRESHOLD     = float(os.getenv("CTR_THRESHOLD",   "0.015"))
POS_IMP_THRESHOLD = int(os.getenv("POS_IMP_THRESHOLD", "5"))
POS_MIN           = float(os.getenv("POS_MIN",          "11.0"))
POS_MAX           = float(os.getenv("POS_MAX",          "20.0"))

# ── 国別分布セクション（継続観測・ボット判定の参考。断定ではない）─────────────
TOP_COUNTRIES = int(os.getenv("TOP_COUNTRIES", "10"))
# 平均エンゲージ時間の閾値は ga4_analyzer.py のチャネル別ボット判定参考（Direct, dur<10）に揃えた。
_COUNTRY_ENGAGEMENT_TIME_THRESHOLD = float(os.getenv("COUNTRY_ENGAGEMENT_TIME_THRESHOLD", "10.0"))
# 直帰率の閾値は既存に倣う基準がないため仮値。実態運用を見ながら調整すること。
_COUNTRY_BOUNCE_RATE_THRESHOLD = float(os.getenv("COUNTRY_BOUNCE_RATE_THRESHOLD", "0.90"))


# ── GA4 Auth ──────────────────────────────────────────────────────────────────

def _build_ga4_client():
    from google.analytics.data_v1beta import BetaAnalyticsDataClient

    sa_json = os.environ.get("GA4_SERVICE_ACCOUNT_KEY", "").strip()
    if sa_json:
        from google.oauth2.service_account import Credentials
        info  = json.loads(sa_json)
        creds = Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/analytics.readonly"]
        )
        return BetaAnalyticsDataClient(credentials=creds)

    from google.oauth2.credentials import Credentials
    creds = Credentials(
        token=None,
        refresh_token=os.environ.get("GA4_OAUTH_REFRESH_TOKEN", ""),
        client_id=os.environ.get("GA4_OAUTH_CLIENT_ID", ""),
        client_secret=os.environ.get("GA4_OAUTH_CLIENT_SECRET", ""),
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/analytics.readonly"],
    )
    return BetaAnalyticsDataClient(credentials=creds)


# ── GA4 Data API helpers ──────────────────────────────────────────────────────

def _japan_filter():
    from google.analytics.data_v1beta.types import FilterExpression, Filter
    return FilterExpression(
        filter=Filter(
            field_name="country",
            string_filter=Filter.StringFilter(
                match_type=Filter.StringFilter.MatchType.EXACT,
                value="Japan",
            ),
        )
    )


def _host_filter():
    from google.analytics.data_v1beta.types import FilterExpression, Filter
    return FilterExpression(
        filter=Filter(
            field_name="hostName",
            string_filter=Filter.StringFilter(
                match_type=Filter.StringFilter.MatchType.CONTAINS,
                value="errorlog.jp",
            ),
        )
    )


def _and_filter(*filters):
    from google.analytics.data_v1beta.types import FilterExpression, FilterExpressionList
    return FilterExpression(
        and_group=FilterExpressionList(expressions=list(filters))
    )


def _date_range_ga4():
    return (
        (TODAY - timedelta(days=9)).strftime("%Y-%m-%d"),
        (TODAY - timedelta(days=3)).strftime("%Y-%m-%d"),
    )


def _run_report(client, dimensions, metrics, row_limit=100, dim_filter=None):
    from google.analytics.data_v1beta.types import (
        DateRange, Dimension, Metric, RunReportRequest,
    )
    start, end = _date_range_ga4()
    kwargs = dict(
        property=f"properties/{PROPERTY_ID}",
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metrics],
        date_ranges=[DateRange(start_date=start, end_date=end)],
        limit=row_limit,
    )
    if dim_filter:
        kwargs["dimension_filter"] = dim_filter

    try:
        resp = client.run_report(RunReportRequest(**kwargs))
    except Exception as e:
        print(f"  [WARN] GA4 query failed (dims={dimensions}): {e}")
        return []

    dim_names = [h.name for h in resp.dimension_headers]
    met_names = [h.name for h in resp.metric_headers]
    rows = []
    for row in resp.rows:
        r = {dim_names[i]: v.value for i, v in enumerate(row.dimension_values)}
        for i, v in enumerate(row.metric_values):
            try:
                r[met_names[i]] = float(v.value)
            except (ValueError, TypeError):
                r[met_names[i]] = 0.0
        rows.append(r)
    return rows


def _run_report_overall(client, metrics, dim_filter=None):
    """ディメンションなしの集計値を1行で返す。"""
    from google.analytics.data_v1beta.types import (
        DateRange, Metric, RunReportRequest,
    )
    start, end = _date_range_ga4()
    kwargs = dict(
        property=f"properties/{PROPERTY_ID}",
        metrics=[Metric(name=m) for m in metrics],
        date_ranges=[DateRange(start_date=start, end_date=end)],
    )
    if dim_filter is not None:
        kwargs["dimension_filter"] = dim_filter
    try:
        resp = client.run_report(RunReportRequest(**kwargs))
    except Exception as e:
        print(f"  [WARN] GA4 overall query failed ({metrics}): {e}")
        return {m: 0.0 for m in metrics}

    met_names = [h.name for h in resp.metric_headers]
    if not resp.rows:
        return {m: 0.0 for m in met_names}
    row = resp.rows[0]
    result = {}
    for i, v in enumerate(row.metric_values):
        try:
            result[met_names[i]] = float(v.value)
        except (ValueError, TypeError):
            result[met_names[i]] = 0.0
    return result


def _event_count(events: list[dict], pattern: str) -> int:
    """eventName が pattern に一致するイベントの合計カウントを返す。"""
    return sum(
        int(e.get("eventCount", 0))
        for e in events
        if re.search(pattern, e.get("eventName", ""), re.IGNORECASE)
    )


# ── GA4: fetch raw data ────────────────────────────────────────────────────────

def _fetch_host_summary(client) -> dict:
    """hostName 別 PV・UU を取得してホスト混入状況サマリーを返す（フィルタなし）。"""
    rows = _run_report(
        client, ["hostName"],
        ["screenPageViews", "activeUsers", "sessions"],
        row_limit=20,
    )
    rows.sort(key=lambda r: -r.get("screenPageViews", 0))

    total_pv = sum(r.get("screenPageViews", 0) for r in rows) or 1
    total_uu = sum(r.get("activeUsers",     0) for r in rows) or 1

    errorlog_pv = sum(r.get("screenPageViews", 0) for r in rows if "errorlog.jp" in r.get("hostName", ""))

    hosts = [
        {
            "host":     r.get("hostName", ""),
            "pv":       int(r.get("screenPageViews", 0)),
            "uu":       int(r.get("activeUsers",     0)),
            "sessions": int(r.get("sessions",        0)),
            "pv_share": round(r.get("screenPageViews", 0) / total_pv, 4),
            "uu_share": round(r.get("activeUsers",     0) / total_uu, 4),
        }
        for r in rows
    ]
    return {
        "primary_host":          "errorlog.jp",
        "hosts":                 hosts,
        "primary_host_pv_share": round(errorlog_pv / total_pv, 4),
        "total_pv_all_hosts":    int(total_pv),
        "total_uu_all_hosts":    int(total_uu),
    }


def fetch_all_ga4(client) -> dict:
    host = _host_filter()

    print("  [GA4] overall metrics (errorlog.jp)...")
    overall = _run_report_overall(client, [
        "activeUsers", "sessions", "screenPageViews", "bounceRate",
    ], dim_filter=host)

    print("  [GA4] channel distribution (errorlog.jp)...")
    channels = _run_report(client, ["sessionDefaultChannelGroup"], ["sessions"], row_limit=20, dim_filter=host)
    channels.sort(key=lambda r: -r.get("sessions", 0))

    print("  [GA4] country distribution (errorlog.jp)...")
    # errorlog.jp 訪問者の国別内訳（japan_ratio 計算に使用）
    countries = _run_report(
        client, ["country"],
        ["activeUsers", "sessions", "engagementRate", "averageSessionDuration", "bounceRate"],
        row_limit=30,
        dim_filter=host,
    )
    countries.sort(key=lambda r: -r.get("activeUsers", 0))

    print("  [GA4] events (errorlog.jp)...")
    events = _run_report(client, ["eventName"], ["eventCount"], row_limit=100, dim_filter=host)

    print("  [GA4] host summary (all hosts)...")
    host_summary = _fetch_host_summary(client)

    return {
        "overall":      overall,
        "channels":     channels,
        "countries":    countries,
        "events":       events,
        "host_summary": host_summary,
    }


# ── GA4: compute metrics ───────────────────────────────────────────────────────

def compute_metrics(data: dict) -> dict:
    ov        = data["overall"]
    channels  = data["channels"]
    countries = data["countries"]
    events    = data["events"]

    active_users = int(ov.get("activeUsers",     0))
    sessions     = int(ov.get("sessions",        0))
    total_pv     = int(ov.get("screenPageViews", 0))
    bounce_rate  = ov.get("bounceRate",          0.0)

    total_ch = sum(r.get("sessions", 0) for r in channels) or 1
    channel_str = ", ".join(
        f"{r.get('sessionDefaultChannelGroup','?')}: {r.get('sessions',0)/total_ch:.0%}"
        for r in channels[:3]
    )
    organic_ratio = next(
        (r.get("sessions", 0) / total_ch
         for r in channels
         if "organic" in r.get("sessionDefaultChannelGroup", "").lower()),
        0.0,
    )

    total_country = sum(r.get("activeUsers", 0) for r in countries) or 1
    japan_ratio = next(
        (r.get("activeUsers", 0) / total_country
         for r in countries if r.get("country", "").lower() in ("japan", "日本")),
        0.0,
    )

    pv_per_sess = total_pv / sessions if sessions else 0.0

    js_errors = _event_count(events, r"exception|javascript_error|js_error")

    return {
        "active_users":  active_users,
        "sessions":      sessions,
        "organic_ratio": organic_ratio,
        "japan_ratio":   japan_ratio,
        "pv_per_sess":   pv_per_sess,
        "bounce_rate":   bounce_rate,
        "js_errors":     js_errors,
        "channel_str":   channel_str,
    }


# ── Status judgment ────────────────────────────────────────────────────────────

def _sig(value: float, good: float, bad: float, lower_is_better: bool = False) -> str:
    if not lower_is_better:
        if value >= good: return "✅ 良好"
        if value <= bad:  return "🔴 要改善"
        return "⚠️ 要注意"
    else:
        if value <= good: return "✅ 良好"
        if value >= bad:  return "🔴 要改善"
        return "⚠️ 要注意"


# ── GSC Auth ──────────────────────────────────────────────────────────────────

_GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


def _build_gsc_service():
    from googleapiclient.discovery import build

    sa_json = (
        os.environ.get("GSC_SERVICE_ACCOUNT_KEY", "").strip()
        or os.environ.get("GA4_SERVICE_ACCOUNT_KEY", "").strip()
    )
    if sa_json:
        from google.oauth2.service_account import Credentials
        info  = json.loads(sa_json)
        creds = Credentials.from_service_account_info(info, scopes=_GSC_SCOPES)
        return build("searchconsole", "v1", credentials=creds, cache_discovery=False)

    client_id     = (os.environ.get("GSC_OAUTH_CLIENT_ID")     or os.environ.get("GA4_OAUTH_CLIENT_ID",     "")).strip()
    client_secret = (os.environ.get("GSC_OAUTH_CLIENT_SECRET") or os.environ.get("GA4_OAUTH_CLIENT_SECRET", "")).strip()
    refresh_token = (os.environ.get("GSC_OAUTH_REFRESH_TOKEN") or os.environ.get("GA4_OAUTH_REFRESH_TOKEN", "")).strip()

    if all([client_id, client_secret, refresh_token]):
        from google.oauth2.credentials import Credentials
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=_GSC_SCOPES,
        )
        return build("searchconsole", "v1", credentials=creds, cache_discovery=False)

    raise RuntimeError("GSC auth missing")


def _gsc_query(service, dimensions: list[str], row_limit: int = 1000) -> list[dict]:
    end   = (TODAY - timedelta(days=3)).strftime("%Y-%m-%d")
    start = (TODAY - timedelta(days=9)).strftime("%Y-%m-%d")
    body  = {
        "startDate":  start,
        "endDate":    end,
        "dimensions": dimensions,
        "rowLimit":   row_limit,
        "dataState":  "all",
    }
    try:
        resp = service.searchanalytics().query(siteUrl=SITE_URL, body=body).execute()
    except Exception as e:
        print(f"  [WARN] GSC query failed (dims={dimensions}): {e}")
        return []

    rows = []
    for r in resp.get("rows", []):
        keys  = r.get("keys", [])
        entry = {d: keys[i] for i, d in enumerate(dimensions) if i < len(keys)}
        entry.update({
            "impressions": r.get("impressions", 0),
            "clicks":      r.get("clicks",      0),
            "ctr":         r.get("ctr",         0.0),
            "position":    r.get("position",    0.0),
        })
        rows.append(entry)
    return rows


# ── GSC: fetch data ────────────────────────────────────────────────────────────

def fetch_gsc_data() -> tuple[list[dict], dict]:
    """ボトルネック記事とサイト全体サマリーをまとめて取得する。"""
    try:
        service = _build_gsc_service()
    except Exception as e:
        print(f"  [WARN] GSC auth failed: {e}")
        return [], {}

    bottlenecks  = _fetch_gsc_bottlenecks(service)
    site_summary = _fetch_gsc_site_summary(service)
    return bottlenecks, site_summary


def _fetch_gsc_site_summary(service) -> dict:
    """GSCのサイト全体週次集計（インプレッション・クリック・掲載順位・CTR）を返す。"""
    end   = (TODAY - timedelta(days=3)).strftime("%Y-%m-%d")
    start = (TODAY - timedelta(days=9)).strftime("%Y-%m-%d")
    body  = {
        "startDate": start,
        "endDate":   end,
        "dataState": "all",
    }
    try:
        resp = service.searchanalytics().query(siteUrl=SITE_URL, body=body).execute()
    except Exception as e:
        print(f"  [WARN] GSC site summary failed: {e}")
        return {}

    rows = resp.get("rows", [])
    if not rows:
        return {"impressions": 0, "clicks": 0, "ctr": 0.0, "position": 0.0}
    r = rows[0]
    return {
        "impressions": int(r.get("impressions", 0)),
        "clicks":      int(r.get("clicks",      0)),
        "ctr":         r.get("ctr",             0.0),
        "position":    r.get("position",        0.0),
    }


def _fetch_gsc_bottlenecks(service) -> list[dict]:
    print("  [GSC] fetching page metrics...")
    page_rows = [
        r for r in _gsc_query(service, ["page"])
        if "/posts/" in r.get("page", "")
    ]
    if not page_rows:
        print("  [GSC] no /posts/ rows")
        return []

    print(f"  [GSC] fetching top queries ({len(page_rows)} pages)...")
    query_rows = _gsc_query(service, ["query", "page"])
    best: dict[str, tuple[str, int]] = {}
    for r in query_rows:
        page = r.get("page", "")
        if "/posts/" not in page:
            continue
        imp = int(r.get("impressions", 0))
        if page not in best or imp > best[page][1]:
            best[page] = (r.get("query", ""), imp)
    top_queries = {p: q for p, (q, _) in best.items()}

    total_ctr_avg = sum(r["ctr"] for r in page_rows) / len(page_rows)
    effective_ctr = min(CTR_THRESHOLD, total_ctr_avg * 0.7)

    results = []
    for r in page_rows:
        page        = r["page"]
        impressions = int(r["impressions"])
        ctr         = r["ctr"]
        position    = r["position"]

        is_low_ctr  = impressions >= CTR_IMP_THRESHOLD and ctr < effective_ctr
        is_stagnant = impressions >= POS_IMP_THRESHOLD and POS_MIN <= position <= POS_MAX
        if not (is_low_ctr or is_stagnant):
            continue

        results.append({
            "page":        page,
            "impressions": impressions,
            "clicks":      int(r["clicks"]),
            "ctr":         round(ctr, 4),
            "position":    round(position, 1),
            "top_query":   top_queries.get(page, ""),
        })

    results.sort(key=lambda x: -x["impressions"])
    print(f"  [GSC] bottlenecks: {len(results)}")
    return results


# ── IndexNow 送信サマリー ──────────────────────────────────────────────────────

def _build_indexnow_section() -> str:
    """data/indexnow_log.jsonl から今週の IndexNow 送信サマリーを返す。"""
    log_path = BASE / "data" / "indexnow_log.jsonl"
    if not log_path.exists():
        return ""

    week_start = (TODAY - timedelta(days=9)).isoformat()
    sent_urls: set[str] = set()

    try:
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("date", "") >= week_start and entry.get("status") == "ok":
                for u in entry.get("urls", []):
                    sent_urls.add(u)
    except Exception as e:
        print(f"  [WARN] indexnow_log.jsonl 読み込みエラー: {e}")
        return ""

    if not sent_urls:
        return ""

    return (
        "\n\n---\n\n"
        "### IndexNow 送信サマリー（今週）\n\n"
        f"IndexNow 経由で送信: **{len(sent_urls)} URL**\n"
    )


# ── Content Gap レポート読み込み ──────────────────────────────────────────────

def _load_content_gap_section() -> str:
    """data/content_gap.json が存在すれば GitHub Issue 用 Markdown を返す。"""
    gap_file = BASE / "data" / "content_gap.json"
    if not gap_file.exists():
        return ""
    try:
        gap = json.loads(gap_file.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [WARN] content_gap.json 読み込みエラー: {e}")
        return ""

    s     = gap.get("summary", {})
    total = s.get("total_queries", 0)
    if not total:
        return ""

    cov_rate  = s.get("coverage_rate", 0.0)
    covered   = s.get("covered",   0)
    partial   = s.get("partial",   0)
    uncovered = s.get("uncovered", 0)

    lines = [
        "",
        "---",
        "",
        "## Content Gap Report",
        "",
        f"Coverage Rate: **{cov_rate:.1%}**",
        "",
        "| 分類 | 件数 |",
        "| :--- | :--- |",
        f"| ✅ Covered   | {covered} |",
        f"| ⚠️ Partial   | {partial} |",
        f"| 🔴 Uncovered | {uncovered} |",
        f"| **合計**     | **{total}** |",
        "",
    ]

    top_items = sorted(
        gap.get("uncovered", []) + gap.get("partial", []),
        key=lambda x: -x.get("opportunity_score", 0),
    )[:10]

    if top_items:
        lines.append("### Top Opportunities")
        lines.append("")
        for i, item in enumerate(top_items, 1):
            cov_icon = "🔴" if item["coverage"] == "uncovered" else "⚠️"
            lines.append(
                f"{i}. {cov_icon} `{item['query']}` "
                f"— Score: {item.get('opportunity_score', 0):.1f}"
            )
        lines.append("")

    return "\n".join(lines)


# ── 競合スクレイピング（現在は無効化中） ──────────────────────────────────────
# 再開する場合:
#   1. main() 内の competitor_section 行のコメントを外す
#   2. weekly_ga4.yml の "Scan competitor outlines" ステップのコメントを外す

def _load_competitor_section() -> str:
    """scripts/competitor_analysis.json が存在すれば Issue 追記用 Markdown を返す。"""
    comp_file = Path(__file__).parent / "competitor_analysis.json"
    if not comp_file.exists():
        return ""
    try:
        data    = json.loads(comp_file.read_text(encoding="utf-8"))
        results = data.get("results", [])
        if not results:
            return ""

        lines = ["", "---", "", "### 競合構成分析（自動スクレイピング）", ""]
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
    except Exception as e:
        print(f"  [WARN] competitor_analysis.json 読み込みエラー: {e}")
        return ""


# ── ノイズ除外サマリー ─────────────────────────────────────────────────────────

def _build_noise_section() -> str:
    """ga4_analyzer.py が出力した noise_stats.json を読んで Issue 用 Markdown を返す。"""
    stats_path = BASE / "reports" / "ga4" / "noise_stats.json"
    if not stats_path.exists():
        return ""
    try:
        import json as _json
        ns = _json.loads(stats_path.read_text(encoding="utf-8"))
    except Exception:
        return ""

    countries = ns.get("noise_countries", [])
    threshold = ns.get("noise_time_threshold", 5.0)
    count     = ns.get("count", 0)
    users     = ns.get("users", 0)
    by_c      = ns.get("by_country", {})
    label     = ", ".join(countries) if countries else "設定なし"

    if count > 0:
        detail = " / ".join(f"{c}: {u} UU" for c, u in by_c.items())
        return (
            f"\n\n---\n\n### ノイズ除外サマリー（Cloudflare bot対策の観測点）\n\n"
            f"| 項目 | 値 |\n"
            f"| :--- | :--- |\n"
            f"| 除外対象国 | {label} |\n"
            f"| 滞在時間しきい値 | {threshold}秒未満 |\n"
            f"| 今週の除外件数 | **{count} 行 / {users} UU** |\n"
            f"| 国別内訳 | {detail} |\n\n"
            f"> Cloudflare bot対策（Bot Fight Mode / WAF）導入後、この数字が減少することを確認してください。"
        )
    else:
        return (
            f"\n\n---\n\n### ノイズ除外サマリー（Cloudflare bot対策の観測点）\n\n"
            f"今週は除外対象なし（{label}・{threshold}秒未満のセッションは検出されませんでした）。"
        )


# ── 国別分布（継続観測・ボット判定の参考）────────────────────────────────────
# ノイズ除外サマリーとは独立したセクション。ノイズ除外サマリーは「除外結果」を記録するのに対し、
# こちらは除外前の主要国の質的指標をそのまま記録し、人間が毎週の推移を見て判断するための材料とする。
# bot自動判定・自動除外は行わない（エラー解決サイトは検索流入後すぐ離脱する正常利用も多いため）。

def _build_country_section(countries: list[dict]) -> str:
    """主要国のセッション数・エンゲージ指標を表形式で記録する（継続観測用）。"""
    if not countries:
        return ""

    top = sorted(countries, key=lambda r: -r.get("activeUsers", 0))[:TOP_COUNTRIES]
    rows = []
    for r in top:
        country  = r.get("country", "")
        sessions = int(r.get("sessions", 0))
        active   = int(r.get("activeUsers", 0))
        eng_rate = r.get("engagementRate", 0.0)
        dur      = r.get("averageSessionDuration", 0.0)
        bounce   = r.get("bounceRate", 0.0)

        flag = ""
        if dur < _COUNTRY_ENGAGEMENT_TIME_THRESHOLD or bounce > _COUNTRY_BOUNCE_RATE_THRESHOLD:
            flag = " ⚠️"

        rows.append(
            f"| {country}{flag} | {sessions:,} | {active:,} | {eng_rate:.2%} "
            f"| {dur:.1f} | {bounce:.2%} |"
        )

    table = "\n".join(rows)
    return (
        "\n\n---\n\n"
        "### 国別分布（継続観測・ボット判定の参考。断定ではありません）\n\n"
        "| 国 | セッション数 | アクティブUU | エンゲージ率 | 平均エンゲージ時間(秒) | 直帰率 |\n"
        "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
        f"{table}\n\n"
        f"> ⚠️ は平均エンゲージ時間 < {_COUNTRY_ENGAGEMENT_TIME_THRESHOLD:.0f}秒 または "
        f"直帰率 > {_COUNTRY_BOUNCE_RATE_THRESHOLD:.0%} の国に付けた**参考フラグ**です"
        "（直帰率の閾値は仮値であり、運用しながら見直してください）。"
        "エラー解決サイトでは検索流入後すぐ離脱する正常な利用も多いため、"
        "この指標だけではボットと**断定できません**。"
        "毎週の推移を人が見て判断するための記録であり、自動的な除外・ブロックには使用していません。"
    )


# ── Markdown rendering ────────────────────────────────────────────────────────

def _pct(v: float, dec: int = 1) -> str:
    return f"{v * 100:.{dec}f}"


def _build_host_summary_section(host_summary: dict) -> str:
    """ホスト別内訳セクション（混入監視用）を返す。"""
    if not host_summary or not host_summary.get("hosts"):
        return ""

    rows = "\n".join(
        f"| `{h['host']}` | {h['pv']:,} | {h['pv_share']:.1%} | {h['uu']:,} | {h['uu_share']:.1%} |"
        for h in host_summary["hosts"]
    )
    pv_share = host_summary.get("primary_host_pv_share", 0)
    has_zenn  = any("zenn" in h["host"] for h in host_summary["hosts"])
    zenn_note = ""
    if has_zenn:
        zenn_pv_share = sum(
            h["pv_share"] for h in host_summary["hosts"] if "zenn" in h["host"]
        )
        zenn_note = f"\n\n> ⚠️ zenn.dev が全体の **{zenn_pv_share:.1%}** を占めています。メイン指標は errorlog.jp のみに絞って集計しています。"

    return (
        "\n\n---\n\n"
        "### ホスト別トラフィック内訳（混入監視）\n\n"
        "| ホスト | PV | PV% | UU | UU% |\n"
        "| :--- | :--- | :--- | :--- | :--- |\n"
        f"{rows}"
        f"\n\n> メイン指標は errorlog.jp のみ（PV の {pv_share:.1%}）で集計しています。"
        + zenn_note
    )


def render_issue_body(
    m: dict,
    bottlenecks: list[dict],
    period: str,
    gsc_summary: dict | None = None,
    noise_section: str = "",
    country_section: str = "",
    content_gap_section: str = "",
    indexnow_section: str = "",
    host_summary_section: str = "",
) -> str:
    if gsc_summary is None:
        gsc_summary = {}

    ga4_table = f"""\
### 1. GA4 トラフィックサマリー

| 分類 | 指標名 | 今週の実績値 | 状態 |
| :--- | :--- | :--- | :--- |
| **集客** | アクティブユーザー数 | {m['active_users']:,} | {_sig(m['active_users'], 500, 100)} |
| | セッション数 | {m['sessions']:,} | {_sig(m['sessions'], 600, 120)} |
| | チャネル比率 | {m['channel_str']} | {_sig(m['organic_ratio'], 0.50, 0.30)} |
| **ユーザー属性** | 日本国内率 | {_pct(m['japan_ratio'])}% | {_sig(m['japan_ratio'], 0.60, 0.40)} |
| **動線** | 1セッションあたりPV数 | {m['pv_per_sess']:.2f} | {_sig(m['pv_per_sess'], 2.0, 1.2)} |
| | 離脱率 | {_pct(m['bounce_rate'])}% | {_sig(m['bounce_rate'], 0.40, 0.70, lower_is_better=True)} |
| **品質** | フロントエラー発生数 | {m['js_errors']:,}件 | {"✅ エラーなし" if m['js_errors'] == 0 else f"🔴 {m['js_errors']}件検出"} |"""

    if gsc_summary:
        gsc_summary_section = f"""

### 2. Search Console サイト全体サマリー

| 指標 | 今週 |
| :--- | :--- |
| 総インプレッション数 | {gsc_summary['impressions']:,} |
| 総クリック数 | {gsc_summary['clicks']:,} |
| 平均掲載順位 | {gsc_summary['position']:.1f} |
| 平均CTR | {gsc_summary['ctr']:.2%} |"""
    else:
        gsc_summary_section = ""

    if bottlenecks:
        rows = "\n".join(
            f"| {i+1} | `{b['page']}` | {b['impressions']:,} | {b['ctr']:.2%} "
            f"| {b['position']:.1f} | {b['top_query'] or '—'} |"
            for i, b in enumerate(bottlenecks[:15])
        )
        gsc_section = f"""

### 3. Search Console ボトルネック記事

判定条件: CTR < {CTR_THRESHOLD:.1%}（インプレッション≥{CTR_IMP_THRESHOLD}件）または掲載順位 {POS_MIN:.0f}〜{POS_MAX:.0f} 位停滞。

| # | 対象URL | 表示回数 | CTR | 平均掲載順位 | 最多検索クエリ |
| :--- | :--- | :--- | :--- | :--- | :--- |
{rows}"""
    else:
        gsc_section = """

### 3. Search Console ボトルネック記事

_今週のボトルネック記事はありませんでした。_"""

    return (
        f"## 週次統合分析レポート（{period}）\n\n"
        + ga4_table
        + gsc_summary_section
        + gsc_section
        + host_summary_section
        + noise_section
        + country_section
        + indexnow_section
        + content_gap_section
        + "\n\n> このIssueは `weekly_ga4.yml` によって自動生成されました。対応完了後クローズしてください。"
    )


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    if not PROPERTY_ID:
        print("[ERROR] GA4_PROPERTY_ID is not set.", file=sys.stderr)
        sys.exit(1)

    period = f"{TODAY - timedelta(days=9)} 〜 {TODAY - timedelta(days=3)}"
    print(f"=== Weekly Unified Report ({period}) ===")

    print("[1/3] Connecting to GA4...")
    try:
        ga4_client = _build_ga4_client()
    except Exception as e:
        print(f"[ERROR] GA4 auth failed: {e}", file=sys.stderr)
        sys.exit(1)

    print("[2/3] Fetching GA4 data...")
    raw_data = fetch_all_ga4(ga4_client)
    metrics  = compute_metrics(raw_data)

    print("[3/3] Fetching GSC data...")
    bottlenecks, gsc_summary = fetch_gsc_data()

    noise_section        = _build_noise_section()
    country_section      = _build_country_section(raw_data.get("countries", []))
    indexnow_section     = _build_indexnow_section()
    content_gap_section  = _load_content_gap_section()
    host_summary         = raw_data.get("host_summary", {})
    host_summary_section = _build_host_summary_section(host_summary)
    # competitor_section = _load_competitor_section()  # 競合スクレイピングは無効化中
    if content_gap_section:
        print("  → Content Gap データあり（Issueに追記します）")
    if indexnow_section:
        print("  → IndexNow 送信ログあり（Issueに追記します）")

    issue_body = render_issue_body(
        metrics, bottlenecks, period,
        gsc_summary=gsc_summary,
        noise_section=noise_section,
        country_section=country_section,
        indexnow_section=indexnow_section,
        content_gap_section=content_gap_section,
        host_summary_section=host_summary_section,
    )
    issue_title = f"【週次レポート】GA4 + GSC ボトルネック ({TODAY.isoformat()})"

    output = {
        "generated_at":      TODAY.isoformat(),
        "period":            period,
        "issue_title":       issue_title,
        "issue_body":        issue_body,
        "bottlenecks_count": len(bottlenecks),
        "metrics_snapshot": {
            "active_users":  metrics["active_users"],
            "sessions":      metrics["sessions"],
            "organic_ratio": round(metrics["organic_ratio"], 4),
            "japan_ratio":   round(metrics["japan_ratio"],   4),
            "pv_per_sess":   round(metrics["pv_per_sess"],   3),
            "bounce_rate":   round(metrics["bounce_rate"],   4),
            "js_errors":     metrics["js_errors"],
        },
        "gsc_summary":      gsc_summary,
        "ga4_host_summary": host_summary,
    }
    REPORT_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nSaved: {REPORT_FILE.relative_to(BASE)}")
    print(f"  active_users={metrics['active_users']}, sessions={metrics['sessions']}, "
          f"organic_ratio={metrics['organic_ratio']:.1%}, bottlenecks={len(bottlenecks)}")
    if gsc_summary:
        print(f"  gsc_impressions={gsc_summary['impressions']:,}, avg_position={gsc_summary['position']:.1f}")
    print("Done.")


if __name__ == "__main__":
    main()
