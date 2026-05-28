"""
Hugo記事をQiita APIで投稿するスクリプト。
scripts/qiita_posted.json で投稿済み記事を管理する。

実行:
  QIITA_ACCESS_TOKEN=xxx python scripts/post_to_qiita.py
  QIITA_COUNT=10 QIITA_ACCESS_TOKEN=xxx python scripts/post_to_qiita.py
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

BASE        = Path(__file__).parent
POSTS_DIR   = BASE.parent / "content" / "posts"
POSTED_PATH = BASE / "qiita_posted.json"

QIITA_API   = "https://qiita.com/api/v2"
QIITA_COUNT = int(os.getenv("QIITA_COUNT", "3"))


def load_posted() -> dict:
    if POSTED_PATH.exists():
        return json.loads(POSTED_PATH.read_text(encoding="utf-8"))
    return {}


def save_posted(posted: dict) -> None:
    POSTED_PATH.write_text(
        json.dumps(posted, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm_text = text[3:end].strip()
    body    = text[end + 4:].lstrip("\n")
    fm: dict = {}
    for line in fm_text.splitlines():
        m_tags = re.match(r'^tags:\s*\[(.+)\]', line)
        if m_tags:
            fm["tags"] = [
                t.strip().strip('"').strip("'")
                for t in m_tags.group(1).split(",")
                if t.strip().strip('"')
            ]
            continue
        m = re.match(r'^(\w+):\s*(.+)', line)
        if m:
            fm[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return fm, body


def get_article_date(src: Path) -> str:
    text = src.read_text(encoding="utf-8")
    m = re.search(r'^date:\s*(.+)', text, re.MULTILINE)
    return m.group(1).strip() if m else "1970-01-01"


def make_qiita_tags(tags: list[str], error_code: str) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()

    for tag in tags:
        if tag.isdigit():
            continue
        if tag not in seen:
            result.append({"name": tag})
            seen.add(tag)

    if error_code:
        name = f"HTTP{error_code}"
        if name not in seen:
            result.append({"name": name})

    if "ErrorLog" not in seen:
        result.append({"name": "ErrorLog"})

    return result[:5]


def strip_internal_links(body: str) -> str:
    body = re.sub(r'\[([^\]]+)\]\(/glossary/[^)]+\)', r'\1', body)
    body = re.sub(r'\[([^\]]+)\]\(/posts/[^)]+\)',    r'\1', body)
    return body


def post_to_qiita(token: str, title: str, body: str, tags: list[dict]) -> str:
    """Qiitaに記事を投稿して item_id を返す。"""
    payload = json.dumps({
        "title":   title,
        "body":    body,
        "tags":    tags,
        "private": False,
        "tweet":   False,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{QIITA_API}/items",
        data=payload,
        headers={
            "Authorization":  f"Bearer {token}",
            "Content-Type":   "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["id"]


def main() -> None:
    token = os.getenv("QIITA_ACCESS_TOKEN")
    if not token:
        print("エラー: QIITA_ACCESS_TOKEN が設定されていません。")
        sys.exit(1)

    # トークン確認
    req_test = urllib.request.Request(
        f"{QIITA_API}/authenticated_user",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req_test) as resp:
            user = json.loads(resp.read())
            print(f"認証成功: {user.get('id')} (フォロワー: {user.get('followers_count')})")
    except urllib.error.HTTPError as e:
        print(f"認証エラー {e.code}: {e.read().decode()[:200]}")
        sys.exit(1)

    posted = load_posted()
    posts  = sorted(POSTS_DIR.glob("*.md"), key=get_article_date)

    count = 0
    for src in posts:
        if src.name.startswith("_"):
            continue
        stem = src.stem
        if stem in posted:
            continue

        text = src.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)

        if fm.get("draft", "").lower() == "true":
            continue

        title      = fm.get("title", stem)
        tags_raw   = fm.get("tags") if isinstance(fm.get("tags"), list) else []
        error_code = fm.get("errorCode", "")
        tags       = make_qiita_tags(tags_raw, error_code)

        body = strip_internal_links(body)
        body += f"\n\n---\n\nこの記事は [errorlog.jp](https://errorlog.jp/posts/{stem}/) でも公開しています。\n"

        print(f"  投稿中: {title}")
        try:
            item_id = post_to_qiita(token, title, body, tags)
            posted[stem] = item_id
            print(f"  → https://qiita.com/items/{item_id}")
            count += 1
        except urllib.error.HTTPError as e:
            body_err = e.read().decode()
            print(f"  HTTPエラー {e.code}: {body_err[:200]}")
            break
        except Exception as e:
            print(f"  エラー: {e}")
            break

        if count >= QIITA_COUNT:
            break

    save_posted(posted)
    print(f"\n完了: {count} 件投稿")


if __name__ == "__main__":
    main()
