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
    validate_sources,
    _classify_resolved_domain,
    _domain_ends_with,
    _has_vendor_community_prefix,
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
        assert check_url_status("ftp://example.com/file")["status"] == "invalid_url"
        assert check_url_status("https://example.com/\x00bad")["status"] == "invalid_url"
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
        result = check_url_status("https://example.com/grounding-api-redirect/\nabc")

    assert result["status"] == "204"
    request = urlopen.call_args.args[0]
    assert request.full_url == "https://example.com/grounding-api-redirect/abc"

    print("PASS test_check_url_status_removes_wrapping_whitespace")


def test_check_url_status_catches_urlopen_invalid_url() -> None:
    """urlopen InvalidURL should be contained inside check_url_status."""
    with patch("urllib.request.urlopen", side_effect=http.client.InvalidURL("bad url")):
        assert check_url_status("https://example.com/valid-looking")["status"] == "error"

    print("PASS test_check_url_status_catches_urlopen_invalid_url")


def _make_source(url: str, final_url: str | None = None) -> dict:
    """validate_sources に渡すソース辞書を生成するヘルパー。"""
    return {"url": url, "title": "", "claim": "", "source_type": "unknown",
            "final_url": final_url, "url_check_status": "200" if final_url else "skipped",
            "is_grounding_redirect": "vertexaisearch" in url}


def _run_validate(sources: list[dict], tags: list[str] | None = None) -> list[dict]:
    """validate_sources を URL チェックなしで走らせるヘルパー。"""
    def _fake_check(url: str) -> dict:
        for s in sources:
            if s["url"] == url:
                return {"status": s.get("url_check_status", "skipped"),
                        "final_url": s.get("final_url")}
        return {"status": "skipped", "final_url": None}
    with patch("fact_check.check_url_status", side_effect=_fake_check):
        validated, _, _, _ = validate_sources(sources, tags)
    return validated


def test_classify_resolved_domain_official() -> None:
    """公式ドメインが official に分類される。"""
    assert _classify_resolved_domain("docs.aws.amazon.com") == "official"
    assert _classify_resolved_domain("sub.docs.aws.amazon.com") == "official"  # サブドメイン
    assert _classify_resolved_domain("firebase.google.com") == "official"
    assert _classify_resolved_domain("docs.stripe.com") == "official"
    print("PASS test_classify_resolved_domain_official")


def test_classify_resolved_domain_community_blog() -> None:
    """コミュニティ・ブログが community_blog に分類される。"""
    assert _classify_resolved_domain("stackoverflow.com") == "community_blog"
    assert _classify_resolved_domain("qiita.com") == "community_blog"
    assert _classify_resolved_domain("zenn.dev") == "community_blog"
    print("PASS test_classify_resolved_domain_community_blog")


def test_classify_resolved_domain_unresolved_grounding() -> None:
    """grounding-redirect で final_url が未解決なら unresolved になる。"""
    gr_url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/ABCDEF"
    sources = [_make_source(gr_url, final_url=None)]
    validated = _run_validate(sources)
    assert validated[0]["resolved_source_type"] == "unresolved"
    assert validated[0]["resolved_domain"] is None
    print("PASS test_classify_resolved_domain_unresolved_grounding")


def test_tool_match_true() -> None:
    """着地ドメインが記事タグの公式ドメインに一致すれば tool_match=True。"""
    gr_url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/ABCDEF"
    sources = [_make_source(gr_url, final_url="https://docs.aws.amazon.com/s3/intro")]
    validated = _run_validate(sources, tags=["AWS"])
    s = validated[0]
    assert s["resolved_source_type"] == "official"
    assert s["tool_match"] is True
    print("PASS test_tool_match_true")


def test_tool_match_false_wrong_tool() -> None:
    """着地ドメインが記事タグと無関係なら tool_match=False。"""
    gr_url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/ABCDEF"
    sources = [_make_source(gr_url, final_url="https://docs.aws.amazon.com/s3/intro")]
    validated = _run_validate(sources, tags=["Docker"])  # AWS記事ではなくDocker
    s = validated[0]
    assert s["resolved_source_type"] == "official"  # ドメイン自体は official
    assert s["tool_match"] is False               # でも Docker の公式ではない
    print("PASS test_tool_match_false_wrong_tool")


def test_tool_match_false_no_tags() -> None:
    """article_tags が空なら tool_match=False（タグ未指定）。"""
    gr_url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/ABCDEF"
    sources = [_make_source(gr_url, final_url="https://docs.aws.amazon.com/s3/intro")]
    validated = _run_validate(sources, tags=[])
    assert validated[0]["tool_match"] is False
    print("PASS test_tool_match_false_no_tags")


def test_vendor_community_prefix_beats_official() -> None:
    """forums./discuss./community. 接頭辞ドメインは official より先に vendor_community になる。"""
    # forums.docker.com は docker.com の傘下だが vendor_community が優先
    assert _classify_resolved_domain("forums.docker.com") == "vendor_community"
    # community.atlassian.com は VENDOR_COMMUNITY_DOMAINS にも載っているが接頭辞ルールで先に捕捉
    assert _classify_resolved_domain("community.atlassian.com") == "vendor_community"
    # discuss.google.dev も接頭辞ルールで vendor_community
    assert _classify_resolved_domain("discuss.google.dev") == "vendor_community"
    # support. は接頭辞ルールに含まれないので official のまま
    assert _classify_resolved_domain("support.atlassian.com") == "official"
    # docs.docker.com は接頭辞ルールに該当せず official
    assert _classify_resolved_domain("docs.docker.com") == "official"
    # mycommunity.example.com は先頭ラベルが "mycommunity" なので接頭辞ルール対象外 → unknown
    assert _classify_resolved_domain("mycommunity.example.com") == "unknown"
    print("PASS test_vendor_community_prefix_beats_official")


def test_has_vendor_community_prefix() -> None:
    """_has_vendor_community_prefix の先頭ラベル完全一致を検証。"""
    assert _has_vendor_community_prefix("forums.docker.com") is True
    assert _has_vendor_community_prefix("discuss.python.org") is True
    assert _has_vendor_community_prefix("community.atlassian.com") is True
    assert _has_vendor_community_prefix("mycommunity.example.com") is False
    assert _has_vendor_community_prefix("docs.docker.com") is False
    assert _has_vendor_community_prefix("support.atlassian.com") is False
    print("PASS test_has_vendor_community_prefix")


def test_tool_match_independent_of_resolved_source_type() -> None:
    """vendor_community に分類されても tool_match は独立して True になる。"""
    gr_url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/ABCDEF"
    # forums.docker.com は Docker の公式ドメイン docker.com 傘下 → tool_match=True
    # かつ resolved_source_type=vendor_community
    sources = [_make_source(gr_url, final_url="https://forums.docker.com/t/some-issue")]
    validated = _run_validate(sources, tags=["Docker"])
    s = validated[0]
    assert s["resolved_source_type"] == "vendor_community"
    assert s["tool_match"] is True
    print("PASS test_tool_match_independent_of_resolved_source_type")


def test_domain_ends_with_subdomain() -> None:
    """サブドメイン一致が正しく動作する。"""
    assert _domain_ends_with("sub.docs.aws.amazon.com", "docs.aws.amazon.com") is True
    assert _domain_ends_with("docs.aws.amazon.com", "docs.aws.amazon.com") is True
    assert _domain_ends_with("notaws.amazon.com", "docs.aws.amazon.com") is False
    # ハイフン区切り（別ドメイン）はサブドメインと見なさない
    assert _domain_ends_with("evil-docs.aws.amazon.com", "docs.aws.amazon.com") is False
    print("PASS test_domain_ends_with_subdomain")


if __name__ == "__main__":
    test_article_hash_pure()
    test_unavailable_status_null_scores()
    test_ok_status_for_passing_result()
    test_check_url_status_rejects_invalid_urls()
    test_check_url_status_removes_wrapping_whitespace()
    test_check_url_status_catches_urlopen_invalid_url()
    test_classify_resolved_domain_official()
    test_classify_resolved_domain_community_blog()
    test_classify_resolved_domain_unresolved_grounding()
    test_tool_match_true()
    test_tool_match_false_wrong_tool()
    test_tool_match_false_no_tags()
    test_domain_ends_with_subdomain()
    test_vendor_community_prefix_beats_official()
    test_has_vendor_community_prefix()
    test_tool_match_independent_of_resolved_source_type()
    print("\nAll tests passed.")
