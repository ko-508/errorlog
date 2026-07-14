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
import subprocess
import sys
import unicodedata
from datetime import date, datetime, timedelta
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


def _date_range_pair(today: date = TODAY) -> tuple[date, date]:
    return today - timedelta(days=9), today - timedelta(days=3)


def _previous_range(start: date, end: date) -> tuple[date, date]:
    days = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    return prev_end - timedelta(days=days - 1), prev_end


def _run_report(client, dimensions, metrics, row_limit=100, dim_filter=None, start_date=None, end_date=None):
    from google.analytics.data_v1beta.types import (
        DateRange, Dimension, Metric, RunReportRequest,
    )
    if start_date is None or end_date is None:
        start, end = _date_range_ga4()
    else:
        start, end = str(start_date), str(end_date)
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


def _run_report_overall(client, metrics, dim_filter=None, start_date=None, end_date=None):
    """ディメンションなしの集計値を1行で返す。"""
    from google.analytics.data_v1beta.types import (
        DateRange, Metric, RunReportRequest,
    )
    if start_date is None or end_date is None:
        start, end = _date_range_ga4()
    else:
        start, end = str(start_date), str(end_date)
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

def _fetch_host_summary(client, start_date=None, end_date=None) -> dict:
    """hostName 別 PV・UU を取得してホスト混入状況サマリーを返す（フィルタなし）。"""
    rows = _run_report(
        client, ["hostName"],
        ["screenPageViews", "activeUsers", "sessions"],
        row_limit=20,
        start_date=start_date,
        end_date=end_date,
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


def fetch_all_ga4(client, start_date=None, end_date=None) -> dict:
    host = _host_filter()

    print("  [GA4] overall metrics (errorlog.jp)...")
    overall = _run_report_overall(client, [
        "activeUsers", "sessions", "screenPageViews", "bounceRate", "averageSessionDuration",
    ], dim_filter=host, start_date=start_date, end_date=end_date)

    print("  [GA4] channel distribution (errorlog.jp)...")
    channels = _run_report(
        client, ["sessionDefaultChannelGroup"], ["sessions"],
        row_limit=20, dim_filter=host, start_date=start_date, end_date=end_date,
    )
    channels.sort(key=lambda r: -r.get("sessions", 0))

    print("  [GA4] country distribution (errorlog.jp)...")
    # errorlog.jp 訪問者の国別内訳（japan_ratio 計算に使用）
    countries = _run_report(
        client, ["country"],
        ["activeUsers", "sessions", "engagementRate", "averageSessionDuration", "bounceRate"],
        row_limit=30,
        dim_filter=host,
        start_date=start_date,
        end_date=end_date,
    )
    countries.sort(key=lambda r: -r.get("activeUsers", 0))

    print("  [GA4] events (errorlog.jp)...")
    events = _run_report(
        client, ["eventName"], ["eventCount"],
        row_limit=100, dim_filter=host, start_date=start_date, end_date=end_date,
    )

    print("  [GA4] host summary (all hosts)...")
    host_summary = _fetch_host_summary(client, start_date=start_date, end_date=end_date)

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
    avg_eng_time = ov.get("averageSessionDuration", 0.0)

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
    organic_sessions = int(next(
        (r.get("sessions", 0)
         for r in channels
         if "organic" in r.get("sessionDefaultChannelGroup", "").lower()),
        0,
    ))
    direct_sessions = int(next(
        (r.get("sessions", 0)
         for r in channels
         if r.get("sessionDefaultChannelGroup", "").lower() == "direct"),
        0,
    ))

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
        "organic_sessions": organic_sessions,
        "direct_sessions":  direct_sessions,
        "organic_ratio": organic_ratio,
        "japan_ratio":   japan_ratio,
        "pv_per_sess":   pv_per_sess,
        "avg_engagement_time": avg_eng_time,
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


def _gsc_query(service, dimensions: list[str], row_limit: int = 1000, start_date=None, end_date=None) -> list[dict]:
    if start_date is None or end_date is None:
        end   = (TODAY - timedelta(days=3)).strftime("%Y-%m-%d")
        start = (TODAY - timedelta(days=9)).strftime("%Y-%m-%d")
    else:
        start = str(start_date)
        end = str(end_date)
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

def fetch_gsc_data() -> tuple[list[dict], dict, dict]:
    """ボトルネック記事とサイト全体サマリーをまとめて取得する。"""
    try:
        service = _build_gsc_service()
    except Exception as e:
        print(f"  [WARN] GSC auth failed: {e}")
        return [], {}, {}

    current_start, current_end = _date_range_pair()
    previous_start, previous_end = _previous_range(current_start, current_end)
    bottlenecks  = _fetch_gsc_bottlenecks(service, current_start, current_end)
    site_summary = _fetch_gsc_site_summary(service, current_start, current_end)
    previous_summary = _fetch_gsc_site_summary(service, previous_start, previous_end)
    return bottlenecks, site_summary, previous_summary


def _fetch_gsc_site_summary(service, start_date=None, end_date=None) -> dict:
    """GSCのサイト全体週次集計（インプレッション・クリック・掲載順位・CTR）を返す。"""
    if start_date is None or end_date is None:
        end   = (TODAY - timedelta(days=3)).strftime("%Y-%m-%d")
        start = (TODAY - timedelta(days=9)).strftime("%Y-%m-%d")
    else:
        start = str(start_date)
        end = str(end_date)
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


def _fetch_gsc_bottlenecks(service, start_date=None, end_date=None) -> list[dict]:
    print("  [GSC] fetching page metrics...")
    page_rows = [
        r for r in _gsc_query(service, ["page"], start_date=start_date, end_date=end_date)
        if "/posts/" in r.get("page", "")
    ]
    if not page_rows:
        print("  [GSC] no /posts/ rows")
        return []

    print(f"  [GSC] fetching top queries ({len(page_rows)} pages)...")
    query_rows = _gsc_query(service, ["query", "page"], start_date=start_date, end_date=end_date)
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
        is_priority_candidate = (
            impressions >= 20
            and (
                (4.0 <= position <= 20.0 and ctr < 0.015)
                or 21.0 <= position <= 40.0
            )
        )
        if not (is_low_ctr or is_stagnant or is_priority_candidate):
            continue

        priority, priority_reason = classify_bottleneck_priority(impressions, ctr, position)
        results.append({
            "page":        page,
            "impressions": impressions,
            "clicks":      int(r["clicks"]),
            "ctr":         round(ctr, 4),
            "position":    round(position, 1),
            "top_query":   top_queries.get(page, ""),
            "priority":    priority,
            "priority_reason": priority_reason,
        })

    results = sort_bottlenecks(results)
    print(f"  [GSC] bottlenecks: {len(results)}")
    return results


def classify_bottleneck_priority(impressions: int, ctr: float, position: float) -> tuple[str, str]:
    """Search Console ボトルネックのA/B/C優先度と判定理由を返す。"""
    if impressions >= 20 and 4.0 <= position <= 20.0 and ctr < 0.015:
        return "A", "表示回数が多く順位は高いがクリックされていない"
    if impressions >= 20 and 21.0 <= position <= 40.0:
        return "B", "表示回数が多く順位21〜40位で改善余地が大きい"
    return "C", "その他の既存ボトルネック条件に該当"


def sort_bottlenecks(bottlenecks: list[dict]) -> list[dict]:
    rank = {"A": 0, "B": 1, "C": 2}
    enriched = []
    for b in bottlenecks:
        item = dict(b)
        if not item.get("priority"):
            p, reason = classify_bottleneck_priority(
                int(item.get("impressions", 0)),
                float(item.get("ctr", 0.0)),
                float(item.get("position", 0.0)),
            )
            item["priority"] = p
            item["priority_reason"] = reason
        enriched.append(item)
    return sorted(enriched, key=lambda x: (rank.get(x.get("priority", "C"), 2), -int(x.get("impressions", 0))))


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

    top_items = _filter_content_gap_items(
        sorted(
            gap.get("uncovered", []) + gap.get("partial", []),
            key=lambda x: -x.get("opportunity_score", 0),
        )
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


def _normalize_gap_query(query: str) -> str:
    q = unicodedata.normalize("NFKC", query or "").strip().lower()
    q = q.strip("\"'`“”‘’")
    q = re.sub(r"[\s\+\-$#*_~|/\\:;,.、。．・!！?？()\[\]{}<>「」『』【】]+$", "", q)
    q = re.sub(r"^[\s\+\-$#*_~|/\\:;,.、。．・!！?？()\[\]{}<>「」『』【】]+", "", q)
    q = re.sub(r"[\+\-$#*_~|/\\:;,.、。．・!！?？()\[\]{}<>「」『』【】]+", " ", q)
    q = re.sub(r"\s+", " ", q)
    return q.strip()


def _is_meaningful_short_gap_query(normalized: str) -> bool:
    if re.search(r"\d{3}\s*(エラー|error|エラ|とは)", normalized):
        return True
    meaningful_terms = (
        "bashとは",
        "bash とは",
        "docker compose",
        "docker-compose",
        "http 401",
        "http 403",
        "http 404",
        "http 429",
        "http 500",
        "http 503",
    )
    return normalized in meaningful_terms


def _is_bad_gap_query(query: str) -> bool:
    normalized = _normalize_gap_query(query)
    if not normalized:
        return True
    if re.search(r"\b(the model returned|data retention mode|traceback|stack trace)\b", normalized):
        return True
    if len(normalized) < 10 and not _is_meaningful_short_gap_query(normalized):
        return True
    if re.search(r"\b(const|let|var|require|import|function|=>)\b", normalized):
        return True
    if re.search(r"[;=<>]|=>|\{|\}|\(|\)", normalized) and re.search(r"\b[a-z_][a-z0-9_]*\b", normalized):
        return True
    if re.fullmatch(r"[\W\d_]+", normalized):
        return True
    vague = {"cliとは", "cli コマンド", "cli", "apiとは"}
    return normalized in vague


def _filter_content_gap_items(items: list[dict]) -> list[dict]:
    filtered = []
    seen: set[str] = set()
    for item in items:
        q = item.get("query", "")
        key = _normalize_gap_query(q)
        if _is_bad_gap_query(q) or key in seen:
            continue
        seen.add(key)
        filtered.append(item)
    return filtered


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


def _fmt_int(v) -> str:
    return f"{int(v or 0):,}"


def _fmt_float(v, dec: int = 1) -> str:
    return f"{float(v or 0):.{dec}f}"


def _fmt_rate(v) -> str:
    return f"{float(v or 0):.2%}"


def _fmt_previous(change: dict, formatter) -> str:
    if not change.get("previous_exists", True):
        return "データなし"
    return formatter(change.get("previous"))


def _safe_pct_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return (current - previous) / previous


def build_change(current: float, previous: float | None, *, kind: str = "number") -> dict:
    previous_exists = previous is not None
    previous_value = float(previous or 0)
    current_value = float(current or 0)
    delta = current_value - previous_value
    pct = None if kind in ("rate", "position", "ratio") else _safe_pct_change(current_value, previous_value)
    return {
        "current": current_value,
        "previous": previous_value,
        "previous_exists": previous_exists,
        "delta": delta,
        "pct_change": pct,
        "kind": kind,
    }


def _format_change(change: dict) -> str:
    if not change.get("previous_exists", True):
        return "データなし"
    kind = change.get("kind", "number")
    delta = float(change.get("delta", 0.0))
    if kind in ("rate", "ratio"):
        sign = "+" if delta >= 0 else ""
        return f"{sign}{delta * 100:.2f}pt"
    if kind == "position":
        sign = "+" if delta >= 0 else ""
        return f"{sign}{delta:.1f}"
    pct = change.get("pct_change")
    if pct is None:
        return "算出不可"
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct * 100:.1f}%"


def build_ga4_comparison(current: dict, previous: dict | None) -> dict:
    previous_exists = bool(previous)
    previous = previous or {}
    keys = {
        "active_users": "number",
        "sessions": "number",
        "organic_sessions": "number",
        "direct_sessions": "number",
        "japan_ratio": "ratio",
        "pv_per_sess": "number",
        "avg_engagement_time": "number",
        "bounce_rate": "rate",
    }
    return {
        key: build_change(
            float(current.get(key, 0)),
            float(previous.get(key, 0)) if previous_exists else None,
            kind=kind,
        )
        for key, kind in keys.items()
    }


def build_gsc_comparison(current: dict, previous: dict | None) -> dict:
    previous_exists = bool(previous)
    previous = previous or {}
    keys = {
        "impressions": "number",
        "clicks": "number",
        "ctr": "rate",
        "position": "position",
    }
    return {
        key: build_change(
            float(current.get(key, 0)),
            float(previous.get(key, 0)) if previous_exists else None,
            kind=kind,
        )
        for key, kind in keys.items()
    }


def _load_previous_weekly_reports(limit: int = 8) -> list[dict]:
    reports = []
    for path in sorted(REPORTS_DIR.glob("weekly_report_*.json"), reverse=True):
        if path == REPORT_FILE:
            continue
        try:
            reports.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"  [WARN] weekly report履歴読み込みエラー {path.name}: {e}")
        if len(reports) >= limit:
            break
    return reports


def _extract_gsc_history(current_period: str, current_gsc: dict, previous_reports: list[dict]) -> list[dict]:
    rows = []
    if current_gsc:
        rows.append({
            "period": current_period,
            **{k: current_gsc.get(k, 0) for k in ("impressions", "clicks", "ctr", "position")},
        })
    for report in previous_reports:
        gsc = report.get("gsc_summary") or report.get("gsc", {}).get("current") or {}
        if not gsc:
            continue
        rows.append({
            "period": report.get("period", report.get("generated_at", "")),
            "impressions": gsc.get("impressions", 0),
            "clicks": gsc.get("clicks", 0),
            "ctr": gsc.get("ctr", 0.0),
            "position": gsc.get("position", 0.0),
        })
        if len(rows) >= 8:
            break
    return rows


def judge_overall_summary(gsc_change: dict, ga4_change: dict) -> str:
    imp = gsc_change.get("impressions", {})
    ctr = gsc_change.get("ctr", {})
    pos = gsc_change.get("position", {})
    imp_pct = imp.get("pct_change")
    pos_delta = pos.get("delta", 0)
    ctr_delta = ctr.get("delta", 0)
    if imp_pct is not None and imp_pct <= -0.10 and pos_delta >= 1.0:
        return "検索表示回数と順位がともに悪化しています。"
    if imp_pct is not None and imp_pct <= -0.10 and ctr_delta > 0:
        return "表示回数は減少していますが、CTRは改善しています。"
    if imp_pct is not None and imp_pct >= 0.10 and pos_delta <= -1.0:
        return "検索表示回数と順位がともに改善しています。"
    organic = ga4_change.get("organic_sessions", {}).get("pct_change")
    if organic is not None and organic <= -0.25:
        return "Organic Searchセッションが大きく減少しています。"
    return "大きな変化はありません。"


def build_anomaly_alerts(gsc_change: dict, ga4_change: dict) -> list[str]:
    alerts = []
    imp_pct = gsc_change.get("impressions", {}).get("pct_change")
    if imp_pct is not None and imp_pct <= -0.50:
        alerts.append(f"🚨 表示回数が前週比{abs(imp_pct) * 100:.0f}%減少しました。")

    click_pct = gsc_change.get("clicks", {}).get("pct_change")
    if click_pct is not None and click_pct <= -0.50:
        alerts.append(f"🚨 クリック数が前週比{abs(click_pct) * 100:.0f}%減少しました。")

    pos = gsc_change.get("position", {})
    if pos.get("previous_exists", True) and float(pos.get("delta", 0.0)) >= 10.0:
        alerts.append(
            f"🚨 平均順位が{_fmt_float(pos.get('previous'))}→{_fmt_float(pos.get('current'))}へ悪化しました。"
        )

    organic_pct = ga4_change.get("organic_sessions", {}).get("pct_change")
    if organic_pct is not None and organic_pct <= -0.50:
        alerts.append("🚨 Organic Searchセッションが大幅減少しました。")

    return alerts


def _build_anomaly_section(gsc_change: dict, ga4_change: dict) -> str:
    alerts = build_anomaly_alerts(gsc_change, ga4_change)
    if not alerts:
        return "## 異常検知\n\n大きな異常は検出されませんでした。"
    return "## 異常検知\n\n" + "\n".join(f"- {alert}" for alert in alerts)


def judge_gsc_trend(history: list[dict]) -> str:
    if len(history) < 4:
        return "データ不足"
    recent = list(reversed(history[:4]))
    first = recent[0]
    last = recent[-1]
    imp_delta = _safe_pct_change(float(last.get("impressions", 0)), float(first.get("impressions", 0)))
    pos_delta = float(last.get("position", 0)) - float(first.get("position", 0))
    if imp_delta is None:
        return "データ不足"
    if imp_delta >= 0.10 and pos_delta <= -1.0:
        return "改善傾向"
    if imp_delta <= -0.10 and pos_delta >= 1.0:
        return "悪化傾向"
    return "横ばい"


def _slug_from_post_path(path: str) -> str:
    return Path(path).stem


def _is_draft_post(path: Path) -> bool:
    try:
        head = path.read_text(encoding="utf-8-sig").split("---", 2)[1]
    except Exception:
        return False
    return re.search(r"^draft:\s*true\s*$", head, re.MULTILINE | re.IGNORECASE) is not None


def _published_posts() -> list[Path]:
    posts = []
    for path in (BASE / "content" / "posts").glob("*.md"):
        if not _is_draft_post(path):
            posts.append(path)
    return posts


def _load_review_status() -> dict:
    path = BASE / "data" / "article_review_status.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"  [WARN] article_review_status.json 読み込みエラー: {e}")
        return {}


def _git_name_status(start: date, end: date) -> list[tuple[str, str]]:
    try:
        proc = subprocess.run(
            [
                "git", "log",
                f"--since={start.isoformat()} 00:00:00",
                f"--until={end.isoformat()} 23:59:59",
                "--name-status", "--pretty=format:",
                "--", "content/posts",
            ],
            cwd=BASE,
            check=False,
            text=True,
            capture_output=True,
        )
    except Exception as e:
        print(f"  [WARN] git log 実行エラー: {e}")
        return []
    rows = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            rows.append((parts[0], parts[-1]))
    return rows


def _count_git_post_changes(start: date, end: date) -> dict:
    rows = _git_name_status(start, end)
    modified = {p for status, p in rows if status.startswith("M") and p.endswith(".md")}
    added = {p for status, p in rows if status.startswith("A") and p.endswith(".md")}
    deleted = {p for status, p in rows if status.startswith("D") and p.endswith(".md")}
    return {
        "modified": len(modified - added),
        "added": len(added),
        "unpublished": len(deleted),
    }


def build_article_progress(start: date, end: date) -> dict:
    posts = _published_posts()
    status = _load_review_status()
    verified = 0
    for post in posts:
        rel = post.relative_to(BASE).as_posix()
        alt = f"posts/{post.name}"
        if status.get(rel, {}).get("verified") is True or status.get(alt, {}).get("verified") is True:
            verified += 1
    weekly = _count_git_post_changes(start, end)
    recent4 = []
    cursor_end = end
    for _ in range(4):
        cursor_start = cursor_end - timedelta(days=6)
        changes = _count_git_post_changes(cursor_start, cursor_end)
        recent4.append({
            "period": f"{cursor_start.isoformat()} 〜 {cursor_end.isoformat()}",
            "modified": changes["modified"],
        })
        cursor_end = cursor_start - timedelta(days=1)
    total = len(posts)
    unverified = max(total - verified, 0)
    return {
        "published_count": total,
        "verified_count": verified,
        "unverified_count": unverified,
        "verification_rate": (verified / total) if total else 0.0,
        "weekly_modified": weekly["modified"],
        "weekly_new": weekly["added"],
        "weekly_unpublished": weekly["unpublished"],
        "recent4_modified": recent4,
        "review_status_source": "data/article_review_status.json" if status else "未設定",
    }


def load_index_status() -> dict:
    current_path = BASE / "reports" / "gsc" / "index_status_latest.json"
    fallback_path = BASE / "reports" / "ga4" / "index_status_latest.json"
    path = current_path if current_path.exists() else fallback_path
    if not path.exists():
        return {"available": False, "message": "Search Console APIではページインデックス登録レポートの集計値を直接取得できないため、自動取得していません。"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"available": False, "message": f"インデックス状況ファイルを読み込めませんでした: {e}"}
    data["available"] = True
    data["source"] = path.relative_to(BASE).as_posix()
    return data


def evaluate_rewrite_record(record: dict, today: date = TODAY) -> dict:
    rewrite_date_raw = record.get("rewrite_date") or record.get("timestamp") or record.get("date")
    try:
        rewrite_date = datetime.fromisoformat(str(rewrite_date_raw)).date()
    except Exception:
        rewrite_date = None
    elapsed = (today - rewrite_date).days if rewrite_date else None
    before_imp = record.get("before_impressions")
    after_imp = record.get("after_impressions")
    before_clicks = record.get("before_clicks")
    after_clicks = record.get("after_clicks")
    before_ctr = record.get("before_ctr")
    after_ctr = record.get("after_ctr")
    before_pos = record.get("before_position")
    after_pos = record.get("after_position")

    verdict = "判定保留"
    reason = "データ不足"
    if elapsed is not None and elapsed < 14:
        reason = "修正から14日未満"
    elif None not in (before_imp, after_imp, before_pos, after_pos):
        imp_change = _safe_pct_change(float(after_imp), float(before_imp))
        pos_improve = float(before_pos) - float(after_pos)
        clicks_up = before_clicks is not None and after_clicks is not None and int(after_clicks) > int(before_clicks)
        if imp_change is not None and (imp_change >= 0.20 or pos_improve >= 3.0 or clicks_up):
            verdict, reason = "改善", "表示回数・順位・クリックのいずれかが改善"
        elif imp_change is not None and imp_change <= -0.20 and pos_improve <= -3.0:
            verdict, reason = "悪化", "表示回数が20%以上減少し順位も3位以上悪化"
        else:
            verdict, reason = "変化なし", "改善・悪化条件に未達"

    url = record.get("url")
    if not url and record.get("slug"):
        url = f"{SITE_URL.rstrip('/')}/posts/{record['slug']}/"
    return {
        "url": url or "取得不可",
        "rewrite_date": rewrite_date_raw or "取得不可",
        "elapsed_days": elapsed,
        "before_impressions": before_imp,
        "after_impressions": after_imp,
        "before_clicks": before_clicks,
        "after_clicks": after_clicks,
        "before_ctr": before_ctr,
        "after_ctr": after_ctr,
        "before_position": before_pos,
        "after_position": after_pos,
        "verdict": verdict,
        "reason": reason,
    }


def load_rewrite_tracking(today: date = TODAY) -> list[dict]:
    paths = [BASE / "scripts" / "rewrite_report.json", BASE / "data" / "rewrite_experiments.json"]
    records = []
    seen = set()
    for path in paths:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [WARN] rewrite tracking読み込みエラー {path.name}: {e}")
            continue
        items = data.get("experiments", data) if isinstance(data, dict) else data
        if not isinstance(items, list):
            continue
        for item in items:
            key = item.get("slug") or item.get("url") or item.get("new_title")
            if key in seen:
                continue
            seen.add(key)
            records.append(evaluate_rewrite_record(item, today=today))
    order = {"悪化": 0, "改善": 1, "変化なし": 2, "判定保留": 3}
    records.sort(key=lambda r: (order.get(r["verdict"], 9), -(r.get("elapsed_days") or -1)))
    return records[:10]


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


def _build_weekly_overview_section(
    ga4_metrics: dict,
    ga4_change: dict,
    gsc_summary: dict,
    gsc_change: dict,
    article_progress: dict,
    bottlenecks: list[dict],
) -> str:
    top = ", ".join(_slug_from_url(b.get("page", "")) for b in bottlenecks[:3]) or "該当なし"
    judgement = judge_overall_summary(gsc_change, ga4_change)
    return f"""## 今週の総括

- GA4 Organic Searchセッション: {_fmt_int(ga4_metrics.get('organic_sessions'))}（前週比 {_format_change(ga4_change['organic_sessions'])}）
- GSC表示回数: {_fmt_int(gsc_summary.get('impressions'))}（前週比 {_format_change(gsc_change['impressions'])}）
- GSCクリック数: {_fmt_int(gsc_summary.get('clicks'))}（前週比 {_format_change(gsc_change['clicks'])}）
- 平均掲載順位: {_fmt_float(gsc_summary.get('position'))}（前週 {_fmt_previous(gsc_change['position'], _fmt_float)}）
- 今週の修正記事数: {_fmt_int(article_progress.get('weekly_modified'))}
- 今週の新規記事数: {_fmt_int(article_progress.get('weekly_new'))}
- 最優先対応記事: {top}

{judgement}"""


def _slug_from_url(url: str) -> str:
    m = re.search(r"/posts/([^/]+)/?", url or "")
    return m.group(1) if m else (url or "取得不可")


def _build_ga4_comparison_section(m: dict, ga4_change: dict) -> str:
    rows = [
        ("アクティブユーザー数", _fmt_int(m.get("active_users")), _fmt_previous(ga4_change["active_users"], _fmt_int), _format_change(ga4_change["active_users"])),
        ("セッション数", _fmt_int(m.get("sessions")), _fmt_previous(ga4_change["sessions"], _fmt_int), _format_change(ga4_change["sessions"])),
        ("Organic Searchセッション数", _fmt_int(m.get("organic_sessions")), _fmt_previous(ga4_change["organic_sessions"], _fmt_int), _format_change(ga4_change["organic_sessions"])),
        ("Directセッション数", _fmt_int(m.get("direct_sessions")), _fmt_previous(ga4_change["direct_sessions"], _fmt_int), _format_change(ga4_change["direct_sessions"])),
        ("日本ユーザー率", _fmt_rate(m.get("japan_ratio")), _fmt_previous(ga4_change["japan_ratio"], _fmt_rate), _format_change(ga4_change["japan_ratio"])),
        ("1セッションあたりPV数", f"{m.get('pv_per_sess', 0):.2f}", _fmt_previous(ga4_change["pv_per_sess"], lambda v: f"{float(v or 0):.2f}"), _format_change(ga4_change["pv_per_sess"])),
        ("平均エンゲージ時間", f"{m.get('avg_engagement_time', 0):.1f}秒", _fmt_previous(ga4_change["avg_engagement_time"], lambda v: f"{float(v or 0):.1f}秒"), _format_change(ga4_change["avg_engagement_time"])),
        ("離脱率", _fmt_rate(m.get("bounce_rate")), _fmt_previous(ga4_change["bounce_rate"], _fmt_rate), _format_change(ga4_change["bounce_rate"])),
    ]
    body = "\n".join(f"| {name} | {cur} | {prev} | {chg} |" for name, cur, prev, chg in rows)
    return f"""### 1. GA4 トラフィックサマリー

メイン指標は `hostname = errorlog.jp` のみで集計しています。

| 指標 | 今週 | 前週 | 前週比 |
| :--- | ---: | ---: | ---: |
{body}

| 補助指標 | 今週の実績値 | 状態 |
| :--- | ---: | :--- |
| チャネル比率 | {m['channel_str']} | {_sig(m['organic_ratio'], 0.50, 0.30)} |
| 日本国内率 | {_pct(m['japan_ratio'])}% | {_sig(m['japan_ratio'], 0.60, 0.40)} |
| フロントエラー発生数 | {m['js_errors']:,}件 | {"✅ エラーなし" if m['js_errors'] == 0 else f"🔴 {m['js_errors']}件検出"} |"""


def _build_gsc_summary_section(gsc_summary: dict, gsc_change: dict) -> str:
    if not gsc_summary:
        return """### 2. Search Console サイト全体サマリー

_GSCデータが取得できませんでした。_"""
    rows = [
        ("総表示回数", _fmt_int(gsc_summary.get("impressions")), _fmt_previous(gsc_change["impressions"], _fmt_int), _format_change(gsc_change["impressions"])),
        ("総クリック数", _fmt_int(gsc_summary.get("clicks")), _fmt_previous(gsc_change["clicks"], _fmt_int), _format_change(gsc_change["clicks"])),
        ("平均CTR", _fmt_rate(gsc_summary.get("ctr")), _fmt_previous(gsc_change["ctr"], _fmt_rate), _format_change(gsc_change["ctr"])),
        ("平均掲載順位", _fmt_float(gsc_summary.get("position")), _fmt_previous(gsc_change["position"], _fmt_float), _format_change(gsc_change["position"])),
    ]
    body = "\n".join(f"| {name} | {cur} | {prev} | {chg} |" for name, cur, prev, chg in rows)
    return f"""### 2. Search Console サイト全体サマリー

| 指標 | 今週 | 前週 | 前週比 |
| :--- | ---: | ---: | ---: |
{body}"""


def _build_bottleneck_section(bottlenecks: list[dict]) -> str:
    if not bottlenecks:
        return """### 3. Search Console ボトルネック記事

_今週のボトルネック記事はありませんでした。_"""
    rows = "\n".join(
        f"| {b.get('priority', 'C')} | `{b['page']}` | {b['impressions']:,} | {b['ctr']:.2%} "
        f"| {b['position']:.1f} | {b.get('top_query') or '—'} | {b.get('priority_reason', '既存条件に該当')} |"
        for b in sort_bottlenecks(bottlenecks)[:15]
    )
    return f"""### 3. Search Console ボトルネック記事

判定条件: CTR < {CTR_THRESHOLD:.1%}（インプレッション≥{CTR_IMP_THRESHOLD}件）または掲載順位 {POS_MIN:.0f}〜{POS_MAX:.0f} 位停滞。

| 優先度 | 対象URL | 表示回数 | CTR | 平均順位 | 最多検索クエリ | 判定理由 |
| :--- | :--- | ---: | ---: | ---: | :--- | :--- |
{rows}"""


def _build_rewrite_tracking_section(records: list[dict]) -> str:
    if not records:
        return """### 改善効果トラッカー

_rewrite_report.json / rewrite_experiments.json に表示可能な修正履歴がありません。_"""
    rows = []
    for r in records:
        elapsed = "取得不可" if r.get("elapsed_days") is None else f"{r['elapsed_days']}日"
        rows.append(
            f"| `{r['url']}` | {r['rewrite_date']} | {elapsed} | "
            f"{_fmt_int(r.get('before_impressions') or 0)} | "
            f"{_fmt_int(r.get('after_impressions') or 0)} | "
            f"{_fmt_rate(r.get('before_ctr') or 0)} | "
            f"{_fmt_rate(r.get('after_ctr') or 0)} | "
            f"{_fmt_float(r.get('before_position') or 0)} | "
            f"{_fmt_float(r.get('after_position') or 0)} | "
            f"{r['verdict']} |"
        )
    return """### 改善効果トラッカー

| URL | 修正日 | 修正後経過日数 | 修正前表示回数 | 修正後表示回数 | 修正前CTR | 修正後CTR | 修正前順位 | 修正後順位 | 判定 |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
""" + "\n".join(rows)


def _build_gsc_history_section(history: list[dict]) -> str:
    if not history:
        return """### サイト全体の順位推移

_GSC履歴データがありません。_"""
    rows = "\n".join(
        f"| {h.get('period', '')} | {_fmt_int(h.get('impressions'))} | {_fmt_int(h.get('clicks'))} | "
        f"{_fmt_rate(h.get('ctr'))} | {_fmt_float(h.get('position'))} |"
        for h in history
    )
    trend = judge_gsc_trend(history)
    return f"""### サイト全体の順位推移

直近4週間の傾向: **{trend}**

| 週 | 表示回数 | クリック | CTR | 平均順位 |
| :--- | ---: | ---: | ---: | ---: |
{rows}"""


def _build_index_status_section(index_status: dict) -> str:
    if not index_status.get("available"):
        return f"""### インデックス状況

{index_status.get('message', '取得不可')}"""
    keys = [
        ("インデックス登録済みURL数", "indexed"),
        ("404 URL数", "not_found_404"),
        ("クロール済み・インデックス未登録数", "crawled_not_indexed"),
        ("noindex URL数", "noindex"),
        ("ソフト404数", "soft_404"),
    ]
    rows = "\n".join(
        f"| {label} | {_fmt_int(index_status.get(key))} |"
        for label, key in keys
    )
    return f"""### インデックス状況

入力元: `{index_status.get('source', '取得不可')}` / 日付: {index_status.get('date', '取得不可')}

| 指標 | 値 |
| :--- | ---: |
{rows}"""


def _build_article_progress_section(progress: dict) -> str:
    recent = " / ".join(f"{r['period']}: {r['modified']}" for r in progress.get("recent4_modified", []))
    return f"""### 記事品質改善の進捗

| 指標 | 値 |
| :--- | ---: |
| 公開記事数 | {_fmt_int(progress.get('published_count'))} |
| 手動検証済み | {_fmt_int(progress.get('verified_count'))} |
| 未検証 | {_fmt_int(progress.get('unverified_count'))} |
| 検証進捗率 | {progress.get('verification_rate', 0):.1%} |
| 今週修正 | {_fmt_int(progress.get('weekly_modified'))} |
| 今週新規公開 | {_fmt_int(progress.get('weekly_new'))} |
| 今週非公開化 | {_fmt_int(progress.get('weekly_unpublished'))} |

直近4週間の修正記事数: {recent or 'データ不足'}

> 検証済み判定の入力元: {progress.get('review_status_source', '未設定')}。未設定の場合、不明な記事は未検証として扱います。"""


def render_issue_body(
    m: dict,
    bottlenecks: list[dict],
    period: str,
    gsc_summary: dict | None = None,
    previous_metrics: dict | None = None,
    previous_gsc_summary: dict | None = None,
    gsc_history: list[dict] | None = None,
    article_progress: dict | None = None,
    rewrite_tracking: list[dict] | None = None,
    index_status: dict | None = None,
    noise_section: str = "",
    country_section: str = "",
    content_gap_section: str = "",
    indexnow_section: str = "",
    host_summary_section: str = "",
) -> str:
    if gsc_summary is None:
        gsc_summary = {}
    previous_metrics = previous_metrics or {}
    previous_gsc_summary = previous_gsc_summary or {}
    article_progress = article_progress or {}
    rewrite_tracking = rewrite_tracking or []
    gsc_history = gsc_history or []
    index_status = index_status or {"available": False}
    ga4_change = build_ga4_comparison(m, previous_metrics)
    gsc_change = build_gsc_comparison(gsc_summary, previous_gsc_summary)

    return (
        f"## 週次統合分析レポート（{period}）\n\n"
        + _build_anomaly_section(gsc_change, ga4_change)
        + "\n\n---\n\n"
        + _build_weekly_overview_section(m, ga4_change, gsc_summary, gsc_change, article_progress, sort_bottlenecks(bottlenecks))
        + "\n\n---\n\n"
        + _build_ga4_comparison_section(m, ga4_change)
        + "\n\n---\n\n"
        + _build_gsc_summary_section(gsc_summary, gsc_change)
        + "\n\n---\n\n"
        + _build_bottleneck_section(bottlenecks)
        + "\n\n---\n\n"
        + _build_rewrite_tracking_section(rewrite_tracking)
        + "\n\n---\n\n"
        + _build_gsc_history_section(gsc_history)
        + "\n\n---\n\n"
        + _build_index_status_section(index_status)
        + "\n\n---\n\n"
        + _build_article_progress_section(article_progress)
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
    current_start, current_end = _date_range_pair()
    previous_start, previous_end = _previous_range(current_start, current_end)
    print(f"=== Weekly Unified Report ({period}) ===")

    print("[1/3] Connecting to GA4...")
    try:
        ga4_client = _build_ga4_client()
    except Exception as e:
        print(f"[ERROR] GA4 auth failed: {e}", file=sys.stderr)
        sys.exit(1)

    print("[2/3] Fetching GA4 data...")
    raw_data = fetch_all_ga4(ga4_client, current_start, current_end)
    metrics  = compute_metrics(raw_data)
    previous_raw_data = fetch_all_ga4(ga4_client, previous_start, previous_end)
    previous_metrics = compute_metrics(previous_raw_data)

    print("[3/3] Fetching GSC data...")
    bottlenecks, gsc_summary, previous_gsc_summary = fetch_gsc_data()

    noise_section        = _build_noise_section()
    country_section      = _build_country_section(raw_data.get("countries", []))
    indexnow_section     = _build_indexnow_section()
    content_gap_section  = _load_content_gap_section()
    host_summary         = raw_data.get("host_summary", {})
    host_summary_section = _build_host_summary_section(host_summary)
    article_progress     = build_article_progress(current_start, current_end)
    rewrite_tracking     = load_rewrite_tracking()
    index_status         = load_index_status()
    previous_reports     = _load_previous_weekly_reports()
    gsc_history          = _extract_gsc_history(period, gsc_summary, previous_reports)
    # competitor_section = _load_competitor_section()  # 競合スクレイピングは無効化中
    if content_gap_section:
        print("  → Content Gap データあり（Issueに追記します）")
    if indexnow_section:
        print("  → IndexNow 送信ログあり（Issueに追記します）")

    issue_body = render_issue_body(
        metrics, bottlenecks, period,
        gsc_summary=gsc_summary,
        previous_metrics=previous_metrics,
        previous_gsc_summary=previous_gsc_summary,
        gsc_history=gsc_history,
        article_progress=article_progress,
        rewrite_tracking=rewrite_tracking,
        index_status=index_status,
        noise_section=noise_section,
        country_section=country_section,
        indexnow_section=indexnow_section,
        content_gap_section=content_gap_section,
        host_summary_section=host_summary_section,
    )
    issue_title = f"【週次レポート】GA4 + GSC ボトルネック ({TODAY.isoformat()})"
    ga4_change = build_ga4_comparison(metrics, previous_metrics)
    gsc_change = build_gsc_comparison(gsc_summary, previous_gsc_summary)

    output = {
        "generated_at":      TODAY.isoformat(),
        "period":            period,
        "period_detail": {
            "start": current_start.isoformat(),
            "end": current_end.isoformat(),
        },
        "previous_period": {
            "start": previous_start.isoformat(),
            "end": previous_end.isoformat(),
        },
        "issue_title":       issue_title,
        "issue_body":        issue_body,
        "bottlenecks_count": len(bottlenecks),
        "summary": {
            "judgement": judge_overall_summary(
                gsc_change,
                ga4_change,
            ),
            "anomalies": build_anomaly_alerts(gsc_change, ga4_change),
            "top_bottlenecks": [_slug_from_url(b.get("page", "")) for b in sort_bottlenecks(bottlenecks)[:3]],
        },
        "metrics_snapshot": {
            "active_users":  metrics["active_users"],
            "sessions":      metrics["sessions"],
            "organic_sessions": metrics["organic_sessions"],
            "direct_sessions": metrics["direct_sessions"],
            "organic_ratio": round(metrics["organic_ratio"], 4),
            "japan_ratio":   round(metrics["japan_ratio"],   4),
            "pv_per_sess":   round(metrics["pv_per_sess"],   3),
            "avg_engagement_time": round(metrics["avg_engagement_time"], 3),
            "bounce_rate":   round(metrics["bounce_rate"],   4),
            "js_errors":     metrics["js_errors"],
        },
        "ga4": {
            "current": metrics,
            "previous": previous_metrics,
            "change": ga4_change,
        },
        "gsc": {
            "current": gsc_summary,
            "previous": previous_gsc_summary,
            "change": gsc_change,
            "weekly_history": gsc_history,
        },
        "gsc_summary":      gsc_summary,
        "ga4_host_summary": host_summary,
        "article_progress": article_progress,
        "rewrite_tracking": rewrite_tracking,
        "index_status": index_status,
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
