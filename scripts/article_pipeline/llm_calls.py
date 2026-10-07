"""Crash-resumable LLM calls with immutable keys, journal, and budget ordering."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any

from . import PipelineError
from .budget import BudgetLedger, actual_cost, decimal_value, estimate_cost, money, reserve_cost, utc_now
from .llm_client import LlmApiError, LlmClient
from .store import RunStore, canonical_json_bytes, sha256_bytes


TERMINAL = {"completed", "incomplete", "failed", "cancelled"}


def logical_key(value: dict[str, Any]) -> str:
    forbidden = {"nonce", "metadata", "attempt", "sdk_version", "pricing"}
    if forbidden & set(value):
        raise PipelineError(f"logical_key の入力に禁止キーがあります: keys={sorted(forbidden & set(value))}")
    return sha256_bytes(canonical_json_bytes(value)).removeprefix("sha256:")


def nonce_for(key: str) -> str:
    return sha256_bytes(("nonce/v1:" + key).encode()).removeprefix("sha256:")[:16]


def attempt_key(key: str, attempt: int) -> str:
    return sha256_bytes(f"attempt/v1:{key}:{attempt}".encode()).removeprefix("sha256:")


def wire_sha256(request: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(request))


def response_output_json(response: dict[str, Any]) -> dict[str, Any]:
    text = response.get("output_text")
    if not isinstance(text, str):
        for item in response.get("output", []) if isinstance(response.get("output"), list) else []:
            for content in item.get("content", []) if isinstance(item, dict) else []:
                if isinstance(content, dict) and content.get("type") == "output_text":
                    text = content.get("text"); break
    if not isinstance(text, str):
        raise PipelineError("LLM 応答に output_text がありません")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PipelineError(f"LLM 応答の output_text が JSON ではありません: error={exc}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"LLM 応答の JSON は object が必要です: type={type(value).__name__}")
    return value


def ensure_resolved(config: dict[str, Any], stage_config: dict[str, Any]) -> None:
    unresolved = []
    for key in ("store",):
        if config["llm"].get(key) is None: unresolved.append("llm." + key)
    if config["llm"]["pricing"].get("max_age_days") is None: unresolved.append("llm.pricing.max_age_days")
    for key in ("monthly_limit_usd", "run_limit_usd", "call_limit_usd"):
        if config["budget"].get(key) is None: unresolved.append("budget." + key)
    for key in ("model", "reasoning_effort", "max_output_tokens", "expected_output_tokens"):
        if stage_config.get(key) is None: unresolved.append(key)
    if unresolved:
        raise PipelineError(f"LLM 呼び出しに必要な設定が未決定です（API は呼びません）: keys={unresolved}")


def build_logical_content(
    *, run_id: str, stage: str, slot: str, stage_config: dict[str, Any],
    instructions_sha256: str, output_schema_sha256: str, payload_sha256: str,
) -> dict[str, Any]:
    return {
        "schema": "llm_logical_key/v1", "run_id": run_id, "stage": stage, "slot": slot,
        "model": stage_config["model"], "reasoning_effort": stage_config["reasoning_effort"],
        "max_output_tokens": stage_config["max_output_tokens"], "store": None,
        "truncation": "disabled", "instructions_sha256": instructions_sha256,
        "output_schema_sha256": output_schema_sha256, "renderer_version": 1,
        "payload_sha256": payload_sha256,
    }


def build_wire_request(
    *, key: str, attempt: int, run_id: str, stage: str, stage_config: dict[str, Any],
    store_value: bool, instructions: str, rendered_input: str, output_schema: dict[str, Any], schema_name: str,
) -> dict[str, Any]:
    return {
        "model": stage_config["model"], "instructions": instructions,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": rendered_input}]}],
        "text": {"format": {"type": "json_schema", "name": schema_name, "strict": True, "schema": output_schema}},
        "reasoning": {"effort": stage_config["reasoning_effort"]},
        "max_output_tokens": stage_config["max_output_tokens"], "background": True,
        "store": store_value, "truncation": "disabled",
        "metadata": {"pipeline": "errorlog-article", "run_id": run_id, "stage": stage,
                     "logical_key": key, "attempt": str(attempt)},
    }


@dataclass
class CallResult:
    logical_key: str
    attempt: int
    response: dict[str, Any]
    actual_usd: str
    reused_from_journal: bool
    record: dict[str, Any]


class LlmCallManager:
    def __init__(self, store: RunStore, config: dict[str, Any], client: LlmClient) -> None:
        self.store, self.config, self.client = store, config, client
        self.budget = BudgetLedger(store, config)

    def _journal_dir(self, run_id: str, key: str) -> Path:
        return Path("runs") / run_id / "llm_journal" / key

    def _attempt_path(self, run_id: str, key: str, attempt: int) -> Path:
        return self._journal_dir(run_id, key) / f"attempt-{attempt}.json"

    def _response_path(self, run_id: str, key: str, attempt: int) -> Path:
        return self._journal_dir(run_id, key) / f"attempt-{attempt}.response.json"

    def _assert_run_reserve_not_exceeded(self, run_id: str) -> None:
        directory = self.store.path(Path("runs") / run_id / "llm_journal")
        if not directory.exists():
            return
        for path in directory.glob("*/attempt-*.json"):
            if path.name.endswith(".response.json"):
                continue
            record = self.store.read_json(path.relative_to(self.store.root))
            if isinstance(record, dict) and record.get("reserve_exceeded") is True:
                raise PipelineError(
                    "確定額が予約額を超えた試行があるため、この run の LLM 呼び出しを停止します: "
                    f"path={path}, logical_key={record.get('logical_key')}, attempt={record.get('attempt')}"
                )

    def _attempts(self, run_id: str, key: str) -> list[dict[str, Any]]:
        directory = self.store.path(self._journal_dir(run_id, key))
        if not directory.exists(): return []
        values=[]
        for path in sorted(directory.glob("attempt-*.json")):
            if path.name.endswith(".response.json"): continue
            value=self.store.read_json(path.relative_to(self.store.root))
            if not isinstance(value, dict) or value.get("schema") != "llm_attempt/v2":
                raise PipelineError(f"LLM ジャーナルが不正です: path={path}")
            values.append(value)
        return sorted(values, key=lambda item: item["attempt"])

    def _update(self, run_id: str, record: dict[str, Any], state: str, **fields: Any) -> dict[str, Any]:
        updated={**record, **fields, "state": state}
        updated["history"]=[*record.get("history", []), {"state": state, "at": utc_now()}]
        self.store.write_json(self._attempt_path(run_id, record["logical_key"], record["attempt"]), updated)
        return updated

    def mark_output_invalid(self, run_id: str, result: CallResult, error: str) -> int:
        """Persist validation failure so a restart cannot buy unlimited retries."""
        record = self.store.read_json(self._attempt_path(run_id, result.logical_key, result.attempt))
        if record.get("output_validation_error") != error:
            record["output_validation_error"] = error
            record["history"] = [
                *record.get("history", []),
                {"state": record["state"], "event": "output_validation_failed", "at": utc_now()},
            ]
            self.store.write_json(self._attempt_path(run_id, result.logical_key, result.attempt), record)
        return sum(
            1 for item in self._attempts(run_id, result.logical_key)
            if item.get("output_validation_error") is not None
        )

    def execute(
        self, *, run_id: str, slug: str, stage: str, slot: str, stage_config: dict[str, Any],
        instructions: str, output_schema: dict[str, Any], schema_name: str,
        payload: dict[str, Any], render: Any, retry_unknown: bool = False,
        retry_terminal: bool = False, max_input_tokens: int | None = None,
        stop_after: str | None = None,
        _automatic_retry: int = 0,
        _force_new_attempt: bool = False,
    ) -> CallResult:
        ensure_resolved(self.config, stage_config)
        self._assert_run_reserve_not_exceeded(run_id)
        payload_sha = sha256_bytes(canonical_json_bytes(payload))
        prompt_sha = sha256_bytes(instructions.encode())
        schema_sha = sha256_bytes(canonical_json_bytes(output_schema))
        logical = build_logical_content(
            run_id=run_id, stage=stage, slot=slot, stage_config=stage_config,
            instructions_sha256=prompt_sha, output_schema_sha256=schema_sha, payload_sha256=payload_sha,
        )
        logical["store"] = self.config["llm"]["store"]
        key = logical_key(logical)
        nonce = nonce_for(key)
        rendered = render(payload, nonce)
        if nonce in json.dumps(payload, ensure_ascii=False):
            raise PipelineError(f"資料本文に区切り用 nonce が含まれています: logical_key={key}")
        attempts = self._attempts(run_id, key)
        record = attempts[-1] if attempts else None
        if record and record["state"] == "unknown_outcome":
            if not retry_unknown:
                raise PipelineError(f"結果不明の LLM 呼び出しがあります。自動再送しません: logical_key={key}, attempt={record['attempt']}")
            record = None
        if record and record["state"] == "completed" and retry_terminal:
            record = None
        rejected_request = record and (
            record["state"] == "rejected"
            or (record["state"] == "reconciled" and record.get("api_outcome") == "rejected")
        )
        if rejected_request and not _force_new_attempt:
            raise PipelineError(
                f"拒否された LLM 呼び出しは自動再試行しません: logical_key={key}, attempt={record['attempt']}"
            )
        if record and (record["state"] == "released" or _force_new_attempt):
            record = None
        attempt = (attempts[-1]["attempt"] + 1) if record is None and attempts else 1
        request = build_wire_request(
            key=key, attempt=attempt if record is None else record["attempt"], run_id=run_id, stage=stage,
            stage_config=stage_config, store_value=self.config["llm"]["store"], instructions=instructions,
            rendered_input=rendered, output_schema=output_schema, schema_name=schema_name,
        )
        wire = wire_sha256(request)
        if record is not None and record["wire_sha256"] != wire:
            raise PipelineError(f"再開時の wire_sha256 が一致しません: logical_key={key}, recorded={record['wire_sha256']}, current={wire}")
        if record is None:
            count_request = {k: v for k, v in request.items() if k not in {"background", "store", "metadata"}}
            input_tokens = self.client.count_input_tokens(count_request, timeout=float(self.config["llm"]["count_timeout_s"]))
            if max_input_tokens is not None and input_tokens > max_input_tokens:
                raise PipelineError(
                    "1件の資料を含む要求が入力トークン上限を超えます。切り詰めません: "
                    f"slot={slot}, input_tokens={input_tokens}, max_input_tokens={max_input_tokens}"
                )
            estimated = estimate_cost(self.config["llm"]["pricing"], stage_config["model"], input_tokens, stage_config["expected_output_tokens"])
            reserve, price_ref = reserve_cost(self.config["llm"]["pricing"], stage_config["model"], input_tokens, stage_config["max_output_tokens"])
            akey=attempt_key(key, attempt)
            month=datetime.now(timezone.utc).strftime("%Y-%m")
            record={
                "schema":"llm_attempt/v2", "logical_key":key, "attempt":attempt, "attempt_key":akey,
                "reservation_id":"rsv_"+akey, "settlement_id":"stl_"+akey, "ledger_month":month,
                "state":"proposed", "wire_sha256":wire, "estimated_usd":money(estimated),
                "proposed_reserve_usd":money(reserve),
                "reserve_basis":{"input_tokens":input_tokens,"max_output_tokens":stage_config["max_output_tokens"],"price_ref":price_ref},
                "run_id":run_id, "slug":slug, "stage":stage, "model":stage_config["model"],
                "last_judgment":None,"response_id":None,"response_sha256":None,"actual_usd":None,"usage":None,
                "history":[{"state":"proposed","at":utc_now()}],
            }
            self.store.create_exclusive_json(self._attempt_path(run_id,key,attempt),record)
            if stop_after == "R1": raise RuntimeError("injected stop after R1")
        proposal={**record,"amount_usd":record["proposed_reserve_usd"]}
        if record["state"] in {"proposed", "budget_rejected"}:
            try:
                self.budget.approve_and_reserve(proposal, stop_after=stop_after if stop_after in {"R3","R4"} else None)
            except PipelineError as exc:
                if "予算上限" in str(exc):
                    if stop_after == "R2x":
                        raise RuntimeError("injected stop after rejected R2 judgment") from exc
                    self._update(run_id,record,"budget_rejected",last_judgment={"error":str(exc)})
                    raise PipelineError(f"budget_exceeded: {exc}") from exc
                raise
            record=self._update(run_id,record,"reserved")
            if stop_after == "R5": raise RuntimeError("injected stop after R5")
        elif record["state"] == "reserved":
            record=self._update(run_id,record,"unknown_outcome")
            self.budget.outcome_unknown(proposal)
            raise PipelineError(f"作成要求を送ったか確認できません。自動再送しません: logical_key={key}, attempt={record['attempt']}")
        response_path=self._response_path(run_id,key,record["attempt"])
        response: dict[str,Any] | None = None
        if record["state"] == "submitted" and self.store.exists(response_path):
            response=self.store.read_json(response_path)
        elif record["state"] == "submitted":
            response=None
        elif record["state"] == "settling":
            response=self.store.read_json(response_path)
        elif record["state"] in TERMINAL:
            response=self.store.read_json(response_path)
            if record.get("reserve_exceeded") is True:
                raise PipelineError(
                    "確定額が予約額を超えたため、この run の以後の LLM 呼び出しを停止します: "
                    f"logical_key={key}, attempt={record['attempt']}"
                )
            return CallResult(key,record["attempt"],response,record["actual_usd"],True,record)
        else:
            try:
                response=self.client.create(request,timeout=float(self.config["llm"]["create_timeout_s"]))
            except LlmApiError as exc:
                if exc.status_code in {400,401,403,404,422}:
                    self._update(
                        run_id, record, "rejected",
                        api_outcome="rejected", billing_status="unreconciled",
                        http_status=exc.status_code, error_code=exc.code,
                    )
                    raise PipelineError(str(exc)) from exc
                if exc.status_code == 429:
                    record = self._update(
                        run_id, record, "rejected",
                        api_outcome="rejected", billing_status="unreconciled",
                        http_status=exc.status_code, error_code=exc.code,
                    )
                    fatal = {
                        "credit_balance_exhausted", "organization_spend_limit_exceeded",
                        "project_spend_limit_exceeded", "organization_usage_limit_exceeded",
                    }
                    if exc.code in fatal:
                        raise PipelineError(f"再試行できない利用上限エラーです: code={exc.code}") from exc
                    if _automatic_retry >= int(self.config["llm"]["max_retries"]):
                        raise PipelineError(f"一時的な利用上限の再試行回数を超えました: retries={_automatic_retry}") from exc
                    if exc.retry_after is not None:
                        if exc.retry_after > float(self.config["llm"]["retry_after_max_s"]):
                            raise PipelineError(
                                f"Retry-After が上限を超えます: retry_after={exc.retry_after}, "
                                f"max={self.config['llm']['retry_after_max_s']}"
                            ) from exc
                        delay = exc.retry_after
                    else:
                        delay = float(self.config["llm"]["retry_backoff_s"][_automatic_retry])
                    time.sleep(delay)
                    return self.execute(
                        run_id=run_id, slug=slug, stage=stage, slot=slot,
                        stage_config=stage_config, instructions=instructions,
                        output_schema=output_schema, schema_name=schema_name,
                        payload=payload, render=render, retry_unknown=retry_unknown,
                        retry_terminal=False, max_input_tokens=max_input_tokens,
                        stop_after=stop_after, _automatic_retry=_automatic_retry + 1,
                        _force_new_attempt=True,
                    )
                record=self._update(run_id,record,"unknown_outcome")
                self.budget.outcome_unknown(proposal)
                raise PipelineError(f"LLM 作成要求の結果が不明です。自動再送しません: {exc}") from exc
            response_id=response.get("id")
            if not isinstance(response_id,str) or not response_id:
                record=self._update(run_id,record,"unknown_outcome")
                self.budget.outcome_unknown(proposal)
                raise PipelineError("LLM 作成応答に response ID がありません。自動再送しません")
            record=self._update(run_id,record,"submitted",response_id=response_id)
            if stop_after == "R7": raise RuntimeError("injected stop after R7")
        deadline = time.monotonic() + float(self.config["llm"]["call_deadline_s"])
        retrieve_failures = 0
        while response is None or response.get("status") not in TERMINAL:
            if time.monotonic() >= deadline:
                try:
                    self.client.cancel(record["response_id"], timeout=float(self.config["llm"]["retrieve_timeout_s"]))
                    response = self.client.retrieve(record["response_id"], timeout=float(self.config["llm"]["retrieve_timeout_s"]))
                except LlmApiError as exc:
                    record = self._update(run_id, record, "unknown_outcome")
                    self.budget.outcome_unknown(proposal)
                    raise PipelineError(f"期限超過後の取消または取得に失敗しました: {exc}") from exc
                if response.get("status") not in TERMINAL:
                    record = self._update(run_id, record, "unknown_outcome")
                    self.budget.outcome_unknown(proposal)
                    raise PipelineError(f"取消後も終了状態を確認できません: status={response.get('status')!r}")
                break
            try:
                response = self.client.retrieve(record["response_id"], timeout=float(self.config["llm"]["retrieve_timeout_s"]))
                retrieve_failures = 0
            except LlmApiError as exc:
                if exc.status_code == 404:
                    record = self._update(run_id, record, "unknown_outcome")
                    self.budget.outcome_unknown(proposal)
                    raise PipelineError(f"LLM 応答を取得できず照合待ちです: response_id={record['response_id']}") from exc
                if exc.status_code not in {None, 408, 409, 429, 500, 502, 503, 504}:
                    raise PipelineError(str(exc)) from exc
                retrieve_failures += 1
                index = min(retrieve_failures - 1, len(self.config["llm"]["retry_backoff_s"]) - 1)
                delay = exc.retry_after if exc.retry_after is not None else float(self.config["llm"]["retry_backoff_s"][index])
                if delay > float(self.config["llm"]["retry_after_max_s"]):
                    raise PipelineError(f"取得の Retry-After が上限を超えます: retry_after={delay}") from exc
                time.sleep(delay)
                continue
            if response.get("status") not in TERMINAL:
                time.sleep(float(self.config["llm"]["poll_interval_s"]))
        if not self.store.exists(response_path): self.store.write_json(response_path,response)
        if stop_after == "S1": raise RuntimeError("injected stop after S1")
        response_sha=self.store.hash(response_path)
        usage=response.get("usage")
        if not isinstance(usage,dict):
            record=self._update(run_id,record,"unknown_outcome",response_sha256=response_sha)
            self.budget.outcome_unknown(proposal)
            raise PipelineError("終了した LLM 応答に usage がありません")
        actual=actual_cost(self.config["llm"]["pricing"],record["model"],usage)
        reserve_exceeded = actual > decimal_value(record["proposed_reserve_usd"], label="proposed_reserve_usd")
        record=self._update(
            run_id, record, "settling", response_sha256=response_sha, usage=usage,
            actual_usd=money(actual), reserve_exceeded=reserve_exceeded,
        )
        if stop_after == "S2": raise RuntimeError("injected stop after S2")
        self.budget.settle(proposal,actual)
        if stop_after == "S3": raise RuntimeError("injected stop after S3")
        final_state=str(response["status"])
        record=self._update(run_id,record,final_state)
        if reserve_exceeded:
            raise PipelineError(
                "確定額が予約額を超えたため、この run の以後の LLM 呼び出しを停止します: "
                f"logical_key={key}, attempt={record['attempt']}, reserve={record['proposed_reserve_usd']}, actual={money(actual)}"
            )
        return CallResult(key,record["attempt"],response,money(actual),False,record)
