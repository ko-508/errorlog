from __future__ import annotations

from scripts.article_pipeline.decode import decode_body


def test_13_charset_precedence_cp932_and_errors() -> None:
    bom = decode_body(b"\xef\xbb\xbfOK", content_type="text/plain; charset=cp932", is_html=False)
    assert (bom.text, bom.charset, bom.decided_by) == ("OK", "utf-8", "bom")
    header = decode_body("日本語".encode("cp932"), content_type="text/plain; charset=shift_jis", is_html=False)
    assert header.text == "日本語"
    meta = decode_body(b'<meta charset="utf-8">hello', content_type="text/html", is_html=True)
    assert meta.text and "hello" in meta.text
    bad = decode_body(b"\xff", content_type="text/plain; charset=utf-8", is_html=False)
    assert bad.reason == "decode_error" and bad.error_position == 0
    unknown = decode_body(b"x", content_type="text/plain; charset=x-unknown", is_html=False)
    assert unknown.reason == "charset_label_unknown"
    assert "�" not in (bad.text or "")
