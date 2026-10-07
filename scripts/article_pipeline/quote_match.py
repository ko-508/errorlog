"""Deterministic quote normalization and source line matching."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def _normalized_with_offsets(value: str) -> tuple[str, list[int]]:
    output: list[str] = []
    offsets: list[int] = []
    in_space = False
    for offset, original in enumerate(value):
        for char in unicodedata.normalize("NFKC", original):
            if char.isspace():
                if output and not in_space:
                    output.append(" ")
                    offsets.append(offset)
                in_space = True
            else:
                output.append(char)
                offsets.append(offset)
                in_space = False
    if output and output[-1] == " ":
        output.pop()
        offsets.pop()
    return "".join(output), offsets


def match_quote(quote: str, source: dict[str, Any], text: str) -> dict[str, Any]:
    if source.get("status") not in {"fetched", "reused"}:
        return {"result": "invalid_source", "method": "normalized_substring", "locations": [], "permalink": None}
    needle = normalize_text(quote)
    if not needle:
        return {"result": "unmatched", "method": "normalized_substring", "locations": [], "permalink": None}
    normalized, offsets = _normalized_with_offsets(text)
    locations: list[dict[str, int]] = []
    cursor = 0
    while True:
        found = normalized.find(needle, cursor)
        if found < 0:
            break
        start_offset = offsets[found]
        end_offset = offsets[found + len(needle) - 1]
        locations.append({
            "line_start": text.count("\n", 0, start_offset) + 1,
            "line_end": text.count("\n", 0, end_offset) + 1,
        })
        cursor = found + 1
    permalink = None
    github = source.get("github")
    if locations and isinstance(github, dict) and github.get("line_anchor") == "supported":
        first = locations[0]
        suffix = f"#L{first['line_start']}"
        if first["line_end"] != first["line_start"]:
            suffix += f"-L{first['line_end']}"
        permalink = str(github["permalink"]) + suffix
    return {
        "result": "matched" if locations else "unmatched",
        "method": "normalized_substring",
        "locations": locations,
        "permalink": permalink,
    }


def match_evidence(
    evidence: dict[str, Any], sources: dict[str, dict[str, Any]], texts: dict[str, str]
) -> dict[str, Any]:
    source_id = evidence.get("source_id")
    source = sources.get(source_id)
    if source is None:
        result = {"result": "invalid_source", "method": "normalized_substring", "locations": [], "permalink": None}
    else:
        result = match_quote(str(evidence.get("quote", "")), source, texts.get(source_id, ""))
    return {**evidence, "quote_match": result}
