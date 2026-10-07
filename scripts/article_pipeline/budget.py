"""Decimal cost accounting, immutable approvals, and append-only budget ledger."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import os
from pathlib import Path
import platform
import time
from typing import Any

from . import PipelineError
from .store import RunStore, canonical_json_bytes, sha256_bytes


MILLION = Decimal("1000000")
EVENTS = {"reserve", "settle", "outcome_unknown", "reconcile", "release"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def decimal_value(value: Any, *, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise PipelineError(f"金額を Decimal として読めません: field={label}, value={value!r}") from exc
    if not result.is_finite() or result < 0:
        raise PipelineError(f"金額は0以上の有限値が必要です: field={label}, value={value!r}")
    return result


def money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000000000001")), "f")


def _rates(pricing: dict[str, Any], model: str, input_tokens: int) -> tuple[dict[str, Any], dict[str, Any]]:
    model_price = pricing.get("models", {}).get(model)
    if not isinstance(model_price, dict):
        raise PipelineError(f"設定にモデルの単価がありません: model={model}")
    max_age = pricing.get("max_age_days")
    if max_age is None:
        raise PipelineError("設定 llm.pricing.max_age_days が未決定です: value=null")
    try:
        checked = date.fromisoformat(model_price["checked_at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PipelineError(f"単価の checked_at が不正です: model={model}") from exc
    if (datetime.now(timezone.utc).date() - checked).days > int(max_age):
        raise PipelineError(f"単価の確認日が古すぎます: model={model}, checked_at={checked}, max_age_days={max_age}")
    band = "long" if input_tokens > int(model_price["short_context_max_input_tokens"]) else "short"
    return model_price[band], {"model": model, "checked_at": model_price["checked_at"], "band": band}


def estimate_cost(pricing: dict[str, Any], model: str, input_tokens: int, expected_output_tokens: int) -> Decimal:
    rates, _ = _rates(pricing, model, input_tokens)
    return (Decimal(input_tokens) * decimal_value(rates["input"], label="input")
            + Decimal(expected_output_tokens) * decimal_value(rates["output"], label="output")) / MILLION


def reserve_cost(pricing: dict[str, Any], model: str, input_tokens: int, max_output_tokens: int) -> tuple[Decimal, dict[str, Any]]:
    rates, reference = _rates(pricing, model, input_tokens)
    input_rate = max(decimal_value(rates["input"], label="input"), decimal_value(rates["cache_write"], label="cache_write"))
    amount = (Decimal(input_tokens) * input_rate
              + Decimal(max_output_tokens) * decimal_value(rates["output"], label="output")) / MILLION
    return amount, reference


def actual_cost(pricing: dict[str, Any], model: str, usage: dict[str, Any]) -> Decimal:
    input_tokens = int(usage.get("input_tokens", 0))
    output_tokens = int(usage.get("output_tokens", 0))
    details = usage.get("input_tokens_details") or {}
    cached = int(details.get("cached_tokens", 0) or 0)
    written = int(details.get("cache_write_tokens", 0) or 0)
    regular = input_tokens - cached - written
    if min(input_tokens, output_tokens, cached, written, regular) < 0:
        raise PipelineError(f"usage のトークン内訳が不正です: usage={usage!r}")
    rates, _ = _rates(pricing, model, input_tokens)
    total = (
        Decimal(regular) * decimal_value(rates["input"], label="input")
        + Decimal(cached) * decimal_value(rates["cached_input"], label="cached_input")
        + Decimal(written) * decimal_value(rates["cache_write"], label="cache_write")
        + Decimal(output_tokens) * decimal_value(rates["output"], label="output")
    )
    return total / MILLION


def checked_record(value: dict[str, Any]) -> dict[str, Any]:
    body = dict(value)
    body.pop("chk", None)
    return {**body, "chk": sha256_bytes(canonical_json_bytes(body))}


def validate_checked(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("chk"), str):
        raise PipelineError(f"{label} の形式が不正です: value_type={type(value).__name__}")
    expected = checked_record(value)["chk"]
    if value["chk"] != expected:
        raise PipelineError(f"{label} の chk が一致しません: expected={expected}, actual={value['chk']}")
    return value


def validate_journal_identifiers(record: dict[str, Any]) -> None:
    logical_key = record.get("logical_key")
    attempt = record.get("attempt")
    if (
        not isinstance(logical_key, str)
        or not logical_key
        or not isinstance(attempt, int)
        or isinstance(attempt, bool)
        or attempt < 1
    ):
        raise PipelineError(
            "ジャーナルの派生識別子を計算できません: "
            f"logical_key={logical_key!r}, attempt={attempt!r}"
        )
    expected_attempt_key = sha256_bytes(
        f"attempt/v1:{logical_key}:{attempt}".encode()
    ).removeprefix("sha256:")
    expected = {
        "attempt_key": expected_attempt_key,
        "reservation_id": "rsv_" + expected_attempt_key,
        "settlement_id": "stl_" + expected_attempt_key,
    }
    differing = [
        key for key, value in expected.items()
        if record.get(key) != value
    ]
    if differing:
        raise PipelineError(
            "ジャーナルの派生識別子が一致しません: "
            f"logical_key={logical_key}, attempt={attempt}, differing={differing}, "
            f"expected={expected}"
        )


class BudgetLock(AbstractContextManager["BudgetLock"]):
    def __init__(self, store: RunStore, wait_s: float) -> None:
        self.store, self.wait_s, self.acquired = store, wait_s, False
        self.relative = Path("locks/budget.lock")

    def acquire(self) -> None:
        deadline = time.monotonic() + self.wait_s
        while True:
            try:
                self.store.create_exclusive_json(self.relative, {
                    "pid": os.getpid(), "hostname": platform.node(), "started_at": utc_now()
                })
                self.acquired = True
                return
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise PipelineError(f"予算ロックを取得できません: path={self.store.path(self.relative)}, wait_s={self.wait_s}")
                time.sleep(min(0.05, max(0.001, deadline - time.monotonic())))

    def release(self) -> None:
        if self.acquired:
            self.store.remove(self.relative)
            self.acquired = False

    def __enter__(self) -> "BudgetLock":
        self.acquire(); return self

    def __exit__(self, *_args: object) -> None:
        self.release()


class BudgetLedger:
    def __init__(self, store: RunStore, config: dict[str, Any]) -> None:
        self.store, self.config = store, config

    def ledger_path(self, month: str) -> Path:
        if not __import__("re").fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
            raise PipelineError(f"台帳の月が不正です: month={month!r}")
        return Path("budget") / f"{month}.jsonl"

    def approval_path(self, month: str, reservation_id: str) -> Path:
        return Path("budget/approvals") / month / f"{reservation_id}.json"

    def read_approval(self, month: str, reservation_id: str) -> dict[str, Any] | None:
        path = self.approval_path(month, reservation_id)
        if not self.store.exists(path): return None
        return validate_checked(self.store.read_json(path), label=f"承認記録 {path}")

    def read_events(self, month: str) -> list[dict[str, Any]]:
        path = self.store.path(self.ledger_path(month))
        if not path.exists(): return []
        data = path.read_bytes()
        if data and not data.endswith(b"\n"):
            raise PipelineError(f"予算台帳の最後の行が途切れています: path={path}; budget repair --month {month} --yes")
        events: list[dict[str, Any]] = []
        for line_number, raw in enumerate(data.splitlines(), 1):
            try:
                import json
                item = json.loads(raw.decode("utf-8"))
            except Exception as exc:
                raise PipelineError(f"予算台帳の行を解析できません: path={path}, line={line_number}, error={exc}") from exc
            item = validate_checked(item, label=f"予算台帳 {path}:{line_number}")
            if item.get("event") not in EVENTS:
                raise PipelineError(f"予算台帳に未知の出来事があります: event={item.get('event')!r}, line={line_number}")
            events.append(item)
        self._validate_events(month, events)
        return events

    def _validate_events(self, month: str, events: list[dict[str, Any]]) -> None:
        groups: dict[str, list[dict[str, Any]]] = {}
        for event in events: groups.setdefault(str(event.get("reservation_id")), []).append(event)
        for reservation, group in groups.items():
            reserves = [e for e in group if e["event"] == "reserve"]
            finals = [e for e in group if e["event"] in {"settle", "reconcile", "release"}]
            unknowns = [e for e in group if e["event"] == "outcome_unknown"]
            if len(reserves) != 1:
                raise PipelineError(f"予約の reserve が一意ではありません: reservation_id={reservation}, count={len(reserves)}")
            if len(finals) > 1 or len(unknowns) > 1:
                raise PipelineError(f"予約の出来事が重複しています: reservation_id={reservation}")
            approval = self.read_approval(month, reservation)
            if approval is None:
                raise PipelineError(f"承認記録のない reserve があります: reservation_id={reservation}")
            if decimal_value(approval["amount_usd"], label="approval.amount") != decimal_value(reserves[0]["amount_usd"], label="reserve.amount"):
                raise PipelineError(f"承認記録と reserve の金額が一致しません: reservation_id={reservation}")
            if approval.get("reservation_id") != reservation or approval.get("run_id") != reserves[0].get("run_id"):
                raise PipelineError(f"承認記録と reserve の識別子が一致しません: reservation_id={reservation}")
            expected_approval_sha = sha256_bytes(canonical_json_bytes(approval))
            if reserves[0].get("approval_sha256") != expected_approval_sha:
                raise PipelineError(
                    "承認記録と reserve のハッシュが一致しません: "
                    f"reservation_id={reservation}, expected={expected_approval_sha}, "
                    f"actual={reserves[0].get('approval_sha256')}"
                )

    def append_event(self, month: str, event: dict[str, Any]) -> bool:
        events = self.read_events(month)
        same = [e for e in events if e.get("event_id") == event.get("event_id")]
        proposed = checked_record(event)
        if same:
            # ``at`` is observational metadata.  A crash replay constructs the
            # same immutable event with a new timestamp and must not append a
            # second accounting entry.
            comparable = lambda item: {k: v for k, v in item.items() if k not in {"chk", "at"}}
            if comparable(same[0]) == comparable(proposed):
                return False
            raise PipelineError(f"同じ識別子で内容が異なる台帳記録があります: event_id={event.get('event_id')}")
        if event.get("event") != "reserve" and not any(e.get("reservation_id") == event.get("reservation_id") for e in events):
            raise PipelineError(f"存在しない予約への出来事です: reservation_id={event.get('reservation_id')}")
        path = self.store.path(self.ledger_path(month))
        path.parent.mkdir(parents=True, exist_ok=True)
        line = canonical_json_bytes(proposed)
        with path.open("ab") as handle:
            handle.write(line); handle.flush(); os.fsync(handle.fileno())
        self.read_events(month)
        return True

    def _all_approvals(self, month: str) -> list[dict[str, Any]]:
        root = self.store.path(Path("budget/approvals") / month)
        if not root.exists(): return []
        return [validate_checked(self.store.read_json(path.relative_to(self.store.root)), label=f"承認記録 {path}") for path in sorted(root.glob("*.json"))]

    def _counted_entries(self, month: str) -> list[tuple[str, str, Decimal]]:
        events = self.read_events(month)
        by_reservation: dict[str, list[dict[str, Any]]] = {}
        for event in events: by_reservation.setdefault(event["reservation_id"], []).append(event)
        approvals: dict[str, dict[str, Any]] = {}
        for approval in self._all_approvals(month):
            reservation = approval["reservation_id"]
            if reservation in approvals:
                raise PipelineError(
                    "同じ予約の承認記録が重複しています: "
                    f"reservation_id={reservation}, month={month}"
                )
            approvals[reservation] = approval
        entries: list[tuple[str, str, Decimal]] = []
        for reservation, approval in approvals.items():
            group = by_reservation.get(reservation, [])
            final = next((e for e in group if e["event"] in {"settle", "reconcile", "release"}), None)
            if final and final["event"] == "release": amount = Decimal(0)
            elif final: amount = decimal_value(final["actual_usd"], label="actual_usd")
            else: amount = decimal_value(approval["amount_usd"], label="amount_usd")
            entries.append((reservation, approval["run_id"], amount))
        return entries

    def counted(self, month: str) -> tuple[Decimal, dict[str, Decimal]]:
        total, runs = Decimal(0), {}
        for _reservation, run_id, amount in self._counted_entries(month):
            total += amount
            runs[run_id] = runs.get(run_id, Decimal(0)) + amount
        return total, runs

    def counted_for_run(self, run_id: str) -> Decimal:
        budget_root = self.store.path("budget")
        months: set[str] = set()
        if budget_root.exists():
            months.update(path.stem for path in budget_root.glob("????-??.jsonl"))
        approvals_root = self.store.path("budget/approvals")
        if approvals_root.exists():
            months.update(path.name for path in approvals_root.glob("????-??") if path.is_dir())

        total = Decimal(0)
        seen_reservations: dict[str, str] = {}
        for month in sorted(months):
            self.ledger_path(month)
            for reservation, entry_run_id, amount in self._counted_entries(month):
                previous_month = seen_reservations.get(reservation)
                if previous_month is not None:
                    raise PipelineError(
                        "同じ予約が複数月に記録されています: "
                        f"reservation_id={reservation}, months={[previous_month, month]}"
                    )
                seen_reservations[reservation] = month
                if entry_run_id == run_id:
                    total += amount
        return total

    def approve_and_reserve(self, proposal: dict[str, Any], *, stop_after: str | None = None) -> dict[str, Any]:
        limits = self.config["budget"]
        if any(limits[key] is None for key in limits):
            raise PipelineError(f"予算上限が未決定です: values={limits!r}")
        amount = decimal_value(proposal["amount_usd"], label="proposal.amount_usd")
        month = proposal["ledger_month"]
        with BudgetLock(self.store, float(self.config["llm"]["budget_lock_wait_s"])):
            existing = self.read_approval(month, proposal["reservation_id"])
            if existing is not None:
                differing = [
                    key for key in ("reservation_id", "run_id", "slug", "stage", "logical_key", "attempt", "wire_sha256")
                    if existing.get(key) != proposal.get(key)
                ]
                if differing or decimal_value(existing["amount_usd"], label="approval.amount") != amount:
                    raise PipelineError(
                        "承認の記録がジャーナルと一致しません: "
                        f"reservation_id={proposal['reservation_id']}, differing={differing}"
                    )
                approval = existing
            else:
                month_total, _month_run_totals = self.counted(month)
                run_total = self.counted_for_run(proposal["run_id"])
                judgment = {
                    "limits": {key: money(decimal_value(value, label=key)) for key, value in limits.items()},
                    "month_counted_before_usd": money(month_total),
                    "run_counted_before_usd": money(run_total),
                }
                rejected = (
                    amount > decimal_value(limits["call_limit_usd"], label="call_limit_usd")
                    or month_total + amount > decimal_value(limits["monthly_limit_usd"], label="monthly_limit_usd")
                    or run_total + amount > decimal_value(limits["run_limit_usd"], label="run_limit_usd")
                )
                if rejected:
                    raise PipelineError(f"予算上限を超えます: judgment={judgment}, reserve_usd={money(amount)}")
                approval = checked_record({
                    "schema": "budget_approval/v1", "reservation_id": proposal["reservation_id"],
                    "run_id": proposal["run_id"], "slug": proposal["slug"], "stage": proposal["stage"],
                    "logical_key": proposal["logical_key"], "attempt": proposal["attempt"],
                    "wire_sha256": proposal["wire_sha256"], "amount_usd": money(amount),
                    "approved_at": utc_now(), "judgment": judgment,
                })
                self.store.write_json(self.approval_path(month, proposal["reservation_id"]), approval)
            if stop_after == "R3": raise RuntimeError("injected stop after R3")
            approval_sha = sha256_bytes(canonical_json_bytes(approval))
            self.append_event(month, checked_record({
                "schema": "budget_event/v1", "event": "reserve",
                "event_id": proposal["reservation_id"], "reservation_id": proposal["reservation_id"],
                "run_id": proposal["run_id"], "amount_usd": money(amount),
                "approval_sha256": approval_sha, "at": utc_now(),
            }))
            if stop_after == "R4": raise RuntimeError("injected stop after R4")
            return approval

    def settle(self, proposal: dict[str, Any], actual: Decimal, *, event: str = "settle", note: str | None = None) -> bool:
        month = proposal["ledger_month"]
        with BudgetLock(self.store, float(self.config["llm"]["budget_lock_wait_s"])):
            payload = {
                "schema": "budget_event/v1", "event": event,
                "event_id": proposal["settlement_id"], "reservation_id": proposal["reservation_id"],
                "settlement_id": proposal["settlement_id"], "run_id": proposal["run_id"],
                "actual_usd": money(actual), "at": utc_now(),
            }
            if note is not None: payload["note"] = note
            return self.append_event(month, checked_record(payload))

    def release(self, record: dict[str, Any], note: str) -> bool:
        month = record["ledger_month"]
        reservation = record["reservation_id"]
        with BudgetLock(self.store, float(self.config["llm"]["budget_lock_wait_s"])):
            approval = self.read_approval(month, reservation)
            if approval is None:
                raise PipelineError(
                    f"解放対象の承認記録がありません: reservation_id={reservation}"
                )
            differing = [
                key
                for key in (
                    "reservation_id", "run_id", "slug", "stage",
                    "logical_key", "attempt", "wire_sha256",
                )
                if approval.get(key) != record.get(key)
            ]
            if (
                differing
                or decimal_value(approval["amount_usd"], label="approval.amount")
                != decimal_value(record["proposed_reserve_usd"], label="journal.reserve")
            ):
                raise PipelineError(
                    "承認の記録がジャーナルと一致しません: "
                    f"reservation_id={reservation}, differing={differing}"
                )
            events = self.read_events(month)
            reserve = next(
                (
                    event for event in events
                    if event["reservation_id"] == reservation
                    and event["event"] == "reserve"
                ),
                None,
            )
            if reserve is None:
                raise PipelineError(
                    f"解放対象の reserve がありません: reservation_id={reservation}"
                )
            release = checked_record({
                "schema": "budget_event/v1", "event": "release",
                "event_id": record["settlement_id"],
                "reservation_id": reservation,
                "settlement_id": record["settlement_id"],
                "run_id": record["run_id"],
                "actual_usd": money(Decimal(0)), "note": note, "at": utc_now(),
            })
            final = next(
                (
                    event for event in events
                    if event["reservation_id"] == reservation
                    and event["event"] in {"settle", "reconcile", "release"}
                ),
                None,
            )
            if final is not None:
                comparable = lambda item: {
                    key: value for key, value in item.items()
                    if key not in {"chk", "at"}
                }
                if comparable(final) == comparable(release):
                    return False
                raise PipelineError(
                    "解放対象に内容または識別子の異なる確定記録があります: "
                    f"reservation_id={reservation}, existing_event={final.get('event')}, "
                    f"existing_event_id={final.get('event_id')}, "
                    f"release_event_id={release.get('event_id')}"
                )
            return self.append_event(month, release)

    def outcome_unknown(self, proposal: dict[str, Any]) -> bool:
        month = proposal["ledger_month"]
        with BudgetLock(self.store, float(self.config["llm"]["budget_lock_wait_s"])):
            return self.append_event(month, checked_record({
                "schema": "budget_event/v1", "event": "outcome_unknown",
                "event_id": "unk_" + proposal["attempt_key"], "reservation_id": proposal["reservation_id"],
                "run_id": proposal["run_id"], "at": utc_now(),
            }))

    def repair(self, month: str) -> dict[str, Any]:
        relative = self.ledger_path(month); path = self.store.path(relative)
        data = path.read_bytes()
        if not data or data.endswith(b"\n"):
            raise PipelineError(f"予算台帳に途切れた最後の行がありません: path={path}")
        cut = data.rfind(b"\n") + 1
        prefix, tail = data[:cut], data[cut:]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        quarantine = Path("budget/quarantine") / f"{month}.{stamp}.jsonl"
        self.store.write_bytes(quarantine, data)
        # Validate every complete line before changing anything.
        temp_relative = Path("budget") / f".{month}.repair-check.jsonl"
        self.store.write_bytes(temp_relative, prefix)
        try:
            original = path
            path = self.store.path(temp_relative)
            parsed = self.read_events_from_bytes(prefix, month)
            del parsed
        finally:
            self.store.remove(temp_relative)
            path = original
        self.store.write_bytes(relative, prefix)
        result = {"month": month, "original_sha256": sha256_bytes(data), "discarded_bytes": len(tail), "quarantine": quarantine.as_posix(), "at": utc_now()}
        repairs = self.store.path("budget/repairs.jsonl")
        repairs.parent.mkdir(parents=True, exist_ok=True)
        with repairs.open("ab") as handle:
            handle.write(canonical_json_bytes(checked_record(result)))
            handle.flush()
            os.fsync(handle.fileno())
        return result

    def read_events_from_bytes(self, data: bytes, month: str) -> list[dict[str, Any]]:
        import json
        events=[]
        for number, raw in enumerate(data.splitlines(), 1):
            try: events.append(validate_checked(json.loads(raw), label=f"予算台帳 {month}:{number}"))
            except Exception as exc:
                if isinstance(exc, PipelineError): raise
                raise PipelineError(f"予算台帳の途中の行が破損しています: month={month}, line={number}") from exc
        self._validate_events(month, events)
        return events

    def check(self, *, apply: bool = False) -> dict[str, Any]:
        """Cross-check approvals, journals, and ledgers; restore only proven reserves."""
        approvals_root = self.store.path("budget/approvals")
        approvals: list[tuple[str, dict[str, Any]]] = []
        if approvals_root.exists():
            for path in sorted(approvals_root.glob("????-??/*.json")):
                month = path.parent.name
                approvals.append((month, validate_checked(self.store.read_json(path.relative_to(self.store.root)), label=f"承認記録 {path}")))
        journals: dict[str, dict[str, Any]] = {}
        runs_root = self.store.path("runs")
        if runs_root.exists():
            for path in runs_root.glob("*/llm_journal/*/attempt-*.json"):
                if path.name.endswith(".response.json"):
                    continue
                record = self.store.read_json(path.relative_to(self.store.root))
                if isinstance(record, dict) and isinstance(record.get("reservation_id"), str):
                    validate_journal_identifiers(record)
                    journals[record["reservation_id"]] = record
        actions: list[dict[str, Any]] = []
        for month, approval in approvals:
            reservation = approval["reservation_id"]
            record = journals.get(reservation)
            if record is None:
                raise PipelineError(f"承認記録に対応するジャーナルがありません: reservation_id={reservation}")
            for key in (
                "run_id", "slug", "stage", "logical_key", "attempt", "wire_sha256",
            ):
                if record.get(key) != approval.get(key):
                    raise PipelineError(f"承認記録とジャーナルが一致しません: reservation_id={reservation}, key={key}")
            if decimal_value(record["proposed_reserve_usd"], label="journal.reserve") != decimal_value(approval["amount_usd"], label="approval.amount"):
                raise PipelineError(f"承認記録とジャーナルの金額が一致しません: reservation_id={reservation}")
            events = self.read_events(month)
            reserve = next((event for event in events if event["reservation_id"] == reservation and event["event"] == "reserve"), None)
            final = next((event for event in events if event["reservation_id"] == reservation and event["event"] in {"settle", "reconcile", "release"}), None)
            if reserve is None:
                actions.append({"action": "restore_reserve", "reservation_id": reservation, "month": month})
                if apply:
                    self.append_event(month, checked_record({
                        "schema": "budget_event/v1", "event": "reserve", "event_id": reservation,
                        "reservation_id": reservation, "run_id": approval["run_id"],
                        "amount_usd": approval["amount_usd"],
                        "approval_sha256": sha256_bytes(canonical_json_bytes(approval)), "at": utc_now(),
                    }))
            if record.get("state") == "reconciled":
                if final is None:
                    raise PipelineError(
                        f"reconciled ジャーナルに対応する reconcile がありません: reservation_id={reservation}"
                    )
                differing = [
                    key for key in ("reservation_id", "settlement_id", "run_id")
                    if final.get(key) != record.get(key)
                ]
                if final.get("event") != "reconcile":
                    differing.append("event")
                if differing:
                    raise PipelineError(
                        "reconcile とジャーナルの識別子が一致しません: "
                        f"reservation_id={reservation}, differing={differing}"
                    )
                if decimal_value(final["actual_usd"], label="ledger.actual") != decimal_value(record["actual_usd"], label="journal.actual"):
                    raise PipelineError(
                        "台帳の照合額がジャーナルと一致しません: "
                        f"reservation_id={reservation}, ledger={final['actual_usd']}, journal={record['actual_usd']}"
                    )
                if final.get("note") != record.get("reconciliation_note"):
                    raise PipelineError(
                        f"台帳の照合理由がジャーナルと一致しません: reservation_id={reservation}"
                    )
            elif record.get("state") in {"settling", "completed", "incomplete", "failed", "cancelled"}:
                events = self.read_events(month)
                final = next((event for event in events if event["reservation_id"] == reservation and event["event"] in {"settle", "reconcile", "release"}), None)
                if final is None:
                    response = Path("runs") / record["run_id"] / "llm_journal" / record["logical_key"] / f"attempt-{record['attempt']}.response.json"
                    if not self.store.exists(response) or self.store.hash(response) != record.get("response_sha256"):
                        raise PipelineError(f"精算を復元できる応答がありません: reservation_id={reservation}")
                    actual = actual_cost(self.config["llm"]["pricing"], record["model"], self.store.read_json(response)["usage"])
                    if money(actual) != record.get("actual_usd"):
                        raise PipelineError(f"応答から再計算した金額がジャーナルと一致しません: reservation_id={reservation}")
                    actions.append({"action": "restore_settle", "reservation_id": reservation, "month": month})
                    if apply:
                        self.append_event(month, checked_record({
                            "schema": "budget_event/v1", "event": "settle",
                            "event_id": record["settlement_id"], "reservation_id": reservation,
                            "settlement_id": record["settlement_id"], "run_id": record["run_id"],
                            "actual_usd": money(actual), "at": utc_now(),
                        }))
                elif final["event"] in {"settle", "reconcile"} and decimal_value(final["actual_usd"], label="ledger.actual") != decimal_value(record["actual_usd"], label="journal.actual"):
                    raise PipelineError(
                        "台帳の精算額がジャーナルと一致しません: "
                        f"reservation_id={reservation}, ledger={final['actual_usd']}, journal={record['actual_usd']}"
                    )
            if record.get("state") == "unknown_outcome":
                if final is not None:
                    raise PipelineError(
                        "照合待ちジャーナルに確定済みの出来事があります: "
                        f"reservation_id={reservation}, event={final.get('event')}, "
                        f"settlement_id={final.get('settlement_id')}"
                    )
                if not any(
                    event["reservation_id"] == reservation and event["event"] == "outcome_unknown"
                    for event in events
                ):
                    actions.append({"action": "restore_outcome_unknown", "reservation_id": reservation, "month": month})
                    if apply:
                        self.append_event(month, checked_record({
                            "schema": "budget_event/v1", "event": "outcome_unknown",
                            "event_id": "unk_" + record["attempt_key"], "reservation_id": reservation,
                            "run_id": record["run_id"], "at": utc_now(),
                        }))
        approved_ids = {approval["reservation_id"] for _month, approval in approvals}
        for reservation, record in sorted(journals.items()):
            if reservation in approved_ids:
                continue
            if record.get("state") in {"proposed", "budget_rejected"}:
                limits = self.config["budget"]
                if any(value is None for value in limits.values()):
                    judgment = "unresolved_budget"
                else:
                    amount = decimal_value(record["proposed_reserve_usd"], label="journal.reserve")
                    month_total, _month_run_totals = self.counted(record["ledger_month"])
                    run_total = self.counted_for_run(record["run_id"])
                    rejected = (
                        amount > decimal_value(limits["call_limit_usd"], label="call_limit_usd")
                        or month_total + amount > decimal_value(limits["monthly_limit_usd"], label="monthly_limit_usd")
                        or run_total + amount > decimal_value(limits["run_limit_usd"], label="run_limit_usd")
                    )
                    judgment = "budget_exceeded" if rejected else "would_approve"
                actions.append({"action": "recheck_unapproved", "reservation_id": reservation, "judgment": judgment})
            else:
                raise PipelineError(
                    "承認記録がないのに reserved 以降のジャーナルがあります。復元しません: "
                    f"reservation_id={reservation}, state={record.get('state')}"
                )
        return {"apply": apply, "approvals": len(approvals), "actions": actions}
