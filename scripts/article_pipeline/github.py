"""Pure GitHub source validation and rendering helpers."""

from __future__ import annotations

import hashlib
from typing import Any
from urllib.parse import quote

from . import PipelineError


def git_blob_sha(body: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(body)).encode("ascii") + b"\0" + body).hexdigest()


def verify_blob_sha(body: bytes, expected: str) -> bool:
    return git_blob_sha(body) == expected


def normalize_github_text(text: str) -> tuple[str, str]:
    line_anchor = "unsupported" if "\r" in text.replace("\r\n", "") else "supported"
    return text.replace("\r\n", "\n"), line_anchor


def issue_text(issue: dict[str, Any], comments: list[dict[str, Any]]) -> str:
    required = {"title", "body", "state", "state_reason", "created_at", "closed_at", "labels", "html_url"}
    missing = sorted(required - set(issue))
    if missing:
        raise PipelineError(f"GitHub Issue 応答に必須キーがありません: missing={missing}")
    labels = [label.get("name", "") for label in issue["labels"] if isinstance(label, dict)]
    lines = [
        f"Title: {issue['title']}",
        f"State: {issue['state']}",
        f"State reason: {issue['state_reason']}",
        f"Created at: {issue['created_at']}",
        f"Closed at: {issue['closed_at']}",
        f"Labels: {', '.join(labels)}",
        f"Pull request: {'yes' if 'pull_request' in issue else 'no'}",
        "",
        str(issue["body"] or ""),
    ]
    for index, comment in enumerate(comments, start=1):
        user = comment.get("user") if isinstance(comment.get("user"), dict) else {}
        lines.extend(
            [
                "",
                f"--- comment {index} by {user.get('login', '')} ({comment.get('author_association', '')}) at {comment.get('created_at', '')} ---",
                str(comment.get("body") or ""),
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def permalink(repo: str, commit_sha: str, path: str) -> str:
    return f"https://github.com/{repo}/blob/{commit_sha}/{quote(path, safe='/')}"
