"""
用語集の用語を投稿記事内で Markdown リンクに自動変換するスクリプト。

ルール:
  - content/glossary/*.md から用語名と URL を収集
  - content/posts/*.md の本文中の用語を [用語](URL) に変換
  - 除外: 見出し行、コードブロック、インラインコード、既存リンク、HTML タグ
  - 長い用語を優先マッチ（部分マッチ防止）
  - 冪等: 既にリンク済みの箇所は再変換しない

実行:
  python scripts/insert_glossary_links.py          # 全記事を処理
  python scripts/insert_glossary_links.py path/md  # 1 ファイル指定
"""

import os
import re
import sys
from pathlib import Path

BASE = Path(__file__).parent
POSTS_DIR    = BASE.parent / "content" / "posts"
GLOSSARY_DIR = BASE.parent / "content" / "glossary"


# ── 用語集の読み込み ────────────────────────────────────

def load_terms() -> list[tuple[str, str]]:
    """
    (用語名, /glossary/slug/) のリストを返す。
    タイトルが「〜とは？わかりやすく解説」形式のページから用語名を抽出。
    長い用語を先に並べることで部分マッチを防止する。
    """
    terms: list[tuple[str, str]] = []
    for path in GLOSSARY_DIR.glob("*.md"):
        if path.name == "_index.md":
            continue
        text = path.read_text(encoding="utf-8")
        m = re.search(r'^title:\s*"(.+?)とは', text, re.MULTILINE)
        if not m:
            # "とは" を含まないタイトルも対象
            m = re.search(r'^title:\s*"([^"]+)"', text, re.MULTILINE)
        if not m:
            continue
        term = m.group(1).strip()
        if len(term) < 2:          # 1 文字は誤マッチしやすいのでスキップ
            continue
        url = f"/glossary/{path.stem}/"
        terms.append((term, url))

    # 長い順（部分マッチ防止）
    terms.sort(key=lambda x: len(x[0]), reverse=True)
    return terms


# ── テキスト処理 ────────────────────────────────────────

def _make_saver(placeholders: dict, idx: list) -> callable:
    """マッチをプレースホルダーに置換してスキップ範囲を保護する。"""
    def save(m: re.Match) -> str:
        key = f"\x00{idx[0]}\x00"
        placeholders[key] = m.group(0)
        idx[0] += 1
        return key
    return save


def process_line(line: str, term_map: dict, pattern: re.Pattern) -> str:
    """
    1 行内の用語を Markdown リンクに変換する。
    既存リンク・インラインコード・HTML タグは保護して変換対象外にする。
    """
    ph: dict[str, str] = {}
    idx = [0]
    save = _make_saver(ph, idx)

    # 保護（変換対象外にするパターン）
    line = re.sub(r'\[[^\]\n]*\]\([^\)\n]*\)', save, line)   # [text](url)
    line = re.sub(r'!\[[^\]\n]*\]\([^\)\n]*\)', save, line)  # ![img](url)
    line = re.sub(r'`[^`\n]+`', save, line)                  # `inline code`
    line = re.sub(r'<a\b[^>]*>.*?</a>', save, line, flags=re.DOTALL)  # <a>
    line = re.sub(r'<[^>\n]+>', save, line)                   # その他 HTML タグ

    # 用語 → Markdown リンクに変換
    def replace(m: re.Match) -> str:
        term = m.group(0)
        url  = term_map.get(term, "")
        return f"[{term}]({url})" if url else term

    line = pattern.sub(replace, line)

    # プレースホルダーを元のテキストに戻す
    for key, val in ph.items():
        line = line.replace(key, val)

    return line


def process_body(body: str, term_map: dict, pattern: re.Pattern) -> str:
    """
    記事本文全体を処理する。
    フェンスドコードブロックと見出し行はスキップ。
    """
    lines = body.split("\n")
    result: list[str] = []
    in_code = False

    for line in lines:
        # フェンスドコードブロックのトグル（``` or ~~~）
        if re.match(r"^(`{3,}|~{3,})", line.rstrip()):
            in_code = not in_code
            result.append(line)
            continue

        if in_code:
            result.append(line)
            continue

        # 見出し行はスキップ（#、##、###…）
        if re.match(r"^#{1,6}\s", line):
            result.append(line)
            continue

        result.append(process_line(line, term_map, pattern))

    return "\n".join(result)


# ── フロントマター分離 ──────────────────────────────────

def split_frontmatter(content: str) -> tuple[str, str]:
    if not content.startswith("---"):
        return "", content
    end = content.find("\n---\n", 3)
    if end == -1:
        return "", content
    return content[: end + 5], content[end + 5:]


# ── メイン ────────────────────────────────────────────

def main() -> None:
    terms = load_terms()
    if not terms:
        print("用語集にページがありません。スキップします。")
        return

    term_map = {term: url for term, url in terms}
    pattern  = re.compile("|".join(re.escape(t) for t, _ in terms))

    if len(sys.argv) > 1:
        targets = [Path(sys.argv[1])]
        if not targets[0].exists():
            print(f"ファイルが見つかりません: {targets[0]}")
            sys.exit(1)
    else:
        targets = sorted(POSTS_DIR.glob("*.md"))

    print(f"リンク挿入開始: 用語 {len(terms)} 語 / 記事 {len(targets)} 件")
    updated = 0

    for path in targets:
        content = path.read_text(encoding="utf-8")
        fm, body = split_frontmatter(content)
        new_body = process_body(body, term_map, pattern)

        new_content = fm + new_body
        if new_content != content:
            path.write_text(new_content, encoding="utf-8")
            print(f"  更新: {path.name}")
            updated += 1

    print(f"\n完了: {updated}/{len(targets)} 件を更新しました。")


if __name__ == "__main__":
    main()
