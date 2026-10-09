import unittest
from contextlib import redirect_stdout
from io import StringIO

from scripts.article_og_image import split_title
from scripts.publish_article import (
    ensure_article_og_image_param,
    parse_frontmatter_for_x_post,
    print_publish_followup,
    print_x_post_fields,
    unexpected_dirty_files,
)


class PublishArticleXPostTest(unittest.TestCase):
    def test_target_article_og_image_is_allowed_dirty_file(self) -> None:
        article = "content/posts/npm_eresolve.md"
        target_og = "static/og/posts/npm_eresolve.png"

        unexpected = unexpected_dirty_files({article, target_og}, article, target_og)

        self.assertEqual(unexpected, set())

    def test_other_article_og_image_remains_unexpected(self) -> None:
        article = "content/posts/npm_eresolve.md"
        target_og = "static/og/posts/npm_eresolve.png"
        other_og = "static/og/posts/npm_e404.png"

        unexpected = unexpected_dirty_files(
            {article, target_og, other_og}, article, target_og
        )

        self.assertEqual(unexpected, {other_og})

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

    def test_print_publish_followup_outputs_article_and_search_console_urls(self) -> None:
        out = StringIO()

        with redirect_stdout(out):
            print_publish_followup("openai_api_429")

        self.assertEqual(
            out.getvalue(),
            "\n公開後の確認\n"
            "状態: push完了（本番への公開完了は未確認）\n"
            "記事URL: https://errorlog.jp/posts/openai_api_429/\n"
            "Search Console: https://search.google.com/search-console?resource_id=https%3A%2F%2Ferrorlog.jp%2F\n"
            "本番で記事が表示されることを確認してください。\n"
            "公開完了後、URL検査欄に記事URLを貼り付けて、インデックス登録をリクエストしてください。\n",
        )


if __name__ == "__main__":
    unittest.main()
