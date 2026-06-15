"""
queue.csv から毎日 DAILY_COUNT 件取り出し、Claude API で記事を生成して
content/posts/ に追加する。GitHub Actions から実行される想定。
"""

import csv
import json
import os
import re
import smtplib
from datetime import date
from email.mime.text import MIMEText
from pathlib import Path

import anthropic

from fact_check import clear_new_article_failure, evaluate_new_article, record_new_article_failure
from lint_articles import (
    ARTICLE_CATEGORY_ERROR,
    check_a1, check_a2, check_a3, check_a4, check_a5, check_a6,
    check_b1, check_b2, check_b3, check_d1_d2, check_secret_token, check_aws_secret_key,
    classify_article, split_frontmatter,
)

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


# ─── Before/After ラベル正規化 ──────────────────────────────────

_BEFORE_LABEL_RE = re.compile(
    r'(?m)^'
    r'(?:#{1,4}[ \t]+|\*\*)?'
    r'(?:Before|before|修正前|エラーが起きる[^ \t\n（(]*)'
    r'(?:[ \t]*[（(][^）)\n]*[）)])?'
    r'[ \t]*[：:]?[ \t]*\*{0,2}[ \t]*$'
)
_AFTER_LABEL_RE = re.compile(
    r'(?m)^'
    r'(?:#{1,4}[ \t]+|\*\*)?'
    r'(?:After|after|修正後[^ \t\n（(]*)'
    r'(?:[ \t]*[（(][^）)\n]*[）)])?'
    r'[ \t]*[：:]?[ \t]*\*{0,2}[ \t]*$'
)
_BEFORE_NORM = '**Before（エラーが起きるコード）：**'
_AFTER_NORM  = '**After（修正後）：**'


def normalize_before_after(text: str) -> str:
    """コードブロック外の Before/After ラベルを統一フォーマットに正規化する。"""
    parts = re.split(r'(```[\s\S]*?```)', text)
    for i, part in enumerate(parts):
        if i % 2 == 0:
            part = _BEFORE_LABEL_RE.sub(_BEFORE_NORM, part)
            part = _AFTER_LABEL_RE.sub(_AFTER_NORM, part)
            parts[i] = part
    return ''.join(parts)


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

## 認証トークン・APIキーの書き方
- コード例の変数値・ヘッダー値・文字列リテラルとして、認証トークンやAPIキーを
  実際の値らしい形式で記述しないこと。これはBefore例・After例・失効例など
  すべてのコード例に適用される。
- トークンやキーに当たる部分は、必ず山かっこで囲んだプレースホルダー
  `<your-xxx>` 形式で書くこと。プレフィックス文字列(例: xoxb-、sk-proj-、
  pk_live_、AKIA、ghp_、glpat- など)を値の先頭に付けた形も書かないこと。
  例:  token = "xoxb-old-expired-token-123"  → NG(プレフィックス＋それらしい値)
       token = "xoxb-YOUR-TOKEN"             → NG(プレフィックスを含む)
       token = "<your-bot-token>"            → OK
       TOKEN = "<your-api-key>"              → OK

- 末尾に必ず以下の免責事項フッターを付ける:

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*

記事本文のみ出力してください。前置きは不要です。"""


def generate_article(client: anthropic.Anthropic, row: dict, lint_feedback: str = "") -> str:
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

    if lint_feedback:
        user_prompt += (
            "\n\n## 前回生成で検出された構造エラー（必ず全て修正すること）\n"
            + lint_feedback
            + "\n\n上記エラーを修正の上、必須セクションが全て揃った完全な記事を執筆してください。"
        )

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


_KNOWLEDGE_GRAPH_SYSTEM = (
    "あなたは技術記事からメタデータを抽出するエージェントです。"
    "記事内容を分析し、指定フィールドを JSON で返してください。"
    "推測は禁止。記事本文に明記されている情報のみを抽出すること。"
    "明記されていない情報は空配列または空文字にすること。"
)

# Phase 3: コンポーネント抽出のヒント（記事本文に明記されている場合のみ使用）
_COMPONENT_HINTS = """
## components 抽出ヒント（最重要フィールド）
記事本文に以下のコンポーネント名が登場する場合のみ抽出すること。

AWS: IAM, STS, S3, Lambda, CloudFront, Route53, EC2, RDS, ECS, EKS, API Gateway, Cognito, KMS
GitHub: Actions, Runner, Packages, Container Registry, Codespaces, Apps
Terraform: Provider, Backend, State, Module, Workspace, Registry
Docker: Compose, BuildKit, Registry, Swarm, Desktop
Kubernetes: Pod, Deployment, Ingress, Service, ConfigMap, Secret, Namespace, HPA
Firebase: Firestore, Auth, Functions, Storage, Hosting, Realtime Database, AppCheck
Cloudflare: Workers, Pages, R2, D1, KV, Tunnel, DNS

上記以外のコンポーネントも本文に明記されていれば抽出してよい。
ただし推測は禁止。本文に文字として現れているものだけを返すこと。
""".strip()


def extract_knowledge_graph(
    client: anthropic.Anthropic,
    title: str,
    body: str,
    tool: str,
    code: str,
) -> dict:
    """記事本文からエラー知識グラフ用メタデータを抽出する（Phase 2+3）。

    body は先頭 3000 文字を使用（精度向上のため 1000 文字から拡張）。
    Returns dict with keys: service, error_type, components, related_services
    """
    prompt = f"""記事「{title}」から以下のメタデータを抽出してください。

## 記事本文（先頭3000文字）
{body[:3000]}

{_COMPONENT_HINTS}

## 抽出するフィールド
- service: 主要サービス名（例: "Terraform", "AWS", "GitHub Actions"）。1つのみ。
- error_type: エラーコード（例: "403", "503", "RESOURCE_EXHAUSTED"）。1つのみ。
- components: 記事本文に登場するサービス内コンポーネント名のリスト。空なら []。
- related_services: 記事本文に登場する関連サービス・ツール名のリスト。空なら []。

## 出力フォーマット（JSON のみ。説明不要）
{{
  "service": "{tool}",
  "error_type": "{code}",
  "components": [],
  "related_services": []
}}"""

    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=_KNOWLEDGE_GRAPH_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        # JSON ブロックを抽出
        m = re.search(r'\{[\s\S]*\}', raw)
        if m:
            data = json.loads(m.group(0))
            return {
                "service":          str(data.get("service", tool)),
                "error_type":       str(data.get("error_type", code)),
                "components":       data.get("components", []) or [],
                "related_services": data.get("related_services", []) or [],
            }
    except Exception as e:
        print(f"  [knowledge_graph] 抽出エラー（スキップ）: {e}")
    return {
        "service": tool,
        "error_type": code,
        "components": [],
        "related_services": [],
    }


# ─── Lint 公開前ゲート ──────────────────────────────────────────

_LINT_MAX_RETRIES = 2
_LINT_BLOCK_RULES = frozenset({"A1", "B1", "B2", "C1"})


def _lint_check_content(content: str, path: Path) -> dict:
    """記事コンテンツ文字列に lint_article と同等のチェックを実行する（ファイル書き込みなし）。"""
    fm, body = split_frontmatter(content)
    is_error = classify_article(path, fm) == ARTICLE_CATEGORY_ERROR

    fails: list[dict] = []
    warns: list[dict] = []

    def _add(severity: str, issues: list) -> None:
        for rule, detail in issues:
            (fails if severity == "FAIL" else warns).append({"rule": rule, "detail": detail})

    if is_error:
        _add("FAIL", check_a1(body))
        _add("WARN", check_a2(body))
        _add("FAIL", check_b1(body))
        _add("WARN", check_b3(body))

    _add("FAIL", check_a3(body))
    _add("WARN", check_a4(body))
    _add("WARN", check_a5(body))
    _add("FAIL", check_a6(fm, body, require_error_code=is_error))
    _add("FAIL", check_b2(body))
    _add("FAIL", check_secret_token(body))
    _add("FAIL", check_aws_secret_key(body))
    _, d_issues = check_d1_d2(body)
    _add("WARN", d_issues)

    return {"fails": fails, "warns": warns}


def _format_lint_feedback(fail_details: list[str]) -> str:
    """FAIL 詳細を Claude 向けフィードバック文字列に変換する（expand_articles.py と同ロジック）。"""
    lines = []
    for detail in fail_details:
        rule = detail.split(":")[0].strip()
        if rule == "A1":
            lines.append(f"・{detail}")
            lines.append("  → 上記セクション見出し（H2）を追加すること。")
        elif rule == "A3":
            lines.append(f"・{detail}")
            lines.append("  → 日本語本文（コードブロック・URL・MD記号を除く）を 1,500 字以上にすること。")
        elif rule == "B1":
            lines.append(f"・{detail}")
            lines.append("  → 「実際のエラーメッセージ例」セクションに、HTTPステータスコードや例外名を含む")
            lines.append("    コードブロック（``` で開き ``` で閉じる）を最低1つ追加すること。")
        else:
            lines.append(f"・{detail}")
    return "\n".join(lines)


def _run_lint_gate(
    client: anthropic.Anthropic,
    row: dict,
    filename: str,
    frontmatter: str,
    body: str,
    disclaimer: str,
    out: Path,
    remaining: list[dict],
) -> tuple[str, bool]:
    """Lint 公開前ゲートを実行し、(最終 article_content, blocked) を返す。

    blocked=True の場合はこの記事をスキップすること。
    キュー戻しはこの関数内で remaining に追加する。

    優先順位:
      1. A6 → 即キュー戻し（リトライ不要）
      2. A1/B1/B2 → 最大 _LINT_MAX_RETRIES 回リトライ → 残ればキュー戻し
      3. A3 のみ → 1 回リトライ → 残ればWARN通過
      4. WARN系のみ → WARN記録のみで通過
    """
    article_content = frontmatter + body + disclaimer
    lint_result = _lint_check_content(article_content, out)
    fail_rules = {f["rule"] for f in lint_result["fails"]}

    def _fail_strs() -> list[str]:
        return [f"{f['rule']}: {f['detail']}" for f in lint_result["fails"]]

    # ① A6 → 即キュー戻し
    if "A6" in fail_rules:
        print(f"  [lint] BLOCK(A6) {filename} → キューに戻す: " + "; ".join(_fail_strs()))
        remaining.append(row)
        return article_content, True

    # ② B1/B2/A1 → 最大 _LINT_MAX_RETRIES 回リトライ
    if fail_rules & _LINT_BLOCK_RULES:
        for attempt in range(1, _LINT_MAX_RETRIES + 1):
            feedback = _format_lint_feedback(_fail_strs())
            print(
                f"  [lint] RETRY({attempt}/{_LINT_MAX_RETRIES}) "
                f"{'/'.join(sorted(fail_rules & _LINT_BLOCK_RULES))} {filename}"
            )
            try:
                retry_body = generate_article(client, row, lint_feedback=feedback)
            except Exception as e:
                print(f"  [lint] retry {attempt} API エラー: {e}")
                break
            retry_body = normalize_before_after(retry_body)
            article_content = frontmatter + retry_body + disclaimer
            lint_result = _lint_check_content(article_content, out)
            fail_rules = {f["rule"] for f in lint_result["fails"]}
            if not (fail_rules & _LINT_BLOCK_RULES):
                print(f"  [lint] PASS after retry {attempt} {filename}")
                break

        if fail_rules & _LINT_BLOCK_RULES:
            print(
                f"  [lint] BLOCK({'/'.join(sorted(fail_rules & _LINT_BLOCK_RULES))}) "
                f"{filename} → キューに戻す（{_LINT_MAX_RETRIES}回リトライ後）: "
                + "; ".join(_fail_strs())
            )
            remaining.append(row)
            return article_content, True

    # ③ A3 のみ → 1 回リトライ、なお残ればWARN通過
    if fail_rules == {"A3"}:
        feedback = _format_lint_feedback(_fail_strs())
        print(f"  [lint] RETRY(A3×1) {filename}: " + _fail_strs()[0])
        try:
            retry_body = generate_article(client, row, lint_feedback=feedback)
            retry_body = normalize_before_after(retry_body)
            article_content = frontmatter + retry_body + disclaimer
            lint_result = _lint_check_content(article_content, out)
            fail_rules = {f["rule"] for f in lint_result["fails"]}
        except Exception as e:
            print(f"  [lint] A3 retry API エラー: {e}")

        if "A3" in fail_rules:
            print(f"  [lint] WARN(A3) {filename} 文字数不足のまま公開: " + _fail_strs()[0])
        else:
            print(f"  [lint] A3 → PASS after retry {filename}")

    # ④ WARN 記録
    warn_strs = [f"{w['rule']}: {w['detail']}" for w in lint_result["warns"]]
    if warn_strs:
        print(f"  [lint] WARN {filename}: " + "; ".join(warn_strs))
    if not lint_result["fails"]:
        print(f"  [lint] PASS {filename}")

    return article_content, False


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

    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    # 当日分がすでに DAILY_COUNT 件以上生成済みなら二重実行とみなしてスキップ
    today_count = sum(
        1 for f in POSTS_DIR.glob("*.md")
        if f"date: {today}" in f.read_text(encoding="utf-8")
    )
    if today_count >= DAILY_COUNT:
        print(f"本日分 {today_count} 件は生成済みです（上限: {DAILY_COUNT}）。スキップします。")
        return

    to_publish = rows[:DAILY_COUNT]
    remaining = rows[DAILY_COUNT:]
    published_count = 0
    published_articles: list[dict] = []
    critical_fail_count = 0

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

        # Phase 3: 知識グラフメタデータを抽出
        kg = extract_knowledge_graph(client, title, body, tool, code)
        kg_components = json.dumps(kg["components"], ensure_ascii=False)
        kg_related    = json.dumps(kg["related_services"], ensure_ascii=False)
        knowledge_graph_lines = (
            f'service: "{kg["service"]}"\n'
            f'error_type: "{kg["error_type"]}"\n'
            f'components: {kg_components}\n'
            f'related_services: {kg_related}\n'
        )

        frontmatter = (
            f'---\n'
            f'title: "{title}"\n'
            f'date: {today}\n'
            f'description: "{description}"\n'
            f'{tags_line}'
            f'errorCode: "{code}"\n'
            f'{knowledge_graph_lines}'
            f'---\n\n'
        )

        disclaimer = (
            "\n\n---\n\n"
            "*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。"
            "ソフトウェアの仕様は予告なく変更されることがあります。"
            "最新の情報は各ツールの公式サポートページをご確認ください。"
            "本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*"
        )
        body = normalize_before_after(body)
        article_content, lint_blocked = _run_lint_gate(
            client, row, filename, frontmatter, body, disclaimer, out, remaining
        )
        if lint_blocked:
            continue
        fact_result = evaluate_new_article(out.relative_to(BASE.parent), article_content)
        scores = fact_result.scores
        print(
            "  fact-check: "
            f"factual={scores['factual_score']} "
            f"freshness={scores['freshness_score']} "
            f"citation={scores['citation_coverage']} "
            f"risk={scores['risk_score']} "
            f"report={fact_result.report_path}"
        )
        if fact_result.critical:
            # critical fail: 記事を書き出さずキュー末尾に戻して次の記事へ続行。
            # raise で全体停止せず、他の正常記事の公開とqueue.csv更新を確実に完了させる。
            # 通知は daily.yml の "Notify critical fact-check failures" ステップが担う。
            failure = record_new_article_failure(out.stem, row, fact_result)
            if failure["status"] == "retry":
                print(
                    f"  fact-check CRITICAL: {filename} をキュー末尾に戻す "
                    f"failure_count={failure['failure_count']} status={failure['status']}"
                )
                remaining.append(row)
            else:
                print(
                    f"  fact-check CRITICAL: {filename} キューから除外 "
                    f"failure_count={failure['failure_count']} status={failure['status']} "
                    f"→ needs_manual_review"
                )
            critical_fail_count += 1
            continue
        if fact_result.status == "fact_check_unavailable":
            print(f"  fact-check unavailable; excluded from publication for retry: {filename}")
            remaining.append(row)
            continue
        if not fact_result.passed:
            failure = record_new_article_failure(out.stem, row, fact_result)
            print(
                f"  fact-check failed; excluded from publication: {filename} "
                f"failure_count={failure['failure_count']} status={failure['status']}"
            )
            if failure["status"] == "retry":
                remaining.append(row)
            else:
                print(f"  fact-check blocked; needs manual review: {filename}")
            continue

        out.write_text(article_content, encoding="utf-8")
        clear_new_article_failure(out.stem, row)
        print(f"  公開: {filename}  →  {title}")
        published_count += 1
        published_articles.append({
            "path": str(out.relative_to(BASE.parent).as_posix()),
            "stem": out.stem,
            "title": title,
            "source_type": "daily",
        })

    # キューを更新
    fieldnames = ["tool", "status_code", "official_meaning", "causes", "solutions"]
    with open(QUEUE_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(remaining)

    # 公開通知スクリプト用のセッションファイルを書き出す
    session_path = BASE.parent / "data" / "publish_session.json"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(
        json.dumps(published_articles, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"\n{published_count} 件を公開しました。残りキュー: {len(remaining)} 件")

    if published_count > 0:
        send_publish_report(published_count, len(remaining), published_articles)

    if len(remaining) < LOW_STOCK_THRESHOLD:
        send_low_stock_alert(len(remaining))

    if critical_fail_count > 0:
        print(
            f"\n[WARN] critical fact-check failures: {critical_fail_count} 件 "
            "→ キュー末尾に戻しました。"
            "data/fact_check_new_article_failures.json を確認してください。"
        )


if __name__ == "__main__":
    main()
