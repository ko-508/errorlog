from __future__ import annotations

import gzip
import json
import socket
import ssl
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

import pytest

from scripts.article_pipeline.net import (
    FetchResult,
    NetFailure,
    NetworkClient,
    PinnedHTTPSConnection,
    Resolver,
)
from tests.article_pipeline_helpers import CONFIG


def net_config(**updates):
    value = json.loads(CONFIG)["acquire"]
    value.update(
        {
            "per_host_interval_s": 0,
            "max_retries": 0,
            "retry_backoff_s": [],
            **updates,
        }
    )
    return value


class FixedResolver:
    def __init__(self, addresses=("93.184.216.34",)):
        self.addresses = list(addresses)
        self.calls = []

    def resolve(self, host, *, timeout, max_abandoned):
        self.calls.append((host, timeout, max_abandoned))
        return list(self.addresses)


class FakeResponse:
    def __init__(self, status=200, headers=None, chunks=(b"ok",)):
        self.status = status
        self.headers = headers or {"Content-Type": "text/plain; charset=utf-8"}
        self.chunks = deque(chunks)
        self.read_calls = 0
        self.fp = None

    def read(self, _size):
        self.read_calls += 1
        return self.chunks.popleft() if self.chunks else b""


class FakeConnection:
    def __init__(self, response, *, connect_delay=0, request_delay=0, response_delay=0, connect_error=None):
        self.response = response
        self.connect_delay = connect_delay
        self.connect_error = connect_error
        self.request_delay = request_delay
        self.response_delay = response_delay
        self.request_args = None
        self.closed = False
        self.sock = None

    def connect(self):
        time.sleep(self.connect_delay)
        if self.connect_error is not None:
            raise self.connect_error

    def request(self, *args, **kwargs):
        time.sleep(self.request_delay)
        self.request_args = (args, kwargs)

    def getresponse(self):
        time.sleep(self.response_delay)
        return self.response

    def close(self):
        self.closed = True


class ConnectionQueue:
    def __init__(self, responses):
        self.responses = deque(responses)
        self.calls = []

    def __call__(self, host, ip, port, timeout, context):
        self.calls.append((host, ip, port, timeout))
        value = self.responses.popleft()
        return value if isinstance(value, FakeConnection) else FakeConnection(value)


def test_pins_verified_address_and_resolves_once_per_redirect() -> None:
    resolver = FixedResolver()
    factory = ConnectionQueue(
        [
            FakeResponse(302, {"Location": "https://example.com/next"}, ()),
            FakeResponse(200, {"Content-Type": "text/plain", "Content-Length": "2"}, (b"ok",)),
        ]
    )
    client = NetworkClient(net_config(), resolver=resolver, connection_factory=factory)
    result = client.fetch("https://example.com/start")
    assert result.body == b"ok"
    assert result.redirects == [
        {"from": "https://example.com/start", "to": "https://example.com/next", "status": 302}
    ]
    assert len(resolver.calls) == 2
    assert [call[1] for call in factory.calls] == ["93.184.216.34", "93.184.216.34"]


def test_github_authorization_is_removed_on_cross_host_redirect() -> None:
    first = FakeConnection(
        FakeResponse(302, {"Location": "https://example.com/final"}, ())
    )
    second = FakeConnection(FakeResponse(200, {}, (b"ok",)))
    client = NetworkClient(
        net_config(), resolver=FixedResolver(),
        connection_factory=ConnectionQueue([first, second]),
    )
    client.fetch(
        "https://api.github.com/start",
        headers={"Authorization": "Bearer SECRET"},
    )
    assert first.request_args[1]["headers"]["Authorization"] == "Bearer SECRET"
    assert "Authorization" not in second.request_args[1]["headers"]


@pytest.mark.parametrize(
    ("location", "reason"),
    [
        ("http://example.com/no", "scheme_not_allowed"),
        ("https://other.example/no", "host_not_allowed"),
        ("https://zenn.dev/no", "comparison_excluded"),
    ],
)
def test_redirect_policy_rejections(location, reason) -> None:
    resolver = FixedResolver()
    factory = ConnectionQueue([FakeResponse(302, {"Location": location}, ())])

    def policy(url, _addresses):
        if "other.example" in url:
            return "host_not_allowed"
        if "zenn.dev" in url:
            return "comparison_excluded"
        return None

    client = NetworkClient(net_config(), resolver=resolver, connection_factory=factory)
    with pytest.raises(NetFailure) as caught:
        client.fetch("https://example.com/start", policy_check=policy)
    assert caught.value.reason == reason


def test_redirect_private_address_and_sixth_redirect_are_rejected() -> None:
    private = FixedResolver(("127.0.0.1",))
    client = NetworkClient(
        net_config(), resolver=private, connection_factory=ConnectionQueue([])
    )
    with pytest.raises(NetFailure, match="non_public_address") as caught:
        client.fetch("https://example.com/")
    assert caught.value.reason == "non_public_address"

    redirects = [FakeResponse(302, {"Location": f"https://example.com/{n}"}, ()) for n in range(6)]
    client = NetworkClient(
        net_config(max_redirects=5),
        resolver=FixedResolver(),
        connection_factory=ConnectionQueue(redirects),
    )
    with pytest.raises(NetFailure) as caught:
        client.fetch("https://example.com/start")
    assert caught.value.reason == "too_many_redirects"


def test_content_length_stream_and_gzip_limits() -> None:
    declared = FakeResponse(200, {"Content-Length": "4"}, (b"data",))
    client = NetworkClient(
        net_config(max_body_bytes=3), resolver=FixedResolver(),
        connection_factory=ConnectionQueue([declared]),
    )
    with pytest.raises(NetFailure) as caught:
        client.fetch("https://example.com/")
    assert caught.value.reason == "too_large"
    assert declared.read_calls == 0

    streamed = FakeResponse(200, {}, (b"ab", b"cd"))
    client = NetworkClient(
        net_config(max_body_bytes=3), resolver=FixedResolver(),
        connection_factory=ConnectionQueue([streamed]),
    )
    with pytest.raises(NetFailure) as caught:
        client.fetch("https://example.com/")
    assert caught.value.reason == "too_large"

    compressed = gzip.compress(b"x" * 100)
    zipped = FakeResponse(200, {"Content-Encoding": "gzip"}, (compressed,))
    client = NetworkClient(
        net_config(max_body_bytes=50), resolver=FixedResolver(),
        connection_factory=ConnectionQueue([zipped]),
    )
    with pytest.raises(NetFailure) as caught:
        client.fetch("https://example.com/")
    assert caught.value.reason == "too_large"


def test_retry_semantics_and_retry_after_limit() -> None:
    responses = [FakeResponse(503), FakeResponse(503), FakeResponse(200)]
    client = NetworkClient(
        net_config(max_retries=2, retry_backoff_s=[0, 0]), resolver=FixedResolver(),
        connection_factory=ConnectionQueue(responses), sleep=lambda _seconds: None,
    )
    result = client.fetch("https://example.com/")
    assert result.http_status == 200
    assert len(result.attempts) == 3

    factory = ConnectionQueue([FakeResponse(404)])
    result = NetworkClient(
        net_config(max_retries=2, retry_backoff_s=[0, 0]), resolver=FixedResolver(),
        connection_factory=factory,
    ).fetch("https://example.com/")
    assert result.http_status == 404
    assert len(factory.calls) == 1

    client = NetworkClient(
        net_config(max_retries=2, retry_backoff_s=[0, 0], retry_after_max_s=60),
        resolver=FixedResolver(),
        connection_factory=ConnectionQueue([FakeResponse(429, {"Retry-After": "120"})]),
    )
    with pytest.raises(NetFailure) as caught:
        client.fetch("https://example.com/")
    assert caught.value.reason == "rate_limited"


def test_request_deadline_and_read_timeout() -> None:
    slow = FakeConnection(FakeResponse(200, {}, (b"ok",)), request_delay=0.04)
    client = NetworkClient(
        net_config(request_deadline_s=0.02, source_deadline_s=1, run_deadline_s=1),
        resolver=FixedResolver(), connection_factory=lambda *_args: slow,
    )
    with pytest.raises(NetFailure) as caught:
        client.fetch("https://example.com/")
    assert caught.value.reason == "request_deadline_exceeded"

    class TimeoutResponse(FakeResponse):
        def read(self, _size):
            raise socket.timeout("fixed timeout")

    client = NetworkClient(
        net_config(request_deadline_s=1), resolver=FixedResolver(),
        connection_factory=ConnectionQueue([TimeoutResponse()]),
    )
    with pytest.raises(NetFailure) as caught:
        client.fetch("https://example.com/")
    assert caught.value.reason == "read_timeout"

    class TrickleResponse(FakeResponse):
        def read(self, size):
            time.sleep(0.015)
            return super().read(size)

    trickle = TrickleResponse(200, {}, (b"a", b"b", b"c"))
    client = NetworkClient(
        net_config(request_deadline_s=0.025, source_deadline_s=1, run_deadline_s=1),
        resolver=FixedResolver(), connection_factory=ConnectionQueue([trickle]),
    )
    with pytest.raises(NetFailure) as caught:
        client.fetch("https://example.com/")
    assert caught.value.reason == "request_deadline_exceeded"


def test_connect_and_header_stalls_remain_within_logical_deadline() -> None:
    connect_timeout = FakeConnection(
        FakeResponse(), connect_error=socket.timeout("connect fixed timeout")
    )
    client = NetworkClient(
        net_config(request_deadline_s=1), resolver=FixedResolver(),
        connection_factory=lambda *_args: connect_timeout,
    )
    with pytest.raises(NetFailure) as caught:
        client.fetch("https://example.com/")
    assert caught.value.reason == "connect_timeout"

    slow_header = FakeConnection(FakeResponse(), response_delay=0.04)
    client = NetworkClient(
        net_config(request_deadline_s=0.02, source_deadline_s=1, run_deadline_s=1),
        resolver=FixedResolver(), connection_factory=lambda *_args: slow_header,
    )
    started = time.monotonic()
    with pytest.raises(NetFailure) as caught:
        client.fetch("https://example.com/")
    assert caught.value.reason == "request_deadline_exceeded"
    assert time.monotonic() - started < 0.5


def test_resolver_timeout_uses_daemon_threads_and_exhausts() -> None:
    release = threading.Event()

    def never_returns(*_args, **_kwargs):
        release.wait(5)
        return []

    resolver = Resolver(never_returns)
    started = time.monotonic()
    try:
        for expected_reason in ("dns_timeout", "dns_timeout", "dns_timeout", "resolver_exhausted"):
            with pytest.raises(NetFailure) as caught:
                resolver.resolve("example.com", timeout=0.01, max_abandoned=3)
            assert caught.value.reason == expected_reason
        assert time.monotonic() - started < 0.5
        assert all(thread.daemon for thread in threading.enumerate() if thread.name.startswith("article-pipeline-dns-"))
    finally:
        release.set()


def test_abandoned_resolver_does_not_keep_child_process_alive() -> None:
    code = (
        "import time\n"
        "from scripts.article_pipeline.net import Resolver, NetFailure\n"
        "def blocked(*a, **k): time.sleep(10)\n"
        "try: Resolver(blocked).resolve('example.com', timeout=.02, max_abandoned=3)\n"
        "except NetFailure as exc: print(exc.reason)\n"
    )
    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=Path(__file__).parents[1],
        check=True, capture_output=True, text=True, timeout=2,
    )
    assert result.stdout.strip() == "dns_timeout"
    assert time.monotonic() - started < 2


def test_local_tls_uses_hostname_verification_and_pinned_connection(tmp_path) -> None:
    openssl = Path(r"C:\Program Files\Git\usr\bin\openssl.exe")
    assert openssl.is_file(), "openssl がないため未実施にはできません"
    key = tmp_path / "key.pem"
    cert = tmp_path / "cert.pem"
    subprocess.run(
        [
            str(openssl), "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(key), "-out", str(cert), "-days", "1",
            "-subj", "/CN=example.com", "-addext", "subjectAltName=DNS:example.com",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(cert, key)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    errors = []

    def serve():
        try:
            raw, _address = listener.accept()
            with server_context.wrap_socket(raw, server_side=True) as channel:
                data = b""
                while b"\r\n\r\n" not in data:
                    data += channel.recv(4096)
                channel.sendall(
                    b"HTTP/1.1 200 OK\r\nContent-Type: text/plain; charset=utf-8\r\n"
                    b"Content-Length: 2\r\nConnection: close\r\n\r\nok"
                )
        except Exception as exc:  # transferred to the test thread
            errors.append(exc)
        finally:
            listener.close()

    server = threading.Thread(target=serve, daemon=True)
    server.start()
    client_context = ssl.create_default_context(cafile=str(cert))

    def factory(host, ip, _port, timeout, context):
        assert host == "example.com"
        assert ip == "93.184.216.34"
        return PinnedHTTPSConnection(
            host, "127.0.0.1", port=port, timeout=timeout, context=context
        )

    result = NetworkClient(
        net_config(), resolver=FixedResolver(), connection_factory=factory,
        ssl_context=client_context,
    ).fetch("https://example.com/fixed")
    server.join(2)
    assert not server.is_alive()
    assert errors == []
    assert result.body == b"ok"
    assert result.resolved_ip == "93.184.216.34"
