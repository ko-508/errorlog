"""S2 source acquisition, reuse, staging, and manifest creation."""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlsplit

from . import PipelineError
from .decode import decode_body
from .github import git_blob_sha, issue_text, normalize_github_text, permalink
from .html_text import EXTRACTOR_VERSION, extract_html_text
from .net import FetchResult, NetFailure, NetworkClient
from .robots import ROBOTS_MAX_BYTES, allowed as robots_allowed, parse_robots
from .store import RunStore, canonical_json_bytes, sha256_bytes
from .urlpolicy import SHA_RE, static_policy_reason


STAGE_VERSION = EXTRACTOR_VERSION
SUCCESS_STATUSES = {"fetched", "reused"}
ALLOWED_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "text/markdown",
    "application/json",
}
REUSE_CONFIG_KEYS = {
    "max_body_bytes",
    "max_redirects",
    "challenge_markers",
    "min_text_chars",
    "issue_comment_pages_max",
    "user_agent",
}


def make_client(config: dict[str, Any]) -> NetworkClient:
    return NetworkClient(config)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise PipelineError(f"fetched_at を解析できません: value={value!r}, error={exc}") from exc


def reuse_config_hash(config: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes({key: config[key] for key in sorted(REUSE_CONFIG_KEYS)}))


def _content_type(headers: dict[str, str]) -> str | None:
    value = headers.get("content-type")
    return value.split(";", 1)[0].strip().lower() if value else None


def _content_type_allowed(value: str | None) -> bool:
    return value in ALLOWED_CONTENT_TYPES or bool(value and value.startswith("text/x-"))


def _ensure_http_result(result: FetchResult, *, purpose: str, require_json: bool = False) -> None:
    if result.http_status == 429:
        raise NetFailure("rate_limited", f"HTTP 429 を受け取りました: purpose={purpose}", attempts=result.attempts)
    if result.http_status >= 500:
        raise NetFailure("http_5xx", f"HTTP {result.http_status} を受け取りました: purpose={purpose}", attempts=result.attempts)
    if require_json and _content_type(result.headers) != "application/json":
        raise NetFailure(
            "content_type_not_allowed",
            f"GitHub API の Content-Type が application/json ではありません: purpose={purpose}, value={_content_type(result.headers)!r}",
            attempts=result.attempts,
        )


def _rate_limit_sufficient(result: FetchResult, *, required: int) -> tuple[bool, int | None]:
    remaining = result.headers.get("x-ratelimit-remaining")
    if remaining is None:
        return True, None
    try:
        value = int(remaining)
    except ValueError as exc:
        raise PipelineError(
            f"X-RateLimit-Remaining が整数ではありません: value={remaining!r}"
        ) from exc
    return value >= required, value


def _request_record(number: int, purpose: str, result: FetchResult, body_path: str) -> dict[str, Any]:
    return {
        "n": number,
        "purpose": purpose,
        "url": result.url,
        "final_url": result.final_url,
        "redirects": result.redirects,
        "resolved_ip": result.resolved_ip,
        "http_status": result.http_status,
        "headers": result.headers,
        "body_path": body_path,
        "body_sha256": sha256_bytes(result.body),
        "body_bytes": len(result.body),
        "attempts": result.attempts,
    }


def _base_source(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": candidate["source_id"],
        "candidate_key": candidate["candidate_key"],
        "kind": candidate["kind"],
        "role_hint": candidate["role_hint"],
        "origins": candidate["origins"],
        "anchor": candidate.get("anchor"),
        "status": None,
        "reason": None,
        "untrusted": True,
        "requests": [],
        "reused_from": None,
        "mentions_errorlog": False,
    }


class Acquirer:
    def __init__(
        self,
        *,
        store: RunStore,
        run_id: str,
        mode: str,
        slug: str,
        config: dict[str, Any],
        client: NetworkClient,
        refetch: str | None,
        previous_root: Path | None,
        previous_quarantined: bool,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.store = store
        self.run_id = run_id
        self.mode = mode
        self.slug = slug
        self.config = config
        self.client = client
        self.refetch = refetch
        self.previous_root = previous_root
        self.previous_quarantined = previous_quarantined
        self.monotonic = monotonic
        self.run_deadline = monotonic() + config["run_deadline_s"]
        self.total_bytes = 0
        self.robots_cache: dict[str, dict[str, Any]] = {}
        self.robots_records: dict[str, dict[str, Any]] = {}
        self.staging = Path("runs") / run_id / "sources.staging"
        self.previous_index: dict[str, Any] | None = None
        self.previous_by_key: dict[str, dict[str, Any]] = {}
        self.previous_index_hash: str | None = None
        self.source_deadline: float | None = None

    def run(self, plan: dict[str, Any]) -> dict[str, Any]:
        sources = Path("runs") / self.run_id / "sources"
        if self.store.exists(sources) or self.store.exists(self.staging):
            raise PipelineError(
                "S2 開始時に sources/ または sources.staging/ が残っています: "
                f"sources={self.store.exists(sources)}, staging={self.store.exists(self.staging)}"
            )
        self.store.mkdir(self.staging, exclusive=True)
        self._load_previous()
        results: list[dict[str, Any]] = []
        candidates = plan.get("candidates") if isinstance(plan, dict) else None
        if not isinstance(candidates, list):
            raise PipelineError("research_plan.json の candidates が配列ではありません")
        for index, candidate in enumerate(candidates):
            if self.monotonic() >= self.run_deadline:
                for remaining in candidates[index:]:
                    item = _base_source(remaining)
                    item.update(status="failed", reason="run_deadline_exceeded")
                    results.append(item)
                break
            reused = self._reuse(candidate)
            if reused is not None:
                results.append(reused)
                continue
            if self.total_bytes >= self.config["max_total_bytes"]:
                item = _base_source(candidate)
                item.update(status="rejected", reason="run_budget_exceeded")
                results.append(item)
                continue
            self.source_deadline = min(
                self.run_deadline,
                self.monotonic() + self.config["source_deadline_s"],
            )
            try:
                results.append(self._fetch_candidate(candidate))
            finally:
                self.source_deadline = None

        summary = Counter(item["status"] for item in results)
        summary_payload = {
            key: summary.get(key, 0)
            for key in ("fetched", "reused", "failed", "blocked", "empty", "rejected")
        }
        members = self._members()
        index = {
            "schema": "sources_index/v1",
            "run_id": self.run_id,
            "mode": self.mode,
            "plan_sha256": sha256_bytes(canonical_json_bytes(plan)),
            "acquire_config_sha256": sha256_bytes(canonical_json_bytes(self.config)),
            "reuse_config_sha256": reuse_config_hash(self.config),
            "extractor_version": EXTRACTOR_VERSION,
            "summary": summary_payload,
            "sources": results,
            "robots": sorted(
                [
                    {key: value for key, value in item.items() if not key.startswith("_")}
                    for item in self.robots_records.values()
                ],
                key=lambda item: item["host"],
            ),
            "members": members,
        }
        self.store.write_json(self.staging / "index.json", index)
        self._verify_staging(index)
        self.store.move_tree(self.staging, sources)
        if not any(item["status"] in SUCCESS_STATUSES for item in results):
            raise PipelineError(
                "S2 で fetched または reused の資料が1件もありません: "
                f"summary={summary_payload}"
            )
        return index

    def _load_previous(self) -> None:
        if self.previous_root is None or self.previous_quarantined or self.refetch == "all":
            return
        index_path = self.previous_root / "sources/index.json"
        if not self.store.exists(index_path):
            if self.refetch == "failed":
                raise PipelineError("前回の sources/index.json がありません。--refetch all を指定してください")
            return
        errors = validate_index_tree(self.store, self.previous_root / "sources")
        if errors:
            if self.refetch == "failed":
                raise PipelineError(
                    "前回の資料が不完全なため再利用できません。--refetch all を指定してください: "
                    + "; ".join(errors)
                )
            return
        index = self.store.read_json(index_path)
        by_key: dict[str, dict[str, Any]] = {}
        for source in index.get("sources", []):
            key = source.get("candidate_key")
            if not isinstance(key, str):
                continue
            if key in by_key:
                raise PipelineError(f"前回の index.json に candidate_key の重複があります: key={key}")
            by_key[key] = source
        self.previous_index = index
        self.previous_by_key = by_key
        self.previous_index_hash = self.store.hash(index_path)

    def _reuse(self, candidate: dict[str, Any]) -> dict[str, Any] | None:
        if self.previous_index is None or self.previous_root is None:
            return None
        old = self.previous_by_key.get(candidate["candidate_key"])
        if old is None or old.get("status") not in SUCCESS_STATUSES:
            return None
        if self.refetch == "failed" and old.get("status") == "failed":
            return None
        fetched_at = old.get("fetched_at")
        if not isinstance(fetched_at, str):
            return None
        age = datetime.now(timezone.utc) - _parse_time(fetched_at)
        if age.total_seconds() > self.config["reuse_max_age_hours"] * 3600:
            return None
        if self.previous_index.get("reuse_config_sha256") != reuse_config_hash(self.config):
            return None
        urls = []
        for request in old.get("requests", []):
            urls.extend([request.get("url"), request.get("final_url")])
            urls.extend(item.get("to") for item in request.get("redirects", []))
        for url in [value for value in urls if isinstance(value, str)]:
            reason = static_policy_reason(candidate=candidate, url=url, config=self.config, mode=self.mode)
            if reason is not None:
                return None
        if self.mode == "comparison" and old.get("mentions_errorlog"):
            return None

        old_id = old["source_id"]
        new_id = candidate["source_id"]
        copied_paths: set[str] = set()
        for member in self.previous_index["members"]:
            member_path = member["path"]
            if member_path.startswith(old_id + "/"):
                destination = new_id + member_path[len(old_id):]
            elif member_path == old.get("robots_ref"):
                destination = member_path
            else:
                continue
            source = self.previous_root / "sources" / member_path
            target = self.staging / destination
            if self.store.exists(target):
                if self.store.hash(target) != member["sha256"]:
                    raise PipelineError(f"再利用先に異なる内容のファイルがあります: path={target}")
            else:
                self.store.copy_bytes(source, target)
            if self.store.hash(target) != member["sha256"]:
                raise PipelineError(f"再利用コピー後のハッシュが一致しません: source={source}, destination={target}")
            copied_paths.add(destination)

        reused = deepcopy(old)
        reused["source_id"] = new_id
        reused["candidate_key"] = candidate["candidate_key"]
        reused["role_hint"] = candidate["role_hint"]
        reused["origins"] = candidate["origins"]
        reused["anchor"] = candidate.get("anchor")
        reused["status"] = "reused"
        reused["reason"] = None
        for request in reused.get("requests", []):
            body_path = request.get("body_path")
            if isinstance(body_path, str) and body_path.startswith(old_id + "/"):
                request["body_path"] = new_id + body_path[len(old_id):]
        text_info = reused.get("text")
        if isinstance(text_info, dict) and isinstance(text_info.get("path"), str):
            text_info["path"] = new_id + text_info["path"][len(old_id):]
        if self.previous_index.get("extractor_version") != EXTRACTOR_VERSION:
            self._rederive_text(reused)
            reused["text_rederived"] = True
        reused["reused_from"] = {
            "index_sha256": self.previous_index_hash,
            "source_id": old_id,
            "candidate_key": candidate["candidate_key"],
        }
        robots_ref = reused.get("robots_ref")
        if isinstance(robots_ref, str):
            matches = [
                record for record in self.previous_index.get("robots", [])
                if isinstance(record, dict) and record.get("body_path") == robots_ref
            ]
            if len(matches) != 1:
                raise PipelineError(
                    "再利用する robots_ref の記録が一意ではありません: "
                    f"robots_ref={robots_ref}, count={len(matches)}"
                )
            self.robots_records[robots_ref] = deepcopy(matches[0])
        if not copied_paths:
            raise PipelineError(f"再利用する資料ファイルが見つかりません: candidate_key={candidate['candidate_key']}")
        return reused

    def _rederive_text(self, source: dict[str, Any]) -> None:
        requests = source.get("requests")
        if not isinstance(requests, list):
            raise PipelineError("再導出する資料の requests が配列ではありません")

        def request_body(purpose: str) -> tuple[dict[str, Any], bytes]:
            matches = [item for item in requests if item.get("purpose") == purpose]
            if len(matches) != 1 or not isinstance(matches[0].get("body_path"), str):
                raise PipelineError(
                    f"再導出に必要な応答が一意ではありません: purpose={purpose}, count={len(matches)}"
                )
            record = matches[0]
            body = self.store.read_bytes(self.staging / record["body_path"])
            if sha256_bytes(body) != record.get("body_sha256"):
                raise PipelineError(
                    f"再導出する応答のハッシュが一致しません: purpose={purpose}, path={record['body_path']}"
                )
            return record, body

        kind = source.get("kind")
        if kind == "url":
            record, body = request_body("source")
            headers = record.get("headers") if isinstance(record.get("headers"), dict) else {}
            content_type = _content_type(headers)
            is_html = content_type in {"text/html", "application/xhtml+xml"}
            decoded = decode_body(
                body,
                content_type=headers.get("content-type", ""),
                is_html=is_html,
            )
            if decoded.reason is not None or decoded.text is None:
                raise PipelineError(
                    f"保存済み応答を再導出できません: reason={decoded.reason}, position={decoded.error_position}"
                )
            if is_html:
                text, extraction = extract_html_text(decoded.text)
            else:
                text, extraction = decoded.text, None
            source["decode"] = {
                "charset": decoded.charset,
                "decided_by": decoded.decided_by,
                "bom": decoded.bom,
            }
            source["extraction"] = extraction
        elif kind == "github_file":
            record, body = request_body("github_raw")
            headers = record.get("headers") if isinstance(record.get("headers"), dict) else {}
            decoded = decode_body(
                body,
                content_type=headers.get("content-type", ""),
                is_html=False,
                force_utf8=True,
            )
            if decoded.reason is not None or decoded.text is None:
                raise PipelineError(
                    f"保存済み GitHub 応答を再導出できません: reason={decoded.reason}, position={decoded.error_position}"
                )
            text, line_anchor = normalize_github_text(decoded.text)
            source["decode"] = {
                "charset": decoded.charset,
                "decided_by": decoded.decided_by,
                "bom": decoded.bom,
            }
            source["extraction"] = None
            if isinstance(source.get("github"), dict):
                source["github"]["line_anchor"] = line_anchor
        elif kind == "github_issue":
            _record, issue_body = request_body("github_issue")
            try:
                issue = json.loads(issue_body.decode("utf-8", errors="strict"))
                comments: list[dict[str, Any]] = []
                for record in requests:
                    if record.get("purpose") != "github_comments":
                        continue
                    body = self.store.read_bytes(self.staging / record["body_path"])
                    if sha256_bytes(body) != record.get("body_sha256"):
                        raise PipelineError(
                            f"再導出するコメント応答のハッシュが一致しません: path={record['body_path']}"
                        )
                    page = json.loads(body.decode("utf-8", errors="strict"))
                    if not isinstance(page, list):
                        raise PipelineError("再導出する GitHub コメント応答が配列ではありません")
                    comments.extend(item for item in page if isinstance(item, dict))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise PipelineError(f"保存済み GitHub Issue 応答を再導出できません: error={exc}") from exc
            if not isinstance(issue, dict):
                raise PipelineError("再導出する GitHub Issue 応答が object ではありません")
            text = issue_text(issue, comments)
            source["extraction"] = None
        else:
            raise PipelineError(f"再導出する資料の kind が不正です: kind={kind!r}")
        text_info = source.get("text")
        if not isinstance(text_info, dict) or not isinstance(text_info.get("path"), str):
            raise PipelineError("再導出する資料の text.path がありません")
        self.store.write_text(self.staging / text_info["path"], text)
        text_info.update(
            sha256=sha256_bytes(text.encode("utf-8")),
            chars=len(text),
            lines=len(text.splitlines()),
        )

    def _fetch_candidate(self, candidate: dict[str, Any]) -> dict[str, Any]:
        item = _base_source(candidate)
        try:
            if candidate["kind"] == "url":
                return self._fetch_url(candidate, item)
            if candidate["kind"] == "github_file":
                return self._fetch_github_file(candidate, item)
            if candidate["kind"] == "github_issue":
                return self._fetch_github_issue(candidate, item)
            raise PipelineError(f"research_plan の kind が不正です: value={candidate['kind']!r}")
        except NetFailure as exc:
            item.update(status="failed", reason=exc.reason, detail={"message": exc.detail}, attempts=exc.attempts)
            return item

    def _policy(self, candidate: dict[str, Any]) -> Callable[[str, list[str]], str | None]:
        return lambda url, _addresses: static_policy_reason(
            candidate=candidate, url=url, config=self.config, mode=self.mode
        )

    def _source_limit(self) -> float:
        if self.source_deadline is None:
            raise PipelineError("資料の時間上限が設定されていません")
        return self.source_deadline

    def _fetch_url(self, candidate: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
        url = candidate["url"]
        reason = static_policy_reason(candidate=candidate, url=url, config=self.config, mode=self.mode)
        if reason is not None:
            item.update(status="rejected", reason=reason)
            return item
        robots_ref, robots_reason = self._robots(candidate, url)
        if robots_reason is not None:
            item.update(status="failed" if robots_reason == "robots_unreachable" else "rejected", reason=robots_reason)
            return item
        result = self.client.fetch(
            url,
            policy_check=self._policy(candidate),
            source_deadline=self._source_limit(),
            run_deadline=self.run_deadline,
        )
        return self._store_text_response(candidate, item, result, purpose="source", number=1, robots_ref=robots_ref)

    def _robots(self, candidate: dict[str, Any], url: str) -> tuple[str | None, str | None]:
        host = urlsplit(url).hostname or ""
        if host in self.robots_cache:
            record = self.robots_cache[host]
            if record.get("reason"):
                return record.get("body_path"), record["reason"]
            rules = record["_rules"]
            return record.get("body_path"), None if robots_allowed(rules, url) else "robots_disallow"
        robots_url = f"https://{host}/robots.txt"
        try:
            result = self.client.fetch(
                robots_url,
                policy_check=self._policy(candidate),
                source_deadline=self._source_limit(),
                run_deadline=self.run_deadline,
            )
        except NetFailure as exc:
            self.robots_cache[host] = {"host": host, "reason": "robots_unreachable", "detail": exc.detail, "_rules": []}
            return None, "robots_unreachable"
        if result.http_status >= 500:
            self.robots_cache[host] = {"host": host, "http_status": result.http_status, "reason": "robots_unreachable", "_rules": []}
            return None, "robots_unreachable"
        body = result.body[:ROBOTS_MAX_BYTES]
        digest = sha256_bytes(body)
        path = f"_robots/{host}/{digest.removeprefix('sha256:')}.bin"
        self.store.write_bytes(self.staging / path, body)
        if 200 <= result.http_status < 300:
            try:
                rules = parse_robots(body)
            except PipelineError as exc:
                self.robots_cache[host] = {
                    "host": host,
                    "http_status": result.http_status,
                    "reason": "robots_unreachable",
                    "detail": str(exc),
                    "body_path": path,
                    "body_sha256": digest,
                    "fetched_at": utc_now(),
                    "_rules": [],
                }
                self.robots_records[path] = self.robots_cache[host]
                return path, "robots_unreachable"
        else:
            rules = []
        record = {
            "host": host,
            "http_status": result.http_status,
            "parsed_rules": len(rules),
            "body_path": path,
            "body_sha256": digest,
            "fetched_at": utc_now(),
            "reason": None,
            "_rules": rules,
        }
        self.robots_cache[host] = record
        self.robots_records[path] = record
        return path, None if robots_allowed(rules, url) else "robots_disallow"

    def _store_text_response(
        self,
        candidate: dict[str, Any],
        item: dict[str, Any],
        result: FetchResult,
        *,
        purpose: str,
        number: int,
        robots_ref: str | None,
        force_utf8: bool = False,
    ) -> dict[str, Any]:
        source_id = candidate["source_id"]
        body_path = f"{source_id}/responses/{number:02d}.bin"
        self.store.write_bytes(self.staging / body_path, result.body)
        self.total_bytes += len(result.body)
        request = _request_record(number, purpose, result, body_path)
        item["requests"].append(request)
        if result.http_status in {403, 429, 503}:
            challenge_type = _content_type(result.headers)
            if _content_type_allowed(challenge_type):
                challenge_decoded = decode_body(
                    result.body,
                    content_type=result.headers.get("content-type", ""),
                    is_html=challenge_type in {"text/html", "application/xhtml+xml"},
                    force_utf8=force_utf8,
                )
                if challenge_decoded.text is not None:
                    marker = next(
                        (
                            value for value in self.config["challenge_markers"]
                            if value.lower() in challenge_decoded.text.lower()
                        ),
                        None,
                    )
                    if marker is not None:
                        item.update(status="blocked", reason="challenge_page", detail={"marker": marker})
                        return item
        if result.http_status == 429 or result.http_status >= 500:
            item.update(status="failed", reason="http_5xx" if result.http_status >= 500 else "rate_limited")
            return item
        if result.http_status >= 400:
            item.update(status="failed", reason="http_4xx", detail={"http_status": result.http_status})
            return item
        content_type = _content_type(result.headers)
        if not _content_type_allowed(content_type):
            item.update(status="rejected", reason="content_type_not_allowed", detail={"content_type": content_type})
            return item
        is_html = content_type in {"text/html", "application/xhtml+xml"}
        decoded = decode_body(
            result.body,
            content_type=result.headers.get("content-type", ""),
            is_html=is_html,
            force_utf8=force_utf8,
        )
        item["decode"] = {
            "charset": decoded.charset,
            "decided_by": decoded.decided_by,
            "bom": decoded.bom,
        }
        if decoded.reason is not None:
            item.update(status="rejected", reason=decoded.reason, detail={"error_position": decoded.error_position})
            return item
        assert decoded.text is not None
        if is_html:
            text, extraction = extract_html_text(decoded.text)
            item["extraction"] = extraction
        else:
            text, item["extraction"] = decoded.text, None
        if len(text) < self.config["min_text_chars"]:
            item.update(status="empty", reason="text_too_short", detail={"chars": len(text)})
            return item
        if self.mode == "comparison" and f"errorlog.jp/posts/{self.slug}" in text:
            item.update(status="rejected", reason="references_comparison_target")
            return item
        item["mentions_errorlog"] = "errorlog.jp" in text
        text_path = f"{source_id}/text.txt"
        self.store.write_text(self.staging / text_path, text)
        item.update(
            status="fetched",
            reason=None,
            fetched_at=utc_now(),
            text={
                "path": text_path,
                "sha256": sha256_bytes(text.encode("utf-8")),
                "chars": len(text),
                "lines": len(text.splitlines()),
            },
            robots_ref=robots_ref,
        )
        return item

    def _api_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        token = os.environ.get("ARTICLE_PIPELINE_GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _api_json(self, candidate: dict[str, Any], url: str, purpose: str, number: int) -> tuple[dict[str, Any] | list[Any], FetchResult, str]:
        result = self.client.fetch(url, headers=self._api_headers(), policy_check=self._policy(candidate), source_deadline=self._source_limit(), run_deadline=self.run_deadline)
        _ensure_http_result(result, purpose=purpose, require_json=True)
        path = f"{candidate['source_id']}/responses/{number:02d}.bin"
        self.store.write_bytes(self.staging / path, result.body)
        self.total_bytes += len(result.body)
        try:
            value = json.loads(result.body.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PipelineError(f"GitHub API 応答を UTF-8 JSON として解析できません: url={url}, error={exc}") from exc
        return value, result, path

    def _fetch_github_file(self, candidate: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
        repo, ref, path = candidate["repo"], candidate["ref"], candidate["path"]
        api = "https://api.github.com/repos/" + repo
        commit_value, commit_result, commit_path = self._api_json(candidate, f"{api}/commits/{quote(ref, safe='')}", "github_commit", 1)
        item["requests"].append(_request_record(1, "github_commit", commit_result, commit_path))
        if not isinstance(commit_value, dict) or not isinstance(commit_value.get("sha"), str) or not SHA_RE.fullmatch(commit_value["sha"]):
            item.update(status="failed", reason="github_ref_ambiguous")
            return item
        commit_sha = commit_value["sha"].lower()
        required_after_first = 2 + (0 if SHA_RE.fullmatch(ref) else 1)
        sufficient, remaining = _rate_limit_sufficient(commit_result, required=required_after_first)
        if not sufficient:
            item.update(status="failed", reason="github_rate_limit_insufficient", detail={"remaining": remaining, "required": required_after_first, "reset": commit_result.headers.get("x-ratelimit-reset")})
            return item
        contents_value, contents_result, contents_path = self._api_json(candidate, f"{api}/contents/{quote(path)}?ref={commit_sha}", "github_contents", 2)
        item["requests"].append(_request_record(2, "github_contents", contents_result, contents_path))
        if not isinstance(contents_value, dict) or contents_value.get("type") != "file":
            item.update(status="rejected", reason="github_not_a_file", detail={"type": contents_value.get("type") if isinstance(contents_value, dict) else None})
            return item
        blob_sha = contents_value.get("sha")
        raw_url = f"https://raw.githubusercontent.com/{repo}/{commit_sha}/{quote(path, safe='/')}"
        robots_ref, robots_reason = self._robots(candidate, raw_url)
        if robots_reason is not None:
            item.update(status="failed" if robots_reason == "robots_unreachable" else "rejected", reason=robots_reason)
            return item
        raw_result = self.client.fetch(raw_url, policy_check=self._policy(candidate), source_deadline=self._source_limit(), run_deadline=self.run_deadline)
        _ensure_http_result(raw_result, purpose="github_raw")
        raw_path = f"{candidate['source_id']}/responses/03.bin"
        self.store.write_bytes(self.staging / raw_path, raw_result.body)
        self.total_bytes += len(raw_result.body)
        item["requests"].append(_request_record(3, "github_raw", raw_result, raw_path))
        if not _content_type_allowed(_content_type(raw_result.headers)):
            item.update(status="rejected", reason="content_type_not_allowed", detail={"content_type": _content_type(raw_result.headers)})
            return item
        if not isinstance(blob_sha, str) or git_blob_sha(raw_result.body) != blob_sha:
            item.update(status="failed", reason="github_blob_mismatch", detail={"expected": blob_sha, "actual": git_blob_sha(raw_result.body)})
            return item
        ref_kind = "sha" if SHA_RE.fullmatch(ref) else "branch"
        version = {"value": None, "method": "none"}
        if ref_kind != "sha":
            tag_result = self.client.fetch(f"{api}/git/ref/tags/{quote(ref, safe='')}", headers=self._api_headers(), policy_check=self._policy(candidate), source_deadline=self._source_limit(), run_deadline=self.run_deadline)
            _ensure_http_result(tag_result, purpose="github_tag", require_json=True)
            tag_path = f"{candidate['source_id']}/responses/04.bin"
            self.store.write_bytes(self.staging / tag_path, tag_result.body)
            self.total_bytes += len(tag_result.body)
            item["requests"].append(_request_record(4, "github_tag", tag_result, tag_path))
            if tag_result.http_status == 200:
                ref_kind = "tag"
                version = {"value": ref, "method": "github_tag"}
        decoded = decode_body(raw_result.body, content_type=raw_result.headers.get("content-type", ""), is_html=False, force_utf8=True)
        if decoded.reason is not None or decoded.text is None:
            item.update(status="rejected", reason=decoded.reason, detail={"error_position": decoded.error_position})
            return item
        text, line_anchor = normalize_github_text(decoded.text)
        if len(text) < self.config["min_text_chars"]:
            item.update(status="empty", reason="text_too_short")
            return item
        text_path = f"{candidate['source_id']}/text.txt"
        self.store.write_text(self.staging / text_path, text)
        commit_date = None
        if isinstance(commit_value.get("commit"), dict) and isinstance(commit_value["commit"].get("committer"), dict):
            commit_date = commit_value["commit"]["committer"].get("date")
        item.update(
            status="fetched", reason=None, fetched_at=utc_now(), robots_ref=robots_ref,
            decode={"charset": decoded.charset, "decided_by": decoded.decided_by, "bom": decoded.bom},
            text={"path": text_path, "sha256": sha256_bytes(text.encode("utf-8")), "chars": len(text), "lines": len(text.splitlines())},
            extraction=None,
            github={"repo": repo, "path": path, "ref_input": ref, "ref_kind": ref_kind, "commit_sha": commit_sha, "commit_date": commit_date, "blob_sha": blob_sha, "blob_sha_verified": True, "permalink": permalink(repo, commit_sha, path), "line_anchor": line_anchor},
            version=version,
        )
        return item

    def _fetch_github_issue(self, candidate: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
        repo, number = candidate["repo"], candidate["number"]
        api = f"https://api.github.com/repos/{repo}/issues/{number}"
        issue, result, path = self._api_json(candidate, api, "github_issue", 1)
        item["requests"].append(_request_record(1, "github_issue", result, path))
        if not isinstance(issue, dict):
            item.update(status="failed", reason="github_api_shape")
            return item
        sufficient, remaining = _rate_limit_sufficient(
            result, required=self.config["issue_comment_pages_max"]
        )
        if not sufficient:
            item.update(
                status="failed",
                reason="github_rate_limit_insufficient",
                detail={
                    "remaining": remaining,
                    "required": self.config["issue_comment_pages_max"],
                    "reset": result.headers.get("x-ratelimit-reset"),
                },
            )
            return item
        comments: list[dict[str, Any]] = []
        truncated = False
        request_number = 2
        for page in range(1, self.config["issue_comment_pages_max"] + 1):
            page_value, page_result, page_path = self._api_json(candidate, f"{api}/comments?per_page=100&page={page}", "github_comments", request_number)
            item["requests"].append(_request_record(request_number, "github_comments", page_result, page_path))
            request_number += 1
            if not isinstance(page_value, list):
                item.update(status="failed", reason="github_api_shape")
                return item
            if not page_value:
                break
            comments.extend(value for value in page_value if isinstance(value, dict))
            if page == self.config["issue_comment_pages_max"] and len(page_value) == 100:
                truncated = True
        text = issue_text(issue, comments)
        if len(text) < self.config["min_text_chars"]:
            item.update(status="empty", reason="text_too_short")
            return item
        text_path = f"{candidate['source_id']}/text.txt"
        self.store.write_text(self.staging / text_path, text)
        item.update(
            status="fetched", reason=None, fetched_at=utc_now(), robots_ref=None,
            decode={"charset": "utf-8", "decided_by": "github_api_json", "bom": False},
            text={"path": text_path, "sha256": sha256_bytes(text.encode("utf-8")), "chars": len(text), "lines": len(text.splitlines())},
            extraction=None,
            github={"repo": repo, "number": number, "html_url": issue.get("html_url"), "pull_request": "pull_request" in issue, "truncated": truncated},
            version={"value": None, "method": "none"},
        )
        return item

    def _members(self) -> list[dict[str, str]]:
        members = []
        for entry in self.store.inspect_tree(self.staging):
            if entry["kind"] != "file" or entry["path"] == "index.json":
                continue
            members.append({"path": entry["path"], "sha256": entry["sha256"]})
        return members

    def _verify_staging(self, index: dict[str, Any]) -> None:
        expected = {"index.json", *(member["path"] for member in index["members"])}
        inventory = self.store.inspect_tree(self.staging)
        actual = {entry["path"] for entry in inventory}
        if actual != expected:
            raise PipelineError(f"sources.staging の内容がマニフェストと一致しません: missing={sorted(expected-actual)}, extra={sorted(actual-expected)}")
        for member in index["members"]:
            actual_hash = self.store.hash(self.staging / member["path"])
            if actual_hash != member["sha256"]:
                raise PipelineError(f"sources.staging のハッシュが一致しません: path={member['path']}, expected={member['sha256']}, actual={actual_hash}")


def validate_index_tree(store: RunStore, root: Path) -> list[str]:
    errors: list[str] = []
    index_path = root / "index.json"
    if not store.exists(index_path):
        return [f"missing: {index_path.as_posix()}"]
    try:
        index = store.read_json(index_path)
    except PipelineError as exc:
        return [str(exc)]
    members = index.get("members") if isinstance(index, dict) else None
    if not isinstance(members, list):
        return ["index.json の members が配列ではありません"]
    expected = {"index.json"}
    for member in members:
        if not isinstance(member, dict) or set(member) != {"path", "sha256"}:
            errors.append(f"invalid member: {member!r}")
            continue
        expected.add(member["path"])
        path = root / member["path"]
        if not store.exists(path):
            errors.append(f"missing: {member['path']}")
        else:
            actual = store.hash(path)
            if actual != member["sha256"]:
                errors.append(f"modified: {member['path']}, expected={member['sha256']}, actual={actual}")
    actual = {entry["path"] for entry in store.inspect_tree(root)}
    for extra in sorted(actual - expected):
        errors.append(f"extra: {extra}")
    return errors


def run_acquire(context: Any, state: dict[str, Any]) -> None:
    plan_relative = context.artifact_relative("research_plan.json")
    plan = context.store.read_json(plan_relative)
    stage_record = state["stages"]["S2_sources"]
    superseded = stage_record.get("superseded_dir")
    previous_root = (
        Path("runs") / context.run_id / superseded if isinstance(superseded, str) else None
    )
    client = context.cache.get("network_client") or make_client(context.config["acquire"])
    acquirer = Acquirer(
        store=context.store,
        run_id=context.run_id,
        mode=state["mode"],
        slug=state["slug"],
        config=context.config["acquire"],
        client=client,
        refetch=context.cache.get("refetch"),
        previous_root=previous_root,
        previous_quarantined=bool(context.cache.get("previous_S2_quarantined")),
    )
    acquirer.run(plan)
    return None
