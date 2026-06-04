"""
週次統合レポート生成スクリプト
GA4 20指標 + Search Console ボトルネック → GitHub Issue 用 Markdown

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

# ── GA4 status thresholds ─────────────────────────────────────────────────────
_THRESHOLDS = {
    "active_users":   (500,   100),    # good >= 500, bad <= 100
    "sessions":       (600,   120),
    "organic_ratio":  (0.50,  0.30),
    "eng_rate":       (0.50,  0.30),
    "avg_eng_sec":    (60.0,  30.0),
    "eng_per_user":   (1.2,   0.8),
    "pv_per_sess":    (2.0,   1.2),
    "scroll_rate":    (0.30,  0.15),
    "vote_rate":      (0.05,  0.01),
    "desktop_ratio":  (0.50,  0.30),
    "new_ratio":      (0.60,  0.30),
    "japan_ratio":    (0.60,  0.40),
    # lower-is-better (inverted):
    "top_land_ratio": (0.50,  0.80),   # concentration <= 50% good, >= 80% bad
    "top_hour_ratio": (0.30,  0.50),
    "pv_conc":        (0.60,  0.80),
    "bounce_rate":    (0.40,  0.70),
}


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

def _date_range_ga4():
    return (
        (TODAY - timedelta(days=6)).strftime("%Y-%m-%d"),
        TODAY.strftime("%Y-%m-%d"),
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


def _run_report_overall(client, metrics):
    """ディメンションなしの集計値を1行で返す。"""
    from google.analytics.data_v1beta.types import (
        DateRange, Metric, RunReportRequest,
    )
    start, end = _date_range_ga4()
    try:
        resp = client.run_report(RunReportRequest(
            property=f"properties/{PROPERTY_ID}",
            metrics=[Metric(name=m) for m in metrics],
            date_ranges=[DateRange(start_date=start, end_date=end)],
        ))
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


# ── GA4: fetch all raw data ────────────────────────────────────────────────────

def fetch_all_ga4(client) -> dict:
    print("  [GA4] overall metrics...")
    overall = _run_report_overall(client, [
        "activeUsers", "sessions", "engagementRate",
        "averageSessionDuration", "engagedSessions",
        "screenPageViews", "bounceRate",
    ])

    print("  [GA4] channel distribution...")
    channels = _run_report(client, ["sessionDefaultChannelGroup"], ["sessions"], row_limit=20)
    channels.sort(key=lambda r: -r.get("sessions", 0))

    print("  [GA4] device category...")
    devices = _run_report(client, ["deviceCategory"], ["sessions"])

    print("  [GA4] new vs returning...")
    nvr = _run_report(client, ["newVsReturning"], ["activeUsers"])

    print("  [GA4] country distribution...")
    countries = _run_report(client, ["country"], ["activeUsers"], row_limit=30)
    countries.sort(key=lambda r: -r.get("activeUsers", 0))

    print("  [GA4] landing pages...")
    landing = _run_report(client, ["landingPage"], ["sessions"], row_limit=20)
    landing.sort(key=lambda r: -r.get("sessions", 0))

    print("  [GA4] hourly distribution...")
    hourly = _run_report(client, ["hour"], ["sessions"])
    hourly.sort(key=lambda r: -r.get("sessions", 0))

    print("  [GA4] page views by page...")
    pages = _run_report(client, ["pagePath"], ["screenPageViews"], row_limit=50)
    pages.sort(key=lambda r: -r.get("screenPageViews", 0))

    print("  [GA4] events...")
    events = _run_report(client, ["eventName"], ["eventCount"], row_limit=100)

    return {
        "overall":   overall,
        "channels":  channels,
        "devices":   devices,
        "nvr":       nvr,
        "countries": countries,
        "landing":   landing,
        "hourly":    hourly,
        "pages":     pages,
        "events":    events,
    }


# ── GA4: compute all 20 metrics ───────────────────────────────────────────────

def compute_metrics(data: dict) -> dict:
    ov        = data["overall"]
    channels  = data["channels"]
    devices   = data["devices"]
    nvr       = data["nvr"]
    countries = data["countries"]
    landing   = data["landing"]
    hourly    = data["hourly"]
    pages     = data["pages"]
    events    = data["events"]

    # ── 基本値 ────────────────────────────────────────────────────────────────
    active_users = int(ov.get("activeUsers",         0))
    sessions     = int(ov.get("sessions",            0))
    eng_rate     = ov.get("engagementRate",          0.0)
    avg_eng_sec  = ov.get("averageSessionDuration",  0.0)
    engaged_sess = int(ov.get("engagedSessions",     0))
    total_pv     = int(ov.get("screenPageViews",     0))
    bounce_rate  = ov.get("bounceRate",              0.0)

    # 3: チャネル比率（上位3チャネルを表示）
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

    # 6: 1人あたりエンゲージメントセッション数
    eng_per_user = engaged_sess / active_users if active_users else 0.0

    # 7: ランディングページ集中度（最多着地ページ / 全着地セッション）
    total_land    = sum(r.get("sessions", 0) for r in landing) or 1
    top_land      = landing[0] if landing else {}
    top_land_sess = top_land.get("sessions", 0)
    top_land_ratio = top_land_sess / total_land
    entrances_str  = f"{top_land.get('landingPage','?')} ({top_land_ratio:.0%})"

    # 8: デバイスカテゴリ別比率（PC率 = desktop / 全デバイス）
    total_dev = sum(r.get("sessions", 0) for r in devices) or 1
    desktop_ratio = next(
        (r.get("sessions", 0) / total_dev
         for r in devices if r.get("deviceCategory", "").lower() == "desktop"),
        0.0,
    )
    devices_sorted = sorted(devices, key=lambda r: -r.get("sessions", 0))
    device_str = ", ".join(
        f"{r.get('deviceCategory', '?')}: {r.get('sessions', 0) / total_dev:.0%}"
        for r in devices_sorted
    ) if devices_sorted else f"PC: {desktop_ratio:.0%}"

    # 9: 新規/リピーター比率
    total_nvr = sum(r.get("activeUsers", 0) for r in nvr) or 1
    new_ratio = next(
        (r.get("activeUsers", 0) / total_nvr
         for r in nvr if r.get("newVsReturning", "").lower() == "new"),
        0.0,
    )
    nvr_str = f"新規: {new_ratio:.0%} / リピーター: {1-new_ratio:.0%}"

    # 10: 日本国内率
    total_country = sum(r.get("activeUsers", 0) for r in countries) or 1
    japan_ratio = next(
        (r.get("activeUsers", 0) / total_country
         for r in countries if r.get("country", "").lower() in ("japan", "日本")),
        0.0,
    )

    # 11: 1セッションあたりPV数
    pv_per_sess = total_pv / sessions if sessions else 0.0

    # 12: スクロール率（GA4標準のscrollイベントは90%到達時に発火）
    scroll_count = _event_count(events, r"^scroll$")
    scroll_rate  = scroll_count / sessions if sessions else 0.0

    # 14: サイト内検索
    site_search = _event_count(events, r"view_search_results|site_search")

    # 15: 時間帯集中度
    total_hourly = sum(r.get("sessions", 0) for r in hourly) or 1
    top_hour     = hourly[0] if hourly else {}
    top_hour_ratio = top_hour.get("sessions", 0) / total_hourly
    hourly_str   = f"{top_hour.get('hour','?')}時台 {top_hour_ratio:.0%}集中"

    # 16: PV集中度（ページ別PVにおける最多ページの割合）
    total_page_pv = sum(r.get("screenPageViews", 0) for r in pages) or 1
    top_page_pv   = pages[0].get("screenPageViews", 0) if pages else 0
    pv_conc       = top_page_pv / total_page_pv
    top_page_path = pages[0].get("pagePath", "?") if pages else "?"
    pv_conc_str   = f"{top_page_path} ({pv_conc:.0%})"

    # 17: JSエラーイベント数
    js_errors = _event_count(events, r"exception|javascript_error|js_error")

    # 18/19: status:yes / status:no カスタムイベント
    status_yes = _event_count(events, r"status_yes|helpful_yes|vote_yes")
    status_no  = _event_count(events, r"status_no|helpful_no|vote_no")

    # 20: 投票率 = (yes + no) / active_users
    vote_rate = (status_yes + status_no) / active_users if active_users else 0.0

    return {
        # 数値（判定に使用）
        "active_users":   active_users,
        "sessions":       sessions,
        "organic_ratio":  organic_ratio,
        "eng_rate":       eng_rate,
        "avg_eng_sec":    avg_eng_sec,
        "eng_per_user":   eng_per_user,
        "top_land_ratio": top_land_ratio,
        "desktop_ratio":  desktop_ratio,
        "new_ratio":      new_ratio,
        "japan_ratio":    japan_ratio,
        "pv_per_sess":    pv_per_sess,
        "scroll_rate":    scroll_rate,
        "bounce_rate":    bounce_rate,
        "site_search":    site_search,
        "top_hour_ratio": top_hour_ratio,
        "pv_conc":        pv_conc,
        "js_errors":      js_errors,
        "status_yes":     status_yes,
        "status_no":      status_no,
        "vote_rate":      vote_rate,
        # 表示文字列
        "channel_str":    channel_str,
        "device_str":     device_str,
        "entrances_str":  entrances_str,
        "nvr_str":        nvr_str,
        "hourly_str":     hourly_str,
        "pv_conc_str":    pv_conc_str,
    }


# ── Status judgment ────────────────────────────────────────────────────────────

def _sig(value: float, good: float, bad: float, lower_is_better: bool = False) -> str:
    """実績値を3段階評価に変換する。"""
    if not lower_is_better:
        if value >= good: return "✅ 良好"
        if value <= bad:  return "🔴 要改善"
        return "⚠️ 要注意"
    else:
        if value <= good: return "✅ 良好"
        if value >= bad:  return "🔴 要改善"
        return "⚠️ 要注意"


def compute_statuses(m: dict) -> list[str]:
    return [
        _sig(m["active_users"],   500,   100),                         # 1
        _sig(m["sessions"],       600,   120),                         # 2
        _sig(m["organic_ratio"],  0.50,  0.30),                        # 3
        _sig(m["eng_rate"],       0.50,  0.30),                        # 4
        _sig(m["avg_eng_sec"],    60.0,  30.0),                        # 5
        _sig(m["eng_per_user"],   1.2,   0.8),                         # 6
        _sig(m["top_land_ratio"], 0.50,  0.80, lower_is_better=True),  # 7
        _sig(m["desktop_ratio"],  0.50,  0.30),                        # 8
        _sig(m["new_ratio"],      0.60,  0.30),                        # 9
        _sig(m["japan_ratio"],    0.60,  0.40),                        # 10
        _sig(m["pv_per_sess"],    2.0,   1.2),                         # 11
        _sig(m["scroll_rate"],    0.30,  0.15),                        # 12
        _sig(m["bounce_rate"],    0.40,  0.70, lower_is_better=True),  # 13
        ("✅ 良好" if m["site_search"] > 10
         else "⚠️ 低利用" if m["site_search"] > 0
         else "ℹ️ なし"),                                               # 14
        _sig(m["top_hour_ratio"], 0.30,  0.50, lower_is_better=True),  # 15
        _sig(m["pv_conc"],        0.60,  0.80, lower_is_better=True),  # 16
        ("✅ エラーなし" if m["js_errors"] == 0
         else f"🔴 {m['js_errors']}件検出"),                            # 17
        ("✅ 良好" if m["status_yes"] > 10
         else "⚠️ 少ない" if m["status_yes"] > 0
         else "ℹ️ なし"),                                               # 18
        ("✅ 良好" if m["status_no"] < m["status_yes"] and m["status_yes"] > 0
         else "⚠️ 要注意" if m["status_no"] > 0
         else "ℹ️ なし"),                                               # 19
        _sig(m["vote_rate"],      0.05,  0.01),                        # 20
    ]


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
    end   = TODAY.strftime("%Y-%m-%d")
    start = (TODAY - timedelta(days=6)).strftime("%Y-%m-%d")
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


# ── GSC: fetch bottlenecks ────────────────────────────────────────────────────

def fetch_gsc_bottlenecks() -> list[dict]:
    try:
        service = _build_gsc_service()
    except Exception as e:
        print(f"  [WARN] GSC auth failed: {e}")
        return []

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

    total_ctr_avg   = sum(r["ctr"] for r in page_rows) / len(page_rows)
    effective_ctr   = min(CTR_THRESHOLD, total_ctr_avg * 0.7)

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


# ── Markdown rendering ────────────────────────────────────────────────────────

def _pct(v: float, dec: int = 1) -> str:
    """0.456 → '45.6'（% 記号なし。テンプレート側で % を付加する）"""
    return f"{v * 100:.{dec}f}"


def render_issue_body(m: dict, statuses: list[str], bottlenecks: list[dict], period: str) -> str:
    s = statuses

    ga4_table = f"""\
### 1. 全体トラフィック＆品質サマリー（GA4 20指標）

| 分類 | # | 指標名 | 今週の実績値 | 状態 |
| :--- | :--- | :--- | :--- | :--- |
| **集客・アクセス** | 1 | アクティブ ユーザー数 | {m['active_users']:,} | {s[0]} |
| | 2 | セッション数 | {m['sessions']:,} | {s[1]} |
| | 3 | セッションの獲得チャネル比率 | {m['channel_str']} | {s[2]} |
| **品質・エンゲージメント** | 4 | エンゲージメント率 | {_pct(m['eng_rate'])}% | {s[3]} |
| | 5 | 平均エンゲージメント時間 | {m['avg_eng_sec']:.0f}秒 | {s[4]} |
| | 6 | 1人あたりエンゲージメントセッション数 | {m['eng_per_user']:.2f} | {s[5]} |
| | 7 | 閲覧開始数（個別記事の着地偏り） | {m['entrances_str']} | {s[6]} |
| **ユーザー特性・端末** | 8 | デバイス カテゴリ（PC率） | {m['device_str']} | {s[7]} |
| | 9 | 新規とリピーターの比率 | {m['nvr_str']} | {s[8]} |
| | 10 | 国および地域（日本国内率） | {_pct(m['japan_ratio'])}% | {s[9]} |
| **回遊・動線ログ** | 11 | 1セッションあたりのPV数 | {m['pv_per_sess']:.2f} | {s[10]} |
| | 12 | スクロール数（90%読了率） | {_pct(m['scroll_rate'])}% | {s[11]} |
| | 13 | 離脱率（直帰率ベース） | {_pct(m['bounce_rate'])}% | {s[12]} |
| | 14 | サイト内検索の利用回数 | {m['site_search']:,}回 | {s[13]} |
| **自律異常検知** | 15 | 時間帯別のセッション分布 | {m['hourly_str']} | {s[14]} |
| | 16 | PVの特定記事への集中度 | {m['pv_conc_str']} | {s[15]} |
| | 17 | ページごとのフロントエラー発生数 | {m['js_errors']:,}件 | {s[16]} |
| **コンバージョン** | 18 | カスタムイベント：status: yes | {m['status_yes']:,} | {s[17]} |
| | 19 | カスタムイベント：status: no | {m['status_no']:,} | {s[18]} |
| | 20 | イベント発生率（投票率） | {_pct(m['vote_rate'])}% | {s[19]} |"""

    if bottlenecks:
        rows = "\n".join(
            f"| {i+1} | `{b['page']}` | {b['impressions']:,} | {b['ctr']:.2%} "
            f"| {b['position']:.1f} | {b['top_query'] or '—'} |"
            for i, b in enumerate(bottlenecks[:15])
        )
        gsc_section = f"""

### 2. 今週のSearch Console ボトルネック記事

判定条件: CTR < {CTR_THRESHOLD:.1%}（インプレッション≥{CTR_IMP_THRESHOLD}件）または掲載順位 {POS_MIN:.0f}〜{POS_MAX:.0f} 位停滞。

| # | 対象URL | 表示回数 | CTR | 平均掲載順位 | 最多検索クエリ（top_query） |
| :--- | :--- | :--- | :--- | :--- | :--- |
{rows}"""
    else:
        gsc_section = """

### 2. 今週のSearch Console ボトルネック記事

_今週のボトルネック記事はありませんでした。_"""

    return (
        f"## 週次統合分析レポート（{period}）\n\n"
        + ga4_table
        + gsc_section
        + "\n\n> このIssueは `weekly_ga4.yml` によって自動生成されました。対応完了後クローズしてください。"
    )


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    if not PROPERTY_ID:
        print("[ERROR] GA4_PROPERTY_ID is not set.", file=sys.stderr)
        sys.exit(1)

    period = f"{TODAY - timedelta(days=6)} 〜 {TODAY}"
    print(f"=== Weekly Unified Report ({period}) ===")

    print("[1/3] Connecting to GA4...")
    try:
        ga4_client = _build_ga4_client()
    except Exception as e:
        print(f"[ERROR] GA4 auth failed: {e}", file=sys.stderr)
        sys.exit(1)

    print("[2/3] Fetching GA4 data (20 metrics)...")
    raw_data = fetch_all_ga4(ga4_client)
    metrics  = compute_metrics(raw_data)
    statuses = compute_statuses(metrics)

    print("[3/3] Fetching GSC bottlenecks...")
    bottlenecks = fetch_gsc_bottlenecks()

    issue_body  = render_issue_body(metrics, statuses, bottlenecks, period)
    issue_title = f"【週次統合レポート】GA4 20指標 + GSC ボトルネック ({TODAY.isoformat()})"

    output = {
        "generated_at":       TODAY.isoformat(),
        "period":             period,
        "issue_title":        issue_title,
        "issue_body":         issue_body,
        "bottlenecks_count":  len(bottlenecks),
        "metrics_snapshot": {
            "active_users":  metrics["active_users"],
            "sessions":      metrics["sessions"],
            "eng_rate":      round(metrics["eng_rate"],    4),
            "avg_eng_sec":   round(metrics["avg_eng_sec"], 1),
            "bounce_rate":   round(metrics["bounce_rate"], 4),
            "pv_per_sess":   round(metrics["pv_per_sess"], 3),
            "scroll_rate":   round(metrics["scroll_rate"], 4),
            "japan_ratio":   round(metrics["japan_ratio"], 4),
            "desktop_ratio": round(metrics["desktop_ratio"], 4),
            "vote_rate":     round(metrics["vote_rate"],   6),
        },
    }
    REPORT_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nSaved: {REPORT_FILE.relative_to(BASE)}")
    print(f"  active_users={metrics['active_users']}, sessions={metrics['sessions']}, "
          f"eng_rate={metrics['eng_rate']:.1%}, bottlenecks={len(bottlenecks)}")
    print("Done.")


if __name__ == "__main__":
    main()
