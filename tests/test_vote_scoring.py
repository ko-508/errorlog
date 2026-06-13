"""Tests for majority-vote scoring and 2-axis gate logic in fact_check.py."""
import dataclasses
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fact_check as fc


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_result(
    factual: int,
    risk: int,
    freshness: int = 90,
    citation: int = 80,
    status: str = "pass",
    score_valid: bool = True,
    path: str = "content/posts/test_tool_500.md",
) -> fc.FactCheckResult:
    passed = factual >= fc.MIN_FACTUAL and risk <= fc.MAX_RISK
    critical = risk >= fc.CRITICAL_RISK
    if critical:
        status = "critical"
    elif not passed:
        status = "reject"
    else:
        status = "pass"
    return fc.FactCheckResult(
        path=path,
        title="Test Article",
        mode="new",
        scores={
            "factual_score": factual,
            "freshness_score": freshness,
            "citation_coverage": citation,
            "risk_score": risk,
        },
        passed=passed,
        critical=critical,
        reasons=[],
        required_actions=[],
        detected_at="2026-01-01",
        status=status,
        score_valid=score_valid,
        article_hash="abc123",
        gemini_model="gemini-2.5-flash",
    )


# ── 2-axis gate logic ─────────────────────────────────────────────────────────

def test_passes_when_factual_and_risk_ok_despite_low_freshness_citation():
    """Low freshness/citation must NOT cause fail if factual+risk are in range."""
    result = _make_result(factual=80, risk=40, freshness=10, citation=0)
    assert result.passed is True


def test_fails_when_factual_below_threshold():
    result = _make_result(factual=70, risk=40)  # factual < MIN_FACTUAL(75)
    assert result.passed is False
    assert result.critical is False


def test_fails_when_risk_above_threshold():
    result = _make_result(factual=90, risk=60)  # risk > MAX_RISK(55)
    assert result.passed is False
    assert result.critical is False


def test_critical_when_risk_above_critical_threshold():
    result = _make_result(factual=90, risk=90)  # risk >= CRITICAL_RISK(85)
    assert result.critical is True


def test_passes_exactly_at_thresholds():
    result = _make_result(factual=75, risk=55)  # exactly at boundary
    assert result.passed is True


# ── Median computation ────────────────────────────────────────────────────────

def test_median_of_three_odd():
    """Median of [95, 50, 80] == 80."""
    import statistics
    vals = [95, 50, 80]
    assert int(statistics.median(vals)) == 80


def test_median_of_three_even_axis():
    """Median of [60, 90, 75] == 75."""
    import statistics
    vals = [60, 90, 75]
    assert int(statistics.median(vals)) == 75


# ── evaluate_new_article voting ───────────────────────────────────────────────

def _mock_evaluate_content(scores_seq):
    """Returns a side_effect function that yields results from scores_seq in order."""
    calls = iter(scores_seq)

    def _side(path, content, mode):
        factual, risk = next(calls)
        return _make_result(factual=factual, risk=risk)

    return _side


def test_vote_count_1_falls_back_to_single_shot(tmp_path):
    """FACT_CHECK_VOTE_COUNT=1 must call evaluate_content exactly once."""
    result = _make_result(factual=85, risk=20)
    with (
        patch.object(fc, "FACT_CHECK_VOTE_COUNT", 1),
        patch("fact_check.evaluate_content", return_value=result) as mock_eval,
        patch("fact_check.save_report", side_effect=lambda r: r),
    ):
        out = fc.evaluate_new_article(Path("content/posts/t.md"), "content")
    mock_eval.assert_called_once()
    assert out.is_final_vote is False  # default, no vote_group assigned
    assert out.vote_count == 1


def test_vote_count_3_calls_evaluate_content_three_times(tmp_path):
    """FACT_CHECK_VOTE_COUNT=3 must call evaluate_content exactly 3 times."""
    scores = [(95, 5), (50, 100), (80, 30)]
    with (
        patch.object(fc, "FACT_CHECK_VOTE_COUNT", 3),
        patch("fact_check.evaluate_content", side_effect=_mock_evaluate_content(scores)) as mock_eval,
        patch("fact_check.save_report", side_effect=lambda r: r),
    ):
        out = fc.evaluate_new_article(Path("content/posts/t.md"), "content")
    assert mock_eval.call_count == 3


def test_vote_median_scores_adopted(tmp_path):
    """Median factual=[95,50,80]→80, risk=[5,100,30]→30; verdict=pass."""
    scores = [(95, 5), (50, 100), (80, 30)]
    with (
        patch.object(fc, "FACT_CHECK_VOTE_COUNT", 3),
        patch("fact_check.evaluate_content", side_effect=_mock_evaluate_content(scores)),
        patch("fact_check.save_report", side_effect=lambda r: r),
    ):
        out = fc.evaluate_new_article(Path("content/posts/t.md"), "content")
    assert out.scores["factual_score"] == 80
    assert out.scores["risk_score"] == 30
    assert out.passed is True
    assert out.is_final_vote is True
    assert out.vote_count == 3
    assert out.vote_group_id != ""


def test_vote_median_fail_when_factual_low():
    """Median factual=[60,50,70]→60 < 75 → fail."""
    scores = [(60, 20), (50, 20), (70, 20)]
    with (
        patch.object(fc, "FACT_CHECK_VOTE_COUNT", 3),
        patch("fact_check.evaluate_content", side_effect=_mock_evaluate_content(scores)),
        patch("fact_check.save_report", side_effect=lambda r: r),
    ):
        out = fc.evaluate_new_article(Path("content/posts/t.md"), "content")
    assert out.passed is False
    assert out.status == "reject"


def test_vote_raw_records_saved_before_final(tmp_path):
    """save_report must be called 4 times total (3 raw + 1 final)."""
    scores = [(95, 5), (50, 100), (80, 30)]
    saved = []
    with (
        patch.object(fc, "FACT_CHECK_VOTE_COUNT", 3),
        patch("fact_check.evaluate_content", side_effect=_mock_evaluate_content(scores)),
        patch("fact_check.save_report", side_effect=lambda r: (saved.append(r), r)[1]),
    ):
        fc.evaluate_new_article(Path("content/posts/t.md"), "content")
    assert len(saved) == 4
    raw_votes = saved[:3]
    final = saved[3]
    assert all(r.is_final_vote is False for r in raw_votes)
    assert final.is_final_vote is True
    assert all(r.vote_group_id == final.vote_group_id for r in raw_votes)


def test_vote_group_id_shared_across_all_records():
    """All 3 raw votes and the final must share the same vote_group_id."""
    scores = [(80, 20), (85, 25), (90, 15)]
    saved = []
    with (
        patch.object(fc, "FACT_CHECK_VOTE_COUNT", 3),
        patch("fact_check.evaluate_content", side_effect=_mock_evaluate_content(scores)),
        patch("fact_check.save_report", side_effect=lambda r: (saved.append(r), r)[1]),
    ):
        fc.evaluate_new_article(Path("content/posts/t.md"), "content")
    group_ids = {r.vote_group_id for r in saved}
    assert len(group_ids) == 1
    assert "" not in group_ids


def test_vote_fallback_when_insufficient_valid(tmp_path):
    """If fewer than 2 valid votes, return last raw result with is_final_vote=True."""
    unavail = _make_result(factual=0, risk=0, score_valid=False, status="fact_check_unavailable")
    unavail.score_valid = False
    scores_iter = iter([unavail, unavail, unavail])

    with (
        patch.object(fc, "FACT_CHECK_VOTE_COUNT", 3),
        patch("fact_check.evaluate_content", side_effect=lambda *a: next(scores_iter)),
        patch("fact_check.save_report", side_effect=lambda r: r),
    ):
        out = fc.evaluate_new_article(Path("content/posts/t.md"), "content")
    assert out.is_final_vote is True
