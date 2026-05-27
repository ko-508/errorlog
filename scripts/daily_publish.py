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

# ⑦ 静的な指示部分をシステムプロンプトに分離してキャッシュ対象にする
_ARTICLE_SYSTEM_PROMPT = """あなたは「ErrorLog（errorlog.jp）」専任のテクニカルライターです。
開発・運用中にエラーコードに直面した日本人エンジニアへ、原因と解決策を的確に解説する記事を執筆します。

## 記事の要件
- Markdown形式で書く（H2見出しのみ使用）
- H1タイトル行は含めない（フロントマターで設定するため）
- 冒頭に1〜2文でエラーの概要を書く
- 「よくある原因」セクション：各原因を具体的に説明する（なぜそうなるかを必ず書く）
- 「解決手順」セクション：各ステップに具体的なコマンドや設定例をコードブロックで示す
- ツール固有のコマンド・設定ファイル名・UIの場所（例：「Cloud Console → IAM → ...」）を明記する
- 「それでも解決しない場合」セクションを最後に追加する
- 全体で1200〜1800文字程度
- 難しい英語用語には括弧で日本語補足を添える（例：「ペイロード（リクエストの本体データ）」）
- ただし Docker、API、JSON のような一般語への補足は不要

## 文体
- ですます調で書く
- 断定的に書く（「できます」より「します」）
- 読者は「エラーが出て焦っている日本人エンジニア」

## コードブロック
- 言語名を必ず指定する（bash, python, yaml, json, javascript 等）
- プレースホルダーは `<your-project-id>` 形式で示す
- コメントは日本語で書く

記事本文のみを出力してください。前置きや説明文は不要です。"""


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
        meaning_short = meaning_text if len(meaning_text) <= 45 else meaning_text[:45] + "…"
        cause_hint = causes_list[0][:30] if causes_list else ""
        description = f"{meaning_short}。{cause_hint}など、{tool} {code} エラーの原因と解決策を解説。"
        description = description[:120]
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
