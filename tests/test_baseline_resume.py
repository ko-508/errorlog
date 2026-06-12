"""Tests for baseline_fact_check.py resume and repair-progress logic."""
import json
import sys
from pathlib import Path

import pytest

# Make scripts/ importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )


def _write_progress(path: Path, scored: list[str], mode: str = "full") -> None:
    path.write_text(
        json.dumps({"mode": mode, "scored": scored, "started_at": "2026-01-01T00:00:00Z"}),
        encoding="utf-8",
    )


# ── load_jsonl_ok_paths ───────────────────────────────────────────────────────

def test_load_jsonl_ok_paths_returns_only_ok(tmp_path, monkeypatch):
    import baseline_fact_check as bfc

    jsonl = tmp_path / "fact_check_score_history.jsonl"
    _write_jsonl(jsonl, [
        {"path": "content/posts/a.md", "status": "ok"},
        {"path": "content/posts/b.md", "status": "failed_fact_check"},
        {"path": "content/posts/c.md", "status": "fact_check_unavailable"},
        {"path": "content/posts/d.md", "status": "ok"},
    ])
    monkeypatch.setattr(bfc, "JSONL_PATH", jsonl)

    result = bfc.load_jsonl_ok_paths()
    assert result == {"content/posts/a.md", "content/posts/d.md"}


def test_load_jsonl_ok_paths_missing_file(tmp_path, monkeypatch):
    import baseline_fact_check as bfc

    monkeypatch.setattr(bfc, "JSONL_PATH", tmp_path / "nonexistent.jsonl")
    assert bfc.load_jsonl_ok_paths() == set()


# ── resume skip logic ─────────────────────────────────────────────────────────

def test_resume_skips_only_ok_paths(tmp_path, monkeypatch):
    """Progress entries whose path is NOT ok in JSONL must be re-queued."""
    import baseline_fact_check as bfc

    jsonl = tmp_path / "fact_check_score_history.jsonl"
    _write_jsonl(jsonl, [
        {"path": "content/posts/ok_article.md", "status": "ok"},
        {"path": "content/posts/failed_article.md", "status": "failed_fact_check"},
    ])

    progress = tmp_path / "baseline_progress.json"
    _write_progress(progress, [
        "content/posts/ok_article.md",
        "content/posts/failed_article.md",
        "content/posts/unavailable_article.md",  # in progress, no JSONL record
    ])

    monkeypatch.setattr(bfc, "JSONL_PATH", jsonl)
    monkeypatch.setattr(bfc, "PROGRESS_PATH", progress)

    progress_set = bfc.load_progress("full")
    ok_in_jsonl = bfc.load_jsonl_ok_paths()
    already = progress_set & ok_in_jsonl

    assert already == {"content/posts/ok_article.md"}
    # failed and unavailable are NOT in the skip set → will be re-scored
    assert "content/posts/failed_article.md" not in already
    assert "content/posts/unavailable_article.md" not in already


def test_resume_ok_article_stays_skipped_after_repair(tmp_path, monkeypatch):
    """An ok article must still be in the skip set after repair_progress runs."""
    import baseline_fact_check as bfc

    jsonl = tmp_path / "fact_check_score_history.jsonl"
    _write_jsonl(jsonl, [
        {"path": "content/posts/ok_article.md", "status": "ok"},
        {"path": "content/posts/failed_article.md", "status": "failed_fact_check"},
    ])

    progress = tmp_path / "baseline_progress.json"
    _write_progress(progress, [
        "content/posts/ok_article.md",
        "content/posts/failed_article.md",
    ])

    monkeypatch.setattr(bfc, "JSONL_PATH", jsonl)
    monkeypatch.setattr(bfc, "PROGRESS_PATH", progress)

    # Run repair (--yes skips confirmation)
    exit_code = bfc.repair_progress(yes=True)
    assert exit_code == 0

    # ok article still in progress
    repaired_progress = bfc.load_progress("full")
    assert "content/posts/ok_article.md" in repaired_progress
    assert "content/posts/failed_article.md" not in repaired_progress

    # Skip set after repair still covers ok article
    ok_in_jsonl = bfc.load_jsonl_ok_paths()
    already = repaired_progress & ok_in_jsonl
    assert "content/posts/ok_article.md" in already


# ── repair_progress ───────────────────────────────────────────────────────────

def test_repair_removes_non_ok_entries(tmp_path, monkeypatch, capsys):
    import baseline_fact_check as bfc

    jsonl = tmp_path / "fact_check_score_history.jsonl"
    _write_jsonl(jsonl, [
        {"path": "content/posts/keep.md", "status": "ok"},
        {"path": "content/posts/drop_failed.md", "status": "failed_fact_check"},
    ])

    progress = tmp_path / "baseline_progress.json"
    _write_progress(progress, [
        "content/posts/keep.md",
        "content/posts/drop_failed.md",
        "content/posts/drop_no_jsonl.md",
    ])

    monkeypatch.setattr(bfc, "JSONL_PATH", jsonl)
    monkeypatch.setattr(bfc, "PROGRESS_PATH", progress)

    exit_code = bfc.repair_progress(yes=True)
    assert exit_code == 0

    data = json.loads(progress.read_text(encoding="utf-8"))
    assert data["scored"] == ["content/posts/keep.md"]

    out = capsys.readouterr().out
    assert "Removed 2" in out
    assert "1 ok entries remain" in out


def test_repair_counts_match_jsonl_not_ok(tmp_path, monkeypatch):
    """Removed count == len(progress entries with no ok in JSONL)."""
    import baseline_fact_check as bfc

    jsonl = tmp_path / "fact_check_score_history.jsonl"
    ok_paths = [f"content/posts/art_{i}.md" for i in range(5)]
    non_ok_paths = [f"content/posts/bad_{i}.md" for i in range(3)]
    _write_jsonl(jsonl, [
        {"path": p, "status": "ok"} for p in ok_paths
    ] + [
        {"path": p, "status": "failed_fact_check"} for p in non_ok_paths
    ])

    all_progress = ok_paths + non_ok_paths + ["content/posts/ghost.md"]  # ghost has no JSONL
    progress = tmp_path / "baseline_progress.json"
    _write_progress(progress, all_progress)

    monkeypatch.setattr(bfc, "JSONL_PATH", jsonl)
    monkeypatch.setattr(bfc, "PROGRESS_PATH", progress)

    bfc.repair_progress(yes=True)

    data = json.loads(progress.read_text(encoding="utf-8"))
    assert set(data["scored"]) == set(ok_paths)
    # removed = 3 non-ok + 1 ghost = 4
    assert len(data["scored"]) == 5


def test_repair_noop_when_progress_missing(tmp_path, monkeypatch, capsys):
    import baseline_fact_check as bfc

    monkeypatch.setattr(bfc, "PROGRESS_PATH", tmp_path / "no_progress.json")
    exit_code = bfc.repair_progress(yes=True)
    assert exit_code == 0
    assert "not found" in capsys.readouterr().out


def test_repair_rejects_repeat_mode(tmp_path, monkeypatch, capsys):
    import baseline_fact_check as bfc

    progress = tmp_path / "baseline_progress.json"
    _write_progress(progress, [], mode="repeat")
    monkeypatch.setattr(bfc, "PROGRESS_PATH", progress)

    exit_code = bfc.repair_progress(yes=True)
    assert exit_code == 1
    assert "repeat" in capsys.readouterr().out
