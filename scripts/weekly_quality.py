"""
content/posts/ の記事を最大 BATCH_SIZE 件チェックし、
1. 自明な括弧言い換えの削除
2. 免責事項の追加（末尾にない場合）
3. 文体の統一（です・ます調）
を Claude API で修正して保存する。
GitHub Actions から実行される想定。
"""

import os
import re
from pathlib import Path

import anthropic

BATCH_SIZE = int(os.getenv("BATCH_SIZE", "20"))

BASE = Path(__file__).parent
POSTS_DIR = BASE.parent / "content" / "posts"

DISCLAIMER = (
    "\n\n---\n\n"
    "*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。"
    "ソフトウェアの仕様は予告なく変更されることがあります。"
    "最新の情報は各ツールの公式サポートページをご確認ください。"
    "本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*"
)

_SYSTEM_PROMPT = """あなたは日本語技術記事の校正者です。
与えられたMarkdown記事本文（フロントマターを除く）を以下のルールで修正してください。

## 修正ルール

### 1. 自明な括弧言い換えの削除
カタカナ語の直後に括弧で自明な日本語訳があるものを削除する。
- 削除する例：「リフレッシュ（更新）」→「リフレッシュ」、「デプロイ（展開）」→「デプロイ」、「コンテナ（容器）」→「コンテナ」、「エラー（誤り）」→「エラー」
- 残す例：「マニフェスト（設定ファイル群）」はエンジニアでも知らない場合があるので残す

### 2. 文体の統一
「です・ます」調に統一する。
- 「〜である。」→「〜です。」
- 「〜だ。」→「〜です。」（ただしコードコメントは変更しない）

## 出力
修正後の本文のみを返してください。フロントマターは含めないでください。
修正が不要な場合は元の本文をそのまま返してください。"""


def has_disclaimer(text: str) -> bool:
    return "免責事項" in text


def split_frontmatter(content: str) -> tuple[str, str]:
    """frontmatter と本文を分離する。"""
    if not content.startswith("---"):
        return "", content
    end = content.find("\n---\n", 3)
    if end == -1:
        return "", content
    fm = content[: end + 5]   # "---\n" を含む
    body = content[end + 5:]
    return fm, body


def fix_article(client: anthropic.Anthropic, body: str) -> str:
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4000,
        system=[{
            "type": "text",
            "text": _SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": body}],
    )
    return message.content[0].text


def main() -> None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("エラー: ANTHROPIC_API_KEY が設定されていません。")
        return

    client = anthropic.Anthropic(api_key=api_key)

    files = sorted(POSTS_DIR.glob("*.md"))[:BATCH_SIZE]
    if not files:
        print("記事が見つかりません。")
        return

    fixed_count = 0

    for path in files:
        original = path.read_text(encoding="utf-8")
        fm, body = split_frontmatter(original)

        # 免責事項チェック
        needs_disclaimer = not has_disclaimer(original)

        # Claude で本文を修正
        fixed_body = fix_article(client, body)

        # 免責事項を末尾に追加
        if needs_disclaimer:
            fixed_body = fixed_body.rstrip() + DISCLAIMER

        new_content = fm + fixed_body

        if new_content != original:
            path.write_text(new_content, encoding="utf-8")
            print(f"修正: {path.name}")
            fixed_count += 1
        else:
            print(f"変更なし: {path.name}")

    print(f"\n合計 {fixed_count} 件修正しました。")


if __name__ == "__main__":
    main()
