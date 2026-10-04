from __future__ import annotations

from scripts.article_pipeline.robots import ROBOTS_MAX_BYTES, allowed, parse_robots


def test_rfc9309_longest_match_allow_tie_wildcard_and_end_anchor() -> None:
    rules = parse_robots(
        b"""
User-agent: *
Disallow: /fish
Allow: /fish$
Allow: /fish/heads
Disallow: /*.php$
"""
    )
    assert allowed(rules, "/fish") is True
    assert allowed(rules, "/fish/heads") is True
    assert allowed(rules, "/fish/tails") is False
    assert allowed(rules, "/index.php") is False
    assert allowed(rules, "/index.php?q=1") is True
    assert allowed(rules, "/index.php/next") is True


def test_specific_user_agent_group_wins_and_input_is_limited() -> None:
    prefix = b"User-agent: errorlog-article-pipeline\nAllow: /ok\nDisallow: /\n"
    body = prefix + b"#" * (ROBOTS_MAX_BYTES - len(prefix)) + b"\nAllow: /late\n"
    rules = parse_robots(body)
    assert allowed(rules, "/ok") is True
    assert allowed(rules, "/late") is False


def test_html_robots_has_no_rules() -> None:
    assert parse_robots(b"<html><body>User-agent *</body></html>") == []
