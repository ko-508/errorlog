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
CTR_IMP_THRESHOLD = int(os.getenv("CTR_IMP_THRESHOLD",  "10"))    # CTR 判定の最低インプレッション数
CTR_THRESHOLD     = float(os.getenv("CTR_THRESHOLD",    "0.015")) # CTR 1.5% 未満 → ボトルネック
POS_IMP_THRESHOLD = int(os.getenv("POS_IMP_THRESHOLD",  "5"))     # 順位判定の最低インプレッション数
POS_MIN           = float(os.getenv("POS_MIN",           "11.0")) # 停滞圏 上限（11位〜）
POS_MAX           = float(os.getenv("POS_MAX",           "20.0")) # 停滞圏 下限（〜20位）
ROW_LIMIT         = 1000

# ── Phase 2: CTR最適化ループ 最優先条件 ────────────────────────────────────────
# impressions > 100 かつ ctr < 0.01 → ultra_priority（最優先リライト対象）
CTR_ULTRA_IMP_MIN = int(os.getenv("CTR_ULTRA_IMP_MIN",   "100"))  # 最優先判定の最低インプレッション数
CTR_ULTRA_MAX     = float(os.getenv("CTR_ULTRA_MAX",      "0.01")) # 最優先判定の最大CTR

GSC_REPORT_FILE      = REPORTS_DIR / f"gsc_{TODAY.strftime('%Y%m%d')}.json"
PRIORITY_FILE        = SCRIPTS_DIR / "rewrite_priority.json"
PRIORITY_REPORT_FILE = SCRIPTS_DIR / "rewrite_priority_report.json"

# ── Phase 2改善: 表示回数下限（リライト効果が小さい記事を除外） ──────────────
MIN_IMPRESSIONS_FOR_REWRITE = int(os.getenv("MIN_IMPRESSIONS_FOR_REWRITE", "50"))


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


def fetch_top_queries(service, rows: list[dict] | None = None) -> dict[str, str]:
    """ページごとの最多インプレッションクエリを返す {page_url: top_query}。"""
    if rows is None:
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


def _ctr_priority_score(impressions: int, ctr: float, position: float = 0.0) -> float:
    """Phase 5 + 改善: CTR最適化スコア。
    impressions < MIN_IMPRESSIONS_FOR_REWRITE の場合は 0 を返す（改善効果が小さいため）。
    priority_score = (impressions * 0.6) + ((1 - ctr) * 100 * 0.3) + (position * 0.1)
    """
    if impressions < MIN_IMPRESSIONS_FOR_REWRITE:
        return 0.0
    return round(impressions * 0.6 + (1.0 - ctr) * 100 * 0.3 + position * 0.1, 2)


def identify_bottlenecks(
    page_rows: list[dict],
    top_queries: dict[str, str],
) -> list[dict]:
    """ボトルネック記事を判定してスコア付きリストで返す。

    優先条件（Phase 2）:
      ultra_priority: impressions > CTR_ULTRA_IMP_MIN かつ ctr < CTR_ULTRA_MAX → 最優先
    通常条件:
      低CTR: impressions >= CTR_IMP_THRESHOLD かつ ctr < effective_ctr_threshold
      位置停滞: position 11〜20 かつ impressions >= POS_IMP_THRESHOLD
    """
    results = []
    total_ctr_avg = (
        sum(r["ctr"] for r in page_rows) / len(page_rows) if page_rows else 0.0
    )
    effective_ctr_threshold = min(CTR_THRESHOLD, total_ctr_avg * 0.7)

    for r in page_rows:
        page        = r["page"]
        impressions = int(r["impressions"])
        clicks      = int(r["clicks"])
        ctr         = r["ctr"]
        position    = r["position"]
        top_query   = top_queries.get(page, "")

        reasons       = []
        ultra_priority = False

        # 最優先判定: impressions > 100 かつ ctr < 0.01
        if impressions > CTR_ULTRA_IMP_MIN and ctr < CTR_ULTRA_MAX:
            ultra_priority = True
            reasons.append(
                f"[最優先] CTR {ctr:.1%} < {CTR_ULTRA_MAX:.0%}"
                f"（インプレッション {impressions} > {CTR_ULTRA_IMP_MIN}）"
            )
        else:
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

        priority_score = _ctr_priority_score(impressions, ctr, position)

        results.append({
            "page":              page,
            "slug":              slug,
            "impressions":       impressions,
            "clicks":            clicks,
            "ctr":               round(ctr, 4),
            "position":          round(position, 1),
            "top_query":         top_query,
            "reasons":           reasons,
            "ultra_priority":    ultra_priority,
            "priority_score":    priority_score,
            "rewrite_eligible":  impressions >= MIN_IMPRESSIONS_FOR_REWRITE,
        })

    # ultra_priority を最前に、次にスコア降順でソート
    results.sort(key=lambda x: (-int(x["ultra_priority"]), -x["priority_score"]))
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
    """rewrite_priority.json に top_query・CTRスコアを追記・更新する（Phase 2）。

    ultra_priority 記事は priority_score = _ctr_priority_score(imp, ctr) で計算し、
    既存エントリを上書き更新する。最終的にスコア降順で保存する。
    """
    existing: list[dict] = []
    if PRIORITY_FILE.exists():
        try:
            existing = json.loads(PRIORITY_FILE.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    existing_by_title: dict[str, dict] = {e["title"]: e for e in existing}
    added = updated = 0

    for b in bottlenecks:
        if not b["slug"]:
            continue

        title = _article_title_from_slug(b["slug"])
        if not title:
            continue

        ctr_score = b.get("priority_score", 0.5)
        is_ultra  = b.get("ultra_priority", False)

        entry = existing_by_title.get(title)
        if entry:
            if b["top_query"]:
                entry["top_query"]    = b["top_query"]
            entry["gsc_position"]    = b["position"]
            entry["gsc_ctr"]         = b["ctr"]
            entry["gsc_impressions"] = b["impressions"]
            entry["gsc_reasons"]     = b["reasons"]
            # ultra_priority 記事のスコアを上書き（CTRスコアが高ければ更新）
            if is_ultra or ctr_score > entry.get("priority_score", 0):
                entry["priority_score"] = ctr_score
                entry["critical"]       = is_ultra
            # Phase 4: slug と rewrite_eligible を追記・更新
            entry["rewrite_eligible"] = b.get("rewrite_eligible", True)
            if b.get("slug") and not entry.get("slug"):
                entry["slug"] = b["slug"]
            updated += 1
        else:
            new_entry = {
                "title":             title,
                "slug":              b.get("slug", ""),
                "priority_score":    ctr_score,
                "critical":          is_ultra,
                "rewrite_eligible":  b.get("rewrite_eligible", True),
                "no_ratio":          0.0,
                "no_count":          0,
                "engagement_sec":    0.0,
                "top_query":         b.get("top_query", ""),
                "gsc_position":      b["position"],
                "gsc_ctr":           b["ctr"],
                "gsc_impressions":   b["impressions"],
                "gsc_reasons":       b["reasons"],
                "queued_at":         TODAY.isoformat(),
                "source":            "gsc_bottleneck",
            }
            existing.append(new_entry)
            existing_by_title[title] = new_entry
            added += 1

    # critical（ultra_priority）を先頭に、次にスコア降順でソート
    existing.sort(key=lambda x: (-int(x.get("critical", False)), -x.get("priority_score", 0)))

    PRIORITY_FILE.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ultra_count = sum(1 for b in bottlenecks if b.get("ultra_priority"))
    print(
        f"  rewrite_priority.json: +{added} added, {updated} updated "
        f"({ultra_count} ultra_priority), sorted by priority_score"
    )


# ── Phase 5: リライト優先順位監査ログ ────────────────────────────────────────

def _save_rewrite_priority_report(bottlenecks: list[dict]) -> None:
    """scripts/rewrite_priority_report.json を生成する。

    なぜ記事が選定された（または除外された）かを後から説明可能にする（監査ログ）。
    """
    eligible = [b for b in bottlenecks if b.get("rewrite_eligible", True)]
    excluded = [b for b in bottlenecks if not b.get("rewrite_eligible", True)]

    top_candidates = []
    for b in eligible[:20]:
        title = _article_title_from_slug(b["slug"]) if b["slug"] else ""
        top_candidates.append({
            "slug":           b["slug"],
            "title":          title,
            "priority_score": b["priority_score"],
            "impressions":    b["impressions"],
            "ctr":            b["ctr"],
            "position":       b["position"],
            "rewrite_eligible": True,
        })

    output = {
        "generated_at":              TODAY.isoformat(),
        "eligible_count":            len(eligible),
        "excluded_low_impressions":  len(excluded),
        "min_impressions_threshold": MIN_IMPRESSIONS_FOR_REWRITE,
        "top_candidates":            top_candidates,
    }
    PRIORITY_REPORT_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"  rewrite_priority_report.json: eligible={len(eligible)}, "
        f"excluded={len(excluded)} (imp<{MIN_IMPRESSIONS_FOR_REWRITE})"
    )


# ── Phase 2: クエリ集約 ───────────────────────────────────────────────────────

def _build_query_aggregates(rows: list[dict]) -> dict[str, list[dict]]:
    """query+page rows からページ別上位10クエリを集約する（API 呼び出しなし）。

    Returns:
        {page_url: [{query, impressions, clicks, ctr, position}, ...]} (impressions降順, max10)
    """
    page_queries: dict[str, list[dict]] = {}
    for r in rows:
        page = r.get("page", "")
        if "/posts/" not in page:
            continue
        page_queries.setdefault(page, []).append({
            "query":       r.get("query", ""),
            "impressions": int(r.get("impressions", 0)),
            "clicks":      int(r.get("clicks", 0)),
            "ctr":         round(float(r.get("ctr", 0.0)), 4),
            "position":    round(float(r.get("position", 0.0)), 1),
        })
    for page in page_queries:
        page_queries[page].sort(key=lambda x: -x["impressions"])
        page_queries[page] = page_queries[page][:10]
    return page_queries


# ── Phase 4: data/search_queries.json 生成 ────────────────────────────────────

def save_search_queries(query_aggregates: dict[str, list[dict]]) -> None:
    """Hugo から site.Data.search_queries で参照可能な data/search_queries.json を生成する。

    構造:
        { slug: { top_queries: [...], avg_ctr: float, avg_position: float } }
    avg_ctr / avg_position は impressions 加重平均。
    """
    DATA_DIR = BASE / "data"
    DATA_DIR.mkdir(exist_ok=True)

    output: dict[str, dict] = {}
    for page, queries in query_aggregates.items():
        if not queries:
            continue
        slug_m = re.search(r"/posts/([^/]+)/?$", page)
        if not slug_m:
            continue
        slug = slug_m.group(1)

        total_imp = sum(q["impressions"] for q in queries) or 1
        avg_ctr = sum(q["ctr"] * q["impressions"] for q in queries) / total_imp
        avg_pos = sum(q["position"] * q["impressions"] for q in queries) / total_imp

        output[slug] = {
            "top_queries":  [q["query"] for q in queries[:10]],
            "avg_ctr":      round(avg_ctr, 4),
            "avg_position": round(avg_pos, 1),
        }

    out_file = DATA_DIR / "search_queries.json"
    out_file.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  data/search_queries.json: {len(output)} slugs -> {out_file.relative_to(BASE)}")


# ── Phase 3: Front Matter top_queries 反映 ────────────────────────────────────

def _remove_top_queries_block(fm_text: str) -> str:
    """Front Matter テキストから既存の top_queries ブロックを除去する。"""
    # block形式: top_queries:\n- "..."\n...
    fm_text = re.sub(
        r'^top_queries:\n(?:[ \t]*-[ \t]+[^\n]*\n?)+',
        '',
        fm_text,
        flags=re.MULTILINE,
    )
    # inline形式: top_queries: [...]
    fm_text = re.sub(
        r'^top_queries:[ \t]*\[.*?\]\n?',
        '',
        fm_text,
        flags=re.MULTILINE,
    )
    return fm_text


def update_top_queries_frontmatter(query_aggregates: dict[str, list[dict]]) -> None:
    """各記事の Front Matter に top_queries（impressions 順上位3件）を追記・更新する。

    条件:
      - データがないページはスキップ（追加しない）
      - 既存の top_queries は上書き更新
      - 本文・他の FM フィールドは変更しない
    """
    updated = skipped = 0

    for page, queries in query_aggregates.items():
        if not queries:
            continue
        slug_m = re.search(r"/posts/([^/]+)/?$", page)
        if not slug_m:
            continue
        slug = slug_m.group(1)

        md = POSTS_DIR / f"{slug}.md"
        if not md.exists():
            skipped += 1
            continue

        top3 = [q["query"] for q in queries[:3]]
        text = md.read_text(encoding="utf-8")

        fm_match = re.match(r'^(---\n)(.*?)(\n---\n)', text, re.DOTALL)
        if not fm_match:
            skipped += 1
            continue

        fm_text = fm_match.group(2)
        fm_clean = _remove_top_queries_block(fm_text).rstrip('\n')
        new_block = "top_queries:\n" + "\n".join(f'- "{q}"' for q in top3)
        new_fm_text = fm_clean + '\n' + new_block

        if new_fm_text == fm_text:
            skipped += 1
            continue

        new_text = (
            fm_match.group(1)
            + new_fm_text
            + fm_match.group(3)
            + text[fm_match.end():]
        )
        md.write_text(new_text, encoding="utf-8")
        updated += 1

    print(f"  top_queries FM: {updated} updated, {skipped} skipped")


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

    # 診断: アクセス可能なプロパティ一覧
    try:
        sites_resp = service.sites().list().execute()
        site_entries = sites_resp.get("siteEntry", [])
        print(f"  accessible sites: {len(site_entries)}")
        for s in site_entries:
            print(f"    {s.get('permissionLevel','?'):12s}  {s.get('siteUrl','')}")
    except Exception as e:
        print(f"  [WARN] sites().list() failed: {e}")

    print("  [1/4] Fetching page metrics...")
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

    print("  [2/4] Fetching query data per page...")
    _qp_rows = _query(service, ["query", "page"])
    top_queries = fetch_top_queries(service, rows=_qp_rows)
    print(f"  top queries resolved: {len(top_queries)} pages")
    query_aggregates = _build_query_aggregates(_qp_rows)
    print(
        f"  query aggregates: {len(query_aggregates)} pages, "
        f"{sum(len(v) for v in query_aggregates.values())} total query-page pairs"
    )

    print("  [3/4] Identifying bottlenecks...")
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
    _save_rewrite_priority_report(bottlenecks)

    print("  [4/4] Saving query learning data...")
    save_search_queries(query_aggregates)
    update_top_queries_frontmatter(query_aggregates)
    print("\nDone.")


if __name__ == "__main__":
    main()
