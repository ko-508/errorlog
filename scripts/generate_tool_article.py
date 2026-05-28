"""
ツール解説記事生成スクリプト。

Step 1: Gemini + Google検索でツールを調査
  - 特徴・できること
  - 料金プラン
  - 似たツールとの比較
  - 向いているユーザー・チーム

Step 2: Claude で日本語記事を執筆

実行:
  python scripts/generate_tool_article.py Slack
  python scripts/generate_tool_article.py "GitHub Actions"
"""

import os
import re
import sys
from datetime import date
from pathlib import Path

import anthropic
from google import genai as google_genai
from google.genai import types as genai_types

BASE      = Path(__file__).parent
POSTS_DIR = BASE.parent / "content" / "posts"

_WRITE_SYSTEM = """\
あなたは「ErrorLog（errorlog.jp）」専任のテクニカルライターです。
開発者向けにツールをわかりやすく解説する記事を執筆します。

## 記事の要件
- Markdown 形式（H2 見出しのみ使用）
- H1 タイトル行は含めない
- 構成：
  1. このツールとは（2〜3文で概要）
  2. 主な特徴・できること（箇条書き）
  3. 料金プラン（表形式か箇条書き）
  4. 似たツールとの比較（表形式を推奨）
  5. こんな人・チームに向いている
- 全体で 1500〜2000 文字
- ですます調・断定的に書く
- 「エラーログ」「トラブルシュート」の文脈に紐づけたコメントを1箇所入れる

## 制約
- ふりがなは付けない
- 「〜ですね！」等の感情表現は使わない
- 主観的な評価（「最高の〜」「革命的な〜」）は使わない

記事本文のみ出力してください。前置き不要。"""


def research_with_gemini(model, tool: str) -> str:
    prompt = f"""「{tool}」というツールについて以下を調べてください。

1. ツールの概要・目的（2〜3文）
2. 主な機能・特徴（5〜8個）
3. 料金プラン（無料プランの有無・有料プランの価格帯）
4. 競合・似たツール（3〜5個）と主な違い
5. 向いているユーザー・チーム規模

最新の公式情報をもとに、日本語で箇条書きでまとめてください。"""

    response = model.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())]
        ),
    )
    return response.text


def write_with_claude(client: anthropic.Anthropic, tool: str, research: str) -> str:
    prompt = f"""## Gemini によるリサーチ結果
{research}

## 執筆依頼
上記リサーチをもとに「{tool}」のツール解説記事を書いてください。"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=3000,
        system=[{
            "type": "text",
            "text": _WRITE_SYSTEM,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def safe_slug(tool: str) -> str:
    s = tool.lower()
    s = re.sub(r"[^a-z0-9]", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def main() -> None:
    if len(sys.argv) < 2:
        print("使い方: python scripts/generate_tool_article.py <ツール名>")
        sys.exit(1)

    tool = " ".join(sys.argv[1:])

    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    gemini_key    = os.getenv("GEMINI_API_KEY")
    if not anthropic_key:
        print("エラー: ANTHROPIC_API_KEY が必要です。")
        sys.exit(1)

    claude = anthropic.Anthropic(api_key=anthropic_key)

    research = ""
    if gemini_key:
        print(f"[1/2] Gemini で {tool} をリサーチ中...")
        try:
            gemini   = google_genai.Client(api_key=gemini_key)
            research = research_with_gemini(gemini, tool)
        except Exception as e:
            print(f"  Gemini スキップ（{e}）")
    else:
        print("[1/2] GEMINI_API_KEY なし → Gemini スキップ")

    step = "3/3" if gemini_key else "2/2"
    print(f"[{step}] Claude で記事を執筆中...")
    body = write_with_claude(claude, tool, research)

    slug  = safe_slug(tool)
    today = date.today().isoformat()
    fname = f"tool_{slug}.md"
    out   = POSTS_DIR / fname

    frontmatter = (
        f'---\n'
        f'title: "{tool} とは？特徴・機能・料金・比較まとめ"\n'
        f'date: {today}\n'
        f'description: "{tool} の特徴・できること・料金プラン・似たツールとの比較を解説。"\n'
        f'tags: ["tool-guide"]\n'
        f'---\n\n'
    )

    out.write_text(frontmatter + body, encoding="utf-8")
    print(f"\n生成完了: {out}")
    print(f"確認: cat {out}")


if __name__ == "__main__":
    main()
