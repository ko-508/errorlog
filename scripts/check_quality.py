"""
投稿前品質チェック＆修正スクリプト。

Step 1 【最優先】Gemini + Google検索で事実確認
  - HTTPステータスコード・コマンド・技術仕様の正確性を検証
  - 誤り・古い情報を指摘

Step 2  Claude で全体修正（Gemini の指摘を最優先で反映）
  1. 事実性の担保
  2. 読者対象の最適化
  3. 構成の論理整合性
  4. 表記の厳格さ

実行:
  python scripts/check_quality.py                 # mtime 昇順（古い順）で BATCH 件
  python scripts/check_quality.py --newest 12     # mtime 降順（新しい順）で 12 件
  python scripts/check_quality.py path/to/file    # 1 ファイル指定
  BATCH=20 python scripts/check_quality.py        # バッチサイズ指定
"""

import os
import re
import sys
from pathlib import Path

import anthropic

BATCH = int(os.getenv("BATCH", "10"))

BASE      = Path(__file__).parent
POSTS_DIR = BASE.parent / "content" / "posts"

# ── Gemini（事実確認）────────────────────────────────────

def fact_check_with_gemini(title: str, body: str) -> str:
    """
    Gemini + Google検索で記事の技術的事実を確認する。
    誤りがあれば箇条書きで返し、なければ空文字を返す。
    """
    try:
        import google.generativeai as genai
        from google.generativeai.types import Tool
    except ImportError:
        return ""

    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        return ""

    genai.configure(api_key=gemini_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    prompt = f"""以下の日本語技術記事（エラーログ解説）の事実確認をしてください。

## 記事タイトル
{title}

## 記事内容（先頭1500文字）
{body[:1500]}

## 確認事項
1. HTTP ステータスコードの説明が正確か（例：「502 は認証エラー」は誤り → 「502 は Bad Gateway」）
2. コマンド・設定値・API パラメータが現在も正しいか
3. エラーの原因説明に技術的な誤りがないか
4. 推奨される解決策が現在も有効か

誤り・不正確な箇所のみを箇条書きで指摘してください。
問題がない場合は「問題なし」とだけ返してください。
説明や前置きは不要です。"""

    try:
        response = model.generate_content(
            prompt,
            tools=[Tool(google_search={})],
        )
        result = response.text.strip()
        return "" if result == "問題なし" else result
    except Exception as e:
        print(f"    Gemini エラー（スキップ）: {e}")
        return ""


# ── Claude（品質修正）────────────────────────────────────

_SYSTEM_PROMPT = """\
あなたは日本語技術記事（エラーログ解説サイト向け）の品質担当編集者です。
記事本文（Markdown フロントマターを除く）を以下の基準で修正してください。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
最優先 ▌ Gemini 事実確認の指摘を反映
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ユーザーメッセージに「## Gemini 事実確認の指摘」セクションがある場合、
その指摘を最優先で記事に反映してください。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
基準1 ▌ 事実性の担保
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
・HTTP ステータスコードが正しく使われているか確認する
  （例：「502 は認証エラー」→「502 は Bad Gateway」）
・コードブロック内のコマンド・構文に明らかな誤りがあれば修正する
・技術的事実の前後矛盾を修正する
・あいまいな断言（「必ず〜」「絶対に〜」）は「一般的に〜」等に緩和する

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
基準2 ▌ 読者対象の最適化
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
・専門用語・カタカナ語の初出時に簡潔な補足がなければ追加する
  補足は括弧内 15 文字以内（例：「冪等性（何度実行しても結果が同じ性質）」）
  ただし URL、コマンド名、固有名詞（Docker 等）は不要
・カタカナ語が 4 語以上連続する場合、一部を平易な日本語に言い換える

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
基準3 ▌ 構成の論理整合性
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
・「まとめ」等の結論段落が直前の内容の繰り返しなら削除する
・中身のない感想段落（「よくあるエラーです」等）は削除する
・前半の原因と後半の解決策が矛盾していれば修正する
・同じ説明が 2 回以上出てくる場合は 2 回目以降を削除する

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
基準4 ▌ 表記の厳格さ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
・末尾長音は「ー」あり（サーバー / フォルダー / コンテナー）
・「〜だ。」「〜である。」→「〜です。」（コードコメント内は変更しない）
・誤字・脱字・助詞の誤用を修正する
・「〜ですね！」「驚くべきことに」等の感情表現を削除する

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
出力ルール
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
・修正後の本文のみ出力する（フロントマターは含めない）
・修正が不要な場合は元の本文をそのまま出力する
・説明や前置きは一切書かない
"""


def check_and_fix(
    client: anthropic.Anthropic,
    body: str,
    gemini_findings: str,
) -> str:
    if gemini_findings:
        user_content = (
            f"## Gemini 事実確認の指摘（最優先で反映してください）\n"
            f"{gemini_findings}\n\n"
            f"## 記事本文\n{body}"
        )
    else:
        user_content = body

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8000,
        system=[{
            "type": "text",
            "text": _SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user_content}],
    )
    return message.content[0].text


# ── フロントマター分離 ──────────────────────────────────

def split_frontmatter(content: str) -> tuple[str, str]:
    if not content.startswith("---"):
        return "", content
    end = content.find("\n---\n", 3)
    if end == -1:
        return "", content
    return content[: end + 5], content[end + 5:]


def get_title(fm: str) -> str:
    m = re.search(r'^title:\s*"(.+?)"', fm, re.MULTILINE)
    return m.group(1) if m else ""


# ── メイン ────────────────────────────────────────────

def main() -> None:
    args    = sys.argv[1:]
    newest  = "--newest" in args
    n_count = BATCH

    # --newest N の N を取得
    for i, a in enumerate(args):
        if a == "--newest" and i + 1 < len(args):
            try:
                n_count = int(args[i + 1])
            except ValueError:
                pass

    file_args = [a for a in args if not a.startswith("--") and not a.lstrip("-").isdigit()]

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("エラー: ANTHROPIC_API_KEY が設定されていません。")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    # 対象ファイルの決定
    if file_args:
        targets = [Path(file_args[0])]
        if not targets[0].exists():
            print(f"ファイルが見つかりません: {targets[0]}")
            sys.exit(1)
    elif newest:
        # mtime 降順（新しい順）
        targets = sorted(
            POSTS_DIR.glob("*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:n_count]
    else:
        # mtime 昇順（古い順・バックログ消化用）
        targets = sorted(
            POSTS_DIR.glob("*.md"),
            key=lambda p: p.stat().st_mtime,
        )[:n_count]

    gemini_available = bool(os.getenv("GEMINI_API_KEY"))
    mode = f"{'新しい順' if newest else '古い順'} {n_count} 件 | Gemini={'あり' if gemini_available else 'なし'}"
    print(f"品質チェック開始: {mode}")
    fixed = 0

    for path in targets:
        print(f"\n  {path.name}")
        original = path.read_text(encoding="utf-8")
        fm, body = split_frontmatter(original)
        title    = get_title(fm)

        # Step 1: Gemini 事実確認（最優先）
        gemini_findings = ""
        if gemini_available:
            print(f"    [1/2] Gemini 事実確認中...")
            gemini_findings = fact_check_with_gemini(title, body)
            if gemini_findings:
                print(f"    → 指摘あり: {gemini_findings[:80]}...")
            else:
                print(f"    → 問題なし")

        # Step 2: Claude 修正
        tag = "[2/2]" if gemini_available else "[1/1]"
        print(f"    {tag} Claude 修正中...")
        fixed_body = check_and_fix(client, body, gemini_findings)

        new_content = fm + fixed_body
        if new_content.strip() == original.strip():
            print(f"    変更なし")
            continue

        path.write_text(new_content, encoding="utf-8")
        print(f"    修正済み")
        fixed += 1

    print(f"\n完了: {fixed}/{len(targets)} 件を修正しました。")


if __name__ == "__main__":
    main()
