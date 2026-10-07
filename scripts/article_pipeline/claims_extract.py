"""S3_claims: extract claims and mechanically match verbatim quotations."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from . import PipelineError
from .graph import StageContext
from .llm_calls import LlmCallManager, response_output_json
from .llm_client import LlmClient
from .quote_match import match_evidence, normalize_text
from .store import canonical_json_bytes, sha256_bytes


STAGE_VERSION = 1
KINDS = {"message_text", "cause", "default_value", "version_behavior", "remedy", "occurrence", "boundary"}
ROLES = {"emission", "condition", "statement", "report", "version_note", "context"}
SUBJECT_KEYS = {"message_literal", "identifier", "value", "version", "other_error"}


def _load_materials(context: StageContext) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, str]]:
    index = context.store.read_json(context.artifact_relative("sources/index.json"))
    raw_sources = index.get("sources") if isinstance(index, dict) else None
    if not isinstance(raw_sources, list):
        raise PipelineError("sources/index.json の sources が配列ではありません")
    sources: dict[str, dict[str, Any]] = {}
    texts: dict[str, str] = {}
    for source in raw_sources:
        if not isinstance(source, dict) or not isinstance(source.get("source_id"), str):
            raise PipelineError(f"sources/index.json の資料が不正です: value={source!r}")
        source_id = source["source_id"]
        if source_id in sources:
            raise PipelineError(f"source_id が重複しています: source_id={source_id}")
        sources[source_id] = source
        if source.get("status") not in {"fetched", "reused"}:
            continue
        text_info = source.get("text")
        if not isinstance(text_info, dict) or not isinstance(text_info.get("path"), str):
            raise PipelineError(f"取得済み資料に text.path がありません: source_id={source_id}")
        relative = context.artifact_relative("sources/" + text_info["path"])
        text = context.store.read_text(relative)
        actual = sha256_bytes(text.encode("utf-8"))
        if actual != text_info.get("sha256"):
            raise PipelineError(
                f"資料本文のハッシュが一致しません: source_id={source_id}, expected={text_info.get('sha256')}, actual={actual}"
            )
        texts[source_id] = text
    return index, sources, texts


def _validate_extract(value: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    if set(value) != {"claims", "instruction_like_text"}:
        raise PipelineError(f"claims_extract/v1 のキーが不正です: keys={sorted(value)}")
    claims = value["claims"]
    if not isinstance(claims, list) or len(claims) > config["max_claims_per_call"]:
        raise PipelineError(f"抽出主張の件数が不正です: count={len(claims) if isinstance(claims, list) else 'not-array'}")
    seen: set[str] = set()
    for claim in claims:
        required = {"temp_id", "kind", "text", "subject", "evidence", "version_scope"}
        if not isinstance(claim, dict) or set(claim) != required:
            raise PipelineError(f"抽出主張の形式が不正です: value={claim!r}")
        if not isinstance(claim["temp_id"], str) or not claim["temp_id"] or claim["temp_id"] in seen:
            raise PipelineError(f"temp_id が空または重複しています: value={claim['temp_id']!r}")
        seen.add(claim["temp_id"])
        if claim["kind"] not in KINDS or not isinstance(claim["text"], str) or not claim["text"]:
            raise PipelineError(f"主張の kind または text が不正です: temp_id={claim['temp_id']}")
        if not isinstance(claim["subject"], dict) or set(claim["subject"]) != SUBJECT_KEYS:
            raise PipelineError(f"subject の形式が不正です: temp_id={claim['temp_id']}")
        if any(item is not None and not isinstance(item, str) for item in claim["subject"].values()):
            raise PipelineError(f"subject の値は文字列または null が必要です: temp_id={claim['temp_id']}")
        evidence = claim["evidence"]
        if not isinstance(evidence, list) or len(evidence) > config["max_evidence_per_claim"]:
            raise PipelineError(f"evidence の件数が不正です: temp_id={claim['temp_id']}")
        for item in evidence:
            if not isinstance(item, dict) or set(item) != {"source_id", "role", "quote"}:
                raise PipelineError(f"evidence の形式が不正です: temp_id={claim['temp_id']}")
            if item["role"] not in ROLES or not isinstance(item["source_id"], str):
                raise PipelineError(f"evidence の source_id または role が不正です: temp_id={claim['temp_id']}")
            if not isinstance(item["quote"], str) or not item["quote"] or len(item["quote"]) > config["max_quote_chars"]:
                raise PipelineError(f"evidence.quote が空または長すぎます: temp_id={claim['temp_id']}")
        scope = claim["version_scope"]
        if scope is not None and (
            not isinstance(scope, dict) or set(scope) != {"product", "constraint"}
            or not isinstance(scope["product"], str) or not scope["product"]
            or (scope["constraint"] is not None and not isinstance(scope["constraint"], str))
        ):
            raise PipelineError(f"version_scope が不正です: temp_id={claim['temp_id']}")
    markers = value["instruction_like_text"]
    if not isinstance(markers, list) or any(
        not isinstance(item, dict) or set(item) != {"source_id", "excerpt"}
        or not all(isinstance(item[key], str) for key in ("source_id", "excerpt"))
        for item in markers
    ):
        raise PipelineError("instruction_like_text の形式が不正です")
    return value


def _render_extract(payload: dict[str, Any], nonce: str, texts: dict[str, str]) -> str:
    blocks = [json.dumps({"topic": payload["topic"]}, ensure_ascii=False, sort_keys=True)]
    for item in payload["sources"]:
        source_id = item["source_id"]
        if nonce in texts[source_id]:
            raise PipelineError(f"資料本文に区切り用 nonce が含まれています: source_id={source_id}, nonce={nonce}")
        blocks.extend((
            f"<<<SOURCE {source_id} {nonce}>>>",
            texts[source_id],
            f"<<<END SOURCE {source_id} {nonce}>>>",
        ))
    return "\n".join(blocks)


def _markers(texts: dict[str, str], configured: list[str]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for source_id in sorted(texts):
        for number, line in enumerate(texts[source_id].splitlines(), 1):
            normalized = normalize_text(line).casefold()
            for marker in configured:
                if normalize_text(marker).casefold() in normalized:
                    found.append({"source_id": source_id, "line": number, "marker": marker})
    return found


def _call_copy(result: Any) -> dict[str, Any]:
    response = result.response
    return {
        "logical_key": result.logical_key,
        "attempt": result.attempt,
        "actual_usd": result.actual_usd,
        "input_tokens": result.record["reserve_basis"]["input_tokens"],
        "usage": result.record.get("usage"),
        "response_id": response.get("id"),
        "reused_from_journal": result.reused_from_journal,
    }


def run_claims_extract(context: StageContext, _state: dict[str, Any]) -> None:
    cfg = context.config["claims"]["extract"]
    if cfg["max_input_tokens_per_call"] is None:
        raise PipelineError("設定 claims.extract.max_input_tokens_per_call が未決定です（API は呼びません）")
    index, sources, texts = _load_materials(context)
    if not texts:
        raise PipelineError("S3_claims に渡せる fetched または reused の資料がありません")
    topic_raw = context.store.read_json(context.artifact_relative("topic.json"))
    topic = {key: topic_raw.get(key) for key in ("slug", "service", "error_text", "error_code")}
    prompt_path = context.repo_root / "config/prompts/s3_extract.v1.md"
    schema_path = context.repo_root / "config/schemas/claims_extract.v1.json"
    instructions = prompt_path.read_text(encoding="utf-8")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["properties"]["claims"]["maxItems"] = cfg["max_claims_per_call"]
    evidence_schema = schema["properties"]["claims"]["items"]["properties"]["evidence"]
    evidence_schema["maxItems"] = cfg["max_evidence_per_claim"]
    evidence_schema["items"]["properties"]["quote"]["maxLength"] = cfg["max_quote_chars"]
    client = context.cache.get("llm_client") or LlmClient()
    manager = LlmCallManager(context.store, context.config, client)
    retry_unknown = bool(context.cache.get("retry_unknown_llm_calls"))
    all_claims: list[dict[str, Any]] = []
    model_markers: list[dict[str, str]] = []
    calls: list[dict[str, Any]] = []
    appearance = 0
    # A singleton is a deterministic source_id-ordered group.  The exact token
    # count is checked before R1; a source that cannot fit is never truncated.
    for source_id in sorted(texts):
        source = sources[source_id]
        payload = {
            "topic": topic,
            "sources": [{"source_id": source_id, "text_sha256": source["text"]["sha256"]}],
        }
        slot = f"extract:{source_id}-{source_id}"
        for validation_attempt in range(2):
            result = manager.execute(
                run_id=context.run_id, slug=topic["slug"], stage="S3_claims", slot=slot,
                stage_config=cfg, instructions=instructions, output_schema=schema,
                schema_name="claims_extract_v1", payload=payload,
                render=lambda value, nonce, texts=texts: _render_extract(value, nonce, texts),
                retry_unknown=retry_unknown, retry_terminal=validation_attempt == 1,
                max_input_tokens=cfg["max_input_tokens_per_call"],
            )
            if result.response.get("status") != "completed":
                raise PipelineError(
                    f"主張抽出の LLM 応答が completed ではありません: status={result.response.get('status')!r}"
                )
            try:
                value = _validate_extract(response_output_json(result.response), cfg)
                break
            except PipelineError as exc:
                invalid_count = manager.mark_output_invalid(context.run_id, result, str(exc))
                if validation_attempt == 1 or invalid_count >= 2:
                    raise
        calls.append(_call_copy(result))
        for claim in value["claims"]:
            matched = deepcopy(claim)
            matched["evidence"] = [match_evidence(item, sources, texts) for item in claim["evidence"]]
            matched["_appearance"] = appearance
            appearance += 1
            all_claims.append(matched)
        model_markers.extend(value["instruction_like_text"])

    def order(claim: dict[str, Any]) -> tuple[str, int, int]:
        first_source = "ZZZZ"
        first_line = 2**31 - 1
        if claim["evidence"]:
            first_source = str(claim["evidence"][0].get("source_id", "ZZZZ"))
            locations = claim["evidence"][0].get("quote_match", {}).get("locations", [])
            if locations:
                first_line = int(locations[0]["line_start"])
        return first_source, first_line, claim["_appearance"]

    output_claims = []
    for number, claim in enumerate(sorted(all_claims, key=order), 1):
        claim.pop("temp_id", None)
        claim.pop("_appearance", None)
        output_claims.append({"claim_id": f"C{number:03d}", **claim})
    output = {
        "schema": "claims_extracted/v1",
        "sources_index_sha256": context.store.hash(context.artifact_relative("sources/index.json")),
        "prompt_sha256": sha256_bytes(prompt_path.read_bytes()),
        "output_schema_sha256": sha256_bytes(canonical_json_bytes(schema)),
        "calls": calls,
        "claims": output_claims,
        "instruction_like_text": model_markers,
        "injection_markers": _markers(texts, context.config["claims"]["injection_markers"]),
    }
    context.write_json("claims.extracted.json", output)
