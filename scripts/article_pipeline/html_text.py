"""Deterministic HTML-to-text extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any


EXTRACTOR_VERSION = 1
DROP_TAGS = {
    "script", "style", "noscript", "template", "svg", "iframe", "object",
    "embed", "form", "nav", "header", "footer", "aside",
}
BLOCK_TAGS = {
    "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
    "dt", "dd", "blockquote", "section", "pre",
}


@dataclass
class Node:
    tag: str
    attrs: dict[str, str | None]
    children: list["Node | str"] = field(default_factory=list)


class TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document", {})
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag.lower(), {key.lower(): value for key, value in attrs})
        self.stack[-1].children.append(node)
        if tag.lower() not in {"br", "meta", "link", "img", "input", "hr", "source", "wbr"}:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self.stack[-1].tag == tag.lower():
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == lowered:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def _walk(node: Node):
    yield node
    for child in node.children:
        if isinstance(child, Node):
            yield from _walk(child)


def _hidden(node: Node) -> bool:
    attrs = node.attrs
    if "hidden" in attrs or (attrs.get("aria-hidden") or "").lower() == "true":
        return True
    style = re.sub(r"\s+", "", (attrs.get("style") or "").lower())
    return "display:none" in style or "visibility:hidden" in style


def _raw_chars(node: Node) -> int:
    return sum(len(child) if isinstance(child, str) else _raw_chars(child) for child in node.children)


def _choose_root(root: Node) -> tuple[Node, str]:
    candidates = list(_walk(root))
    for label, predicate in (
        ("main", lambda node: node.tag == "main"),
        ("article", lambda node: node.tag == "article"),
        ("role_main", lambda node: (node.attrs.get("role") or "").lower() == "main"),
    ):
        found = [node for node in candidates if predicate(node)]
        if len(found) == 1:
            return found[0], label
    bodies = [node for node in candidates if node.tag == "body"]
    return (bodies[0], "body") if bodies else (root, "document")


def extract_html_text(html: str) -> tuple[str, dict[str, Any]]:
    parser = TreeParser()
    parser.feed(html)
    parser.close()
    selected, root_name = _choose_root(parser.root)
    pieces: list[str] = []
    preserved: dict[str, str] = {}
    dropped_hidden = 0

    def preserve_pre(node: Node) -> str:
        nonlocal dropped_hidden
        output: list[str] = []
        for child in node.children:
            if isinstance(child, str):
                output.append(child)
            elif child.tag in DROP_TAGS:
                continue
            elif _hidden(child):
                dropped_hidden += _raw_chars(child)
            else:
                output.append(preserve_pre(child))
        return "".join(output)

    def emit(node: Node, *, pre: bool = False) -> None:
        nonlocal dropped_hidden
        if node.tag in DROP_TAGS:
            return
        if _hidden(node):
            dropped_hidden += _raw_chars(node)
            return
        if node.tag == "pre":
            token_number = len(preserved)
            token = f"\x00ARTICLE_PIPELINE_PRE_{token_number}\x00"
            while token in html:
                token_number += 1
                token = f"\x00ARTICLE_PIPELINE_PRE_{token_number}\x00"
            preserved[token] = preserve_pre(node)
            pieces.extend(("\n", token, "\n"))
            return
        current_pre = pre or node.tag == "pre"
        if node.tag in BLOCK_TAGS:
            pieces.append("\n")
            if node.tag.startswith("h") and len(node.tag) == 2 and node.tag[1].isdigit():
                pieces.append("#" * int(node.tag[1]) + " ")
            elif node.tag == "li":
                pieces.append("- ")
        elif node.tag in {"td", "th"} and pieces:
            pieces.append(" | ")
        elif node.tag == "br":
            pieces.append("\n")
        for child in node.children:
            if isinstance(child, str):
                pieces.append(child if current_pre else re.sub(r"\s+", " ", child))
            else:
                emit(child, pre=current_pre)
        if node.tag in BLOCK_TAGS:
            pieces.append("\n")

    emit(selected)
    text = "".join(pieces)
    lines = [line.rstrip() for line in text.splitlines()]
    normalized: list[str] = []
    blank_count = 0
    for line in lines:
        if line:
            blank_count = 0
            normalized.append(line.strip() if not line.startswith(" ") else line.rstrip())
        else:
            blank_count += 1
            if blank_count <= 2:
                normalized.append("")
    text = "\n".join(normalized).strip() + "\n"
    for token, raw in preserved.items():
        text = text.replace(token, raw)
    outline = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if match:
            outline.append({"level": len(match.group(1)), "text": match.group(2), "line": line_number})
    return text, {"root": root_name, "dropped_hidden_chars": dropped_hidden, "outline": outline}
