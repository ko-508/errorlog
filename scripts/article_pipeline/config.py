"""Strict configuration loading for the article pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import PipelineError

try:
    import yaml
except ImportError:
    yaml = None


if yaml is not None:
    class UniqueKeyLoader(yaml.SafeLoader):
        pass


    def _construct_unique_mapping(loader: Any, node: Any, deep: bool = False) -> dict[Any, Any]:
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in mapping:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"duplicate key: {key!r}",
                    key_node.start_mark,
                )
            mapping[key] = loader.construct_object(value_node, deep=deep)
        return mapping


    UniqueKeyLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        _construct_unique_mapping,
    )


def load_strict_yaml(path: Path) -> Any:
    if yaml is None:
        raise PipelineError(
            f"PyYAML が必要です: path={path}, install_command='pip install pyyaml'"
        )
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise PipelineError(f"YAML ファイルを読めません: path={path}, error={exc}") from exc
    try:
        return yaml.load(text, Loader=UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise PipelineError(f"YAML を解析できません: path={path}, error={exc}") from exc


def _exact_mapping(value: Any, expected: set[str], *, label: str, path: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PipelineError(
            f"設定 {label} は object が必要です: path={path}, type={type(value).__name__}"
        )
    actual = set(value)
    if actual != expected:
        raise PipelineError(
            f"設定 {label} のキーが不正です: path={path}, "
            f"missing={sorted(expected - actual)}, unknown={sorted(actual - expected)}"
        )
    return value


def _positive_number(value: Any, *, key: str, integer: bool = False) -> int | float:
    expected = int if integer else (int, float)
    if not isinstance(value, expected) or isinstance(value, bool) or value <= 0:
        kind = "正の整数" if integer else "正の数値"
        raise PipelineError(f"設定 {key} は{kind}が必要です: value={value!r}")
    return value


def load_config(path: Path) -> dict[str, Any]:
    value = load_strict_yaml(path)
    root = _exact_mapping(
        value,
        {"paths", "intake", "plan", "acquire"},
        label="トップレベル",
        path=path,
    )
    paths = _exact_mapping(
        root["paths"],
        {"run_root", "posts_dir", "drafts_dir"},
        label="paths",
        path=path,
    )
    intake = _exact_mapping(
        root["intake"],
        {"overlap_threshold", "overlap_top_n"},
        label="intake",
        path=path,
    )
    plan = _exact_mapping(root["plan"], {"mode"}, label="plan", path=path)
    acquire_keys = {
        "allowed_hosts",
        "comparison_denied_hosts",
        "self_hosts",
        "self_repos",
        "challenge_markers",
        "user_agent",
        "dns_timeout_s",
        "connect_timeout_s",
        "read_timeout_s",
        "request_deadline_s",
        "source_deadline_s",
        "run_deadline_s",
        "max_abandoned_resolvers",
        "max_redirects",
        "max_body_bytes",
        "max_total_bytes",
        "max_sources",
        "per_host_interval_s",
        "max_retries",
        "retry_backoff_s",
        "retry_after_max_s",
        "min_text_chars",
        "issue_comment_pages_max",
        "reuse_max_age_hours",
    }
    acquire = _exact_mapping(root["acquire"], acquire_keys, label="acquire", path=path)

    if paths["run_root"] != "run/article_pipeline":
        raise PipelineError(
            f"設定 paths.run_root は固定です: actual={paths['run_root']!r}, expected='run/article_pipeline'"
        )
    if not all(isinstance(paths[key], str) and paths[key] for key in paths):
        raise PipelineError(f"設定 paths の値は空でない文字列が必要です: value={paths!r}")
    threshold = intake["overlap_threshold"]
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or not 0 <= threshold <= 1:
        raise PipelineError(f"overlap_threshold は 0 以上 1 以下の数値が必要です: value={threshold!r}")
    _positive_number(intake["overlap_top_n"], key="intake.overlap_top_n", integer=True)
    if plan["mode"] != "manual":
        raise PipelineError(f"P2 の plan.mode は manual 固定です: value={plan['mode']!r}")

    allowed = acquire["allowed_hosts"]
    if not isinstance(allowed, list) or not allowed:
        raise PipelineError("設定 acquire.allowed_hosts は1件以上の配列が必要です")
    seen_hosts: set[str] = set()
    for index, item in enumerate(allowed):
        mapping = _exact_mapping(
            item, {"host", "include_subdomains"}, label=f"acquire.allowed_hosts[{index}]", path=path
        )
        host = mapping["host"]
        if not isinstance(host, str) or not host or host != host.lower():
            raise PipelineError(f"allowed_hosts の host は小文字の空でない文字列が必要です: index={index}, value={host!r}")
        if not isinstance(mapping["include_subdomains"], bool):
            raise PipelineError(f"allowed_hosts.include_subdomains は bool が必要です: index={index}")
        if host in seen_hosts:
            raise PipelineError(f"allowed_hosts の host が重複しています: host={host}")
        seen_hosts.add(host)

    for key in ("comparison_denied_hosts", "self_hosts", "self_repos", "challenge_markers"):
        items = acquire[key]
        if not isinstance(items, list) or not all(isinstance(item, str) and item for item in items):
            raise PipelineError(f"設定 acquire.{key} は空でない文字列の配列が必要です: value={items!r}")
        if len(set(items)) != len(items):
            raise PipelineError(f"設定 acquire.{key} に重複があります: value={items!r}")
    if not isinstance(acquire["user_agent"], str) or not acquire["user_agent"]:
        raise PipelineError("設定 acquire.user_agent は空でない文字列が必要です")

    number_keys = {
        "dns_timeout_s",
        "connect_timeout_s",
        "read_timeout_s",
        "request_deadline_s",
        "source_deadline_s",
        "run_deadline_s",
        "per_host_interval_s",
        "retry_after_max_s",
        "reuse_max_age_hours",
    }
    integer_keys = {
        "max_abandoned_resolvers",
        "max_redirects",
        "max_body_bytes",
        "max_total_bytes",
        "max_sources",
        "max_retries",
        "min_text_chars",
        "issue_comment_pages_max",
    }
    for key in number_keys:
        _positive_number(acquire[key], key=f"acquire.{key}")
    for key in integer_keys:
        if key in {"max_redirects", "max_retries"} and acquire[key] == 0:
            continue
        _positive_number(acquire[key], key=f"acquire.{key}", integer=True)
    backoff = acquire["retry_backoff_s"]
    if not isinstance(backoff, list) or len(backoff) != acquire["max_retries"]:
        raise PipelineError(
            "設定 acquire.retry_backoff_s の件数は max_retries と一致する必要があります: "
            f"backoff={backoff!r}, max_retries={acquire['max_retries']!r}"
        )
    for index, seconds in enumerate(backoff):
        _positive_number(seconds, key=f"acquire.retry_backoff_s[{index}]")
    if acquire["max_total_bytes"] < acquire["max_body_bytes"]:
        raise PipelineError("max_total_bytes は max_body_bytes 以上でなければなりません")

    request = acquire["request_deadline_s"]
    source = acquire["source_deadline_s"]
    run = acquire["run_deadline_s"]
    for key in ("dns_timeout_s", "connect_timeout_s", "read_timeout_s"):
        if acquire[key] > request:
            raise PipelineError(
                f"時間上限の関係が不正です: acquire.{key}={acquire[key]} > request_deadline_s={request}"
            )
    if request > source or source > run:
        raise PipelineError(
            "時間上限の関係が不正です: "
            f"request_deadline_s={request}, source_deadline_s={source}, run_deadline_s={run}"
        )
    return root
