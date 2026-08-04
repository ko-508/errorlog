import unittest
from contextlib import redirect_stdout
from io import StringIO

from scripts.article_og_image import split_title
from scripts.publish_article import ensure_article_og_image_param, parse_frontmatter_for_x_post, print_x_post_fields


class PublishArticleXPostTest(unittest.TestCase):
    def test_parse_frontmatter_for_x_post_reads_title_and_tags(self) -> None:
        text = """---
title: "AWS S3 の AccessDenied エラー：原因と解決策"
date: 2026-08-04
tags: ["AWS S3", "AccessDenied"]
service: "AWS S3"
---

body
"""

        title, tags, service = parse_frontmatter_for_x_post(text)

        self.assertEqual(title, "AWS S3 の AccessDenied エラー：原因と解決策")
        self.assertEqual(tags, ["AWS S3", "AccessDenied"])
        self.assertEqual(service, "AWS S3")

    def test_ensure_article_og_image_param_inserts_after_tags(self) -> None:
        text = """---
title: "OpenAI API の 429 エラー：原因と解決策"
tags: ["OpenAI API"]
service: "OpenAI API"
---

body
"""

        updated = ensure_article_og_image_param(text, "og/posts/openai_api_429.png")

        self.assertIn('tags: ["OpenAI API"]\nimages: ["og/posts/openai_api_429.png"]\nservice:', updated)

    def test_split_title_breaks_before_reason_and_solution(self) -> None:
        self.assertEqual(
            split_title("OpenAI API の 429 エラー：原因と解決策"),
            ["OpenAI API の 429 エラー：", "原因と解決策"],
        )

    def test_print_x_post_fields_outputs_copyable_title_and_url_only(self) -> None:
        out = StringIO()

        with redirect_stdout(out):
            print_x_post_fields("openai_api_429", "OpenAI API の 429 エラー：原因と解決策")

        self.assertEqual(
            out.getvalue(),
            "\nX 投稿用\n"
            "OpenAI API の 429 エラー：原因と解決策\n"
            "https://errorlog.jp/posts/openai_api_429/?utm_source=x&utm_medium=social&utm_campaign=article_share\n",
        )


if __name__ == "__main__":
    unittest.main()
