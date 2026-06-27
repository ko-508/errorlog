import sys

sys.path.insert(0, "scripts")

from daily_publish import _EDITOR_NOTE_SECTION_RE
from lint_articles import _EDITOR_NOTE_RE


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
