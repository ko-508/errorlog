import builtins
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scripts.article_pipeline import PipelineError
from scripts.article_pipeline.llm_client import LlmClient, SdkTransport


class Transport:
    def __init__(self):
        self.calls = []

    def count_input_tokens(self, request, *, timeout):
        self.calls.append(("count", request, timeout)); return {"input_tokens": 12}

    def create_response(self, request, *, timeout):
        self.calls.append(("create", request, timeout)); return {"id": "resp_1"}

    def retrieve_response(self, response_id, *, timeout):
        self.calls.append(("retrieve", response_id, timeout)); return {"id": response_id}

    def cancel_response(self, response_id, *, timeout):
        self.calls.append(("cancel", response_id, timeout)); return {"id": response_id, "status": "cancelled"}


def test_injected_transport_uses_only_four_operations():
    transport = Transport(); client = LlmClient(transport)
    assert client.count_input_tokens({"model": "m"}, timeout=1) == 12
    client.create({}, timeout=2); client.retrieve("resp_1", timeout=3); client.cancel("resp_1", timeout=4)
    assert [item[0] for item in transport.calls] == ["count", "create", "retrieve", "cancel"]


def test_sdk_is_lazy_and_missing_sdk_has_explicit_error():
    client = LlmClient()
    assert client._transport is None
    real_import = builtins.__import__
    def blocked(name, *args, **kwargs):
        if name == "openai":
            raise ImportError("blocked")
        return real_import(name, *args, **kwargs)
    with patch("builtins.__import__", side_effect=blocked):
        with pytest.raises(PipelineError, match="openai==3.24.0"):
            SdkTransport()


def test_sdk_client_disables_automatic_retries_and_fixes_base_url(monkeypatch):
    captured = {}
    class FakeOpenAI:
        def __init__(self, **kwargs): captured.update(kwargs)
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    SdkTransport()
    assert captured == {"max_retries": 0, "base_url": "https://api.openai.com/v1"}
