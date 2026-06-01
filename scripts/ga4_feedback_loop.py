"""
GA4 feedback loop + bottleneck reporter + priority scoring (Task C)

Task 07: error_solved votes → rewrite_priority.json + lastmod reset
Task 08: low-engagement pages → bottleneck_YYYYMMDD.json (GitHub Issue source)
Task C:  Combined scoring = no_ratio × instant-bounce factor
         Critical articles (score > CRITICAL_SCORE_THRESHOLD) get
         lastmod reset to CRITICAL_LASTMOD_DAYS ago so refresh_articles.py
         processes them at the absolute top of its queue.

Auth (priority order):
  GA4_SERVICE_ACCOUNT_KEY  Service account JSON string (CI recommended)
  GA4_OAUTH_CLIENT_ID / GA4_OAUTH_CLIENT_SECRET / GA4_OAUTH_REFRESH_TOKEN
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

TODAY       = date.today()
PROPERTY_ID = os.environ.get("GA4_PROPERTY_ID", "").strip()

# ── Thresholds ────────────────────────────────────────────────────────────────
NO_COUNT_THRESHOLD      = int(os.getenv("NO_COUNT_THRESHOLD",   "3"))
NO_RATIO_THRESHOLD      = float(os.getenv("NO_RATIO_THRESHOLD", "0.5"))
INSTANT_BOUNCE_SEC      = float(os.getenv("INSTANT_BOUNCE_SEC", "30.0"))
CRITICAL_SCORE_THRESHOLD = float(os.getenv("CRITICAL_SCORE",   "1.0"))
PRIORITY_TOP_N          = int(os.getenv("PRIORITY_TOP_N",       "5"))
BOTTLENECK_TOP_N        = int(os.getenv("BOTTLENECK_TOP_N",     "10"))
BOTTLENECK_MIN_PV       = int(os.getenv("BOTTLENECK_MIN_PV",    "10"))

# Days to subtract from today when resetting lastmod
# Critical (score > CRITICAL_SCORE_THRESHOLD): pushed to the very front
# Normal priority: just past the REFRESH_DAYS threshold
_CRITICAL_LASTMOD_DAYS = 365
_NORMAL_LASTMOD_DAYS   = 91

PRIORITY_FILE   = SCRIPTS_DIR / "rewrite_priority.json"
BOTTLENECK_FILE = REPORTS_DIR / f"bottleneck_{TODAY.strftime('%Y%m%d')}.json"


# ── Authentication ────────────────────────────────────────────────────────────

def _build_client():
    from google.analytics.data_v1beta import BetaAnalyticsDataClient

    sa_key = os.environ.get("GA4_SERVICE_ACCOUNT_KEY", "").strip()
    if sa_key:
        from google.oauth2.service_account import Credentials
        info = json.loads(sa_key)
        creds = Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/analytics.readonly"],
        )
        return BetaAnalyticsDataClient(credentials=creds)

    client_id     = os.environ.get("GA4_OAUTH_CLIENT_ID",     "").strip()
    client_secret = os.environ.get("GA4_OAUTH_CLIENT_SECRET", "").strip()
    refresh_token = os.environ.get("GA4_OAUTH_REFRESH_TOKEN", "").strip()
    if not all([client_id, client_secret, refresh_token]):
        raise RuntimeError(
            "GA4 auth missing: set GA4_SERVICE_ACCOUNT_KEY or OAuth credentials."
        )
    from google.oauth2.credentials import Credentials
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/analytics.readonly"],
    )
    return BetaAnalyticsDataClient(credentials=creds)


# ── GA4 report runner ─────────────────────────────────────────────────────────

def _run_report(client, dimensions, metrics, days=7, dim_filter=None):
    from google.analytics.data_v1beta.types import (
        DateRange, Dimension, Metric, RunReportRequest,
    )
    end   = TODAY.strftime("%Y-%m-%d")
    start = (TODAY - timedelta(days=days - 1)).strftime("%Y-%m-%d")

    kwargs = dict(
        property=f"properties/{PROPERTY_ID}",
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metrics],
        date_ranges=[DateRange(start_date=start, end_date=end)],
    )
    if dim_filter is not None:
        kwargs["dimension_filter"] = dim_filter

    response = client.run_report(RunReportRequest(**kwargs))
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


def _event_name_filter(event_name: str):
    from google.analytics.data_v1beta.types import FilterExpression, Filter
    return FilterExpression(
        filter=Filter(
            field_name="eventName",
            string_filter=Filter.StringFilter(
                match_type=Filter.StringFilter.MatchType.EXACT,
                value=event_name,
            ),
        )
    )


# ── Task 07 / Task C: vote data ───────────────────────────────────────────────

def fetch_feedback_votes(client) -> list[dict]:
    """Aggregate error_solved events by article_title × status."""
    try:
        rows = _run_report(
            client,
            dimensions=["customEvent:article_title", "customEvent:status"],
            metrics=["eventCount"],
            days=7,
            dim_filter=_event_name_filter("error_solved"),
        )
        print(f"  error_solved votes: {len(rows)} rows")
        return rows
    except Exception as e:
        print(f"  [WARN] customEvent dimensions unavailable ({e})")
        print("  -> falling back to pageTitle + total eventCount")
        return _fetch_feedback_fallback(client)


def _fetch_feedback_fallback(client) -> list[dict]:
    try:
        rows = _run_report(
            client,
            dimensions=["pageTitle"],
            metrics=["eventCount"],
            days=7,
            dim_filter=_event_name_filter("error_solved"),
        )
        return [
            {
                "customEvent:article_title": r.get("pageTitle", ""),
                "customEvent:status":        "(unknown)",
                "eventCount":                r.get("eventCount", 0),
            }
            for r in rows
        ]
    except Exception as e:
        print(f"  [WARN] fallback also failed: {e}")
        return []


# ── Task C: page-level engagement data ───────────────────────────────────────

def fetch_page_engagement(client) -> list[dict]:
    """Fetch per-page engagement metrics for the scoring join.

    Returns rows with keys: pageTitle, pagePath,
    averageSessionDuration, engagementRate, screenPageViews.
    Only /posts/ pages are included; hub/nav pages are excluded.
    """
    try:
        rows = _run_report(
            client,
            dimensions=["pageTitle", "pagePath"],
            metrics=[
                "screenPageViews",
                "averageSessionDuration",
                "engagementRate",
            ],
            days=7,
        )
        return [r for r in rows if "/posts/" in r.get("pagePath", "")]
    except Exception as e:
        print(f"  [WARN] page engagement fetch failed: {e}")
        return []


# ── Task C: priority scoring ──────────────────────────────────────────────────

def _priority_score(no_ratio: float, no_count: int, engagement_sec: float) -> float:
    """Composite rewrite-priority score.

    Formula: no_ratio × (1 + instant_bounce_factor)

    instant_bounce_factor = max(0, 1 - engagement_sec / INSTANT_BOUNCE_SEC)
      → 1.0 at 0s engagement, 0.0 at ≥ 30s engagement (linear decay)

    Score interpretation:
      ≥ CRITICAL_SCORE_THRESHOLD  → critical (instant bounce + high no ratio)
      > 0                         → needs rewrite (high no ratio alone)
      0                           → below threshold, no action
    """
    if no_count < NO_COUNT_THRESHOLD and no_ratio < NO_RATIO_THRESHOLD:
        return 0.0
    bounce_factor = max(0.0, 1.0 - engagement_sec / INSTANT_BOUNCE_SEC)
    return round(no_ratio * (1.0 + bounce_factor), 4)


def score_articles(vote_rows: list[dict], engagement_rows: list[dict]) -> list[dict]:
    """Join vote data with page engagement metrics and compute priority scores.

    Steps:
      1. Aggregate no/yes counts per article title from vote_rows.
      2. Build title → engagement_sec lookup from engagement_rows.
      3. Compute _priority_score for each article.
      4. Return list sorted by score descending, filtered to score > 0.
    """
    from collections import defaultdict

    # Step 1: aggregate votes
    counts: dict[str, dict] = defaultdict(lambda: {"yes": 0, "no": 0})
    for r in vote_rows:
        title  = r.get("customEvent:article_title", "").strip()
        status = r.get("customEvent:status", "").strip().lower()
        count  = int(r.get("eventCount", 0))
        if not title:
            continue
        if status == "yes":
            counts[title]["yes"] += count
        elif status == "no":
            counts[title]["no"] += count
        else:
            counts[title]["no"] += count  # unknown → conservative

    # Step 2: build engagement lookup (normalized title → engagement_sec)
    engagement_map: dict[str, float] = {}
    for r in engagement_rows:
        eng_title = r.get("pageTitle", "").strip()
        if eng_title:
            engagement_map[eng_title] = r.get("averageSessionDuration", 0.0)

    # Step 3: score each article
    scored = []
    for title, c in counts.items():
        total = c["yes"] + c["no"]
        if total == 0:
            continue
        no_ratio      = c["no"] / total
        engagement_sec = engagement_map.get(title, 0.0)
        score          = _priority_score(no_ratio, c["no"], engagement_sec)
        if score <= 0.0:
            continue
        scored.append({
            "title":          title,
            "yes":            c["yes"],
            "no":             c["no"],
            "total":          total,
            "no_ratio":       round(no_ratio, 3),
            "engagement_sec": round(engagement_sec, 1),
            "priority_score": score,
            "critical":       score >= CRITICAL_SCORE_THRESHOLD,
        })

    scored.sort(key=lambda x: -x["priority_score"])
    return scored


# ── Priority queue persistence ────────────────────────────────────────────────

def update_priority_queue(scored: list[dict]) -> None:
    """Write scored articles to rewrite_priority.json.

    New entries are inserted at the head (highest priority first).
    Critical articles are marked and will receive a more aggressive lastmod reset.
    """
    existing: list[dict] = []
    if PRIORITY_FILE.exists():
        try:
            existing = json.loads(PRIORITY_FILE.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    existing_titles = {e["title"] for e in existing}
    new_entries: list[dict] = []
    for item in scored:
        if item["title"] in existing_titles:
            continue
        new_entries.append({
            "title":          item["title"],
            "priority_score": item["priority_score"],
            "critical":       item["critical"],
            "no_ratio":       item["no_ratio"],
            "no_count":       item["no"],
            "engagement_sec": item["engagement_sec"],
            "queued_at":      TODAY.isoformat(),
            "source":         "ga4_feedback_loop",
        })

    # Critical articles go to the very front
    merged = (
        [e for e in new_entries if e["critical"]]
        + [e for e in new_entries if not e["critical"]]
        + existing
    )
    PRIORITY_FILE.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    critical_new = sum(1 for e in new_entries if e["critical"])
    print(
        f"  rewrite_priority.json: +{len(new_entries)} added "
        f"({critical_new} critical), {len(merged)} total"
    )


def reset_lastmod_for_priority(scored: list[dict]) -> int:
    """Reset lastmod in content/posts/ to force articles into refresh_articles.py queue.

    Critical articles (score ≥ CRITICAL_SCORE_THRESHOLD) are set to
    _CRITICAL_LASTMOD_DAYS ago so they sort to the absolute top.
    Normal articles are set to _NORMAL_LASTMOD_DAYS ago.
    """
    title_to_score = {item["title"]: item for item in scored}
    reset = 0

    for md in POSTS_DIR.glob("*.md"):
        text = md.read_text(encoding="utf-8")
        m = re.match(r'^---\n(.*?)\n---\n', text, re.DOTALL)
        if not m:
            continue
        title_m = re.search(r'^title:\s*"?([^"\n]+)"?\s*$', m.group(1), re.MULTILINE)
        if not title_m:
            continue
        article_title = title_m.group(1).strip()
        if article_title not in title_to_score:
            continue

        item     = title_to_score[article_title]
        days_ago = _CRITICAL_LASTMOD_DAYS if item["critical"] else _NORMAL_LASTMOD_DAYS
        old_date = (TODAY - timedelta(days=days_ago)).isoformat()

        if "lastmod:" in text:
            new_text = re.sub(r'(?m)^lastmod:.*$', f'lastmod: {old_date}', text, count=1)
        else:
            new_text = text.replace(
                m.group(0),
                m.group(0).replace('\n---\n', f'\nlastmod: {old_date}\n---\n', 1),
            )

        if new_text != text:
            md.write_text(new_text, encoding="utf-8")
            label = "CRITICAL" if item["critical"] else "normal"
            print(f"  lastmod reset [{label}] → {old_date}: {md.name}")
            reset += 1

    return reset


# ── Task 08: bottleneck page extraction ───────────────────────────────────────

def fetch_bottleneck_pages(client) -> list[dict]:
    """Extract /posts/ pages with low engagement time.

    Filters: pagePath must contain /posts/ AND screenPageViews >= BOTTLENECK_MIN_PV.
    Hub/nav pages (/, /search/, /tags/, external Zenn pages, etc.) are excluded.
    """
    rows = _run_report(
        client,
        dimensions=["pagePath", "pageTitle"],
        metrics=[
            "screenPageViews",
            "averageSessionDuration",
            "engagementRate",
            "bounceRate",
        ],
        days=7,
    )
    rows = [
        r for r in rows
        if "/posts/" in r.get("pagePath", "")
        and r.get("screenPageViews", 0) >= BOTTLENECK_MIN_PV
    ]
    rows.sort(key=lambda r: r.get("averageSessionDuration", 0))
    return rows[:BOTTLENECK_TOP_N]


def save_bottleneck(bottleneck: list[dict]) -> None:
    output = {
        "generated_at": TODAY.isoformat(),
        "period_days":  7,
        "threshold_pv": BOTTLENECK_MIN_PV,
        "top_n":        BOTTLENECK_TOP_N,
        "pages":        bottleneck,
    }
    BOTTLENECK_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  bottleneck file: {BOTTLENECK_FILE.relative_to(BASE)}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    if not PROPERTY_ID:
        print("[ERROR] GA4_PROPERTY_ID is not set.", file=sys.stderr)
        sys.exit(1)

    client = _build_client()

    # ── Task 07 + Task C: scored feedback loop ────────────────────────────────
    print("=== Task C: priority scoring (votes × engagement) ===")

    print("  [1/2] Fetching error_solved votes...")
    vote_rows = fetch_feedback_votes(client)

    print("  [2/2] Fetching page engagement metrics...")
    engagement_rows = fetch_page_engagement(client)

    scored = score_articles(vote_rows, engagement_rows)
    top    = scored[:PRIORITY_TOP_N]

    print(f"\n  Scored articles: {len(scored)}  |  Top {PRIORITY_TOP_N} for rewrite queue:")
    for item in top:
        flag = "🔴 CRITICAL" if item["critical"] else "🟡 priority"
        print(
            f"    [{flag}] score={item['priority_score']:.3f} "
            f"no={item['no_ratio']:.0%} eng={item['engagement_sec']:.1f}s  "
            f"{item['title'][:60]}"
        )

    if top:
        update_priority_queue(top)
        reset_count = reset_lastmod_for_priority(top)
        print(f"  lastmod reset: {reset_count} files")
    else:
        print("  No priority rewrite targets this week.")

    # ── Task 08: bottleneck extraction ────────────────────────────────────────
    print("\n=== Task 08: bottleneck page extraction ===")
    bottleneck = fetch_bottleneck_pages(client)
    print(f"  Bottleneck pages: {len(bottleneck)}")
    for r in bottleneck:
        print(
            f"    [{r.get('averageSessionDuration', 0):.1f}s | "
            f"eng {r.get('engagementRate', 0):.2f}]  "
            f"{r.get('pageTitle', r.get('pagePath', ''))[:60]}"
        )
    save_bottleneck(bottleneck)

    print("\nDone.")


if __name__ == "__main__":
    main()
