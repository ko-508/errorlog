"""Manual S1 research-plan construction."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from . import PipelineError
from .config import load_strict_yaml
from .store import canonical_json_bytes, sha256_bytes
from .urlpolicy import candidate_key, github_url_candidate, normalize_https_url, validate_repo


ROLES = {"official_impl", "official_doc", "case", "boundary", "other"}
ROOT_KEYS = {"schema", "candidates"}
COMMON_KEYS = {"role_hint", "note"}


def _candidate_from_url(url: Any, role: str, origins: list[str]) -> dict[str, Any]:
    normalized, anchor = normalize_https_url(url)
    converted = github_url_candidate(normalized, role_hint=role, origins=origins)
    if converted is not None:
        converted["anchor"] = anchor
        return converted
    return {
        "kind": "url",
        "url": normalized,
        "anchor": anchor,
        "role_hint": role,
        "origins": origins,
    }


def _candidate_from_mapping(item: Any, *, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise PipelineError(f"URL 候補は object が必要です: index={index}, value={item!r}")
    unknown = set(item) - (COMMON_KEYS | {"url", "github_file", "github_issue"})
    if unknown:
        raise PipelineError(f"URL 候補に未知のキーがあります: index={index}, keys={sorted(unknown)}")
    kinds = [key for key in ("url", "github_file", "github_issue") if key in item]
    if len(kinds) != 1:
        raise PipelineError(f"URL 候補は url/github_file/github_issue のどれか1種類だけ必要です: index={index}, found={kinds}")
    role = item.get("role_hint")
    if role not in ROLES:
        raise PipelineError(f"role_hint が不正です: index={index}, value={role!r}, allowed={sorted(ROLES)}")
    if "note" in item and not isinstance(item["note"], str):
        raise PipelineError(f"note は文字列が必要です: index={index}, value={item['note']!r}")
    kind = kinds[0]
    if kind == "url":
        return _candidate_from_url(item["url"], role, ["url_candidates"])
    value = item[kind]
    if not isinstance(value, dict):
        raise PipelineError(f"{kind} は object が必要です: index={index}, value={value!r}")
    if kind == "github_file":
        expected = {"repo", "path", "ref"}
        if set(value) != expected:
            raise PipelineError(f"github_file のキーが不正です: index={index}, actual={sorted(value)}, expected={sorted(expected)}")
        repo = validate_repo(value["repo"])
        path = value["path"]
        ref = value["ref"]
        if not isinstance(path, str) or not path or path.startswith("/") or ".." in Path(path).parts:
            raise PipelineError(f"github_file.path が不正です: index={index}, value={path!r}")
        if not isinstance(ref, str) or not ref:
            raise PipelineError(f"github_file.ref は空でない文字列が必要です: index={index}, value={ref!r}")
        return {"kind": kind, "repo": repo, "path": path, "ref": ref, "role_hint": role, "origins": ["url_candidates"]}
    expected = {"repo", "number"}
    if set(value) != expected:
        raise PipelineError(f"github_issue のキーが不正です: index={index}, actual={sorted(value)}, expected={sorted(expected)}")
    repo = validate_repo(value["repo"])
    number = value["number"]
    if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
        raise PipelineError(f"github_issue.number は正の整数が必要です: index={index}, value={number!r}")
    return {"kind": kind, "repo": repo, "number": number, "role_hint": role, "origins": ["url_candidates"]}


def load_candidates(path: Path, *, hint_urls: list[str], max_sources: int) -> dict[str, Any]:
    value = load_strict_yaml(path)
    if not isinstance(value, dict) or set(value) != ROOT_KEYS:
        actual = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise PipelineError(f"URL 候補ファイルのキーが不正です: path={path}, actual={actual}, expected={sorted(ROOT_KEYS)}")
    if value["schema"] != "url_candidates/v1":
        raise PipelineError(f"URL 候補ファイルの schema が未対応です: path={path}, value={value['schema']!r}")
    if not isinstance(value["candidates"], list):
        raise PipelineError(f"URL 候補ファイルの candidates は配列が必要です: path={path}")
    normalized = [
        _candidate_from_mapping(item, index=index)
        for index, item in enumerate(value["candidates"], start=1)
    ]
    for url in hint_urls:
        normalized.append(_candidate_from_url(url, "other", ["topic_hint_urls"]))

    merged: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    for candidate in normalized:
        key = candidate_key(candidate)
        if key in by_key:
            existing = by_key[key]
            for origin in candidate["origins"]:
                if origin not in existing["origins"]:
                    existing["origins"].append(origin)
            continue
        copy = deepcopy(candidate)
        copy["candidate_key"] = key
        by_key[key] = copy
        merged.append(copy)
    if len(merged) > max_sources:
        raise PipelineError(f"URL 候補が上限を超えています: count={len(merged)}, max_sources={max_sources}")
    for index, candidate in enumerate(merged, start=1):
        candidate["source_id"] = f"S{index:03d}"
    return {"schema": "research_plan/v1", "origin": "manual", "candidates": merged}


def normalized_candidates_hash(plan: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(plan))


def prepare_plan(*, state: dict[str, Any], config: dict[str, Any], topic: dict[str, Any]) -> dict[str, Any]:
    source = state.get("url_candidates_source")
    if config["plan"]["mode"] != "manual":
        raise PipelineError(f"P2 の plan.mode は manual 固定です: value={config['plan']['mode']!r}")
    if not isinstance(source, str) or not source:
        raise PipelineError("S1_plan の URL 候補ファイルが未登録です。new --url-candidates または attach-candidates を使ってください")
    path = Path(source)
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise PipelineError(f"URL 候補ファイルが存在しません: path={path}, error={exc}") from exc
    plan = load_candidates(
        resolved,
        hint_urls=topic.get("hint_urls", []),
        max_sources=config["acquire"]["max_sources"],
    )
    return {"plan": plan, "input_parts": {"url_candidates": normalized_candidates_hash(plan)}}
