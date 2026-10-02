import unittest
from pathlib import Path

from scripts.mobile_publish import (
    ZERO_SHA,
    draft_from_push,
    parse_publish_metadata,
    require_single_changed_draft,
    slug_from_draft_path,
)


def article_bytes(
    *,
    publish_slug: str = '"sample-2"',
    publish_note: str = '"スマホ公開"',
    publish_zenn: str = "false",
) -> bytes:
    return (
        "---\n"
        'title: "Sample"\n'
        f"publish_slug: {publish_slug}\n"
        'tags: ["test"]\n'
        f"publish_note: {publish_note}\n"
        'service: "Test"\n'
        f"publish_zenn: {publish_zenn}\n"
        "---\n"
        "\n"
        "本文\n"
    ).encode("utf-8")


class MobilePublishMetadataTest(unittest.TestCase):
    def test_missing_publish_fields_stop(self) -> None:
        for field in ("publish_slug", "publish_note", "publish_zenn"):
            with self.subTest(field=field):
                raw = article_bytes().decode("utf-8")
                raw = "".join(
                    line for line in raw.splitlines(keepends=True)
                    if not line.startswith(f"{field}:")
                )
                with self.assertRaises(SystemExit):
                    parse_publish_metadata(raw.encode("utf-8"), "sample-2")

    def test_invalid_publish_field_types_stop(self) -> None:
        cases = (
            {"publish_slug": "sample-2"},
            {"publish_note": "123"},
            {"publish_zenn": '"false"'},
            {"publish_zenn": "yes"},
        )
        for values in cases:
            with self.subTest(values=values):
                with self.assertRaises(SystemExit):
                    parse_publish_metadata(article_bytes(**values), "sample-2")

    def test_publish_slug_mismatch_stops(self) -> None:
        with self.assertRaises(SystemExit):
            parse_publish_metadata(article_bytes(publish_slug='"different"'), "sample-2")

    def test_hyphen_number_filename_is_valid_slug(self) -> None:
        self.assertEqual(slug_from_draft_path(Path("drafts/sample-2.md")), "sample-2")

    def test_crlf_frontmatter_stops(self) -> None:
        raw = article_bytes().replace(b"\n", b"\r\n")
        with self.assertRaises(SystemExit):
            parse_publish_metadata(raw, "sample-2")

    def test_removal_preserves_every_other_byte(self) -> None:
        metadata = parse_publish_metadata(article_bytes(publish_zenn="true"), "sample-2")
        expected = (
            "---\n"
            'title: "Sample"\n'
            'tags: ["test"]\n'
            'service: "Test"\n'
            "---\n"
            "\n"
            "本文\n"
        )
        self.assertEqual(metadata.article_text.encode("utf-8"), expected.encode("utf-8"))
        self.assertEqual(metadata.note, "スマホ公開")
        self.assertTrue(metadata.zenn)


class MobilePublishDiffTest(unittest.TestCase):
    def test_zero_changed_drafts_stops(self) -> None:
        with self.assertRaises(SystemExit):
            require_single_changed_draft("")

    def test_two_changed_drafts_stop(self) -> None:
        output = "A\tdrafts/one.md\nM\tdrafts/two.md\n"
        with self.assertRaises(SystemExit):
            require_single_changed_draft(output)

    def test_single_added_draft_is_returned(self) -> None:
        self.assertEqual(
            require_single_changed_draft("A\tdrafts/sample-2.md\n"),
            Path("drafts/sample-2.md"),
        )

    def test_zero_before_sha_stops(self) -> None:
        with self.assertRaises(SystemExit):
            draft_from_push(ZERO_SHA, "1" * 40)


if __name__ == "__main__":
    unittest.main()
