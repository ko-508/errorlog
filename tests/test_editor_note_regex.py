import sys
import types

sys.path.insert(0, "scripts")
sys.modules.setdefault("anthropic", types.SimpleNamespace(Anthropic=object))

from daily_publish import (
    UNVERIFIABLE_DOMAINS,
    _EDITOR_NOTE_SECTION_RE,
    _url_netloc,
    extract_urls,
)
from lint_articles import _EDITOR_NOTE_RE


UNVERIFIABLE_ACTUAL = (
    "縺薙・繝峨Γ繧､繝ｳ縺ｯ蜿門ｾ励・辣ｧ蜷医〒縺阪↑縺・◆繧∝ｼ慕畑貅舌→縺励※菴ｿ逕ｨ荳榊庄"
)


def _is_unverifiable_url(url: str) -> bool:
    netloc = _url_netloc(url)
    return bool(
        netloc
        and any(netloc == domain or netloc.endswith("." + domain) for domain in UNVERIFIABLE_DOMAINS)
    )


def _synthetic_mismatches_from_editor_note(body: str) -> list[dict[str, str]]:
    match = _EDITOR_NOTE_SECTION_RE.search(body)
    if not match:
        return []

    mismatches = []
    for url in extract_urls(match.group(0)):
        if _is_unverifiable_url(url):
            mismatches.append({
                "url": url,
                "claimed": "",
                "actual": UNVERIFIABLE_ACTUAL,
            })
    return mismatches


def test_section_re_matches_straight_apostrophe():
    body = "\n## Editor's Note\n\nsome content\n"
    assert _EDITOR_NOTE_SECTION_RE.search(body) is not None


def test_section_re_matches_curly_apostrophe():
    # U+2019 - Claude Haiku generates this form.
    body = "\n## Editor\u2019s Note\n\nsome content\n"
    assert _EDITOR_NOTE_SECTION_RE.search(body) is not None


def test_section_re_matches_no_apostrophe():
    body = "\n## Editors Note\n\nsome content\n"
    assert _EDITOR_NOTE_SECTION_RE.search(body) is not None


def test_note_re_matches_straight_apostrophe():
    body = "## Editor's Note\n\nsome content\n"
    assert _EDITOR_NOTE_RE.search(body) is not None


def test_note_re_matches_curly_apostrophe():
    body = "\n## Editor\u2019s Note\n\nsome content\n"
    assert _EDITOR_NOTE_RE.search(body) is not None


def test_subn_replaces_curly_apostrophe_section():
    body = "\n## エラーの概要\n\ncontent\n\n## Editor\u2019s Note\n\nold content\n"
    new_section = "\n## Editor\u2019s Note\n\nnew content"
    result, count = _EDITOR_NOTE_SECTION_RE.subn(new_section, body, count=1)
    assert count == 1
    assert "new content" in result
    assert "old content" not in result


def test_unverifiable_domains_are_detected_after_netloc_normalization():
    assert _is_unverifiable_url(
        "https://www.reddit.com/r/archlinux/comments/1cjm063/podman_krun_502_bad_gateway/"
    )
    assert _is_unverifiable_url("https://redd.it/abc123")
    assert _is_unverifiable_url(
        "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQExample"
    )

    assert not _is_unverifiable_url("https://stackoverflow.com/questions/44778448/example")
    assert not _is_unverifiable_url("https://github.com/containers/podman/discussions/27308")


def test_editor_note_unverifiable_url_creates_synthetic_mismatch():
    reddit_url = "https://www.reddit.com/r/archlinux/comments/1cjm063/podman_krun_502_bad_gateway/"
    body = f"""
## Overview

content

## Editor's Note

See {reddit_url} for the cited discussion.

## Next Section

more content
"""

    mismatches = _synthetic_mismatches_from_editor_note(body)

    assert mismatches == [{
        "url": reddit_url,
        "claimed": "",
        "actual": UNVERIFIABLE_ACTUAL,
    }]


def test_editor_note_normal_domains_do_not_create_synthetic_mismatch():
    body = """
## Editor's Note

See https://stackoverflow.com/questions/44778448/example and
https://github.com/containers/podman/discussions/27308.
"""

    assert _synthetic_mismatches_from_editor_note(body) == []


def test_synthetic_mismatch_makes_citation_repair_loop_condition_truthy():
    body = """
## Editor's Note

See https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQExample.
"""
    citation_mismatches: list[dict[str, str]] = []

    citation_mismatches = citation_mismatches + _synthetic_mismatches_from_editor_note(body)

    assert citation_mismatches
