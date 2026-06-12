"""Unit tests for baseline_fact_check.py stratification and side-effect isolation."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from baseline_fact_check import (
    STRATIFY_DAILY,
    STRATIFY_EXTREME_N,
    STRATIFY_RSS,
    STRATIFY_TOOL_MAX,
    _filter_existing_paths,
    score_with_retry,
    stratify_repeat_set,
)
from fact_check import BASE as FC_BASE, FactCheckResult, REPORTS_DIR, REWRITE_CANDIDATES_PATH, SCORE_HISTORY_PATH, save_report


# ── Synthetic fixtures ────────────────────────────────────────────────────────

def _make_paths(prefix: str, n: int) -> list[Path]:
    """Create fake Path objects (no files on disk)."""
    return [Path(f"content/posts/{prefix}_{i:03d}.md") for i in range(n)]


def _tool_fn_cycling(tools: list[str]) -> "Callable[[Path], str]":
    """Returns a tool function that cycles through the given list by path index."""
    def fn(p: Path) -> str:
        idx = int(p.stem.rsplit("_", 1)[-1])
        return tools[idx % len(tools)]
    return fn


def _len_fn_sequential(base: int = 1000, step: int = 100) -> "Callable[[Path], int]":
    """Returns a length function that assigns base + idx * step."""
    def fn(p: Path) -> int:
        idx = int(p.stem.rsplit("_", 1)[-1])
        return base + idx * step
    return fn


# ── Stratification tests ──────────────────────────────────────────────────────

def test_stratify_counts() -> None:
    """STRATIFY_DAILY daily + STRATIFY_RSS rss = 30 articles total."""
    daily = _make_paths("daily", 60)
    rss = _make_paths("auto", 20)

    # Use a tool function with enough distinct tools so limit isn't hit by tool_max
    tools = [f"tool_{i}" for i in range(30)]
    tool_fn = _tool_fn_cycling(tools)
    len_fn = _len_fn_sequential()

    selected = stratify_repeat_set(daily, rss, _tool_fn=tool_fn, _len_fn=len_fn)

    daily_sel = [p for p in selected if "daily" in p.stem]
    rss_sel = [p for p in selected if "auto" in p.stem]

    assert len(daily_sel) == STRATIFY_DAILY, f"Expected {STRATIFY_DAILY} daily, got {len(daily_sel)}"
    assert len(rss_sel) == STRATIFY_RSS, f"Expected {STRATIFY_RSS} rss, got {len(rss_sel)}"
    assert len(selected) == STRATIFY_DAILY + STRATIFY_RSS

    print("PASS test_stratify_counts")


def test_stratify_tool_max() -> None:
    """No tool appears more than STRATIFY_TOOL_MAX times in either bucket."""
    # Only 3 distinct tools → forces tool_max constraint to bind
    tools = ["toolA", "toolB", "toolC"]
    tool_fn = _tool_fn_cycling(tools)
    len_fn = _len_fn_sequential()

    daily = _make_paths("daily", 60)
    rss = _make_paths("auto", 20)
    selected = stratify_repeat_set(daily, rss, _tool_fn=tool_fn, _len_fn=len_fn)

    from baseline_fact_check import get_tool as real_get_tool
    # Count tool occurrences in each bucket separately
    daily_sel = [p for p in selected if "daily" in p.stem]
    rss_sel = [p for p in selected if "auto" in p.stem]

    for bucket, bucket_name in [(daily_sel, "daily"), (rss_sel, "rss")]:
        tool_counts: dict[str, int] = {}
        for p in bucket:
            t = tool_fn(p)
            tool_counts[t] = tool_counts.get(t, 0) + 1
        for t, count in tool_counts.items():
            assert count <= STRATIFY_TOOL_MAX, (
                f"{bucket_name} bucket: tool '{t}' appears {count} times, max is {STRATIFY_TOOL_MAX}"
            )

    print("PASS test_stratify_tool_max")


def test_stratify_extremes_included() -> None:
    """At least STRATIFY_EXTREME_N shortest and STRATIFY_EXTREME_N longest are included."""
    # 60 daily articles with sequential lengths 1000, 1100, 1200, ...
    daily = _make_paths("daily", 60)
    # Make enough distinct tools so tool_max won't block extreme articles
    tools = [f"tool_{i}" for i in range(30)]
    tool_fn = _tool_fn_cycling(tools)
    len_fn = _len_fn_sequential(base=1000, step=100)

    # daily_000 has len 1000 (shortest), daily_059 has len 6900 (longest)
    sorted_daily = sorted(daily, key=len_fn)
    must_short = set(sorted_daily[:STRATIFY_EXTREME_N])
    must_long = set(sorted_daily[-STRATIFY_EXTREME_N:])

    rss = _make_paths("auto", 20)
    selected = stratify_repeat_set(daily, rss, _tool_fn=tool_fn, _len_fn=len_fn)
    daily_sel = set(p for p in selected if "daily" in p.stem)

    for p in must_short:
        assert p in daily_sel, f"Shortest article {p.name} not in selection"
    for p in must_long:
        assert p in daily_sel, f"Longest article {p.name} not in selection"

    print("PASS test_stratify_extremes_included")


def test_stratify_deterministic() -> None:
    """Same inputs produce identical selections across calls (seed=42)."""
    daily = _make_paths("daily", 60)
    rss = _make_paths("auto", 20)
    tools = [f"tool_{i}" for i in range(30)]
    tool_fn = _tool_fn_cycling(tools)
    len_fn = _len_fn_sequential()

    sel1 = stratify_repeat_set(daily, rss, seed=42, _tool_fn=tool_fn, _len_fn=len_fn)
    sel2 = stratify_repeat_set(daily, rss, seed=42, _tool_fn=tool_fn, _len_fn=len_fn)
    assert sel1 == sel2

    print("PASS test_stratify_deterministic")


# ── Side-effect isolation tests ───────────────────────────────────────────────

def test_filter_existing_paths_skips_missing() -> None:
    """Missing saved paths are skipped before scoring."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        existing = tmp_path / "content" / "posts" / "existing.md"
        missing = tmp_path / "content" / "posts" / "missing.md"
        existing.parent.mkdir(parents=True)
        existing.write_text("---\ntitle: Existing\n---\nBody\n", encoding="utf-8")

        filtered = _filter_existing_paths([existing, missing], "test")

        assert filtered == [existing]

    print("PASS test_filter_existing_paths_skips_missing")


def _make_unavailable_result() -> FactCheckResult:
    return FactCheckResult(
        path="content/posts/docker_404.md",
        title="Docker 404",
        mode="existing",
        scores={"factual_score": 0, "freshness_score": 0, "citation_coverage": 0, "risk_score": 0},
        passed=False,
        critical=False,
        reasons=["external fact check unavailable: quota exceeded"],
        required_actions=[],
        detected_at="2026-06-12",
        status="fact_check_unavailable",
        score_valid=False,
    )


def test_save_report_write_report_false_no_report_file() -> None:
    """write_report=False でレポートファイルが reports/ に作成されないことを確認する。"""
    result = _make_unavailable_result()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        fake_reports = tmp_path / "reports" / "fact_check"
        fake_history = tmp_path / "history.jsonl"

        with (
            patch("fact_check.REPORTS_DIR", fake_reports),
            patch("fact_check.SCORE_HISTORY_PATH", fake_history),
        ):
            save_report(result, write_report=False)

        # reports/ ディレクトリは作られていない
        assert not fake_reports.exists(), "reports/ should not be created when write_report=False"
        # JSONL は追記されている
        assert fake_history.exists() and fake_history.stat().st_size > 0, "JSONL must be written"

    print("PASS test_save_report_write_report_false_no_report_file")


def test_save_report_write_report_false_no_rewrite_candidates() -> None:
    """write_report=False でも rewrite_candidates.json が変更されないことを確認する。"""
    result = _make_unavailable_result()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        fake_rewrite = tmp_path / "rewrite_candidates.json"
        fake_history = tmp_path / "history.jsonl"

        with (
            patch("fact_check.SCORE_HISTORY_PATH", fake_history),
            patch("fact_check.REWRITE_CANDIDATES_PATH", fake_rewrite),
            patch("fact_check.REPORTS_DIR", tmp_path / "reports"),
        ):
            save_report(result, write_report=False)

        assert not fake_rewrite.exists(), "rewrite_candidates.json must not be created in baseline mode"

    print("PASS test_save_report_write_report_false_no_rewrite_candidates")


def test_save_report_write_report_true_creates_file() -> None:
    """write_report=True（既存デフォルト）でレポートファイルが作成されることを確認する。"""
    result = _make_unavailable_result()
    result.score_valid = True
    result.status = "pass"
    result.scores = {"factual_score": 80, "freshness_score": 70, "citation_coverage": 50, "risk_score": 20}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        fake_reports = tmp_path / "reports" / "fact_check"
        fake_history = tmp_path / "history.jsonl"

        with (
            patch("fact_check.REPORTS_DIR", fake_reports),
            patch("fact_check.SCORE_HISTORY_PATH", fake_history),
            patch("fact_check.BASE", tmp_path),
        ):
            save_report(result, write_report=True)

        report_files = list((fake_reports / "existing_articles").glob("*.json"))
        assert len(report_files) == 1, f"Expected 1 report file, found {len(report_files)}"

    print("PASS test_save_report_write_report_true_creates_file")


def test_score_with_retry_missing_file_no_crash_and_failed_jsonl() -> None:
    """存在しないパスを渡してもクラッシュせず failed_fact_check レコードが JSONL に書かれること。

    これは二重防御の内側の層（score_with_retry 存在ガード）を検証する。
    _filter_existing_paths が外側でブロックした後もこのガードが機能することを保証する。
    """
    missing = FC_BASE / "content" / "posts" / "_test_nonexistent_deleted_article.md"
    assert not missing.exists(), f"Test requires file to not exist: {missing}"

    # FileNotFoundError を投げずに返ること
    result = score_with_retry(missing, sleep_seconds=0)

    assert result.status == "failed_fact_check", f"Expected failed_fact_check, got {result.status!r}"
    assert result.error_detail == "file not found (deleted after selection)"
    assert result.score_valid is False
    assert result.passed is False

    # save_report(write_report=False) でも JSONL に failed レコードが書かれること
    with tempfile.TemporaryDirectory() as tmp:
        fake_history = Path(tmp) / "fact_check_score_history.jsonl"
        with (
            patch("fact_check.SCORE_HISTORY_PATH", fake_history),
            patch("fact_check.BASE", FC_BASE),
        ):
            save_report(result, write_report=False)

        lines = [l for l in fake_history.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == 1, f"Expected 1 JSONL line, got {len(lines)}"
        record = json.loads(lines[0])
        assert record["status"] == "failed_fact_check"
        assert record["error_detail"] == "file not found (deleted after selection)"
        assert record.get("overall_judgement") == "failed_fact_check"

    print("PASS test_score_with_retry_missing_file_no_crash_and_failed_jsonl")


if __name__ == "__main__":
    test_stratify_counts()
    test_stratify_tool_max()
    test_stratify_extremes_included()
    test_stratify_deterministic()
    test_filter_existing_paths_skips_missing()
    test_save_report_write_report_false_no_report_file()
    test_save_report_write_report_false_no_rewrite_candidates()
    test_save_report_write_report_true_creates_file()
    test_score_with_retry_missing_file_no_crash_and_failed_jsonl()
    print("\nAll tests passed.")
