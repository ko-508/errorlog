"""
CTR実験トラッキング: rewrite_report.json の after 指標を更新し
data/rewrite_experiments.json を生成する。

実行タイミング: リライトから MEASUREMENT_DAYS 日後（既定 14 日）に
weekly_ga4.yml から呼び出す。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

# ─── fetch_search_console の共通ユーティリティを再利用 ────────────
sys.path.insert(0, str(Path(__file__).parent))
from fetch_search_console import _build_service, _query, SITE_URL  # noqa: E402

# ─── パス ──────────────────────────────────────────────────────────
BASE                  = Path(__file__).parent.parent
REWRITE_REPORT_FILE   = Path(__file__).parent / "rewrite_report.json"
REWRITE_EXPERIMENTS   = BASE / "data" / "rewrite_experiments.json"

# ─── 設定 ──────────────────────────────────────────────────────────
MEASUREMENT_DAYS = int(os.getenv("MEASUREMENT_DAYS", "14"))
TODAY            = date.today()


# ─── GSC page 指標取得 ────────────────────────────────────────────

def _fetch_page_metrics(service) -> dict[str, dict]:
    """GSC から page 次元の指標を取得し {url: {ctr, position, impressions}} を返す。"""
    rows = _query(service, ["page"])
    result: dict[str, dict] = {}
    for row in rows:
        url    = row["page"].rstrip("/")
        result[url] = {
            "ctr":         row.get("ctr", 0.0),
            "position":    row.get("position", 0.0),
            "impressions": row.get("impressions", 0),
        }
    return result


def _slug_to_url(slug: str) -> str:
    """slug を GSC に登録されている URL 形式に変換する。"""
    base = SITE_URL.rstrip("/")
    return f"{base}/posts/{slug}/"


# ─── メイン処理 ───────────────────────────────────────────────────

def main() -> None:
    if not REWRITE_REPORT_FILE.exists():
        print("[SKIP] rewrite_report.json が存在しません。")
        return

    records: list[dict] = json.loads(
        REWRITE_REPORT_FILE.read_text(encoding="utf-8")
    )

    cutoff = (TODAY - timedelta(days=MEASUREMENT_DAYS)).isoformat()
    pending = [
        r for r in records
        if r.get("rewrite_date", "") <= cutoff
        and "after_ctr" not in r
    ]

    if not pending:
        print(f"[SKIP] after 指標未取得のエントリなし（測定期間 {MEASUREMENT_DAYS} 日未満）。")
        _write_experiments(records)
        return

    print(f"[INFO] after 指標更新対象: {len(pending)} 件 (cutoff={cutoff})")

    try:
        service = _build_service()
    except Exception as e:
        print(f"[ERROR] GSC 認証失敗: {e}", file=sys.stderr)
        sys.exit(1)

    page_metrics = _fetch_page_metrics(service)
    print(f"[INFO] GSC page データ取得: {len(page_metrics)} URL")

    updated = 0
    for record in records:
        if "after_ctr" in record:
            continue
        rewrite_date = record.get("rewrite_date", "")
        if rewrite_date > cutoff:
            continue

        slug = record.get("slug", "")
        url  = _slug_to_url(slug).rstrip("/")
        m    = page_metrics.get(url) or page_metrics.get(url + "/")
        if not m:
            print(f"  [MISS] {slug} — GSC にデータなし (URL={url})")
            continue

        record["after_ctr"]         = round(m["ctr"], 6)
        record["after_position"]    = round(m["position"], 2)
        record["after_impressions"] = m["impressions"]
        record["ctr_change"]        = round(
            m["ctr"] - record.get("before_ctr", 0.0), 6
        )
        record["position_change"]   = round(
            m["position"] - record.get("before_position", 0.0), 2
        )
        updated += 1

    REWRITE_REPORT_FILE.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[INFO] rewrite_report.json 更新: {updated} 件")

    _write_experiments(records)
    _print_rankings(records)


def _write_experiments(records: list[dict]) -> None:
    """data/rewrite_experiments.json を生成する（Hugo からアクセス可能）。"""
    completed = [r for r in records if "after_ctr" in r]
    REWRITE_EXPERIMENTS.parent.mkdir(parents=True, exist_ok=True)
    REWRITE_EXPERIMENTS.write_text(
        json.dumps(
            {
                "generated_at":     TODAY.isoformat(),
                "total_rewrites":   len(records),
                "measured_count":   len(completed),
                "experiments":      completed,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[INFO] data/rewrite_experiments.json: {len(completed)} 件")


def _print_rankings(records: list[dict]) -> None:
    """CTR 改善・悪化ランキングを出力する。"""
    completed = [r for r in records if "ctr_change" in r]
    if not completed:
        print("[INFO] ランキング出力対象なし。")
        return

    improved   = sorted(completed, key=lambda r: r["ctr_change"], reverse=True)[:20]
    degraded   = sorted(completed, key=lambda r: r["ctr_change"])[:20]

    print("\n=== CTR 改善 TOP20 ===")
    for i, r in enumerate(improved, 1):
        sign = "+" if r["ctr_change"] >= 0 else ""
        print(
            f"  {i:2}. [{r.get('slug','')}] {r.get('new_title','')[:40]}"
            f"  CTR {sign}{r['ctr_change']:.2%}"
            f"  ({r.get('before_ctr',0):.2%} → {r.get('after_ctr',0):.2%})"
        )

    print("\n=== CTR 悪化 TOP20 ===")
    for i, r in enumerate(degraded, 1):
        print(
            f"  {i:2}. [{r.get('slug','')}] {r.get('new_title','')[:40]}"
            f"  CTR {r['ctr_change']:.2%}"
            f"  ({r.get('before_ctr',0):.2%} → {r.get('after_ctr',0):.2%})"
        )


if __name__ == "__main__":
    main()
