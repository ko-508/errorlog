from datetime import datetime, timezone
from decimal import Decimal
import json
import multiprocessing
from pathlib import Path

import pytest

from scripts.article_pipeline import PipelineError
from scripts.article_pipeline.budget import BudgetLedger, actual_cost, estimate_cost, reserve_cost
from scripts.article_pipeline.store import RunStore, sha256_bytes
from tests.article_pipeline_helpers import CONFIG


def _reserve_worker(root, config, item, gate, results):
    gate.wait()
    try:
        BudgetLedger(RunStore(Path(root)), config).approve_and_reserve(item)
        results.put("approved")
    except PipelineError as exc:
        results.put("rejected" if "予算上限" in str(exc) else f"error:{exc}")


def configured(tmp_path):
    (tmp_path / "run/article_pipeline").mkdir(parents=True)
    config = json.loads(CONFIG)
    config["llm"]["pricing"]["max_age_days"] = 3650
    config["llm"]["pricing"]["models"]["test-model"]["checked_at"] = datetime.now(timezone.utc).date().isoformat()
    config["budget"] = {"monthly_limit_usd": 10, "run_limit_usd": 5, "call_limit_usd": 2}
    return config, RunStore(tmp_path)


def proposal(amount="0.100000000000"):
    logical_key = "key"
    attempt_key = sha256_bytes(
        f"attempt/v1:{logical_key}:1".encode()
    ).removeprefix("sha256:")
    return {
        "reservation_id": "rsv_" + attempt_key,
        "settlement_id": "stl_" + attempt_key,
        "attempt_key": attempt_key,
        "ledger_month": datetime.now(timezone.utc).strftime("%Y-%m"), "run_id": "run-a",
        "slug": "sample", "stage": "S3_claims", "logical_key": logical_key, "attempt": 1,
        "wire_sha256": "sha256:wire", "amount_usd": amount,
    }


def for_month(item, month, suffix):
    logical_key = f"key-{suffix}"
    attempt_key = sha256_bytes(
        f"attempt/v1:{logical_key}:1".encode()
    ).removeprefix("sha256:")
    return {
        **item,
        "ledger_month": month,
        "reservation_id": "rsv_" + attempt_key,
        "settlement_id": "stl_" + attempt_key,
        "attempt_key": attempt_key,
        "logical_key": logical_key,
        "wire_sha256": f"sha256:{suffix}",
    }


def write_journal(store, item, *, state="proposed", wire=None, actual=None):
    record = {
        "schema": "llm_attempt/v2", "logical_key": item["logical_key"], "attempt": item["attempt"],
        "attempt_key": item["attempt_key"], "reservation_id": item["reservation_id"],
        "settlement_id": item["settlement_id"], "ledger_month": item["ledger_month"],
        "state": state, "wire_sha256": wire or item["wire_sha256"],
        "proposed_reserve_usd": item["amount_usd"], "run_id": item["run_id"],
        "slug": item["slug"], "stage": item["stage"], "model": "test-model",
        "actual_usd": actual, "response_sha256": None,
    }
    store.write_json(f"runs/{item['run_id']}/llm_journal/{item['logical_key']}/attempt-1.json", record)
    return record


def test_decimal_costs_cache_write_and_long_context(tmp_path):
    config, _store = configured(tmp_path)
    pricing = config["llm"]["pricing"]
    assert estimate_cost(pricing, "test-model", 100, 20) == Decimal("0.0004")
    reserve, short = reserve_cost(pricing, "test-model", 100, 20)
    assert reserve == Decimal("0.00045") and short["band"] == "short"
    _reserve, long = reserve_cost(pricing, "test-model", 272001, 20)
    assert long["band"] == "long"
    assert actual_cost(pricing, "test-model", {"input_tokens": 100, "output_tokens": 20, "input_tokens_details": {"cached_tokens": 30, "cache_write_tokens": 10}}) == Decimal("0.000348")


def test_unknown_stale_and_unresolved_pricing_stop(tmp_path):
    config, _store = configured(tmp_path); pricing = config["llm"]["pricing"]
    with pytest.raises(PipelineError, match="単価がありません"):
        reserve_cost(pricing, "missing", 1, 1)
    pricing["max_age_days"] = None
    with pytest.raises(PipelineError, match="未決定"):
        reserve_cost(pricing, "test-model", 1, 1)
    pricing["max_age_days"] = 1
    pricing["models"]["test-model"]["checked_at"] = "2020-01-01"
    with pytest.raises(PipelineError, match="古すぎ"):
        reserve_cost(pricing, "test-model", 1, 1)


@pytest.mark.parametrize("stop", ["R3", "R4"])
def test_approval_and_reserve_resume_is_idempotent(tmp_path, stop):
    config, store = configured(tmp_path); ledger = BudgetLedger(store, config); item = proposal()
    with pytest.raises(RuntimeError):
        ledger.approve_and_reserve(item, stop_after=stop)
    ledger.approve_and_reserve(item)
    ledger.approve_and_reserve(item)
    events = ledger.read_events(item["ledger_month"])
    assert [event["event"] for event in events] == ["reserve"]
    assert len(ledger._all_approvals(item["ledger_month"])) == 1


def test_unsettled_approval_is_counted_and_limit_rejects(tmp_path):
    config, store = configured(tmp_path); config["budget"]["monthly_limit_usd"] = "0.15"
    ledger = BudgetLedger(store, config)
    with pytest.raises(RuntimeError):
        ledger.approve_and_reserve(proposal("0.1"), stop_after="R3")
    second = {**proposal("0.1"), "reservation_id": "rsv_b", "settlement_id": "stl_b", "attempt_key": "b", "wire_sha256": "sha256:b"}
    with pytest.raises(PipelineError, match="予算上限"):
        ledger.approve_and_reserve(second)
    assert ledger.read_approval(second["ledger_month"], "rsv_b") is None


def test_run_limit_counts_approved_reservation_from_previous_month(tmp_path):
    config, store = configured(tmp_path)
    config["budget"] = {"monthly_limit_usd": "10", "run_limit_usd": "1", "call_limit_usd": "1"}
    ledger = BudgetLedger(store, config)
    previous = for_month(proposal("0.6"), "2026-08", "previous")
    current = for_month(proposal("0.5"), "2026-09", "current")
    with pytest.raises(RuntimeError):
        ledger.approve_and_reserve(previous, stop_after="R3")
    with pytest.raises(PipelineError, match="予算上限"):
        ledger.approve_and_reserve(current)
    assert ledger.read_approval(current["ledger_month"], current["reservation_id"]) is None


def test_run_limit_counts_unreconciled_reservation_from_previous_month(tmp_path):
    config, store = configured(tmp_path)
    config["budget"] = {"monthly_limit_usd": "10", "run_limit_usd": "1", "call_limit_usd": "1"}
    ledger = BudgetLedger(store, config)
    previous = for_month(proposal("0.7"), "2026-08", "previous")
    current = for_month(proposal("0.4"), "2026-09", "current")
    ledger.approve_and_reserve(previous)
    ledger.outcome_unknown(previous)
    with pytest.raises(PipelineError, match="予算上限"):
        ledger.approve_and_reserve(current)


@pytest.mark.parametrize(
    ("event", "actual", "current_amount", "expected_total"),
    [
        ("settle", "0.2", "0.7", Decimal("0.9")),
        ("reconcile", "0.3", "0.6", Decimal("0.9")),
        ("release", "0", "0.9", Decimal("0.9")),
    ],
)
def test_run_limit_uses_previous_month_final_amount(tmp_path, event, actual, current_amount, expected_total):
    config, store = configured(tmp_path)
    config["budget"] = {"monthly_limit_usd": "10", "run_limit_usd": "1", "call_limit_usd": "1"}
    ledger = BudgetLedger(store, config)
    previous = for_month(proposal("0.8"), "2026-08", "previous")
    current = for_month(proposal(current_amount), "2026-09", "current")
    ledger.approve_and_reserve(previous)
    ledger.settle(previous, Decimal(actual), event=event, note="test" if event == "release" else None)
    ledger.approve_and_reserve(current)
    assert ledger.counted_for_run("run-a") == expected_total


def test_month_limit_does_not_count_other_months(tmp_path):
    config, store = configured(tmp_path)
    config["budget"] = {"monthly_limit_usd": "0.8", "run_limit_usd": "2", "call_limit_usd": "1"}
    ledger = BudgetLedger(store, config)
    previous = for_month(proposal("0.7"), "2026-08", "previous")
    current = for_month(proposal("0.7"), "2026-09", "current")
    ledger.approve_and_reserve(previous)
    ledger.approve_and_reserve(current)
    current_total, _runs = ledger.counted("2026-09")
    assert current_total == Decimal("0.7")
    assert ledger.counted_for_run("run-a") == Decimal("1.4")


def test_settlement_replay_does_not_double_count(tmp_path):
    config, store = configured(tmp_path); ledger = BudgetLedger(store, config); item = proposal()
    ledger.approve_and_reserve(item)
    assert ledger.settle(item, Decimal("0.04")) is True
    assert ledger.settle(item, Decimal("0.04")) is False
    assert [event["event"] for event in ledger.read_events(item["ledger_month"])] == ["reserve", "settle"]
    with pytest.raises(PipelineError, match="内容が異なる"):
        ledger.settle(item, Decimal("0.05"))


def test_torn_last_line_repairs_and_preserves_original(tmp_path):
    config, store = configured(tmp_path); ledger = BudgetLedger(store, config); item = proposal()
    ledger.approve_and_reserve(item)
    path = store.path(ledger.ledger_path(item["ledger_month"]))
    original = path.read_bytes() + b'{"partial"'
    path.write_bytes(original)
    with pytest.raises(PipelineError, match="途切れ"):
        ledger.read_events(item["ledger_month"])
    result = ledger.repair(item["ledger_month"])
    assert store.read_bytes(result["quarantine"]) == original
    assert len(ledger.read_events(item["ledger_month"])) == 1


def test_budget_lock_timeout_stops_without_unlocked_judgment(tmp_path):
    config, store = configured(tmp_path); store.create_exclusive_json("locks/budget.lock", {"pid": 1})
    with pytest.raises(PipelineError, match="予算ロック"):
        BudgetLedger(store, config).approve_and_reserve(proposal())
    assert BudgetLedger(store, config).read_approval(proposal()["ledger_month"], "rsv_a") is None


def test_settlement_for_nonexistent_reservation_stops(tmp_path):
    config, store = configured(tmp_path)
    with pytest.raises(PipelineError, match="存在しない予約"):
        BudgetLedger(store, config).settle(proposal(), Decimal("0.01"))


def test_repair_refuses_corruption_in_complete_line(tmp_path):
    config, store = configured(tmp_path); ledger = BudgetLedger(store, config); item = proposal()
    ledger.approve_and_reserve(item)
    path = store.path(ledger.ledger_path(item["ledger_month"]))
    damaged = b"!" + path.read_bytes()[1:] + b"partial"
    path.write_bytes(damaged)
    with pytest.raises(PipelineError):
        ledger.repair(item["ledger_month"])
    assert path.read_bytes() == damaged
    assert any(candidate.read_bytes() == damaged for candidate in store.path("budget/quarantine").glob("*.jsonl"))


def test_budget_check_restores_approved_reserve_once(tmp_path):
    config, store = configured(tmp_path); ledger = BudgetLedger(store, config); item = proposal()
    with pytest.raises(RuntimeError): ledger.approve_and_reserve(item, stop_after="R3")
    write_journal(store, item)
    first = ledger.check(apply=True); second = ledger.check(apply=True)
    assert [action["action"] for action in first["actions"]] == ["restore_reserve"]
    assert second["actions"] == []
    assert len(ledger.read_events(item["ledger_month"])) == 1


def test_budget_check_does_not_approve_unapproved_proposal(tmp_path):
    config, store = configured(tmp_path); ledger = BudgetLedger(store, config); item = proposal()
    write_journal(store, item)
    result = ledger.check(apply=True)
    assert result["actions"][0]["action"] == "recheck_unapproved"
    assert ledger.read_approval(item["ledger_month"], item["reservation_id"]) is None
    assert ledger.read_events(item["ledger_month"]) == []


def test_budget_check_rejects_approval_journal_mismatch(tmp_path):
    config, store = configured(tmp_path); ledger = BudgetLedger(store, config); item = proposal()
    with pytest.raises(RuntimeError): ledger.approve_and_reserve(item, stop_after="R3")
    write_journal(store, item, wire="sha256:different")
    with pytest.raises(PipelineError, match="一致しません"):
        ledger.check(apply=False)


def test_release_event_changes_counted_amount_to_zero(tmp_path):
    config, store = configured(tmp_path); ledger = BudgetLedger(store, config); item = proposal()
    ledger.approve_and_reserve(item)
    assert ledger.settle(item, Decimal(0), event="release", note="not sent") is True
    total, _runs = ledger.counted(item["ledger_month"])
    assert total == Decimal(0)


def test_two_spawned_processes_cannot_approve_past_shared_limit(tmp_path):
    config, store = configured(tmp_path)
    config["budget"] = {"monthly_limit_usd": "1.0", "run_limit_usd": "1.0", "call_limit_usd": "1.0"}
    first = proposal("0.75")
    second = {
        **proposal("0.75"), "reservation_id": "rsv_b", "settlement_id": "stl_b",
        "attempt_key": "b", "run_id": "run-b", "slug": "other", "logical_key": "key-b",
        "wire_sha256": "sha256:b",
    }
    context = multiprocessing.get_context("spawn")
    gate = context.Event(); results = context.Queue()
    processes = [
        context.Process(target=_reserve_worker, args=(str(tmp_path), config, item, gate, results))
        for item in (first, second)
    ]
    for process in processes: process.start()
    gate.set()
    for process in processes:
        process.join(15)
        assert process.exitcode == 0
    outcomes = sorted(results.get(timeout=2) for _ in processes)
    assert outcomes == ["approved", "rejected"]
    month = first["ledger_month"]
    assert len(BudgetLedger(store, config)._all_approvals(month)) == 1
    assert len(BudgetLedger(store, config).read_events(month)) == 1
