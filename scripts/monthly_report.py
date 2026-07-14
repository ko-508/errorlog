"""
月次統合レポート生成スクリプト
前月1日〜前月末日の GA4 + GSC + 改善進捗を GitHub Issue 用 Markdown と JSON にまとめる。
"""

from __future__ import annotations

import calendar
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import weekly_report as weekly

BASE = weekly.BASE
REPORTS_DIR = weekly.REPORTS_DIR
TODAY = date.today()
CONFIG_PATH = BASE / "data" / "report_config.json"
METRIC_KEYS = {
    "active_users": None,
    "sessions": None,
    "organic_sessions": None,
    "direct_sessions": None,
    "organic_ratio": None,
    "japan_ratio": None,
    "pv_per_sess": None,
    "avg_engagement_time": None,
    "bounce_rate": None,
    "js_errors": None,
    "channel_str": "データなし",
}


def load_report_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"  [WARN] report_config.json 読み込みエラー: {e}")
        return {}


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _is_full_month(start: date, end: date, measurement_start: date | None) -> bool:
    if measurement_start is None:
        return True
    return measurement_start <= start


def build_comparison_context(previous_start: date, previous_end: date, config: dict | None = None) -> dict:
    config = config or {}
    starts = [
        _parse_date(config.get("site_launch_date")),
        _parse_date(config.get("ga4_measurement_start_date")),
        _parse_date(config.get("gsc_measurement_start_date")),
    ]
    effective_start = max([d for d in starts if d is not None], default=None)
    is_complete = _is_full_month(previous_start, previous_end, effective_start)
    return {
        "previous_month_complete": is_complete,
        "reference_only": not is_complete,
        "measurement_start_date": effective_start.isoformat() if effective_start else None,
        "note": "" if is_complete else "前月は計測開始後の一部期間のみのため、前月比は参考値です。",
    }


def _status_metrics(status: str, reason: str) -> dict:
    metrics = dict(METRIC_KEYS)
    metrics["status"] = status
    metrics["reason"] = reason
    return metrics


def _is_empty_ga4_raw(raw: dict) -> bool:
    overall = raw.get("overall") or {}
    hosts = raw.get("host_summary", {}).get("hosts", [])
    channels = raw.get("channels") or []
    countries = raw.get("countries") or []
    if not overall and not hosts and not channels and not countries:
        return True
    if overall and not hosts and not channels and not countries:
        return all(float(v or 0) == 0.0 for v in overall.values())
    return False


def _raw_has_errorlog_host(raw: dict) -> bool:
    return any("errorlog.jp" in h.get("host", "") for h in raw.get("host_summary", {}).get("hosts", []))


def compute_monthly_metrics(raw: dict, start: date, config: dict | None = None, query_errors: list[str] | None = None) -> dict:
    config = config or {}
    query_errors = query_errors or []
    measurement_start = _parse_date(config.get("ga4_measurement_start_date") or config.get("site_launch_date"))
    if measurement_start and start < measurement_start.replace(day=1) and start < measurement_start:
        return _status_metrics("no_data", "measurement_not_started")
    if query_errors:
        return _status_metrics("error", "; ".join(query_errors))
    if _is_empty_ga4_raw(raw):
        return _status_metrics("no_data", "empty_response")
    if raw.get("host_summary", {}).get("hosts") and not _raw_has_errorlog_host(raw):
        return _status_metrics("no_data", "hostname_mismatch")
    metrics = weekly.compute_metrics(raw)
    metrics["status"] = "ok"
    metrics["reason"] = ""
    return metrics


def _display_value(value, kind: str = "number") -> str:
    if value is None:
        return "データなし"
    if kind == "rate":
        return weekly._fmt_rate(value)
    if kind == "float":
        return weekly._fmt_float(value)
    if kind == "seconds":
        return f"{float(value):.1f}秒"
    if kind == "decimal2":
        return f"{float(value):.2f}"
    return weekly._fmt_int(value)


def _format_monthly_change(change: dict, comparison_context: dict | None = None) -> str:
    if not change.get("current_exists", True):
        return "算出不可"
    if not change.get("previous_exists", True):
        return "算出不可"
    text = weekly._format_change(change)
    if comparison_context and comparison_context.get("reference_only") and text not in ("データなし", "算出不可"):
        return f"{text}（参考）"
    return text


def build_monthly_ga4_comparison(current: dict, previous: dict | None) -> dict:
    ga4 = {}
    for key, kind in {
        "active_users": "number",
        "sessions": "number",
        "organic_sessions": "number",
        "direct_sessions": "number",
        "japan_ratio": "ratio",
        "pv_per_sess": "number",
        "avg_engagement_time": "number",
        "bounce_rate": "rate",
    }.items():
        ga4[key] = weekly.build_change(current.get(key), previous.get(key) if previous else None, kind=kind)
    return ga4


def build_monthly_gsc_comparison(current: dict, previous: dict | None) -> dict:
    changes = {}
    for key, kind in {"impressions": "number", "clicks": "number", "ctr": "rate", "position": "position"}.items():
        changes[key] = weekly.build_change(current.get(key), previous.get(key) if previous else None, kind=kind)
    return changes


def month_period_for_run(run_date: date = TODAY) -> tuple[date, date]:
    first_this_month = run_date.replace(day=1)
    end = first_this_month - timedelta(days=1)
    start = end.replace(day=1)
    return start, end


def previous_month_period(start: date) -> tuple[date, date]:
    previous_end = start - timedelta(days=1)
    return previous_end.replace(day=1), previous_end


def month_key(start: date) -> str:
    return start.strftime("%Y-%m")


def month_label(start: date) -> str:
    return f"{start.year}年{start.month}月"


def monthly_report_path(start: date) -> Path:
    return REPORTS_DIR / f"monthly_report_{start.strftime('%Y%m')}.json"


def fetch_monthly_gsc(start: date, end: date, previous_start: date, previous_end: date) -> tuple[list[dict], dict, dict, list[dict]]:
    try:
        service = weekly._build_gsc_service()
    except Exception as e:
        print(f"  [WARN] GSC auth failed: {e}")
        return [], {}, {}, []

    current_bottlenecks = weekly._fetch_gsc_bottlenecks(service, start, end)
    previous_bottlenecks = weekly._fetch_gsc_bottlenecks(service, previous_start, previous_end)
    previous_pages = {b.get("page") for b in previous_bottlenecks}

    for item in current_bottlenecks:
        item["status"] = "継続" if item.get("page") in previous_pages else "新規"

    current_summary = weekly._fetch_gsc_site_summary(service, start, end)
    previous_summary = weekly._fetch_gsc_site_summary(service, previous_start, previous_end)
    return current_bottlenecks, current_summary, previous_summary, previous_bottlenecks


def build_monthly_anomaly_alerts(
    gsc_change: dict,
    ga4_change: dict,
    current_metrics: dict,
    host_summary: dict,
    comparison_context: dict | None = None,
) -> list[str]:
    alerts = []
    use_comparison = not (comparison_context or {}).get("reference_only")
    if use_comparison:
        imp_pct = gsc_change.get("impressions", {}).get("pct_change")
        if imp_pct is not None and imp_pct <= -0.50:
            alerts.append(f"🚨 表示回数が前月比{abs(imp_pct) * 100:.1f}%減少しました。")

        click_pct = gsc_change.get("clicks", {}).get("pct_change")
        if click_pct is not None and click_pct <= -0.50:
            alerts.append(f"🚨 クリック数が前月比{abs(click_pct) * 100:.1f}%減少しました。")

        pos = gsc_change.get("position", {})
        if pos.get("previous_exists", True) and float(pos.get("delta", 0.0)) >= 10.0:
            alerts.append(
                f"🚨 平均掲載順位が{weekly._fmt_float(pos.get('previous'))}から"
                f"{weekly._fmt_float(pos.get('current'))}へ悪化しました。"
            )

        organic_pct = ga4_change.get("organic_sessions", {}).get("pct_change")
        if organic_pct is not None and organic_pct <= -0.50:
            alerts.append("🚨 Organic Searchセッションが大幅減少しました。")

        sessions_pct = ga4_change.get("sessions", {}).get("pct_change")
        if sessions_pct is not None and sessions_pct <= -0.50:
            alerts.append("🚨 errorlog.jpのセッションが前月比50%以上減少しました。")

    zenn_share = sum(
        float(h.get("pv_share", 0.0))
        for h in host_summary.get("hosts", [])
        if "zenn.dev" in h.get("host", "")
    )
    if zenn_share >= 0.90:
        alerts.append(f"⚠️ zenn.devがGA4全体の{zenn_share:.1%}を占めています。")

    if float(current_metrics.get("japan_ratio", 0.0)) < 0.30:
        alerts.append("⚠️ 日本国内率が30%未満です。")

    return alerts


def build_monthly_judgement(
    gsc_change: dict,
    ga4_change: dict,
    rewrite_tracking: list[dict],
    comparison_context: dict | None = None,
) -> str:
    if (comparison_context or {}).get("reference_only"):
        return "前月は不完全月のため、前月比による傾向判定は行っていません。"

    improved = sum(1 for r in rewrite_tracking if r.get("verdict") == "改善")
    worsened = sum(1 for r in rewrite_tracking if r.get("verdict") == "悪化")
    imp_pct = gsc_change.get("impressions", {}).get("pct_change")
    click_pct = gsc_change.get("clicks", {}).get("pct_change")
    ctr_delta = gsc_change.get("ctr", {}).get("delta", 0)
    pos_delta = gsc_change.get("position", {}).get("delta", 0)
    organic_pct = ga4_change.get("organic_sessions", {}).get("pct_change")

    imp_up = imp_pct is not None and imp_pct >= 0.20
    imp_down = imp_pct is not None and imp_pct <= -0.20
    click_up = click_pct is not None and click_pct >= 0.20
    click_down = click_pct is not None and click_pct <= -0.20
    pos_better = pos_delta <= -3.0
    pos_worse = pos_delta >= 3.0
    organic_up = organic_pct is not None and organic_pct >= 0.20
    organic_down = organic_pct is not None and organic_pct <= -0.20

    if imp_down and ctr_delta > 0:
        return "検索流入は減少しましたが、CTRは改善しています。"
    if (imp_up or click_up or organic_up) and pos_worse:
        return "流入は増えましたが、平均順位は悪化しています。"
    if click_up and organic_down:
        return "クリックは増えましたが、Organic Searchセッションは減少しています。"

    improve_count = sum([imp_up, click_up, pos_better, organic_up])
    worsen_count = sum([imp_down, click_down, pos_worse, organic_down])
    if improve_count and not worsen_count:
        return "検索表示回数・クリック・順位・Organic Searchのいずれかに改善傾向があります。"
    if worsen_count and not improve_count:
        return "検索表示回数・クリック・順位・Organic Searchのいずれかに悪化傾向があります。"
    if improve_count and worsen_count:
        return "改善指標と悪化指標が混在しています。優先記事を確認してください。"
    if improved > worsened and improved > 0:
        return "既存記事の修正後、検索表示回数に改善傾向が見られます。"
    return "前月から大きな変化はありません。"


def _load_rewrite_source_records() -> list[dict]:
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
            records.append(item)
    return records


def _parse_record_date(record: dict) -> date | None:
    raw = record.get("rewrite_date") or record.get("timestamp") or record.get("date")
    try:
        return datetime.fromisoformat(str(raw)).date()
    except Exception:
        return None


def _normalize_post_path(path: str | None) -> str:
    if not path:
        return ""
    return path.replace("\\", "/").strip()


def _is_post_path(path: str | None) -> bool:
    p = _normalize_post_path(path)
    return p.startswith("content/posts/") and p.endswith(".md")


def aggregate_article_events(events: list[dict], history_complete: bool = True) -> dict:
    new_articles: set[str] = set()
    modified_articles: set[str] = set()
    unpublished_articles: set[str] = set()
    renamed_to: set[str] = set()
    renamed_from: set[str] = set()

    for event in events:
        status = event.get("status", "")
        path = _normalize_post_path(event.get("path"))
        old_path = _normalize_post_path(event.get("old_path"))
        new_path = _normalize_post_path(event.get("new_path") or path)
        old_draft = event.get("old_draft")
        new_draft = event.get("new_draft")

        if status.startswith("R") and (_is_post_path(old_path) or _is_post_path(new_path)):
            if _is_post_path(old_path):
                renamed_from.add(old_path)
            if _is_post_path(new_path):
                renamed_to.add(new_path)
                modified_articles.add(new_path)
            continue

        if not _is_post_path(path):
            continue

        if old_draft is True and new_draft is False:
            new_articles.add(path)
            continue
        if old_draft is False and new_draft is True:
            unpublished_articles.add(path)
            continue

        if status.startswith("A"):
            new_articles.add(path)
        elif status.startswith("D"):
            unpublished_articles.add(path)
        elif status.startswith("M"):
            modified_articles.add(path)

    modified_articles -= new_articles
    unpublished_articles -= new_articles
    return {
        "modified": len(modified_articles),
        "added": len(new_articles),
        "unpublished": len(unpublished_articles),
        "modified_articles": sorted(modified_articles),
        "new_articles": sorted(new_articles),
        "unpublished_articles": sorted(unpublished_articles),
        "renamed_from": sorted(renamed_from),
        "renamed_to": sorted(renamed_to),
        "source": "git_history",
        "history_complete": history_complete,
    }


def _git_history_complete() -> bool:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--is-shallow-repository"],
            cwd=BASE,
            text=True,
            capture_output=True,
            check=False,
        )
    except Exception:
        return False
    return proc.stdout.strip().lower() != "true"


def _git_post_events(start: date, end: date) -> list[dict]:
    try:
        proc = subprocess.run(
            [
                "git", "log",
                "--find-renames",
                "--date=iso-strict",
                f"--since={start.isoformat()}T00:00:00+09:00",
                f"--until={end.isoformat()}T23:59:59+09:00",
                "--name-status",
                "--pretty=format:commit %H %cI",
                "--", "content/posts",
            ],
            cwd=BASE,
            text=True,
            capture_output=True,
            check=False,
        )
    except Exception as e:
        print(f"  [WARN] git log 実行エラー: {e}")
        return []

    events = []
    current_commit = ""
    current_date = ""
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("commit "):
            parts = line.split()
            current_commit = parts[1] if len(parts) > 1 else ""
            current_date = parts[2] if len(parts) > 2 else ""
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("R") and len(parts) >= 3:
            events.append({
                "status": status,
                "old_path": parts[1],
                "new_path": parts[2],
                "commit": current_commit,
                "commit_date": current_date,
            })
        elif len(parts) >= 2:
            events.append({
                "status": status,
                "path": parts[-1],
                "commit": current_commit,
                "commit_date": current_date,
            })
    return events


def load_monthly_rewrite_tracking(start: date, end: date, today: date = TODAY) -> list[dict]:
    cutoff = start - timedelta(days=92)
    rows = []
    for raw in _load_rewrite_source_records():
        rewrite_date = _parse_record_date(raw)
        evaluated = weekly.evaluate_rewrite_record(raw, today=today)
        verdict = evaluated.get("verdict")
        include = False
        if rewrite_date is not None:
            include = start <= rewrite_date <= end or cutoff <= rewrite_date <= end
        if verdict in ("悪化", "改善"):
            include = True
        if include:
            rows.append(evaluated)

    order = {"悪化": 0, "改善": 1, "変化なし": 2, "判定保留": 3}
    rows.sort(key=lambda r: (order.get(r.get("verdict"), 9), -(r.get("elapsed_days") or -1)))
    return rows[:20]


def rewrite_verdict_counts(records: list[dict]) -> dict:
    counts = Counter(r.get("verdict", "判定保留") for r in records)
    return {key: counts.get(key, 0) for key in ("改善", "変化なし", "悪化", "判定保留")}


def _rewrite_verdict_label(record: dict) -> str:
    verdict = record.get("verdict", "判定保留")
    reason = record.get("reason", "")
    if verdict == "判定保留" and reason:
        return f"判定保留（{reason}）"
    return verdict


def build_monthly_article_progress(start: date, end: date, previous_start: date, previous_end: date) -> dict:
    history_complete = _git_history_complete()
    current = aggregate_article_events(_git_post_events(start, end), history_complete=history_complete)
    previous = aggregate_article_events(_git_post_events(previous_start, previous_end), history_complete=history_complete)
    posts = weekly._published_posts()
    status = weekly._load_review_status()

    verified = 0
    for post in posts:
        rel = post.relative_to(BASE).as_posix()
        alt = f"posts/{post.name}"
        if status.get(rel, {}).get("verified") is True or status.get(alt, {}).get("verified") is True:
            verified += 1

    days = (end - start).days + 1
    total = len(posts)
    return {
        "published_count": total,
        "verified_count": verified,
        "unverified_count": max(total - verified, 0),
        "verification_rate": (verified / total) if total else 0.0,
        "current": current,
        "previous": previous,
        "daily_modified_avg": current["modified"] / days,
        "daily_new_avg": current["added"] / days,
        "review_status_source": "data/article_review_status.json" if status else "未設定",
        "source": "git_history_jst",
        "history_complete": history_complete,
    }


def _load_monthly_content_gap(limit: int = 20) -> tuple[str, dict]:
    gap_file = BASE / "data" / "content_gap.json"
    if not gap_file.exists():
        return "", {}
    try:
        gap = json.loads(gap_file.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [WARN] content_gap.json 読み込みエラー: {e}")
        return "", {}

    summary = gap.get("summary", {})
    total = summary.get("total_queries", 0)
    if not total:
        return "", summary

    top_items = weekly._filter_content_gap_items(
        sorted(
            gap.get("uncovered", []) + gap.get("partial", []),
            key=lambda x: -x.get("opportunity_score", 0),
        )
    )[:limit]

    lines = [
        "",
        "---",
        "",
        "## Content Gap Report",
        "",
        f"Coverage Rate: **{summary.get('coverage_rate', 0.0):.1%}**",
        "",
        "| 分類 | 件数 |",
        "| :--- | ---: |",
        f"| Covered | {summary.get('covered', 0)} |",
        f"| Partial | {summary.get('partial', 0)} |",
        f"| Uncovered | {summary.get('uncovered', 0)} |",
        f"| **合計** | **{total}** |",
        "",
    ]
    if top_items:
        lines.extend(["### Top Opportunities", ""])
        for i, item in enumerate(top_items, 1):
            cov_icon = "🔴" if item.get("coverage") == "uncovered" else "⚠️"
            lines.append(
                f"{i}. {cov_icon} `{item.get('query', '')}` "
                f"— Score: {item.get('opportunity_score', 0):.1f}"
            )
        lines.append("")

    return "\n".join(lines), {"summary": summary, "top_opportunities": top_items}


def read_report_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_monthly_history(current_output: dict | None = None, limit: int = 6) -> list[dict]:
    rows = []
    if current_output:
        rows.append(_history_row_from_report(current_output))

    for path in sorted(REPORTS_DIR.glob("monthly_report_*.json"), reverse=True):
        data = read_report_json(path)
        if not data:
            continue
        row = _history_row_from_report(data)
        if current_output and row.get("month") == current_output.get("month"):
            continue
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows[:limit]


def _history_row_from_report(report: dict) -> dict:
    ga4 = report.get("ga4", {}).get("current") or report.get("metrics_snapshot") or {}
    gsc = report.get("gsc", {}).get("current") or report.get("gsc_summary") or {}
    progress = report.get("article_progress", {})
    current_progress = progress.get("current", progress)
    return {
        "month": report.get("month") or report.get("generated_at", "取得不可")[:7],
        "active_users": ga4.get("active_users", 0),
        "sessions": ga4.get("sessions", 0),
        "organic_sessions": ga4.get("organic_sessions", 0),
        "impressions": gsc.get("impressions", 0),
        "clicks": gsc.get("clicks", 0),
        "ctr": gsc.get("ctr", 0.0),
        "position": gsc.get("position", 0.0),
        "modified": current_progress.get("modified", current_progress.get("weekly_modified", 0)),
        "added": current_progress.get("added", current_progress.get("weekly_new", 0)),
    }


def _build_monthly_history_section(history: list[dict]) -> str:
    if not history:
        return "## 月次推移\n\n_月次履歴データがありません。_"
    rows = "\n".join(
        f"| {h.get('month', '')} | {weekly._fmt_int(h.get('active_users'))} | "
        f"{weekly._fmt_int(h.get('sessions'))} | {weekly._fmt_int(h.get('organic_sessions'))} | "
        f"{weekly._fmt_int(h.get('impressions'))} | {weekly._fmt_int(h.get('clicks'))} | "
        f"{weekly._fmt_rate(h.get('ctr'))} | {weekly._fmt_float(h.get('position'))} | "
        f"{weekly._fmt_int(h.get('modified'))} | {weekly._fmt_int(h.get('added'))} |"
        for h in history
    )
    return f"""## 月次推移

| 月 | GA4アクティブユーザー | GA4セッション | Organic Search | GSC表示回数 | クリック | CTR | 平均順位 | 修正記事数 | 新規記事数 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{rows}"""


def _build_monthly_anomaly_section(alerts: list[str]) -> str:
    if not alerts:
        return "## 異常検知\n\n大きな異常は検出されませんでした。"
    return "## 異常検知\n\n" + "\n".join(f"- {alert}" for alert in alerts)


def _build_monthly_overview_section(
    metrics: dict,
    ga4_change: dict,
    gsc_summary: dict,
    gsc_change: dict,
    article_progress: dict,
    bottlenecks: list[dict],
    judgement: str,
    comparison_context: dict | None = None,
) -> str:
    top = "、".join(weekly._slug_from_url(b.get("page", "")) for b in weekly.sort_bottlenecks(bottlenecks)[:3]) or "該当なし"
    current = article_progress.get("current", {})
    return f"""## 今月の総括

- GA4 Organic Searchセッション: {_display_value(metrics.get('organic_sessions'))}（前月比 {_format_monthly_change(ga4_change['organic_sessions'], comparison_context)}）
- GSC表示回数: {_display_value(gsc_summary.get('impressions'))}（前月比 {_format_monthly_change(gsc_change['impressions'], comparison_context)}）
- GSCクリック数: {_display_value(gsc_summary.get('clicks'))}（前月比 {_format_monthly_change(gsc_change['clicks'], comparison_context)}）
- 平均掲載順位: {_display_value(gsc_summary.get('position'), 'float')}（前月 {weekly._fmt_previous(gsc_change['position'], lambda v: _display_value(v, 'float'))}）
- 今月修正した記事数: {weekly._fmt_int(current.get('modified'))}
- 今月新規公開した記事数: {weekly._fmt_int(current.get('added'))}
- 今月非公開化した記事数: {weekly._fmt_int(current.get('unpublished'))}
- 最優先対応記事: {top}

{judgement}"""


def _build_ga4_monthly_section(metrics: dict, ga4_change: dict, comparison_context: dict | None = None) -> str:
    rows = [
        ("アクティブユーザー", _display_value(metrics.get("active_users")), weekly._fmt_previous(ga4_change["active_users"], _display_value), _format_monthly_change(ga4_change["active_users"], comparison_context)),
        ("セッション", _display_value(metrics.get("sessions")), weekly._fmt_previous(ga4_change["sessions"], _display_value), _format_monthly_change(ga4_change["sessions"], comparison_context)),
        ("Organic Searchセッション", _display_value(metrics.get("organic_sessions")), weekly._fmt_previous(ga4_change["organic_sessions"], _display_value), _format_monthly_change(ga4_change["organic_sessions"], comparison_context)),
        ("Directセッション", _display_value(metrics.get("direct_sessions")), weekly._fmt_previous(ga4_change["direct_sessions"], _display_value), _format_monthly_change(ga4_change["direct_sessions"], comparison_context)),
        ("日本国内率", _display_value(metrics.get("japan_ratio"), "rate"), weekly._fmt_previous(ga4_change["japan_ratio"], lambda v: _display_value(v, "rate")), _format_monthly_change(ga4_change["japan_ratio"], comparison_context)),
        ("1セッションあたりPV", _display_value(metrics.get("pv_per_sess"), "decimal2"), weekly._fmt_previous(ga4_change["pv_per_sess"], lambda v: _display_value(v, "decimal2")), _format_monthly_change(ga4_change["pv_per_sess"], comparison_context)),
        ("平均エンゲージ時間", _display_value(metrics.get("avg_engagement_time"), "seconds"), weekly._fmt_previous(ga4_change["avg_engagement_time"], lambda v: _display_value(v, "seconds")), _format_monthly_change(ga4_change["avg_engagement_time"], comparison_context)),
        ("離脱率", _display_value(metrics.get("bounce_rate"), "rate"), weekly._fmt_previous(ga4_change["bounce_rate"], lambda v: _display_value(v, "rate")), _format_monthly_change(ga4_change["bounce_rate"], comparison_context)),
    ]
    body = "\n".join(f"| {name} | {cur} | {prev} | {chg} |" for name, cur, prev, chg in rows)
    return f"""## GA4トラフィックサマリー

メイン指標は `hostname = errorlog.jp` のみで集計しています。

| 指標 | 今月 | 前月 | 前月比 |
| :--- | ---: | ---: | ---: |
{body}"""


def _build_gsc_monthly_section(gsc_summary: dict, gsc_change: dict, comparison_context: dict | None = None) -> str:
    if not gsc_summary:
        return "## Search Consoleサイト全体サマリー\n\n_GSCデータが取得できませんでした。_"
    rows = [
        ("総表示回数", _display_value(gsc_summary.get("impressions")), weekly._fmt_previous(gsc_change["impressions"], _display_value), _format_monthly_change(gsc_change["impressions"], comparison_context)),
        ("総クリック数", _display_value(gsc_summary.get("clicks")), weekly._fmt_previous(gsc_change["clicks"], _display_value), _format_monthly_change(gsc_change["clicks"], comparison_context)),
        ("平均CTR", _display_value(gsc_summary.get("ctr"), "rate"), weekly._fmt_previous(gsc_change["ctr"], lambda v: _display_value(v, "rate")), _format_monthly_change(gsc_change["ctr"], comparison_context)),
        ("平均掲載順位", _display_value(gsc_summary.get("position"), "float"), weekly._fmt_previous(gsc_change["position"], lambda v: _display_value(v, "float")), _format_monthly_change(gsc_change["position"], comparison_context)),
    ]
    body = "\n".join(f"| {name} | {cur} | {prev} | {chg} |" for name, cur, prev, chg in rows)
    return f"""## Search Consoleサイト全体サマリー

| 指標 | 今月 | 前月 | 前月比 |
| :--- | ---: | ---: | ---: |
{body}"""


def _build_monthly_bottleneck_section(bottlenecks: list[dict]) -> str:
    if not bottlenecks:
        return "## Search Consoleボトルネック記事\n\n_今月のボトルネック記事はありませんでした。_"
    rows = "\n".join(
        f"| {b.get('priority', 'C')} | {b.get('status', '新規')} | `{b.get('page', '')}` | "
        f"{weekly._fmt_int(b.get('impressions'))} | {weekly._fmt_int(b.get('clicks'))} | "
        f"{weekly._fmt_rate(b.get('ctr'))} | {weekly._fmt_float(b.get('position'))} | "
        f"{b.get('top_query') or '—'} | {b.get('priority_reason', '既存条件に該当')} |"
        for b in weekly.sort_bottlenecks(bottlenecks)[:30]
    )
    return f"""## Search Consoleボトルネック記事

| 優先度 | 状態 | URL | 表示回数 | クリック数 | CTR | 平均掲載順位 | 最多検索クエリ | 判定理由 |
| :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | :--- |
{rows}"""


def _build_monthly_rewrite_section(records: list[dict]) -> str:
    counts = rewrite_verdict_counts(records)
    count_rows = "\n".join(f"| {key} | {value} |" for key, value in counts.items())
    if not records:
        return f"""## 改善効果トラッカー

| 判定 | 件数 |
| :--- | ---: |
{count_rows}

_rewrite_report.json / rewrite_experiments.json に表示可能な修正履歴がありません。_"""

    rows = []
    for r in records[:20]:
        elapsed = "取得不可" if r.get("elapsed_days") is None else f"{r['elapsed_days']}日"
        rows.append(
            f"| `{r['url']}` | {r['rewrite_date']} | {elapsed} | "
            f"{_display_value(r.get('before_impressions'))} | "
            f"{_display_value(r.get('after_impressions'))} | "
            f"{_display_value(r.get('before_clicks'))} | "
            f"{_display_value(r.get('after_clicks'))} | "
            f"{_display_value(r.get('before_ctr'), 'rate')} | "
            f"{_display_value(r.get('after_ctr'), 'rate')} | "
            f"{_display_value(r.get('before_position'), 'float')} | "
            f"{_display_value(r.get('after_position'), 'float')} | "
            f"{_rewrite_verdict_label(r)} |"
        )
    return f"""## 改善効果トラッカー

| 判定 | 件数 |
| :--- | ---: |
{count_rows}

| URL | 修正日 | 修正後経過日数 | 修正前表示回数 | 修正後表示回数 | 修正前クリック数 | 修正後クリック数 | 修正前CTR | 修正後CTR | 修正前順位 | 修正後順位 | 判定 |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
{chr(10).join(rows)}"""


def _build_monthly_article_progress_section(progress: dict) -> str:
    current = progress.get("current", {})
    previous = progress.get("previous", {})
    return f"""## 記事品質改善の進捗

| 指標 | 今月 | 前月 |
| :--- | ---: | ---: |
| 修正記事数 | {weekly._fmt_int(current.get('modified'))} | {weekly._fmt_int(previous.get('modified'))} |
| 新規公開記事数 | {weekly._fmt_int(current.get('added'))} | {weekly._fmt_int(previous.get('added'))} |
| 非公開化記事数 | {weekly._fmt_int(current.get('unpublished'))} | {weekly._fmt_int(previous.get('unpublished'))} |
| 1日平均修正数 | {progress.get('daily_modified_avg', 0):.2f} | {(previous.get('modified', 0) / max(1, calendar.monthrange((date.fromisoformat(progress['previous_start']).year), (date.fromisoformat(progress['previous_start']).month))[1])) if progress.get('previous_start') else 0:.2f} |
| 1日平均新規数 | {progress.get('daily_new_avg', 0):.2f} | {(previous.get('added', 0) / max(1, calendar.monthrange((date.fromisoformat(progress['previous_start']).year), (date.fromisoformat(progress['previous_start']).month))[1])) if progress.get('previous_start') else 0:.2f} |

| 現在指標 | 値 |
| :--- | ---: |
| 現在の公開記事数 | {weekly._fmt_int(progress.get('published_count'))} |
| 手動検証済み記事数 | {weekly._fmt_int(progress.get('verified_count'))} |
| 未検証記事数 | {weekly._fmt_int(progress.get('unverified_count'))} |
| 検証進捗率 | {progress.get('verification_rate', 0):.1%} |

> 検証済み判定の入力元: {progress.get('review_status_source', '未設定')}。推測でverifiedは付与していません。"""


def _build_action_candidates_section(bottlenecks: list[dict], rewrite_tracking: list[dict]) -> str:
    candidates = weekly.sort_bottlenecks(bottlenecks)[:10]
    rows = []
    for b in candidates:
        action = "タイトル・導入文・検索意図との一致を優先確認"
        if b.get("priority") == "B":
            action = "内部リンク追加と本文の検索意図補強"
        rows.append(
            f"| {b.get('priority', 'C')} | `{b.get('page', '')}` | "
            f"{weekly._fmt_int(b.get('impressions'))} | {weekly._fmt_rate(b.get('ctr'))} | "
            f"{weekly._fmt_float(b.get('position'))} | {action} |"
        )
    if not rows:
        return "## 今月の対応候補\n\n_対応候補はありません。_"
    return """## 今月の対応候補

| 優先度 | URL | 表示回数 | CTR | 平均順位 | 推奨対応 |
| :--- | :--- | ---: | ---: | ---: | :--- |
""" + "\n".join(rows)


def render_monthly_issue_body(
    month: str,
    period_text: str,
    metrics: dict,
    previous_metrics: dict,
    gsc_summary: dict,
    previous_gsc_summary: dict,
    bottlenecks: list[dict],
    rewrite_tracking: list[dict],
    article_progress: dict,
    host_summary: dict,
    countries: list[dict],
    content_gap_section: str,
    monthly_history: list[dict],
    index_status: dict,
    data_status: list[str] | None = None,
    comparison_context: dict | None = None,
) -> str:
    ga4_change = build_monthly_ga4_comparison(metrics, previous_metrics)
    gsc_change = build_monthly_gsc_comparison(gsc_summary, previous_gsc_summary)
    alerts = build_monthly_anomaly_alerts(gsc_change, ga4_change, metrics, host_summary, comparison_context)
    judgement = build_monthly_judgement(gsc_change, ga4_change, rewrite_tracking, comparison_context)
    host_section = weekly._build_host_summary_section(host_summary).replace("###", "##", 1)
    noise_section = weekly._build_noise_section().replace("今週", "今月")
    country_section = weekly._build_country_section(countries).replace("###", "##", 1)
    index_section = weekly._build_index_status_section(index_status).replace("###", "##", 1)

    data_warning = ""
    if data_status:
        data_warning = "\n\n> データ取得状況: " + " / ".join(data_status)
    if comparison_context and comparison_context.get("note"):
        data_warning += f"\n\n> {comparison_context['note']}"

    return (
        f"# 月次統合分析レポート（{month}）\n\n対象期間: {period_text}"
        + data_warning
        + "\n\n---\n\n"
        + _build_monthly_overview_section(metrics, ga4_change, gsc_summary, gsc_change, article_progress, bottlenecks, judgement, comparison_context)
        + "\n\n---\n\n"
        + _build_monthly_anomaly_section(alerts)
        + "\n\n---\n\n"
        + _build_ga4_monthly_section(metrics, ga4_change, comparison_context)
        + "\n\n---\n\n"
        + _build_gsc_monthly_section(gsc_summary, gsc_change, comparison_context)
        + "\n\n---\n\n"
        + _build_monthly_bottleneck_section(bottlenecks)
        + "\n\n---\n\n"
        + _build_monthly_rewrite_section(rewrite_tracking)
        + host_section
        + noise_section
        + country_section
        + "\n\n---\n\n"
        + _build_monthly_article_progress_section(article_progress)
        + "\n\n---\n\n"
        + index_section
        + content_gap_section
        + "\n\n---\n\n"
        + _build_monthly_history_section(monthly_history)
        + "\n\n---\n\n"
        + _build_action_candidates_section(bottlenecks, rewrite_tracking)
        + "\n\n> このIssueは `monthly_ga4.yml` によって自動生成されました。対応完了後クローズしてください。"
    )


def issue_search_query(title: str) -> str:
    return f'repo:${{OWNER}}/${{REPO}} is:issue in:title "{title}"'


def duplicate_issue_number(existing_issues: list[dict], title: str) -> int | None:
    for issue in existing_issues:
        if issue.get("title") == title and issue.get("number") is not None:
            return int(issue["number"])
    return None


def build_monthly_output(run_date: date = TODAY) -> dict:
    start, end = month_period_for_run(run_date)
    previous_start, previous_end = previous_month_period(start)
    config = load_report_config()
    comparison_context = build_comparison_context(previous_start, previous_end, config)
    month = month_key(start)
    period_text = f"{start.isoformat()} 〜 {end.isoformat()}"
    data_status = []

    current_raw = {"overall": {}, "channels": [], "countries": [], "events": [], "host_summary": {}}
    previous_raw = {"overall": {}, "channels": [], "countries": [], "events": [], "host_summary": {}}
    try:
        ga4_client = weekly._build_ga4_client()
        weekly.GA4_QUERY_ERRORS.clear()
        current_raw = weekly.fetch_all_ga4(ga4_client, start, end)
        current_ga4_errors = list(weekly.GA4_QUERY_ERRORS)
        weekly.GA4_QUERY_ERRORS.clear()
        previous_raw = weekly.fetch_all_ga4(ga4_client, previous_start, previous_end)
        previous_ga4_errors = list(weekly.GA4_QUERY_ERRORS)
    except Exception as e:
        data_status.append(f"GA4データ取得失敗: {e}")
        current_ga4_errors = [str(e)]
        previous_ga4_errors = [str(e)]

    metrics = compute_monthly_metrics(current_raw, start, config, current_ga4_errors)
    previous_metrics = compute_monthly_metrics(previous_raw, previous_start, config, previous_ga4_errors)
    if metrics.get("status") != "ok":
        data_status.append(f"GA4今月データ: {metrics.get('status')} ({metrics.get('reason')})")
    if previous_metrics.get("status") != "ok":
        data_status.append(f"GA4前月データ: {previous_metrics.get('status')} ({previous_metrics.get('reason')})")

    bottlenecks, gsc_summary, previous_gsc_summary, _previous_bottlenecks = fetch_monthly_gsc(
        start, end, previous_start, previous_end
    )
    if not gsc_summary:
        data_status.append("GSCデータ取得失敗またはデータなし")

    rewrite_tracking = load_monthly_rewrite_tracking(start, end, today=run_date)
    article_progress = build_monthly_article_progress(start, end, previous_start, previous_end)
    article_progress["previous_start"] = previous_start.isoformat()
    article_progress["previous_end"] = previous_end.isoformat()
    content_gap_section, content_gap = _load_monthly_content_gap(limit=20)
    index_status = weekly.load_index_status()

    ga4_change = build_monthly_ga4_comparison(metrics, previous_metrics)
    gsc_change = build_monthly_gsc_comparison(gsc_summary, previous_gsc_summary)
    host_summary = current_raw.get("host_summary", {})
    anomalies = build_monthly_anomaly_alerts(gsc_change, ga4_change, metrics, host_summary, comparison_context)
    judgement = build_monthly_judgement(gsc_change, ga4_change, rewrite_tracking, comparison_context)

    placeholder = {
        "report_type": "monthly",
        "generated_at": run_date.isoformat(),
        "month": month,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "previous_period": {"start": previous_start.isoformat(), "end": previous_end.isoformat()},
        "summary": {
            "judgement": judgement,
            "anomalies": anomalies,
            "comparison_context": comparison_context,
            "top_bottlenecks": [weekly._slug_from_url(b.get("page", "")) for b in weekly.sort_bottlenecks(bottlenecks)[:3]],
        },
        "anomalies": anomalies,
        "ga4": {
            "current": metrics,
            "previous": previous_metrics,
            "change": ga4_change,
            "host_breakdown": host_summary.get("hosts", []),
        },
        "gsc": {
            "current": gsc_summary,
            "previous": previous_gsc_summary,
            "change": gsc_change,
            "bottlenecks": weekly.sort_bottlenecks(bottlenecks),
        },
        "rewrite_tracking": rewrite_tracking,
        "rewrite_verdict_counts": rewrite_verdict_counts(rewrite_tracking),
        "article_progress": article_progress,
        "content_gap": content_gap,
        "monthly_history": [],
        "data_status": data_status,
        "report_config": config,
    }
    monthly_history = load_monthly_history(placeholder, limit=6)
    placeholder["monthly_history"] = monthly_history
    placeholder["issue_title"] = f"【月次レポート】GA4 + GSC ボトルネック（{month_label(start)}）"
    placeholder["issue_body"] = render_monthly_issue_body(
        month_label(start),
        period_text,
        metrics,
        previous_metrics,
        gsc_summary,
        previous_gsc_summary,
        bottlenecks,
        rewrite_tracking,
        article_progress,
        host_summary,
        current_raw.get("countries", []),
        content_gap_section,
        monthly_history,
        index_status,
        data_status=data_status,
        comparison_context=comparison_context,
    )
    return placeholder


def main() -> None:
    start, _end = month_period_for_run(TODAY)
    output = build_monthly_output(TODAY)
    path = monthly_report_path(start)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {path.relative_to(BASE)}")
    if output.get("data_status"):
        print("[WARN] " + " / ".join(output["data_status"]))
    print("Done.")


if __name__ == "__main__":
    main()
