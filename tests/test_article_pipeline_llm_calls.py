from datetime import datetime, timezone
from decimal import Decimal
import json
from unittest.mock import patch

import pytest

from scripts.article_pipeline import PipelineError
from scripts.article_pipeline.budget import BudgetLedger
from scripts.article_pipeline.llm_calls import (
    LlmCallManager,
    build_logical_content,
    logical_key,
    nonce_for,
)
from scripts.article_pipeline.llm_client import LlmApiError, LlmClient
from scripts.article_pipeline.store import RunStore
from tests.article_pipeline_helpers import CONFIG


class MockTransport:
    def __init__(self):
        self.counts = 0; self.creates = 0; self.retrieves = 0
        self.response = {
            "id": "resp_1", "status": "completed", "output_text": '{"ok":true}',
            "usage": {"input_tokens": 100, "output_tokens": 10, "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0}},
        }

    def count_input_tokens(self, request, *, timeout):
        self.counts += 1; return {"input_tokens": 100}

    def create_response(self, request, *, timeout):
        self.creates += 1; self.last_request = request; return dict(self.response)

    def retrieve_response(self, response_id, *, timeout):
        self.retrieves += 1; return dict(self.response)

    def cancel_response(self, response_id, *, timeout):
        return {**self.response, "status": "cancelled"}


def setup(tmp_path):
    (tmp_path / "run/article_pipeline/runs/run-a").mkdir(parents=True)
    config = json.loads(CONFIG)
    config["llm"]["store"] = False
    config["llm"]["pricing"]["max_age_days"] = 3650
    config["llm"]["pricing"]["models"]["test-model"]["checked_at"] = datetime.now(timezone.utc).date().isoformat()
    config["budget"] = {"monthly_limit_usd": 10, "run_limit_usd": 5, "call_limit_usd": 2}
    stage = {"model": "test-model", "reasoning_effort": "low", "max_output_tokens": 100, "expected_output_tokens": 20}
    transport = MockTransport(); store = RunStore(tmp_path)
    return config, stage, transport, store, LlmCallManager(store, config, LlmClient(transport))


def invoke(manager, stage, **kwargs):
    return manager.execute(
        run_id="run-a", slug="sample", stage="S3_claims", slot="extract:S001-S001",
        stage_config=stage, instructions="fixed", output_schema={"type": "object"},
        schema_name="test", payload={"sources": [{"source_id": "S001", "hash": "x"}]},
        render=lambda payload, nonce: f"<<<SOURCE S001 {nonce}>>>data<<<END SOURCE S001 {nonce}>>>",
        **kwargs,
    )


@pytest.mark.parametrize("field", ["store", "model", "budget", "pricing"])
def test_unresolved_values_stop_before_token_count(tmp_path, field):
    config, stage, transport, _store, manager = setup(tmp_path)
    if field == "store": config["llm"]["store"] = None
    elif field == "model": stage["model"] = None
    elif field == "budget": config["budget"]["run_limit_usd"] = None
    else: config["llm"]["pricing"]["max_age_days"] = None
    with pytest.raises(PipelineError, match="未決定"):
        invoke(manager, stage)
    assert transport.counts == transport.creates == 0


def test_logical_key_excludes_attempt_metadata_and_nonce():
    value = {"schema": "llm_logical_key/v1", "slot": "x", "payload_sha256": "sha256:x"}
    key = logical_key(value)
    assert key == logical_key(dict(value))
    assert nonce_for(key) == nonce_for(key)
    for forbidden in ("attempt", "metadata", "nonce", "pricing", "sdk_version"):
        with pytest.raises(PipelineError, match="禁止キー"):
            logical_key({**value, forbidden: "x"})


def test_logical_key_is_stable_and_changes_for_each_content_input():
    stage = {
        "model": "test-model",
        "reasoning_effort": "low",
        "max_output_tokens": 100,
    }
    base = build_logical_content(
        run_id="run-a",
        stage="S3_claims",
        slot="extract:S001-S001",
        stage_config=stage,
        instructions_sha256="sha256:prompt",
        output_schema_sha256="sha256:schema",
        payload_sha256="sha256:source-body",
    )
    expected = logical_key(base)
    assert logical_key(dict(base)) == expected
    variants = [
        {**base, "slot": "extract:S002-S002"},
        {**base, "model": "another-model"},
        {**base, "max_output_tokens": 101},
        {**base, "instructions_sha256": "sha256:other-prompt"},
        {**base, "output_schema_sha256": "sha256:other-schema"},
        {**base, "payload_sha256": "sha256:other-source-body"},
    ]
    assert len({logical_key(value) for value in variants}) == len(variants)
    assert all(logical_key(value) != expected for value in variants)


@pytest.mark.parametrize("stop", ["R1", "R3", "R4"])
def test_budget_stop_positions_resume_with_one_reserve_and_one_send(tmp_path, stop):
    config, stage, transport, store, manager = setup(tmp_path)
    with pytest.raises(RuntimeError):
        invoke(manager, stage, stop_after=stop)
    result = invoke(manager, stage)
    result2 = invoke(manager, stage)
    assert result.response["id"] == "resp_1" and result2.reused_from_journal is True
    assert transport.creates == 1
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    events = BudgetLedger(store, config).read_events(month)
    assert [event["event"] for event in events] == ["reserve", "settle"]


def test_reserved_stop_becomes_unknown_and_never_resends_implicitly(tmp_path):
    config, stage, transport, store, manager = setup(tmp_path)
    with pytest.raises(RuntimeError):
        invoke(manager, stage, stop_after="R5")
    with pytest.raises(PipelineError, match="自動再送しません"):
        invoke(manager, stage)
    with pytest.raises(PipelineError, match="結果不明"):
        invoke(manager, stage)
    assert transport.creates == 0
    events = BudgetLedger(store, config).read_events(datetime.now(timezone.utc).strftime("%Y-%m"))
    assert [event["event"] for event in events] == ["reserve", "outcome_unknown"]


def test_explicit_retry_of_unknown_uses_attempt_two_and_keeps_first_reservation(tmp_path):
    config, stage, transport, store, manager = setup(tmp_path)
    with pytest.raises(RuntimeError):
        invoke(manager, stage, stop_after="R5")
    with pytest.raises(PipelineError, match="自動再送しません"):
        invoke(manager, stage)
    result = invoke(manager, stage, retry_unknown=True)
    assert result.attempt == 2 and transport.creates == 1
    events = BudgetLedger(store, config).read_events(datetime.now(timezone.utc).strftime("%Y-%m"))
    assert [event["event"] for event in events] == ["reserve", "outcome_unknown", "reserve", "settle"]


def test_submitted_resume_retrieves_without_create_and_without_double_accounting(tmp_path):
    config, stage, transport, store, manager = setup(tmp_path)
    with pytest.raises(RuntimeError):
        invoke(manager, stage, stop_after="R7")
    result = invoke(manager, stage)
    assert result.response["id"] == "resp_1"
    assert transport.creates == 1 and transport.retrieves == 1
    assert invoke(manager, stage).reused_from_journal is True
    events = BudgetLedger(store, config).read_events(datetime.now(timezone.utc).strftime("%Y-%m"))
    assert [event["event"] for event in events] == ["reserve", "settle"]


@pytest.mark.parametrize("stop", ["S1", "S2", "S3"])
def test_settlement_stop_positions_reuse_saved_response_and_single_settle(tmp_path, stop):
    config, stage, transport, store, manager = setup(tmp_path)
    with pytest.raises(RuntimeError):
        invoke(manager, stage, stop_after=stop)
    invoke(manager, stage); invoke(manager, stage)
    assert transport.creates == 1 and transport.retrieves == 0
    events = BudgetLedger(store, config).read_events(datetime.now(timezone.utc).strftime("%Y-%m"))
    assert [event["event"] for event in events] == ["reserve", "settle"]


def test_nonce_in_payload_stops_before_send(tmp_path):
    _config, stage, transport, _store, manager = setup(tmp_path)
    with patch("scripts.article_pipeline.llm_calls.nonce_for", return_value="forbidden"):
        with pytest.raises(PipelineError, match="nonce"):
            manager.execute(
                run_id="run-a", slug="sample", stage="S3_claims", slot="x", stage_config=stage,
                instructions="fixed", output_schema={"type": "object"}, schema_name="test",
                payload={"source_text": "contains forbidden delimiter"}, render=lambda payload, nonce: nonce,
            )
    assert transport.creates == 0


@pytest.mark.parametrize(
    "error",
    [
        LlmApiError("create", "disconnect"),
        LlmApiError("create", "timeout"),
        LlmApiError("create", "overloaded", status_code=503),
    ],
    ids=("connection", "timeout", "5xx"),
)
def test_create_connection_failure_is_unknown_and_is_not_resent(tmp_path, error):
    config, stage, transport, store, manager = setup(tmp_path)
    def fail(request, *, timeout):
        transport.creates += 1
        raise error
    transport.create_response = fail
    with pytest.raises(PipelineError, match="結果が不明"):
        invoke(manager, stage)
    with pytest.raises(PipelineError, match="結果不明"):
        invoke(manager, stage)
    assert transport.creates == 1
    events = BudgetLedger(store, config).read_events(datetime.now(timezone.utc).strftime("%Y-%m"))
    assert [event["event"] for event in events] == ["reserve", "outcome_unknown"]


def test_temporary_429_keeps_reservation_and_retries_as_new_attempt(tmp_path):
    config, stage, transport, store, manager = setup(tmp_path)
    original = transport.create_response
    requests = []
    def once(request, *, timeout):
        requests.append(request)
        if transport.creates == 0:
            transport.creates += 1
            raise LlmApiError("create", "slow", status_code=429, code="rate_limit", retry_after=0)
        return original(request, timeout=timeout)
    transport.create_response = once
    result = invoke(manager, stage)
    assert result.attempt == 2 and transport.creates == 2
    first, second = requests
    assert first["metadata"]["logical_key"] == second["metadata"]["logical_key"]
    assert first["metadata"]["attempt"] == "1"
    assert second["metadata"]["attempt"] == "2"
    without_attempt = lambda request: {
        **request,
        "metadata": {
            key: value
            for key, value in request["metadata"].items()
            if key != "attempt"
        },
    }
    assert without_attempt(first) == without_attempt(second)
    events = BudgetLedger(store, config).read_events(datetime.now(timezone.utc).strftime("%Y-%m"))
    assert [event["event"] for event in events] == ["reserve", "reserve", "settle"]
    key = next(manager.store.path("runs/run-a/llm_journal").iterdir()).name
    attempts = manager._attempts("run-a", key)
    assert attempts[0]["state"] == "rejected"
    assert attempts[0]["api_outcome"] == "rejected"
    assert attempts[0]["billing_status"] == "unreconciled"
    assert attempts[0]["actual_usd"] is None
    assert attempts[1]["state"] == "completed"
    counted, runs = BudgetLedger(store, config).counted(attempts[0]["ledger_month"])
    assert counted == Decimal(attempts[0]["proposed_reserve_usd"]) + Decimal(attempts[1]["actual_usd"])
    assert runs["run-a"] == counted


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422, 429])
def test_rejected_4xx_keeps_reservation_and_resume_does_not_retry(tmp_path, status):
    config, stage, transport, store, manager = setup(tmp_path)
    if status == 429:
        config["llm"]["max_retries"] = 0
    def reject(request, *, timeout):
        transport.creates += 1
        raise LlmApiError("create", "rejected", status_code=status, code="rate_limit" if status == 429 else "bad_request")
    transport.create_response = reject
    with pytest.raises(PipelineError):
        invoke(manager, stage)
    for _repeat in range(3):
        with pytest.raises(PipelineError, match="自動再試行しません"):
            invoke(manager, stage)
    assert transport.creates == 1
    events = BudgetLedger(store, config).read_events(datetime.now(timezone.utc).strftime("%Y-%m"))
    assert [event["event"] for event in events] == ["reserve"]
    key = next(manager.store.path("runs/run-a/llm_journal").iterdir()).name
    record = manager._attempts("run-a", key)[0]
    assert record["state"] == "rejected"
    assert record["api_outcome"] == "rejected"
    assert record["billing_status"] == "unreconciled"
    assert record["http_status"] == status
    assert record["actual_usd"] is None
    counted, runs = BudgetLedger(store, config).counted(record["ledger_month"])
    assert counted == Decimal(record["proposed_reserve_usd"])
    assert runs == {"run-a": counted}


def test_spend_limit_429_never_retries_and_keeps_reservation(tmp_path):
    config, stage, transport, store, manager = setup(tmp_path)
    def reject(request, *, timeout):
        transport.creates += 1
        raise LlmApiError("create", "limit", status_code=429, code="project_spend_limit_exceeded")
    transport.create_response = reject
    with pytest.raises(PipelineError, match="再試行できない"):
        invoke(manager, stage)
    assert transport.creates == 1
    events = BudgetLedger(store, config).read_events(datetime.now(timezone.utc).strftime("%Y-%m"))
    assert [event["event"] for event in events] == ["reserve"]


def test_temporary_429_previous_reservation_is_included_in_retry_budget(tmp_path):
    config, stage, transport, store, manager = setup(tmp_path)
    config["budget"] = {
        "monthly_limit_usd": "10",
        "run_limit_usd": "0.002",
        "call_limit_usd": "2",
    }

    def reject_once(request, *, timeout):
        transport.creates += 1
        raise LlmApiError(
            "create", "slow", status_code=429, code="rate_limit", retry_after=0,
        )

    transport.create_response = reject_once
    with pytest.raises(PipelineError, match="budget_exceeded"):
        invoke(manager, stage)
    assert transport.creates == 1
    key = next(manager.store.path("runs/run-a/llm_journal").iterdir()).name
    attempts = manager._attempts("run-a", key)
    assert [record["state"] for record in attempts] == ["rejected", "budget_rejected"]
    assert attempts[0]["billing_status"] == "unreconciled"
    events = BudgetLedger(store, config).read_events(attempts[0]["ledger_month"])
    assert [event["event"] for event in events] == ["reserve"]
    assert BudgetLedger(store, config).counted_for_run("run-a") == Decimal(
        attempts[0]["proposed_reserve_usd"]
    )

    with pytest.raises(PipelineError, match="budget_exceeded"):
        invoke(manager, stage)
    assert transport.creates == 1
    assert len(manager._attempts("run-a", key)) == 2
    assert BudgetLedger(store, config).read_events(attempts[0]["ledger_month"]) == events


def test_retrieve_5xx_retries_only_retrieve(tmp_path):
    _config, stage, transport, _store, manager = setup(tmp_path)
    terminal = dict(transport.response)
    transport.create_response = lambda request, timeout: ({"id": "resp_1", "status": "in_progress"})
    calls = {"n": 0}
    def retrieve(response_id, *, timeout):
        transport.retrieves += 1; calls["n"] += 1
        if calls["n"] == 1:
            raise LlmApiError("retrieve", "overloaded", status_code=503)
        return terminal
    transport.retrieve_response = retrieve
    result = invoke(manager, stage)
    assert result.response["status"] == "completed"
    assert transport.retrieves == 2


def test_retrieve_404_becomes_unknown_without_resend(tmp_path):
    _config, stage, transport, _store, manager = setup(tmp_path)
    transport.create_response = lambda request, timeout: ({"id": "resp_1", "status": "in_progress"})
    def missing(response_id, *, timeout):
        transport.retrieves += 1
        raise LlmApiError("retrieve", "gone", status_code=404)
    transport.retrieve_response = missing
    with pytest.raises(PipelineError, match="照合待ち"):
        invoke(manager, stage)
    assert transport.retrieves == 1


def test_deadline_cancels_then_settles_terminal_response(tmp_path):
    config, stage, transport, _store, manager = setup(tmp_path)
    config["llm"]["call_deadline_s"] = 0
    transport.create_response = lambda request, timeout: ({"id": "resp_1", "status": "in_progress"})
    transport.cancelled = 0
    def cancel(response_id, *, timeout):
        transport.cancelled += 1
        return {"id": response_id, "status": "cancelling"}
    transport.cancel_response = cancel
    transport.response["status"] = "cancelled"
    result = invoke(manager, stage)
    assert result.response["status"] == "cancelled" and transport.cancelled == 1


def test_incomplete_is_settled_and_never_automatically_retried(tmp_path):
    _config, stage, transport, _store, manager = setup(tmp_path)
    transport.response["status"] = "incomplete"
    first = invoke(manager, stage)
    second = invoke(manager, stage)
    assert first.response["status"] == "incomplete" and second.reused_from_journal is True
    assert transport.creates == 1


def test_wire_change_without_renderer_version_bump_stops_resume(tmp_path):
    _config, stage, _transport, _store, manager = setup(tmp_path)
    with pytest.raises(RuntimeError):
        invoke(manager, stage, stop_after="R1")
    with pytest.raises(PipelineError, match="wire_sha256"):
        manager.execute(
            run_id="run-a", slug="sample", stage="S3_claims", slot="extract:S001-S001",
            stage_config=stage, instructions="fixed", output_schema={"type": "object"},
            schema_name="test", payload={"sources": [{"source_id": "S001", "hash": "x"}]},
            render=lambda payload, nonce: f"changed {nonce}",
        )


def test_budget_rejection_stop_before_journal_update_rechecks_same_attempt(tmp_path):
    config, stage, transport, _store, manager = setup(tmp_path)
    config["budget"]["call_limit_usd"] = "0.0001"
    with pytest.raises(RuntimeError, match="R2"):
        invoke(manager, stage, stop_after="R2x")
    with pytest.raises(PipelineError, match="budget_exceeded"):
        invoke(manager, stage)
    attempts = manager._attempts("run-a", next((manager.store.path("runs/run-a/llm_journal")).iterdir()).name)
    assert len(attempts) == 1 and attempts[0]["attempt"] == 1 and transport.creates == 0


def test_previous_month_cost_can_reject_before_send(tmp_path):
    config, stage, transport, store, manager = setup(tmp_path)
    config["budget"] = {"monthly_limit_usd": "10", "run_limit_usd": "0.1001", "call_limit_usd": "2"}
    previous = {
        "reservation_id": "rsv_previous", "settlement_id": "stl_previous",
        "attempt_key": "previous", "ledger_month": "2026-08", "run_id": "run-a",
        "slug": "sample", "stage": "S3_claims", "logical_key": "previous",
        "attempt": 1, "wire_sha256": "sha256:previous", "amount_usd": "0.1",
    }
    BudgetLedger(store, config).approve_and_reserve(previous)
    with pytest.raises(PipelineError, match="budget_exceeded"):
        invoke(manager, stage)
    assert transport.counts == 1 and transport.creates == 0


def test_secret_environment_value_is_never_persisted(tmp_path, monkeypatch):
    _config, stage, _transport, store, manager = setup(tmp_path)
    secret = "sk-test-never-persist-this-value"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    invoke(manager, stage)
    for path in store.path("runs/run-a").rglob("*"):
        if path.is_file():
            assert secret.encode() not in path.read_bytes()
