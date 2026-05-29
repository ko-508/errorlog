"""
薄いコンテンツ（1200文字未満）の記事を Claude で拡張するスクリプト。

各記事に以下を必ず追加:
  - 実際のエラーメッセージ例（コードブロック）
  - Before/After コード例
  - ツール固有の深掘り解説

実行:
  ANTHROPIC_API_KEY=xxx python scripts/expand_articles.py
  MAX_EXPAND=10 ANTHROPIC_API_KEY=xxx python scripts/expand_articles.py
  FORCE=1 MAX_EXPAND=5 ANTHROPIC_API_KEY=xxx python scripts/expand_articles.py
"""

import os
import re
import sys
from datetime import date
from pathlib import Path

import anthropic

BASE      = Path(__file__).parent
POSTS_DIR = BASE.parent / "content" / "posts"

MAX_EXPAND     = int(os.getenv("MAX_EXPAND", "10"))
FORCE          = os.getenv("FORCE", "0") == "1"
MIN_CHARS      = 1200

_SYSTEM = """\
あなたは「ErrorLog（errorlog.jp）」専任のテクニカルライターです。
日本人エンジニア向けに、HTTPエラーの原因と解決策を実用的に解説する記事を執筆します。

## 必須セクション（この順番で記述）

### 1. エラーの概要（H2）
このエラーの公式な意味と、対象ツールでの典型的な発生状況を2〜3文で説明する。

### 2. 実際のエラーメッセージ例（H2）
対象ツールが実際に出力するエラーログ・JSONレスポンス・コンソール出力を
コードブロックで1〜2個示す。実在しそうなリアルな例を記述すること。

### 3. よくある原因と解決手順（H2）
各原因について:
- 「なぜ発生するか」の説明
- Before（エラーが起きる設定/コード/コマンド）のコードブロック
- After（修正後）のコードブロック
を必ずセットで記述する。原因は最低3つ挙げる。

### 4. ツール固有の注意点（H2）
ツールの特性に応じた深掘りを記述する。例:
- AWS: API Gateway / S3 / Cognito / Lambda など頻出サービスごとの原因
- Docker: Compose設定 / レジストリ認証 / ネットワーク設定
- Kubernetes: RBAC / ServiceAccount / Namespace の設定ミス
- Nginx: location設定 / upstream設定 / プロキシヘッダー
- Stripe: APIバージョン / Webhookの署名検証 / 冪等性キー
など、そのツールで実際によく起きるパターンを解説する。

### 5. それでも解決しない場合（H2）
- 確認すべきログの場所やデバッグコマンド
- 公式ドキュメントへの参照（具体的なページ名）
- コミュニティリソース（GitHub Issues等）

## 品質要件
- 全体で1500文字以上2500文字以下
- H1タイトルは含めない
- コードブロックには必ず言語名を指定（bash, json, yaml, python, javascript等）
- プレースホルダーは `<your-xxx>` 形式
- ですます調・断定的に書く
- ふりがな補足は不要
- 「まとめ」セクションは不要

記事本文のみ出力してください。前置きは不要です。"""


def parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm_text = text[3:end].strip()
    body    = text[end + 4:].lstrip("\n")
    fm: dict = {}
    for line in fm_text.splitlines():
        m = re.match(r'^(\w+):\s*(.+)', line)
        if m:
            fm[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return fm, body


def get_frontmatter_block(text: str) -> str:
    m = re.match(r"^(---\n.*?\n---\n)", text, re.DOTALL)
    return m.group(1) if m else ""


def body_char_count(body: str) -> int:
    text = re.sub(r'```[\s\S]*?```', '', body)       # コードブロック除去
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # リンク→テキストのみ
    text = re.sub(r'[#\-*`>\[\]()!]', '', text)
    return len(text.replace(' ', '').replace('\n', ''))


def needs_expand(body: str) -> bool:
    return body_char_count(body) < MIN_CHARS


def expand_with_claude(client: anthropic.Anthropic, title: str, tool: str, code: str, old_body: str) -> str:
    prompt = f"""## 記事情報
- タイトル: {title}
- ツール: {tool}
- エラーコード: {code}

## 現在の記事（参考）
{old_body[:600]}

## 執筆依頼
上記の「{tool} の {code} エラー」について、必須セクションをすべて含む完全な記事を執筆してください。
現在の記事の内容は参考程度に活用し、より詳細・実用的な内容に拡張してください。"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4000,
        system=[{
            "type": "text",
            "text": _SYSTEM,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def main() -> None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("エラー: ANTHROPIC_API_KEY が設定されていません。")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    today  = date.today().isoformat()

    posts = sorted(POSTS_DIR.glob("*.md"), key=lambda p: p.name)
    targets = []

    for src in posts:
        if src.name.startswith("_"):
            continue
        text = src.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)
        if fm.get("draft", "").lower() == "true":
            continue
        if FORCE or needs_expand(body):
            targets.append(src)

    print(f"拡張対象: {len(targets)} 件（閾値: {MIN_CHARS}文字未満）")
    targets = targets[:MAX_EXPAND]
    print(f"今回処理: {len(targets)} 件\n")

    expanded = 0
    skipped  = 0

    for src in targets:
        text = src.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)
        title = fm.get("title", src.stem)

        # ツール名とエラーコードをタイトルから抽出
        m = re.match(r'^(.+?) の (\d+) エラー', title)
        if m:
            tool = m.group(1)
            code = m.group(2)
        else:
            tool = fm.get("tags", src.stem.split("_")[0] if "_" in src.stem else src.stem)
            code = fm.get("errorCode", "")

        print(f"  処理中: {src.name}")
        try:
            new_body = expand_with_claude(client, title, tool, code, body)
        except Exception as e:
            print(f"  Claude エラー: {e}")
            skipped += 1
            continue

        char_count = body_char_count(new_body)
        print(f"  → {char_count} 文字")

        # frontmatter に lastmod を追加/更新
        fm_block = get_frontmatter_block(text)
        if "lastmod:" in fm_block:
            new_fm = re.sub(r"lastmod:.*", f"lastmod: {today}", fm_block)
        else:
            new_fm = re.sub(r"\n---\n$", f"\nlastmod: {today}\n---\n", fm_block)

        disclaimer = (
            "\n\n---\n\n"
            "*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。"
            "ソフトウェアの仕様は予告なく変更されることがあります。"
            "最新の情報は各ツールの公式サポートページをご確認ください。"
            "本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*"
        )

        src.write_text(new_fm + "\n" + new_body + disclaimer, encoding="utf-8")
        expanded += 1

    print(f"\n完了: {expanded} 件拡張 / {skipped} 件スキップ")


if __name__ == "__main__":
    main()
