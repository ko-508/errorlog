"""
Hugo 記事を Zenn 形式に変換して ZENN_DIR に出力するスクリプト。
scripts/zenn_synced.json で同期済み記事の最終同期日を管理し、
lastmod が更新された記事は自動的に再同期する。

使い方:
  ZENN_DIR=../zenn-content python scripts/zenn_sync.py           # 新規＋更新のみ
  ZENN_DIR=../zenn-content python scripts/zenn_sync.py --force   # 全記事強制同期
"""

import json
import os
import re
import sys
from pathlib import Path

BASE      = Path(__file__).parent
POSTS_DIR = BASE.parent / "content" / "posts"
ZENN_DIR  = Path(os.getenv("ZENN_DIR", str(BASE.parent.parent / "zenn-content")))
MANIFEST  = BASE / "zenn_synced.json"

TOOL_EMOJI: dict[str, str] = {
    "docker":        "🐳",
    "kubernetes":    "☸️",
    "aws":           "☁️",
    "firebase":      "🔥",
    "slack":         "💬",
    "github":        "🐙",
    "git":           "📦",
    "python":        "🐍",
    "node":          "🟢",
    "nginx":         "🌐",
    "mysql":         "🗄️",
    "postgres":      "🐘",
    "redis":         "🔴",
    "mongodb":       "🍃",
    "terraform":     "🏗️",
    "vercel":        "▲",
    "netlify":       "🚀",
    "heroku":        "💜",
    "stripe":        "💳",
    "sendgrid":      "📧",
    "twilio":        "📞",
    "elasticsearch": "🔍",
    "grafana":       "📊",
    "jenkins":       "🤖",
    "ansible":       "⚙️",
}

DEFAULT_EMOJI_TOOL  = "🔧"
DEFAULT_EMOJI_ERROR = "🚫"


def load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {}


def save_manifest(manifest: dict) -> None:
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2),
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
                if t.strip().strip('"').strip("'")
            ]
            continue

        m = re.match(r'^(\w+):\s*(.+)', line)
        if m:
            key = m.group(1)
            val = m.group(2).strip().strip('"').strip("'")
            fm[key] = val

    return fm, body


def article_date(fm: dict) -> str:
    """lastmod があればそれを、なければ date を返す。"""
    return fm.get("lastmod") or fm.get("date") or "1970-01-01"


def make_zenn_slug(hugo_stem: str) -> str:
    slug = "el-" + re.sub(r"[^a-z0-9]", "-", hugo_stem.lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    if len(slug) > 50:
        slug = slug[:50].rstrip("-")
    while len(slug) < 12:
        slug += "-x"
    return slug


def pick_emoji(stem: str, tags: list[str]) -> str:
    if stem.startswith("tool_"):
        key = stem[5:].lower()
        for tool_key, emoji in TOOL_EMOJI.items():
            if tool_key in key:
                return emoji
        return DEFAULT_EMOJI_TOOL

    for tag in tags:
        for tool_key, emoji in TOOL_EMOJI.items():
            if tool_key in tag.lower():
                return emoji

    return DEFAULT_EMOJI_ERROR


def make_zenn_topics(tags: list[str], stem: str) -> list[str]:
    topics: list[str] = []

    for tag in tags:
        if tag.isdigit():
            continue
        t = re.sub(r"[^a-z0-9-]", "-", tag.lower())
        t = re.sub(r"-+", "-", t).strip("-")
        if len(t) < 2:
            continue
        if len(t) > 20:
            t = t[:20].rstrip("-")
        if t and t not in topics:
            topics.append(t)
        if len(topics) >= 4:
            break

    if "error" not in " ".join(topics) and not stem.startswith("tool_"):
        topics.append("error")

    if not topics:
        topics = ["tech"]

    return topics[:5]


def strip_internal_links(body: str) -> str:
    body = re.sub(r'\[([^\]]+)\]\(/glossary/[^)]+\)', r'\1', body)
    body = re.sub(r'\[([^\]]+)\]\(/posts/[^)]+\)', r'\1', body)
    return body


def needs_sync(stem: str, fm: dict, manifest: dict, zenn_articles_dir: Path, force: bool) -> bool:
    """同期が必要かどうかを判定する。"""
    if force:
        return True

    zenn_slug = make_zenn_slug(stem)
    out_path  = zenn_articles_dir / f"{zenn_slug}.md"

    # Zennファイルが存在しない → 新規
    if not out_path.exists():
        return True

    # マニフェストに記録がない → 同期が必要
    if stem not in manifest:
        return True

    # 記事の更新日 > 最終同期日 → 更新あり
    return article_date(fm) > manifest[stem]


def convert(src: Path, zenn_articles_dir: Path, manifest: dict, force: bool) -> tuple[bool, str]:
    """1記事を変換して Zenn 形式で書き出す。(書き出したか, 記事日付) を返す。"""
    text = src.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)

    if fm.get("draft", "").lower() == "true":
        return False, ""

    stem = src.stem

    if not needs_sync(stem, fm, manifest, zenn_articles_dir, force):
        return False, ""

    zenn_slug  = make_zenn_slug(stem)
    out_path   = zenn_articles_dir / f"{zenn_slug}.md"
    tags       = fm.get("tags") if isinstance(fm.get("tags"), list) else []
    emoji      = pick_emoji(stem, tags)
    topics     = make_zenn_topics(tags, stem)
    title      = fm.get("title", stem)
    topics_str = "[" + ", ".join(f'"{t}"' for t in topics) + "]"

    zenn_fm = (
        f"---\n"
        f'title: "{title}"\n'
        f'emoji: "{emoji}"\n'
        f'type: "tech"\n'
        f"topics: {topics_str}\n"
        f"published: true\n"
        f"---\n\n"
    )

    body = strip_internal_links(body)
    out_path.write_text(zenn_fm + body, encoding="utf-8")
    return True, article_date(fm)


def main() -> None:
    force = "--force" in sys.argv
    limit = int(os.getenv("ZENN_LIMIT", "0"))

    zenn_articles_dir = ZENN_DIR / "articles"
    zenn_articles_dir.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest()
    posts    = sorted(POSTS_DIR.glob("*.md"))
    written  = 0
    skipped  = 0

    for src in posts:
        if src.name.startswith("_"):
            continue
        ok, synced_date = convert(src, zenn_articles_dir, manifest, force)
        if ok:
            manifest[src.stem] = synced_date
            written += 1
            print(f"  ✓ {src.stem}")
            if limit > 0 and written >= limit:
                print(f"  (ZENN_LIMIT={limit} に達したため停止)")
                break
        else:
            skipped += 1

    save_manifest(manifest)
    print(f"\n完了: {written} 件同期 / {skipped} 件スキップ")


if __name__ == "__main__":
    main()
