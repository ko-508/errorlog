from __future__ import annotations

from scripts.article_pipeline.github import (
    git_blob_sha,
    issue_text,
    normalize_github_text,
    permalink,
    verify_blob_sha,
)


def test_git_blob_sha_text_normalization_and_permalink() -> None:
    body = b"one\r\ntwo\r\n"
    digest = git_blob_sha(body)
    assert len(digest) == 40
    assert verify_blob_sha(body, digest)
    assert not verify_blob_sha(body + b"x", digest)
    assert normalize_github_text(body.decode()) == ("one\ntwo\n", "supported")
    assert normalize_github_text("one\rtwo") == ("one\rtwo", "unsupported")
    assert permalink("o/r", "a" * 40, "docs/a b.md") == (
        "https://github.com/o/r/blob/" + "a" * 40 + "/docs/a%20b.md"
    )


def test_issue_rendering_keeps_state_pull_request_and_author_association() -> None:
    issue = {
        "title": "Failure",
        "body": "Issue body",
        "state": "closed",
        "state_reason": "completed",
        "created_at": "2026-01-01T00:00:00Z",
        "closed_at": "2026-01-02T00:00:00Z",
        "labels": [{"name": "bug"}],
        "html_url": "https://github.com/o/r/issues/1",
        "pull_request": {},
    }
    comments = [
        {
            "body": "First comment",
            "created_at": "2026-01-01T01:00:00Z",
            "author_association": "MEMBER",
            "user": {"login": "alice"},
        },
        {
            "body": "Second comment",
            "created_at": "2026-01-01T02:00:00Z",
            "author_association": "NONE",
            "user": {"login": "bob"},
        },
    ]
    rendered = issue_text(issue, comments)
    assert "Pull request: yes" in rendered
    assert "comment 1 by alice (MEMBER)" in rendered
    assert "comment 2 by bob (NONE)" in rendered
