"""
content/posts/ の記事を走査して頻出専門用語を抽出し、
用語集ページ（content/glossary/）を自動生成する。
毎週末に GitHub Actions から実行される想定。

動作：
  1. 全記事をスキャンして用語リストと照合・頻度カウント
  2. 頻度上位 TOP_COUNT 語のうちページ未作成のものを抽出
  3. Claude API で用語解説ページを生成
  4. content/glossary/<term>.md として保存
"""

import os
import re
from collections import Counter
from pathlib import Path

import anthropic

TOP_COUNT = int(os.getenv("TOP_COUNT", "10"))

BASE = Path(__file__).parent
POSTS_DIR = BASE.parent / "content" / "posts"
GLOSSARY_DIR = BASE.parent / "content" / "glossary"

# 走査対象の専門用語リスト（用語 → 日本語読み）
TERM_LIST = {
    "API": "エーピーアイ",
    "JSON": "ジェイソン",
    "OAuth": "オーオース",
    "HTTP": "エイチティーティーピー",
    "HTTPS": "エイチティーティーピーエス",
    "REST": "レスト",
    "SDK": "エスディーケー",
    "CLI": "シーエルアイ",
    "IAM": "アイエーエム",
    "VPC": "ブイピーシー",
    "DNS": "ディーエヌエス",
    "SSL": "エスエスエル",
    "TLS": "ティーエルエス",
    "JWT": "ジェイダブリューティー",
    "CORS": "コルス",
    "CDN": "シーディーエヌ",
    "CI/CD": "シーアイシーディー",
    "Docker": "ドッカー",
    "Kubernetes": "クーバネティス",
    "コンテナ": "コンテナ",
    "クレデンシャル": "クレデンシャル",
    "トークン": "トークン",
    "エンドポイント": "エンドポイント",
    "ペイロード": "ペイロード",
    "スコープ": "スコープ",
    "レスポンス": "レスポンス",
    "リクエスト": "リクエスト",
    "ステータスコード": "ステータスコード",
    "デプロイ": "デプロイ",
    "リポジトリ": "リポジトリ",
    "ブランチ": "ブランチ",
    "マージ": "マージ",
    "コミット": "コミット",
    "環境変数": "かんきょうへんすう",
    "バケット": "バケット",
    "インスタンス": "インスタンス",
    "ロール": "ロール",
    "ポリシー": "ポリシー",
    "サービスアカウント": "サービスアカウント",
    "Webhook": "ウェブフック",
    "冪等性": "べきとうせい",
    "認証": "にんしょう",
    "認可": "にんか",
    "暗号化": "あんごうか",
    "レート制限": "レートせいげん",
    "スロットリング": "スロットリング",
    "バックオフ": "バックオフ",
    "ヘルスチェック": "ヘルスチェック",
    "ロードバランサー": "ロードバランサー",
    "Namespace": "ネームスペース",
    "マニフェスト": "マニフェスト",
    "RBAC": "アールバック",
    "サーバーレス": "サーバーレス",
    "コールドスタート": "コールドスタート",
    "マイクロサービス": "マイクロサービス",
    "プロキシ": "プロキシ",
    "バージョニング": "バージョニング",
    "YAML": "ヤムル",
    "gRPC": "ジーアールピーシー",
    "GraphQL": "グラフキューエル",
}


def safe_slug(term: str) -> str:
    """用語からURLスラグを生成する。"""
    slug = term.lower()
    slug = re.sub(r"[^a-z0-9぀-鿿]", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "term"


def scan_terms() -> Counter:
    """全記事を走査して用語の出現頻度をカウントする。"""
    counter = Counter()
    md_files = list(POSTS_DIR.glob("*.md"))

    if not md_files:
        print("記事がまだありません。")
        return counter

    for md_path in md_files:
        text = md_path.read_text(encoding="utf-8")
        for term in TERM_LIST:
            if term in text:
                counter[term] += text.count(term)

    return counter


def generate_glossary_page(client: anthropic.Anthropic, term: str) -> str:
    """Claude API で用語解説ページの本文を生成する。"""
    prompt = f"""あなたは日本人向けのわかりやすい技術用語解説ライターです。
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
- 専門用語が出たら括弧で補足する
- 全体で400〜600文字程度
- 記事本文のみ出力（前置き不要）"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def main() -> None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("エラー: ANTHROPIC_API_KEY が設定されていません。")
        return

    client = anthropic.Anthropic(api_key=api_key)

    print("記事を走査中...")
    counter = scan_terms()

    if not counter:
        print("対象用語が見つかりませんでした。")
        return

    print("\n頻出用語 TOP 20:")
    for term, count in counter.most_common(20):
        print(f"  {term}: {count}回")

    # 未作成ページの上位を抽出
    GLOSSARY_DIR.mkdir(parents=True, exist_ok=True)
    existing = {p.stem for p in GLOSSARY_DIR.glob("*.md") if p.stem != "_index"}

    to_create = []
    for term, count in counter.most_common():
        slug = safe_slug(term)
        if slug not in existing:
            to_create.append((term, slug))
        if len(to_create) >= TOP_COUNT:
            break

    if not to_create:
        print("\n新規作成が必要な用語ページはありません。")
        return

    print(f"\n{len(to_create)} 件の用語ページを生成します...")

    for term, slug in to_create:
        print(f"  生成中: {term} ...")
        try:
            body = generate_glossary_page(client, term)
        except Exception as e:
            print(f"    APIエラー: {e}")
            continue

        frontmatter = (
            f'---\n'
            f'title: "{term}とは？わかりやすく解説"\n'
            f'description: "{term}の意味をわかりやすく説明します。エラー解決に役立つ基本用語の解説です。"\n'
            f'layout: "glossary"\n'
            f'---\n\n'
        )

        out = GLOSSARY_DIR / f"{slug}.md"
        out.write_text(frontmatter + body, encoding="utf-8")
        print(f"    作成: {out.name}")

    # _index.md（用語集一覧ページ）がなければ作成
    index_path = GLOSSARY_DIR / "_index.md"
    if not index_path.exists():
        index_path.write_text(
            '---\n'
            'title: "用語集"\n'
            'description: "エラーログでよく出てくる技術用語をわかりやすく解説します。"\n'
            '---\n',
            encoding="utf-8",
        )
        print("\n用語集インデックスページを作成しました。")

    print(f"\n完了: {len(to_create)} 件の用語ページを生成しました。")


if __name__ == "__main__":
    main()
