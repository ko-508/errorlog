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
        {"paths", "intake", "plan", "acquire", "llm", "budget", "claims"},
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
    llm = _exact_mapping(
        root["llm"],
        {"store", "budget_lock_wait_s", "max_retries", "retry_backoff_s", "retry_after_max_s",
         "count_timeout_s", "create_timeout_s", "retrieve_timeout_s", "poll_interval_s",
         "call_deadline_s", "pricing"},
        label="llm", path=path,
    )
    budget = _exact_mapping(
        root["budget"], {"monthly_limit_usd", "run_limit_usd", "call_limit_usd"},
        label="budget", path=path,
    )
    claims = _exact_mapping(
        root["claims"], {"extract", "support", "source_types", "injection_markers"},
        label="claims", path=path,
    )

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

    if llm["store"] is not None and not isinstance(llm["store"], bool):
        raise PipelineError(f"設定 llm.store は bool または null が必要です: value={llm['store']!r}")
    for key in ("budget_lock_wait_s", "retry_after_max_s", "count_timeout_s", "create_timeout_s",
                "retrieve_timeout_s", "poll_interval_s", "call_deadline_s"):
        _positive_number(llm[key], key=f"llm.{key}")
    if not isinstance(llm["max_retries"], int) or isinstance(llm["max_retries"], bool) or llm["max_retries"] < 0:
        raise PipelineError(f"設定 llm.max_retries は0以上の整数が必要です: value={llm['max_retries']!r}")
    if (not isinstance(llm["retry_backoff_s"], list)
            or len(llm["retry_backoff_s"]) != llm["max_retries"]):
        raise PipelineError("設定 llm.retry_backoff_s の件数は llm.max_retries と一致する必要があります")
    for index, seconds in enumerate(llm["retry_backoff_s"]):
        _positive_number(seconds, key=f"llm.retry_backoff_s[{index}]")
    pricing = _exact_mapping(llm["pricing"], {"max_age_days", "models"}, label="llm.pricing", path=path)
    if pricing["max_age_days"] is not None:
        _positive_number(pricing["max_age_days"], key="llm.pricing.max_age_days", integer=True)
    if not isinstance(pricing["models"], dict) or not pricing["models"]:
        raise PipelineError("設定 llm.pricing.models は1件以上の object が必要です")
    price_keys = {"input", "cached_input", "cache_write", "output"}
    for model, raw_model in pricing["models"].items():
        if not isinstance(model, str) or not model:
            raise PipelineError(f"設定 llm.pricing.models のモデル名が不正です: value={model!r}")
        model_cfg = _exact_mapping(
            raw_model, {"source", "checked_at", "short_context_max_input_tokens", "short", "long"},
            label=f"llm.pricing.models.{model}", path=path,
        )
        if not isinstance(model_cfg["source"], str) or not model_cfg["source"].startswith("https://"):
            raise PipelineError(f"単価の source は https URL が必要です: model={model}")
        if not isinstance(model_cfg["checked_at"], str) or not model_cfg["checked_at"]:
            raise PipelineError(f"単価の checked_at は空でない文字列が必要です: model={model}")
        _positive_number(model_cfg["short_context_max_input_tokens"], key=f"pricing.{model}.short_context_max_input_tokens", integer=True)
        for band in ("short", "long"):
            rates = _exact_mapping(model_cfg[band], price_keys, label=f"pricing.{model}.{band}", path=path)
            for rate, number in rates.items():
                _positive_number(number, key=f"pricing.{model}.{band}.{rate}")

    for key, value in budget.items():
        if value is not None:
            _positive_number(value, key=f"budget.{key}")

    extract = _exact_mapping(
        claims["extract"],
        {"model", "reasoning_effort", "max_output_tokens", "expected_output_tokens",
         "max_input_tokens_per_call", "max_claims_per_call", "max_evidence_per_claim", "max_quote_chars"},
        label="claims.extract", path=path,
    )
    support = _exact_mapping(
        claims["support"],
        {"model", "reasoning_effort", "max_output_tokens", "expected_output_tokens",
         "claims_per_call", "context_lines", "max_link_span_lines"},
        label="claims.support", path=path,
    )
    for label, section, nullable in (
        ("claims.extract", extract, {"model", "reasoning_effort", "max_output_tokens", "expected_output_tokens", "max_input_tokens_per_call"}),
        ("claims.support", support, {"model", "reasoning_effort", "max_output_tokens", "expected_output_tokens"}),
    ):
        for key, item in section.items():
            if key in {"model", "reasoning_effort"}:
                if item is not None and (not isinstance(item, str) or not item):
                    raise PipelineError(f"設定 {label}.{key} は空でない文字列または null が必要です")
            elif item is None:
                if key not in nullable:
                    raise PipelineError(f"設定 {label}.{key} は null にできません")
            else:
                _positive_number(item, key=f"{label}.{key}", integer=True)
    source_types = _exact_mapping(
        claims["source_types"], {"official_repos", "official_doc_hosts", "vendor_community_hosts"},
        label="claims.source_types", path=path,
    )
    for key, items in source_types.items():
        if not isinstance(items, list) or not all(isinstance(item, str) and item for item in items) or len(set(items)) != len(items):
            raise PipelineError(f"設定 claims.source_types.{key} は重複のない文字列配列が必要です")
    markers = claims["injection_markers"]
    if not isinstance(markers, list) or not markers or not all(isinstance(item, str) and item for item in markers):
        raise PipelineError("設定 claims.injection_markers は空でない文字列の配列が必要です")
    return root
