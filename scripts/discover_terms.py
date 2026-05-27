"""
content/posts/ の記事を走査して terms.json に未登録の技術用語を抽出し、
Claude API でフィルタリングして追記する。
weekly_glossary.yml の前段として実行される想定。
"""

import json
import re
from collections import Counter
from pathlib import Path

import anthropic
import os

BASE = Path(__file__).parent
POSTS_DIR = BASE.parent / "content" / "posts"
TERMS_PATH = BASE / "terms.json"

# 抽出対象パターン
# カタカナ語（3文字以上）・英大文字略語（2〜6文字）・よく使う英単語
KATAKANA_RE = re.compile(r"[ァ-ヶー]{3,}")
ACRONYM_RE = re.compile(r"\b[A-Z]{2,6}\b")
# フロントマターを除外するため --- 区切りを読み飛ばす
FRONTMATTER_RE = re.compile(r"^---.*?---\s*", re.DOTALL)

# 除外リスト（一般すぎる・用語集不要）
STOP_WORDS = {
    "エラー", "コード", "ページ", "サービス", "ユーザー", "データ",
    "ファイル", "フォルダ", "システム", "アプリ", "サーバー", "クライアント",
    "メッセージ", "ログ", "パス", "URL", "ID", "OK", "NG", "UI", "OS",
    "PC", "IT", "IP", "HTTP", "NULL", "EOF", "AND", "NOT", "FOR",
    "THE", "GET", "SET", "PUT", "POST", "AWS", "GCP", "API",
}


def load_terms() -> dict:
    return json.loads(TERMS_PATH.read_text(encoding="utf-8"))


def save_terms(terms: dict) -> None:
    TERMS_PATH.write_text(
        json.dumps(terms, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def extract_candidates(existing: set) -> list[tuple[str, int]]:
    """記事から候補用語を抽出して頻度順に返す。"""
    counter = Counter()
    for path in POSTS_DIR.glob("*.md"):
        text = FRONTMATTER_RE.sub("", path.read_text(encoding="utf-8"))
        # コードブロックを除外
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)

        for m in KATAKANA_RE.findall(text):
            if m not in existing and m not in STOP_WORDS:
                counter[m] += 1
        for m in ACRONYM_RE.findall(text):
            if m not in existing and m not in STOP_WORDS:
                counter[m] += 1

    # 2記事以上に出現するものに絞る
    return [(t, c) for t, c in counter.most_common(60) if c >= 2]


def filter_with_claude(client: anthropic.Anthropic, candidates: list[str]) -> list[str]:
    """Claude に「用語集に載せる価値があるか」を判定させる。"""
    if not candidates:
        return []

    listed = "\n".join(f"- {t}" for t in candidates)
    prompt = f"""以下は日本語技術記事（エラー解決ガイド）から抽出された用語候補です。
用語集に解説ページを作る価値がある用語だけを選んでください。

## 選ぶ基準
- エンジニア初心者が「意味を知りたい」と思いそうな技術用語
- ツール名・プロトコル名・設計概念など

## 除外する基準
- 一般的すぎて説明不要（「テスト」「設定」「確認」など）
- 固有名詞すぎて汎用性がない（特定バージョン番号など）
- すでに自明な略語

## 候補
{listed}

選んだ用語を1行1語で列挙してください。前置き・説明不要。"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    lines = message.content[0].text.strip().splitlines()
    return [l.lstrip("- •・").strip() for l in lines if l.strip()]


def main() -> None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("エラー: ANTHROPIC_API_KEY が設定されていません。")
        return

    client = anthropic.Anthropic(api_key=api_key)

    terms = load_terms()
    existing = set(terms.keys())

    print("記事から用語候補を抽出中...")
    candidates = extract_candidates(existing)

    if not candidates:
        print("新しい用語候補が見つかりませんでした。")
        return

    print(f"候補 {len(candidates)} 語:")
    for term, count in candidates[:20]:
        print(f"  {term}: {count}回")

    candidate_terms = [t for t, _ in candidates]

    print("\nClaude でフィルタリング中...")
    approved = filter_with_claude(client, candidate_terms)

    # 既存にないものだけ追加
    added = []
    for term in approved:
        if term not in terms:
            terms[term] = term  # 読み仮名は term 名そのまま（scan_glossary が使う）
            added.append(term)

    if added:
        save_terms(terms)
        print(f"\n{len(added)} 語を terms.json に追加しました:")
        for t in added:
            print(f"  + {t}")
    else:
        print("\n追加すべき新用語はありませんでした。")


if __name__ == "__main__":
    main()
