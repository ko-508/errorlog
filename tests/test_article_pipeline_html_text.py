from __future__ import annotations

from pathlib import Path

from scripts.article_pipeline.html_text import extract_html_text


FIXTURES = Path(__file__).parent / "fixtures/article_pipeline"


def test_html_extraction_matches_fixed_fixture_and_is_deterministic() -> None:
    html = (FIXTURES / "page.html").read_text(encoding="utf-8")
    expected = (FIXTURES / "page_expected.txt").read_text(encoding="utf-8")

    first = extract_html_text(html)
    second = extract_html_text(html)

    assert first == second
    assert first[0] == expected
    assert first[1]["root"] == "main"
    assert first[1]["dropped_hidden_chars"] > 0
    assert first[1]["outline"]
    for forbidden in ("script secret", "style secret", "nav secret", "hidden secret"):
        assert forbidden not in first[0]


def test_root_selection_requires_exactly_one_candidate() -> None:
    text, extraction = extract_html_text(
        "<body><main>one</main><main>two</main><article>chosen</article></body>"
    )
    assert extraction["root"] == "article"
    assert text == "chosen\n"


def test_pre_preserves_spaces_trailing_whitespace_and_three_blank_lines() -> None:
    raw = "  first  \n\n\n second\t "
    text, _extraction = extract_html_text(f"<main><p>before</p><pre>{raw}</pre><p>after</p></main>")
    assert raw in text
