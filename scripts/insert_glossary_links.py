"""
用語集の用語を投稿記事内で Markdown リンクに自動変換するスクリプト。

ルール:
  - content/glossary/*.md から用語名と URL を収集
  - content/posts/*.md の本文中の用語を [用語](URL) に変換
  - 除外: 見出し行、フェンスドコードブロック、インラインコード、
           既存 Markdown リンク、HTML タグ、裸URL
  - 日本語文字種別（カタカナ/ひらがな/漢字）と ASCII の境界チェックで
    部分マッチを防止（例:「サポート」内の「ポート」は誤マッチしない）
  - 長い用語を優先マッチ（短い用語への部分マッチ防止）
  - 冪等：既にリンク済みの箇所は保護パターンで除外

実行:
  python scripts/insert_glossary_links.py           # 全記事を処理
  python scripts/insert_glossary_links.py --reset   # 既存の用語集リンクを解除して再挿入
  python scripts/insert_glossary_links.py path.md   # 1 ファイル指定
"""

import os
import re
import sys
from pathlib import Path

BASE         = Path(__file__).parent
POSTS_DIR    = BASE.parent / "content" / "posts"
GLOSSARY_DIR = BASE.parent / "content" / "glossary"


# ══════════════════════════════════════════════════════════════
# 1. Unicode 文字種レンジ定義
#    Python re の文字クラス []内で使用できる正確な hex レンジ
# ══════════════════════════════════════════════════════════════

# ひらがな: U+3040–U+309F（小文字・濁点・半濁点・繰り返し記号を含む全域）
_RANGE_HIRAGANA = "぀-ゟ"

# カタカナ（全角）: U+30A1–U+30FA（ァ〜ヺ）+ U+30FC（ー長音符）
# U+30A0(゠二重ハイフン) と U+30FB(・中点) は語区切り記号なので除外
_RANGE_KATAKANA_FW = "ァ-ヺー"

# カタカナ（半角）: U+FF65–U+FF9F（半角ｦ〜ﾟ）
_RANGE_KATAKANA_HW = "･-ﾟ"

# CJK 統合漢字: U+4E00–U+9FFF（常用漢字・人名漢字等）
_RANGE_KANJI_MAIN = "一-鿿"

# CJK 拡張 A: U+3400–U+4DBF（旧字・異体字等）
_RANGE_KANJI_EXT_A = "㐀-䶿"

# ASCII 英数字
_RANGE_ASCII = "A-Za-z0-9"

# 文字種 → 「同種文字クラス」の文字列（lookbehind/lookahead に使用）
_BOUNDARY_CLASS: dict[str, str] = {
    "hiragana" : f"[{_RANGE_HIRAGANA}]",
    "katakana" : f"[{_RANGE_KATAKANA_FW}{_RANGE_KATAKANA_HW}]",
    "kanji"    : f"[{_RANGE_KANJI_MAIN}{_RANGE_KANJI_EXT_A}]",
    "ascii"    : f"[{_RANGE_ASCII}]",
}


def _get_char_class(ch: str) -> str | None:
    """
    1 文字を受け取り、所属する文字種キーを返す。
    どの種別にも属さない場合（記号・スペース等）は None。

    >>> _get_char_class("ポ")
    'katakana'
    >>> _get_char_class("す")
    'hiragana'
    >>> _get_char_class("漢")
    'kanji'
    >>> _get_char_class("A")
    'ascii'
    >>> _get_char_class("。")  # 句読点
    is None
    """
    cp = ord(ch)
    if 0x3040 <= cp <= 0x309F:
        return "hiragana"
    if 0x30A0 <= cp <= 0x30FF:
        return "katakana"
    if 0xFF65 <= cp <= 0xFF9F:
        return "katakana"
    if 0x4E00 <= cp <= 0x9FFF:
        return "kanji"
    if 0x3400 <= cp <= 0x4DBF:
        return "kanji"
    if ch.isascii() and (ch.isalpha() or ch.isdigit()):
        return "ascii"
    return None


# ══════════════════════════════════════════════════════════════
# 2. ワードバウンダリ付き正規表現パターン生成
# ══════════════════════════════════════════════════════════════

def build_term_regex(term: str) -> str:
    """
    用語に対して、部分マッチを防ぐ lookbehind/lookahead 付きパターンを返す。

    ロジック:
      - 用語の「先頭文字」が属する文字種と同じ文字が直前に来たらマッチしない
      - 用語の「末尾文字」が属する文字種と同じ文字が直後に来たらマッチしない

    例:
      「ポート」（カタカナ）
        → (?<![゠-ヿ･-ﾟ])ポート(?![゠-ヿ･-ﾟ])
        → 「サポート」の「サ」(カタカナ) が直前 → マッチしない ✓

      「HTTP」（ASCII）
        → (?<![A-Za-z0-9])HTTP(?![A-Za-z0-9])
        → 「HTTPS」の「S」が直後 → マッチしない ✓
        → 「https://」は裸URL保護で除外済み ✓
    """
    if not term:
        return re.escape(term)

    first_cls = _get_char_class(term[0])
    last_cls  = _get_char_class(term[-1])
    escaped   = re.escape(term)

    # lookbehind: 先頭と同種の文字が直前にあればマッチしない（幅 1 固定）
    prefix = f"(?<!{_BOUNDARY_CLASS[first_cls]})" if first_cls else ""

    # lookahead: 末尾と同種の文字が直後にあればマッチしない
    suffix = f"(?!{_BOUNDARY_CLASS[last_cls]})" if last_cls else ""

    return f"{prefix}{escaped}{suffix}"


# ══════════════════════════════════════════════════════════════
# 3. 保護機構（プレースホルダー方式）
# ══════════════════════════════════════════════════════════════

# プレースホルダー形式: \x00PROTECT{n}\x00
# \x00 (NUL) は通常テキストに出現しないため、用語の誤マッチが起きない
_PH_FMT = "\x00PROTECT{n}\x00"

# 保護対象パターン（優先度順に適用）
_PROTECT_PATTERNS: list[str] = [
    r"!\[[^\]\n]*\]\([^\)\n]*\)",       # Markdown 画像 ![alt](url)  ← リンクより先に
    r"\[[^\]\n]*\]\([^\)\n]*\)",        # Markdown リンク [text](url)
    r"`[^`\n]+`",                        # インラインコード `code`
    r"<a\b[^>]*>.*?</a>",               # HTML <a>...</a>
    r"<[^>\n]+>",                        # その他 HTML タグ <tag />
    r"https?://\S+",                     # 裸URL（https://... / http://...）
]


def _protect(text: str, patterns: list[str]) -> tuple[str, list[str]]:
    """
    patterns に一致する部分をすべてプレースホルダーに置換する。

    返り値:
      (保護後テキスト,  元の文字列リスト)

    リストの index n に対応するプレースホルダーは _PH_FMT.format(n=n)。
    """
    saved: list[str] = []

    def _save(m: re.Match) -> str:
        idx = len(saved)
        saved.append(m.group(0))
        return _PH_FMT.format(n=idx)

    for pat in patterns:
        text = re.sub(pat, _save, text, flags=re.DOTALL)

    return text, saved


def _restore(text: str, saved: list[str]) -> str:
    """プレースホルダーを元の文字列に逆順で戻す。"""
    # 逆順にすることで、プレースホルダー内にプレースホルダーが含まれても正しく復元できる
    for i in reversed(range(len(saved))):
        text = text.replace(_PH_FMT.format(n=i), saved[i])
    return text


# ══════════════════════════════════════════════════════════════
# 4. 用語集の読み込み
# ══════════════════════════════════════════════════════════════

def load_terms() -> list[tuple[str, str]]:
    """
    (用語名, /glossary/slug/) のリストを返す。
    長い用語を先頭に並べることで、短い用語への部分マッチを防ぐ。
    """
    terms: list[tuple[str, str]] = []
    for path in GLOSSARY_DIR.glob("*.md"):
        if path.name == "_index.md":
            continue
        text = path.read_text(encoding="utf-8")

        # タイトル: "〜とは？わかりやすく解説" から用語名を抽出
        m = re.search(r'^title:\s*"(.+?)とは', text, re.MULTILINE)
        if not m:
            m = re.search(r'^title:\s*"([^"]+)"', text, re.MULTILINE)
        if not m:
            continue

        term = m.group(1).strip()
        if len(term) < 2:       # 1文字は誤マッチしやすいのでスキップ
            continue

        terms.append((term, f"/glossary/{path.stem}/"))

    terms.sort(key=lambda x: len(x[0]), reverse=True)  # 長い順
    return terms


# ══════════════════════════════════════════════════════════════
# 5. 本文処理
# ══════════════════════════════════════════════════════════════

def _insert_links_in_line(
    line: str,
    term_map: dict[str, str],
    combined: re.Pattern,
) -> str:
    """
    1 行のテキストに対してリンク挿入を行う。

    手順:
      1. 保護対象（既存リンク・インラインコード・URL等）をプレースホルダーに退避
      2. 用語パターン（combined）で一致箇所を [用語](URL) に置換
      3. プレースホルダーを元の文字列に復元
    """
    text, saved = _protect(line, _PROTECT_PATTERNS)

    def _replace(m: re.Match) -> str:
        term = m.group(0)
        url  = term_map.get(term, "")
        return f"[{term}]({url})" if url else term

    text = combined.sub(_replace, text)
    return _restore(text, saved)


def process_body(
    body: str,
    term_map: dict[str, str],
    combined: re.Pattern,
) -> str:
    """
    記事本文全体を処理する。
    フェンスドコードブロック（``` / ~~~）と見出し行（#）はスキップ。
    """
    lines   = body.split("\n")
    result  : list[str] = []
    in_code = False

    for line in lines:
        # フェンスドコードブロックの開始/終了をトグル
        if re.match(r"^(`{3,}|~{3,})", line.rstrip()):
            in_code = not in_code
            result.append(line)
            continue

        if in_code:
            result.append(line)
            continue

        # 見出し行（#, ##, ### …）はスキップ
        if re.match(r"^#{1,6}\s", line):
            result.append(line)
            continue

        result.append(_insert_links_in_line(line, term_map, combined))

    return "\n".join(result)


def undo_glossary_links(body: str) -> str:
    """
    本文中の用語集 Markdown リンク [用語](/glossary/…/) を
    プレーンテキストに戻す（--reset モード用）。
    """
    return re.sub(
        r"\[([^\]\n]+)\]\(/glossary/[^\)\n]+/\)",
        r"\1",
        body,
    )


# ══════════════════════════════════════════════════════════════
# 6. フロントマター分離
# ══════════════════════════════════════════════════════════════

def split_frontmatter(content: str) -> tuple[str, str]:
    """YAML フロントマター（--- ブロック）と本文を分離する。"""
    if not content.startswith("---"):
        return "", content
    end = content.find("\n---\n", 3)
    if end == -1:
        return "", content
    return content[: end + 5], content[end + 5:]


# ══════════════════════════════════════════════════════════════
# 7. メイン
# ══════════════════════════════════════════════════════════════

def main() -> None:
    args   = sys.argv[1:]
    reset  = "--reset" in args
    files  = [a for a in args if not a.startswith("--")]

    terms = load_terms()
    if not terms:
        print("用語集にページがありません。スキップします。")
        return

    term_map = {term: url for term, url in terms}
    combined = re.compile(
        "|".join(build_term_regex(term) for term, _ in terms)
    )

    if files:
        targets = [Path(files[0])]
        if not targets[0].exists():
            print(f"ファイルが見つかりません: {targets[0]}")
            sys.exit(1)
    else:
        targets = sorted(POSTS_DIR.glob("*.md"))

    mode = "リセット＋再挿入" if reset else "リンク挿入"
    print(f"{mode}: 用語 {len(terms)} 語 / 記事 {len(targets)} 件")
    updated = 0

    for path in targets:
        content  = path.read_text(encoding="utf-8")
        fm, body = split_frontmatter(content)

        if reset:
            body = undo_glossary_links(body)

        new_body    = process_body(body, term_map, combined)
        new_content = fm + new_body

        if new_content != content:
            path.write_text(new_content, encoding="utf-8")
            print(f"  更新: {path.name}")
            updated += 1

    print(f"\n完了: {updated}/{len(targets)} 件を更新しました。")


if __name__ == "__main__":
    main()
