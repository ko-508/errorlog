"""Unit tests for fact_check.py schema additions (article_hash, null scores, status values)."""

import json
import http.client
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
from fact_check import (
    FactCheckResult,
    append_score_history,
    check_url_status,
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

        # 実行ステータスは "fact_check_unavailable"
        assert record["status"] == "fact_check_unavailable", f"Unexpected status: {record['status']}"
        # スコアは null
        assert record["factual_score"] is None, f"Expected null, got {record['factual_score']}"
        assert record["freshness_score"] is None
        assert record["citation_coverage"] is None
        assert record["risk_score"] is None
        # overall_judgement は result.status をそのまま保持
        assert record["overall_judgement"] == "fact_check_unavailable"

        # 全新フィールドが存在することを確認
        for f in ("gemini_model", "workflow", "run_id", "eval_id", "trigger",
                  "prompt_version", "article_hash", "unsupported_claims", "sources"):
            assert f in record, f"Missing field: {f}"

        print("PASS test_unavailable_status_null_scores")
    finally:
        tmp_path.unlink(missing_ok=True)


def test_ok_status_for_passing_result() -> None:
    """採点が正常完了した場合、status="ok" になり overall_judgement が判定値を持つことを検証する。"""
    for judgement in ("pass", "needs_revision", "reject", "critical"):
        result = FactCheckResult(
            path="content/posts/docker_404.md",
            title="Docker の 404 エラー",
            mode="existing",
            scores={
                "factual_score": 82,
                "freshness_score": 75,
                "citation_coverage": 60,
                "risk_score": 22,
            },
            passed=(judgement == "pass"),
            critical=(judgement == "critical"),
            reasons=[],
            required_actions=[],
            detected_at="2026-06-12",
            status=judgement,
            score_valid=True,
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            tmp_path = Path(f.name)

        try:
            with patch("fact_check.SCORE_HISTORY_PATH", tmp_path):
                append_score_history(result)

            record = json.loads(tmp_path.read_text(encoding="utf-8").strip())

            # 実行ステータスは常に "ok"
            assert record["status"] == "ok", (
                f"judgement={judgement}: expected status='ok', got '{record['status']}'"
            )
            # 採点判定は overall_judgement に保持
            assert record["overall_judgement"] == judgement, (
                f"Expected overall_judgement='{judgement}', got '{record['overall_judgement']}'"
            )
            # スコアは null にならない
            assert record["factual_score"] == 82
            # eval_id は UUID4 形式（8-4-4-4-12）
            parts = record["eval_id"].split("-")
            assert len(parts) == 5, f"eval_id is not UUID4: {record['eval_id']}"
        finally:
            tmp_path.unlink(missing_ok=True)

    print("PASS test_ok_status_for_passing_result")


def test_check_url_status_rejects_invalid_urls() -> None:
    """Invalid URL inputs should never leak exceptions."""
    with patch("urllib.request.urlopen") as urlopen:
        assert check_url_status("ftp://example.com/file") == "invalid_url"
        assert check_url_status("https://example.com/\x00bad") == "invalid_url"
        urlopen.assert_not_called()

    print("PASS test_check_url_status_rejects_invalid_urls")


def test_check_url_status_removes_wrapping_whitespace() -> None:
    """Whitespace introduced by line wrapping is removed before validation."""
    class FakeResponse:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    with patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
        status = check_url_status("https://example.com/grounding-api-redirect/\nabc")

    assert status == "204"
    request = urlopen.call_args.args[0]
    assert request.full_url == "https://example.com/grounding-api-redirect/abc"

    print("PASS test_check_url_status_removes_wrapping_whitespace")


def test_check_url_status_catches_urlopen_invalid_url() -> None:
    """urlopen InvalidURL should be contained inside check_url_status."""
    with patch("urllib.request.urlopen", side_effect=http.client.InvalidURL("bad url")):
        assert check_url_status("https://example.com/valid-looking") == "error"

    print("PASS test_check_url_status_catches_urlopen_invalid_url")


if __name__ == "__main__":
    test_article_hash_pure()
    test_unavailable_status_null_scores()
    test_ok_status_for_passing_result()
    test_check_url_status_rejects_invalid_urls()
    test_check_url_status_removes_wrapping_whitespace()
    test_check_url_status_catches_urlopen_invalid_url()
    print("\nAll tests passed.")
