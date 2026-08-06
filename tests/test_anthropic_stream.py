import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "anthropic_generate_article.py"
SPEC = importlib.util.spec_from_file_location("anthropic_generate_article", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakeResponse:
    def __init__(self, events: list[dict]) -> None:
        body = "".join(
            f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
            for event in events
        )
        self.lines = iter(body.encode("utf-8").splitlines(keepends=True))

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def readline(self) -> bytes:
        return next(self.lines, b"")


def stream_events(*, complete: bool) -> list[dict]:
    events = [
        {
            "type": "message_start",
            "message": {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "content": [],
                "model": "claude-opus-5",
                "stop_reason": None,
                "usage": {"input_tokens": 12, "output_tokens": 0},
            },
        },
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "draft"}},
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn"},
            "usage": {"output_tokens": 3, "server_tool_use": {"web_search_requests": 1}},
        },
    ]
    if complete:
        events.append({"type": "message_stop"})
    return events


class AnthropicStreamTests(unittest.TestCase):
    def call_stream(self, root: Path, events: list[dict]):
        with (
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch.object(MODULE.urllib.request, "urlopen", return_value=FakeResponse(events)),
        ):
            return MODULE.post_anthropic_stream("messages", {"model": "test"}, root, 0)

    def test_reconstructs_response_and_saves_checkpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "stream"
            response = self.call_stream(root, stream_events(complete=True))
            self.assertEqual(response["content"][0]["text"], "draft")
            self.assertEqual(response["usage"]["output_tokens"], 3)
            self.assertEqual((root / "partial_output.md").read_text(encoding="utf-8"), "draft")
            self.assertTrue((root / "events.jsonl").is_file())
            self.assertTrue((root / "response.json").is_file())

    def test_incomplete_stream_keeps_partial_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "stream"
            with self.assertRaisesRegex(SystemExit, "完了前に切断"):
                self.call_stream(root, stream_events(complete=False))
            self.assertEqual((root / "partial_output.md").read_text(encoding="utf-8"), "draft")
            self.assertTrue((root / "events.jsonl").is_file())


if __name__ == "__main__":
    unittest.main()
