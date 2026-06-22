"""
Gemini + Google検索でトレンドの開発ツールを発見し tools.json に追加する。

検索対象:
  - Reddit: r/devops, r/programming, r/webdev, r/sysadmin, r/MachineLearning
  - X（旧Twitter）のテック系ハッシュタグ
  - Hacker News, GitHub Trending, Zenn, Qiita

実行:
  python scripts/discover_tools.py
"""

import json
import os
from pathlib import Path

from google import genai as google_genai
from google.genai import types as genai_types

BASE       = Path(__file__).parent
TOOLS_PATH = BASE / "tools.json"


def load_tools() -> list[str]:
    return json.loads(TOOLS_PATH.read_text(encoding="utf-8"))["tools"]


def save_tools(tools: list[str]) -> None:
    TOOLS_PATH.write_text(
        json.dumps({"tools": tools}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def discover_with_gemini(model, existing: list[str]) -> list[str]:
    """
    Gemini + Google検索でトレンドの開発ツールを発見する。
    """
    existing_str = "、".join(existing)

    prompt = f"""以下の情報源から、開発者がエラーやトラブルシュートで検索している
最新・トレンドの開発ツールを調べてください。

## 検索してほしい情報源
- Reddit: r/devops, r/programming, r/webdev, r/sysadmin, r/selfhosted, r/MachineLearning
- X（旧Twitter）のテック系トレンド・ハッシュタグ（#devops, #cloudnative, #llm, #aitools）
- Hacker News（Show HN, Ask HN）
- GitHub Trending（過去1ヶ月）
- Zenn・Qiita のトレンド記事

## 選定条件（すべてを満たすもののみ）
- HTTP エラー（4xx/5xx）が発生するツール（API・CLI・クラウドサービス等）
- 2024〜2025年に注目度・採用数が増加しているもの
- 日本人エンジニアも利用しているもの

## 需要フィルタリング（以下の基準を満たさないツールは除外）
以下のいずれかを実際に確認できるツールのみを選定してください：
- Reddit の関連スレッドで Upvote が 5 以上、またはコメントが 3 件以上ついている
- X（Twitter）で複数のユーザーが同じエラーを報告している、または言及数が一定以上ある
- Hacker News・GitHub Issues・Stack Overflow で同様の問題報告が複数確認できる
- Google 検索で「ツール名 エラー」「ツール名 error」の結果が十分に存在する

マイナーすぎて誰も検索しないツール、コミュニティでの問題報告が確認できないツールは除外してください。

## 既にカバー済み（追加不要）
{existing_str}

上記以外で追加すべきツールを15〜25個、ツール名のみを1行1語で列挙してください。
説明・番号・記号は不要です。"""

    try:
        response = model.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())]
            ),
        )
        lines = response.text.strip().splitlines()
        new_tools: list[str] = []
        for line in lines:
            # 記号・番号を除去してツール名だけ抽出
            tool = line.strip()
            tool = tool.lstrip("0123456789.-）)・ ")
            tool = tool.strip()
            if tool and tool not in existing and len(tool) >= 2:
                new_tools.append(tool)
        return new_tools
    except Exception as e:
        print(f"Gemini エラー: {e}")
        return []


def main() -> None:
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        print("エラー: GEMINI_API_KEY が設定されていません。")
        return

    gemini_client = google_genai.Client(api_key=gemini_key)

    existing = load_tools()
    print(f"既存ツール数: {len(existing)}")

    print("Gemini でトレンドツールを調査中...")
    new_tools = discover_with_gemini(gemini_client, existing)

    if not new_tools:
        print("新しいツールが見つかりませんでした。")
        return

    print(f"\n発見した新ツール ({len(new_tools)} 件):")
    for t in new_tools:
        print(f"  + {t}")

    updated = existing + [t for t in new_tools if t not in existing]
    save_tools(updated)
    print(f"\ntools.json を更新: {len(existing)} → {len(updated)} ツール")


if __name__ == "__main__":
    main()
