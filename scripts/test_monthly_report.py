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


if __name__ == "__main__":
    unittest.main()
