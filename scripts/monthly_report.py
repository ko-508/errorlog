"""
月次統合レポート生成スクリプト
前月1日〜前月末日の GA4 + GSC + 改善進捗を GitHub Issue 用 Markdown と JSON にまとめる。
"""

from __future__ import annotations

import calendar
import json
import os
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import weekly_report as weekly

BASE = weekly.BASE
REPORTS_DIR = weekly.REPORTS_DIR
TODAY = date.today()


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
) -> list[str]:
    alerts = []
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


def build_monthly_judgement(gsc_change: dict, ga4_change: dict, rewrite_tracking: list[dict]) -> str:
    improved = sum(1 for r in rewrite_tracking if r.get("verdict") == "改善")
    worsened = sum(1 for r in rewrite_tracking if r.get("verdict") == "悪化")
    imp_pct = gsc_change.get("impressions", {}).get("pct_change")
    ctr_delta = gsc_change.get("ctr", {}).get("delta", 0)
    pos_delta = gsc_change.get("position", {}).get("delta", 0)

    if imp_pct is not None and imp_pct <= -0.10 and pos_delta >= 1.0:
        return "検索表示回数と平均順位がともに悪化しています。"
    if imp_pct is not None and imp_pct <= -0.10 and ctr_delta > 0:
        return "検索流入は減少しましたが、CTRは改善しています。"
    if improved > worsened and improved > 0:
        return "既存記事の修正後、検索表示回数に改善傾向が見られます。"

    organic = ga4_change.get("organic_sessions", {}).get("pct_change")
    if organic is not None and organic <= -0.25:
        return "Organic Searchセッションが減少しています。"
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


def build_monthly_article_progress(start: date, end: date, previous_start: date, previous_end: date) -> dict:
    current = weekly._count_git_post_changes(start, end)
    previous = weekly._count_git_post_changes(previous_start, previous_end)
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
) -> str:
    top = "、".join(weekly._slug_from_url(b.get("page", "")) for b in weekly.sort_bottlenecks(bottlenecks)[:3]) or "該当なし"
    current = article_progress.get("current", {})
    return f"""## 今月の総括

- GA4 Organic Searchセッション: {weekly._fmt_int(metrics.get('organic_sessions'))}（前月比 {weekly._format_change(ga4_change['organic_sessions'])}）
- GSC表示回数: {weekly._fmt_int(gsc_summary.get('impressions'))}（前月比 {weekly._format_change(gsc_change['impressions'])}）
- GSCクリック数: {weekly._fmt_int(gsc_summary.get('clicks'))}（前月比 {weekly._format_change(gsc_change['clicks'])}）
- 平均掲載順位: {weekly._fmt_float(gsc_summary.get('position'))}（前月 {weekly._fmt_previous(gsc_change['position'], weekly._fmt_float)}）
- 今月修正した記事数: {weekly._fmt_int(current.get('modified'))}
- 今月新規公開した記事数: {weekly._fmt_int(current.get('added'))}
- 今月非公開化した記事数: {weekly._fmt_int(current.get('unpublished'))}
- 最優先対応記事: {top}

{judgement}"""


def _build_ga4_monthly_section(metrics: dict, ga4_change: dict) -> str:
    rows = [
        ("アクティブユーザー", weekly._fmt_int(metrics.get("active_users")), weekly._fmt_previous(ga4_change["active_users"], weekly._fmt_int), weekly._format_change(ga4_change["active_users"])),
        ("セッション", weekly._fmt_int(metrics.get("sessions")), weekly._fmt_previous(ga4_change["sessions"], weekly._fmt_int), weekly._format_change(ga4_change["sessions"])),
        ("Organic Searchセッション", weekly._fmt_int(metrics.get("organic_sessions")), weekly._fmt_previous(ga4_change["organic_sessions"], weekly._fmt_int), weekly._format_change(ga4_change["organic_sessions"])),
        ("Directセッション", weekly._fmt_int(metrics.get("direct_sessions")), weekly._fmt_previous(ga4_change["direct_sessions"], weekly._fmt_int), weekly._format_change(ga4_change["direct_sessions"])),
        ("日本国内率", weekly._fmt_rate(metrics.get("japan_ratio")), weekly._fmt_previous(ga4_change["japan_ratio"], weekly._fmt_rate), weekly._format_change(ga4_change["japan_ratio"])),
        ("1セッションあたりPV", f"{metrics.get('pv_per_sess', 0):.2f}", weekly._fmt_previous(ga4_change["pv_per_sess"], lambda v: f"{float(v or 0):.2f}"), weekly._format_change(ga4_change["pv_per_sess"])),
        ("平均エンゲージ時間", f"{metrics.get('avg_engagement_time', 0):.1f}秒", weekly._fmt_previous(ga4_change["avg_engagement_time"], lambda v: f"{float(v or 0):.1f}秒"), weekly._format_change(ga4_change["avg_engagement_time"])),
        ("離脱率", weekly._fmt_rate(metrics.get("bounce_rate")), weekly._fmt_previous(ga4_change["bounce_rate"], weekly._fmt_rate), weekly._format_change(ga4_change["bounce_rate"])),
    ]
    body = "\n".join(f"| {name} | {cur} | {prev} | {chg} |" for name, cur, prev, chg in rows)
    return f"""## GA4トラフィックサマリー

メイン指標は `hostname = errorlog.jp` のみで集計しています。

| 指標 | 今月 | 前月 | 前月比 |
| :--- | ---: | ---: | ---: |
{body}"""


def _build_gsc_monthly_section(gsc_summary: dict, gsc_change: dict) -> str:
    if not gsc_summary:
        return "## Search Consoleサイト全体サマリー\n\n_GSCデータが取得できませんでした。_"
    rows = [
        ("総表示回数", weekly._fmt_int(gsc_summary.get("impressions")), weekly._fmt_previous(gsc_change["impressions"], weekly._fmt_int), weekly._format_change(gsc_change["impressions"])),
        ("総クリック数", weekly._fmt_int(gsc_summary.get("clicks")), weekly._fmt_previous(gsc_change["clicks"], weekly._fmt_int), weekly._format_change(gsc_change["clicks"])),
        ("平均CTR", weekly._fmt_rate(gsc_summary.get("ctr")), weekly._fmt_previous(gsc_change["ctr"], weekly._fmt_rate), weekly._format_change(gsc_change["ctr"])),
        ("平均掲載順位", weekly._fmt_float(gsc_summary.get("position")), weekly._fmt_previous(gsc_change["position"], weekly._fmt_float), weekly._format_change(gsc_change["position"])),
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
            f"{weekly._fmt_int(r.get('before_impressions') or 0)} | "
            f"{weekly._fmt_int(r.get('after_impressions') or 0)} | "
            f"{weekly._fmt_int(r.get('before_clicks') or 0)} | "
            f"{weekly._fmt_int(r.get('after_clicks') or 0)} | "
            f"{weekly._fmt_rate(r.get('before_ctr') or 0)} | "
            f"{weekly._fmt_rate(r.get('after_ctr') or 0)} | "
            f"{weekly._fmt_float(r.get('before_position') or 0)} | "
            f"{weekly._fmt_float(r.get('after_position') or 0)} | "
            f"{r['verdict']} |"
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
) -> str:
    ga4_change = weekly.build_ga4_comparison(metrics, previous_metrics)
    gsc_change = weekly.build_gsc_comparison(gsc_summary, previous_gsc_summary)
    alerts = build_monthly_anomaly_alerts(gsc_change, ga4_change, metrics, host_summary)
    judgement = build_monthly_judgement(gsc_change, ga4_change, rewrite_tracking)
    host_section = weekly._build_host_summary_section(host_summary).replace("###", "##", 1)
    noise_section = weekly._build_noise_section().replace("今週", "今月")
    country_section = weekly._build_country_section(countries).replace("###", "##", 1)
    index_section = weekly._build_index_status_section(index_status).replace("###", "##", 1)

    data_warning = ""
    if data_status:
        data_warning = "\n\n> データ取得状況: " + " / ".join(data_status)

    return (
        f"# 月次統合分析レポート（{month}）\n\n対象期間: {period_text}"
        + data_warning
        + "\n\n---\n\n"
        + _build_monthly_overview_section(metrics, ga4_change, gsc_summary, gsc_change, article_progress, bottlenecks, judgement)
        + "\n\n---\n\n"
        + _build_monthly_anomaly_section(alerts)
        + "\n\n---\n\n"
        + _build_ga4_monthly_section(metrics, ga4_change)
        + "\n\n---\n\n"
        + _build_gsc_monthly_section(gsc_summary, gsc_change)
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
    month = month_key(start)
    period_text = f"{start.isoformat()} 〜 {end.isoformat()}"
    data_status = []

    current_raw = {"overall": {}, "channels": [], "countries": [], "events": [], "host_summary": {}}
    previous_raw = {"overall": {}, "channels": [], "countries": [], "events": [], "host_summary": {}}
    try:
        ga4_client = weekly._build_ga4_client()
        current_raw = weekly.fetch_all_ga4(ga4_client, start, end)
        previous_raw = weekly.fetch_all_ga4(ga4_client, previous_start, previous_end)
    except Exception as e:
        data_status.append(f"GA4データ取得失敗: {e}")

    metrics = weekly.compute_metrics(current_raw)
    previous_metrics = weekly.compute_metrics(previous_raw)

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

    ga4_change = weekly.build_ga4_comparison(metrics, previous_metrics)
    gsc_change = weekly.build_gsc_comparison(gsc_summary, previous_gsc_summary)
    host_summary = current_raw.get("host_summary", {})
    anomalies = build_monthly_anomaly_alerts(gsc_change, ga4_change, metrics, host_summary)
    judgement = build_monthly_judgement(gsc_change, ga4_change, rewrite_tracking)

    placeholder = {
        "report_type": "monthly",
        "generated_at": run_date.isoformat(),
        "month": month,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "previous_period": {"start": previous_start.isoformat(), "end": previous_end.isoformat()},
        "summary": {
            "judgement": judgement,
            "anomalies": anomalies,
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
