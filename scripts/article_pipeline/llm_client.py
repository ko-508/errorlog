"""The only OpenAI API boundary for the article pipeline.

Production imports the official SDK lazily. Tests inject a transport and never
need an API key or a network connection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from . import PipelineError


class LlmTransport(Protocol):
    def count_input_tokens(self, request: dict[str, Any], *, timeout: float) -> Any: ...
    def create_response(self, request: dict[str, Any], *, timeout: float) -> Any: ...
    def retrieve_response(self, response_id: str, *, timeout: float) -> Any: ...
    def cancel_response(self, response_id: str, *, timeout: float) -> Any: ...


@dataclass
class LlmApiError(Exception):
    operation: str
    detail: str
    status_code: int | None = None
    code: str | None = None
    retry_after: float | None = None
    response_id: str | None = None

    def __str__(self) -> str:
        return (
            f"LLM API が失敗しました: operation={self.operation}, status={self.status_code}, "
            f"code={self.code}, detail={self.detail}"
        )


def _plain(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        result = dump(mode="json")
        if isinstance(result, dict):
            return result
    raise PipelineError(f"LLM SDK 応答を object に変換できません: type={type(value).__name__}")


class SdkTransport:
    def __init__(self) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise PipelineError(
                "OpenAI SDK が導入されていません: required=openai==3.24.0, "
                "install_file=requirements-article-pipeline.txt"
            ) from exc
        # The SDK reads OPENAI_API_KEY itself. The pipeline never reads its value.
        self.client = OpenAI(max_retries=0, base_url="https://api.openai.com/v1")

    def count_input_tokens(self, request: dict[str, Any], *, timeout: float) -> Any:
        return self.client.responses.input_tokens.count(timeout=timeout, **request)

    def create_response(self, request: dict[str, Any], *, timeout: float) -> Any:
        return self.client.responses.create(timeout=timeout, **request)

    def retrieve_response(self, response_id: str, *, timeout: float) -> Any:
        return self.client.responses.retrieve(response_id, timeout=timeout)

    def cancel_response(self, response_id: str, *, timeout: float) -> Any:
        return self.client.responses.cancel(response_id, timeout=timeout)


class LlmClient:
    def __init__(self, transport: LlmTransport | None = None) -> None:
        self._transport = transport

    @property
    def transport(self) -> LlmTransport:
        if self._transport is None:
            self._transport = SdkTransport()
        return self._transport

    def count_input_tokens(self, request: dict[str, Any], *, timeout: float) -> int:
        try:
            value = _plain(self.transport.count_input_tokens(request, timeout=timeout))
        except LlmApiError:
            raise
        except Exception as exc:
            raise LlmApiError("count", type(exc).__name__) from exc
        count = value.get("input_tokens")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise PipelineError(f"入力トークン数の応答が不正です: value={count!r}")
        return count

    def create(self, request: dict[str, Any], *, timeout: float) -> dict[str, Any]:
        try:
            return _plain(self.transport.create_response(request, timeout=timeout))
        except LlmApiError:
            raise
        except Exception as exc:
            raise LlmApiError("create", type(exc).__name__) from exc

    def retrieve(self, response_id: str, *, timeout: float) -> dict[str, Any]:
        try:
            return _plain(self.transport.retrieve_response(response_id, timeout=timeout))
        except LlmApiError:
            raise
        except Exception as exc:
            raise LlmApiError("retrieve", type(exc).__name__, response_id=response_id) from exc

    def cancel(self, response_id: str, *, timeout: float) -> dict[str, Any]:
        try:
            return _plain(self.transport.cancel_response(response_id, timeout=timeout))
        except LlmApiError:
            raise
        except Exception as exc:
            raise LlmApiError("cancel", type(exc).__name__, response_id=response_id) from exc
