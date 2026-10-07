"""S3_support: classify sources, judge support, and calculate sufficiency."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from . import PipelineError
from .basis_rules import (
    assign_source_types,
    ca_impl_function_scope_unchecked,
    decide_support,
    precheck_claim,
    validate_link_value,
    vb_diff_version_pair_unchecked,
)
from .claims_extract import _call_copy, _load_materials
from .graph import StageContext
from .llm_calls import LlmCallManager, response_output_json
from .llm_client import LlmClient
from .store import canonical_json_bytes, sha256_bytes


STAGE_VERSION = 1
BASIS_CODES = {"MT-IMPL", "MT-DOC", "CA-DOC", "CA-IMPL", "DV-DOC", "DV-IMPL", "VB-NOTES", "VB-DIFF", "RM-DOC", "OC-REPORT", "BD-PAIR", "NONE"}
FUNCTIONS = {"emits_message", "documents_message", "states_cause", "condition_leads_to_emission", "states_default", "defines_value", "uses_value", "states_version_change", "shows_behavior_before", "shows_behavior_after", "recommends_remedy", "reports_occurrence", "distinguishes", "unrelated", "contradicts"}


def _context(text: str, locations: list[dict[str, int]], surrounding: int) -> dict[str, Any]:
    if not locations:
        return {"line_start": None, "line_end": None, "text": ""}
    lines = text.splitlines()
    start = max(1, locations[0]["line_start"] - surrounding)
    end = min(len(lines), locations[0]["line_end"] + surrounding)
    return {"line_start": start, "line_end": end, "text": "\n".join(lines[start - 1:end])}


def _validate_judgements(value: dict[str, Any], batch: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if set(value) != {"judgements"} or not isinstance(value["judgements"], list):
        raise PipelineError("claims_support/v2 の形式が不正です")
    expected = {claim["claim_id"] for claim in batch}
    seen: dict[str, dict[str, Any]] = {}
    by_id = {claim["claim_id"]: claim for claim in batch}
    for judgement in value["judgements"]:
        required = {"claim_id", "basis_code", "evidence_assessment", "link_confirmed", "support", "contradicted", "reason", "missing"}
        if not isinstance(judgement, dict) or set(judgement) != required:
            raise PipelineError(f"判定の形式が不正です: value={judgement!r}")
        claim_id = judgement["claim_id"]
        if claim_id not in expected:
            raise PipelineError(f"入力にない claim_id の判定があります: claim_id={claim_id}")
        if claim_id in seen:
            raise PipelineError(f"claim_id の判定が重複しています: claim_id={claim_id}")
        if judgement["basis_code"] not in BASIS_CODES:
            raise PipelineError(f"basis_code が不正です: claim_id={claim_id}")
        if judgement["support"] not in {"supported", "partial", "unsupported"} or not isinstance(judgement["contradicted"], bool):
            raise PipelineError(f"support または contradicted が不正です: claim_id={claim_id}")
        validate_link_value(judgement["basis_code"], judgement["link_confirmed"])
        assessments = judgement["evidence_assessment"]
        if not isinstance(assessments, list):
            raise PipelineError(f"evidence_assessment が配列ではありません: claim_id={claim_id}")
        indexes: set[int] = set()
        evidence_count = len(by_id[claim_id]["evidence"])
        for item in assessments:
            if not isinstance(item, dict) or set(item) != {"evidence_index", "function", "reason"}:
                raise PipelineError(f"evidence_assessment の形式が不正です: claim_id={claim_id}")
            index = item["evidence_index"]
            if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < evidence_count:
                raise PipelineError(f"存在しない evidence_index です: claim_id={claim_id}, evidence_index={index!r}")
            if index in indexes:
                raise PipelineError(f"evidence_index が重複しています: claim_id={claim_id}, evidence_index={index}")
            indexes.add(index)
            if item["function"] not in FUNCTIONS or not isinstance(item["reason"], str) or not item["reason"]:
                raise PipelineError(f"evidence_assessment の function または reason が不正です: claim_id={claim_id}")
        if not isinstance(judgement["reason"], str) or not judgement["reason"] or not isinstance(judgement["missing"], list):
            raise PipelineError(f"判定理由の形式が不正です: claim_id={claim_id}")
        seen[claim_id] = judgement
    missing = sorted(expected - set(seen))
    if missing:
        raise PipelineError(f"判定がない主張があります: claim_ids={missing}")
    return seen


def _render_support(payload: dict[str, Any], nonce: str) -> str:
    # nonce is included in a data envelope even though this stage carries
    # program-selected excerpts rather than whole source documents.
    return (
        f"<<<SOURCE SUPPORT {nonce}>>>\n"
        + json.dumps(payload, ensure_ascii=False, sort_keys=True)
        + f"\n<<<END SOURCE SUPPORT {nonce}>>>"
    )


def run_claims_support(context: StageContext, _state: dict[str, Any]) -> None:
    cfg = context.config["claims"]["support"]
    index, sources, texts = _load_materials(context)
    extracted = context.store.read_json(context.artifact_relative("claims.extracted.json"))
    if not isinstance(extracted, dict) or extracted.get("schema") != "claims_extracted/v1" or not isinstance(extracted.get("claims"), list):
        raise PipelineError("claims.extracted.json の形式が不正です")
    current_index_hash = context.store.hash(context.artifact_relative("sources/index.json"))
    if extracted.get("sources_index_sha256") != current_index_hash:
        raise PipelineError(
            "抽出結果は無効です（資料が抽出後に変わっています）: "
            f"recorded={extracted.get('sources_index_sha256')}, current={current_index_hash}"
        )
    source_types = assign_source_types(list(sources.values()), context.config["claims"]["source_types"])
    prepared: list[dict[str, Any]] = []
    final_by_id: dict[str, dict[str, Any]] = {}
    for raw in extracted["claims"]:
        claim = deepcopy(raw)
        for evidence in claim.get("evidence", []):
            evidence["source_type"] = source_types.get(evidence.get("source_id"), "third_party")
        passed = precheck_claim(claim, sources, source_types, max_link_span_lines=cfg["max_link_span_lines"])
        claim["precheck_passed"] = passed
        if not passed:
            if ca_impl_function_scope_unchecked(
                claim,
                sources,
                source_types,
                max_link_span_lines=cfg["max_link_span_lines"],
            ):
                reason = "function_scope_unchecked"
            elif vb_diff_version_pair_unchecked(claim, sources, source_types):
                reason = "version_pair_unchecked"
            elif claim.get("kind") == "boundary":
                reason = "boundary_sides_unchecked"
            else:
                reason = "required_basis_missing"
            final_by_id[claim["claim_id"]] = {
                **claim, "status": "unverified", "basis": None, "support": "not_judged",
                "unverified_reason": reason, "writing_constraint": None,
                "judgement": None,
            }
            continue
        payload_claim = {
            "claim_id": claim["claim_id"], "kind": claim["kind"], "text": claim["text"],
            "subject": claim.get("subject"), "version_scope": claim.get("version_scope"),
            "precheck_passed": passed, "evidence": [],
        }
        for index_number, evidence in enumerate(claim.get("evidence", [])):
            source_id = evidence.get("source_id")
            payload_claim["evidence"].append({
                "evidence_index": index_number, "source_id": source_id,
                "quote": evidence.get("quote"), "quote_match": evidence.get("quote_match"),
                "source_type": source_types.get(source_id, "third_party"),
                "context": _context(texts.get(source_id, ""), evidence.get("quote_match", {}).get("locations", []), cfg["context_lines"]),
            })
        prepared.append({"claim": claim, "payload": payload_claim})

    calls: list[dict[str, Any]] = []
    if prepared:
        prompt_path = context.repo_root / "config/prompts/s3_support.v1.md"
        schema_path = context.repo_root / "config/schemas/claims_support.v2.json"
        instructions = prompt_path.read_text(encoding="utf-8")
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema["properties"]["judgements"]["maxItems"] = cfg["claims_per_call"]
        client = context.cache.get("llm_client") or LlmClient()
        manager = LlmCallManager(context.store, context.config, client)
        retry_unknown = bool(context.cache.get("retry_unknown_llm_calls"))
        size = cfg["claims_per_call"]
        for offset in range(0, len(prepared), size):
            group = prepared[offset:offset + size]
            payload = {"claims": [item["payload"] for item in group]}
            slot = f"support:{group[0]['claim']['claim_id']}-{group[-1]['claim']['claim_id']}"
            for validation_attempt in range(2):
                result = manager.execute(
                    run_id=context.run_id, slug=_state["slug"], stage="S3_support", slot=slot,
                    stage_config=cfg, instructions=instructions, output_schema=schema,
                    schema_name="claims_support_v2", payload=payload, render=_render_support,
                    retry_unknown=retry_unknown, retry_terminal=validation_attempt == 1,
                )
                if result.response.get("status") != "completed":
                    raise PipelineError(
                        f"裏付け判定の LLM 応答が completed ではありません: status={result.response.get('status')!r}"
                    )
                try:
                    judgements = _validate_judgements(response_output_json(result.response), [item["claim"] for item in group])
                    break
                except PipelineError as exc:
                    invalid_count = manager.mark_output_invalid(context.run_id, result, str(exc))
                    if validation_attempt == 1 or invalid_count >= 2:
                        raise
            calls.append(_call_copy(result))
            for item in group:
                claim = item["claim"]
                judgement = judgements[claim["claim_id"]]
                status, reason, constraint = decide_support(claim, judgement)
                version_scope = claim.get("version_scope")
                if (
                    status == "verified" and isinstance(version_scope, dict)
                    and version_scope.get("constraint") is not None
                ):
                    # The design deliberately leaves the constraint syntax
                    # undefined.  Fail closed rather than interpreting an
                    # arbitrary range expression or silently accepting it.
                    status, reason, constraint = "unverified", "version_scope_unchecked", None
                if judgement["basis_code"] == "OC-REPORT" and any(
                    sources.get(evidence.get("source_id"), {}).get("kind") == "github_issue"
                    and "\nState: closed\n" in ("\n" + texts.get(evidence.get("source_id"), ""))
                    for evidence in claim.get("evidence", [])
                ):
                    constraint = "occurrence_report_past"
                final_by_id[claim["claim_id"]] = {
                    **claim, "status": status, "basis": judgement["basis_code"],
                    "support": judgement["support"], "unverified_reason": reason,
                    "writing_constraint": constraint, "judgement": judgement,
                }

    final_claims = [final_by_id[claim["claim_id"]] for claim in extracted["claims"]]
    official: set[str] = set()
    cases: set[str] = set()
    boundaries: set[str] = set()
    counted_claims: dict[str, list[str]] = {"official": [], "case": [], "boundary": []}
    for claim in final_claims:
        if claim["status"] != "verified":
            continue
        ids = {e["source_id"] for e in claim.get("evidence", []) if e.get("quote_match", {}).get("result") == "matched"}
        for source_id in ids:
            source_type = source_types.get(source_id)
            if source_type in {"official_impl", "official_doc"}:
                official.add(source_id)
                counted_claims["official"].append(claim["claim_id"])
            if source_type in {"case", "vendor_community"}:
                cases.add(source_id)
                counted_claims["case"].append(claim["claim_id"])
            if claim["kind"] == "boundary":
                boundaries.add(source_id)
                counted_claims["boundary"].append(claim["claim_id"])
    counts = {"official_sources": len(official), "case_sources": len(cases), "boundary_sources": len(boundaries)}
    requirements = {"official_sources": 3, "case_sources": 1, "boundary_sources": 1}
    missing = [key for key, required in requirements.items() if counts[key] < required]
    claims_hash = context.store.hash(context.artifact_relative("claims.extracted.json"))
    prompt_path = context.repo_root / "config/prompts/s3_support.v1.md"
    output = {
        "schema": "claims/v1", "sources_index_sha256": current_index_hash,
        "claims_extracted_sha256": claims_hash,
        "prompt_sha256": sha256_bytes(prompt_path.read_bytes()), "calls": calls,
        "source_types": source_types, "claims": final_claims,
    }
    sufficiency = {
        "schema": "sufficiency/v1", "sufficient": not missing,
        "requirements": requirements, "counts": counts, "missing": missing,
        "sources": {"official": sorted(official), "case": sorted(cases), "boundary": sorted(boundaries)},
        "claims": {key: sorted(set(value)) for key, value in counted_claims.items()},
    }
    context.write_json("claims.json", output)
    context.write_json("sufficiency.json", sufficiency)
