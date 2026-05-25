"""
queue.csv から毎日 DAILY_COUNT 件取り出してコンテンツを生成し content/posts/ に追加する。
GitHub Actions から実行される想定。
"""

import csv
import os
import re
import smtplib
from datetime import date
from email.mime.text import MIMEText
from pathlib import Path

DAILY_COUNT = int(os.getenv("DAILY_COUNT", "3"))

BASE = Path(__file__).parent
TEMPLATE_PATH = BASE / "template.md"
QUEUE_PATH = BASE / "queue.csv"
POSTS_DIR = BASE.parent / "content" / "posts"

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


LOW_STOCK_THRESHOLD = 10


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
        f"https://ko-508.github.io/errorlog/"
    )
    _send_gmail(
        f"[ErrorLog] {published_count} 記事を公開しました（残り {remaining_count} 件）",
        body,
    )
    print(f"公開通知メール送信済み")


def send_low_stock_alert(remaining_count: int) -> None:
    gmail_user = os.getenv("GMAIL_USER")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")
    if not gmail_user or not gmail_password:
        print("メール通知: GMAIL_USER / GMAIL_APP_PASSWORD 未設定のためスキップ")
        return

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


def safe_filename(tool: str, code: str) -> str:
    name = f"{tool}_{code}".lower()
    return re.sub(r"[^a-z0-9_]", "_", name) + ".md"


def format_list(raw: str, marker: str) -> str:
    items = [item.strip() for item in raw.split("|") if item.strip()]
    return "\n".join(f"{marker} {item}" for item in items)


def extract_tags(filename: str) -> list[str]:
    stem = Path(filename).stem
    for prefix, label in TOOL_TAGS.items():
        if stem.startswith(prefix):
            return [label]
    return []


def main() -> None:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

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

        content = (
            template
            .replace("{tool}", tool)
            .replace("{status_code}", code)
            .replace("{official_meaning}", row["official_meaning"].strip())
            .replace("{causes_list}", format_list(row["causes"], "-"))
            .replace("{solutions_list}", format_list(row["solutions"], "1."))
        )

        filename = safe_filename(tool, code)
        out = POSTS_DIR / filename

        # 既存ファイルがあればスキップ（重複防止）
        if out.exists():
            print(f"SKIP {filename} （既に存在）")
            continue

        # H1 と説明文を抽出
        title = f"{tool} の {code} エラー：原因と解決策"
        description = ""
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("> "):
                description = re.sub(r"\*+(.+?)\*+", r"\1", stripped[2:].strip())
                break

        # H1 を除いた本文
        lines = content.splitlines(keepends=True)
        body = content
        for i, line in enumerate(lines):
            if line.startswith("# "):
                rest = lines[i + 1:]
                while rest and rest[0].strip() == "":
                    rest.pop(0)
                body = "".join(rest)
                break

        tags = extract_tags(filename)
        tags_line = f'tags: ["' + '", "'.join(tags) + '"]\n' if tags else ""
        error_code = Path(filename).stem.split("_")[-1]

        frontmatter = (
            f'---\n'
            f'title: "{title}"\n'
            f'date: {today}\n'
            f'description: "{description}"\n'
            f'{tags_line}'
            f'errorCode: "{error_code}"\n'
            f'---\n\n'
        )

        out.write_text(frontmatter + body, encoding="utf-8")
        print(f"公開: {filename}  →  {title}")
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
