"""The only network boundary used by the article pipeline."""

from __future__ import annotations

import gzip
import http.client
import queue
import socket
import ssl
import threading
import time
import zlib
from dataclasses import dataclass
from email.message import Message
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit

from . import PipelineError
from .urlpolicy import all_addresses_public


SAVED_HEADERS = {
    "content-type", "content-length", "content-encoding", "etag", "last-modified",
    "date", "location", "retry-after", "x-github-request-id",
    "x-ratelimit-remaining", "x-ratelimit-reset",
}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class NetFailure(PipelineError):
    def __init__(self, reason: str, detail: str, *, attempts: list[dict[str, Any]] | None = None) -> None:
        super().__init__(f"network failure: reason={reason}, detail={detail}")
        self.reason = reason
        self.detail = detail
        self.attempts = attempts or []


@dataclass(frozen=True)
class FetchResult:
    url: str
    final_url: str
    redirects: list[dict[str, Any]]
    resolved_ip: str
    http_status: int
    headers: dict[str, str]
    body: bytes
    attempts: list[dict[str, Any]]


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(
        self,
        host: str,
        ip: str,
        *,
        port: int = 443,
        timeout: float,
        context: ssl.SSLContext,
    ) -> None:
        super().__init__(host, port=port, timeout=timeout, context=context)
        self._verified_ip = ip

    def connect(self) -> None:
        raw = socket.create_connection((self._verified_ip, self.port), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


class Resolver:
    def __init__(self, lookup: Callable[..., Any] = socket.getaddrinfo) -> None:
        self.lookup = lookup
        self.abandoned = 0

    def resolve(self, host: str, *, timeout: float, max_abandoned: int) -> list[str]:
        if self.abandoned >= max_abandoned:
            raise NetFailure(
                "resolver_exhausted",
                f"置き去りの名前解決が上限です: abandoned={self.abandoned}, max={max_abandoned}",
            )
        result_queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)

        def work() -> None:
            try:
                value = self.lookup(host, 443, type=socket.SOCK_STREAM)
                result_queue.put_nowait(("ok", value))
            except Exception as exc:  # result is transferred to the caller
                result_queue.put_nowait(("error", exc))

        thread = threading.Thread(target=work, daemon=True, name=f"article-pipeline-dns-{host}")
        thread.start()
        thread.join(timeout)
        if thread.is_alive():
            self.abandoned += 1
            raise NetFailure("dns_timeout", f"名前解決が時間内に戻りません: host={host}, timeout={timeout}")
        status, value = result_queue.get_nowait()
        if status == "error":
            raise NetFailure("dns_error", f"名前解決に失敗しました: host={host}, error={value}")
        addresses: list[str] = []
        for item in value:
            address = item[4][0]
            if address not in addresses:
                addresses.append(address)
        if not addresses:
            raise NetFailure("dns_error", f"名前解決結果が空です: host={host}")
        return addresses


ConnectionFactory = Callable[[str, str, int, float, ssl.SSLContext], Any]
PolicyCheck = Callable[[str, list[str]], str | None]


def default_connection_factory(
    host: str,
    ip: str,
    port: int,
    timeout: float,
    context: ssl.SSLContext,
) -> PinnedHTTPSConnection:
    return PinnedHTTPSConnection(host, ip, port=port, timeout=timeout, context=context)


class NetworkClient:
    def __init__(
        self,
        config: dict[str, Any],
        *,
        resolver: Resolver | None = None,
        connection_factory: ConnectionFactory = default_connection_factory,
        ssl_context: ssl.SSLContext | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.resolver = resolver or Resolver()
        self.connection_factory = connection_factory
        self.ssl_context = ssl_context or ssl.create_default_context()
        self.monotonic = monotonic
        self.sleep = sleep
        self._host_last_request: dict[str, float] = {}

    def fetch(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        policy_check: PolicyCheck | None = None,
        source_deadline: float | None = None,
        run_deadline: float | None = None,
    ) -> FetchResult:
        attempts: list[dict[str, Any]] = []
        source_deadline = source_deadline or self.monotonic() + self.config["source_deadline_s"]
        run_deadline = run_deadline or self.monotonic() + self.config["run_deadline_s"]
        logical_deadline = [
            min(
                self.monotonic() + self.config["request_deadline_s"],
                source_deadline,
                run_deadline,
            )
        ]
        last_result: FetchResult | None = None
        for attempt_index in range(self.config["max_retries"] + 1):
            started = self.monotonic()
            try:
                result = self._logical_request(
                    url,
                    headers=headers or {},
                    policy_check=policy_check,
                    source_deadline=source_deadline,
                    run_deadline=run_deadline,
                    logical_deadline=logical_deadline,
                )
                attempts.append(
                    {
                        "at": _utc_now(),
                        "result": "ok" if result.http_status < 500 and result.http_status != 429 else "http_error",
                        "http_status": result.http_status,
                        "elapsed_s": round(self.monotonic() - started, 6),
                        "waited_s": 0,
                    }
                )
                last_result = FetchResult(
                    result.url,
                    result.final_url,
                    result.redirects,
                    result.resolved_ip,
                    result.http_status,
                    result.headers,
                    result.body,
                    list(attempts),
                )
                if result.http_status != 429 and result.http_status < 500:
                    return last_result
                if attempt_index >= self.config["max_retries"]:
                    return last_result
                wait = self._retry_wait(result.headers, attempt_index)
            except NetFailure as exc:
                attempts.append(
                    {
                        "at": _utc_now(),
                        "result": "error",
                        "error": exc.reason,
                        "detail": exc.detail,
                        "elapsed_s": round(self.monotonic() - started, 6),
                        "waited_s": 0,
                    }
                )
                if exc.reason in {
                    "scheme_not_allowed", "host_not_allowed", "self_source",
                    "comparison_excluded", "non_public_address", "too_many_redirects",
                    "too_large", "unsupported_encoding", "resolver_exhausted",
                    "rate_limited",
                } or attempt_index >= self.config["max_retries"]:
                    exc.attempts = attempts
                    raise
                wait = self.config["retry_backoff_s"][attempt_index]
            remaining = min(source_deadline, run_deadline) - self.monotonic()
            if wait > remaining:
                raise NetFailure(
                    "source_deadline_exceeded",
                    f"再試行の待ち時間が残り時間を超えます: wait={wait}, remaining={remaining}",
                    attempts=attempts,
                )
            attempts[-1]["waited_s"] = wait
            self.sleep(wait)
            # Retry waits count toward source/run limits, but not the logical
            # request limit (§18.5.9).
            logical_deadline[0] = min(
                logical_deadline[0] + wait,
                source_deadline,
                run_deadline,
            )
        if last_result is None:
            raise NetFailure("request_failed", "応答を得られませんでした", attempts=attempts)
        return last_result

    def _retry_wait(self, headers: dict[str, str], attempt_index: int) -> float:
        retry_after = headers.get("retry-after")
        if retry_after is not None:
            try:
                seconds = float(retry_after)
            except ValueError:
                raise NetFailure("rate_limited", f"Retry-After が秒数ではありません: value={retry_after!r}")
            if seconds > self.config["retry_after_max_s"]:
                raise NetFailure(
                    "rate_limited",
                    f"Retry-After が待機上限を超えています: value={seconds}, max={self.config['retry_after_max_s']}",
                )
            return seconds
        return float(self.config["retry_backoff_s"][attempt_index])

    def _logical_request(
        self,
        url: str,
        *,
        headers: dict[str, str],
        policy_check: PolicyCheck | None,
        source_deadline: float,
        run_deadline: float,
        logical_deadline: list[float],
    ) -> FetchResult:
        current = url
        redirects: list[dict[str, Any]] = []
        for redirect_index in range(self.config["max_redirects"] + 1):
            remaining = logical_deadline[0] - self.monotonic()
            if remaining <= 0:
                raise NetFailure("request_deadline_exceeded", f"論理要求の時間上限を超えました: url={url}")
            try:
                parsed = urlsplit(current)
                parsed_port = parsed.port
            except ValueError as exc:
                raise NetFailure("scheme_not_allowed", f"転送先 URL を解析できません: url={current}, error={exc}") from exc
            if (
                parsed.scheme != "https"
                or parsed_port not in (None, 443)
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
            ):
                raise NetFailure("scheme_not_allowed", f"転送先が https:443 ではありません: url={current}")
            host = parsed.hostname.lower()
            pace_wait = self._pace(host, min(source_deadline, run_deadline))
            logical_deadline[0] = min(
                logical_deadline[0] + pace_wait,
                source_deadline,
                run_deadline,
            )
            dns_timeout = min(self.config["dns_timeout_s"], logical_deadline[0] - self.monotonic())
            if dns_timeout <= 0:
                raise NetFailure("request_deadline_exceeded", f"名前解決前に上限を超えました: url={current}")
            addresses = self.resolver.resolve(
                host,
                timeout=dns_timeout,
                max_abandoned=self.config["max_abandoned_resolvers"],
            )
            if not all_addresses_public(addresses):
                raise NetFailure("non_public_address", f"公開アドレス以外を含みます: host={host}, addresses={addresses}")
            if policy_check is not None:
                reason = policy_check(current, addresses)
                if reason is not None:
                    raise NetFailure(reason, f"取得方針により拒否されました: url={current}")
            ip = addresses[0]
            timeout = min(self.config["connect_timeout_s"], logical_deadline[0] - self.monotonic())
            if timeout <= 0:
                raise NetFailure("request_deadline_exceeded", f"接続前に上限を超えました: url={current}")
            connection = self.connection_factory(host, ip, 443, timeout, self.ssl_context)
            request_headers = {
                "User-Agent": self.config["user_agent"],
                "Accept-Encoding": "gzip, identity",
                "Connection": "close",
                **headers,
            }
            if host != "api.github.com":
                request_headers.pop("Authorization", None)
            try:
                connection.connect()
                remaining = logical_deadline[0] - self.monotonic()
                if remaining <= 0:
                    raise NetFailure("request_deadline_exceeded", f"接続中に論理要求の上限を超えました: url={current}")
                if getattr(connection, "sock", None) is not None:
                    connection.sock.settimeout(min(self.config["read_timeout_s"], remaining))
            except NetFailure:
                raise
            except (socket.timeout, TimeoutError) as exc:
                reason = "request_deadline_exceeded" if self.monotonic() >= logical_deadline[0] else "connect_timeout"
                raise NetFailure(reason, f"接続がタイムアウトしました: url={current}, ip={ip}, error={exc}") from exc
            except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
                raise NetFailure("connect_error", f"HTTPS 接続に失敗しました: url={current}, ip={ip}, error={exc}") from exc
            try:
                target = parsed.path or "/"
                if parsed.query:
                    target += "?" + parsed.query
                connection.request("GET", target, headers=request_headers)
                response = connection.getresponse()
                response_headers = _saved_headers(response.headers)
                status = int(response.status)
                if status in REDIRECT_STATUSES:
                    location = response_headers.get("location")
                    if not location:
                        raise NetFailure("redirect_without_location", f"Location のない転送です: url={current}, status={status}")
                    if redirect_index >= self.config["max_redirects"]:
                        raise NetFailure("too_many_redirects", f"転送回数が上限を超えました: url={url}")
                    next_url = urljoin(current, location)
                    redirects.append({"from": current, "to": next_url, "status": status})
                    current = next_url
                    continue
                body = self._read_body(response, response_headers, logical_deadline[0])
                if self.monotonic() > logical_deadline[0]:
                    raise NetFailure("request_deadline_exceeded", f"応答処理中に論理要求の上限を超えました: url={current}")
                return FetchResult(url, current, redirects, ip, status, response_headers, body, [])
            except NetFailure:
                raise
            except (socket.timeout, TimeoutError) as exc:
                reason = "request_deadline_exceeded" if self.monotonic() >= logical_deadline[0] else "read_timeout"
                raise NetFailure(reason, f"通信がタイムアウトしました: url={current}, error={exc}") from exc
            except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
                raise NetFailure("connect_error", f"HTTPS 通信に失敗しました: url={current}, ip={ip}, error={exc}") from exc
            finally:
                connection.close()
        raise NetFailure("too_many_redirects", f"転送回数が上限を超えました: url={url}")

    def _read_body(self, response: Any, headers: dict[str, str], deadline: float) -> bytes:
        length = headers.get("content-length")
        if length is not None:
            try:
                declared = int(length)
            except ValueError as exc:
                raise NetFailure("invalid_content_length", f"Content-Length が整数ではありません: value={length!r}") from exc
            if declared > self.config["max_body_bytes"]:
                raise NetFailure("too_large", f"Content-Length が上限を超えています: value={declared}, max={self.config['max_body_bytes']}")
        chunks: list[bytes] = []
        received = 0
        while True:
            remaining = deadline - self.monotonic()
            if remaining <= 0:
                raise NetFailure("request_deadline_exceeded", "本文受信中に論理要求の上限を超えました")
            if getattr(response, "fp", None) is not None and getattr(response.fp, "raw", None) is not None:
                sock = getattr(response.fp.raw, "_sock", None)
                if sock is not None:
                    sock.settimeout(min(self.config["read_timeout_s"], remaining))
            chunk = response.read(65536)
            if not chunk:
                break
            received += len(chunk)
            if received > self.config["max_body_bytes"]:
                raise NetFailure("too_large", f"受信本文が上限を超えました: received={received}, max={self.config['max_body_bytes']}")
            chunks.append(chunk)
        encoded = b"".join(chunks)
        encoding = headers.get("content-encoding", "identity").lower().strip()
        if encoding in {"", "identity"}:
            return encoded
        if encoding != "gzip":
            raise NetFailure("unsupported_encoding", f"Content-Encoding が未対応です: value={encoding!r}")
        try:
            decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
            output = decompressor.decompress(encoded, self.config["max_body_bytes"] + 1)
            if len(output) > self.config["max_body_bytes"] or decompressor.unconsumed_tail:
                raise NetFailure("too_large", f"gzip 展開後の本文が上限を超えました: max={self.config['max_body_bytes']}")
            output += decompressor.flush(self.config["max_body_bytes"] + 1 - len(output))
        except NetFailure:
            raise
        except (zlib.error, ValueError) as exc:
            raise NetFailure("decode_gzip_error", f"gzip を展開できません: error={exc}") from exc
        if len(output) > self.config["max_body_bytes"] or decompressor.unconsumed_tail:
            raise NetFailure("too_large", f"gzip 展開後の本文が上限を超えました: max={self.config['max_body_bytes']}")
        return output

    def _pace(self, host: str, deadline: float) -> float:
        now = self.monotonic()
        last = self._host_last_request.get(host)
        waited = 0.0
        if last is not None:
            wait = self.config["per_host_interval_s"] - (now - last)
            if wait > 0:
                if now + wait > deadline:
                    raise NetFailure("source_deadline_exceeded", f"ホスト間隔の待機が残り時間を超えます: host={host}, wait={wait}")
                self.sleep(wait)
                waited = wait
        self._host_last_request[host] = self.monotonic()
        return waited


def _saved_headers(headers: Message | Any) -> dict[str, str]:
    return {
        key.lower(): value
        for key, value in headers.items()
        if key.lower() in SAVED_HEADERS
    }


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
