"""Tests for generate_gemini_content_with_timeout thread-based implementation.

旧 multiprocessing+Queue 方式では Gemini の大きなレスポンスが OS パイプバッファを
超えた際に proc.join() とのデッドロックが発生していた。
ThreadPoolExecutor 方式ではこのクラスのバグが構造上発生しないことをここで検証する。
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
from fact_check import generate_gemini_content_with_timeout


def test_large_response_no_deadlock() -> None:
    """数百KB相当の大きなレスポンスでもタイムアウトせず正しく取得できることを検証する。

    旧 multiprocessing+proc.join(timeout) 方式では、レスポンスが OS パイプバッファ
    (Windows ~4 KB) を超えると子の queue.put() がブロックし、
    proc.join() と互いに待ち合うデッドロックが発生していた。
    ThreadPoolExecutor 方式ではプロセス間 IPC がなく、このデッドロックは起きない。
    """
    big_payload = json.dumps({
        "factual_score": 78,
        "freshness_score": 65,
        "citation_coverage": 42,
        "risk_score": 25,
        "reasons": [f"reason_{i}: " + "x" * 100 for i in range(1000)],
        "required_actions": [],
        "sources": [],
        "unsupported_claims": [],
        "claims": [],
    })
    assert len(big_payload) > 100_000, f"Test payload too small: {len(big_payload)} bytes"

    with patch("fact_check._call_gemini_api", return_value=big_payload):
        result = generate_gemini_content_with_timeout("dummy_key", "gemini-2.5-flash", "test prompt")

    assert result.status == "ok", f"Expected status=ok, got {result.status!r}: {result.error}"
    assert result.scores is not None
    assert result.scores["factual_score"] == 78
    assert result.scores["risk_score"] == 25

    print(f"PASS test_large_response_no_deadlock  ({len(big_payload):,} bytes payload)")


def test_timeout_returns_unavailable() -> None:
    """指定タイムアウト内に応答がない場合、status=unavailable / error_category=timeout で返る。"""

    def slow_api(api_key: str, model: str, prompt: str) -> str:
        time.sleep(60)  # タイムアウト後に main スレッドが先に返るため実際には到達しない
        return "{}"

    with (
        patch("fact_check._call_gemini_api", side_effect=slow_api),
        patch("fact_check.GEMINI_TIMEOUT_SECONDS", 0.05),
    ):
        t0 = time.monotonic()
        result = generate_gemini_content_with_timeout("dummy_key", "gemini-2.5-flash", "test")
        elapsed = time.monotonic() - t0

    assert result.status == "unavailable", f"Expected unavailable, got {result.status!r}"
    assert result.error_category == "timeout", f"Expected timeout, got {result.error_category!r}"
    # タイムアウト値(0.05s)の 10 倍以内に返っていること（デッドロックしていない）
    assert elapsed < 0.5, f"Took too long: {elapsed:.2f}s (possible deadlock)"

    print(f"PASS test_timeout_returns_unavailable  (elapsed={elapsed*1000:.0f}ms)")


def test_api_error_returns_unavailable() -> None:
    """Gemini API が例外を投げた場合、status=unavailable でエラー情報が返る。"""

    def failing_api(api_key: str, model: str, prompt: str) -> str:
        raise RuntimeError("503 Service Unavailable")

    with patch("fact_check._call_gemini_api", side_effect=failing_api):
        result = generate_gemini_content_with_timeout("dummy_key", "gemini-2.5-flash", "test")

    assert result.status == "unavailable", f"Expected unavailable, got {result.status!r}"
    assert "RuntimeError" in result.error, f"Exception type not in error: {result.error!r}"
    assert "503" in result.error, f"Error message not in error: {result.error!r}"

    print(f"PASS test_api_error_returns_unavailable  (error={result.error[:60]!r})")


if __name__ == "__main__":
    test_large_response_no_deadlock()
    test_timeout_returns_unavailable()
    test_api_error_returns_unavailable()
    print("\nAll tests passed.")
