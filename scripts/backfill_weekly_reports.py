"""
過去の週次レポートを現行の errorlog.jp ホストフィルタ条件で再生成する。

使い方:
  python scripts/backfill_weekly_reports.py --run-dates 2026-06-08,2026-06-14
  python scripts/backfill_weekly_reports.py --all-existing
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import weekly_report as weekly

BASE = weekly.BASE
REPORTS_DIR = weekly.REPORTS_DIR


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"invalid ISO date: {value}") from e


def _period_for_run_date(run_date: date) -> tuple[date, date]:
    return run_date - timedelta(days=9), run_date - timedelta(days=3)


def _previous_range(start: date, end: date) -> tuple[date, date]:
    days = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    return prev_end - timedelta(days=days - 1), prev_end


def _existing_run_dates() -> list[date]:
    dates = []
    for path in sorted(REPORTS_DIR.glob("weekly_report_*.json")):
        stamp = path.stem.replace("weekly_report_", "")
        try:
            dates.append(date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:8])))
        except ValueError:
            continue
    return dates


def _load_previous_weekly_reports_for(output_path: Path, limit: int = 8) -> list[dict]:
    reports = []
    for path in sorted(REPORTS_DIR.glob("weekly_report_*.json"), reverse=True):
        if path == output_path:
            continue
        try:
            reports.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"  [WARN] weekly report履歴読み込みエラー {path.name}: {e}")
        if len(reports) >= limit:
            break
    return reports


def _fetch_gsc_for_period(start: date, end: date, previous_start: date, previous_end: date) -> tuple[list[dict], dict, dict]:
    service = weekly._build_gsc_service()
    bottlenecks = weekly._fetch_gsc_bottlenecks(service, start, end)
    current_summary = weekly._fetch_gsc_site_summary(service, start, end)
    previous_summary = weekly._fetch_gsc_site_summary(service, previous_start, previous_end)
    return bottlenecks, current_summary, previous_summary


def build_weekly_report_for(run_date: date) -> dict:
    current_start, current_end = _period_for_run_date(run_date)
    previous_start, previous_end = _previous_range(current_start, current_end)
    period = f"{current_start.isoformat()} 〜 {current_end.isoformat()}"
    output_path = REPORTS_DIR / f"weekly_report_{run_date.strftime('%Y%m%d')}.json"

    print(f"=== Backfill weekly report {run_date.isoformat()} ({period}) ===")
    print("[1/3] Fetching GA4 data with hostName CONTAINS errorlog.jp...")
    weekly.GA4_QUERY_ERRORS.clear()
    ga4_client = weekly._build_ga4_client()
    raw_data = weekly.fetch_all_ga4(ga4_client, current_start, current_end)
    current_ga4_errors = list(weekly.GA4_QUERY_ERRORS)
    weekly.GA4_QUERY_ERRORS.clear()
    previous_raw_data = weekly.fetch_all_ga4(ga4_client, previous_start, previous_end)
    previous_ga4_errors = list(weekly.GA4_QUERY_ERRORS)
    if current_ga4_errors or previous_ga4_errors:
        raise RuntimeError(
            "GA4 query failed: "
            + " / ".join(current_ga4_errors + previous_ga4_errors)
        )

    metrics = weekly.compute_metrics(raw_data)
    previous_metrics = weekly.compute_metrics(previous_raw_data)

    print("[2/3] Fetching GSC data...")
    bottlenecks, gsc_summary, previous_gsc_summary = _fetch_gsc_for_period(
        current_start,
        current_end,
        previous_start,
        previous_end,
    )

    print("[3/3] Rendering report JSON...")
    host_summary = raw_data.get("host_summary", {})
    host_summary_section = weekly._build_host_summary_section(host_summary)
    country_section = weekly._build_country_section(raw_data.get("countries", []))
    article_progress = weekly.build_article_progress(current_start, current_end)
    rewrite_tracking = weekly.load_rewrite_tracking(today=run_date)
    index_status = weekly.load_index_status()
    previous_reports = _load_previous_weekly_reports_for(output_path)
    gsc_history = weekly._extract_gsc_history(period, gsc_summary, previous_reports)
    ga4_change = weekly.build_ga4_comparison(metrics, previous_metrics)
    gsc_change = weekly.build_gsc_comparison(gsc_summary, previous_gsc_summary)

    issue_body = weekly.render_issue_body(
        metrics,
        bottlenecks,
        period,
        gsc_summary=gsc_summary,
        previous_metrics=previous_metrics,
        previous_gsc_summary=previous_gsc_summary,
        gsc_history=gsc_history,
        article_progress=article_progress,
        rewrite_tracking=rewrite_tracking,
        index_status=index_status,
        noise_section="",
        country_section=country_section,
        indexnow_section="",
        content_gap_section="",
        host_summary_section=host_summary_section,
    )
    issue_title = f"【週次レポート】GA4 + GSC ボトルネック ({run_date.isoformat()})"

    return {
        "report_type": "weekly",
        "generated_at": run_date.isoformat(),
        "period": period,
        "period_detail": {
            "start": current_start.isoformat(),
            "end": current_end.isoformat(),
        },
        "previous_period": {
            "start": previous_start.isoformat(),
            "end": previous_end.isoformat(),
        },
        "host_filter": "hostName CONTAINS errorlog.jp",
        "issue_title": issue_title,
        "issue_body": issue_body,
        "bottlenecks_count": len(bottlenecks),
        "summary": {
            "judgement": weekly.judge_overall_summary(gsc_change, ga4_change),
            "anomalies": weekly.build_anomaly_alerts(gsc_change, ga4_change),
            "top_bottlenecks": [
                weekly._slug_from_url(b.get("page", ""))
                for b in weekly.sort_bottlenecks(bottlenecks)[:3]
            ],
        },
        "metrics_snapshot": {
            "active_users": metrics["active_users"],
            "sessions": metrics["sessions"],
            "organic_sessions": metrics["organic_sessions"],
            "direct_sessions": metrics["direct_sessions"],
            "organic_ratio": round(metrics["organic_ratio"], 4),
            "japan_ratio": round(metrics["japan_ratio"], 4),
            "pv_per_sess": round(metrics["pv_per_sess"], 3),
            "avg_engagement_time": round(metrics["avg_engagement_time"], 3),
            "bounce_rate": round(metrics["bounce_rate"], 4),
            "js_errors": metrics["js_errors"],
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
        "gsc_summary": gsc_summary,
        "ga4_host_summary": host_summary,
        "article_progress": article_progress,
        "rewrite_tracking": rewrite_tracking,
        "index_status": index_status,
    }


def write_report(run_date: date) -> Path:
    report = build_weekly_report_for(run_date)
    path = REPORTS_DIR / f"weekly_report_{run_date.strftime('%Y%m%d')}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {path.relative_to(BASE)}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dates", help="comma-separated run dates, e.g. 2026-06-08,2026-06-14")
    parser.add_argument("--all-existing", action="store_true", help="regenerate all existing weekly_report_*.json files")
    args = parser.parse_args()

    if not args.run_dates and not args.all_existing:
        parser.error("--run-dates or --all-existing is required")

    if not os.environ.get("GA4_PROPERTY_ID", "").strip():
        print("[ERROR] GA4_PROPERTY_ID is not set.", file=sys.stderr)
        sys.exit(1)

    if args.all_existing:
        run_dates = _existing_run_dates()
    else:
        run_dates = [_parse_date(v.strip()) for v in args.run_dates.split(",") if v.strip()]

    if not run_dates:
        print("[ERROR] no target reports found.", file=sys.stderr)
        sys.exit(1)

    for run_date in run_dates:
        write_report(run_date)


if __name__ == "__main__":
    main()
