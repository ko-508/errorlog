"""Small RFC 9309 robots.txt parser with longest-match semantics."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from . import PipelineError


ROBOTS_MAX_BYTES = 500 * 1024


@dataclass(frozen=True)
class Rule:
    allow: bool
    pattern: str

    def match_length(self, path: str) -> int | None:
        escaped = re.escape(self.pattern).replace(r"\*", ".*")
        anchored = escaped.endswith(r"\$")
        if anchored:
            escaped = escaped[:-2] + "$"
        match = re.match(escaped, path)
        if match is None:
            return None
        return len(self.pattern.replace("*", "").removesuffix("$"))


def parse_robots(body: bytes, *, user_agent: str = "errorlog-article-pipeline") -> list[Rule]:
    try:
        text = body[:ROBOTS_MAX_BYTES].decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise PipelineError(
            f"robots.txt が UTF-8 ではありません: position={exc.start}"
        ) from exc
    groups: list[tuple[list[str], list[Rule]]] = []
    agents: list[str] = []
    rules: list[Rule] = []
    seen_rule = False
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if seen_rule:
                groups.append((agents, rules))
                agents, rules, seen_rule = [], [], False
            agents.append(value.lower())
        elif key in {"allow", "disallow"} and agents:
            seen_rule = True
            if value or key == "allow":
                rules.append(Rule(key == "allow", value))
    if agents:
        groups.append((agents, rules))
    exact = [rule for agent_list, group_rules in groups if user_agent.lower() in agent_list for rule in group_rules]
    if exact:
        return exact
    return [rule for agent_list, group_rules in groups if "*" in agent_list for rule in group_rules]


def allowed(rules: list[Rule], url_or_path: str) -> bool:
    if "://" in url_or_path:
        parsed = urlsplit(url_or_path)
        path = parsed.path + (("?" + parsed.query) if parsed.query else "")
    else:
        path = url_or_path
    path = path or "/"
    matches = [(length, rule.allow) for rule in rules if (length := rule.match_length(path)) is not None]
    if not matches:
        return True
    longest = max(length for length, _allow in matches)
    return any(allow for length, allow in matches if length == longest)
