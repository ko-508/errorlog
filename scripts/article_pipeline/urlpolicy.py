"""URL normalization and acquisition policy checks."""

from __future__ import annotations

import ipaddress
import re
from typing import Any, Iterable
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from . import PipelineError
from .store import canonical_json_bytes, sha256_bytes


REPO_RE = re.compile(r"^[^/\s]+/[^/\s]+$")
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def normalize_https_url(value: str) -> tuple[str, str | None]:
    if not isinstance(value, str) or not value:
        raise PipelineError(f"URL は空でない文字列が必要です: value={value!r}")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise PipelineError(f"URL を解析できません: url={value!r}, error={exc}") from exc
    if parsed.scheme.lower() != "https":
        raise PipelineError(f"URL は https:// に限ります: url={value!r}")
    if parsed.username is not None or parsed.password is not None:
        raise PipelineError(f"ユーザー情報付き URL は使用できません: url={value!r}")
    if not parsed.hostname:
        raise PipelineError(f"URL のホストが空です: url={value!r}")
    try:
        ipaddress.ip_address(parsed.hostname.strip("[]"))
    except ValueError:
        pass
    else:
        raise PipelineError(f"IP アドレスを直接指定した URL は使用できません: url={value!r}")
    if port not in (None, 443):
        raise PipelineError(f"URL のポートは 443 のみ許可します: url={value!r}, port={port}")
    try:
        host = parsed.hostname.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise PipelineError(f"URL のホストを IDNA に変換できません: url={value!r}, error={exc}") from exc
    netloc = host if port in (None, 443) else f"{host}:{port}"
    path = quote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~")
    normalized = urlunsplit(("https", netloc, path, parsed.query, ""))
    return normalized, parsed.fragment or None


def validate_repo(repo: Any) -> str:
    if not isinstance(repo, str) or not REPO_RE.fullmatch(repo):
        raise PipelineError(f"GitHub repo は owner/name 形式が必要です: value={repo!r}")
    return repo


def candidate_key(candidate: dict[str, Any]) -> str:
    kind = candidate["kind"]
    if kind == "url":
        identity = {"kind": kind, "url": candidate["url"]}
    elif kind == "github_file":
        identity = {
            "kind": kind,
            "repo": candidate["repo"],
            "path": candidate["path"],
            "ref": candidate["ref"],
        }
    elif kind == "github_issue":
        identity = {"kind": kind, "repo": candidate["repo"], "number": candidate["number"]}
    else:
        raise PipelineError(f"候補 kind が不正です: kind={kind!r}")
    return sha256_bytes(canonical_json_bytes(identity))


def github_url_candidate(url: str, *, role_hint: str, origins: list[str]) -> dict[str, Any] | None:
    parsed = urlsplit(url)
    if parsed.hostname != "github.com":
        return None
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if len(parts) >= 5 and parts[2] == "blob":
        candidate = {
            "kind": "github_file",
            "repo": f"{parts[0]}/{parts[1]}",
            "ref": parts[3],
            "path": "/".join(parts[4:]),
            "role_hint": role_hint,
            "origins": origins,
        }
        return candidate
    if len(parts) == 4 and parts[2] in {"issues", "pull"} and parts[3].isdigit():
        number = int(parts[3])
        if number <= 0:
            raise PipelineError(f"GitHub Issue 番号は正の整数が必要です: url={url}")
        return {
            "kind": "github_issue",
            "repo": f"{parts[0]}/{parts[1]}",
            "number": number,
            "role_hint": role_hint,
            "origins": origins,
        }
    return {
        "kind": "url",
        "url": url,
        "anchor": parsed.fragment or None,
        "role_hint": role_hint,
        "origins": origins,
        "github_html_unsupported": True,
    }


def host_matches(host: str, configured: str, include_subdomains: bool = True) -> bool:
    return host == configured or (include_subdomains and host.endswith("." + configured))


def static_policy_reason(
    *,
    candidate: dict[str, Any],
    url: str,
    config: dict[str, Any],
    mode: str,
) -> str | None:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or parsed.port not in (None, 443):
        return "scheme_not_allowed"
    repo = candidate.get("repo")
    if any(host_matches(host, item) for item in config["self_hosts"]):
        return "self_source"
    if isinstance(repo, str) and repo.lower() in {item.lower() for item in config["self_repos"]}:
        return "self_source"
    if mode == "comparison" and any(
        host_matches(host, item) for item in config["comparison_denied_hosts"]
    ):
        return "comparison_excluded"
    if candidate.get("github_html_unsupported"):
        return "github_html_not_supported"
    allowed = any(
        host_matches(host, item["host"], item["include_subdomains"])
        for item in config["allowed_hosts"]
    )
    if not allowed:
        return "host_not_allowed"
    return None


def address_is_public(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise PipelineError(f"名前解決結果が IP アドレスではありません: value={value!r}") from exc
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return False
    if address.version == 4 and address in ipaddress.ip_network("100.64.0.0/10"):
        return False
    return bool(address.is_global)


def all_addresses_public(addresses: Iterable[str]) -> bool:
    values = list(addresses)
    return bool(values) and all(address_is_public(value) for value in values)
