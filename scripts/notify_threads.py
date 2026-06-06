"""Make Webhook へ新規公開記事を通知する（Threads 拡散用）"""
import os
import re
import sys
import subprocess
import json
import requests


def get_new_articles():
    result = subprocess.run(
        ["git", "diff", "HEAD~1", "HEAD", "--name-only", "--diff-filter=A", "content/posts/"],
        capture_output=True,
        text=True,
    )
    return [f for f in result.stdout.strip().splitlines() if f.endswith(".md")]


def parse_frontmatter_title(path):
    with open(path, encoding="utf-8") as f:
        content = f.read()
    m = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE)
    return m.group(1).strip('"\'') if m else "新しい記事"


def main():
    webhook_url = os.environ.get("MAKE_WEBHOOK_URL")
    if not webhook_url:
        print("MAKE_WEBHOOK_URL not set, skipping")
        sys.exit(0)

    new_files = get_new_articles()
    if not new_files:
        print("No new articles, skipping")
        sys.exit(0)

    articles = []
    for path in new_files:
        try:
            title = parse_frontmatter_title(path)
            slug = os.path.basename(path).replace(".md", "")
            url = f"https://errorlog.jp/posts/{slug}/"
            articles.append({"title": title, "url": url})
            print(f"  - {title}")
        except Exception as e:
            print(f"Error processing {path}: {e}")

    if not articles:
        sys.exit(0)

    for article in articles:
        resp = requests.post(webhook_url, json=article, timeout=10)
        print(f"Make webhook: {resp.status_code} - {article['title']}")
        if not resp.ok:
            print(resp.text)


if __name__ == "__main__":
    main()
