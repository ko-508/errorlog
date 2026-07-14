"""ユニットテスト: weekly_report.py の週次レポート計算ロジック。"""
from __future__ import annotations

import unittest
from datetime import date

import weekly_report as wr


class WeeklyReportCalculationsTest(unittest.TestCase):
    def test_week_over_week_change_with_previous_value(self) -> None:
        change = wr.build_change(80, 100)
        self.assertEqual(change["delta"], -20)
        self.assertAlmostEqual(change["pct_change"], -0.2)
        self.assertEqual(wr._format_change(change), "-20.0%")

    def test_week_over_week_change_with_zero_previous_value(self) -> None:
        change = wr.build_change(10, 0)
        self.assertIsNone(change["pct_change"])
        self.assertEqual(wr._format_change(change), "算出不可")

    def test_missing_previous_data_displays_no_data(self) -> None:
        change = wr.build_change(10, None)
        self.assertFalse(change["previous_exists"])
        self.assertEqual(wr._format_change(change), "データなし")

    def test_position_change_uses_positive_number_for_worse_rank(self) -> None:
        change = wr.build_change(43.9, 19.0, kind="position")
        self.assertEqual(wr._format_change(change), "+24.9")

    def test_missing_gsc_data_keeps_rendering(self) -> None:
        section = wr._build_gsc_summary_section({}, wr.build_gsc_comparison({}, {}))
        self.assertIn("GSCデータが取得できませんでした", section)

    def test_missing_ga4_data_computes_zero_metrics(self) -> None:
        metrics = wr.compute_metrics({"overall": {}, "channels": [], "countries": [], "events": []})
        self.assertEqual(metrics["active_users"], 0)
        self.assertEqual(metrics["organic_sessions"], 0)
        self.assertEqual(metrics["direct_sessions"], 0)

    def test_zenn_only_host_summary_does_not_become_main_metric(self) -> None:
        section = wr._build_host_summary_section({
            "primary_host_pv_share": 0.0,
            "hosts": [{"host": "zenn.dev", "pv": 10, "pv_share": 1.0, "uu": 8, "uu_share": 1.0}],
        })
        self.assertIn("メイン指標は errorlog.jp のみ", section)
        self.assertIn("zenn.dev", section)

    def test_mixed_hosts_report_keeps_zenn_warning(self) -> None:
        section = wr._build_host_summary_section({
            "primary_host_pv_share": 0.4,
            "hosts": [
                {"host": "errorlog.jp", "pv": 4, "pv_share": 0.4, "uu": 3, "uu_share": 0.5},
                {"host": "zenn.dev", "pv": 6, "pv_share": 0.6, "uu": 3, "uu_share": 0.5},
            ],
        })
        self.assertIn("zenn.dev が全体", section)
        self.assertIn("errorlog.jp のみ", section)

    def test_recent_rewrite_is_pending(self) -> None:
        record = wr.evaluate_rewrite_record(
            {"slug": "github_api_404", "rewrite_date": "2026-07-01"},
            today=date(2026, 7, 10),
        )
        self.assertEqual(record["verdict"], "判定保留")
        self.assertEqual(record["reason"], "修正から14日未満")

    def test_position_improvement_direction_is_lower_number(self) -> None:
        record = wr.evaluate_rewrite_record(
            {
                "slug": "github_api_404",
                "rewrite_date": "2026-06-01",
                "before_impressions": 10,
                "after_impressions": 10,
                "before_position": 20.0,
                "after_position": 16.5,
            },
            today=date(2026, 7, 1),
        )
        self.assertEqual(record["verdict"], "改善")

    def test_missing_index_status_file_is_nonfatal(self) -> None:
        status = wr.load_index_status()
        if not status.get("available"):
            self.assertIn("自動取得していません", status["message"])

    def test_old_weekly_report_json_can_feed_history(self) -> None:
        history = wr._extract_gsc_history(
            "2026-07-03 〜 2026-07-09",
            {"impressions": 100, "clicks": 5, "ctr": 0.05, "position": 10.0},
            [{"period": "2026-06-26 〜 2026-07-02", "gsc_summary": {"impressions": 80, "clicks": 4, "ctr": 0.05, "position": 12.0}}],
        )
        self.assertEqual(len(history), 2)
        self.assertEqual(history[1]["impressions"], 80)


class WeeklyReportBottleneckPriorityTest(unittest.TestCase):
    def test_bottleneck_priority_rules(self) -> None:
        self.assertEqual(wr.classify_bottleneck_priority(20, 0.0, 10.0)[0], "A")
        self.assertEqual(wr.classify_bottleneck_priority(20, 0.02, 25.0)[0], "B")
        self.assertEqual(wr.classify_bottleneck_priority(5, 0.04, 40.0)[0], "C")

    def test_bottleneck_sort_uses_priority_then_impressions(self) -> None:
        rows = wr.sort_bottlenecks([
            {"page": "c", "impressions": 100, "ctr": 0.04, "position": 50.0},
            {"page": "b", "impressions": 30, "ctr": 0.02, "position": 25.0},
            {"page": "a", "impressions": 20, "ctr": 0.0, "position": 8.0},
        ])
        self.assertEqual([r["priority"] for r in rows], ["A", "B", "C"])


class WeeklyReportContentGapTest(unittest.TestCase):
    def test_content_gap_filter_removes_duplicates_and_code(self) -> None:
        items = [
            {"query": "apiが過負荷状態です。"},
            {"query": "apiが過負荷状態です"},
            {"query": "const sellingpartnerapi = require('amazon-sp-api')"},
            {"query": "cliとは"},
            {"query": "github api 403 forbidden"},
        ]
        filtered = wr._filter_content_gap_items(items)
        self.assertEqual([x["query"] for x in filtered], ["apiが過負荷状態です。", "github api 403 forbidden"])

    def test_content_gap_filter_keeps_meaningful_short_terms(self) -> None:
        items = [
            {"query": "+429"},
            {"query": "429+"},
            {"query": "401エラー"},
            {"query": "bashとは"},
            {"query": "docker compose"},
            {"query": "the model returned the following errors: data retention mode 'default' is not available for this model"},
        ]
        filtered = wr._filter_content_gap_items(items)
        self.assertEqual([x["query"] for x in filtered], ["401エラー", "bashとは", "docker compose"])


class WeeklyReportAnomalyTest(unittest.TestCase):
    def test_anomaly_alerts_detect_major_drop_and_position_worse(self) -> None:
        alerts = wr.build_anomaly_alerts(
            {
                "impressions": wr.build_change(388, 2304),
                "clicks": wr.build_change(6, 20),
                "position": wr.build_change(43.9, 19.0, kind="position"),
            },
            {"organic_sessions": wr.build_change(10, 30)},
        )
        self.assertEqual(len(alerts), 4)
        self.assertIn("表示回数", alerts[0])
        self.assertTrue(any("19.0→43.9" in a for a in alerts))


if __name__ == "__main__":
    unittest.main()
