"""
content/posts/ の記事を走査して頻出専門用語を抽出し、
用語集ページ（content/glossary/）を自動生成する。
毎週末に GitHub Actions から実行される想定。

優先順位:
  1. 既存 word 記事の「関連する言葉」セクションに登場し未作成の用語
  2. 全記事での出現頻度が高く未作成の用語
"""

import json
import os
import re
from collections import Counter
from pathlib import Path

import anthropic

TOP_COUNT = int(os.getenv("TOP_COUNT", "10"))

BASE = Path(__file__).parent
POSTS_DIR = BASE.parent / "content" / "posts"
GLOSSARY_DIR = BASE.parent / "content" / "glossary"
TERMS_PATH = BASE / "terms.json"


def load_term_list() -> dict:
    return json.loads(TERMS_PATH.read_text(encoding="utf-8"))


def save_term_list(terms: dict) -> None:
    TERMS_PATH.write_text(
        json.dumps(terms, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def safe_slug(term: str) -> str:
    """用語からURLスラグを生成する。"""
    slug = term.lower()
    slug = re.sub(r"[^a-z0-9぀-鿿]", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "term"


def collect_related_terms(existing_slugs: set) -> list[str]:
    """
    既存 word 記事の「関連する言葉」セクションから
    まだページのない用語を収集して返す（出現回数が多い順）。
    """
    counter: Counter = Counter()

    for md_path in GLOSSARY_DIR.glob("*.md"):
        if md_path.name == "_index.md":
            continue
        text = md_path.read_text(encoding="utf-8")

        # フロントマターを除去
        body = re.sub(r"^---.*?---\s*", "", text, flags=re.DOTALL)

        # 「関連する言葉」セクションを抜き出す
        m = re.search(
            r"^##\s*関連する言葉\s*\n(.*?)(?=\n##\s|\Z)",
            body,
            re.DOTALL | re.MULTILINE,
        )
        if not m:
            continue

        section = m.group(1)
        # **用語** または **用語**：説明 のパターンを抽出
        for term in re.findall(r"\*\*([^*\n]+)\*\*", section):
            term = term.strip()
            if term and safe_slug(term) not in existing_slugs:
                counter[term] += 1

    # 複数ページから参照されているものを優先
    return [term for term, _ in counter.most_common()]


def scan_terms() -> Counter:
    """全記事を走査して用語の出現頻度をカウントする。"""
    term_list = load_term_list()
    counter: Counter = Counter()
    md_files = list(POSTS_DIR.glob("*.md"))

    if not md_files:
        print("記事がまだありません。")
        return counter

    for md_path in md_files:
        text = md_path.read_text(encoding="utf-8")
        for term in term_list:
            if term in text:
                counter[term] += text.count(term)

    return counter


def generate_glossary_page(client: anthropic.Anthropic, term: str) -> str:
    """Claude API で用語解説ページの本文を生成する。"""
    prompt = f"""あなたは日本人向けのわかりやすい技術用語解説ライターです。
「{term}」という技術用語について、IT初心者や非エンジニアにもわかる解説ページを日本語で書いてください。

## 要件
- Markdown形式（H2見出しを使う）
- H1タイトル行は含めない
- 構成：
  1. 一言でいうと（1〜2文で超シンプルに説明）
  2. もう少し詳しく（具体的なたとえ話を使って説明）
  3. よく使われる場面（エラーログサイトの文脈で）
  4. 関連する言葉
- 中学生でもわかる言葉を使う
- 漢字にふりがな（読み仮名）を付けない（例：「処理（しょり）」のような表記は不要）
- 全体で400〜600文字程度
- 記事本文のみ出力（前置き不要）"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def main() -> None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("エラー: ANTHROPIC_API_KEY が設定されていません。")
        return

    client = anthropic.Anthropic(api_key=api_key)

    GLOSSARY_DIR.mkdir(parents=True, exist_ok=True)
    existing_slugs = {p.stem for p in GLOSSARY_DIR.glob("*.md") if p.stem != "_index"}

    force_all = os.getenv("FORCE_ALL", "0") == "1"

    if force_all:
        term_list = load_term_list()
        print("FORCE_ALL モード: 全用語を生成します...")
        to_create = [
            (term, safe_slug(term))
            for term in term_list
            if safe_slug(term) not in existing_slugs
        ]

    else:
        # ── 優先度 1: 既存 word 記事の「関連する言葉」から未作成の用語 ──
        print("既存 word 記事から「関連する言葉」を収集中...")
        related = collect_related_terms(existing_slugs)

        if related:
            print(f"  → 未作成の関連用語: {len(related)} 語")
            for t in related[:10]:
                print(f"    ★ {t}")
        else:
            print("  → なし")

        # ── 優先度 2: 記事内の出現頻度が高い未作成用語 ──
        print("\n記事を走査中...")
        counter = scan_terms()

        freq_candidates = []
        for term, count in counter.most_common():
            slug = safe_slug(term)
            if slug not in existing_slugs:
                freq_candidates.append((term, count))

        if freq_candidates:
            print(f"  → 頻出未作成用語 TOP10:")
            for t, c in freq_candidates[:10]:
                print(f"    {t}: {c}回")

        # ── マージ（関連語優先、重複排除、TOP_COUNT に絞る）──
        seen_slugs: set = set(existing_slugs)
        to_create: list = []

        for term in related:
            slug = safe_slug(term)
            if slug not in seen_slugs and len(to_create) < TOP_COUNT:
                to_create.append((term, slug))
                seen_slugs.add(slug)

        for term, _ in freq_candidates:
            slug = safe_slug(term)
            if slug not in seen_slugs and len(to_create) < TOP_COUNT:
                to_create.append((term, slug))
                seen_slugs.add(slug)

        # 新規に採用した関連語を terms.json に追加
        term_list = load_term_list()
        added_to_json = []
        for term, _ in to_create:
            if term not in term_list:
                term_list[term] = term
                added_to_json.append(term)
        if added_to_json:
            save_term_list(term_list)
            print(f"\nterms.json に {len(added_to_json)} 語を追加:")
            for t in added_to_json:
                print(f"  + {t}")

    if not to_create:
        print("\n新規作成が必要な用語ページはありません。")
        return

    print(f"\n{len(to_create)} 件の用語ページを生成します...")
    for i, (term, slug) in enumerate(to_create, 1):
        source = "★関連語" if i <= len([t for t in collect_related_terms(existing_slugs) if safe_slug(t) == slug or t == term]) else "頻出語"
        print(f"  [{i}/{len(to_create)}] {term} ...")
        try:
            body = generate_glossary_page(client, term)
        except Exception as e:
            print(f"    APIエラー: {e}")
            continue

        frontmatter = (
            f'---\n'
            f'title: "{term}とは？わかりやすく解説"\n'
            f'description: "{term}の意味をわかりやすく説明します。エラー解決に役立つ基本用語の解説です。"\n'
            f'tags: ["word"]\n'
            f'layout: "glossary"\n'
            f'---\n\n'
        )

        out = GLOSSARY_DIR / f"{slug}.md"
        out.write_text(frontmatter + body, encoding="utf-8")
        print(f"    作成: {out.name}")

    # _index.md がなければ作成
    index_path = GLOSSARY_DIR / "_index.md"
    if not index_path.exists():
        index_path.write_text(
            '---\n'
            'title: "用語集"\n'
            'description: "エラーログでよく出てくる技術用語をわかりやすく解説します。"\n'
            'layout: "list"\n'
            '---\n',
            encoding="utf-8",
        )

    print(f"\n完了: {len(to_create)} 件の用語ページを生成しました。")


if __name__ == "__main__":
    main()
