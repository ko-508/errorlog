from __future__ import annotations

import pytest

from scripts.article_pipeline import PipelineError
from scripts.article_pipeline.urlpolicy import (
    address_is_public,
    all_addresses_public,
    candidate_key,
    normalize_https_url,
    static_policy_reason,
)


CONFIG = {
    "allowed_hosts": [
        {"host": "docs.python.org", "include_subdomains": False},
        {"host": "api.github.com", "include_subdomains": False},
    ],
    "comparison_denied_hosts": ["zenn.dev", "qiita.com"],
    "self_hosts": ["errorlog.jp"],
    "self_repos": ["ko-508/errorlog", "ko-508/zenn-content"],
}


@pytest.mark.parametrize(
    ("candidate", "url", "mode", "reason"),
    [
        ({"kind": "url"}, "https://not-allowed.example/x", "candidate", "host_not_allowed"),
        ({"kind": "url"}, "https://errorlog.jp/x", "candidate", "self_source"),
        ({"kind": "github_file", "repo": "ko-508/errorlog"}, "https://api.github.com/x", "candidate", "self_source"),
        ({"kind": "url"}, "https://zenn.dev/x", "comparison", "comparison_excluded"),
        ({"kind": "url"}, "https://qiita.com/x", "comparison", "comparison_excluded"),
        ({"kind": "url"}, "https://zenn.dev/x", "candidate", "host_not_allowed"),
    ],
)
def test_06_policy_reasons(candidate, url, mode, reason) -> None:
    assert static_policy_reason(candidate=candidate, url=url, config=CONFIG, mode=mode) == reason


@pytest.mark.parametrize(
    "address",
    ["10.0.0.1", "127.0.0.1", "169.254.1.1", "100.64.0.1", "fc00::1", "::ffff:192.0.2.1"],
)
def test_07_non_public_addresses_are_rejected(address: str) -> None:
    assert not address_is_public(address)
    assert not all_addresses_public(["8.8.8.8", address])


def test_38_candidate_key_excludes_role_anchor_and_includes_ref() -> None:
    base = {"kind": "github_file", "repo": "a/b", "path": "x", "ref": "main"}
    one = {**base, "role_hint": "case", "anchor": "L1", "origins": ["a"]}
    two = {**base, "role_hint": "official_doc", "anchor": "L9", "origins": ["b"]}
    changed = {**base, "ref": "v2"}
    assert candidate_key(one) == candidate_key(two)
    assert candidate_key(one) != candidate_key(changed)


def test_normalize_url_idna_fragment_and_port() -> None:
    url, anchor = normalize_https_url("HTTPS://例え.jp:443/a#part")
    assert url == "https://xn--r8jz45g.jp/a"
    assert anchor == "part"
    encoded, _anchor = normalize_https_url("https://example.com/a%2Fb")
    assert encoded == "https://example.com/a%2Fb"
    with pytest.raises(PipelineError, match="ポート"):
        normalize_https_url("https://example.com:444/a")
