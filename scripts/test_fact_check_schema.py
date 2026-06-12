"""Unit tests for fact_check.py schema additions (article_hash, null scores)."""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
from fact_check import (
    FactCheckResult,
    append_score_history,
    compute_article_hash,
    split_frontmatter,
)


def test_article_hash_pure() -> None:
    """同一本文→同一ハッシュ、フロントマター変更のみ→ハッシュ不変 を検証する。"""
    body = "## エラーの概要\n\nHTTP 404 は Not Found です。"

    # 決定的（何度呼んでも同じ結果）
    assert compute_article_hash(body) == compute_article_hash(body)

    # フロントマターを変えても body は同一なのでハッシュは変わらない
    content_a = "---\ntitle: \"テスト A\"\ndate: 2024-01-01\n---\n" + body
    content_b = "---\ntitle: \"テスト B\"\ndate: 2026-06-12\nlastmod: 2026-06-12\n---\n" + body
    _, body_a = split_frontmatter(content_a)
    _, body_b = split_frontmatter(content_b)
    assert compute_article_hash(body_a) == compute_article_hash(body_b)

    # 本文が異なれば異なるハッシュ
    other = "## 別の本文\n\nHTTP 500 は Internal Server Error です。"
    assert compute_article_hash(body) != compute_article_hash(other)

    # 12桁小文字16進数
    h = compute_article_hash(body)
    assert len(h) == 12
    assert all(c in "0123456789abcdef" for c in h)

    print("PASS test_article_hash_pure")


def test_unavailable_status_null_scores() -> None:
    """status=fact_check_unavailable のレコードでスコアが null になることを検証する。"""
    result = FactCheckResult(
        path="content/posts/test_500.md",
        title="テスト 500 エラー",
        mode="existing",
        scores={
            "factual_score": 0,
            "freshness_score": 0,
            "citation_coverage": 0,
            "risk_score": 0,
        },
        passed=False,
        critical=False,
        reasons=["external fact check unavailable: quota exceeded"],
        required_actions=["Retry when Gemini becomes available."],
        detected_at="2026-06-12",
        status="fact_check_unavailable",
        score_valid=False,
    )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        tmp_path = Path(f.name)

    try:
        with patch("fact_check.SCORE_HISTORY_PATH", tmp_path):
            append_score_history(result)

        lines = [ln.strip() for ln in tmp_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == 1, f"Expected 1 record, got {len(lines)}"
        record = json.loads(lines[0])

        assert record["status"] == "fact_check_unavailable"
        assert record["factual_score"] is None, f"Expected null, got {record['factual_score']}"
        assert record["freshness_score"] is None
        assert record["citation_coverage"] is None
        assert record["risk_score"] is None

        # 新フィールドが存在することを確認
        for field in ("gemini_model", "workflow", "run_id", "trigger", "prompt_version",
                      "article_hash", "unsupported_claims", "sources"):
            assert field in record, f"Missing field: {field}"

        print("PASS test_unavailable_status_null_scores")
    finally:
        tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    test_article_hash_pure()
    test_unavailable_status_null_scores()
    print("\nAll tests passed.")
