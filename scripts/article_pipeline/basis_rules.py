"""Mechanical evidence prechecks and support-rule enforcement."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from . import PipelineError
from .quote_match import normalize_text


SOURCE_TYPES = {"official_impl", "official_doc", "vendor_community", "case", "third_party"}
LINK_RULES = {"CA-IMPL", "DV-IMPL", "VB-DIFF", "BD-PAIR"}


def classify_source(source: dict[str, Any], config: dict[str, Any]) -> str:
    kind = source.get("kind")
    github = source.get("github") if isinstance(source.get("github"), dict) else {}
    repo = github.get("repo") or source.get("repo")
    if kind == "github_file" and repo in config["official_repos"]:
        return "official_impl"
    if kind == "github_issue" and repo in config["official_repos"]:
        return "case"
    if kind == "url":
        requests = source.get("requests") or []
        url = requests[-1].get("final_url", "") if requests else source.get("url", "")
        host = (urlsplit(url).hostname or "").lower()
        if host in config["official_doc_hosts"]:
            return "official_doc"
        if host in config["vendor_community_hosts"]:
            return "vendor_community"
    return "third_party"


def assign_source_types(sources: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, str]:
    return {str(source["source_id"]): classify_source(source, config) for source in sources}


def _matched(evidence: dict[str, Any]) -> bool:
    return evidence.get("quote_match", {}).get("result") == "matched"


def _contains(evidence: dict[str, Any], value: Any) -> bool:
    return isinstance(value, str) and bool(value) and normalize_text(value) in normalize_text(str(evidence.get("quote", "")))


def _type(evidence: dict[str, Any], source_types: dict[str, str], expected: str | set[str]) -> bool:
    values = {expected} if isinstance(expected, str) else expected
    return _matched(evidence) and source_types.get(str(evidence.get("source_id"))) in values


def ca_impl_function_scope_unchecked(
    claim: dict[str, Any],
    sources_by_id: dict[str, dict[str, Any]],
    source_types: dict[str, str],
    *,
    max_link_span_lines: int,
) -> bool:
    if claim.get("kind") != "cause":
        return False
    evidence = claim.get("evidence") if isinstance(claim.get("evidence"), list) else []
    subject = claim.get("subject") if isinstance(claim.get("subject"), dict) else {}
    literal = subject.get("message_literal")
    impl = [item for item in evidence if _type(item, source_types, "official_impl")]
    emissions = [item for item in impl if _contains(item, literal)]
    conditions = [item for item in impl if not _contains(item, literal)]
    for emission in emissions:
        for condition in conditions:
            emission_source = str(emission.get("source_id"))
            condition_source = str(condition.get("source_id"))
            if emission_source != condition_source:
                continue
            emission_github = sources_by_id.get(emission_source, {}).get("github", {})
            condition_github = sources_by_id.get(condition_source, {}).get("github", {})
            if emission_github.get("commit_sha") != condition_github.get("commit_sha"):
                continue
            emission_line = emission["quote_match"]["locations"][0]["line_start"]
            condition_line = condition["quote_match"]["locations"][0]["line_start"]
            if abs(emission_line - condition_line) <= max_link_span_lines:
                return True
    return False


def vb_diff_version_pair_unchecked(
    claim: dict[str, Any],
    sources_by_id: dict[str, dict[str, Any]],
    source_types: dict[str, str],
) -> bool:
    if claim.get("kind") != "version_behavior":
        return False
    evidence = claim.get("evidence") if isinstance(claim.get("evidence"), list) else []
    impl = [item for item in evidence if _type(item, source_types, "official_impl")]
    for before in impl:
        for after in impl:
            if before is after:
                continue
            before_github = sources_by_id.get(str(before.get("source_id")), {}).get("github", {})
            after_github = sources_by_id.get(str(after.get("source_id")), {}).get("github", {})
            if (
                before_github.get("repo") == after_github.get("repo")
                and before_github.get("path") == after_github.get("path")
                and before_github.get("commit_sha") != after_github.get("commit_sha")
                and before_github.get("ref_kind") == after_github.get("ref_kind") == "tag"
            ):
                return True
    return False


def precheck_claim(
    claim: dict[str, Any],
    sources_by_id: dict[str, dict[str, Any]],
    source_types: dict[str, str],
    *,
    max_link_span_lines: int,
) -> list[str]:
    kind = claim.get("kind")
    evidence = claim.get("evidence") if isinstance(claim.get("evidence"), list) else []
    subject = claim.get("subject") if isinstance(claim.get("subject"), dict) else {}
    passed: list[str] = []
    docs = [e for e in evidence if _type(e, source_types, "official_doc")]
    impl = [e for e in evidence if _type(e, source_types, "official_impl")]
    cases = [e for e in evidence if _type(e, source_types, {"case", "vendor_community"})]
    literal, identifier, value, version = (
        subject.get("message_literal"), subject.get("identifier"), subject.get("value"), subject.get("version")
    )
    if kind == "message_text":
        if any(_contains(e, literal) for e in impl): passed.append("MT-IMPL")
        if any(_contains(e, literal) for e in docs): passed.append("MT-DOC")
    elif kind == "cause":
        if docs: passed.append("CA-DOC")
        # The current source artifacts do not contain function boundaries.
        # Same-file, same-commit, nearby lines are insufficient to prove that
        # the condition and emission are in the same function.
    elif kind == "default_value":
        if any(_contains(e, value) and (not identifier or _contains(e, identifier)) for e in docs): passed.append("DV-DOC")
        definitions = [e for e in impl if _contains(e, identifier) and _contains(e, value)]
        uses = [e for e in impl if _contains(e, identifier) and e not in definitions]
        if any(d["source_id"] == u["source_id"] for d in definitions for u in uses): passed.append("DV-IMPL")
    elif kind == "version_behavior":
        if any(_contains(e, version) for e in docs): passed.append("VB-NOTES")
        # Tag names and distinct commits do not establish version ordering or
        # bind either quotation to the claim's target version.
    elif kind == "remedy":
        if docs: passed.append("RM-DOC")
    elif kind == "occurrence":
        if cases: passed.append("OC-REPORT")
    elif kind == "boundary":
        left, right = subject.get("message_literal"), subject.get("other_error")
        if any(_contains(e, left) for e in docs + impl) and any(_contains(e, right) for e in docs + impl):
            passed.append("BD-PAIR")
    return sorted(set(passed))


REQUIRED_FUNCTIONS = {
    "MT-IMPL": {"emits_message"}, "MT-DOC": {"documents_message"},
    "CA-DOC": {"states_cause"}, "CA-IMPL": {"emits_message", "condition_leads_to_emission"},
    "DV-DOC": {"states_default"}, "DV-IMPL": {"defines_value", "uses_value"},
    "VB-NOTES": {"states_version_change"}, "VB-DIFF": {"shows_behavior_before", "shows_behavior_after"},
    "RM-DOC": {"recommends_remedy"}, "OC-REPORT": {"reports_occurrence"}, "BD-PAIR": {"distinguishes"},
}


def validate_link_value(basis_code: str, value: Any) -> None:
    if basis_code in LINK_RULES and value not in {True, False}:
        raise PipelineError(f"つながりを要求する規則の link_confirmed は bool が必要です: basis_code={basis_code}")
    if basis_code not in LINK_RULES and value is not None:
        raise PipelineError(f"つながりを要求しない規則の link_confirmed は null が必要です: basis_code={basis_code}")


def decide_support(claim: dict[str, Any], judgement: dict[str, Any]) -> tuple[str, str | None, str | None]:
    basis = judgement.get("basis_code")
    if basis == "CA-IMPL":
        return "unverified", "function_scope_unchecked", None
    if basis == "VB-DIFF":
        return "unverified", "version_pair_unchecked", None
    prechecked = claim.get("precheck_passed", [])
    if basis not in prechecked:
        return "unverified", "basis_mismatch", None
    validate_link_value(str(basis), judgement.get("link_confirmed"))
    assessments = judgement.get("evidence_assessment", [])
    by_index = {
        item.get("evidence_index"): item.get("function")
        for item in assessments if isinstance(item, dict)
    }
    functions = set(by_index.values())
    if "contradicts" in functions or judgement.get("contradicted") is True:
        return "contradicted", None, None
    evidence = claim.get("evidence", [])
    subject = claim.get("subject") if isinstance(claim.get("subject"), dict) else {}
    literal, identifier, value = subject.get("message_literal"), subject.get("identifier"), subject.get("value")
    typed = lambda index, expected: evidence[index].get("source_type") == expected
    contains = lambda index, expected: _contains(evidence[index], expected)
    indexed = range(len(evidence))
    if basis == "BD-PAIR":
        other = subject.get("other_error")
        side_function_types = {
            "emits_message": "official_impl",
            "documents_message": "official_doc",
            "states_cause": "official_doc",
        }
        def evidence_identity(index: int) -> tuple[Any, ...]:
            item = evidence[index]
            locations = item.get("quote_match", {}).get("locations", [])
            ranges = tuple(
                (location.get("line_start"), location.get("line_end"))
                for location in locations if isinstance(location, dict)
            )
            return (
                item.get("source_id"),
                ranges,
                normalize_text(str(item.get("quote", ""))),
            )
        left_indexes = {
            index for index in indexed
            if contains(index, literal)
            and typed(index, side_function_types.get(by_index.get(index), ""))
        }
        right_indexes = {
            index for index in indexed
            if contains(index, other)
            and typed(index, side_function_types.get(by_index.get(index), ""))
        }
        side_pairs = {
            (left, right)
            for left in left_indexes
            for right in right_indexes
            if evidence_identity(left) != evidence_identity(right)
        }
        if not side_pairs:
            return "unverified", "boundary_sides_unchecked", None
        distinction_indexes = {
            index for index in indexed
            if by_index.get(index) == "distinguishes"
            and contains(index, literal)
            and contains(index, other)
        }
        if not any(
            evidence_identity(distinction) not in {
                evidence_identity(left), evidence_identity(right)
            }
            for left, right in side_pairs
            for distinction in distinction_indexes
        ):
            return "unverified", "boundary_distinction_unchecked", None
    if not REQUIRED_FUNCTIONS.get(str(basis), set()).issubset(functions):
        return "unverified", "basis_not_established", None
    established = True
    if basis == "MT-IMPL":
        established = any(typed(i, "official_impl") and contains(i, literal) and by_index.get(i) == "emits_message" for i in indexed)
    elif basis == "MT-DOC":
        established = any(typed(i, "official_doc") and contains(i, literal) and by_index.get(i) == "documents_message" for i in indexed)
    elif basis == "CA-DOC":
        established = any(typed(i, "official_doc") and by_index.get(i) == "states_cause" for i in indexed)
    elif basis == "DV-DOC":
        established = any(typed(i, "official_doc") and contains(i, value) and (not identifier or contains(i, identifier)) and by_index.get(i) == "states_default" for i in indexed)
    elif basis == "DV-IMPL":
        definitions = [i for i in indexed if typed(i, "official_impl") and contains(i, identifier) and contains(i, value) and by_index.get(i) == "defines_value"]
        uses = [i for i in indexed if typed(i, "official_impl") and contains(i, identifier) and by_index.get(i) == "uses_value"]
        established = any(evidence[d]["source_id"] == evidence[u]["source_id"] and d != u for d in definitions for u in uses)
    elif basis == "VB-NOTES":
        established = any(typed(i, "official_doc") and by_index.get(i) == "states_version_change" for i in indexed)
    elif basis == "RM-DOC":
        established = any(typed(i, "official_doc") and by_index.get(i) == "recommends_remedy" for i in indexed)
    elif basis == "OC-REPORT":
        established = any(evidence[i].get("source_type") in {"case", "vendor_community"} and by_index.get(i) == "reports_occurrence" for i in indexed)
    elif basis == "BD-PAIR":
        established = True
    if not established:
        return "unverified", "basis_not_established", None
    if basis in LINK_RULES and judgement.get("link_confirmed") is not True:
        return "unverified", "basis_not_established", None
    if judgement.get("support") != "supported":
        return "unverified", "partial_or_unsupported", None
    if any(e.get("quote_match", {}).get("result") != "matched" for e in claim.get("evidence", [])):
        return "unverified", "quote_unmatched", None
    constraint = None
    if str(basis).endswith("-IMPL") or basis == "VB-DIFF":
        constraint = "implementation_reading"
    if basis == "OC-REPORT":
        constraint = "occurrence_report"
    return "verified", None, constraint
