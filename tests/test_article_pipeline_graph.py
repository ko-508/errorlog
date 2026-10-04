from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from scripts.article_pipeline import PipelineError
from scripts.article_pipeline.graph import (
    ArtifactSpec,
    PipelineGraph,
    StageContext,
    StageSpec,
)
from scripts.article_pipeline.state import StateFile, initial_state
from scripts.article_pipeline.store import RunStore
from tests.article_pipeline_helpers import RepoCase


class GraphTest(RepoCase):
    def make_graph(
        self,
        *,
        first_kind: str = "generated",
        first_version: int = 1,
        first_input=None,
        first_runner=None,
    ) -> tuple[RunStore, StateFile, StageContext, PipelineGraph]:
        store = RunStore(self.root)
        store.ensure_gitignored()
        run_id = "cand_20261004T000000Z_sample_error_abcd"
        if not store.exists(Path("runs") / run_id):
            store.mkdir(Path("runs") / run_id, exclusive=True)

        def run_a(context: StageContext, _state: dict[str, Any]) -> None:
            value = context.cache.get("a_value", "A")
            context.write_text("a.txt", value)

        def run_b(context: StageContext, _state: dict[str, Any]) -> None:
            context.write_text("b.txt", str(context.config["second"]["value"]))

        def run_c(context: StageContext, _state: dict[str, Any]) -> None:
            context.write_text("c.txt", "C")

        def run_d(context: StageContext, _state: dict[str, Any]) -> None:
            context.write_text("d.txt", "D")

        stages = [
            StageSpec(
                "A",
                first_version,
                artifacts=(ArtifactSpec("a.txt", first_kind),),
                input_provider=first_input,
                runner=first_runner or run_a,
            ),
            StageSpec(
                "B",
                1,
                dependencies=("A",),
                config_keys=("second.value",),
                artifacts=(ArtifactSpec("b.txt"),),
                runner=run_b,
            ),
            StageSpec(
                "C",
                1,
                artifacts=(ArtifactSpec("c.txt"),),
                runner=run_c,
            ),
            StageSpec(
                "D",
                1,
                dependencies=("B",),
                artifacts=(ArtifactSpec("d.txt"),),
                runner=run_d,
            ),
        ]
        graph = PipelineGraph(stages)
        state_file = StateFile(store, run_id)
        if not store.exists(Path("runs") / run_id / "state.json"):
            state_file.write(
                initial_state(
                    run_id=run_id,
                    slug="sample_error",
                    mode="candidate",
                    topic_source=self.write_topic(),
                    stage_names=graph.stage_names,
                )
            )
        context = StageContext(
            self.root,
            store,
            run_id,
            {"second": {"value": "one"}},
        )
        return store, state_file, context, graph

    def test_generated_change_stops_then_accepts_and_invalidates_dependents(self) -> None:
        store, state_file, context, graph = self.make_graph()
        graph.resume(context, state_file)
        context.write_text("a.txt", "human change")
        with self.assertRaisesRegex(PipelineError, "--accept-modified"):
            graph.resume(context, state_file, through="A")
        state = graph.resume(
            context,
            state_file,
            through="A",
            accept_modified=("a.txt",),
        )
        self.assertEqual(state["stages"]["A"]["status"], "done")
        self.assertEqual(state["stages"]["B"]["status"], "invalidated")
        self.assertEqual(state["stages"]["C"]["status"], "done")
        self.assertEqual(state["stages"]["D"]["status"], "invalidated")

    def test_editable_change_records_revision_and_only_invalidates_dependents(self) -> None:
        store, state_file, context, graph = self.make_graph(first_kind="editable")
        graph.resume(context, state_file)
        context.write_text("a.txt", "edited")
        state = graph.resume(context, state_file, through="A")
        self.assertEqual(state["draft_revisions"][-1]["source"], "human_edit")
        self.assertEqual(state["stages"]["B"]["status"], "invalidated")
        self.assertEqual(state["stages"]["C"]["status"], "done")
        self.assertEqual(state["stages"]["D"]["status"], "invalidated")
        superseded = self.root / "run/article_pipeline/runs" / context.run_id / "superseded"
        archived = list(superseded.glob("*/A/a.txt"))
        self.assertTrue(archived)
        self.assertEqual(archived[0].read_text(encoding="utf-8"), "A")

    def test_derived_change_stops(self) -> None:
        _store, state_file, context, graph = self.make_graph(first_kind="derived")
        graph.resume(context, state_file)
        context.write_text("a.txt", "edited")
        with self.assertRaisesRegex(PipelineError, "派生物"):
            graph.resume(context, state_file, through="A")

    def test_missing_output_always_stops_including_editable_and_accept(self) -> None:
        for kind in ("generated", "editable", "derived"):
            with self.subTest(kind):
                self.tearDown()
                self.setUp()
                store, state_file, context, graph = self.make_graph(first_kind=kind)
                graph.resume(context, state_file)
                store.remove(Path("runs") / context.run_id / "a.txt")
                with self.assertRaisesRegex(PipelineError, "欠損"):
                    graph.resume(
                        context,
                        state_file,
                        through="A",
                        accept_modified=("a.txt",),
                    )

    def test_input_change_with_same_output_does_not_invalidate_downstream(self) -> None:
        external = self.root / "input.txt"
        external.write_text("one", encoding="utf-8")

        def inputs(_context: StageContext, _state: dict[str, Any]) -> Mapping[str, Any]:
            return {"external": external.read_text(encoding="utf-8")}

        _store, state_file, context, graph = self.make_graph(first_input=inputs)
        graph.resume(context, state_file)
        external.write_text("two", encoding="utf-8")
        state = graph.resume(context, state_file, through="A")
        self.assertEqual(state["stages"]["A"]["attempts"], 2)
        self.assertEqual(state["stages"]["B"]["status"], "done")

    def test_input_change_with_changed_output_invalidates_all_dependents(self) -> None:
        external = self.root / "input.txt"
        external.write_text("one", encoding="utf-8")

        def inputs(_context: StageContext, _state: dict[str, Any]) -> Mapping[str, Any]:
            value = external.read_text(encoding="utf-8")
            _context.cache["a_value"] = value
            return {"external": value}

        _store, state_file, context, graph = self.make_graph(first_input=inputs)
        graph.resume(context, state_file)
        external.write_text("two", encoding="utf-8")
        state = graph.resume(context, state_file, through="A")
        self.assertEqual(state["stages"]["B"]["status"], "invalidated")
        self.assertEqual(state["stages"]["C"]["status"], "done")
        self.assertEqual(state["stages"]["D"]["status"], "invalidated")

    def test_later_stage_config_change_invalidates_only_it_and_dependents(self) -> None:
        store, state_file, context, graph = self.make_graph()
        graph.resume(context, state_file)
        context.config["second"]["value"] = "two"
        state = graph.resume(context, state_file, through="B")
        self.assertEqual(state["stages"]["A"]["attempts"], 1)
        self.assertEqual(state["stages"]["B"]["attempts"], 2)
        self.assertEqual(store.read_text(Path("runs") / context.run_id / "b.txt"), "two")
        self.assertEqual(state["stages"]["C"]["status"], "done")
        self.assertEqual(state["stages"]["D"]["status"], "invalidated")

    def test_stage_version_change_reruns_stage_and_invalidates_dependents_on_change(self) -> None:
        _store, state_file, context, graph = self.make_graph()
        graph.resume(context, state_file)

        def versioned(context: StageContext, _state: dict[str, Any]) -> None:
            context.write_text("a.txt", "A version 2")

        _store2, state_file2, context2, graph2 = self.make_graph(
            first_version=2,
            first_runner=versioned,
        )
        state = graph2.resume(context2, state_file2, through="A")
        self.assertEqual(state["stages"]["A"]["stage_version"], 2)
        self.assertEqual(state["stages"]["B"]["status"], "invalidated")
        self.assertEqual(state["stages"]["D"]["status"], "invalidated")

    def test_interrupted_running_stage_is_failed_archived_and_rebuilt(self) -> None:
        store, state_file, context, graph = self.make_graph()
        state = state_file.read()
        state = state_file.transition(
            state,
            "A",
            "running",
            stage_version=1,
            attempts=1,
            input_fingerprint="sha256:interrupted",
        )
        context.write_text("a.txt", "partial")
        state = graph.resume(context, state_file, through="A")
        self.assertEqual(state["stages"]["A"]["status"], "done")
        self.assertEqual(state["stages"]["A"]["attempts"], 2)
        archived = list(
            (self.root / "run/article_pipeline/runs" / context.run_id / "superseded").glob(
                "*/A/a.txt"
            )
        )
        self.assertTrue(archived)
        self.assertEqual(archived[0].read_text(encoding="utf-8"), "partial")

    def test_status_rejects_stale_body_hash_record(self) -> None:
        store, state_file, context, graph = self.make_graph()
        graph.resume(context, state_file)
        context.write_text("draft.annotated.md", "before")
        context.write_text("draft.md", "derived")
        context.write_json(
            "verification.json",
            {
                "draft_annotated_sha256": store.hash(
                    Path("runs") / context.run_id / "draft.annotated.md"
                ),
                "draft_sha256": store.hash(Path("runs") / context.run_id / "draft.md"),
            },
        )
        context.write_text("draft.annotated.md", "after")
        with self.assertRaisesRegex(PipelineError, "検証結果は無効"):
            graph.verify_status(context, state_file)
