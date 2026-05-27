"""
用語集ページの品質チェックと再生成。
- ASCII 文字が混入した見出し（例：「もう letterいえ詳しく」）を検出
- 文字数が極端に少ないページを検出
- 問題ページを Claude API で再生成する
GitHub Actions から実行される想定（週次 weekly_glossary.yml の前段）。
"""

import json
import os
import re
from pathlib import Path

import anthropic

BASE = Path(__file__).parent
GLOSSARY_DIR = BASE.parent / "content" / "glossary"
TERMS_PATH = BASE / "terms.json"

MIN_CHARS = 200   # これ未満は短すぎと判定
BATCH = int(os.getenv("REPAIR_BATCH", "10"))   # 1回の上限

# 見出しに ASCII 英字が混入しているパターン（日本語の見出しに英単語が混ざる）
BAD_HEADING_RE = re.compile(r"^##\s+.*[a-zA-Z]{3,}.*[ぁ-んァ-ン]|^##\s+.*[ぁ-んァ-ン].*[a-zA-Z]{3,}", re.MULTILINE)

_SYSTEM_PROMPT = """あなたは日本人向けのわかりやすい技術用語解説ライターです。
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
- 見出しは必ず **日本語** で書く（英語を混ぜない）
- 全体で400〜600文字程度
- 記事本文のみ出力（前置き不要）"""


def is_bad(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    body = re.sub(r"^---.*?---\s*", "", text, flags=re.DOTALL)
    if len(body.strip()) < MIN_CHARS:
        return True
    if BAD_HEADING_RE.search(body):
        return True
    return False


def extract_term(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    m = re.search(r'title:\s*"(.+?)とは？', text)
    return m.group(1) if m else path.stem


def regenerate(client: anthropic.Anthropic, term: str) -> str:
    prompt = _SYSTEM_PROMPT.replace("{term}", term)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def split_frontmatter(content: str) -> tuple[str, str]:
    if not content.startswith("---"):
        return "", content
    end = content.find("\n---\n", 3)
    if end == -1:
        return "", content
    return content[: end + 5], content[end + 5:]


def main() -> None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY が設定されていません。")
        return

    client = anthropic.Anthropic(api_key=api_key)

    bad_files = [
        p for p in sorted(GLOSSARY_DIR.glob("*.md"))
        if p.name != "_index.md" and is_bad(p)
    ]

    if not bad_files:
        print("品質不良ページはありません。")
        return

    print(f"品質不良: {len(bad_files)} 件（今回は最大 {BATCH} 件修正）")
    targets = bad_files[:BATCH]

    fixed = 0
    for path in targets:
        term = extract_term(path)
        print(f"  再生成: {term} ({path.name})")
        try:
            body = regenerate(client, term)
        except Exception as e:
            print(f"    APIエラー: {e}")
            continue

        original = path.read_text(encoding="utf-8")
        fm, _ = split_frontmatter(original)
        path.write_text(fm + body, encoding="utf-8")
        fixed += 1

    print(f"\n{fixed} 件を再生成しました。")


if __name__ == "__main__":
    main()
