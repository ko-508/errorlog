"""Strict charset detection and decoding for acquired sources."""

from __future__ import annotations

import codecs
import re
from dataclasses import dataclass


CHARSET_ALIASES = {
    "utf-8": "utf-8",
    "utf8": "utf-8",
    "utf-16": "utf-16",
    "utf-16le": "utf-16-le",
    "utf-16-le": "utf-16-le",
    "utf-16be": "utf-16-be",
    "utf-16-be": "utf-16-be",
    "shift_jis": "cp932",
    "shift-jis": "cp932",
    "sjis": "cp932",
    "x-sjis": "cp932",
    "cp932": "cp932",
    "windows-31j": "cp932",
    "iso-8859-1": "windows-1252",
    "latin1": "windows-1252",
    "latin-1": "windows-1252",
    "windows-1252": "windows-1252",
    "cp1252": "windows-1252",
    "euc-jp": "euc-jp",
    "euc_jp": "euc-jp",
}
HEADER_CHARSET_RE = re.compile(r"charset\s*=\s*[\"']?([^;\s\"']+)", re.I)
META_CHARSET_RE = re.compile(rb"<meta\b[^>]*\bcharset\s*=\s*[\"']?([^\s\"'/>;]+)", re.I)
META_HTTP_EQUIV_RE = re.compile(
    rb"<meta\b(?=[^>]*\bhttp-equiv\s*=\s*[\"']?content-type[\"']?)(?=[^>]*\bcontent\s*=\s*[\"'][^\"']*charset\s*=\s*([^;\s\"']+))[^>]*>",
    re.I,
)


@dataclass(frozen=True)
class DecodeResult:
    text: str | None
    charset: str | None
    decided_by: str | None
    bom: bool
    reason: str | None = None
    error_position: int | None = None


def normalize_charset(label: str) -> str | None:
    return CHARSET_ALIASES.get(label.strip().lower())


def _header_charset(content_type: str) -> str | None:
    match = HEADER_CHARSET_RE.search(content_type)
    return match.group(1) if match else None


def _meta_charset(body: bytes) -> str | None:
    head = body[:1024]
    match = META_CHARSET_RE.search(head)
    if match:
        return match.group(1).decode("ascii", errors="strict")
    match = META_HTTP_EQUIV_RE.search(head)
    if match:
        return match.group(1).decode("ascii", errors="strict")
    return None


def decode_body(
    body: bytes,
    *,
    content_type: str,
    is_html: bool,
    force_utf8: bool = False,
) -> DecodeResult:
    bom = False
    label: str | None = None
    decided_by: str | None = None
    payload = body
    if body.startswith(codecs.BOM_UTF8):
        bom, label, decided_by, payload = True, "utf-8", "bom", body[len(codecs.BOM_UTF8):]
    elif body.startswith(codecs.BOM_UTF16_LE):
        bom, label, decided_by, payload = True, "utf-16-le", "bom", body[len(codecs.BOM_UTF16_LE):]
    elif body.startswith(codecs.BOM_UTF16_BE):
        bom, label, decided_by, payload = True, "utf-16-be", "bom", body[len(codecs.BOM_UTF16_BE):]
    else:
        header_label = _header_charset(content_type)
        if header_label is not None:
            label, decided_by = header_label, "http_header"
        elif is_html:
            try:
                meta_label = _meta_charset(body)
            except UnicodeDecodeError:
                return DecodeResult(None, None, None, False, "charset_label_unknown")
            if meta_label is not None:
                label, decided_by = meta_label, "html_meta"
        if label is None and force_utf8:
            label, decided_by = "utf-8", "github_raw_utf8"
    if label is None:
        return DecodeResult(None, None, None, bom, "charset_unknown")
    normalized = normalize_charset(label)
    if normalized is None:
        return DecodeResult(None, None, decided_by, bom, "charset_label_unknown")
    try:
        text = payload.decode(normalized, errors="strict")
    except UnicodeDecodeError as exc:
        return DecodeResult(None, normalized, decided_by, bom, "decode_error", exc.start)
    return DecodeResult(text, normalized, decided_by, bom)
