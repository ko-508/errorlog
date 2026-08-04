import unittest

from scripts.publish_article import make_hashtags, parse_frontmatter_for_x_post


class PublishArticleXPostTest(unittest.TestCase):
    def test_parse_frontmatter_for_x_post_reads_title_and_tags(self) -> None:
        text = """---
title: "AWS S3 の AccessDenied エラー：原因と解決策"
date: 2026-08-04
tags: ["AWS S3", "AccessDenied"]
---

body
"""

        title, tags = parse_frontmatter_for_x_post(text)

        self.assertEqual(title, "AWS S3 の AccessDenied エラー：原因と解決策")
        self.assertEqual(tags, ["AWS S3", "AccessDenied"])

    def test_make_hashtags_removes_x_unsupported_separators(self) -> None:
        self.assertEqual(make_hashtags(["AWS S3", "tool-guide", "Nginx"]), "#AWSS3 #toolguide #Nginx")


if __name__ == "__main__":
    unittest.main()
