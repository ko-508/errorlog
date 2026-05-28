"""
content/posts/ の記事を定期的にチェックし、古くなったものを
Gemini（リサーチ） → Claude（ライティング） の2段階で最新版に更新する。
3ヶ月（90日）に一度 GitHub Actions から実行される想定。

動作：
  1. 全記事のフロントマターから date / lastmod を確認
  2. REFRESH_DAYS 日以上更新されていない記事を抽出
  3. Gemini が Google検索で最新情報をリサーチ
  4. Claude がリサーチ結果をもとに記事をリライト
  5. frontmatter の lastmod を今日の日付に更新して保存
"""

import os
import re
from datetime import date, datetime
from pathlib import Path

import anthropic
from google import genai as google_genai
from google.genai import types as genai_types

REFRESH_DAYS = int(os.getenv("REFRESH_DAYS", "90"))
MAX_REFRESH = int(os.getenv("MAX_REFRESH", "20"))

BASE = Path(__file__).parent
POSTS_DIR = BASE.parent / "content" / "posts"


# ─── フロントマター操作 ────────────────────────────────────

def parse_frontmatter(text: str) -> dict:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return {}
    fm = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip().strip('"')
    return fm


def get_body(text: str) -> str:
    match = re.match(r"^---\n.*?\n---\n\n?", text, re.DOTALL)
    return text[match.end():] if match else text


def get_frontmatter_block(text: str) -> str:
    match = re.match(r"^(---\n.*?\n---\n)", text, re.DOTALL)
    return match.group(1) if match else ""


def needs_refresh(fm: dict, threshold_days: int) -> bool:
    check_key = fm.get("lastmod") or fm.get("date")
    if not check_key:
        return True
    try:
        last_date = datetime.strptime(check_key, "%Y-%m-%d").date()
        return (date.today() - last_date).days >= threshold_days
    except ValueError:
        return True


# ─── Step 1: Gemini でリサーチ ─────────────────────────────

def research_with_gemini(gemini_model, title: str, old_body: str) -> str:
    """Gemini + Google検索で記事テーマの最新情報を収集する。"""

    prompt = f"""以下のタイトルの技術記事を最新版にアップデートするためのリサーチをしてください。

## 記事タイトル
{title}

## 現在の記事内容
{old_body[:800]}

## リサーチしてほしいこと
1. 記事に登場するコマンドや設定が現在も正しいか確認する
2. 公式ドキュメントの最新URLや推奨手順を調べる
3. このエラーに関して最近変更された点・新しい解決策があれば調べる
4. 現在の標準的な対処方法をまとめる

調査結果を箇条書きでまとめてください。日本語で回答してください。"""

    try:
        response = gemini_model.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())]
            ),
        )
        return response.text
    except Exception as e:
        print(f"    Gemini リサーチエラー: {e}")
        return ""


# ─── Step 2: Claude でリライト ─────────────────────────────

def rewrite_with_claude(
    claude_client: anthropic.Anthropic,
    title: str,
    old_body: str,
    research: str,
) -> str:
    """Geminiのリサーチ結果をもとに Claude が記事をリライトする。"""

    research_section = f"""
## Gemini による最新情報リサーチ結果
{research}
""" if research else "（リサーチ結果なし：元の内容を改善してください）"

    prompt = f"""あなたは日本人向けの技術記事ライターです。
以下の「元の記事」を、「最新情報リサーチ結果」をもとに最新版にリライトしてください。

{research_section}

## 元の記事
{old_body}

## リライトの要件
- リサーチ結果で判明した最新情報・変更点を記事に反映する
- 古くなったコマンドや手順を最新の書き方に修正する
- 読者はIT初心者・非エンジニアも含むため、平易な日本語にする
- 専門用語には括弧で補足説明を加える（例：「API（外部サービスとのやり取り口）」）
- Markdown形式を維持する（H2見出し、コードブロックなど）
- H1タイトル行は含めない
- 構成（見出し構造）は変えずに内容を更新する
- 文字数は元の記事と同程度（±20%以内）

リライト後の本文のみを出力してください（前置き・説明は不要）。"""

    message = claude_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


# ─── メイン ───────────────────────────────────────────────

def main() -> None:
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    if not anthropic_key:
        print("エラー: ANTHROPIC_API_KEY が設定されていません。")
        return
    if not gemini_key:
        print("エラー: GEMINI_API_KEY が設定されていません。")
        return

    claude_client = anthropic.Anthropic(api_key=anthropic_key)
    gemini_client = google_genai.Client(api_key=gemini_key)
    gemini_model = gemini_client

    md_files = sorted(POSTS_DIR.glob("*.md"))
    if not md_files:
        print("記事がありません。")
        return

    # 更新対象を抽出（古い順）
    targets = []
    for md_path in md_files:
        text = md_path.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if needs_refresh(fm, REFRESH_DAYS):
            check_date = fm.get("lastmod") or fm.get("date") or "不明"
            targets.append((check_date, md_path))

    targets.sort(key=lambda x: x[0])
    targets = targets[:MAX_REFRESH]

    print(f"更新対象: {len(targets)} 件（閾値: {REFRESH_DAYS}日）\n")
    if not targets:
        print("更新が必要な記事はありません。")
        return

    today = date.today().isoformat()
    refreshed, skipped = [], []

    for last_date, md_path in targets:
        text = md_path.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        title = fm.get("title", md_path.stem)
        old_body = get_body(text)

        print(f"  処理中: {md_path.name}（最終更新: {last_date}）")

        # Step 1: Gemini でリサーチ
        print(f"    [1/2] Gemini がリサーチ中...")
        research = research_with_gemini(gemini_model, title, old_body)

        # Step 2: Claude でリライト
        print(f"    [2/2] Claude がリライト中...")
        try:
            new_body = rewrite_with_claude(claude_client, title, old_body, research)
        except Exception as e:
            print(f"    Claude エラー: {e}")
            skipped.append(md_path.name)
            continue

        # lastmod を更新して保存
        fm_block = get_frontmatter_block(text)
        if "lastmod:" in fm_block:
            new_fm = re.sub(r"lastmod:.*", f"lastmod: {today}", fm_block)
        else:
            new_fm = re.sub(r"\n---\n$", f"\nlastmod: {today}\n---\n", fm_block)

        md_path.write_text(new_fm + "\n" + new_body, encoding="utf-8")
        print(f"    完了: {title}")
        refreshed.append(md_path.name)

    print(f"\n完了: 更新 {len(refreshed)} 件 / スキップ {len(skipped)} 件")
    if skipped:
        print(f"スキップ: {', '.join(skipped)}")


if __name__ == "__main__":
    main()
