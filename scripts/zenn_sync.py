"""
Hugo 記事を Zenn 形式に変換して ZENN_DIR に出力するスクリプト。
scripts/zenn_synced.json で同期済み記事の最終同期「日時」を管理し、
ファイルの mtime が最終同期タイムスタンプより新しければ自動再同期する。

・lastmod は表示用（サイトに表示する最終更新日）として維持する
・同期判定はファイルの実際の更新時刻（mtime）で行うため
  同日に複数回更新した場合も確実に再同期される

使い方:
  ZENN_DIR=../zenn-content python scripts/zenn_sync.py                       # 新規＋更新のみ
  ZENN_DIR=../zenn-content python scripts/zenn_sync.py --force               # 全記事強制同期
  ZENN_DIR=../zenn-content python scripts/zenn_sync.py --slugs a,b,c         # 指定記事のみ強制同期
                                                                             # (draft は指定しても同期しない)
"""

import datetime
import json
import os
import re
import sys
from pathlib import Path

BASE      = Path(__file__).parent
POSTS_DIR = BASE.parent / "content" / "posts"
ZENN_DIR  = Path(os.getenv("ZENN_DIR", str(BASE.parent.parent / "zenn-content")))
MANIFEST  = BASE / "zenn_synced.json"
SITE_BASE = "https://errorlog.jp"

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


def rewrite_internal_links(body: str) -> str:
    """内部リンクを Zenn 掲載用に書き換える。

    ・/posts/ へのリンクは errorlog.jp の絶対URLに変換する
      （本文中の関連記事への誘導を機能させるため。削除すると文が壊れる）
    ・/glossary/ へのリンクはリンクを外して文字だけ残す
    """
    body = re.sub(r'\[([^\]]+)\]\(/glossary/[^)]+\)', r'\1', body)
    body = re.sub(
        r'\[([^\]]+)\]\((/posts/[^)]+)\)',
        lambda m: f"[{m.group(1)}]({SITE_BASE}{m.group(2)})",
        body,
    )
    return body


def source_notice(stem: str) -> str:
    """冒頭に挿入する元記事への誘導ブロック。"""
    url = f"{SITE_BASE}/posts/{stem}/"
    return (
        ":::message\n"
        f"本記事は技術エラー解説サイト [errorlog.jp]({SITE_BASE}/) からの転載です。"
        f"最新の内容と関連エラーの一覧は元記事を参照してください。\n"
        f"元記事: {url}\n"
        ":::\n\n"
    )


def needs_sync(src: Path, stem: str, manifest: dict, zenn_articles_dir: Path, force: bool) -> bool:
    """同期が必要かどうかを判定する。

    判定基準: ファイルの mtime > マニフェストの最終同期タイムスタンプ
    同日複数回の更新にも対応するため日付ではなく時刻で比較する。
    """
    if force:
        return True

    zenn_slug = make_zenn_slug(stem)
    out_path  = zenn_articles_dir / f"{zenn_slug}.md"

    # Zenn ファイルが存在しない → 新規
    if not out_path.exists():
        return True

    # マニフェストに記録がない → 同期が必要
    if stem not in manifest:
        return True

    # ファイルの実際の更新時刻
    file_mtime = datetime.datetime.fromtimestamp(src.stat().st_mtime)

    # マニフェストの値を datetime にパース（旧形式の日付文字列も許容）
    try:
        last_sync = datetime.datetime.fromisoformat(manifest[stem])
    except (ValueError, TypeError):
        return True  # パース失敗 → 念のため再同期

    return file_mtime > last_sync


def convert(src: Path, zenn_articles_dir: Path, manifest: dict, force: bool) -> tuple[bool, str]:
    """1記事を変換して Zenn 形式で書き出す。(書き出したか, 同期タイムスタンプ) を返す。"""
    text = src.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)

    stem = src.stem

    if fm.get("draft", "").lower() == "true":
        # draft は同期しない（--slugs で明示指定された場合も安全側に倒す）
        if force:
            print(f"  ! {stem} は draft のため同期しません")
        return False, ""

    if not needs_sync(src, stem, manifest, zenn_articles_dir, force):
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

    body = rewrite_internal_links(body)
    out_path.write_text(zenn_fm + source_notice(stem) + body, encoding="utf-8")
    # 同期完了時刻を ISO datetime で返す（マニフェストに記録）
    return True, datetime.datetime.now().isoformat()


def parse_slugs_arg(argv: list[str]) -> list[str]:
    """--slugs a,b,c または --slugs=a,b,c を解釈して slug のリストを返す。"""
    for i, arg in enumerate(argv):
        if arg == "--slugs" and i + 1 < len(argv):
            return [s.strip() for s in argv[i + 1].split(",") if s.strip()]
        if arg.startswith("--slugs="):
            return [s.strip() for s in arg.split("=", 1)[1].split(",") if s.strip()]
    return []


def main() -> None:
    force = "--force" in sys.argv
    slugs = parse_slugs_arg(sys.argv)
    limit = int(os.getenv("ZENN_LIMIT", "0"))

    zenn_articles_dir = ZENN_DIR / "articles"
    zenn_articles_dir.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest()
    posts    = sorted(POSTS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    written  = 0
    skipped  = 0

    if slugs:
        # 指定 slug のみを対象に強制同期（存在しない slug は明示的に報告）
        stems_found = {p.stem for p in posts}
        for s in slugs:
            if s not in stems_found:
                print(f"  ! 指定された slug が見つかりません: {s}")
        posts = [p for p in posts if p.stem in slugs]
        force = True
        limit = 0  # slug 指定時は件数制限を適用しない

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