from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.article_pipeline import PipelineError
from scripts.article_pipeline.__main__ import command_new, command_resume
from scripts.article_pipeline.graph import PipelineGraph, build_production_stages
from scripts.article_pipeline.intake import load_topic
from scripts.article_pipeline.state import StateFile, initial_state
from scripts.article_pipeline.store import RunStore
from tests.article_pipeline_helpers import RepoCase, topic_text


class IntakeTest(RepoCase):
    def test_candidate_gates_existing_post_draft_and_ready_run(self) -> None:
        with self.subTest("existing post"):
            self.write_post()
            with self.assertRaisesRegex(PipelineError, "既存記事"):
                self.run_new()

        self.tearDown()
        self.setUp()
        with self.subTest("draft"):
            (self.root / "drafts/sample_error.md").write_text("draft", encoding="utf-8")
            with self.assertRaisesRegex(PipelineError, "人手下書き"):
                self.run_new()

        self.tearDown()
        self.setUp()
        with self.subTest("ready run"):
            store = RunStore(self.root)
            store.ensure_gitignored()
            run_id = "cand_20261004T000000Z_sample_error_abcd"
            store.mkdir(Path("runs") / run_id, exclusive=True)
            state = initial_state(
                run_id=run_id,
                slug="sample_error",
                mode="candidate",
                topic_source=self.write_topic(),
                stage_names=PipelineGraph(build_production_stages()).stage_names,
            )
            state["verdict"] = "ready_for_human_review"
            StateFile(store, run_id).write(state)
            with self.assertRaisesRegex(PipelineError, "--new-run"):
                self.run_new()
            self.assertEqual(self.run_new(new_run=True), 0)

    def test_comparison_without_article_stops(self) -> None:
        with self.assertRaisesRegex(PipelineError, "比較対象記事がありません"):
            self.run_new(mode="comparison")

    def test_comparison_records_target_and_excludes_it(self) -> None:
        post = self.write_post()
        expected_blob = self.git("hash-object", post.relative_to(self.root).as_posix())
        self.assertEqual(self.run_new(mode="comparison"), 0)
        states = list((self.root / "run/article_pipeline/runs").glob("cmp_*/state.json"))
        self.assertEqual(len(states), 1)
        state = json.loads(states[0].read_text(encoding="utf-8"))
        self.assertFalse(state["publish_allowed"])
        self.assertEqual(state["comparison_target"]["blob_sha"], expected_blob)
        report = json.loads((states[0].parent / "dedup_report.json").read_text(encoding="utf-8"))
        self.assertNotIn("sample_error", [item["slug"] for item in report["overlaps"]])
        self.assertEqual(report["excluded_for_comparison"][0]["slug"], "sample_error")

    def test_topic_format_change_reruns_s0_with_identical_hashes(self) -> None:
        self.assertEqual(self.run_new(), 0)
        state_path = next((self.root / "run/article_pipeline/runs").glob("*/state.json"))
        before = json.loads(state_path.read_text(encoding="utf-8"))
        topic_path = Path(before["topic_source"])
        topic_path.write_text("\n  " + topic_text(), encoding="utf-8")
        args = argparse.Namespace(
            run=before["run_id"],
            from_stage=None,
            accept_modified=None,
        )
        self.assertEqual(command_resume(args, self.root), 0)
        after = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(
            before["stages"]["S0_intake"]["outputs"],
            after["stages"]["S0_intake"]["outputs"],
        )
        self.assertEqual(after["stages"]["S1_plan"]["status"], "pending")
        self.assertEqual(after["stages"]["S0_intake"]["attempts"], 2)

    def test_topic_content_change_invalidates_all_dependents(self) -> None:
        self.assertEqual(self.run_new(), 0)
        state_path = next((self.root / "run/article_pipeline/runs").glob("*/state.json"))
        state = json.loads(state_path.read_text(encoding="utf-8"))
        topic_path = Path(state["topic_source"])
        topic_path.write_text(
            topic_text().replace('"service": "Sample"', '"service": "Changed"'),
            encoding="utf-8",
        )
        args = argparse.Namespace(run=state["run_id"], from_stage=None, accept_modified=None)
        self.assertEqual(command_resume(args, self.root), 0)
        after = json.loads(state_path.read_text(encoding="utf-8"))
        for name in list(after["stages"])[1:]:
            self.assertEqual(after["stages"][name]["status"], "invalidated", name)

    def test_same_input_produces_same_s0_hashes(self) -> None:
        self.assertEqual(self.run_new(), 0)
        first_state_path = next((self.root / "run/article_pipeline/runs").glob("*/state.json"))
        first = json.loads(first_state_path.read_text(encoding="utf-8"))
        self.assertEqual(self.run_new(), 0)
        states = sorted((self.root / "run/article_pipeline/runs").glob("*/state.json"))
        second_path = next(path for path in states if path != first_state_path)
        second = json.loads(second_path.read_text(encoding="utf-8"))
        self.assertEqual(
            first["stages"]["S0_intake"]["outputs"],
            second["stages"]["S0_intake"]["outputs"],
        )

    def test_invalid_topic_variants_stop_with_cause(self) -> None:
        variants = {
            "duplicate": '{"slug":"sample_error","slug":"duplicate","service":"Sample","error_text":"x","error_code":"E100"}',
            "unknown": topic_text().replace('"notes": ""', '"notes": "", "mystery": true'),
            "slug": topic_text("Invalid Slug"),
            "http": topic_text().replace("https://", "http://"),
        }
        patterns = {
            "duplicate": "duplicate key",
            "unknown": "未知のキー",
            "slug": "slug が不正",
            "http": "https://",
        }
        for name, text in variants.items():
            with self.subTest(name):
                path = self.root / f"{name}.yml"
                path.write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(PipelineError, patterns[name]):
                    load_topic(path)

    def test_slug_is_fixed_after_run_creation(self) -> None:
        self.assertEqual(self.run_new(), 0)
        state_path = next((self.root / "run/article_pipeline/runs").glob("*/state.json"))
        state = json.loads(state_path.read_text(encoding="utf-8"))
        Path(state["topic_source"]).write_text(topic_text("different_slug"), encoding="utf-8")
        args = argparse.Namespace(run=state["run_id"], from_stage=None, accept_modified=None)
        with self.assertRaisesRegex(PipelineError, "新しい run"):
            command_resume(args, self.root)
        unchanged = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(unchanged["slug"], "sample_error")
        self.assertEqual(unchanged["mode"], "candidate")

    def test_mode_is_fixed_after_run_creation(self) -> None:
        self.assertEqual(self.run_new(), 0)
        state_path = next((self.root / "run/article_pipeline/runs").glob("*/state.json"))
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["mode"] = "comparison"
        state["publish_allowed"] = False
        state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        args = argparse.Namespace(run=state["run_id"], from_stage=None, accept_modified=None)
        with self.assertRaisesRegex(PipelineError, "mode を変更できません"):
            command_resume(args, self.root)
