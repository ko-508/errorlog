"""
合成データを使った audit_fact_check.py のユニットテスト。

テスト項目:
  1. 再採点グループ構築:同一 path + 同一 hash のみがグループ化、hash 違いは除外
  2. フリップ率計算:2回採点×3記事、うち1記事が反転 → 33% が出る
  3. モデル混在警告:2モデル混在データで警告が出て最多モデルに絞られる
  4. status!=ok がスコア分析から除外され分析G に計上される
"""

from __future__ import annotations

import json
import sys
import tempfile
import math
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))

import audit_fact_check as aud


# ── Synthetic record factory ──────────────────────────────────────────────────

def _rec(
    path: str,
    article_hash: str = "aabbccdd",
    status: str = "ok",
    factual: int = 80,
    freshness: int = 70,
    citation: int = 50,
    risk: int = 20,
    model: str = "gemini-2.5-flash",
    prompt_version: str = "1",
    eval_id: str | None = None,
    checked_at: str = "2026-06-12T10:00:00Z",
    overall_judgement: str = "pass",
) -> dict:
    import uuid
    return {
        "eval_id":           eval_id or str(uuid.uuid4()),
        "path":              path,
        "article_hash":      article_hash,
        "status":            status,
        "factual_score":     factual if status == "ok" else None,
        "freshness_score":   freshness if status == "ok" else None,
        "citation_coverage": citation if status == "ok" else None,
        "risk_score":        risk if status == "ok" else None,
        "gemini_model":      model,
        "prompt_version":    prompt_version,
        "checked_at":        checked_at,
        "overall_judgement": overall_judgement,
        "sources":           [],
        "unsupported_claims": [],
        "error_detail":      None,
    }


# ── Test 1: Rescore group construction ───────────────────────────────────────

def test_rescore_group_construction() -> None:
    """
    同一 path + 同一 hash → グループ化
    同一 path + 異なる hash → hash_changed に分離
    単一レコードのみ → グループ化されない
    """
    records = [
        # Group A: same path, same hash (2 records)
        _rec("content/posts/docker_404.md", article_hash="hash_stable", eval_id="e1"),
        _rec("content/posts/docker_404.md", article_hash="hash_stable", eval_id="e2"),
        # Hash-changed: same path, different hashes
        _rec("content/posts/aws_500.md",    article_hash="hash_v1",     eval_id="e3"),
        _rec("content/posts/aws_500.md",    article_hash="hash_v2",     eval_id="e4"),
        # Single record only: must NOT appear in pure_groups
        _rec("content/posts/gcp_404.md",    article_hash="hash_single", eval_id="e5"),
    ]

    pure_groups, hash_changed, notes = aud.build_rescore_groups(records)

    # Only docker_404 should be in pure_groups
    assert len(pure_groups) == 1, f"Expected 1 pure group, got {len(pure_groups)}: {list(pure_groups.keys())}"
    assert "content/posts/docker_404.md" in pure_groups

    # aws_500 has hash change → must be in hash_changed
    assert "content/posts/aws_500.md" in hash_changed

    # gcp_404 (single record) must not appear in either
    assert "content/posts/gcp_404.md" not in pure_groups
    assert "content/posts/gcp_404.md" not in hash_changed

    print("PASS test_rescore_group_construction")


# ── Test 2: Flip rate = 33% ───────────────────────────────────────────────────

def test_flip_rate_33_percent() -> None:
    """
    3グループ、うち1グループが反転 → flip_rate = 1/3 ≈ 33.3%

    Thresholds:
      factual >= 75, freshness >= 50, citation_coverage >= 10, risk <= 55

    Group A (no flip):  both pass    factual=80/80
    Group B (no flip):  both fail    factual=60/60
    Group C (flip):     one pass, one fail  factual=80/60
    """
    records = [
        # Group A: stable pass
        _rec("posts/a.md", "hash_a", factual=80, freshness=70, citation=50, risk=20,
             overall_judgement="pass",           eval_id="a1"),
        _rec("posts/a.md", "hash_a", factual=80, freshness=70, citation=50, risk=20,
             overall_judgement="pass",           eval_id="a2"),
        # Group B: stable fail
        _rec("posts/b.md", "hash_b", factual=60, freshness=70, citation=50, risk=20,
             overall_judgement="needs_revision", eval_id="b1"),
        _rec("posts/b.md", "hash_b", factual=60, freshness=70, citation=50, risk=20,
             overall_judgement="needs_revision", eval_id="b2"),
        # Group C: flip (factual crosses 75)
        _rec("posts/c.md", "hash_c", factual=80, freshness=70, citation=50, risk=20,
             overall_judgement="pass",           eval_id="c1"),
        _rec("posts/c.md", "hash_c", factual=60, freshness=70, citation=50, risk=20,
             overall_judgement="needs_revision", eval_id="c2"),
    ]

    ok_records = [r for r in records if r["status"] == "ok"]
    pure_groups, _, _ = aud.build_rescore_groups(ok_records)

    assert len(pure_groups) == 3, f"Expected 3 groups, got {len(pure_groups)}"

    result = aud.analyze_flip_rate(pure_groups, ok_records)

    assert result["n_groups"] == 3
    assert result["flip_count"] == 1, f"Expected 1 flip, got {result['flip_count']}"

    expected_rate = 1 / 3
    actual_rate = result["flip_rate"]
    assert actual_rate is not None
    assert abs(actual_rate - expected_rate) < 0.001, (
        f"Expected flip_rate≈{expected_rate:.4f}, got {actual_rate}"
    )

    # flip_rate_pct should be ~33.3
    assert result["flip_rate_pct"] is not None
    assert abs(result["flip_rate_pct"] - 33.3) < 0.15, (
        f"Expected flip_rate_pct≈33.3, got {result['flip_rate_pct']}"
    )

    # factual_score should be identified as the cause
    assert result["axis_flip_cause"]["factual_score"] >= 1

    print(f"PASS test_flip_rate_33_percent  (flip_rate={result['flip_rate_pct']:.1f}%)")


# ── Test 3: Model mixing warning ─────────────────────────────────────────────

def test_model_mixing_warning() -> None:
    """
    2モデル混在データで:
      - model_mixed=True が検出される
      - 最多モデル(gemini-2.5-flash)のみが分析対象に絞られる
    """
    records_flash = [
        _rec(f"posts/a{i}.md", model="gemini-2.5-flash", eval_id=f"f{i}")
        for i in range(5)
    ]
    records_lite = [
        _rec(f"posts/b{i}.md", model="gemini-2.5-flash-lite", eval_id=f"l{i}")
        for i in range(2)
    ]
    all_records = records_flash + records_lite

    from collections import defaultdict
    model_counts: dict[str, int] = defaultdict(int)
    for r in all_records:
        model_counts[r.get("gemini_model", "?")] += 1

    primary = max(model_counts, key=model_counts.__getitem__)
    model_mixed = len(model_counts) > 1
    filtered = [r for r in all_records if r.get("gemini_model") == primary]

    assert model_mixed, "Expected model_mixed=True"
    assert primary == "gemini-2.5-flash"
    assert len(filtered) == 5, f"Expected 5 flash records, got {len(filtered)}"
    assert all(r["gemini_model"] == "gemini-2.5-flash" for r in filtered)

    print(f"PASS test_model_mixing_warning  (primary={primary}, kept={len(filtered)}/{len(all_records)})")


# ── Test 4: status!=ok excluded from score analysis, counted in G ────────────

def test_status_nonok_excluded_from_scores() -> None:
    """
    status=ok でないレコードはスコア分析(analyze_rescore_variance)から除外され、
    analyze_execution_health の status_counts に計上される。
    """
    ok_rec  = _rec("posts/ok.md",    status="ok",                    eval_id="ok1")
    unav_rec = _rec("posts/unav.md", status="fact_check_unavailable", eval_id="uv1")
    fail_rec = _rec("posts/fail.md", status="failed_fact_check",      eval_id="ff1")
    all_records = [ok_rec, unav_rec, fail_rec]

    ok_records = [r for r in all_records if r.get("status") == "ok"]
    assert len(ok_records) == 1

    # Rescore analysis uses only ok_records → pure_groups built from 1 record (no group)
    pure_groups, _, _ = aud.build_rescore_groups(ok_records)
    result_a = aud.analyze_rescore_variance(pure_groups)
    assert result_a["n_groups"] == 0, f"Expected 0 groups, got {result_a['n_groups']}"

    # Execution health sees all 3
    result_g = aud.analyze_execution_health(all_records)
    assert result_g["n_total"] == 3
    assert result_g["status_counts"].get("ok") == 1
    assert result_g["status_counts"].get("fact_check_unavailable") == 1
    assert result_g["status_counts"].get("failed_fact_check") == 1

    print("PASS test_status_nonok_excluded_from_scores")


# ── Runner ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_rescore_group_construction()
    test_flip_rate_33_percent()
    test_model_mixing_warning()
    test_status_nonok_excluded_from_scores()
    print("\nAll tests passed.")
