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


def send_publish_report(published_count: int, remaining_count: int) -> None:
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    body = (
        f"{now} に {published_count} 記事を公開しました。\n\n"
        f"残りキュー: {remaining_count} 件\n"
        f"https://errorlog.jp/"
    )
    _send_gmail(
        f"[ErrorLog] {published_count} 記事を公開しました（残り {remaining_count} 件）",
        body,
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

def generate_article(client: anthropic.Anthropic, row: dict) -> str:
    """Claude API を使って高品質な記事本文を生成する。"""
    tool = row["tool"].strip()
    code = row["status_code"].strip()
    meaning = row["official_meaning"].strip()
    causes = [c.strip() for c in row["causes"].split("|") if c.strip()]
    solutions = [s.strip() for s in row["solutions"].split("|") if s.strip()]

    causes_text = "\n".join(f"- {c}" for c in causes)
    solutions_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(solutions))

    prompt = f"""あなたは日本人向けの開発者向けテクニカルライターです。
以下の情報をもとに、**{tool} の {code} エラー**についての解説記事を日本語で書いてください。

## 基本情報
- ツール: {tool}
- エラーコード: {code}
- 公式の意味: {meaning}
- よくある原因:
{causes_text}
- 解決策:
{solutions_text}

## 記事の要件
- Markdown形式で書く（H2見出しを使う）
- H1タイトル行は**含めない**（フロントマターで設定するため）
- 冒頭に1〜2文でエラーの概要を説明する
- 「よくある原因」セクションでは、各原因を具体的に説明する（なぜそうなるか）
- 「解決手順」セクションでは、各ステップに**具体的なコマンドや設定例**をコードブロックで示す
- ツール固有のコマンド・設定ファイル名・UIの場所を明記する
- 最後に「それでも解決しない場合」のセクションを追加する
- 全体で600〜900文字程度
- 難しい英語用語には括弧で日本語説明を添える
- 読者は「エラーが出て焦っている日本人エンジニア」を想定する

記事本文のみを出力してください（前置きや説明は不要）。"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
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
        description = f"{tool} の {code} エラーの原因と解決策をわかりやすく解説します。"
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

        out.write_text(frontmatter + body, encoding="utf-8")
        print(f"  公開: {filename}  →  {title}")
        published_count += 1

    # キューを更新
    fieldnames = ["tool", "status_code", "official_meaning", "causes", "solutions"]
    with open(QUEUE_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(remaining)

    print(f"\n{published_count} 件を公開しました。残りキュー: {len(remaining)} 件")

    if published_count > 0:
        send_publish_report(published_count, len(remaining))

    if len(remaining) < LOW_STOCK_THRESHOLD:
        send_low_stock_alert(len(remaining))


if __name__ == "__main__":
    main()
