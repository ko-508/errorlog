import argparse
import contextlib
from datetime import datetime, timezone
from decimal import Decimal
import io
import json
from pathlib import Path
import shutil
from unittest.mock import patch

import pytest

from scripts.article_pipeline import PipelineError
from scripts.article_pipeline.__main__ import build_parser, command_new, main
from scripts.article_pipeline.budget import BudgetLedger, checked_record
from scripts.article_pipeline.graph import ArtifactSpec, PipelineGraph, StageContext, StageSpec, build_production_stages
from scripts.article_pipeline.llm_client import LlmApiError, LlmClient
from scripts.article_pipeline.llm_calls import LlmCallManager, attempt_key
from scripts.article_pipeline.state import StateFile, initial_state
from scripts.article_pipeline.store import RunStore, canonical_json_bytes, sha256_bytes
from tests.article_pipeline_helpers import CONFIG, RepoCase, article_text
from tests.test_article_pipeline_cli_p2 import FixedClient
from tests.test_article_pipeline_claims_extract import Responses, extracted_output


class ValidationResponses:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def count_input_tokens(self, request, *, timeout):
        return {"input_tokens": 100}

    def create_response(self, request, *, timeout):
        self.requests.append(request)
        response = dict(self.responses.pop(0))
        response.setdefault("id", f"resp_{len(self.requests)}")
        return response

    def retrieve_response(self, response_id, *, timeout):
        raise AssertionError("retrieve not expected")

    def cancel_response(self, response_id, *, timeout):
        raise AssertionError("cancel not expected")


class RecoveryTransport:
    def __init__(self, output, *, fail_create=False):
        self.requests = []
        self.retrievals = []
        self.fail_create = fail_create
        self.response = {
            "id": "resp_recovery",
            "status": "completed",
            "output_text": json.dumps(output, ensure_ascii=False),
            "usage": {
                "input_tokens": 100,
                "output_tokens": 20,
                "input_tokens_details": {
                    "cached_tokens": 0,
                    "cache_write_tokens": 0,
                },
            },
        }

    def count_input_tokens(self, request, *, timeout):
        return {"input_tokens": 100}

    def create_response(self, request, *, timeout):
        self.requests.append(request)
        if self.fail_create:
            raise LlmApiError("create", "injected disconnect")
        return dict(self.response)

    def retrieve_response(self, response_id, *, timeout):
        self.retrievals.append(response_id)
        return dict(self.response)

    def cancel_response(self, response_id, *, timeout):
        raise AssertionError("cancel not expected")


class RejectedTransport:
    def __init__(self, status_code=400, code="bad_request"):
        self.status_code = status_code
        self.code = code
        self.requests = []

    def count_input_tokens(self, request, *, timeout):
        return {"input_tokens": 100}

    def create_response(self, request, *, timeout):
        self.requests.append(request)
        raise LlmApiError(
            "create", "rejected", status_code=self.status_code, code=self.code,
        )

    def retrieve_response(self, response_id, *, timeout):
        raise AssertionError("retrieve not expected")

    def cancel_response(self, response_id, *, timeout):
        raise AssertionError("cancel not expected")


def test_parser_exposes_p3_stages_and_management_commands():
    parser = build_parser()
    assert parser.parse_args(["resume", "--run", "r", "--through", "S3_claims"]).through == "S3_claims"
    args = parser.parse_args(["resume", "--run", "r", "--through", "S3_support", "--retry-unknown-llm-calls"])
    assert args.through == "S3_support" and args.retry_unknown_llm_calls is True
    assert parser.parse_args(["claims", "--run", "r", "--show", "C001"]).show == "C001"
    assert parser.parse_args(["llm", "calls", "--run", "r"]).llm_command == "calls"
    assert parser.parse_args(["budget", "check", "--apply"]).apply is True
    assert parser.parse_args(["unlock", "--budget", "--yes"]).budget is True


class TestP3Graph(RepoCase):
    run_id = "cand_20261005T000000Z_sample_error_abcd"

    def old_state(self):
        store = RunStore(self.root); store.mkdir(Path("runs") / self.run_id, exclusive=True)
        old = ["S0_intake", "S1_plan", "S2_sources", "S3_claims", "S4_write", "S5_code", "S6_verify", "S7_verdict"]
        state = initial_state(run_id=self.run_id, slug="sample_error", mode="candidate", topic_source=self.write_topic(), stage_names=old)
        state_file = StateFile(store, self.run_id); state_file.write(state)
        return store, state_file, state

    def test_p2_state_adds_support_pending_in_the_correct_position(self):
        store, state_file, _state = self.old_state()
        graph = PipelineGraph(build_production_stages())
        migrated = graph.verify_status(StageContext(self.root, store, self.run_id, {}), state_file)
        assert list(migrated["stages"])[3:6] == ["S3_claims", "S3_support", "S4_write"]
        assert migrated["stages"]["S3_support"] == {"status": "pending", "attempts": 0}

    def test_p2_state_with_later_done_or_old_claims_done_stops(self):
        for stage in ("S3_claims", "S4_write"):
            with self.subTest(stage=stage):
                self.tearDown(); self.setUp()
                store, state_file, state = self.old_state()
                state["stages"][stage]["status"] = "done"
                state_file.write(state)
                with self.assertRaises(PipelineError):
                    PipelineGraph(build_production_stages()).verify_status(StageContext(self.root, store, self.run_id, {}), state_file)

    def test_claim_outputs_cannot_be_accepted_as_human_edits(self):
        store = RunStore(self.root); store.mkdir(Path("runs") / self.run_id, exclusive=True)
        def runner(context, _state): context.write_text("claims.json", "original")
        graph = PipelineGraph([StageSpec("S3_support", 1, artifacts=(ArtifactSpec("claims.json"),), runner=runner)])
        state_file = StateFile(store, self.run_id)
        state_file.write(initial_state(run_id=self.run_id, slug="sample_error", mode="candidate", topic_source=self.write_topic(), stage_names=graph.stage_names))
        context = StageContext(self.root, store, self.run_id, {})
        graph.resume(context, state_file)
        context.write_text("claims.json", "changed")
        with self.assertRaisesRegex(PipelineError, "受け入れられません"):
            graph.resume(context, state_file, through="S3_support", accept_modified=("claims.json",))

    def test_format_only_candidate_change_skips_s1_and_keeps_s2_done(self):
        topic = self.write_topic()
        candidates = self.root / "run/article_pipeline/inbox/candidates.yml"
        candidates.write_text(
            "schema: url_candidates/v1\ncandidates:\n"
            "- url: https://example.com/docs\n  role_hint: official_doc\n",
            encoding="utf-8",
        )
        command_new(argparse.Namespace(topic=str(topic), mode="candidate", new_run=False, url_candidates=str(candidates)), self.root)
        run_id = next((self.root / "run/article_pipeline/runs").iterdir()).name
        store = RunStore(self.root); graph = PipelineGraph(build_production_stages())
        context = StageContext(self.root, store, run_id, json.loads(CONFIG), {"network_client": FixedClient()})
        state_file = StateFile(store, run_id)
        before = graph.resume(context, state_file, through="S2_sources")
        s1_attempts = before["stages"]["S1_plan"]["attempts"]
        candidates.write_text(
            "# formatting only\nschema: url_candidates/v1\ncandidates:\n"
            "  - role_hint: official_doc\n    url: https://example.com/docs\n",
            encoding="utf-8",
        )
        after = graph.resume(StageContext(self.root, store, run_id, json.loads(CONFIG)), state_file, through="S1_plan")
        assert after["stages"]["S1_plan"]["attempts"] == s1_attempts
        assert after["stages"]["S2_sources"]["status"] == "done"

    def test_claims_record_hash_mismatch_stops_status(self):
        store, state_file, state = self.old_state()
        state = PipelineGraph(build_production_stages())._migrate_state(state_file, state)
        context = StageContext(self.root, store, self.run_id, {})
        context.write_text("sources/index.json", "source")
        context.write_text("claims.extracted.json", "extract")
        context.write_json("claims.json", {
            "sources_index_sha256": "sha256:wrong",
            "claims_extracted_sha256": store.hash(context.artifact_relative("claims.extracted.json")),
        })
        with self.assertRaisesRegex(PipelineError, "判定結果は無効"):
            PipelineGraph(build_production_stages())._verify_body_hash_records(context)

    def test_cli_from_claims_archives_outputs_but_reuses_llm_journal(self):
        config = json.loads(CONFIG)
        config["llm"]["store"] = False
        config["llm"]["pricing"]["max_age_days"] = 3650
        config["llm"]["pricing"]["models"]["test-model"]["checked_at"] = (
            datetime.now(timezone.utc).date().isoformat()
        )
        config["budget"] = {
            "monthly_limit_usd": 10,
            "run_limit_usd": 5,
            "call_limit_usd": 2,
        }
        config["claims"]["extract"].update(
            model="test-model",
            reasoning_effort="low",
            max_output_tokens=1000,
            expected_output_tokens=200,
            max_input_tokens_per_call=1000,
        )
        config["claims"]["support"].update(
            model="test-model",
            reasoning_effort="low",
            max_output_tokens=1000,
            expected_output_tokens=200,
        )
        config["claims"]["source_types"]["official_doc_hosts"] = ["example.com"]
        (self.root / "config/openai_article_pipeline.yml").write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        repository = Path(__file__).parents[1]
        for relative in (
            "config/prompts/s3_extract.v1.md",
            "config/prompts/s3_support.v1.md",
            "config/schemas/claims_extract.v1.json",
            "config/schemas/claims_support.v2.json",
        ):
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(repository / relative, destination)

        topic = self.write_topic()
        candidates = self.root / "run/article_pipeline/inbox/candidates.yml"
        candidates.write_text(
            "schema: url_candidates/v1\ncandidates:\n"
            "- {url: https://example.com/docs, role_hint: official_doc}\n",
            encoding="utf-8",
        )
        assert command_new(
            argparse.Namespace(
                topic=str(topic), mode="candidate", new_run=False,
                url_candidates=str(candidates),
            ),
            self.root,
        ) == 0
        run_id = next((self.root / "run/article_pipeline/runs").iterdir()).name

        extracted = {
            "claims": [{
                "temp_id": "x1",
                "kind": "message_text",
                "text": "Sample connection error が表示される",
                "subject": {
                    "message_literal": "Sample connection error",
                    "identifier": None,
                    "value": None,
                    "version": None,
                    "other_error": None,
                },
                "evidence": [{
                    "source_id": "S001",
                    "role": "statement",
                    "quote": "Sample connection error",
                }],
                "version_scope": None,
            }],
            "instruction_like_text": [],
        }
        supported = {
            "judgements": [{
                "claim_id": "C001",
                "basis_code": "MT-DOC",
                "evidence_assessment": [{
                    "evidence_index": 0,
                    "function": "documents_message",
                    "reason": "公式文書がメッセージを記載している",
                }],
                "link_confirmed": None,
                "support": "supported",
                "contradicted": False,
                "reason": "引用が主張を裏付ける",
                "missing": [],
            }],
        }
        transport = Responses([extracted, supported])
        llm_client = LlmClient(transport)
        store = RunStore(self.root)
        graph = PipelineGraph(build_production_stages())
        context = StageContext(
            self.root,
            store,
            run_id,
            config,
            {
                "network_client": FixedClient(
                    body=b"Sample connection error is documented here.\n"
                ),
                "llm_client": llm_client,
            },
        )
        state_file = StateFile(store, run_id)
        completed = graph.resume(context, state_file, through="S3_support")
        assert completed["stages"]["S3_claims"]["status"] == "done"
        assert completed["stages"]["S3_support"]["status"] == "done"

        run_root = Path("runs") / run_id
        original_outputs = {
            name: store.read_bytes(run_root / name)
            for name in ("claims.extracted.json", "claims.json", "sufficiency.json")
        }
        journal = run_root / "llm_journal"
        journal_before = store.inspect_tree(journal)
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        ledger = BudgetLedger(store, config)

        def counts():
            events = ledger.read_events(month)
            return {
                "create": len(transport.requests),
                "reserve": sum(event["event"] == "reserve" for event in events),
                "settle": sum(event["event"] == "settle" for event in events),
            }

        assert counts() == {"create": 2, "reserve": 2, "settle": 2}

        def resume_from_claims():
            with (
                patch("scripts.article_pipeline.__main__.repo_root", return_value=self.root),
                patch("scripts.article_pipeline.claims_extract.LlmClient", return_value=llm_client),
                patch("scripts.article_pipeline.claims_support.LlmClient", return_value=llm_client),
            ):
                assert main([
                    "resume", "--run", run_id,
                    "--from", "S3_claims", "--through", "S3_support",
                ]) == 0

        resume_from_claims()
        first_outputs = {
            name: store.read_bytes(run_root / name)
            for name in ("claims.extracted.json", "claims.json", "sufficiency.json")
        }
        assert store.read_json(run_root / "claims.extracted.json")["calls"][0]["reused_from_journal"] is True
        assert store.read_json(run_root / "claims.json")["calls"][0]["reused_from_journal"] is True
        first_state = state_file.read()
        assert first_state["stages"]["S3_claims"]["status"] == "done"
        assert first_state["stages"]["S3_support"]["status"] == "done"
        assert store.inspect_tree(journal) == journal_before
        assert counts() == {"create": 2, "reserve": 2, "settle": 2}

        superseded = store.path(run_root / "superseded")
        claim_archives = sorted(superseded.glob("*/S3_claims/claims.extracted.json"))
        support_archives = sorted(superseded.glob("*/S3_support/claims.json"))
        sufficiency_archives = sorted(superseded.glob("*/S3_support/sufficiency.json"))
        assert len(claim_archives) == len(support_archives) == len(sufficiency_archives) == 1
        assert claim_archives[0].read_bytes() == original_outputs["claims.extracted.json"]
        assert support_archives[0].read_bytes() == original_outputs["claims.json"]
        assert sufficiency_archives[0].read_bytes() == original_outputs["sufficiency.json"]
        assert list(superseded.rglob("llm_journal")) == []

        resume_from_claims()
        assert store.read_json(run_root / "claims.extracted.json")["calls"][0]["reused_from_journal"] is True
        assert store.read_json(run_root / "claims.json")["calls"][0]["reused_from_journal"] is True
        second_state = state_file.read()
        assert second_state["stages"]["S3_claims"]["status"] == "done"
        assert second_state["stages"]["S3_support"]["status"] == "done"
        assert store.inspect_tree(journal) == journal_before
        assert counts() == {"create": 2, "reserve": 2, "settle": 2}

        claim_archives = sorted(superseded.glob("*/S3_claims/claims.extracted.json"))
        support_archives = sorted(superseded.glob("*/S3_support/claims.json"))
        sufficiency_archives = sorted(superseded.glob("*/S3_support/sufficiency.json"))
        assert len(claim_archives) == len(support_archives) == len(sufficiency_archives) == 2
        assert any(path.read_bytes() == first_outputs["claims.extracted.json"] for path in claim_archives)
        assert any(path.read_bytes() == first_outputs["claims.json"] for path in support_archives)
        assert any(path.read_bytes() == first_outputs["sufficiency.json"] for path in sufficiency_archives)
        assert list(superseded.rglob("llm_journal")) == []

    def _validation_cli_run(self, *, mode="candidate"):
        config = json.loads(CONFIG)
        config["llm"]["store"] = False
        config["llm"]["pricing"]["max_age_days"] = 3650
        config["llm"]["pricing"]["models"]["test-model"]["checked_at"] = (
            datetime.now(timezone.utc).date().isoformat()
        )
        config["budget"] = {
            "monthly_limit_usd": 10,
            "run_limit_usd": 5,
            "call_limit_usd": 2,
        }
        config["claims"]["extract"].update(
            model="test-model",
            reasoning_effort="low",
            max_output_tokens=1000,
            expected_output_tokens=200,
            max_input_tokens_per_call=1000,
        )
        config["claims"]["support"].update(
            model="test-model",
            reasoning_effort="low",
            max_output_tokens=1000,
            expected_output_tokens=200,
        )
        config["claims"]["source_types"]["official_doc_hosts"] = ["example.com"]
        (self.root / "config/openai_article_pipeline.yml").write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        repository = Path(__file__).parents[1]
        for relative in (
            "config/prompts/s3_extract.v1.md",
            "config/prompts/s3_support.v1.md",
            "config/schemas/claims_extract.v1.json",
            "config/schemas/claims_support.v2.json",
        ):
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(repository / relative, destination)

        if mode == "comparison":
            self.write_post()
        topic = self.write_topic()
        candidates = self.root / "run/article_pipeline/inbox/candidates.yml"
        candidates.write_text(
            "schema: url_candidates/v1\ncandidates:\n"
            "- {url: https://example.com/docs, role_hint: official_doc}\n",
            encoding="utf-8",
        )
        assert command_new(
            argparse.Namespace(
                topic=str(topic), mode=mode, new_run=False,
                url_candidates=str(candidates),
            ),
            self.root,
        ) == 0
        run_id = next((self.root / "run/article_pipeline/runs").iterdir()).name
        store = RunStore(self.root)
        graph = PipelineGraph(build_production_stages())
        context = StageContext(
            self.root,
            store,
            run_id,
            config,
            {"network_client": FixedClient(body=b"E100 happens when the socket closes\n")},
        )
        graph.resume(context, StateFile(store, run_id), through="S2_sources")
        return config, store, run_id

    @staticmethod
    def _completed_validation_response(*, output=None, refusal=False):
        response = {
            "status": "completed",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 20,
                "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
            },
        }
        if refusal:
            response["output"] = [{
                "type": "message",
                "content": [{"type": "refusal", "refusal": "safety refusal"}],
            }]
        else:
            response["output_text"] = json.dumps(output, ensure_ascii=False)
        return response

    @staticmethod
    def _valid_support_output():
        return {"judgements": [{
            "claim_id": "C001",
            "basis_code": "CA-DOC",
            "evidence_assessment": [{
                "evidence_index": 0,
                "function": "states_cause",
                "reason": "原因を直接述べている",
            }],
            "link_confirmed": None,
            "support": "supported",
            "contradicted": False,
            "reason": "引用が主張を裏付ける",
            "missing": [],
        }]}

    def _validation_resume(self, run_id, stage, client):
        stdout = io.StringIO()
        stderr = io.StringIO()
        target = (
            "scripts.article_pipeline.claims_extract.LlmClient"
            if stage == "S3_claims"
            else "scripts.article_pipeline.claims_support.LlmClient"
        )
        with (
            patch("scripts.article_pipeline.__main__.repo_root", return_value=self.root),
            patch(target, return_value=client),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = main(["resume", "--run", run_id, "--through", stage])
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def _complete_p3_cli_run(self):
        config, store, run_id = self._validation_cli_run()
        extract_transport = Responses([extracted_output()])
        code, _stdout, stderr = self._validation_resume(
            run_id, "S3_claims", LlmClient(extract_transport)
        )
        assert code == 0, stderr
        support_transport = Responses([self._valid_support_output()])
        code, _stdout, stderr = self._validation_resume(
            run_id, "S3_support", LlmClient(support_transport)
        )
        assert code == 0, stderr
        return config, store, run_id, extract_transport, support_transport

    def test_cli_rejects_accept_modified_for_each_claim_artifact(self):
        for artifact in (
            "claims.extracted.json", "claims.json", "sufficiency.json"
        ):
            with self.subTest(artifact=artifact):
                self.tearDown()
                self.setUp()
                _config, store, run_id, _extract, _support = (
                    self._complete_p3_cli_run()
                )
                relative = Path("runs") / run_id / artifact
                store.write_bytes(relative, store.read_bytes(relative) + b"\n")
                exit_code, _stdout, stderr = self._reconcile_cli([
                    "resume", "--run", run_id,
                    "--through", "S3_support",
                    "--accept-modified", artifact,
                ])
                assert exit_code == 1
                assert "受け入れられません" in stderr

    def test_cli_status_and_resume_migrate_p2_state(self):
        for command in ("status", "resume"):
            with self.subTest(command=command):
                self.tearDown()
                self.setUp()
                _config, store, run_id = self._validation_cli_run()
                state_file = StateFile(store, run_id)
                state = state_file.read()
                state["stages"].pop("S3_support")
                state_file.write(state)
                arguments = [command, "--run", run_id]
                if command == "resume":
                    arguments.extend(["--through", "S2_sources"])
                exit_code, _stdout, stderr = self._reconcile_cli(arguments)
                assert exit_code == 0, stderr
                migrated = state_file.read()
                assert migrated["stages"]["S3_support"] == {
                    "status": "pending", "attempts": 0
                }
                assert list(migrated["stages"])[3:6] == [
                    "S3_claims", "S3_support", "S4_write"
                ]

    def test_cli_secret_is_absent_from_requests_outputs_and_all_saved_files(self):
        _config, store, run_id = self._validation_cli_run()
        secret = "sk-test-cli-secret-must-not-persist"
        transport = Responses([extracted_output()])
        with patch.dict("os.environ", {"OPENAI_API_KEY": secret}):
            code, stdout, stderr = self._validation_resume(
                run_id, "S3_claims", LlmClient(transport)
            )
        assert code == 0, stderr
        assert secret not in stdout
        assert secret not in stderr
        assert secret not in json.dumps(transport.requests, ensure_ascii=False)
        for path in store.root.rglob("*"):
            if path.is_file():
                assert secret.encode() not in path.read_bytes(), path

    def test_cli_stage_invalidation_follows_production_dependencies(self):
        config, store, run_id, _extract, _support = self._complete_p3_cli_run()
        state_file = StateFile(store, run_id)
        before = state_file.read()
        claims_attempts = before["stages"]["S3_claims"]["attempts"]
        support_attempts = before["stages"]["S3_support"]["attempts"]

        config["claims"]["support"]["context_lines"] += 1
        (self.root / "config/openai_article_pipeline.yml").write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        support_transport = Responses([self._valid_support_output()])
        code, _stdout, stderr = self._validation_resume(
            run_id, "S3_support", LlmClient(support_transport)
        )
        assert code == 0, stderr
        after_support = state_file.read()
        assert after_support["stages"]["S3_claims"]["attempts"] == claims_attempts
        assert after_support["stages"]["S3_support"]["attempts"] == support_attempts + 1
        assert len(support_transport.requests) == 0
        assert store.read_json(
            Path("runs") / run_id / "claims.json"
        )["calls"][0]["reused_from_journal"] is True

        changed_source = FixedClient(
            body=b"E100 changed source material after S2 refetch\n"
        )
        with patch(
            "scripts.article_pipeline.acquire.NetworkClient",
            return_value=changed_source,
        ):
            exit_code, _stdout, stderr = self._reconcile_cli([
                "resume", "--run", run_id,
                "--from", "S2_sources", "--through", "S2_sources",
                "--refetch", "all",
            ])
        assert exit_code == 0, stderr
        after_s2 = state_file.read()
        assert after_s2["stages"]["S2_sources"]["status"] == "done"
        assert after_s2["stages"]["S3_claims"]["status"] == "invalidated"
        assert after_s2["stages"]["S3_support"]["status"] == "invalidated"

    def test_comparison_article_is_absent_from_llm_request_and_git_status_is_stable(self):
        _config, _store, run_id = self._validation_cli_run(mode="comparison")
        before = self.git("status", "--porcelain")
        transport = Responses([extracted_output()])
        code, _stdout, stderr = self._validation_resume(
            run_id, "S3_claims", LlmClient(transport)
        )
        assert code == 0, stderr
        assert self.git("status", "--porcelain") == before
        request_text = transport.requests[0]["input"][0]["content"][0]["text"]
        assert article_text("sample_error") not in request_text
        state = StateFile(RunStore(self.root), run_id).read()
        assert state["mode"] == "comparison"
        assert state["publish_allowed"] is False

    @staticmethod
    def _stage_attempts(store, run_id, stage):
        root = store.path(Path("runs") / run_id / "llm_journal")
        records = []
        for path in root.glob("*/attempt-*.json"):
            if path.name.endswith(".response.json"):
                continue
            value = store.read_json(path.relative_to(store.root))
            if value.get("stage") == stage:
                records.append(value)
        return sorted(records, key=lambda value: value["attempt"])

    @staticmethod
    def _other_run_snapshot(store, ledger, path, record):
        approval = ledger.approval_path(
            record["ledger_month"], record["reservation_id"]
        )
        return {
            "approval": store.read_bytes(approval),
            "journal": store.read_bytes(path),
            "events": [
                event
                for event in ledger.read_events(record["ledger_month"])
                if event["reservation_id"] == record["reservation_id"]
            ],
        }

    def _interrupt_claims_call(self, stop, *, fail_create=False):
        config, store, run_id = self._validation_cli_run()
        transport = RecoveryTransport(
            extracted_output(), fail_create=fail_create
        )
        client = LlmClient(transport)
        graph = PipelineGraph(build_production_stages())
        context = StageContext(
            self.root,
            store,
            run_id,
            config,
            {"llm_client": client},
        )
        state_file = StateFile(store, run_id)
        if stop == "R6":
            with pytest.raises(PipelineError, match="結果が不明"):
                graph.resume(context, state_file, through="S3_claims")
        else:
            original_execute = LlmCallManager.execute

            def stop_call(manager, **kwargs):
                return original_execute(manager, **kwargs, stop_after=stop)

            with patch.object(LlmCallManager, "execute", new=stop_call):
                with pytest.raises(RuntimeError, match=stop):
                    graph.resume(context, state_file, through="S3_claims")
        records = self._stage_attempts(store, run_id, "S3_claims")
        assert len(records) == 1
        record = records[0]
        journal_path = (
            Path("runs") / run_id / "llm_journal" / record["logical_key"]
            / f"attempt-{record['attempt']}.json"
        )
        return (
            config,
            store,
            run_id,
            transport,
            client,
            journal_path,
            record,
        )

    def test_cli_repeated_resume_is_idempotent_at_pre_send_and_submitted_stops(self):
        for stop in ("R1", "R3", "R4", "R7"):
            with self.subTest(stop=stop):
                self.tearDown()
                self.setUp()
                (
                    config,
                    store,
                    run_id,
                    transport,
                    client,
                    journal_path,
                    record,
                ) = self._interrupt_claims_call(stop)
                ledger = BudgetLedger(store, config)
                other_path, other = self._add_other_approved_reservation(
                    store, ledger, f"other_run_{stop.lower()}", record
                )
                other_before = self._other_run_snapshot(
                    store, ledger, other_path, other
                )
                initial_creates = len(transport.requests)
                assert initial_creates == (1 if stop == "R7" else 0)
                assert len(transport.retrievals) == 0

                code, _stdout, stderr = self._validation_resume(
                    run_id, "S3_claims", client
                )
                assert code == 0, stderr
                assert len(transport.requests) == 1
                assert len(transport.retrievals) == (1 if stop == "R7" else 0)
                completed = store.read_json(journal_path)
                assert completed["state"] == "completed"
                response_path = journal_path.with_name("attempt-1.response.json")
                assert store.exists(response_path)
                target_events = [
                    event
                    for event in ledger.read_events(record["ledger_month"])
                    if event["reservation_id"] == record["reservation_id"]
                ]
                assert [event["event"] for event in target_events] == [
                    "reserve", "settle"
                ]
                assert len(self._stage_attempts(store, run_id, "S3_claims")) == 1
                approval_path = ledger.approval_path(
                    record["ledger_month"], record["reservation_id"]
                )
                approval_after = store.read_bytes(approval_path)
                journal_after = store.read_bytes(journal_path)
                response_after = store.read_bytes(response_path)
                all_events_after = ledger.read_events(record["ledger_month"])
                assert self._other_run_snapshot(
                    store, ledger, other_path, other
                ) == other_before

                for _repeat in range(2):
                    code, _stdout, stderr = self._validation_resume(
                        run_id, "S3_claims", client
                    )
                    assert code == 0, stderr
                    assert len(transport.requests) == 1
                    assert len(transport.retrievals) == (1 if stop == "R7" else 0)
                    assert len(self._stage_attempts(store, run_id, "S3_claims")) == 1
                    assert store.read_bytes(approval_path) == approval_after
                    assert store.read_bytes(journal_path) == journal_after
                    assert store.read_bytes(response_path) == response_after
                    assert ledger.read_events(record["ledger_month"]) == all_events_after
                    assert self._other_run_snapshot(
                        store, ledger, other_path, other
                    ) == other_before

    def test_cli_repeated_resume_never_resends_reserved_or_unknown_outcome(self):
        for stop in ("R5", "R6"):
            with self.subTest(stop=stop):
                self.tearDown()
                self.setUp()
                (
                    config,
                    store,
                    run_id,
                    transport,
                    client,
                    journal_path,
                    record,
                ) = self._interrupt_claims_call(
                    stop, fail_create=(stop == "R6")
                )
                ledger = BudgetLedger(store, config)
                other_path, other = self._add_other_approved_reservation(
                    store, ledger, f"other_run_{stop.lower()}", record
                )
                other_before = self._other_run_snapshot(
                    store, ledger, other_path, other
                )
                creates_before = len(transport.requests)
                assert creates_before == (1 if stop == "R6" else 0)

                stable = None
                for _resume in range(3):
                    code, _stdout, stderr = self._validation_resume(
                        run_id, "S3_claims", client
                    )
                    assert code == 1
                    assert "自動再送しません" in stderr
                    assert len(transport.requests) == creates_before
                    assert len(transport.retrievals) == 0
                    current = store.read_json(journal_path)
                    assert current["state"] == "unknown_outcome"
                    target_events = [
                        event
                        for event in ledger.read_events(record["ledger_month"])
                        if event["reservation_id"] == record["reservation_id"]
                    ]
                    assert [event["event"] for event in target_events] == [
                        "reserve", "outcome_unknown"
                    ]
                    assert len(self._stage_attempts(store, run_id, "S3_claims")) == 1
                    current_snapshot = {
                        "approval": store.read_bytes(ledger.approval_path(
                            record["ledger_month"], record["reservation_id"]
                        )),
                        "journal": store.read_bytes(journal_path),
                        "events": target_events,
                    }
                    if stable is None:
                        stable = current_snapshot
                    else:
                        assert current_snapshot == stable
                    assert self._other_run_snapshot(
                        store, ledger, other_path, other
                    ) == other_before

    def test_cli_repeated_resume_after_r2_rejection_keeps_same_attempt(self):
        config, store, run_id = self._validation_cli_run()
        config["budget"]["call_limit_usd"] = 0.0001
        (self.root / "config/openai_article_pipeline.yml").write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        transport = RecoveryTransport(extracted_output())
        client = LlmClient(transport)
        graph = PipelineGraph(build_production_stages())
        context = StageContext(
            self.root, store, run_id, config, {"llm_client": client}
        )
        original_execute = LlmCallManager.execute

        def stop_after_rejection(manager, **kwargs):
            return original_execute(manager, **kwargs, stop_after="R2x")

        with patch.object(LlmCallManager, "execute", new=stop_after_rejection):
            with pytest.raises(RuntimeError, match="R2"):
                graph.resume(
                    context, StateFile(store, run_id), through="S3_claims"
                )
        record = self._stage_attempts(store, run_id, "S3_claims")[0]
        journal_path = (
            Path("runs") / run_id / "llm_journal" / record["logical_key"]
            / "attempt-1.json"
        )
        ledger = BudgetLedger(store, config)
        high_limits = json.loads(json.dumps(config))
        high_limits["budget"] = {
            "monthly_limit_usd": 10,
            "run_limit_usd": 5,
            "call_limit_usd": 2,
        }
        other_ledger = BudgetLedger(store, high_limits)
        other_path, other = self._add_other_approved_reservation(
            store, other_ledger, "other_run_r2", record
        )
        other_before = self._other_run_snapshot(
            store, ledger, other_path, other
        )

        def assert_unapproved_check(expected_state):
            journal_before = store.read_bytes(journal_path)
            for command in (["budget", "check"], ["budget", "check", "--apply"]):
                code, stdout, stderr = self._reconcile_cli(command)
                assert code == 0, stderr
                actions = [
                    item for item in json.loads(stdout)["actions"]
                    if item.get("reservation_id") == record["reservation_id"]
                ]
                assert actions == [{
                    "action": "recheck_unapproved",
                    "judgment": "budget_exceeded",
                    "reservation_id": record["reservation_id"],
                }]
                assert store.read_json(journal_path)["state"] == expected_state
                assert store.read_bytes(journal_path) == journal_before
                assert not store.exists(ledger.approval_path(
                    record["ledger_month"], record["reservation_id"]
                ))
                assert not any(
                    event["reservation_id"] == record["reservation_id"]
                    for event in ledger.read_events(record["ledger_month"])
                )

        assert_unapproved_check("proposed")

        for resume_index in range(3):
            code, _stdout, stderr = self._validation_resume(
                run_id, "S3_claims", client
            )
            assert code == 1
            assert "budget_exceeded" in stderr
            attempts = self._stage_attempts(store, run_id, "S3_claims")
            assert len(attempts) == 1
            assert attempts[0]["attempt"] == 1
            assert attempts[0]["state"] == "budget_rejected"
            assert len(transport.requests) == 0
            assert len(transport.retrievals) == 0
            assert not store.exists(ledger.approval_path(
                record["ledger_month"], record["reservation_id"]
            ))
            assert not any(
                event["reservation_id"] == record["reservation_id"]
                for event in ledger.read_events(record["ledger_month"])
            )
            assert store.exists(journal_path)
            assert self._other_run_snapshot(
                store, ledger, other_path, other
            ) == other_before
            if resume_index == 0:
                assert_unapproved_check("budget_rejected")

    def test_cli_refusal_and_schema_invalid_retry_once_for_both_s3_stages(self):
        for stage in ("S3_claims", "S3_support"):
            for response_kind in ("refusal", "schema_invalid"):
                for second_valid in (True, False):
                    with self.subTest(
                        stage=stage,
                        response_kind=response_kind,
                        second_valid=second_valid,
                    ):
                        self.tearDown()
                        self.setUp()
                        config, store, run_id = self._validation_cli_run()
                        if stage == "S3_support":
                            extract_transport = Responses([extracted_output()])
                            code, _stdout, stderr = self._validation_resume(
                                run_id,
                                "S3_claims",
                                LlmClient(extract_transport),
                            )
                            assert code == 0, stderr
                            assert len(extract_transport.requests) == 1

                        def invalid_response():
                            if response_kind == "refusal":
                                return self._completed_validation_response(refusal=True)
                            return self._completed_validation_response(output={"unexpected": True})

                        valid_output = (
                            extracted_output()
                            if stage == "S3_claims"
                            else self._valid_support_output()
                        )
                        responses = [invalid_response()]
                        responses.append(
                            self._completed_validation_response(output=valid_output)
                            if second_valid else invalid_response()
                        )
                        transport = ValidationResponses(responses)
                        client = LlmClient(transport)
                        code, _stdout, stderr = self._validation_resume(run_id, stage, client)
                        assert code == (0 if second_valid else 1), stderr
                        assert len(transport.requests) == 2

                        attempts = self._stage_attempts(store, run_id, stage)
                        assert [record["attempt"] for record in attempts] == [1, 2]
                        assert all(record["state"] == "completed" for record in attempts)
                        assert "output_validation_error" in attempts[0]
                        assert ("output_validation_error" not in attempts[1]) is second_valid

                        ledger = BudgetLedger(store, config)
                        events = ledger.read_events(attempts[0]["ledger_month"])
                        stage_ids = {record["reservation_id"] for record in attempts}
                        stage_events = [
                            event for event in events
                            if event["reservation_id"] in stage_ids
                        ]
                        assert sum(event["event"] == "reserve" for event in stage_events) == 2
                        assert sum(event["event"] == "settle" for event in stage_events) == 2
                        for record in attempts:
                            assert Decimal(record["actual_usd"]) > 0
                            final = next(
                                event for event in stage_events
                                if event["reservation_id"] == record["reservation_id"]
                                and event["event"] == "settle"
                            )
                            assert final["actual_usd"] == record["actual_usd"]

                        artifact = Path("runs") / run_id / (
                            "claims.extracted.json" if stage == "S3_claims" else "claims.json"
                        )
                        if second_valid:
                            assert store.exists(artifact)
                            output = store.read_json(artifact)
                            assert output["calls"][0]["attempt"] == 2
                            if stage == "S3_support":
                                assert output["claims"][0]["status"] == "verified"
                        else:
                            expected = (
                                "LLM 応答に output_text がありません"
                                if response_kind == "refusal"
                                else (
                                    "claims_extract/v1 のキーが不正です"
                                    if stage == "S3_claims"
                                    else "claims_support/v2 の形式が不正です"
                                )
                            )
                            assert expected in stderr
                            assert not store.exists(artifact)
                            if stage == "S3_support":
                                assert not store.exists(Path("runs") / run_id / "sufficiency.json")

                        events_before_resume = ledger.read_events(attempts[0]["ledger_month"])
                        for _repeat in range(2):
                            code, _stdout, repeated_stderr = self._validation_resume(
                                run_id, stage, client
                            )
                            assert code == (0 if second_valid else 1), repeated_stderr
                            assert len(transport.requests) == 2
                            assert [
                                record["attempt"]
                                for record in self._stage_attempts(store, run_id, stage)
                            ] == [1, 2]
                            assert ledger.read_events(attempts[0]["ledger_month"]) == events_before_resume

    def test_cli_budget_rejected_resume_rechecks_latest_month_total_same_attempt(self):
        config, store, run_id = self._validation_cli_run()
        config["budget"] = {
            "monthly_limit_usd": 0.015,
            "run_limit_usd": 0.02,
            "call_limit_usd": 0.02,
        }
        (self.root / "config/openai_article_pipeline.yml").write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        ledger = BudgetLedger(store, config)
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        other_run_id = "other_run_budget_holder"
        other_logical_key = "other-run-reservation"
        other_attempt_key = attempt_key(other_logical_key, 1)
        other = {
            "schema": "llm_attempt/v2",
            "logical_key": other_logical_key,
            "attempt": 1,
            "attempt_key": other_attempt_key,
            "reservation_id": "rsv_" + other_attempt_key,
            "settlement_id": "stl_" + other_attempt_key,
            "ledger_month": month,
            "state": "reserved",
            "wire_sha256": "sha256:other-run-wire",
            "estimated_usd": "0.005000000000",
            "proposed_reserve_usd": "0.010000000000",
            "reserve_basis": {
                "input_tokens": 100,
                "max_output_tokens": 1000,
                "price_ref": {"model": "test-model"},
            },
            "run_id": other_run_id,
            "slug": "other_error",
            "stage": "S3_claims",
            "model": "test-model",
            "last_judgment": None,
            "response_id": None,
            "response_sha256": None,
            "actual_usd": None,
            "usage": None,
            "history": [{"state": "reserved", "at": "2026-10-06T00:00:00Z"}],
        }
        ledger.approve_and_reserve({**other, "amount_usd": other["proposed_reserve_usd"]})
        other_path = (
            Path("runs") / other_run_id / "llm_journal" / other_logical_key
            / "attempt-1.json"
        )
        store.write_json(other_path, other)
        other_approval_path = ledger.approval_path(month, other["reservation_id"])
        other_before = {
            "approval": store.read_bytes(other_approval_path),
            "journal": store.read_bytes(other_path),
            "events": [
                event for event in ledger.read_events(month)
                if event["reservation_id"] == other["reservation_id"]
            ],
        }
        assert ledger.counted(month)[0] == Decimal("0.01")
        assert ledger.counted_for_run(other_run_id) == Decimal("0.01")
        assert ledger.counted_for_run(run_id) == Decimal(0)

        transport = Responses([extracted_output()])
        client = LlmClient(transport)
        code, _stdout, stderr = self._validation_resume(run_id, "S3_claims", client)
        assert code == 1
        assert "budget_exceeded" in stderr
        attempts = self._stage_attempts(store, run_id, "S3_claims")
        assert len(attempts) == 1
        rejected = attempts[0]
        assert rejected["attempt"] == 1
        assert rejected["state"] == "budget_rejected"
        reserve = Decimal(rejected["proposed_reserve_usd"])
        assert reserve == Decimal("0.010250000000")
        assert Decimal("0.01") + reserve > Decimal("0.015")
        assert reserve <= Decimal("0.02")
        assert ledger.counted_for_run(run_id) + reserve <= Decimal("0.02")
        target_approval_path = ledger.approval_path(month, rejected["reservation_id"])
        assert not store.exists(target_approval_path)
        assert not any(
            event["reservation_id"] == rejected["reservation_id"]
            for event in ledger.read_events(month)
        )
        assert len(transport.requests) == 0

        code, _stdout, stderr = self._validation_resume(run_id, "S3_claims", client)
        assert code == 1
        assert "budget_exceeded" in stderr
        attempts = self._stage_attempts(store, run_id, "S3_claims")
        assert len(attempts) == 1
        assert attempts[0]["attempt"] == 1
        assert attempts[0]["state"] == "budget_rejected"
        assert not store.exists(target_approval_path)
        assert not any(
            event["reservation_id"] == rejected["reservation_id"]
            for event in ledger.read_events(month)
        )
        assert len(transport.requests) == 0
        assert store.read_bytes(other_approval_path) == other_before["approval"]
        assert store.read_bytes(other_path) == other_before["journal"]
        assert [
            event for event in ledger.read_events(month)
            if event["reservation_id"] == other["reservation_id"]
        ] == other_before["events"]

        assert ledger.settle(other, Decimal("0.001")) is True
        other = {
            **other,
            "state": "completed",
            "actual_usd": "0.001000000000",
            "history": [
                *other["history"],
                {"state": "completed", "at": "2026-10-06T00:01:00Z"},
            ],
        }
        store.write_json(other_path, other)
        assert ledger.counted(month)[0] == Decimal("0.001")
        assert ledger.counted_for_run(other_run_id) == Decimal("0.001")
        assert Decimal("0.001") + reserve <= Decimal("0.015")
        other_settled = {
            "approval": store.read_bytes(other_approval_path),
            "journal": store.read_bytes(other_path),
            "events": [
                event for event in ledger.read_events(month)
                if event["reservation_id"] == other["reservation_id"]
            ],
        }

        code, _stdout, stderr = self._validation_resume(run_id, "S3_claims", client)
        assert code == 0, stderr
        assert len(transport.requests) == 1
        attempts = self._stage_attempts(store, run_id, "S3_claims")
        assert len(attempts) == 1
        completed = attempts[0]
        assert completed["attempt"] == 1
        assert completed["state"] == "completed"
        assert store.exists(target_approval_path)
        target_events = [
            event for event in ledger.read_events(month)
            if event["reservation_id"] == completed["reservation_id"]
        ]
        assert [event["event"] for event in target_events] == ["reserve", "settle"]
        assert Decimal(target_events[-1]["actual_usd"]) == Decimal(completed["actual_usd"])
        expected_month_total = Decimal("0.001") + Decimal(completed["actual_usd"])
        month_total, run_totals = ledger.counted(month)
        assert month_total == expected_month_total
        assert run_totals[other_run_id] == Decimal("0.001")
        assert run_totals[run_id] == Decimal(completed["actual_usd"])
        assert store.read_bytes(other_approval_path) == other_settled["approval"]
        assert store.read_bytes(other_path) == other_settled["journal"]
        assert [
            event for event in ledger.read_events(month)
            if event["reservation_id"] == other["reservation_id"]
        ] == other_settled["events"]

        target_approval = store.read_bytes(target_approval_path)
        all_events = ledger.read_events(month)
        for _repeat in range(2):
            code, _stdout, stderr = self._validation_resume(
                run_id, "S3_claims", client
            )
            assert code == 0, stderr
            assert len(transport.requests) == 1
            assert store.read_bytes(target_approval_path) == target_approval
            assert ledger.read_events(month) == all_events
            assert len(self._stage_attempts(store, run_id, "S3_claims")) == 1
            assert store.read_bytes(other_approval_path) == other_settled["approval"]
            assert store.read_bytes(other_path) == other_settled["journal"]
            assert [
                event for event in ledger.read_events(month)
                if event["reservation_id"] == other["reservation_id"]
            ] == other_settled["events"]

    def _approved_proposed_cli_run(self):
        config, store, run_id = self._validation_cli_run()
        transport = Responses([])
        client = LlmClient(transport)
        graph = PipelineGraph(build_production_stages())
        context = StageContext(
            self.root,
            store,
            run_id,
            config,
            {"llm_client": client},
        )
        original_execute = LlmCallManager.execute

        def stop_after_reserve(manager, **kwargs):
            return original_execute(manager, **kwargs, stop_after="R4")

        with patch.object(LlmCallManager, "execute", new=stop_after_reserve):
            with pytest.raises(RuntimeError, match="R4"):
                graph.resume(context, StateFile(store, run_id), through="S3_claims")

        records = self._stage_attempts(store, run_id, "S3_claims")
        assert len(records) == 1
        record = records[0]
        assert record["state"] == "proposed"
        journal_path = (
            Path("runs") / run_id / "llm_journal" / record["logical_key"]
            / f"attempt-{record['attempt']}.json"
        )
        ledger = BudgetLedger(store, config)
        assert ledger.read_approval(record["ledger_month"], record["reservation_id"]) is not None
        assert [
            event["event"] for event in ledger.read_events(record["ledger_month"])
        ] == ["reserve"]
        assert len(transport.requests) == 0
        return config, store, run_id, transport, journal_path, record

    @staticmethod
    def _add_other_approved_reservation(store, ledger, run_id, record):
        logical_key = "other-budget-release-reservation"
        key = attempt_key(logical_key, 1)
        other = {
            **record,
            "logical_key": logical_key,
            "attempt": 1,
            "attempt_key": key,
            "reservation_id": "rsv_" + key,
            "settlement_id": "stl_" + key,
            "wire_sha256": "sha256:other-wire",
            "proposed_reserve_usd": "0.250000000000",
            "state": "proposed",
            "history": [{"state": "proposed", "at": "2026-10-06T00:00:00Z"}],
        }
        ledger.approve_and_reserve({**other, "amount_usd": other["proposed_reserve_usd"]})
        path = Path("runs") / run_id / "llm_journal" / logical_key / "attempt-1.json"
        store.write_json(path, other)
        return path, other

    def test_cli_repairs_torn_reserve_then_restores_and_resumes_once(self):
        config, store, run_id, _transport, _journal_path, record = (
            self._approved_proposed_cli_run()
        )
        ledger = BudgetLedger(store, config)
        ledger_path = ledger.ledger_path(record["ledger_month"])
        complete = store.read_bytes(ledger_path)
        torn = complete[:-max(2, len(complete) // 3)]
        assert torn and not torn.endswith(b"\n")
        store.write_bytes(ledger_path, torn)

        resume_transport = Responses([extracted_output()])
        code, _stdout, stderr = self._validation_resume(
            run_id, "S3_claims", LlmClient(resume_transport)
        )
        assert code == 1
        assert "途切れ" in stderr
        assert len(resume_transport.requests) == 0
        code, _stdout, stderr = self._reconcile_cli(["budget", "check"])
        assert code == 1
        assert "途切れ" in stderr

        code, stdout, stderr = self._reconcile_cli([
            "budget", "repair", "--month", record["ledger_month"], "--yes"
        ])
        assert code == 0, stderr
        repair = json.loads(stdout)
        quarantine = Path(repair["quarantine"])
        assert store.read_bytes(quarantine) == torn
        assert ledger.read_events(record["ledger_month"]) == []

        code, stdout, stderr = self._reconcile_cli([
            "budget", "check", "--apply"
        ])
        assert code == 0, stderr
        assert [item["action"] for item in json.loads(stdout)["actions"]] == [
            "restore_reserve"
        ]
        assert [event["event"] for event in ledger.read_events(
            record["ledger_month"]
        )] == ["reserve"]

        code, _stdout, stderr = self._validation_resume(
            run_id, "S3_claims", LlmClient(resume_transport)
        )
        assert code == 0, stderr
        assert len(resume_transport.requests) == 1
        final_events = ledger.read_events(record["ledger_month"])
        assert [event["event"] for event in final_events] == [
            "reserve", "settle"
        ]
        code, _stdout, stderr = self._validation_resume(
            run_id, "S3_claims", LlmClient(resume_transport)
        )
        assert code == 0, stderr
        assert len(resume_transport.requests) == 1
        assert ledger.read_events(record["ledger_month"]) == final_events

    def test_cli_budget_release_only_zeroes_target_and_duplicate_does_not_append(self):
        config, store, run_id, transport, journal_path, record = self._approved_proposed_cli_run()
        ledger = BudgetLedger(store, config)
        other_path, other = self._add_other_approved_reservation(
            store, ledger, run_id, record
        )
        target_approval = ledger.approval_path(record["ledger_month"], record["reservation_id"])
        target_approval_before = store.read_bytes(target_approval)
        other_approval = ledger.approval_path(other["ledger_month"], other["reservation_id"])
        other_before = {
            "approval": store.read_bytes(other_approval),
            "journal": store.read_bytes(other_path),
            "events": [
                event for event in ledger.read_events(record["ledger_month"])
                if event["reservation_id"] == other["reservation_id"]
            ],
        }
        before_total, before_runs = ledger.counted(record["ledger_month"])
        assert before_total == Decimal(record["proposed_reserve_usd"]) + Decimal("0.25")
        assert before_runs[run_id] == before_total

        command = [
            "budget", "release", "--reservation", record["reservation_id"],
            "--note", "confirmed not sent",
        ]
        exit_code, stdout, stderr = self._reconcile_cli(command)
        assert exit_code == 0, stderr
        assert "予約を解放しました" in stdout
        assert len(transport.requests) == 0
        updated = store.read_json(journal_path)
        assert updated["state"] == "released"
        assert updated["history"][-1]["note"] == "confirmed not sent"
        target_events = [
            event for event in ledger.read_events(record["ledger_month"])
            if event["reservation_id"] == record["reservation_id"]
        ]
        assert [event["event"] for event in target_events] == ["reserve", "release"]
        assert target_events[-1]["actual_usd"] == "0.000000000000"
        after_total, after_runs = ledger.counted(record["ledger_month"])
        assert after_total == Decimal("0.25")
        assert after_runs[run_id] == Decimal("0.25")
        assert store.read_bytes(target_approval) == target_approval_before
        assert store.read_bytes(other_approval) == other_before["approval"]
        assert store.read_bytes(other_path) == other_before["journal"]
        assert [
            event for event in ledger.read_events(record["ledger_month"])
            if event["reservation_id"] == other["reservation_id"]
        ] == other_before["events"]

        after_first = self._accounting_snapshot(
            store, ledger, journal_path, record
        )
        exit_code, _stdout, stderr = self._reconcile_cli(command)
        assert exit_code == 1
        assert "proposed の予約だけ解放できます" in stderr
        assert self._accounting_snapshot(
            store, ledger, journal_path, record
        ) == after_first
        assert sum(
            event["event"] == "release"
            for event in ledger.read_events(record["ledger_month"])
            if event["reservation_id"] == record["reservation_id"]
        ) == 1
        assert len(transport.requests) == 0

    def _interrupted_budget_release(self):
        config, store, run_id, transport, journal_path, record = (
            self._approved_proposed_cli_run()
        )
        ledger = BudgetLedger(store, config)
        other_path, other = self._add_other_approved_reservation(
            store, ledger, run_id, record
        )
        command = [
            "budget", "release", "--reservation", record["reservation_id"],
            "--note", "confirmed not sent",
        ]
        before_events = ledger.read_events(record["ledger_month"])
        assert sum(
            event["event"] == "reserve"
            for event in before_events
            if event["reservation_id"] == record["reservation_id"]
        ) == 1
        assert store.read_json(journal_path)["state"] == "proposed"
        journal_before = store.read_bytes(journal_path)
        original_write_json = RunStore.write_json

        def stop_before_released_journal(instance, relative, value):
            if (
                Path(relative) == journal_path
                and isinstance(value, dict)
                and value.get("state") == "released"
            ):
                raise RuntimeError("injected stop after release ledger append")
            return original_write_json(instance, relative, value)

        with patch.object(RunStore, "write_json", new=stop_before_released_journal):
            with pytest.raises(RuntimeError, match="after release ledger append"):
                self._reconcile_cli(command)

        interrupted_events = ledger.read_events(record["ledger_month"])
        target_events = [
            event for event in interrupted_events
            if event["reservation_id"] == record["reservation_id"]
        ]
        assert [event["event"] for event in target_events] == ["reserve", "release"]
        assert store.read_bytes(journal_path) == journal_before
        assert store.read_json(journal_path)["state"] == "proposed"
        assert ledger.counted(record["ledger_month"])[1][run_id] == Decimal("0.25")
        assert len(transport.requests) == 0
        return (
            config, store, run_id, transport, ledger, journal_path, record,
            other_path, other, command, before_events, interrupted_events,
        )

    def test_cli_budget_release_recovers_after_ledger_append_before_journal_update(self):
        (
            _config, store, run_id, transport, ledger, journal_path, record,
            other_path, other, command, before_events, interrupted_events,
        ) = self._interrupted_budget_release()
        target_before = [
            event for event in before_events
            if event["reservation_id"] == record["reservation_id"]
        ]
        target_interrupted = [
            event for event in interrupted_events
            if event["reservation_id"] == record["reservation_id"]
        ]
        other_before = [
            event for event in before_events
            if event["reservation_id"] == other["reservation_id"]
        ]
        other_interrupted = [
            event for event in interrupted_events
            if event["reservation_id"] == other["reservation_id"]
        ]
        assert len(target_before) == 1
        assert len(target_interrupted) == 2
        assert other_interrupted == other_before
        other_journal_before = store.read_bytes(other_path)

        exit_code, stdout, stderr = self._reconcile_cli(command)
        assert exit_code == 0, stderr
        assert "予約を解放しました" in stdout
        recovered_events = ledger.read_events(record["ledger_month"])
        target_recovered = [
            event for event in recovered_events
            if event["reservation_id"] == record["reservation_id"]
        ]
        assert target_recovered == target_interrupted
        assert store.read_json(journal_path)["state"] == "released"
        assert store.read_bytes(other_path) == other_journal_before
        assert [
            event for event in recovered_events
            if event["reservation_id"] == other["reservation_id"]
        ] == other_before
        total, runs = ledger.counted(record["ledger_month"])
        assert total == Decimal("0.25")
        assert runs[run_id] == Decimal("0.25")
        assert len(transport.requests) == 0

        exit_code, stdout, stderr = self._reconcile_cli(["budget", "check"])
        assert exit_code == 0, stderr
        assert json.loads(stdout)["actions"] == []
        assert ledger.read_events(record["ledger_month"]) == recovered_events
        assert len(transport.requests) == 0

    def test_cli_budget_release_interruption_rejects_changed_reason_or_identifier(self):
        for changed in ("reason", "settlement_id"):
            with self.subTest(changed=changed):
                self.tearDown()
                self.setUp()
                (
                    _config, store, _run_id, transport, ledger, journal_path,
                    record, other_path, other, command, _before_events,
                    _interrupted_events,
                ) = self._interrupted_budget_release()
                if changed == "reason":
                    retry_command = [*command[:-1], "different reason"]
                else:
                    modified = store.read_json(journal_path)
                    modified["settlement_id"] = "stl_different"
                    store.write_json(journal_path, modified)
                    retry_command = command
                snapshot = {
                    "target_approval": store.read_bytes(
                        ledger.approval_path(record["ledger_month"], record["reservation_id"])
                    ),
                    "other_approval": store.read_bytes(
                        ledger.approval_path(other["ledger_month"], other["reservation_id"])
                    ),
                    "ledger": store.read_bytes(ledger.ledger_path(record["ledger_month"])),
                    "target_journal": store.read_bytes(journal_path),
                    "other_journal": store.read_bytes(other_path),
                }
                exit_code, _stdout, stderr = self._reconcile_cli(retry_command)
                assert exit_code == 1
                assert "内容または識別子の異なる確定記録" in stderr
                assert {
                    "target_approval": store.read_bytes(
                        ledger.approval_path(record["ledger_month"], record["reservation_id"])
                    ),
                    "other_approval": store.read_bytes(
                        ledger.approval_path(other["ledger_month"], other["reservation_id"])
                    ),
                    "ledger": store.read_bytes(ledger.ledger_path(record["ledger_month"])),
                    "target_journal": store.read_bytes(journal_path),
                    "other_journal": store.read_bytes(other_path),
                } == snapshot
                assert len(transport.requests) == 0

    def test_cli_budget_release_rejects_sent_unknown_and_settled_without_changes(self):
        for state in ("reserved", "submitted", "unknown_outcome", "completed"):
            with self.subTest(state=state):
                self.tearDown()
                self.setUp()
                config, store, _run_id, transport, journal_path, record = (
                    self._approved_proposed_cli_run()
                )
                ledger = BudgetLedger(store, config)
                if state == "submitted":
                    record["response_id"] = "resp_sent"
                elif state == "unknown_outcome":
                    assert ledger.outcome_unknown(record) is True
                elif state == "completed":
                    assert ledger.settle(record, Decimal("0.001")) is True
                    record["actual_usd"] = "0.001000000000"
                record["state"] = state
                record["history"] = [
                    *record["history"],
                    {"state": state, "at": "2026-10-06T00:00:00Z"},
                ]
                store.write_json(journal_path, record)
                before = self._accounting_snapshot(
                    store, ledger, journal_path, record
                )
                exit_code, _stdout, stderr = self._reconcile_cli([
                    "budget", "release", "--reservation", record["reservation_id"],
                    "--note", "must not release",
                ])
                assert exit_code == 1
                assert f"state={state}" in stderr
                assert self._accounting_snapshot(
                    store, ledger, journal_path, record
                ) == before
                assert len(transport.requests) == 0

    def test_cli_budget_release_rejects_approval_mismatch_without_changes(self):
        config, store, _run_id, transport, journal_path, record = (
            self._approved_proposed_cli_run()
        )
        ledger = BudgetLedger(store, config)
        month = record["ledger_month"]
        events = ledger.read_events(month)
        approval_path = ledger.approval_path(month, record["reservation_id"])
        approval = ledger.read_approval(month, record["reservation_id"])
        approval = checked_record({**approval, "wire_sha256": "sha256:different-wire"})
        store.write_json(approval_path, approval)
        reserve = checked_record({
            **events[0],
            "approval_sha256": sha256_bytes(canonical_json_bytes(approval)),
        })
        store.write_bytes(
            ledger.ledger_path(month), canonical_json_bytes(reserve)
        )
        assert ledger.read_events(month)[0]["event"] == "reserve"
        before = self._accounting_snapshot(store, ledger, journal_path, record)

        exit_code, _stdout, stderr = self._reconcile_cli([
            "budget", "release", "--reservation", record["reservation_id"],
            "--note", "must not release",
        ])
        assert exit_code == 1
        assert "承認の記録がジャーナルと一致しません" in stderr
        assert self._accounting_snapshot(store, ledger, journal_path, record) == before
        assert len(transport.requests) == 0

    def test_cli_budget_release_budget_lock_failure_changes_nothing(self):
        config, store, _run_id, transport, journal_path, record = (
            self._approved_proposed_cli_run()
        )
        ledger = BudgetLedger(store, config)
        before = self._accounting_snapshot(store, ledger, journal_path, record)
        store.create_exclusive_json("locks/budget.lock", {
            "hostname": "test", "pid": 999999, "started_at": "2026-10-06T00:00:00Z",
        })
        try:
            exit_code, _stdout, stderr = self._reconcile_cli([
                "budget", "release", "--reservation", record["reservation_id"],
                "--note", "lock contention",
            ])
            assert exit_code == 1
            assert "予算ロックを取得できません" in stderr
            assert self._accounting_snapshot(
                store, ledger, journal_path, record
            ) == before
            assert len(transport.requests) == 0
        finally:
            store.remove("locks/budget.lock")

    def test_cli_budget_release_slug_lock_failure_changes_nothing(self):
        config, store, run_id, transport, journal_path, record = (
            self._approved_proposed_cli_run()
        )
        ledger = BudgetLedger(store, config)
        before = self._accounting_snapshot(store, ledger, journal_path, record)
        state = StateFile(store, run_id).read()
        lock_path = Path("locks") / f"{state['slug']}.lock"
        store.create_exclusive_json(lock_path, {
            "hostname": "test", "pid": 999999, "run_id": "another-run",
            "started_at": "2026-10-06T00:00:00Z",
        })
        try:
            exit_code, _stdout, stderr = self._reconcile_cli([
                "budget", "release", "--reservation", record["reservation_id"],
                "--note", "run is active",
            ])
            assert exit_code == 1
            assert "slug のロックを取得できません" in stderr
            assert self._accounting_snapshot(
                store, ledger, journal_path, record
            ) == before
            assert len(transport.requests) == 0
        finally:
            store.remove(lock_path)

    def _reserved_cli_run(self):
        config = json.loads(CONFIG)
        config["llm"]["store"] = False
        config["llm"]["pricing"]["max_age_days"] = 3650
        config["llm"]["pricing"]["models"]["test-model"]["checked_at"] = (
            datetime.now(timezone.utc).date().isoformat()
        )
        config["budget"] = {
            "monthly_limit_usd": 10,
            "run_limit_usd": 5,
            "call_limit_usd": 2,
        }
        config["claims"]["extract"].update(
            model="test-model",
            reasoning_effort="low",
            max_output_tokens=1000,
            expected_output_tokens=200,
            max_input_tokens_per_call=1000,
        )
        (self.root / "config/openai_article_pipeline.yml").write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        repository = Path(__file__).parents[1]
        for relative in (
            "config/prompts/s3_extract.v1.md",
            "config/schemas/claims_extract.v1.json",
        ):
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(repository / relative, destination)

        topic = self.write_topic()
        candidates = self.root / "run/article_pipeline/inbox/candidates.yml"
        candidates.write_text(
            "schema: url_candidates/v1\ncandidates:\n"
            "- {url: https://example.com/docs, role_hint: official_doc}\n",
            encoding="utf-8",
        )
        assert command_new(
            argparse.Namespace(
                topic=str(topic), mode="candidate", new_run=False,
                url_candidates=str(candidates),
            ),
            self.root,
        ) == 0
        run_id = next((self.root / "run/article_pipeline/runs").iterdir()).name
        transport = Responses([])
        llm_client = LlmClient(transport)
        store = RunStore(self.root)
        graph = PipelineGraph(build_production_stages())
        context = StageContext(
            self.root,
            store,
            run_id,
            config,
            {
                "network_client": FixedClient(
                    body=b"Sample connection error is documented here.\n"
                ),
                "llm_client": llm_client,
            },
        )
        state_file = StateFile(store, run_id)
        original_execute = LlmCallManager.execute

        def stop_at_reserved(manager, **kwargs):
            return original_execute(manager, **kwargs, stop_after="R5")

        with patch.object(LlmCallManager, "execute", new=stop_at_reserved):
            with pytest.raises(RuntimeError, match="R5"):
                graph.resume(context, state_file, through="S3_claims")

        records = [
            path for path in store.path(Path("runs") / run_id / "llm_journal").glob("*/attempt-*.json")
            if not path.name.endswith(".response.json")
        ]
        assert len(records) == 1
        journal_path = records[0].relative_to(store.root)
        record = store.read_json(journal_path)
        assert record["state"] == "reserved"
        ledger = BudgetLedger(store, config)
        assert [event["event"] for event in ledger.read_events(record["ledger_month"])] == ["reserve"]
        assert ledger.read_approval(record["ledger_month"], record["reservation_id"]) is not None
        return config, store, run_id, transport, llm_client, journal_path, record

    @staticmethod
    def _budget_integrity_snapshot(store, ledger, journal_path, record):
        response_path = journal_path.with_name(
            f"attempt-{record['attempt']}.response.json"
        )
        paths = {
            "approval": ledger.approval_path(
                record["ledger_month"], record["reservation_id"]
            ),
            "ledger": ledger.ledger_path(record["ledger_month"]),
            "journal": journal_path,
            "response": response_path,
        }
        return {
            key: store.read_bytes(path) if store.exists(path) else None
            for key, path in paths.items()
        }

    def test_cli_budget_integrity_rejects_each_approval_journal_reserve_mismatch(self):
        expected_messages = {
            "amount": "承認記録とジャーナルの金額が一致しません",
            "run_id": "承認記録とジャーナルが一致しません",
            "slug": "承認記録とジャーナルが一致しません",
            "stage": "承認記録とジャーナルが一致しません",
            "logical_key": "承認記録とジャーナルが一致しません",
            "attempt": "承認記録とジャーナルが一致しません",
            "attempt_key": "ジャーナルの派生識別子が一致しません",
            "reservation_id": "ジャーナルの派生識別子が一致しません",
            "settlement_id": "ジャーナルの派生識別子が一致しません",
            "wire_sha256": "承認記録とジャーナルが一致しません",
            "approval_chk": "承認記録",
            "reserve_approval_hash": "承認記録と reserve のハッシュが一致しません",
        }
        approval_fields = {
            "amount", "run_id", "slug", "stage", "logical_key", "attempt",
            "wire_sha256",
        }
        for case, expected in expected_messages.items():
            with self.subTest(case=case):
                self.tearDown()
                self.setUp()
                config, store, run_id, transport, llm_client, journal_path, record = (
                    self._reserved_cli_run()
                )
                ledger = BudgetLedger(store, config)
                month = record["ledger_month"]
                original_reservation = record["reservation_id"]
                approval_path = ledger.approval_path(month, original_reservation)
                approval = ledger.read_approval(month, original_reservation)
                events = ledger.read_events(month)
                assert len(events) == 1 and events[0]["event"] == "reserve"
                reserve_event = events[0]

                if case in approval_fields:
                    if case == "amount":
                        approval["amount_usd"] = "0.500000000000"
                        reserve_event["amount_usd"] = "0.500000000000"
                    elif case == "run_id":
                        approval["run_id"] = "different-run"
                        reserve_event["run_id"] = "different-run"
                    elif case == "attempt":
                        approval["attempt"] = record["attempt"] + 1
                    else:
                        approval[case] = f"different-{case}"
                    approval = checked_record(approval)
                    store.write_json(approval_path, approval)
                    reserve_event["approval_sha256"] = sha256_bytes(
                        canonical_json_bytes(approval)
                    )
                    reserve_event = checked_record(reserve_event)
                    store.write_bytes(
                        ledger.ledger_path(month), canonical_json_bytes(reserve_event)
                    )
                elif case == "attempt_key":
                    record["attempt_key"] = "different-attempt-key"
                    store.write_json(journal_path, record)
                elif case == "settlement_id":
                    record["settlement_id"] = "stl_different"
                    store.write_json(journal_path, record)
                elif case == "reservation_id":
                    record["reservation_id"] = "rsv_different"
                    store.write_json(journal_path, record)
                    approval["reservation_id"] = record["reservation_id"]
                    approval = checked_record(approval)
                    store.remove(approval_path)
                    approval_path = ledger.approval_path(month, record["reservation_id"])
                    store.write_json(approval_path, approval)
                    reserve_event["event_id"] = record["reservation_id"]
                    reserve_event["reservation_id"] = record["reservation_id"]
                    reserve_event["approval_sha256"] = sha256_bytes(
                        canonical_json_bytes(approval)
                    )
                    reserve_event = checked_record(reserve_event)
                    store.write_bytes(
                        ledger.ledger_path(month), canonical_json_bytes(reserve_event)
                    )
                elif case == "approval_chk":
                    approval["chk"] = "sha256:invalid"
                    store.write_json(approval_path, approval)
                else:
                    reserve_event["approval_sha256"] = "sha256:invalid"
                    reserve_event = checked_record(reserve_event)
                    store.write_bytes(
                        ledger.ledger_path(month), canonical_json_bytes(reserve_event)
                    )

                before = self._budget_integrity_snapshot(
                    store, ledger, journal_path, record
                )
                commands = [
                    ["status", "--run", run_id],
                    ["budget", "check"],
                    ["budget", "check", "--apply"],
                    ["resume", "--run", run_id, "--through", "S3_claims"],
                ]
                with patch(
                    "scripts.article_pipeline.claims_extract.LlmClient",
                    return_value=llm_client,
                ):
                    for command in commands:
                        exit_code, _stdout, stderr = self._reconcile_cli(command)
                        assert exit_code == 1, (case, command, stderr)
                        assert expected in stderr
                        assert self._budget_integrity_snapshot(
                            store, ledger, journal_path, record
                        ) == before
                        assert len(transport.requests) == 0

    def test_cli_budget_integrity_accepts_normal_approved_record(self):
        config, store, run_id, transport, _client, journal_path, record = (
            self._reserved_cli_run()
        )
        ledger = BudgetLedger(store, config)
        before = self._budget_integrity_snapshot(
            store, ledger, journal_path, record
        )
        for command in (
            ["status", "--run", run_id],
            ["budget", "check"],
            ["budget", "check", "--apply"],
        ):
            exit_code, stdout, stderr = self._reconcile_cli(command)
            assert exit_code == 0, (command, stderr)
            if command[:2] == ["budget", "check"]:
                assert json.loads(stdout)["actions"] == []
            assert self._budget_integrity_snapshot(
                store, ledger, journal_path, record
            ) == before
            assert len(transport.requests) == 0

    def _assert_unapproved_reserved_cli_stops_without_changes(self, *, keep_reserve):
        config, store, run_id, transport, llm_client, journal_path, record = self._reserved_cli_run()
        ledger = BudgetLedger(store, config)
        approval_path = ledger.approval_path(record["ledger_month"], record["reservation_id"])
        store.remove(approval_path)
        ledger_path = ledger.ledger_path(record["ledger_month"])
        if not keep_reserve:
            store.remove(ledger_path)

        journal_before = store.read_bytes(journal_path)
        ledger_before = store.read_bytes(ledger_path) if store.exists(ledger_path) else None
        assert not store.exists(approval_path)
        commands = [
            ["resume", "--run", run_id, "--through", "S3_claims"],
            ["status", "--run", run_id],
            ["budget", "check"],
            ["budget", "check", "--apply"],
        ]
        with (
            patch("scripts.article_pipeline.__main__.repo_root", return_value=self.root),
            patch("scripts.article_pipeline.claims_extract.LlmClient", return_value=llm_client),
        ):
            for command in commands:
                stdout = io.StringIO()
                stderr = io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    exit_code = main(command)
                assert exit_code == 1, (command, stdout.getvalue(), stderr.getvalue())
                assert "承認記録がないのに reserved 以降のジャーナルがあります" in stderr.getvalue()
                assert record["reservation_id"] in stderr.getvalue()
                assert len(transport.requests) == 0
                assert not store.exists(approval_path)
                assert store.read_bytes(journal_path) == journal_before
                assert (store.read_bytes(ledger_path) if store.exists(ledger_path) else None) == ledger_before

    def test_cli_rejects_unapproved_reserved_journal_with_reserve_ledger(self):
        self._assert_unapproved_reserved_cli_stops_without_changes(keep_reserve=True)

    def test_cli_rejects_unapproved_reserved_journal_without_reserve_ledger(self):
        self._assert_unapproved_reserved_cli_stops_without_changes(keep_reserve=False)

    def test_cli_resume_keeps_normal_approved_reserved_recovery(self):
        config, store, run_id, transport, llm_client, journal_path, record = self._reserved_cli_run()
        ledger = BudgetLedger(store, config)
        approval_path = ledger.approval_path(record["ledger_month"], record["reservation_id"])
        approval_before = store.read_bytes(approval_path)
        with (
            patch("scripts.article_pipeline.__main__.repo_root", return_value=self.root),
            patch("scripts.article_pipeline.claims_extract.LlmClient", return_value=llm_client),
        ):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = main(["resume", "--run", run_id, "--through", "S3_claims"])
        assert exit_code == 1
        assert "作成要求を送ったか確認できません。自動再送しません" in stderr.getvalue()
        assert len(transport.requests) == 0
        assert store.read_bytes(approval_path) == approval_before
        assert store.read_json(journal_path)["state"] == "unknown_outcome"
        assert [
            event["event"] for event in ledger.read_events(record["ledger_month"])
        ] == ["reserve", "outcome_unknown"]

    def _unknown_cli_run(self):
        config, store, run_id, transport, llm_client, journal_path, record = self._reserved_cli_run()
        ledger = BudgetLedger(store, config)
        assert ledger.outcome_unknown(record) is True
        record = {
            **record,
            "state": "unknown_outcome",
            "history": [
                *record.get("history", []),
                {"state": "unknown_outcome", "at": "2026-10-06T00:00:00Z"},
            ],
        }
        store.write_json(journal_path, record)
        return config, store, run_id, transport, llm_client, journal_path, record

    def _reconcile_cli(self, arguments):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch("scripts.article_pipeline.__main__.repo_root", return_value=self.root),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = main(arguments)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    @staticmethod
    def _accounting_snapshot(store, ledger, journal_path, record):
        approval_path = ledger.approval_path(record["ledger_month"], record["reservation_id"])
        ledger_path = ledger.ledger_path(record["ledger_month"])
        return {
            "approval": store.read_bytes(approval_path),
            "ledger": store.read_bytes(ledger_path),
            "journal": store.read_bytes(journal_path),
        }

    def test_cli_reconcile_updates_counted_amount_once_and_is_idempotent(self):
        config, store, run_id, transport, _client, journal_path, record = self._unknown_cli_run()
        ledger = BudgetLedger(store, config)
        other_logical_key = "other-logical-key"
        other_attempt_key = attempt_key(other_logical_key, 1)
        other = {
            **record,
            "logical_key": other_logical_key,
            "attempt": 1,
            "attempt_key": other_attempt_key,
            "reservation_id": "rsv_" + other_attempt_key,
            "settlement_id": "stl_" + other_attempt_key,
            "wire_sha256": "sha256:other-wire",
            "proposed_reserve_usd": "0.250000000000",
            "state": "reserved",
            "history": [{"state": "reserved", "at": "2026-10-06T00:00:00Z"}],
        }
        ledger.approve_and_reserve({**other, "amount_usd": other["proposed_reserve_usd"]})
        other_journal = Path("runs") / run_id / "llm_journal" / other_logical_key / "attempt-1.json"
        store.write_json(other_journal, other)
        other_journal_before = store.read_bytes(other_journal)
        target_approval = ledger.approval_path(record["ledger_month"], record["reservation_id"])
        other_approval = ledger.approval_path(other["ledger_month"], other["reservation_id"])
        target_approval_before = store.read_bytes(target_approval)
        other_approval_before = store.read_bytes(other_approval)
        command = [
            "llm", "reconcile", "--run", run_id,
            "--logical-key", record["logical_key"], "--attempt", str(record["attempt"]),
            "--actual-usd", "0.000123456789", "--note", "usage dashboard checked",
        ]
        before_total, _runs = ledger.counted(record["ledger_month"])
        assert before_total == Decimal(record["proposed_reserve_usd"]) + Decimal("0.25")

        exit_code, _stdout, stderr = self._reconcile_cli(command)
        assert exit_code == 0, stderr
        updated = store.read_json(journal_path)
        assert updated["state"] == "reconciled"
        assert updated["actual_usd"] == "0.000123456789"
        assert updated["reconciliation_note"] == "usage dashboard checked"
        events = ledger.read_events(record["ledger_month"])
        target_events = [event for event in events if event["reservation_id"] == record["reservation_id"]]
        other_events = [event for event in events if event["reservation_id"] == other["reservation_id"]]
        assert [event["event"] for event in target_events] == ["reserve", "outcome_unknown", "reconcile"]
        assert [event["event"] for event in other_events] == ["reserve"]
        assert sum(event["event"] == "reserve" for event in target_events) == 1
        assert sum(event["event"] == "reconcile" for event in target_events) == 1
        after_total, run_totals = ledger.counted(record["ledger_month"])
        expected_total = Decimal("0.000123456789") + Decimal("0.25")
        assert after_total == expected_total
        assert run_totals[run_id] == expected_total
        assert store.read_bytes(target_approval) == target_approval_before
        assert store.read_bytes(other_approval) == other_approval_before
        assert store.read_bytes(other_journal) == other_journal_before
        assert len(transport.requests) == 0

        after_first = self._accounting_snapshot(store, ledger, journal_path, record)
        exit_code, stdout, stderr = self._reconcile_cli(command)
        assert exit_code == 0, stderr
        assert "同じ照合が既に記録されています" in stdout
        assert self._accounting_snapshot(store, ledger, journal_path, record) == after_first
        assert len(transport.requests) == 0

        for changed in (
            [*command[:-4], "--actual-usd", "0.000123456788", "--note", "usage dashboard checked"],
            [*command[:-1], "different evidence"],
        ):
            exit_code, _stdout, stderr = self._reconcile_cli(changed)
            assert exit_code == 1
            assert "内容の異なる照合" in stderr
            assert self._accounting_snapshot(store, ledger, journal_path, record) == after_first
            assert len(transport.requests) == 0

    def test_cli_reconcile_not_billed_counts_zero(self):
        config, store, run_id, transport, _client, journal_path, record = self._unknown_cli_run()
        ledger = BudgetLedger(store, config)
        exit_code, _stdout, stderr = self._reconcile_cli([
            "llm", "reconcile", "--run", run_id,
            "--logical-key", record["logical_key"], "--attempt", str(record["attempt"]),
            "--not-billed", "--note", "provider confirmed no charge",
        ])
        assert exit_code == 0, stderr
        assert store.read_json(journal_path)["actual_usd"] == "0.000000000000"
        assert ledger.counted(record["ledger_month"])[0] == Decimal(0)
        assert [
            event["event"] for event in ledger.read_events(record["ledger_month"])
        ] == ["reserve", "outcome_unknown", "reconcile"]
        assert len(transport.requests) == 0

    def test_cli_rejected_request_keeps_reserve_until_manual_reconciliation(self):
        config, store, run_id = self._validation_cli_run()
        transport = RejectedTransport()
        client = LlmClient(transport)

        exit_code, _stdout, stderr = self._validation_resume(
            run_id, "S3_claims", client
        )
        assert exit_code == 1
        assert "status=400" in stderr
        records = self._stage_attempts(store, run_id, "S3_claims")
        assert len(records) == 1
        record = records[0]
        journal_path = (
            Path("runs") / run_id / "llm_journal" / record["logical_key"]
            / f"attempt-{record['attempt']}.json"
        )
        ledger = BudgetLedger(store, config)
        target_events = [
            event for event in ledger.read_events(record["ledger_month"])
            if event["reservation_id"] == record["reservation_id"]
        ]
        assert [event["event"] for event in target_events] == ["reserve"]
        assert record["state"] == "rejected"
        assert record["api_outcome"] == "rejected"
        assert record["billing_status"] == "unreconciled"
        assert record["actual_usd"] is None

        other_logical_key = "other-run-4xx-logical-key"
        other_attempt_key = attempt_key(other_logical_key, 1)
        other = {
            **record,
            "run_id": "other_run_4xx",
            "slug": "other_run_4xx",
            "logical_key": other_logical_key,
            "attempt": 1,
            "attempt_key": other_attempt_key,
            "reservation_id": "rsv_" + other_attempt_key,
            "settlement_id": "stl_" + other_attempt_key,
            "wire_sha256": "sha256:other-run-4xx-wire",
            "proposed_reserve_usd": "0.250000000000",
            "state": "proposed",
            "api_outcome": None,
            "billing_status": None,
            "history": [{"state": "proposed", "at": "2026-10-07T00:00:00Z"}],
        }
        ledger.approve_and_reserve({
            **other, "amount_usd": other["proposed_reserve_usd"],
        })
        other_path = (
            Path("runs/other_run_4xx/llm_journal") / other_logical_key
            / "attempt-1.json"
        )
        store.write_json(other_path, other)
        other_before = self._other_run_snapshot(
            store, ledger, other_path, other
        )
        target_before = self._accounting_snapshot(
            store, ledger, journal_path, record
        )
        before_total, before_runs = ledger.counted(record["ledger_month"])
        assert before_runs[run_id] == Decimal(record["proposed_reserve_usd"])
        assert before_runs["other_run_4xx"] == Decimal("0.25")

        for _repeat in range(2):
            exit_code, _stdout, stderr = self._validation_resume(
                run_id, "S3_claims", client
            )
            assert exit_code == 1
            assert "自動再試行しません" in stderr
            assert len(transport.requests) == 1
            assert self._accounting_snapshot(
                store, ledger, journal_path, record
            ) == target_before
            assert self._other_run_snapshot(
                store, ledger, other_path, other
            ) == other_before
            assert ledger.counted(record["ledger_month"])[0] == before_total

        exit_code, _stdout, stderr = self._reconcile_cli([
            "llm", "reconcile", "--run", run_id,
            "--logical-key", record["logical_key"],
            "--attempt", str(record["attempt"]),
            "--actual-usd", "0.000100000000",
            "--note", "provider usage checked",
        ])
        assert exit_code == 0, stderr
        updated = store.read_json(journal_path)
        assert updated["state"] == "reconciled"
        assert updated["api_outcome"] == "rejected"
        assert updated["billing_status"] == "settled"
        assert updated["actual_usd"] == "0.000100000000"
        events = ledger.read_events(record["ledger_month"])
        target_events = [
            event for event in events
            if event["reservation_id"] == record["reservation_id"]
        ]
        assert [event["event"] for event in target_events] == [
            "reserve", "reconcile",
        ]
        after_total, after_runs = ledger.counted(record["ledger_month"])
        assert after_runs[run_id] == Decimal("0.000100000000")
        assert after_runs["other_run_4xx"] == Decimal("0.25")
        assert after_total == Decimal("0.250100000000")
        assert self._other_run_snapshot(
            store, ledger, other_path, other
        ) == other_before

        events_after_reconcile = ledger.read_events(record["ledger_month"])
        exit_code, _stdout, stderr = self._validation_resume(
            run_id, "S3_claims", client
        )
        assert exit_code == 1
        assert "自動再試行しません" in stderr
        assert len(transport.requests) == 1
        assert ledger.read_events(record["ledger_month"]) == events_after_reconcile
        assert self._other_run_snapshot(
            store, ledger, other_path, other
        ) == other_before

    def test_cli_reconcile_rejects_lookup_note_amount_and_state_without_changes(self):
        for case in ("logical_key", "attempt", "note", "amount", "state"):
            with self.subTest(case=case):
                self.tearDown()
                self.setUp()
                if case == "state":
                    config, store, run_id, transport, _client, journal_path, record = self._reserved_cli_run()
                else:
                    config, store, run_id, transport, _client, journal_path, record = self._unknown_cli_run()
                ledger = BudgetLedger(store, config)
                before = self._accounting_snapshot(store, ledger, journal_path, record)
                logical_key = "missing" if case == "logical_key" else record["logical_key"]
                attempt = record["attempt"] + 1 if case == "attempt" else record["attempt"]
                amount = "-0.1" if case == "amount" else "0.1"
                note = "   " if case == "note" else "checked"
                exit_code, _stdout, stderr = self._reconcile_cli([
                    "llm", "reconcile", "--run", run_id,
                    "--logical-key", logical_key, "--attempt", str(attempt),
                    "--actual-usd", amount, "--note", note,
                ])
                assert exit_code == 1
                expected = {
                    "logical_key": "照合対象の試行",
                    "attempt": "照合対象の試行",
                    "note": "空でない --note",
                    "amount": "0以上の有限値",
                    "state": "照合待ちではない試行",
                }[case]
                assert expected in stderr
                assert self._accounting_snapshot(store, ledger, journal_path, record) == before
                assert len(transport.requests) == 0

    def test_cli_reconcile_rejects_journal_approval_amount_mismatch_without_changes(self):
        config, store, run_id, transport, _client, journal_path, record = self._unknown_cli_run()
        record["proposed_reserve_usd"] = "0.500000000000"
        store.write_json(journal_path, record)
        ledger = BudgetLedger(store, config)
        before = self._accounting_snapshot(store, ledger, journal_path, record)
        exit_code, _stdout, stderr = self._reconcile_cli([
            "llm", "reconcile", "--run", run_id,
            "--logical-key", record["logical_key"], "--attempt", str(record["attempt"]),
            "--actual-usd", "0.1", "--note", "checked",
        ])
        assert exit_code == 1
        assert "承認記録とジャーナルの金額が一致しません" in stderr
        assert self._accounting_snapshot(store, ledger, journal_path, record) == before
        assert len(transport.requests) == 0

    def test_cli_reconcile_rejects_derived_identifier_mismatch_without_changes(self):
        config, store, run_id, transport, _client, journal_path, record = self._unknown_cli_run()
        record["settlement_id"] = "stl_wrong"
        store.write_json(journal_path, record)
        ledger = BudgetLedger(store, config)
        before = self._accounting_snapshot(store, ledger, journal_path, record)
        exit_code, _stdout, stderr = self._reconcile_cli([
            "llm", "reconcile", "--run", run_id,
            "--logical-key", record["logical_key"], "--attempt", str(record["attempt"]),
            "--actual-usd", "0.1", "--note", "checked",
        ])
        assert exit_code == 1
        assert "試行の識別子が一致しません" in stderr
        assert self._accounting_snapshot(store, ledger, journal_path, record) == before
        assert len(transport.requests) == 0

    def test_cli_reconcile_rejects_conflicting_ledger_identifier_without_changes(self):
        config, store, run_id, transport, _client, journal_path, record = self._unknown_cli_run()
        ledger = BudgetLedger(store, config)
        conflicting = {**record, "settlement_id": "stl_wrong"}
        assert ledger.settle(
            {**conflicting, "amount_usd": conflicting["proposed_reserve_usd"]},
            Decimal("0.1"),
            event="reconcile",
            note="different record",
        ) is True
        before = self._accounting_snapshot(store, ledger, journal_path, record)
        exit_code, _stdout, stderr = self._reconcile_cli([
            "llm", "reconcile", "--run", run_id,
            "--logical-key", record["logical_key"], "--attempt", str(record["attempt"]),
            "--actual-usd", "0.1", "--note", "checked",
        ])
        assert exit_code == 1
        assert "照合待ちジャーナルに確定済みの出来事があります" in stderr
        assert self._accounting_snapshot(store, ledger, journal_path, record) == before
        assert len(transport.requests) == 0

    def _settlement_stop_cli_run(self, stop):
        config = json.loads(CONFIG)
        config["llm"]["store"] = False
        config["llm"]["pricing"]["max_age_days"] = 3650
        config["llm"]["pricing"]["models"]["test-model"]["checked_at"] = (
            datetime.now(timezone.utc).date().isoformat()
        )
        config["budget"] = {
            "monthly_limit_usd": 10,
            "run_limit_usd": 5,
            "call_limit_usd": 2,
        }
        config["claims"]["extract"].update(
            model="test-model",
            reasoning_effort="low",
            max_output_tokens=1000,
            expected_output_tokens=200,
            max_input_tokens_per_call=1000,
        )
        (self.root / "config/openai_article_pipeline.yml").write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        repository = Path(__file__).parents[1]
        for relative in (
            "config/prompts/s3_extract.v1.md",
            "config/schemas/claims_extract.v1.json",
        ):
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(repository / relative, destination)

        topic = self.write_topic()
        candidates = self.root / "run/article_pipeline/inbox/candidates.yml"
        candidates.write_text(
            "schema: url_candidates/v1\ncandidates:\n"
            "- {url: https://example.com/docs, role_hint: official_doc}\n",
            encoding="utf-8",
        )
        assert command_new(
            argparse.Namespace(
                topic=str(topic), mode="candidate", new_run=False,
                url_candidates=str(candidates),
            ),
            self.root,
        ) == 0
        run_id = next((self.root / "run/article_pipeline/runs").iterdir()).name
        transport = Responses([extracted_output()])
        llm_client = LlmClient(transport)
        store = RunStore(self.root)
        graph = PipelineGraph(build_production_stages())
        context = StageContext(
            self.root,
            store,
            run_id,
            config,
            {
                "network_client": FixedClient(
                    body=b"E100 happens when the socket closes\n"
                ),
                "llm_client": llm_client,
            },
        )
        state_file = StateFile(store, run_id)
        original_execute = LlmCallManager.execute

        def stop_during_settlement(manager, **kwargs):
            if stop == "S4":
                original_execute(manager, **kwargs)
                raise RuntimeError("injected stop after S4")
            return original_execute(manager, **kwargs, stop_after=stop)

        with patch.object(LlmCallManager, "execute", new=stop_during_settlement):
            with pytest.raises(RuntimeError, match=stop):
                graph.resume(context, state_file, through="S3_claims")

        journal_root = store.path(Path("runs") / run_id / "llm_journal")
        records = [
            path for path in journal_root.glob("*/attempt-*.json")
            if not path.name.endswith(".response.json")
        ]
        responses = list(journal_root.glob("*/attempt-*.response.json"))
        assert len(records) == len(responses) == 1
        journal_path = records[0].relative_to(store.root)
        response_path = responses[0].relative_to(store.root)
        record = store.read_json(journal_path)
        expected_states = {
            "S1": "submitted",
            "S2": "settling",
            "S3": "settling",
            "S4": "completed",
        }
        assert record["state"] == expected_states[stop]
        ledger = BudgetLedger(store, config)
        events = ledger.read_events(record["ledger_month"])
        expected_events = ["reserve"] if stop in {"S1", "S2"} else ["reserve", "settle"]
        assert [event["event"] for event in events] == expected_events
        assert len(transport.requests) == 1
        return config, store, run_id, transport, llm_client, journal_path, response_path, record

    @staticmethod
    def _settlement_snapshot(store, ledger, journal_path, response_path, record):
        paths = {
            "approval": ledger.approval_path(record["ledger_month"], record["reservation_id"]),
            "ledger": ledger.ledger_path(record["ledger_month"]),
            "journal": journal_path,
            "response": response_path,
        }
        return {
            key: store.read_bytes(path) if store.exists(path) else None
            for key, path in paths.items()
        }

    def test_cli_budget_check_recovers_settlement_and_resume_reuses_response(self):
        for stop in ("S1", "S2", "S3", "S4"):
            with self.subTest(stop=stop):
                self.tearDown()
                self.setUp()
                config, store, run_id, transport, llm_client, journal_path, response_path, record = (
                    self._settlement_stop_cli_run(stop)
                )
                ledger = BudgetLedger(store, config)
                other_path, other = self._add_other_approved_reservation(
                    store, ledger, f"other_run_{stop.lower()}", record
                )
                other_before = self._other_run_snapshot(
                    store, ledger, other_path, other
                )
                before_check = self._settlement_snapshot(
                    store, ledger, journal_path, response_path, record
                )
                exit_code, stdout, stderr = self._reconcile_cli(["budget", "check"])
                assert exit_code == 0, stderr
                actions = json.loads(stdout)["actions"]
                assert [item["action"] for item in actions] == (
                    ["restore_settle"] if stop == "S2" else []
                )
                assert self._settlement_snapshot(
                    store, ledger, journal_path, response_path, record
                ) == before_check

                exit_code, stdout, stderr = self._reconcile_cli(["budget", "check", "--apply"])
                assert exit_code == 0, stderr
                applied_actions = json.loads(stdout)["actions"]
                assert [item["action"] for item in applied_actions] == (
                    ["restore_settle"] if stop == "S2" else []
                )
                after_apply = self._settlement_snapshot(
                    store, ledger, journal_path, response_path, record
                )
                assert after_apply["journal"] == before_check["journal"]
                assert after_apply["response"] == before_check["response"]
                assert after_apply["approval"] == before_check["approval"]
                events = ledger.read_events(record["ledger_month"])
                target_events = [
                    event for event in events
                    if event["reservation_id"] == record["reservation_id"]
                ]
                expected_settles = 0 if stop == "S1" else 1
                assert sum(event["event"] == "reserve" for event in target_events) == 1
                assert sum(event["event"] == "settle" for event in target_events) == expected_settles
                assert self._other_run_snapshot(
                    store, ledger, other_path, other
                ) == other_before

                exit_code, stdout, stderr = self._reconcile_cli(["budget", "check", "--apply"])
                assert exit_code == 0, stderr
                assert json.loads(stdout)["actions"] == []
                assert ledger.read_events(record["ledger_month"]) == events

                with (
                    patch("scripts.article_pipeline.__main__.repo_root", return_value=self.root),
                    patch("scripts.article_pipeline.claims_extract.LlmClient", return_value=llm_client),
                ):
                    exit_code = main(["resume", "--run", run_id, "--through", "S3_claims"])
                assert exit_code == 0
                assert len(transport.requests) == 1
                assert store.read_bytes(response_path) == before_check["response"]
                final_events = ledger.read_events(record["ledger_month"])
                final_target_events = [
                    event for event in final_events
                    if event["reservation_id"] == record["reservation_id"]
                ]
                assert sum(event["event"] == "reserve" for event in final_target_events) == 1
                assert sum(event["event"] == "settle" for event in final_target_events) == 1
                extracted = store.read_json(Path("runs") / run_id / "claims.extracted.json")
                assert extracted["calls"][0]["reused_from_journal"] is (stop == "S4")
                assert self._other_run_snapshot(
                    store, ledger, other_path, other
                ) == other_before

                for _repeat in range(2):
                    exit_code, stdout, stderr = self._reconcile_cli(["budget", "check", "--apply"])
                    assert exit_code == 0, stderr
                    assert json.loads(stdout)["actions"] == []
                    with (
                        patch("scripts.article_pipeline.__main__.repo_root", return_value=self.root),
                        patch("scripts.article_pipeline.claims_extract.LlmClient", return_value=llm_client),
                    ):
                        exit_code = main(["resume", "--run", run_id, "--through", "S3_claims"])
                    assert exit_code == 0
                    assert len(transport.requests) == 1
                    assert ledger.read_events(record["ledger_month"]) == final_events
                    assert self._other_run_snapshot(
                        store, ledger, other_path, other
                    ) == other_before

    def test_cli_budget_check_rejects_invalid_settlement_recovery_without_changes(self):
        cases = {
            "amount": "応答から再計算した金額がジャーナルと一致しません",
            "response_missing": "精算を復元できる応答がありません",
            "response_modified": "精算を復元できる応答がありません",
            "approval_missing": "承認記録がないのに reserved 以降のジャーナルがあります",
        }
        for case, expected in cases.items():
            with self.subTest(case=case):
                self.tearDown()
                self.setUp()
                config, store, run_id, transport, llm_client, journal_path, response_path, record = (
                    self._settlement_stop_cli_run("S2")
                )
                ledger = BudgetLedger(store, config)
                if case == "amount":
                    record["actual_usd"] = "9.000000000000"
                    store.write_json(journal_path, record)
                elif case == "response_missing":
                    store.remove(response_path)
                elif case == "response_modified":
                    store.write_json(response_path, {"modified": True})
                else:
                    store.remove(ledger.approval_path(record["ledger_month"], record["reservation_id"]))
                before = self._settlement_snapshot(
                    store, ledger, journal_path, response_path, record
                )
                commands = [
                    ["budget", "check"],
                    ["budget", "check", "--apply"],
                    ["resume", "--run", run_id, "--through", "S3_claims"],
                ]
                with (
                    patch("scripts.article_pipeline.__main__.repo_root", return_value=self.root),
                    patch("scripts.article_pipeline.claims_extract.LlmClient", return_value=llm_client),
                ):
                    for command in commands:
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                            exit_code = main(command)
                        assert exit_code == 1
                        assert expected in stderr.getvalue()
                        assert self._settlement_snapshot(
                            store, ledger, journal_path, response_path, record
                        ) == before
                        assert len(transport.requests) == 1


def test_production_graph_has_split_claim_stages_and_dependencies():
    graph = PipelineGraph(build_production_stages())
    assert graph.stage_names == ["S0_intake", "S1_plan", "S2_sources", "S3_claims", "S3_support", "S4_write", "S5_code", "S6_verify", "S7_verdict"]
    assert graph.by_name["S4_write"].dependencies == ("S3_support",)
    assert graph.by_name["S6_verify"].dependencies == ("S2_sources", "S3_claims", "S3_support", "S4_write", "S5_code")
