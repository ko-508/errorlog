from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.article_pipeline import PipelineError
from scripts.article_pipeline.plan_manual import load_candidates, normalized_candidates_hash


def write_yaml(tmp_path: Path, value: str) -> Path:
    path = tmp_path / "candidates.yml"
    path.write_text(value, encoding="utf-8")
    return path


def test_01_manual_plan_is_deterministic(tmp_path: Path) -> None:
    path = write_yaml(
        tmp_path,
        """schema: url_candidates/v1
candidates:
  - url: https://docs.python.org/3/library/pathlib.html#pathlib.Path
    role_hint: official_doc
  - github_file:
      repo: python/cpython
      path: Lib/pathlib/__init__.py
      ref: main
    role_hint: official_impl
""",
    )
    first = load_candidates(path, hint_urls=[], max_sources=40)
    second = load_candidates(path, hint_urls=[], max_sources=40)
    assert first == second
    assert normalized_candidates_hash(first) == normalized_candidates_hash(second)
    assert [item["source_id"] for item in first["candidates"]] == ["S001", "S002"]


@pytest.mark.parametrize(
    ("text", "pattern"),
    [
        ("schema: url_candidates/v1\nschema: duplicate\ncandidates: []\n", "duplicate key"),
        ("schema: url_candidates/v1\ncandidates: []\nunknown: true\n", "未知|キーが不正"),
        ("schema: url_candidates/v1\ncandidates:\n- {url: https://example.com, github_issue: {repo: a/b, number: 1}, role_hint: other}\n", "1種類"),
        ("schema: url_candidates/v1\ncandidates:\n- {url: http://example.com, role_hint: other}\n", "https"),
        ("schema: url_candidates/v1\ncandidates:\n- {url: https://u@example.com, role_hint: other}\n", "ユーザー情報"),
        ("schema: url_candidates/v1\ncandidates:\n- {url: https://127.0.0.1, role_hint: other}\n", "IP アドレス"),
    ],
)
def test_02_invalid_candidates_stop(tmp_path: Path, text: str, pattern: str) -> None:
    with pytest.raises(PipelineError, match=pattern):
        load_candidates(write_yaml(tmp_path, text), hint_urls=[], max_sources=40)
    too_many = {
        "schema": "url_candidates/v1",
        "candidates": [
            {"url": f"https://example.com/{index}", "role_hint": "other"}
            for index in range(41)
        ],
    }
    with pytest.raises(PipelineError, match="上限"):
        load_candidates(write_yaml(tmp_path, json.dumps(too_many)), hint_urls=[], max_sources=40)


def test_03_github_urls_are_converted(tmp_path: Path) -> None:
    path = write_yaml(
        tmp_path,
        """schema: url_candidates/v1
candidates:
- {url: https://github.com/python/cpython/blob/main/README.rst#L1, role_hint: official_impl}
- {url: https://github.com/python/cpython/issues/1, role_hint: case}
- {url: https://github.com/python/cpython/pull/2, role_hint: case}
- {url: https://github.com/python/cpython/actions, role_hint: other}
""",
    )
    plan = load_candidates(path, hint_urls=[], max_sources=40)
    assert [item["kind"] for item in plan["candidates"]] == [
        "github_file", "github_issue", "github_issue", "url"
    ]
    assert plan["candidates"][0]["anchor"] == "L1"
    assert plan["candidates"][3]["github_html_unsupported"] is True


def test_04_format_only_change_has_same_normalized_hash(tmp_path: Path) -> None:
    first = write_yaml(tmp_path, '{"schema":"url_candidates/v1","candidates":[{"url":"https://example.com/a","role_hint":"other"}]}')
    one = load_candidates(first, hint_urls=[], max_sources=40)
    first.write_text(
        "schema: url_candidates/v1\ncandidates:\n  - role_hint: other\n    url: https://example.com/a\n",
        encoding="utf-8",
    )
    two = load_candidates(first, hint_urls=[], max_sources=40)
    assert normalized_candidates_hash(one) == normalized_candidates_hash(two)


def test_05_hint_and_duplicate_candidates_merge_origins(tmp_path: Path) -> None:
    path = write_yaml(
        tmp_path,
        "schema: url_candidates/v1\ncandidates:\n- {url: https://example.com/a, role_hint: official_doc}\n",
    )
    plan = load_candidates(path, hint_urls=["https://example.com/a"], max_sources=40)
    assert len(plan["candidates"]) == 1
    assert plan["candidates"][0]["origins"] == ["url_candidates", "topic_hint_urls"]
