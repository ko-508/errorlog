"""
Google Search Console API から過去7日間の検索パフォーマンスデータを取得し、
ボトルネック記事（高インプレッション低CTR・11〜20位停滞）を自動判定する。

出力:
  reports/ga4/gsc_YYYYMMDD.json   ボトルネックデータ（Issue 起票用）
  scripts/rewrite_priority.json   top_query を追記（refresh_articles.py 連携）

認証（優先順）:
  GSC_SERVICE_ACCOUNT_KEY   サービスアカウント JSON 文字列
  GA4_SERVICE_ACCOUNT_KEY   フォールバック（同一 SA が GSC にもアクセス権を持つ場合）
"""

import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

BASE        = Path(__file__).parent.parent
SCRIPTS_DIR = Path(__file__).parent
POSTS_DIR   = BASE / "content" / "posts"
REPORTS_DIR = BASE / "reports" / "ga4"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

TODAY    = date.today()
SITE_URL = os.getenv("GSC_SITE_URL", "https://errorlog.jp/")

# ── Thresholds ────────────────────────────────────────────────────────────────
CTR_IMP_THRESHOLD = int(os.getenv("CTR_IMP_THRESHOLD",  "50"))    # CTR 判定の最低インプレッション数
CTR_THRESHOLD     = float(os.getenv("CTR_THRESHOLD",    "0.015")) # CTR 1.5% 未満 → ボトルネック
POS_IMP_THRESHOLD = int(os.getenv("POS_IMP_THRESHOLD",  "20"))    # 順位判定の最低インプレッション数
POS_MIN           = float(os.getenv("POS_MIN",           "11.0")) # 停滞圏 上限（11位〜）
POS_MAX           = float(os.getenv("POS_MAX",           "20.0")) # 停滞圏 下限（〜20位）
ROW_LIMIT         = 1000

GSC_REPORT_FILE = REPORTS_DIR / f"gsc_{TODAY.strftime('%Y%m%d')}.json"
PRIORITY_FILE   = SCRIPTS_DIR / "rewrite_priority.json"


# ── Authentication ────────────────────────────────────────────────────────────

_GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


def _build_service():
    """認証優先順:
    1. GSC_SERVICE_ACCOUNT_KEY  サービスアカウント JSON（Search Console にユーザー追加不要）
    2. GA4_SERVICE_ACCOUNT_KEY  同上（GA4 と共用 SA の場合）
    3. GSC_OAUTH_* / GA4_OAUTH_* OAuth2リフレッシュトークン（Search Console プロパティへ
       アクセス権を持つ Google アカウントで取得したもの）
    """
    from googleapiclient.discovery import build

    # ── サービスアカウント ──────────────────────────────────────────────────
    sa_json = (
        os.environ.get("GSC_SERVICE_ACCOUNT_KEY", "").strip()
        or os.environ.get("GA4_SERVICE_ACCOUNT_KEY", "").strip()
    )
    if sa_json:
        from google.oauth2.service_account import Credentials
        info  = json.loads(sa_json)
        creds = Credentials.from_service_account_info(info, scopes=_GSC_SCOPES)
        return build("searchconsole", "v1", credentials=creds, cache_discovery=False)

    # ── OAuth2（GA4_OAUTH_* または GSC_OAUTH_* を流用） ───────────────────
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

    raise RuntimeError(
        "GSC auth missing. Set one of:\n"
        "  GSC_SERVICE_ACCOUNT_KEY  (service account JSON)\n"
        "  GA4_OAUTH_CLIENT_ID + GA4_OAUTH_CLIENT_SECRET + GA4_OAUTH_REFRESH_TOKEN  (OAuth2)"
    )


# ── API helpers ───────────────────────────────────────────────────────────────

def _date_range() -> dict[str, str]:
    end   = TODAY.strftime("%Y-%m-%d")
    start = (TODAY - timedelta(days=6)).strftime("%Y-%m-%d")
    return {"startDate": start, "endDate": end}


def _query(service, dimensions: list[str], row_limit: int = ROW_LIMIT) -> list[dict]:
    body = {
        **_date_range(),
        "dimensions":       dimensions,
        "rowLimit":         row_limit,
        "dataState":        "all",
    }
    try:
        resp = service.searchanalytics().query(siteUrl=SITE_URL, body=body).execute()
    except Exception as e:
        print(f"  [WARN] GSC query failed (dimensions={dimensions}): {e}")
        return []

    rows = []
    for r in resp.get("rows", []):
        keys   = r.get("keys", [])
        entry  = {d: keys[i] for i, d in enumerate(dimensions) if i < len(keys)}
        entry["impressions"] = r.get("impressions", 0)
        entry["clicks"]      = r.get("clicks",      0)
        entry["ctr"]         = r.get("ctr",         0.0)
        entry["position"]    = r.get("position",    0.0)
        rows.append(entry)
    return rows


# ── Data processing ───────────────────────────────────────────────────────────

def fetch_page_metrics(service) -> list[dict]:
    """ページ別パフォーマンス指標を取得。/posts/ 以外を除外。"""
    rows = _query(service, ["page"])
    filtered = [r for r in rows if "/posts/" in r.get("page", "")]
    print(f"  page metrics: {len(filtered)} /posts/ rows (total {len(rows)})")
    return filtered


def fetch_top_queries(service) -> dict[str, str]:
    """ページごとの最多インプレッションクエリを返す {page_url: top_query}。"""
    rows = _query(service, ["query", "page"])

    best: dict[str, tuple[str, int]] = {}  # page → (query, impressions)
    for r in rows:
        page  = r.get("page", "")
        query = r.get("query", "")
        imp   = int(r.get("impressions", 0))
        if "/posts/" not in page:
            continue
        if page not in best or imp > best[page][1]:
            best[page] = (query, imp)

    return {page: q for page, (q, _) in best.items()}


def identify_bottlenecks(
    page_rows: list[dict],
    top_queries: dict[str, str],
) -> list[dict]:
    """ボトルネック記事を判定してスコア付きリストで返す。"""
    results = []
    total_ctr_avg = (
        sum(r["ctr"] for r in page_rows) / len(page_rows) if page_rows else 0.0
    )
    effective_ctr_threshold = min(CTR_THRESHOLD, total_ctr_avg * 0.7)

    for r in page_rows:
        page       = r["page"]
        impressions = int(r["impressions"])
        clicks      = int(r["clicks"])
        ctr         = r["ctr"]
        position    = r["position"]
        top_query   = top_queries.get(page, "")

        reasons = []

        # 判定1: 高インプレッション低CTR
        if impressions >= CTR_IMP_THRESHOLD and ctr < effective_ctr_threshold:
            reasons.append(
                f"CTR {ctr:.1%} < 閾値 {effective_ctr_threshold:.1%}"
                f"（インプレッション {impressions}）"
            )

        # 判定2: 11〜20位停滞
        if impressions >= POS_IMP_THRESHOLD and POS_MIN <= position <= POS_MAX:
            reasons.append(f"掲載順位 {position:.1f} 位（停滞圏 {POS_MIN:.0f}〜{POS_MAX:.0f} 位）")

        if not reasons:
            continue

        # パスからスラグ抽出: /posts/docker_503/ → docker_503
        slug = re.search(r"/posts/([^/]+)/?$", page)
        slug = slug.group(1) if slug else ""

        results.append({
            "page":        page,
            "slug":        slug,
            "impressions": impressions,
            "clicks":      clicks,
            "ctr":         round(ctr, 4),
            "position":    round(position, 1),
            "top_query":   top_query,
            "reasons":     reasons,
        })

    # インプレッション降順
    results.sort(key=lambda x: -x["impressions"])
    return results


# ── Persistence ───────────────────────────────────────────────────────────────

def save_gsc_report(bottlenecks: list[dict], page_rows: list[dict]) -> None:
    output = {
        "generated_at":     TODAY.isoformat(),
        "site_url":         SITE_URL,
        "period_days":      7,
        "ctr_threshold":    CTR_THRESHOLD,
        "pos_range":        [POS_MIN, POS_MAX],
        "total_pages":      len(page_rows),
        "bottlenecks":      bottlenecks,
    }
    GSC_REPORT_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  GSC report: {GSC_REPORT_FILE.relative_to(BASE)}")


def _article_title_from_slug(slug: str) -> str:
    """スラグから記事タイトルを取得する。"""
    md = POSTS_DIR / f"{slug}.md"
    if not md.exists():
        return ""
    text = md.read_text(encoding="utf-8-sig")
    m = re.search(r'^title:\s*"?([^"\n]+)"?\s*$', text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def update_priority_with_top_query(bottlenecks: list[dict]) -> None:
    """rewrite_priority.json に top_query を追記・更新する。"""
    existing: list[dict] = []
    if PRIORITY_FILE.exists():
        try:
            existing = json.loads(PRIORITY_FILE.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    existing_by_title: dict[str, dict] = {e["title"]: e for e in existing}
    added = updated = 0

    for b in bottlenecks:
        if not b["top_query"] or not b["slug"]:
            continue

        title = _article_title_from_slug(b["slug"])
        if not title:
            continue

        entry = existing_by_title.get(title)
        if entry:
            entry["top_query"]      = b["top_query"]
            entry["gsc_position"]   = b["position"]
            entry["gsc_ctr"]        = b["ctr"]
            entry["gsc_reasons"]    = b["reasons"]
            updated += 1
        else:
            new_entry = {
                "title":         title,
                "priority_score": 0.5,
                "critical":       False,
                "no_ratio":       0.0,
                "no_count":       0,
                "engagement_sec": 0.0,
                "top_query":      b["top_query"],
                "gsc_position":   b["position"],
                "gsc_ctr":        b["ctr"],
                "gsc_reasons":    b["reasons"],
                "queued_at":      TODAY.isoformat(),
                "source":         "gsc_bottleneck",
            }
            existing.append(new_entry)
            existing_by_title[title] = new_entry
            added += 1

    PRIORITY_FILE.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  rewrite_priority.json: +{added} added, {updated} updated with top_query")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    if not SITE_URL:
        print("[ERROR] GSC_SITE_URL is not set.", file=sys.stderr)
        sys.exit(1)

    print(f"=== Search Console Analysis ({TODAY}) ===")
    print(f"  Site: {SITE_URL}")

    try:
        service = _build_service()
    except Exception as e:
        print(f"[ERROR] GSC auth failed: {e}", file=sys.stderr)
        sys.exit(1)

    print("  [1/3] Fetching page metrics...")
    # 診断用: /posts/ フィルター前の全データを確認
    raw_rows = _query(service, ["page"])
    print(f"  raw rows from API: {len(raw_rows)}")
    if raw_rows:
        sample = raw_rows[0].get("page", "")
        print(f"  sample page URL: {sample}")
    page_rows = [r for r in raw_rows if "/posts/" in r.get("page", "")]
    print(f"  /posts/ rows after filter: {len(page_rows)}")

    # データが空でもレポートは常に保存する
    if not raw_rows:
        print("  [WARN] No data returned from Search Console API.")
        print("         Check: site URL, OAuth scope (webmasters.readonly), property access.")
        save_gsc_report([], [])
        return

    print("  [2/3] Fetching top queries per page...")
    top_queries = fetch_top_queries(service)
    print(f"  top queries resolved: {len(top_queries)} pages")

    print("  [3/3] Identifying bottlenecks...")
    bottlenecks = identify_bottlenecks(page_rows, top_queries)
    print(f"  bottlenecks: {len(bottlenecks)} pages")

    for b in bottlenecks[:10]:
        print(
            f"    [{b['position']:.1f}位 / CTR {b['ctr']:.1%}]  "
            f"{b['page']}"
            + (f"\n      top_query: {b['top_query']}" if b['top_query'] else "")
        )

    save_gsc_report(bottlenecks, page_rows)
    update_priority_with_top_query(bottlenecks)
    print("\nDone.")


if __name__ == "__main__":
    main()
