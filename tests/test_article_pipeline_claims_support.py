import json
from pathlib import Path
import shutil

import pytest

from scripts.article_pipeline import PipelineError
from scripts.article_pipeline.basis_rules import (
    ca_impl_function_scope_unchecked,
    decide_support,
    precheck_claim,
    vb_diff_version_pair_unchecked,
)
from scripts.article_pipeline.claims_support import _validate_judgements
from scripts.article_pipeline.claims_support import run_claims_support
from scripts.article_pipeline.claims_extract import run_claims_extract
from scripts.article_pipeline.store import sha256_bytes
from tests.test_article_pipeline_claims_extract import context, extracted_output


def evidence(source_id, source_type, quote, line=1):
    return {"source_id": source_id, "source_type": source_type, "quote": quote,
            "quote_match": {"result": "matched", "locations": [{"line_start": line, "line_end": line}]}}


def test_matched_error_text_alone_does_not_establish_cause():
    claim = {"kind": "cause", "subject": {"message_literal": "E100"},
             "evidence": [evidence("S001", "official_impl", "emit E100", 10)]}
    sources = {"S001": {"github": {"commit_sha": "a"}}}
    assert precheck_claim(claim, sources, {"S001": "official_impl"}, max_link_span_lines=80) == []


@pytest.mark.parametrize(
    ("basis", "functions", "link", "expected"),
    [
        ("MT-IMPL", ["unrelated"], None, "unverified"),
        ("MT-IMPL", ["emits_message"], None, "verified"),
        ("CA-IMPL", ["emits_message", "condition_leads_to_emission"], False, "unverified"),
        ("CA-IMPL", ["emits_message", "condition_leads_to_emission"], True, "unverified"),
    ],
)
def test_final_status_requires_every_semantic_condition(basis, functions, link, expected):
    claim = {"precheck_passed": [basis], "subject": {"message_literal": "E100"},
             "evidence": [evidence("S001", "official_impl", "E100"), evidence("S001", "official_impl", "condition", 2)]}
    judgement = {"basis_code": basis, "link_confirmed": link, "support": "supported", "contradicted": False,
                 "evidence_assessment": [{"evidence_index": i, "function": value, "reason": "ok"} for i, value in enumerate(functions)]}
    result = decide_support(claim, judgement)
    assert result[0] == expected
    if basis == "CA-IMPL":
        assert result[1] == "function_scope_unchecked"


def test_ca_impl_nearby_lines_without_function_scope_do_not_pass_precheck():
    claim = {
        "kind": "cause",
        "subject": {"message_literal": "E100"},
        "evidence": [
            evidence("S001", "official_impl", "emit E100", 10),
            evidence("S001", "official_impl", "if socket_closed", 12),
        ],
    }
    sources = {"S001": {"github": {"commit_sha": "abc"}}}
    source_types = {"S001": "official_impl"}
    assert precheck_claim(claim, sources, source_types, max_link_span_lines=80) == []
    assert ca_impl_function_scope_unchecked(
        claim, sources, source_types, max_link_span_lines=80
    ) is True


def test_ca_doc_remains_available_when_ca_impl_function_scope_is_unchecked():
    claim = {
        "kind": "cause",
        "subject": {"message_literal": "E100"},
        "evidence": [
            evidence("S001", "official_impl", "emit E100", 10),
            evidence("S001", "official_impl", "if socket_closed", 12),
            evidence("S002", "official_doc", "The socket closing causes E100", 1),
        ],
    }
    sources = {
        "S001": {"github": {"commit_sha": "abc"}},
        "S002": {},
    }
    source_types = {"S001": "official_impl", "S002": "official_doc"}
    assert precheck_claim(claim, sources, source_types, max_link_span_lines=80) == ["CA-DOC"]


def test_support_saves_ca_impl_only_claim_as_function_scope_unchecked(tmp_path):
    output = extracted_output()
    output["claims"][0]["evidence"] = [
        {"source_id": "S001", "role": "emission", "quote": "E100 happens when the socket closes"},
        {"source_id": "S001", "role": "condition", "quote": "first line"},
    ]
    ctx, transport, _text = context(tmp_path, output)
    root = Path(__file__).parents[1]
    support_prompt = tmp_path / "config/prompts/s3_support.v1.md"
    support_prompt.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / "config/prompts/s3_support.v1.md", support_prompt)
    index_path = ctx.store.path(ctx.artifact_relative("sources/index.json"))
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["sources"][0].update({
        "kind": "github_file",
        "github": {
            "repo": "example/project",
            "commit_sha": "abc",
            "path": "src/error.py",
            "ref_kind": "commit",
        },
    })
    index_path.write_text(json.dumps(index), encoding="utf-8")
    ctx.config["claims"]["source_types"]["official_repos"] = ["example/project"]
    run_claims_extract(ctx, {"slug": "sample_error"})
    assert len(transport.requests) == 1

    run_claims_support(ctx, {"slug": "sample_error"})

    assert len(transport.requests) == 1
    claims = ctx.store.read_json(ctx.artifact_relative("claims.json"))
    claim = claims["claims"][0]
    assert claim["precheck_passed"] == []
    assert claim["status"] == "unverified"
    assert claim["unverified_reason"] == "function_scope_unchecked"
    assert claim["judgement"] is None


def test_basis_mismatch_and_contradiction_never_verify():
    claim = {"precheck_passed": ["MT-DOC"], "evidence": [evidence("S001", "official_doc", "E100")]}
    mismatch = {"basis_code": "MT-IMPL", "link_confirmed": None, "support": "supported", "contradicted": False, "evidence_assessment": []}
    assert decide_support(claim, mismatch)[:2] == ("unverified", "basis_mismatch")
    contradicted = {"basis_code": "MT-DOC", "link_confirmed": None, "support": "supported", "contradicted": False,
                    "evidence_assessment": [{"evidence_index": 0, "function": "contradicts", "reason": "no"}]}
    assert decide_support(claim, contradicted)[0] == "contradicted"
    boundary = {
        "precheck_passed": ["BD-PAIR"],
        "subject": {"message_literal": "E100", "other_error": "E200"},
        "evidence": [
            evidence("S001", "official_doc", "E100"),
            evidence("S002", "official_doc", "E200"),
            evidence("S003", "official_doc", "E100 differs from E200"),
        ],
    }
    boundary_judgement = {
        "basis_code": "BD-PAIR", "link_confirmed": True, "support": "supported",
        "contradicted": False,
        "evidence_assessment": [
            {"evidence_index": 0, "function": "documents_message", "reason": "left"},
            {"evidence_index": 1, "function": "documents_message", "reason": "right"},
            {"evidence_index": 2, "function": "distinguishes", "reason": "difference"},
        ],
    }
    assert decide_support(boundary, boundary_judgement)[0] == "verified"
    boundary_judgement["evidence_assessment"] = boundary_judgement["evidence_assessment"][1:]
    assert decide_support(boundary, boundary_judgement)[0] == "unverified"


def test_judgement_rejects_missing_duplicate_unknown_and_bad_index():
    batch = [{"claim_id": "C001", "evidence": [{}]}, {"claim_id": "C002", "evidence": [{}]}]
    base = {"basis_code": "NONE", "evidence_assessment": [], "link_confirmed": None,
            "support": "unsupported", "contradicted": False, "reason": "no", "missing": []}
    with pytest.raises(PipelineError, match="判定がない"):
        _validate_judgements({"judgements": [{"claim_id": "C001", **base}]}, batch)
    with pytest.raises(PipelineError, match="重複"):
        _validate_judgements({"judgements": [{"claim_id": "C001", **base}, {"claim_id": "C001", **base}]}, batch[:1])
    with pytest.raises(PipelineError, match="入力にない"):
        _validate_judgements({"judgements": [{"claim_id": "C999", **base}]}, batch[:1])
    bad = {**base, "evidence_assessment": [{"evidence_index": 2, "function": "unrelated", "reason": "x"}]}
    with pytest.raises(PipelineError, match="存在しない"):
        _validate_judgements({"judgements": [{"claim_id": "C001", **bad}]}, batch[:1])


def test_role_is_not_used_by_precheck():
    claim = {"kind": "message_text", "subject": {"message_literal": "E100"},
             "evidence": [{**evidence("S001", "official_doc", "documents E100"), "role": "condition"}]}
    first = precheck_claim(claim, {"S001": {}}, {"S001": "official_doc"}, max_link_span_lines=80)
    claim["evidence"][0]["role"] = "emission"
    assert precheck_claim(claim, {"S001": {}}, {"S001": "official_doc"}, max_link_span_lines=80) == first == ["MT-DOC"]


def test_evidence_role_does_not_change_full_support_result(tmp_path):
    results = []
    requests = []
    for role in ("condition", "emission"):
        root_path = tmp_path / role
        output = extracted_output()
        output["claims"][0]["evidence"][0]["role"] = role
        ctx, transport, _text = context(root_path, output)
        repository = Path(__file__).parents[1]
        for relative in (
            "config/prompts/s3_support.v1.md",
            "config/schemas/claims_support.v2.json",
        ):
            target = root_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(repository / relative, target)
        ctx.config["claims"]["source_types"]["official_doc_hosts"] = [
            "docs.example.com"
        ]
        ctx.config["claims"]["support"].update(
            model="test-model",
            reasoning_effort="low",
            max_output_tokens=1000,
            expected_output_tokens=200,
        )
        run_claims_extract(ctx, {"slug": "sample_error"})
        transport.outputs.append({"judgements": [{
            "claim_id": "C001",
            "basis_code": "CA-DOC",
            "evidence_assessment": [{
                "evidence_index": 0,
                "function": "states_cause",
                "reason": "原因を述べる",
            }],
            "link_confirmed": None,
            "support": "supported",
            "contradicted": False,
            "reason": "直接述べる",
            "missing": [],
        }]})
        run_claims_support(ctx, {"slug": "sample_error"})
        claim = ctx.store.read_json(
            ctx.artifact_relative("claims.json")
        )["claims"][0]
        results.append({
            key: claim[key]
            for key in (
                "precheck_passed", "status", "basis", "support",
                "unverified_reason", "writing_constraint",
            )
        })
        requests.append(transport.requests[-1]["input"][0]["content"][0]["text"])
    assert results[0] == results[1]
    assert requests[0] == requests[1]
    assert '"role"' not in requests[0]


@pytest.mark.parametrize(
    ("basis", "link", "pattern"),
    [
        ("MT-DOC", True, "null が必要"),
        ("CA-IMPL", None, "bool が必要"),
    ],
)
def test_judgement_rejects_invalid_link_confirmed_shape(basis, link, pattern):
    batch = [{"claim_id": "C001", "evidence": [{}]}]
    judgement = {
        "claim_id": "C001",
        "basis_code": basis,
        "evidence_assessment": [],
        "link_confirmed": link,
        "support": "unsupported",
        "contradicted": False,
        "reason": "shape check",
        "missing": [],
    }
    with pytest.raises(PipelineError, match=pattern):
        _validate_judgements({"judgements": [judgement]}, batch)


@pytest.mark.parametrize(
    ("basis", "claim", "functions", "link"),
    [
        (
            "MT-DOC",
            {
                "subject": {"message_literal": "E100"},
                "evidence": [evidence("S001", "official_doc", "documents E100")],
            },
            ["documents_message"],
            None,
        ),
        (
            "CA-DOC",
            {
                "subject": {"message_literal": "E100"},
                "evidence": [evidence("S001", "official_doc", "E100 cause")],
            },
            ["states_cause"],
            None,
        ),
        (
            "DV-DOC",
            {
                "subject": {"identifier": "limit", "value": "10"},
                "evidence": [evidence("S001", "official_doc", "limit defaults to 10")],
            },
            ["states_default"],
            None,
        ),
        (
            "DV-IMPL",
            {
                "subject": {"identifier": "limit", "value": "10"},
                "evidence": [
                    evidence("S001", "official_impl", "limit = 10"),
                    evidence("S001", "official_impl", "use limit", 2),
                ],
            },
            ["defines_value", "uses_value"],
            True,
        ),
        (
            "VB-NOTES",
            {
                "subject": {"version": "2.0"},
                "evidence": [evidence("S001", "official_doc", "Changed in 2.0")],
            },
            ["states_version_change"],
            None,
        ),
        (
            "RM-DOC",
            {
                "subject": {},
                "evidence": [evidence("S001", "official_doc", "Run repair")],
            },
            ["recommends_remedy"],
            None,
        ),
        (
            "OC-REPORT",
            {
                "subject": {},
                "evidence": [evidence("S001", "case", "I encountered E100")],
            },
            ["reports_occurrence"],
            None,
        ),
    ],
)
def test_decide_support_for_remaining_semantic_rules(
    basis, claim, functions, link
):
    claim = {**claim, "precheck_passed": [basis]}
    judgement = {
        "basis_code": basis,
        "evidence_assessment": [
            {"evidence_index": index, "function": function, "reason": "ok"}
            for index, function in enumerate(functions)
        ],
        "link_confirmed": link,
        "support": "supported",
        "contradicted": False,
    }
    assert decide_support(claim, judgement)[0] == "verified"
    judgement["evidence_assessment"][0]["function"] = "unrelated"
    assert decide_support(claim, judgement)[0] == "unverified"


def test_support_request_omits_extraction_metadata_and_writes_insufficient_gate(tmp_path):
    ctx, transport, _text = context(tmp_path, extracted_output())
    root = Path(__file__).parents[1]
    for relative in ("config/prompts/s3_support.v1.md", "config/schemas/claims_support.v2.json"):
        target = tmp_path / relative; target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(root / relative, target)
    ctx.config["claims"]["source_types"]["official_doc_hosts"] = ["docs.example.com"]
    ctx.config["claims"]["support"].update(model="test-model", reasoning_effort="low", max_output_tokens=1000, expected_output_tokens=200)
    run_claims_extract(ctx, {"slug": "sample_error"})
    transport.outputs.append({"judgements": [{
        "claim_id": "C001", "basis_code": "CA-DOC",
        "evidence_assessment": [{"evidence_index": 0, "function": "states_cause", "reason": "原因を述べる"}],
        "link_confirmed": None, "support": "supported", "contradicted": False,
        "reason": "直接述べる", "missing": [],
    }]})
    run_claims_support(ctx, {"slug": "sample_error"})
    claims = ctx.store.read_json(ctx.artifact_relative("claims.json"))
    assert claims["claims"][0]["status"] == "verified"
    request = transport.requests[-1]["input"][0]["content"][0]["text"]
    assert "temp_id" not in request and "instruction_like_text" not in request and '"role"' not in request
    sufficiency = ctx.store.read_json(ctx.artifact_relative("sufficiency.json"))
    assert sufficiency["sufficient"] is False
    assert sufficiency["counts"]["official_sources"] == 1


def test_closed_issue_occurrence_is_saved_with_past_constraint(tmp_path):
    output = extracted_output()
    output["claims"][0].update(
        kind="occurrence",
        text="E100 was reported",
        subject={
            "message_literal": None,
            "identifier": None,
            "value": None,
            "version": None,
            "other_error": None,
        },
        evidence=[{
            "source_id": "S001",
            "role": "report",
            "quote": "I encountered E100",
        }],
    )
    ctx, transport, _text = context(tmp_path, output)
    repository = Path(__file__).parents[1]
    for relative in (
        "config/prompts/s3_support.v1.md",
        "config/schemas/claims_support.v2.json",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repository / relative, target)
    issue_text = "Issue: I encountered E100\nState: closed\n"
    ctx.write_text("sources/S001/text.txt", issue_text)
    index = ctx.store.read_json(ctx.artifact_relative("sources/index.json"))
    index["sources"][0].update({
        "kind": "github_issue",
        "github": {"repo": "example/project", "issue_number": 1},
        "text": {
            "path": "S001/text.txt",
            "sha256": sha256_bytes(issue_text.encode()),
            "chars": len(issue_text),
            "lines": 2,
        },
    })
    ctx.write_json("sources/index.json", index)
    ctx.config["claims"]["source_types"]["official_repos"] = ["example/project"]
    ctx.config["claims"]["support"].update(
        model="test-model",
        reasoning_effort="low",
        max_output_tokens=1000,
        expected_output_tokens=200,
    )
    run_claims_extract(ctx, {"slug": "sample_error"})
    transport.outputs.append({"judgements": [{
        "claim_id": "C001",
        "basis_code": "OC-REPORT",
        "evidence_assessment": [{
            "evidence_index": 0,
            "function": "reports_occurrence",
            "reason": "issue reports the occurrence",
        }],
        "link_confirmed": None,
        "support": "supported",
        "contradicted": False,
        "reason": "reported occurrence",
        "missing": [],
    }]})

    run_claims_support(ctx, {"slug": "sample_error"})

    claim = ctx.store.read_json(ctx.artifact_relative("claims.json"))["claims"][0]
    assert claim["status"] == "verified"
    assert claim["writing_constraint"] == "occurrence_report_past"


@pytest.mark.parametrize(
    ("constraint", "expected_status", "expected_reason"),
    [
        (">=2.0", "unverified", "version_scope_unchecked"),
        (None, "verified", None),
    ],
)
def test_support_applies_version_scope_constraint_fail_closed(
    tmp_path, constraint, expected_status, expected_reason
):
    output = extracted_output()
    output["claims"][0]["version_scope"] = {
        "product": "Sample",
        "constraint": constraint,
    }
    ctx, transport, _text = context(tmp_path, output)
    root = Path(__file__).parents[1]
    for relative in ("config/prompts/s3_support.v1.md", "config/schemas/claims_support.v2.json"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, target)
    ctx.config["claims"]["source_types"]["official_doc_hosts"] = ["docs.example.com"]
    ctx.config["claims"]["support"].update(
        model="test-model",
        reasoning_effort="low",
        max_output_tokens=1000,
        expected_output_tokens=200,
    )
    run_claims_extract(ctx, {"slug": "sample_error"})
    transport.outputs.append({"judgements": [{
        "claim_id": "C001",
        "basis_code": "CA-DOC",
        "evidence_assessment": [
            {"evidence_index": 0, "function": "states_cause", "reason": "原因を述べる"}
        ],
        "link_confirmed": None,
        "support": "supported",
        "contradicted": False,
        "reason": "直接述べる",
        "missing": [],
    }]})

    run_claims_support(ctx, {"slug": "sample_error"})

    claim = ctx.store.read_json(ctx.artifact_relative("claims.json"))["claims"][0]
    assert claim["version_scope"] == {"product": "Sample", "constraint": constraint}
    assert claim["status"] == expected_status
    assert claim["unverified_reason"] == expected_reason


def _vb_diff_context(tmp_path):
    ctx, transport, _text = context(tmp_path, extracted_output())
    root = Path(__file__).parents[1]
    for relative in ("config/prompts/s3_support.v1.md", "config/schemas/claims_support.v2.json"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, target)
    ctx.config["claims"]["source_types"]["official_repos"] = ["example/project"]
    ctx.config["claims"]["support"].update(
        model="test-model",
        reasoning_effort="low",
        max_output_tokens=1000,
        expected_output_tokens=200,
    )
    source_rows = []
    for source_id, tag, commit, text in (
        ("S001", "v1.0.0", "1111111", "old behavior\n"),
        ("S002", "v2.0.0", "2222222", "new behavior\n"),
    ):
        ctx.write_text(f"sources/{source_id}/text.txt", text)
        source_rows.append({
            "source_id": source_id,
            "kind": "github_file",
            "status": "fetched",
            "github": {
                "repo": "example/project",
                "path": "src/feature.py",
                "commit_sha": commit,
                "ref_kind": "tag",
                "requested_ref": tag,
            },
            "text": {
                "path": f"{source_id}/text.txt",
                "sha256": sha256_bytes(text.encode()),
                "chars": len(text),
                "lines": 1,
            },
        })
    ctx.write_json("sources/index.json", {
        "schema": "sources_index/v1",
        "sources": source_rows,
        "members": [],
    })
    ctx.write_json("claims.extracted.json", {
        "schema": "claims_extracted/v1",
        "sources_index_sha256": ctx.store.hash(ctx.artifact_relative("sources/index.json")),
        "claims": [{
            "claim_id": "C001",
            "kind": "version_behavior",
            "text": "v2.0.0 changes the behavior",
            "subject": {
                "message_literal": None,
                "identifier": None,
                "value": None,
                "version": "v2.0.0",
                "other_error": None,
            },
            "evidence": [
                {
                    "source_id": "S001",
                    "role": "version_note",
                    "quote": "old behavior",
                    "quote_match": {
                        "result": "matched",
                        "locations": [{"line_start": 1, "line_end": 1}],
                    },
                },
                {
                    "source_id": "S002",
                    "role": "version_note",
                    "quote": "new behavior",
                    "quote_match": {
                        "result": "matched",
                        "locations": [{"line_start": 1, "line_end": 1}],
                    },
                },
            ],
            "version_scope": None,
        }],
    })
    return ctx, transport


@pytest.mark.parametrize("case", ["unmapped", "reversed_model_labels"])
def test_support_rejects_vb_diff_without_machine_checked_version_pair(
    tmp_path, monkeypatch, case
):
    ctx, transport = _vb_diff_context(tmp_path)
    if case == "reversed_model_labels":
        monkeypatch.setattr(
            "scripts.article_pipeline.claims_support.precheck_claim",
            lambda *_args, **_kwargs: ["VB-DIFF"],
        )
        transport.outputs = [{"judgements": [{
            "claim_id": "C001",
            "basis_code": "VB-DIFF",
            "evidence_assessment": [
                {"evidence_index": 0, "function": "shows_behavior_after", "reason": "reversed"},
                {"evidence_index": 1, "function": "shows_behavior_before", "reason": "reversed"},
            ],
            "link_confirmed": True,
            "support": "supported",
            "contradicted": False,
            "reason": "model affirms the reversed pair",
            "missing": [],
        }]}]
    else:
        transport.outputs = []

    run_claims_support(ctx, {"slug": "sample_error"})

    claim = ctx.store.read_json(ctx.artifact_relative("claims.json"))["claims"][0]
    assert claim["status"] == "unverified"
    assert claim["unverified_reason"] == "version_pair_unchecked"
    if case == "unmapped":
        assert claim["precheck_passed"] == []
        assert claim["judgement"] is None
        assert len(transport.requests) == 0
        sources = {
            row["source_id"]: row
            for row in ctx.store.read_json(ctx.artifact_relative("sources/index.json"))["sources"]
        }
        source_types = {"S001": "official_impl", "S002": "official_impl"}
        assert vb_diff_version_pair_unchecked(
            claim, sources, source_types
        ) is True
    else:
        assert claim["precheck_passed"] == ["VB-DIFF"]
        assert claim["judgement"]["basis_code"] == "VB-DIFF"
        assert len(transport.requests) == 1


def _boundary_support_context(tmp_path, case):
    ctx, transport, _text = context(tmp_path, extracted_output())
    root = Path(__file__).parents[1]
    for relative in ("config/prompts/s3_support.v1.md", "config/schemas/claims_support.v2.json"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, target)
    ctx.config["claims"]["source_types"]["official_doc_hosts"] = ["docs.example.com"]
    ctx.config["claims"]["support"].update(
        model="test-model",
        reasoning_effort="low",
        max_output_tokens=1000,
        expected_output_tokens=200,
    )
    text = "E100 is one error\nE200 is another error\nE100 differs from E200\n"
    ctx.write_text("sources/S001/text.txt", text)
    ctx.write_json("sources/index.json", {
        "schema": "sources_index/v1",
        "sources": [{
            "source_id": "S001",
            "kind": "url",
            "status": "fetched",
            "requests": [{"final_url": "https://docs.example.com/errors"}],
            "text": {
                "path": "S001/text.txt",
                "sha256": sha256_bytes(text.encode()),
                "chars": len(text),
                "lines": 3,
            },
        }],
        "members": [],
    })
    quotes = {
        "left": ("E100 is one error", 1),
        "right": ("E200 is another error", 2),
        "difference": ("E100 differs from E200", 3),
    }
    case_evidence = {
        "missing_side": ["left", "difference"],
        "same_evidence_for_both_sides": ["difference", "difference"],
        "duplicated_quote_for_both_sides": ["difference", "difference", "difference"],
        "duplicated_side_as_distinction": ["difference", "right", "difference"],
        "missing_distinction": ["left", "right"],
        "valid": ["left", "right", "difference"],
    }[case]
    evidence = []
    for name in case_evidence:
        quote, line = quotes[name]
        evidence.append({
            "source_id": "S001",
            "role": "statement",
            "quote": quote,
            "quote_match": {
                "result": "matched",
                "locations": [{"line_start": line, "line_end": line}],
            },
        })
    ctx.write_json("claims.extracted.json", {
        "schema": "claims_extracted/v1",
        "sources_index_sha256": ctx.store.hash(ctx.artifact_relative("sources/index.json")),
        "claims": [{
            "claim_id": "C001",
            "kind": "boundary",
            "text": "E100 and E200 are different errors",
            "subject": {
                "message_literal": "E100",
                "identifier": None,
                "value": None,
                "version": None,
                "other_error": "E200",
            },
            "evidence": evidence,
            "version_scope": None,
        }],
    })
    assessments = {
        "missing_side": [
            {"evidence_index": 0, "function": "documents_message", "reason": "left"},
            {"evidence_index": 1, "function": "distinguishes", "reason": "difference"},
        ],
        "same_evidence_for_both_sides": [
            {"evidence_index": 0, "function": "documents_message", "reason": "both sides"},
            {"evidence_index": 1, "function": "distinguishes", "reason": "difference"},
        ],
        "duplicated_quote_for_both_sides": [
            {"evidence_index": 0, "function": "documents_message", "reason": "left copy"},
            {"evidence_index": 1, "function": "documents_message", "reason": "right copy"},
            {"evidence_index": 2, "function": "distinguishes", "reason": "difference copy"},
        ],
        "duplicated_side_as_distinction": [
            {"evidence_index": 0, "function": "documents_message", "reason": "left"},
            {"evidence_index": 1, "function": "documents_message", "reason": "right"},
            {"evidence_index": 2, "function": "distinguishes", "reason": "left duplicate"},
        ],
        "missing_distinction": [
            {"evidence_index": 0, "function": "documents_message", "reason": "left"},
            {"evidence_index": 1, "function": "documents_message", "reason": "right"},
        ],
        "valid": [
            {"evidence_index": 0, "function": "documents_message", "reason": "left"},
            {"evidence_index": 1, "function": "documents_message", "reason": "right"},
            {"evidence_index": 2, "function": "distinguishes", "reason": "difference"},
        ],
    }[case]
    transport.outputs = [{"judgements": [{
        "claim_id": "C001",
        "basis_code": "BD-PAIR",
        "evidence_assessment": assessments,
        "link_confirmed": True,
        "support": "supported",
        "contradicted": False,
        "reason": "model affirms the boundary",
        "missing": [],
    }]}]
    return ctx, transport


@pytest.mark.parametrize(
    ("case", "expected_status", "expected_reason"),
    [
        ("missing_side", "unverified", "boundary_sides_unchecked"),
        ("same_evidence_for_both_sides", "unverified", "boundary_sides_unchecked"),
        ("duplicated_quote_for_both_sides", "unverified", "boundary_sides_unchecked"),
        ("duplicated_side_as_distinction", "unverified", "boundary_distinction_unchecked"),
        ("missing_distinction", "unverified", "boundary_distinction_unchecked"),
        ("valid", "verified", None),
    ],
)
def test_support_enforces_boundary_evidence_mapping(
    tmp_path, case, expected_status, expected_reason
):
    ctx, transport = _boundary_support_context(tmp_path, case)

    run_claims_support(ctx, {"slug": "sample_error"})

    claim = ctx.store.read_json(ctx.artifact_relative("claims.json"))["claims"][0]
    assert claim["status"] == expected_status
    assert claim["unverified_reason"] == expected_reason
    assert claim["judgement"]["support"] == "supported"
    assert len(transport.requests) == 1


def test_empty_source_type_lists_make_all_third_party_without_support_api_call(tmp_path):
    ctx, transport, _text = context(tmp_path, extracted_output())
    root = Path(__file__).parents[1]
    for relative in ("config/prompts/s3_support.v1.md", "config/schemas/claims_support.v2.json"):
        target = tmp_path / relative; target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(root / relative, target)
    run_claims_extract(ctx, {"slug": "sample_error"})
    assert len(transport.requests) == 1
    run_claims_support(ctx, {"slug": "sample_error"})
    assert len(transport.requests) == 1
    claims = ctx.store.read_json(ctx.artifact_relative("claims.json"))
    assert claims["source_types"] == {"S001": "third_party"}
    assert claims["claims"][0]["unverified_reason"] == "required_basis_missing"


@pytest.mark.parametrize(
    ("claim", "source_types", "expected"),
    [
        ({"kind": "default_value", "subject": {"identifier": "limit", "value": "10"}, "evidence": [evidence("S001", "official_doc", "limit defaults to 10")]}, {"S001": "official_doc"}, ["DV-DOC"]),
        ({"kind": "default_value", "subject": {"identifier": "limit", "value": "10"}, "evidence": [evidence("S001", "official_impl", "limit = 10", 1), evidence("S001", "official_impl", "use limit", 2)]}, {"S001": "official_impl"}, ["DV-IMPL"]),
        ({"kind": "version_behavior", "subject": {"version": "2.0"}, "evidence": [evidence("S001", "official_doc", "Changed in 2.0")]}, {"S001": "official_doc"}, ["VB-NOTES"]),
        ({"kind": "remedy", "subject": {}, "evidence": [evidence("S001", "official_doc", "Run repair") ]}, {"S001": "official_doc"}, ["RM-DOC"]),
        ({"kind": "occurrence", "subject": {}, "evidence": [evidence("S001", "case", "I encountered E100")]}, {"S001": "case"}, ["OC-REPORT"]),
        ({"kind": "boundary", "subject": {"message_literal": "E100", "other_error": "E200"}, "evidence": [evidence("S001", "official_doc", "E100"), evidence("S002", "official_doc", "E200")]}, {"S001": "official_doc", "S002": "official_doc"}, ["BD-PAIR"]),
    ],
)
def test_mechanical_prechecks_for_remaining_basis_families(claim, source_types, expected):
    sources = {source_id: {"github": {"commit_sha": "a"}} for source_id in source_types}
    assert precheck_claim(claim, sources, source_types, max_link_span_lines=80) == expected
