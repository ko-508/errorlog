"""
queue.csv から毎日 DAILY_COUNT 件取り出し、Claude API で記事を生成して
content/posts/ に追加する。GitHub Actions から実行される想定。
"""

import csv
import os
import re
import smtplib
from datetime import date
from email.mime.text import MIMEText
from pathlib import Path

import anthropic

DAILY_COUNT = int(os.getenv("DAILY_COUNT", "3"))

BASE = Path(__file__).parent
QUEUE_PATH = BASE / "queue.csv"
POSTS_DIR = BASE.parent / "content" / "posts"

LOW_STOCK_THRESHOLD = 10

TOOL_TAGS = {
    "docker_compose": "Docker Compose",
    "docker": "Docker",
    "aws_s3": "AWS S3",
    "aws_lambda": "AWS Lambda",
    "aws": "AWS",
    "firebase": "Firebase",
    "github_actions": "GitHub Actions",
    "github_api": "GitHub API",
    "openai_api": "OpenAI API",
    "kubernetes": "Kubernetes",
    "nginx": "Nginx",
    "stripe": "Stripe",
    "slack": "Slack",
    "gcp": "GCP",
    "podman": "Podman",
    "minikube": "Minikube",
    "azure": "Azure",
    "supabase": "Supabase",
    "vercel": "Vercel",
    "terraform": "Terraform",
    "ansible": "Ansible",
    "gitlab": "GitLab",
    "bitbucket": "Bitbucket",
    "postman": "Postman",
    "jenkins": "Jenkins",
    "circleci": "CircleCI",
    "prometheus": "Prometheus",
    "grafana": "Grafana",
    "datadog": "Datadog",
    "shopify": "Shopify",
    "zoom": "Zoom",
    "chatwork": "Chatwork",
    "freee": "freee",
    "base": "BASE",
}


# ─── メール通知 ────────────────────────────────────────────

def _send_gmail(subject: str, body: str) -> None:
    gmail_user = os.getenv("GMAIL_USER")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")
    if not gmail_user or not gmail_password:
        print("メール通知: GMAIL_USER / GMAIL_APP_PASSWORD 未設定のためスキップ")
        return
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = gmail_user
    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.starttls()
        smtp.login(gmail_user, gmail_password)
        smtp.send_message(msg)


def make_zenn_slug(stem: str) -> str:
    slug = "el-" + re.sub(r"[^a-z0-9]", "-", stem.lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:50] if len(slug) > 50 else slug


def send_publish_report(published_count: int, remaining_count: int, articles: list[dict]) -> None:
    from datetime import datetime, timezone, timedelta
    JST = timezone(timedelta(hours=9))
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
    lines = [f"{now} に {published_count} 記事を公開しました。\n"]
    for a in articles:
        zenn_slug = make_zenn_slug(a["stem"])
        lines.append(f"・{a['title']}")
        lines.append(f"  errorlog.jp: https://errorlog.jp/posts/{a['stem']}/")
        lines.append(f"  Zenn:        https://zenn.dev/errorlog/articles/{zenn_slug}\n")
    lines.append(f"残りキュー: {remaining_count} 件")
    _send_gmail(
        f"[ErrorLog] {published_count} 記事を公開しました（残り {remaining_count} 件）",
        "\n".join(lines),
    )
    print("公開通知メール送信済み")


def send_low_stock_alert(remaining_count: int) -> None:
    body = (
        f"ErrorLog のストック記事が残り {remaining_count} 件になりました。\n\n"
        f"scripts/queue.csv に新しい記事を追加してください。\n"
        f"https://github.com/ko-508/errorlog/blob/main/scripts/queue.csv"
    )
    _send_gmail(
        f"[ErrorLog] ストック残り {remaining_count} 記事 — 補充が必要です",
        body,
    )
    print(f"低ストック通知メール送信済み: 残り {remaining_count} 記事")


# ─── ユーティリティ ────────────────────────────────────────

def safe_filename(tool: str, code: str) -> str:
    name = f"{tool}_{code}".lower()
    return re.sub(r"[^a-z0-9_]", "_", name) + ".md"


def extract_tags(filename: str) -> list[str]:
    stem = Path(filename).stem
    for prefix, label in TOOL_TAGS.items():
        if stem.startswith(prefix):
            return [label]
    return []


# ─── Claude API で記事生成 ──────────────────────────────────

# ⑦ 静的な指示部分をシステムプロンプトに分離してキャッシュ対象にする
_ARTICLE_SYSTEM_PROMPT = """あなたは「ErrorLog（errorlog.jp）」専任のテクニカルライターです。
日本人エンジニア向けに、HTTPエラーの原因と解決策を実用的に解説する記事を執筆します。

## 必須セクション（この順番で記述）

### 1. エラーの概要（H2）
このエラーの公式な意味と、対象ツールでの典型的な発生状況を2〜3文で説明する。

### 2. 実際のエラーメッセージ例（H2）
対象ツールが実際に出力するエラーログ・JSONレスポンス・コンソール出力をコードブロックで1〜2個示す。

### 3. よくある原因と解決手順（H2）
原因ごとに「### 原因N：〇〇」(H3)で区切り、各原因に必ず以下のセットを含める:
- なぜ発生するかの説明
- Before/Afterコード対比（下記の**厳密な形式**で記述すること）:

**Before（エラーが起きるコード）：**

```言語名
# エラーが発生するコードや設定
```

**After（修正後）：**

```言語名
# 修正後のコードや設定
```

原因は最低3つ挙げる。

### 4. ツール固有の注意点（H2）
ツールの特性に応じた深掘りを記述する（サービス・設定ごとのパターン）。

### 5. それでも解決しない場合（H2）
確認すべきログの場所・デバッグコマンド・公式ドキュメントへの参照。

## 品質要件
- 全体で1500文字以上（日本語本文のみ。マークダウン記号・URL・コードは除いてカウント）
- H1タイトルは含めない
- コードブロックには必ず言語名を指定（bash, json, yaml, python, javascript等）
- プレースホルダーは `<your-xxx>` 形式
- ですます調・断定的に書く
- ふりがな補足は不要（「デプロイ（展開）」のような自明な言い換えは書かない）
- 「まとめ」セクションは不要
- 末尾に必ず以下の免責事項フッターを付ける:

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*

記事本文のみ出力してください。前置きは不要です。"""


def generate_article(client: anthropic.Anthropic, row: dict) -> str:
    """Claude API を使って記事本文を生成する（システムプロンプトキャッシュ使用）。"""
    tool = row["tool"].strip()
    code = row["status_code"].strip()
    meaning = row["official_meaning"].strip()
    causes = [c.strip() for c in row["causes"].split("|") if c.strip()]
    solutions = [s.strip() for s in row["solutions"].split("|") if s.strip()]

    causes_text = "\n".join(f"- {c}" for c in causes)
    solutions_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(solutions))

    user_prompt = f"""以下の情報をもとに **{tool} の {code} エラー** の解説記事を書いてください。

- ツール: {tool}
- エラーコード: {code}
- 公式の意味: {meaning}
- よくある原因:
{causes_text}
- 解決策:
{solutions_text}"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=3000,
        system=[{
            "type": "text",
            "text": _ARTICLE_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user_prompt}],
    )
    return message.content[0].text


# ─── メイン ───────────────────────────────────────────────

def main() -> None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("エラー: ANTHROPIC_API_KEY が設定されていません。")
        return

    client = anthropic.Anthropic(api_key=api_key)

    with open(QUEUE_PATH, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("キューが空です。scripts/queue.csv に記事を追加してください。")
        return

    to_publish = rows[:DAILY_COUNT]
    remaining = rows[DAILY_COUNT:]

    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    published_count = 0
    published_articles: list[dict] = []

    for row in to_publish:
        tool = row["tool"].strip()
        code = row["status_code"].strip()
        filename = safe_filename(tool, code)
        out = POSTS_DIR / filename

        if out.exists():
            print(f"SKIP {filename} （既に存在）")
            continue

        print(f"生成中: {tool} {code} ...")
        try:
            body = generate_article(client, row)
        except Exception as e:
            print(f"  API エラー: {e}")
            continue

        title = f"{tool} の {code} エラー：原因と解決策"
        meaning_text = row["official_meaning"].strip()
        causes_list = [c.strip() for c in row["causes"].split("|") if c.strip()]
        meaning_clean = meaning_text.rstrip("。．")
        if len(meaning_clean) > 60:
            meaning_clean = meaning_clean[:60].rstrip("。．、,")
        description = f"{meaning_clean}。{tool} {code} エラーの原因と解決策を解説します。"
        tags = extract_tags(filename)
        tags_line = 'tags: ["' + '", "'.join(tags) + '"]\n' if tags else ""

        frontmatter = (
            f'---\n'
            f'title: "{title}"\n'
            f'date: {today}\n'
            f'description: "{description}"\n'
            f'{tags_line}'
            f'errorCode: "{code}"\n'
            f'---\n\n'
        )

        disclaimer = (
            "\n\n---\n\n"
            "*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。"
            "ソフトウェアの仕様は予告なく変更されることがあります。"
            "最新の情報は各ツールの公式サポートページをご確認ください。"
            "本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*"
        )
        out.write_text(frontmatter + body + disclaimer, encoding="utf-8")
        print(f"  公開: {filename}  →  {title}")
        published_count += 1
        published_articles.append({"stem": out.stem, "title": title})

    # キューを更新
    fieldnames = ["tool", "status_code", "official_meaning", "causes", "solutions"]
    with open(QUEUE_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(remaining)

    print(f"\n{published_count} 件を公開しました。残りキュー: {len(remaining)} 件")

    if published_count > 0:
        send_publish_report(published_count, len(remaining), published_articles)

    if len(remaining) < LOW_STOCK_THRESHOLD:
        send_low_stock_alert(len(remaining))


if __name__ == "__main__":
    main()
