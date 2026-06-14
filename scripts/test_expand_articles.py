"""
expand_articles.py のユニットテスト。

対象:
  - _load_needs_rewrite: 順序・除外条件
  - _filter_pending: clean 記事除外・削除済み除外・順序保持
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import expand_articles as ea


# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_report(articles: list[dict], tmp_path: Path) -> Path:
    report_path = tmp_path / "lint_report.json"
    report_path.write_text(json.dumps({"articles": articles}), encoding="utf-8")
    return report_path


def _entry(name: str, rules: list[str], cat: str = "error_article") -> dict:
    return {
        "path": f"content/posts/{name}",
        "category": cat,
        "fails": [{"rule": r, "detail": "dummy"} for r in rules],
    }


# ─── _load_needs_rewrite ──────────────────────────────────────────────────────

def test_needs_rewrite_a3_only_before_a1(tmp_path, monkeypatch):
    """A3-only 記事が A1-containing 記事より前に並ぶこと。"""
    articles = [
        _entry("minikube_400.md", ["A1", "A3"]),   # A1 含む → 後
        _entry("docker_401.md",   ["A3"]),           # A3-only → 先
        _entry("nginx_500.md",    ["A3"]),           # A3-only → 先
        _entry("gcp_400.md",      ["A1"]),           # A1 のみ → 後
    ]
    monkeypatch.setattr(ea, "LINT_REPORT_PATH", _make_report(articles, tmp_path))

    entries = ea._load_needs_rewrite()
    names = [Path(e["path"]).name for e in entries]

    a3_only_idx = [i for i, e in enumerate(entries) if "A1" not in e["fail_rules"]]
    a1_idx      = [i for i, e in enumerate(entries) if "A1" in e["fail_rules"]]

    assert a3_only_idx, "A3-only entries must exist"
    assert a1_idx,      "A1 entries must exist"
    assert max(a3_only_idx) < min(a1_idx), (
        f"A3-only not all before A1 in: {names}"
    )


def test_needs_rewrite_excludes_b2(tmp_path, monkeypatch):
    """B2 FAIL 記事は needs_rewrite に含まれないこと。"""
    articles = [
        _entry("docker_401.md", ["B2", "A3"]),  # B2 → 除外
        _entry("nginx_500.md",  ["A3"]),          # → 含む
    ]
    monkeypatch.setattr(ea, "LINT_REPORT_PATH", _make_report(articles, tmp_path))

    entries = ea._load_needs_rewrite()
    names = [Path(e["path"]).name for e in entries]

    assert "docker_401.md" not in names, "B2 article must be excluded"
    assert "nginx_500.md" in names


def test_needs_rewrite_excludes_non_error_articles(tmp_path, monkeypatch):
    """non_error_article（skipped）は除外されること。"""
    articles = [
        _entry("tool_docker.md", ["A3"], cat="non_error_article"),
        _entry("docker_401.md",  ["A3"]),
    ]
    monkeypatch.setattr(ea, "LINT_REPORT_PATH", _make_report(articles, tmp_path))

    entries = ea._load_needs_rewrite()
    names = [Path(e["path"]).name for e in entries]

    assert "tool_docker.md" not in names
    assert "docker_401.md" in names


def test_needs_rewrite_excludes_clean_articles(tmp_path, monkeypatch):
    """FAIL なし記事（clean）は除外されること。"""
    articles = [
        _entry("docker_401.md", []),   # FAIL なし → clean
        _entry("nginx_500.md",  ["A3"]),
    ]
    monkeypatch.setattr(ea, "LINT_REPORT_PATH", _make_report(articles, tmp_path))

    entries = ea._load_needs_rewrite()
    names = [Path(e["path"]).name for e in entries]

    assert "docker_401.md" not in names, "Clean article (no fails) must be excluded"
    assert "nginx_500.md" in names


# ─── _filter_pending ──────────────────────────────────────────────────────────

def test_filter_pending_excludes_already_clean(tmp_path):
    """前回 expand で PASS した記事（Lint PASS）は次回実行で除外されること。"""
    # ファイルを作成
    (tmp_path / "docker_401.md").write_text("content", encoding="utf-8")
    (tmp_path / "nginx_500.md").write_text("content", encoding="utf-8")

    entries = [
        {"path": "docker_401.md", "fail_rules": ["A3"]},
        {"path": "nginx_500.md",  "fail_rules": ["A3"]},
    ]

    def mock_lint_check(path: Path):
        if path.name == "docker_401.md":
            return (True, [])          # 既に clean
        return (False, ["A3: 文字数不足"])

    with patch.object(ea, "_lint_check", side_effect=mock_lint_check):
        result = ea._filter_pending(entries, tmp_path, set())

    names = [p.name for p, _ in result]
    assert "docker_401.md" not in names, "Already-clean article must not be re-processed"
    assert "nginx_500.md" in names,      "Still-failing article must remain in queue"


def test_filter_pending_excludes_deleted(tmp_path):
    """削除済みとしてマークされた記事は除外されること。"""
    (tmp_path / "nginx_500.md").write_text("content", encoding="utf-8")
    # docker_401.md はファイルも存在しない

    entries = [
        {"path": "docker_401.md", "fail_rules": ["A3"]},
        {"path": "nginx_500.md",  "fail_rules": ["A3"]},
    ]
    deleted = {"docker_401.md"}

    with patch.object(ea, "_lint_check", return_value=(False, ["A3: x"])):
        result = ea._filter_pending(entries, tmp_path, deleted)

    names = [p.name for p, _ in result]
    assert "docker_401.md" not in names
    assert "nginx_500.md" in names


def test_filter_pending_preserves_order(tmp_path):
    """_filter_pending は入力エントリの順序（A3先・A1後）を保持すること。"""
    names_in = ["a3_only.md", "also_a3.md", "has_a1.md"]
    for n in names_in:
        (tmp_path / n).write_text("x", encoding="utf-8")

    entries = [
        {"path": "a3_only.md",  "fail_rules": ["A3"]},
        {"path": "also_a3.md",  "fail_rules": ["A3"]},
        {"path": "has_a1.md",   "fail_rules": ["A1", "A3"]},
    ]

    with patch.object(ea, "_lint_check", return_value=(False, ["A3: x"])):
        result = ea._filter_pending(entries, tmp_path, set())

    out_names = [p.name for p, _ in result]
    assert out_names == names_in, f"Order not preserved: {out_names}"
