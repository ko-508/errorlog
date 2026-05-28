"""
投稿前品質チェック＆修正スクリプト。

品質基準:
  1. 事実性の担保     - HTTP ステータスコード・コードブロックの正確性
  2. 読者対象の最適化 - 専門用語多用・初出時の補足欠落
  3. 構成の論理整合性 - AI特有の繰り返し・まとめ段落・前後矛盾
  4. 表記の厳格さ     - 誤字・表記揺れ・助詞誤用・感情表現

実行方法:
  python scripts/check_quality.py               # mtime 昇順で BATCH 件処理
  python scripts/check_quality.py path/to/file  # 1 ファイル指定
  BATCH=5 python scripts/check_quality.py       # バッチサイズ指定
"""

import os
import re
import sys
from pathlib import Path

import anthropic

BATCH = int(os.getenv("BATCH", "10"))

BASE = Path(__file__).parent
POSTS_DIR = BASE.parent / "content" / "posts"

_SYSTEM_PROMPT = """\
あなたは日本語技術記事（エラーログ解説サイト向け）の品質担当編集者です。
以下の4基準に従い、記事本文（Markdownフロントマターを除く）を直接修正してください。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
基準1 ▌ 事実性の担保
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
・HTTP ステータスコードが正しく使われているか確認する
  （例：「502 は認証エラー」→「502 は Bad Gateway」）
・コードブロック内のコマンド・構文に明らかな誤りがあれば修正する
・技術的事実の前後矛盾（「タイムアウトは 200 を返す」等）を修正する
・あいまいな断言（「必ず〜」「絶対に〜」）は「一般的に〜」等に緩和する

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
基準2 ▌ 読者対象の最適化
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
・専門用語・カタカナ語の初出時に簡潔な補足がなければ追加する
  補足は括弧内 15 文字以内を目安に（例：「冪等性（何度実行しても結果が同じ性質）」）
  ただしURL、コマンド名、固有名詞（Docker、Kubernetes等）は補足不要
・カタカナ語が 4 語以上連続する場合、一部を平易な日本語に言い換える

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
基準3 ▌ 構成の論理整合性
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
・「まとめ」「以上」で始まる結論段落が直前の内容をそのまま繰り返している場合は削除する
・中身のない感想段落（「このエラーはよく遭遇します」「ぜひ活用してみてください」等）は削除する
・前半で述べた原因と後半の解決策が矛盾していれば修正する
・同じ説明が 2 回以上出てくる場合は 2 回目以降を削除する

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
基準4 ▌ 表記の厳格さ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【表記揺れ統一ルール】
・末尾長音は「ー」あり（サーバー / フォルダー / コンテナー / プロバイダー）
  ※ただし慣用的に「ー」なしが定着しているもの（コマンド、ユーザー等）はそのまま
・「〜ない」→「〜ません」（です・ます調に統一）
・「〜だ。」「〜である。」→「〜です。」（コードコメント内は変更しない）
・誤字・脱字・助詞の誤用（「〜をする」→「〜をします」等）を修正する

【感情表現の削除】
以下のような過度な感情・褒め言葉は削除または平易な表現に置き換える:
「〜ですね！」「驚くべきことに」「実は」「ぜひ〜してみてください」
「非常に便利」「とても重要」「ぜひ覚えておいてください」
→ 論理的・平易なトーンに統一する

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
出力ルール
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
・修正後の本文のみ出力する（フロントマターは含めない）
・修正が不要な場合は元の本文をそのまま出力する
・説明や前置きは一切書かない
"""


def split_frontmatter(content: str) -> tuple[str, str]:
    if not content.startswith("---"):
        return "", content
    end = content.find("\n---\n", 3)
    if end == -1:
        return "", content
    return content[: end + 5], content[end + 5:]


def check_and_fix(client: anthropic.Anthropic, body: str) -> str:
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8000,
        system=[{
            "type": "text",
            "text": _SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": body}],
    )
    return message.content[0].text


def process_file(client: anthropic.Anthropic, path: Path) -> bool:
    """1 ファイルを処理し、変更があれば上書き保存して True を返す。"""
    original = path.read_text(encoding="utf-8")
    fm, body = split_frontmatter(original)

    fixed_body = check_and_fix(client, body)

    new_content = fm + fixed_body
    if new_content.strip() == original.strip():
        print(f"  変更なし: {path.name}")
        return False

    path.write_text(new_content, encoding="utf-8")
    print(f"  修正済み: {path.name}")
    return True


def main() -> None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("エラー: ANTHROPIC_API_KEY が設定されていません。")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    # 対象ファイルの決定
    if len(sys.argv) > 1:
        targets = [Path(sys.argv[1])]
        if not targets[0].exists():
            print(f"ファイルが見つかりません: {targets[0]}")
            sys.exit(1)
    else:
        # mtime 昇順（最も長く放置されたファイル優先）
        targets = sorted(
            POSTS_DIR.glob("*.md"),
            key=lambda p: p.stat().st_mtime,
        )[:BATCH]

    if not targets:
        print("対象ファイルがありません。")
        return

    print(f"品質チェック開始: {len(targets)} 件")
    fixed = 0
    for path in targets:
        if process_file(client, path):
            fixed += 1

    print(f"\n完了: {fixed}/{len(targets)} 件を修正しました。")


if __name__ == "__main__":
    main()
