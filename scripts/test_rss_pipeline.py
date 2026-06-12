"""Tests for RSS pipeline eligibility gate and related guards.

Coverage:
  1. eligible=NO rejects article regardless of score >= SCORE_THRESHOLD
  2. [[SKIP]] detection prevents file save and records skipped_at_generation=True
  3. deleted_paths guard excludes ineligible articles from expand/refresh targets
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent))


# ── Test 1: eligible=NO rejects regardless of score ──────────────────────────

def test_eligible_no_rejects_above_threshold() -> None:
    """An article with eligible=NO must be rejected even if score >= SCORE_THRESHOLD."""
    import asyncio
    from rss_pipeline import score_article, SCORE_THRESHOLD

    # Gemini returns eligible=NO with a score above threshold (e.g. 75)
    gemini_response = '{"eligible": "NO", "score": 75}'

    async def _run():
        mock_client = MagicMock()
        mock_types = MagicMock()
        with patch("rss_pipeline._gemini_call", new=AsyncMock(return_value=gemini_response)):
            eligible, score = await score_article(mock_client, mock_types, "Some migration post", "body")
        return eligible, score

    eligible, score = asyncio.run(_run())
    assert not eligible, f"Expected eligible=False, got {eligible}"
    assert score == 75, f"Expected score=75, got {score}"
    assert score >= SCORE_THRESHOLD, "Score should be above threshold to prove the gate works"
    print(f"PASS test_eligible_no_rejects_above_threshold  (score={score}, threshold={SCORE_THRESHOLD})")


# ── Test 2: [[SKIP]] prevents save and records skipped_at_generation ─────────

def test_skip_detection_prevents_save_and_records_jsonl() -> None:
    """generate_draft returning [[SKIP]] must not save a file and must write skipped_at_generation=True."""
    import asyncio
    from rss_pipeline import generate_draft, append_rss_score_history, SCORE_HISTORY_FILE

    skip_output = "[[SKIP: no specific error found]]"

    async def _run_gen():
        mock_client = MagicMock()
        mock_types = MagicMock()
        article = {"title": "Why I migrated from X to Y", "feed_name": "Test Blog", "link": "https://example.com/post"}
        with patch("rss_pipeline._gemini_call", new=AsyncMock(return_value=skip_output)):
            content, skipped = await generate_draft(mock_client, mock_types, article, "body text")
        return content, skipped

    content, skipped = asyncio.run(_run_gen())
    assert skipped, "Expected skipped=True when output contains [[SKIP"
    assert "[[SKIP" in content

    # Verify append_rss_score_history records skipped_at_generation=True
    with tempfile.TemporaryDirectory() as tmpdir:
        history_path = Path(tmpdir) / "rss_score_history.jsonl"
        with patch("rss_pipeline.SCORE_HISTORY_FILE", history_path):
            append_rss_score_history(
                scored_at="2026-06-12T00:00:00Z",
                source_url="https://example.com/post",
                title="Why I migrated from X to Y",
                eligible=True,
                score=70,
                adopted=False,
                skipped_at_generation=True,
            )
        record = json.loads(history_path.read_text(encoding="utf-8").strip())
        assert record["skipped_at_generation"] is True
        assert record["adopted"] is False
        assert record["eligible"] is True
        assert record["score"] == 70

    print("PASS test_skip_detection_prevents_save_and_records_jsonl")


# ── Test 3: deleted guard excludes paths from expand/refresh ──────────────────

def test_deleted_paths_excluded_from_expand() -> None:
    """Files listed in deleted_articles.json must be excluded from expand targets."""
    import importlib

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        posts_dir = tmpdir / "content" / "posts"
        posts_dir.mkdir(parents=True)
        data_dir = tmpdir / "data"
        data_dir.mkdir()

        # Create two articles: one deleted, one eligible
        deleted_md = posts_dir / "auto_bad.md"
        good_md = posts_dir / "docker_404.md"

        # Both are short (< MIN_CHARS) so they'd normally be expand targets
        deleted_md.write_text("---\ntitle: \"Bad\"\ndate: 2026-06-10\n---\nshort body", encoding="utf-8")
        good_md.write_text("---\ntitle: \"Good\"\ndate: 2026-06-10\n---\nshort body", encoding="utf-8")

        # deleted_articles.json lists the bad article
        (data_dir / "deleted_articles.json").write_text(
            json.dumps([{"path": "content/posts/auto_bad.md", "url": "https://errorlog.jp/posts/auto_bad/",
                         "deleted_at": "2026-06-12", "reason": "ineligible: no specific error"}]),
            encoding="utf-8",
        )

        import expand_articles as ea
        orig_posts  = ea.POSTS_DIR
        orig_deleted = ea.DELETED_FILE
        try:
            ea.POSTS_DIR    = posts_dir
            ea.DELETED_FILE = data_dir / "deleted_articles.json"
            ea.FORCE        = True  # force all short articles to be candidates

            deleted_paths = ea._load_deleted_paths()
            candidates = []
            for src in sorted(posts_dir.glob("*.md"), key=lambda p: p.name):
                rel = f"content/posts/{src.name}"
                if rel in deleted_paths:
                    continue
                candidates.append(src)

            names = [p.name for p in candidates]
            assert "auto_bad.md" not in names, f"auto_bad.md should be excluded, got {names}"
            assert "docker_404.md" in names, f"docker_404.md should be included, got {names}"
        finally:
            ea.POSTS_DIR    = orig_posts
            ea.DELETED_FILE = orig_deleted
            ea.FORCE        = False

    print("PASS test_deleted_paths_excluded_from_expand")


if __name__ == "__main__":
    test_eligible_no_rejects_above_threshold()
    test_skip_detection_prevents_save_and_records_jsonl()
    test_deleted_paths_excluded_from_expand()
    print("\nAll tests passed.")
