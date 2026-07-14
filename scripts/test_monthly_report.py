"""ユニットテスト: monthly_report.py の月次レポート計算ロジック。"""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import monthly_report as mr
import weekly_report as wr


class MonthlyReportPeriodTest(unittest.TestCase):
    def test_january_run_targets_previous_december(self) -> None:
        start, end = mr.month_period_for_run(date(2026, 1, 1))
        self.assertEqual(start, date(2025, 12, 1))
        self.assertEqual(end, date(2025, 12, 31))

    def test_march_run_targets_february_end(self) -> None:
        start, end = mr.month_period_for_run(date(2026, 3, 1))
        self.assertEqual(start, date(2026, 2, 1))
        self.assertEqual(end, date(2026, 2, 28))

    def test_leap_year_february_end(self) -> None:
        start, end = mr.month_period_for_run(date(2024, 3, 1))
        self.assertEqual(start, date(2024, 2, 1))
        self.assertEqual(end, date(2024, 2, 29))


class MonthlyReportComparisonTest(unittest.TestCase):
    def test_previous_month_comparison(self) -> None:
        change = wr.build_change(8240, 12430)
        self.assertEqual(wr._format_change(change), "-33.7%")

    def test_previous_month_zero_value(self) -> None:
        change = wr.build_change(10, 0)
        self.assertIsNone(change["pct_change"])
        self.assertEqual(wr._format_change(change), "算出不可")

    def test_rate_fields_use_point_delta(self) -> None:
        change = wr.build_change(0.0147, 0.0151, kind="rate")
        self.assertEqual(wr._format_change(change), "-0.04pt")

    def test_position_direction_is_not_reversed(self) -> None:
        worse = wr.build_change(31.5, 21.8, kind="position")
        better = wr.build_change(18.0, 21.8, kind="position")
        self.assertEqual(wr._format_change(worse), "+9.7")
        self.assertEqual(wr._format_change(better), "-3.8")

    def test_incomplete_month_is_reference_value(self) -> None:
        ctx = mr.build_comparison_context(
            date(2026, 5, 1),
            date(2026, 5, 31),
            {"site_launch_date": "2026-05-27"},
        )
        change = wr.build_change(5225, 138)
        self.assertTrue(ctx["reference_only"])
        self.assertEqual(mr._format_monthly_change(change, ctx), "+3686.2%（参考）")

    def test_null_displays_as_no_data(self) -> None:
        self.assertEqual(mr._display_value(None), "データなし")
        change = wr.build_change(310, None)
        self.assertEqual(mr._format_monthly_change(change), "算出不可")

    def test_actual_zero_displays_as_zero(self) -> None:
        self.assertEqual(mr._display_value(0), "0")


class MonthlyReportJudgementTest(unittest.TestCase):
    def test_large_improvement_is_not_flat(self) -> None:
        text = mr.build_monthly_judgement(
            {
                "impressions": wr.build_change(5225, 138),
                "clicks": wr.build_change(88, 1),
                "ctr": wr.build_change(0.016, 0.007, kind="rate"),
                "position": wr.build_change(24.0, 52.9, kind="position"),
            },
            {"organic_sessions": wr.build_change(120, 50)},
            [],
        )
        self.assertNotEqual(text, "前月から大きな変化はありません。")
        self.assertIn("改善", text)

    def test_large_worsening_is_not_flat(self) -> None:
        text = mr.build_monthly_judgement(
            {
                "impressions": wr.build_change(100, 1000),
                "clicks": wr.build_change(10, 100),
                "ctr": wr.build_change(0.01, 0.01, kind="rate"),
                "position": wr.build_change(40.0, 20.0, kind="position"),
            },
            {"organic_sessions": wr.build_change(20, 100)},
            [],
        )
        self.assertNotEqual(text, "前月から大きな変化はありません。")
        self.assertIn("悪化", text)

    def test_incomplete_month_is_excluded_from_judgement(self) -> None:
        text = mr.build_monthly_judgement(
            {"impressions": wr.build_change(5225, 138), "ctr": wr.build_change(0.01, 0.01, kind="rate"), "position": wr.build_change(24.0, 52.9, kind="position")},
            {"organic_sessions": wr.build_change(120, 0)},
            [],
            {"reference_only": True},
        )
        self.assertIn("判定は行っていません", text)

    def test_mixed_impressions_down_ctr_up(self) -> None:
        text = mr.build_monthly_judgement(
            {"impressions": wr.build_change(80, 100), "clicks": wr.build_change(10, 10), "ctr": wr.build_change(0.02, 0.01, kind="rate"), "position": wr.build_change(20.0, 20.0, kind="position")},
            {"organic_sessions": wr.build_change(10, 10)},
            [],
        )
        self.assertIn("CTRは改善", text)


class MonthlyReportDataShapeTest(unittest.TestCase):
    def test_errorlog_and_zenn_mixed_host_alert(self) -> None:
        alerts = mr.build_monthly_anomaly_alerts(
            {},
            {},
            {"japan_ratio": 0.50},
            {"hosts": [
                {"host": "zenn.dev", "pv_share": 0.948},
                {"host": "errorlog.jp", "pv_share": 0.052},
            ]},
        )
        self.assertTrue(any("zenn.dev" in alert for alert in alerts))

    def test_incomplete_month_not_used_for_anomaly(self) -> None:
        alerts = mr.build_monthly_anomaly_alerts(
            {"impressions": wr.build_change(10, 1000), "clicks": wr.build_change(1, 100), "position": wr.build_change(50.0, 10.0, kind="position")},
            {"organic_sessions": wr.build_change(1, 100), "sessions": wr.build_change(1, 100)},
            {"japan_ratio": 0.50},
            {"hosts": []},
            {"reference_only": True},
        )
        self.assertEqual(alerts, [])

    def test_zenn_only_host_alert(self) -> None:
        alerts = mr.build_monthly_anomaly_alerts(
            {},
            {},
            {"japan_ratio": 0.50},
            {"hosts": [{"host": "zenn.dev", "pv_share": 1.0}]},
        )
        self.assertTrue(any("100.0%" in alert for alert in alerts))

    def test_missing_gsc_data_renders_message(self) -> None:
        section = mr._build_gsc_monthly_section({}, wr.build_gsc_comparison({}, {}))
        self.assertIn("GSCデータが取得できませんでした", section)

    def test_missing_ga4_data_computes_zero_metrics(self) -> None:
        metrics = wr.compute_metrics({"overall": {}, "channels": [], "countries": [], "events": []})
        self.assertEqual(metrics["sessions"], 0)
        self.assertEqual(metrics["organic_sessions"], 0)

    def test_ga4_previous_data_exists(self) -> None:
        raw = {
            "overall": {"activeUsers": 1, "sessions": 2, "screenPageViews": 4, "bounceRate": 0.5, "averageSessionDuration": 10},
            "channels": [{"sessionDefaultChannelGroup": "Organic Search", "sessions": 2}],
            "countries": [{"country": "Japan", "activeUsers": 1}],
            "events": [],
            "host_summary": {"hosts": [{"host": "errorlog.jp", "pv": 4, "pv_share": 1.0}]},
        }
        metrics = mr.compute_monthly_metrics(raw, date(2026, 5, 1), {})
        self.assertEqual(metrics["status"], "ok")
        self.assertEqual(metrics["sessions"], 2)

    def test_ga4_previous_actual_zero(self) -> None:
        raw = {
            "overall": {"activeUsers": 0, "sessions": 0, "screenPageViews": 0, "bounceRate": 0, "averageSessionDuration": 0},
            "channels": [],
            "countries": [],
            "events": [],
            "host_summary": {"hosts": [{"host": "errorlog.jp", "pv": 0, "pv_share": 0.0}]},
        }
        metrics = mr.compute_monthly_metrics(raw, date(2026, 6, 1), {})
        self.assertEqual(metrics["status"], "ok")
        self.assertEqual(metrics["sessions"], 0)

    def test_ga4_previous_no_data(self) -> None:
        metrics = mr.compute_monthly_metrics({"overall": {}, "channels": [], "countries": [], "events": [], "host_summary": {}}, date(2026, 6, 1), {})
        self.assertEqual(metrics["status"], "no_data")
        self.assertIsNone(metrics["sessions"])

    def test_ga4_api_failure(self) -> None:
        metrics = mr.compute_monthly_metrics({}, date(2026, 6, 1), {}, ["boom"])
        self.assertEqual(metrics["status"], "error")
        self.assertIn("boom", metrics["reason"])

    def test_hostname_mismatch(self) -> None:
        raw = {"overall": {"activeUsers": 1}, "channels": [], "countries": [], "events": [], "host_summary": {"hosts": [{"host": "zenn.dev", "pv": 10}]}}
        metrics = mr.compute_monthly_metrics(raw, date(2026, 6, 1), {})
        self.assertEqual(metrics["reason"], "hostname_mismatch")

    def test_monthly_history_less_than_six_months(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_dir = mr.REPORTS_DIR
            mr.REPORTS_DIR = Path(tmp)
            try:
                (mr.REPORTS_DIR / "monthly_report_202606.json").write_text(
                    json.dumps({"report_type": "monthly", "month": "2026-06", "ga4": {"current": {"sessions": 1}}}),
                    encoding="utf-8",
                )
                history = mr.load_monthly_history(limit=6)
            finally:
                mr.REPORTS_DIR = old_dir
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["month"], "2026-06")

    def test_recent_rewrite_is_pending(self) -> None:
        record = wr.evaluate_rewrite_record(
            {"slug": "github_api_404", "rewrite_date": "2026-07-20"},
            today=date(2026, 8, 1),
        )
        self.assertEqual(record["verdict"], "判定保留")

    def test_rewrite_missing_before_position_is_not_zero(self) -> None:
        record = wr.evaluate_rewrite_record(
            {"slug": "github_api_404", "rewrite_date": "2026-06-01", "after_position": 10.0},
            today=date(2026, 7, 1),
        )
        section = mr._build_monthly_rewrite_section([record])
        self.assertIn("データなし", section)
        self.assertIn("判定保留（修正前データ不足）", section)

    def test_duplicate_issue_detection(self) -> None:
        number = mr.duplicate_issue_number(
            [{"number": 12, "title": "【月次レポート】GA4 + GSC ボトルネック（2026年7月）"}],
            "【月次レポート】GA4 + GSC ボトルネック（2026年7月）",
        )
        self.assertEqual(number, 12)

    def test_old_weekly_json_can_be_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "weekly_report_20260712.json"
            path.write_text(json.dumps({"generated_at": "2026-07-12", "gsc_summary": {"impressions": 1}}), encoding="utf-8")
            data = mr.read_report_json(path)
        self.assertEqual(data["gsc_summary"]["impressions"], 1)

    def test_monthly_json_report_type_is_saved(self) -> None:
        output = {
            "report_type": "monthly",
            "month": "2026-07",
            "period": {"start": "2026-07-01", "end": "2026-07-31"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "monthly_report_202607.json"
            path.write_text(json.dumps(output), encoding="utf-8")
            loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["report_type"], "monthly")


class MonthlyReportGitHistoryTest(unittest.TestCase):
    def test_git_history_counts_new_modified_deleted(self) -> None:
        result = mr.aggregate_article_events([
            {"status": "A", "path": "content/posts/new.md"},
            {"status": "M", "path": "content/posts/existing.md"},
            {"status": "D", "path": "content/posts/old.md"},
        ])
        self.assertEqual(result["added"], 1)
        self.assertEqual(result["modified"], 1)
        self.assertEqual(result["unpublished"], 1)

    def test_rename_is_not_counted_as_delete_and_add(self) -> None:
        result = mr.aggregate_article_events([
            {"status": "R100", "old_path": "content/posts/a.md", "new_path": "content/posts/b.md"},
        ])
        self.assertEqual(result["added"], 0)
        self.assertEqual(result["unpublished"], 0)
        self.assertEqual(result["modified"], 1)

    def test_duplicate_modifications_are_deduplicated(self) -> None:
        result = mr.aggregate_article_events([
            {"status": "M", "path": "content/posts/a.md"},
            {"status": "M", "path": "content/posts/a.md"},
        ])
        self.assertEqual(result["modified"], 1)

    def test_draft_to_public_and_public_to_draft(self) -> None:
        result = mr.aggregate_article_events([
            {"status": "M", "path": "content/posts/a.md", "old_draft": True, "new_draft": False},
            {"status": "M", "path": "content/posts/b.md", "old_draft": False, "new_draft": True},
        ])
        self.assertEqual(result["added"], 1)
        self.assertEqual(result["unpublished"], 1)

    def test_ignores_non_post_paths(self) -> None:
        result = mr.aggregate_article_events([
            {"status": "M", "path": "content/privacy.md"},
            {"status": "A", "path": "data/foo.json"},
        ])
        self.assertEqual(result["added"], 0)
        self.assertEqual(result["modified"], 0)

    def test_incomplete_git_history_flag(self) -> None:
        result = mr.aggregate_article_events([], history_complete=False)
        self.assertFalse(result["history_complete"])


if __name__ == "__main__":
    unittest.main()
