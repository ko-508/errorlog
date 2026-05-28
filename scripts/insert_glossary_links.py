"""
用語集の用語を投稿記事内で Markdown リンクに自動変換するスクリプト。

ルール:
  - content/glossary/*.md から用語名と URL を収集
  - content/posts/*.md の本文中の用語を [用語](URL) に変換
  - 除外: 見出し、コードブロック、インラインコード、既存リンク、HTML タグ、裸URL
  - 日本語文字種別のワードバウンダリ（「サポート」内の「ポート」等を誤マッチしない）
  - 長い用語を優先（部分マッチ防止）
  - 冪等: 既にリンク済みの箇所は再変換しない

実行:
  python scripts/insert_glossary_links.py           # 全記事を処理
  python scripts/insert_glossary_links.py --reset   # 既存の用語集リンクを解除してから再挿入
  python scripts/insert_glossary_links.py file.md   # 1ファイル指定
"""

import os
import re
import sys
from pathlib import Path

BASE         = Path(__file__).parent
POSTS_DIR    = BASE.parent / "content" / "posts"
GLOSSARY_DIR = BASE.parent / "content" / "glossary"

# 文字種別パターン（ワードバウンダリ用）
_KAT = r"[ァ-ヶーｦ-ﾟ]"   # カタカナ（全角・半角・長音符）
_HIR = r"[ぁ-ん]"           # ひらがな
_KAN = r"[一-鿿㐀-䶿]"  # 漢字
_ASC = r"[A-Za-z0-9]"       # ASCII 英数字


# ── 用語集の読み込み ────────────────────────────────────

def load_terms() -> list[tuple[str, str]]:
    """
    (用語名, /glossary/slug/) のリストを返す（長い順）。
    """
    terms: list[tuple[str, str]] = []
    for path in GLOSSARY_DIR.glob("*.md"):
        if path.name == "_index.md":
            continue
        text = path.read_text(encoding="utf-8")
        m = re.search(r'^title:\s*"(.+?)とは', text, re.MULTILINE)
        if not m:
            m = re.search(r'^title:\s*"([^"]+)"', text, re.MULTILINE)
        if not m:
            continue
        term = m.group(1).strip()
        if len(term) < 2:          # 1文字は誤マッチしやすいのでスキップ
            continue
        url = f"/glossary/{path.stem}/"
        terms.append((term, url))

    terms.sort(key=lambda x: len(x[0]), reverse=True)
    return terms


# ── ワードバウンダリ付きパターン生成 ─────────────────────

def _char_class(ch: str) -> str | None:
    """文字がどの種別に属するかを返す。"""
    if re.match(_KAT, ch): return _KAT
    if re.match(_HIR, ch): return _HIR
    if re.match(_KAN, ch): return _KAN
    if re.match(_ASC, ch): return _ASC
    return None


def build_term_regex(term: str) -> str:
    """
    部分マッチを防ぐ lookbehind/lookahead 付きパターンを生成する。
    例: 「ポート」→ 「サポート」内でマッチしない
        「API」   → URL内の「api」にマッチしない（大文字小文字区別あり）
    """
    escaped = re.escape(term)
    first_class = _char_class(term[0])
    last_class  = _char_class(term[-1])

    prefix = f"(?<!{first_class})" if first_class else ""
    suffix = f"(?!{last_class})"   if last_class  else ""

    return f"{prefix}{escaped}{suffix}"


# ── テキスト処理 ────────────────────────────────────────

def _saver(ph: dict, idx: list):
    def save(m: re.Match) -> str:
        key = f"\x00{idx[0]}\x00"
        ph[key] = m.group(0)
        idx[0] += 1
        return key
    return save


def process_line(line: str, term_map: dict, pattern: re.Pattern) -> str:
    """
    1 行内の用語を Markdown リンクに変換。
    以下の範囲は保護して変換対象外にする:
      - 既存 Markdown リンク [text](url)
      - 画像 ![alt](url)
      - インラインコード `code`
      - HTML <a> タグ・その他タグ
      - 裸の URL（https://...）
    """
    ph: dict[str, str] = {}
    idx = [0]
    save = _saver(ph, idx)

    # ── 保護パターン（優先度順に適用）──
    line = re.sub(r'!\[[^\]\n]*\]\([^\)\n]*\)', save, line)       # ![img](url)
    line = re.sub(r'\[[^\]\n]*\]\([^\)\n]*\)', save, line)        # [text](url)
    line = re.sub(r'`[^`\n]+`', save, line)                       # `inline code`
    line = re.sub(r'<a\b[^>]*>.*?</a>', save, line, flags=re.DOTALL)  # <a>...</a>
    line = re.sub(r'<[^>\n]+>', save, line)                        # <tag />
    line = re.sub(r'https?://\S+', save, line)                     # 裸URL

    # ── 用語 → Markdown リンクに変換 ──
    def replace(m: re.Match) -> str:
        term = m.group(0)
        url  = term_map.get(term, "")
        return f"[{term}]({url})" if url else term

    line = pattern.sub(replace, line)

    # ── プレースホルダーを復元 ──
    for key, val in ph.items():
        line = line.replace(key, val)

    return line


def process_body(body: str, term_map: dict, pattern: re.Pattern) -> str:
    """
    本文全体を処理。コードブロック・見出しはスキップ。
    """
    lines = body.split("\n")
    result: list[str] = []
    in_code = False

    for line in lines:
        # フェンスドコードブロックのトグル
        if re.match(r"^(`{3,}|~{3,})", line.rstrip()):
            in_code = not in_code
            result.append(line)
            continue

        if in_code:
            result.append(line)
            continue

        # 見出し行をスキップ（#, ##, ### …）
        if re.match(r"^#{1,6}\s", line):
            result.append(line)
            continue

        result.append(process_line(line, term_map, pattern))

    return "\n".join(result)


def undo_glossary_links(body: str) -> str:
    """既存の用語集リンク [用語](/glossary/…/) を用語テキストだけに戻す。"""
    return re.sub(r"\[([^\]\n]+)\]\(/glossary/[^\)\n]+/\)", r"\1", body)


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
    args = sys.argv[1:]
    reset = "--reset" in args
    file_args = [a for a in args if not a.startswith("--")]

    terms = load_terms()
    if not terms:
        print("用語集にページがありません。スキップします。")
        return

    term_map = {term: url for term, url in terms}
    pattern  = re.compile(
        "|".join(build_term_regex(term) for term, _ in terms)
    )

    if file_args:
        targets = [Path(file_args[0])]
        if not targets[0].exists():
            print(f"ファイルが見つかりません: {targets[0]}")
            sys.exit(1)
    else:
        targets = sorted(POSTS_DIR.glob("*.md"))

    mode = "リセット＋再挿入" if reset else "リンク挿入"
    print(f"{mode}: 用語 {len(terms)} 語 / 記事 {len(targets)} 件")
    updated = 0

    for path in targets:
        content = path.read_text(encoding="utf-8")
        fm, body = split_frontmatter(content)

        if reset:
            body = undo_glossary_links(body)

        new_body    = process_body(body, term_map, pattern)
        new_content = fm + new_body

        if new_content != content:
            path.write_text(new_content, encoding="utf-8")
            print(f"  更新: {path.name}")
            updated += 1

    print(f"\n完了: {updated}/{len(targets)} 件を更新しました。")


if __name__ == "__main__":
    main()
