from scripts.article_pipeline.quote_match import match_evidence, match_quote, normalize_text


def source(status="fetched"):
    return {
        "source_id": "S001", "status": status,
        "github": {"line_anchor": "supported", "permalink": "https://github.com/o/r/blob/abc/a.py"},
    }


def test_normalization_and_all_locations_with_github_lines():
    text = "zero\nＡ  B\nother\nA B\n"
    result = match_quote("A\tB", source(), text)
    assert normalize_text("Ａ\tB") == "A B"
    assert result["result"] == "matched"
    assert result["locations"] == [{"line_start": 2, "line_end": 2}, {"line_start": 4, "line_end": 4}]
    assert result["permalink"].endswith("#L2")


def test_unmatched_missing_and_failed_sources_are_not_evidence():
    assert match_quote("missing", source(), "body")["result"] == "unmatched"
    assert match_quote("body", source("failed"), "body")["result"] == "invalid_source"
    result = match_evidence({"source_id": "S999", "role": "context", "quote": "x"}, {}, {})
    assert result["quote_match"]["result"] == "invalid_source"

