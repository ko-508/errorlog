"""
content/posts/ の記事を定期的にチェックし、古くなったものを Claude API で最新版に更新する。
3ヶ月（90日）に一度 GitHub Actions から実行される想定。

動作：
  1. 全記事のフロントマターから date / lastmod を確認
  2. REFRESH_DAYS 日以上更新されていない記事を抽出
  3. Claude API で内容を最新情報に基づいてリライト
  4. frontmatter の lastmod を今日の日付に更新して保存
"""

import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import anthropic

REFRESH_DAYS = int(os.getenv("REFRESH_DAYS", "90"))
MAX_REFRESH = int(os.getenv("MAX_REFRESH", "20"))  # 1回の実行で更新する最大記事数

BASE = Path(__file__).parent
POSTS_DIR = BASE.parent / "content" / "posts"


def parse_frontmatter(text: str) -> dict:
    """Markdownのフロントマターをパースして辞書で返す。"""
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return {}
    fm = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip().strip('"')
    return fm


def update_frontmatter(text: str, key: str, value: str) -> str:
    """フロントマターの特定キーを更新または追加する。"""
    # 既存キーの更新
    updated = re.sub(
        rf'^{key}:.*$',
        f'{key}: {value}',
        text,
        flags=re.MULTILINE,
    )
    # キーが存在しなかった場合は追加
    if f"{key}:" not in updated:
        updated = updated.replace("---\n\n", f"---\n{key}: {value}\n\n", 1)
    return updated


def get_body(text: str) -> str:
    """フロントマターを除いた本文を返す。"""
    match = re.match(r"^---\n.*?\n---\n\n?", text, re.DOTALL)
    if match:
        return text[match.end():]
    return text


def get_frontmatter_block(text: str) -> str:
    """フロントマター部分（---〜---）を返す。"""
    match = re.match(r"^(---\n.*?\n---\n)", text, re.DOTALL)
    return match.group(1) if match else ""


def needs_refresh(fm: dict, threshold_days: int) -> bool:
    """記事が更新期限を超えているか判定する。"""
    check_key = fm.get("lastmod") or fm.get("date")
    if not check_key:
        return True
    try:
        last_date = datetime.strptime(check_key, "%Y-%m-%d").date()
        return (date.today() - last_date).days >= threshold_days
    except ValueError:
        return True


def refresh_article(client: anthropic.Anthropic, title: str, old_body: str) -> str:
    """Claude API で記事本文を最新情報に基づきリライトする。"""
    prompt = f"""以下は「{title}」というタイトルの技術記事です。
内容を以下の観点でリライトしてください。

## リライトの要件
- 情報が古くなっている可能性のある部分を最新の状況に合わせて修正する
- コマンドや設定例が現在の標準的な書き方になっているか確認して修正する
- 読者はIT初心者・非エンジニアも含むため、できるだけ平易な日本語にする
- 専門用語には括弧で補足説明を加える
- Markdown形式を維持する（H2見出し、コードブロックなど）
- H1タイトル行は含めない
- 構成（見出し構造）は変えずに内容を更新する
- 文字数は元の記事と同程度（±20%以内）

## 元の記事
{old_body}

リライト後の本文のみを出力してください（前置き不要）。"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def main() -> None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("エラー: ANTHROPIC_API_KEY が設定されていません。")
        return

    client = anthropic.Anthropic(api_key=api_key)
    today = date.today().isoformat()

    md_files = sorted(POSTS_DIR.glob("*.md"))
    if not md_files:
        print("記事がありません。")
        return

    # 更新対象を抽出（古い順に並び替え）
    targets = []
    for md_path in md_files:
        text = md_path.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if needs_refresh(fm, REFRESH_DAYS):
            check_date = fm.get("lastmod") or fm.get("date") or "不明"
            targets.append((check_date, md_path))

    targets.sort(key=lambda x: x[0])  # 古い順
    targets = targets[:MAX_REFRESH]

    print(f"更新対象: {len(targets)} 件（閾値: {REFRESH_DAYS}日）\n")

    if not targets:
        print("更新が必要な記事はありません。")
        return

    refreshed, skipped = [], []

    for last_date, md_path in targets:
        text = md_path.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        title = fm.get("title", md_path.stem)
        old_body = get_body(text)

        print(f"  更新中: {md_path.name}（最終更新: {last_date}）...")
        try:
            new_body = refresh_article(client, title, old_body)
        except Exception as e:
            print(f"    APIエラー: {e}")
            skipped.append(md_path.name)
            continue

        # frontmatter に lastmod を更新
        fm_block = get_frontmatter_block(text)
        if "lastmod:" in fm_block:
            new_fm = re.sub(r"lastmod:.*", f"lastmod: {today}", fm_block)
        else:
            new_fm = fm_block.replace("---\n", f"---\nlastmod: {today}\n", 1)

        new_text = new_fm + "\n" + new_body
        md_path.write_text(new_text, encoding="utf-8")
        print(f"    完了: {title}")
        refreshed.append(md_path.name)

    print(f"\n完了: 更新 {len(refreshed)} 件 / スキップ {len(skipped)} 件")
    if skipped:
        print(f"スキップ: {', '.join(skipped)}")


if __name__ == "__main__":
    main()
