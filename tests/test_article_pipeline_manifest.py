from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.article_pipeline import PipelineError
from scripts.article_pipeline.acquire import utc_now
from scripts.article_pipeline.graph import PipelineGraph, StageContext, build_production_stages
from scripts.article_pipeline.net import FetchResult
from scripts.article_pipeline.state import StateFile, initial_state
from scripts.article_pipeline.store import RunStore
from tests.article_pipeline_helpers import CONFIG, RepoCase


class FakeClient:
    def __init__(self, source_body=b"fixed material long enough"):
        self.source_body = source_body
        self.calls = []

    def fetch(self, url, **_kwargs):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            status, body, content_type = 404, b"", "text/plain; charset=utf-8"
        else:
            status, body, content_type = 200, self.source_body, "text/plain; charset=utf-8"
        return FetchResult(
            url=url, final_url=url, redirects=[], resolved_ip="93.184.216.34",
            http_status=status, headers={"content-type": content_type}, body=body,
            attempts=[{"result": "ok"}],
        )


class TestManifestRecovery(RepoCase):
    def setUp(self):
        super().setUp()
        self.config = json.loads(CONFIG)
        self.store = RunStore(self.root)
        self.graph = PipelineGraph(build_production_stages())
        self.run_id = "cand_20261004T000000Z_sample_error_abcd"
        self.topic = self.write_topic()
        self.candidates = self.root / "run/article_pipeline/inbox/candidates.yml"
        self.candidates.write_text(
            "schema: url_candidates/v1\ncandidates:\n"
            "  - url: https://example.com/docs\n"
            "    role_hint: official_doc\n",
            encoding="utf-8",
        )
        self.store.mkdir(Path("runs") / self.run_id, exclusive=True)
        self.state_file = StateFile(self.store, self.run_id)
        self.state_file.write(
            initial_state(
                run_id=self.run_id, slug="sample_error", mode="candidate",
                topic_source=self.topic, url_candidates_source=self.candidates,
                stage_names=self.graph.stage_names,
            )
        )
        self.context = StageContext(self.root, self.store, self.run_id, self.config)
        self.graph.resume(self.context, self.state_file, through="S1_plan")

    @property
    def run_root(self):
        return Path("runs") / self.run_id

    def finish_s2(self, body=b"fixed material long enough"):
        self.context.cache["network_client"] = FakeClient(body)
        return self.graph.resume(self.context, self.state_file, through="S2_sources")

    def test_manifest_modified_missing_extra_stop_resume_status_and_accept(self):
        self.finish_s2()
        text = self.run_root / "sources/S001/text.txt"
        self.store.write_text(text, "human modification")
        before_state = self.store.read_bytes(self.run_root / "state.json")
        before_tree = self.store.inspect_tree(self.run_root / "sources")

        for operation in (
            lambda: self.graph.resume(self.context, self.state_file, through="S2_sources"),
            lambda: self.graph.verify_status(self.context, self.state_file),
            lambda: self.graph.resume(
                self.context, self.state_file, through="S2_sources",
                accept_modified=["sources/index.json"],
            ),
        ):
            with pytest.raises(PipelineError, match="S001/text.txt|復旧コマンド"):
                operation()
            assert self.store.read_bytes(self.run_root / "state.json") == before_state
            assert self.store.inspect_tree(self.run_root / "sources") == before_tree

        # Each kind is reported with the affected name.
        self.store.write_bytes(self.run_root / "sources/extra.bin", b"extra")
        with pytest.raises(PipelineError, match="extra.bin"):
            self.graph.verify_status(self.context, self.state_file)
        self.store.remove(self.run_root / "sources/extra.bin")
        self.store.remove(text)
        with pytest.raises(PipelineError, match="S001/text.txt"):
            self.graph.verify_status(self.context, self.state_file)

    def test_refetch_failed_does_not_move_corrupt_sources_but_all_quarantines(self):
        self.finish_s2(b"original exact bytes")
        text = self.run_root / "sources/S001/text.txt"
        self.store.write_bytes(text, b"corrupt exact bytes")
        before = self.store.read_bytes(text)
        with pytest.raises(PipelineError, match="--refetch all"):
            self.graph.resume(
                self.context, self.state_file, through="S2_sources",
                from_stage="S2_sources", refetch="failed",
            )
        assert self.store.read_bytes(text) == before
        assert not self.store.exists(self.run_root / "superseded")

        self.context.cache["network_client"] = FakeClient(b"replacement material")
        state = self.graph.resume(
            self.context, self.state_file, through="S2_sources",
            from_stage="S2_sources", refetch="all",
        )
        record = state["stages"]["S2_sources"]
        report = self.store.read_json(self.run_root / record["recovery_report"])
        assert report["quarantined"] is True
        issue = next(item for item in report["issues"] if item["path"] == "S001/text.txt")
        assert issue["expected"].startswith("sha256:")
        assert issue["actual"].startswith("sha256:")
        archived = self.run_root / record["superseded_dir"] / "sources/S001/text.txt"
        assert self.store.read_bytes(archived) == before
        assert self.store.read_bytes(text) == b"replacement material"
        assert "pending_recovery" not in state

    def test_upstream_corruption_is_never_recovered_by_refetch_all(self):
        self.finish_s2()
        topic = self.run_root / "topic.json"
        self.store.write_text(topic, "{}")
        sources_before = self.store.inspect_tree(self.run_root / "sources")
        with pytest.raises(PipelineError, match="topic.json"):
            self.graph.resume(
                self.context, self.state_file, through="S2_sources",
                from_stage="S2_sources", refetch="all",
            )
        assert self.store.inspect_tree(self.run_root / "sources") == sources_before

    def test_pending_recovery_resumes_after_source_tree_was_already_moved(self):
        self.finish_s2(b"original long enough")
        text = self.run_root / "sources/S001/text.txt"
        self.store.write_bytes(text, b"damaged")
        original_move_tree = self.store.move_tree
        raised = False

        def move_then_interrupt(source, destination):
            nonlocal raised
            value = original_move_tree(source, destination)
            if not raised:
                raised = True
                raise RuntimeError("simulated power loss after rename")
            return value

        with patch.object(self.store, "move_tree", side_effect=move_then_interrupt):
            with pytest.raises(RuntimeError, match="power loss"):
                self.graph.resume(
                    self.context, self.state_file, through="S2_sources",
                    from_stage="S2_sources", refetch="all",
                )
        pending_state = self.state_file.read()
        assert "pending_recovery" in pending_state
        planned = pending_state["pending_recovery"]["planned"]
        assert not self.store.exists(planned[0]["source"])
        assert self.store.exists(planned[0]["destination"])
        with pytest.raises(PipelineError, match="pending_recovery"):
            self.graph.verify_status(self.context, self.state_file)
        with pytest.raises(PipelineError, match="未完了の復旧"):
            self.graph.resume(self.context, self.state_file, through="S2_sources")

        self.context.cache["network_client"] = FakeClient(b"fresh after resume")
        state = self.graph.resume(
            self.context, self.state_file, through="S2_sources",
            from_stage="S2_sources", refetch="all",
        )
        assert "pending_recovery" not in state
        assert self.store.read_bytes(self.run_root / "sources/S001/text.txt") == b"fresh after resume"
        assert self.store.exists(planned[0]["destination"])

    def test_interrupted_staging_and_atomic_temp_are_archived_then_rebuilt(self):
        staging = self.run_root / "sources.staging"
        self.store.mkdir(staging)
        self.store.write_bytes(staging / "S001/responses/01.bin", b"partial")
        # Simulate the temporary name left by an abrupt process termination.
        temp_relative = staging / "S001/.text.txt.fixed.tmp"
        temp_absolute = self.store.path(temp_relative)
        temp_absolute.parent.mkdir(parents=True, exist_ok=True)
        temp_absolute.write_bytes(b"temporary exact")
        before = self.store.inspect_tree(staging)
        state = self.state_file.read()
        parts = self.graph.input_parts(self.graph.by_name["S2_sources"], self.context, state)
        state = self.state_file.transition(
            state, "S2_sources", "running", attempts=1,
            stage_version=1, input_parts=parts,
            input_fingerprint=self.graph.fingerprint(parts), started_at=utc_now(),
        )

        self.context.cache["network_client"] = FakeClient(b"complete after interruption")
        state = self.graph.resume(self.context, self.state_file, through="S2_sources")
        superseded = self.run_root / state["stages"]["S2_sources"]["superseded_dir"]
        archived_staging = superseded / "sources.staging"
        assert self.store.inspect_tree(archived_staging) == before
        note = self.store.read_json(superseded / "archive_note.json")
        assert note["reason"] == "interrupted"
        assert any(item["path"].endswith(".text.txt.fixed.tmp") for item in note["inventory"])
        assert not self.store.exists(staging)
        assert not any(".tmp" in item["path"] for item in self.store.inspect_tree(self.run_root / "sources"))

    def test_completed_staging_before_rename_is_also_archived(self):
        staging = self.run_root / "sources.staging"
        self.store.mkdir(staging)
        self.store.write_json(staging / "index.json", {"members": []})
        state = self.state_file.read()
        parts = self.graph.input_parts(self.graph.by_name["S2_sources"], self.context, state)
        self.state_file.transition(
            state, "S2_sources", "running", attempts=1,
            stage_version=1, input_parts=parts,
            input_fingerprint=self.graph.fingerprint(parts), started_at=utc_now(),
        )
        self.context.cache["network_client"] = FakeClient()
        state = self.graph.resume(self.context, self.state_file, through="S2_sources")
        superseded = self.run_root / state["stages"]["S2_sources"]["superseded_dir"]
        assert self.store.exists(superseded / "sources.staging/index.json")
        assert not self.store.exists(staging)

    def test_windows_directory_rename_preserves_inventory(self):
        source = self.run_root / "windows-source"
        destination = self.run_root / "windows-destination"
        self.store.mkdir(source)
        self.store.write_bytes(source / "nested/file.bin", b"windows move bytes")
        before = self.store.inspect_tree(source)
        returned = self.store.move_tree(source, destination)
        assert returned == before
        assert not self.store.exists(source)
        assert self.store.inspect_tree(destination) == before

    def test_clean_refetch_failed_archives_whole_tree_and_reuses_success(self):
        first = self.finish_s2(b"stable fetched material")
        old = self.store.read_json(self.run_root / "sources/index.json")["sources"][0]
        old_fetched_at = old["fetched_at"]
        old_inventory = self.store.inspect_tree(self.run_root / "sources")
        # No request is expected: the clean, fresh successful source must be reused.
        no_fetch = FakeClient(b"must not be fetched")
        self.context.cache["network_client"] = no_fetch
        state = self.graph.resume(
            self.context, self.state_file, through="S2_sources",
            from_stage="S2_sources", refetch="failed",
        )
        current_index = self.store.read_json(self.run_root / "sources/index.json")
        current = current_index["sources"][0]
        assert current["status"] == "reused"
        assert current["fetched_at"] == old_fetched_at
        assert no_fetch.calls == []
        assert current_index["robots"]
        superseded = self.run_root / state["stages"]["S2_sources"]["superseded_dir"] / "sources"
        assert self.store.inspect_tree(superseded) == old_inventory
        assert not any(item["path"].startswith("old/") for item in self.store.inspect_tree(self.run_root / "sources"))

    def test_recovery_archives_human_edited_downstream_output_and_invalidates_descendants(self):
        self.finish_s2(b"source before corruption")
        draft = self.run_root / "draft.annotated.md"
        human_bytes = b"human edited draft exact bytes\r\n"
        self.store.write_bytes(draft, human_bytes)
        self.store.write_bytes(self.run_root / "sources/S001/text.txt", b"corrupt source")
        self.context.cache["network_client"] = FakeClient(b"fresh source material")
        state = self.graph.resume(
            self.context, self.state_file, through="S2_sources",
            from_stage="S2_sources", refetch="all",
        )
        s2 = state["stages"]["S2_sources"]
        report = self.store.read_json(self.run_root / s2["recovery_report"])
        planned_draft = next(
            item for item in report["planned"] if item["source"].endswith("draft.annotated.md")
        )
        assert self.store.read_bytes(planned_draft["destination"]) == human_bytes
        recorded = report["inventories"]["S4_write"]
        assert any(item["sha256"] for item in recorded if item["path"] == "draft.annotated.md")
        for name in ("S3_claims", "S4_write", "S5_code", "S6_verify", "S7_verdict"):
            assert state["stages"][name]["status"] == "invalidated"
