"""
公開済み記事URLを確認してGmail通知を送る。

daily_publish.py または rss_pipeline が記事を作成した後、GitHub Pages deploy 完了後に実行する。
URL が 200 を返すまでリトライし、確認後に Gmail 通知する。
二重通知防止: data/published_notification_history.json に通知済み URL を記録。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import smtplib
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
POSTS_DIR = BASE / "content" / "posts"
REPORTS_NEW = BASE / "reports" / "fact_check" / "new_articles"
REPORTS_EXISTING = BASE / "reports" / "fact_check" / "existing_articles"
HISTORY_PATH = BASE / "data" / "published_notification_history.json"
SITE_BASE = "https://errorlog.jp/posts"

MAX_RETRIES = int(os.getenv("PUBLISH_NOTIFY_MAX_RETRIES", "10"))
RETRY_SECONDS = int(os.getenv("PUBLISH_NOTIFY_RETRY_SECONDS", "60"))
FAIL_ON_ERROR = os.getenv("PUBLISH_NOTIFY_FAIL_ON_ERROR", "false").lower() == "true"
NOTIFY_TO = os.getenv("PUBLISH_NOTIFY_TO") or os.getenv("GMAIL_USER")
NOTIFY_FROM = os.getenv("PUBLISH_NOTIFY_FROM") or os.getenv("GMAIL_USER")


# ─── Gmail ────────────────────────────────────────────────────────────────────

def _send_gmail(subject: str, body: str) -> None:
    gmail_user = os.getenv("GMAIL_USER")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")
    if not gmail_user or not gmail_password:
        print("[publish-notify] GMAIL_USER / GMAIL_APP_PASSWORD 未設定のためスキップ")
        return
    to_addr = NOTIFY_TO or gmail_user
    from_addr = NOTIFY_FROM or gmail_user
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.starttls()
        smtp.login(gmail_user, gmail_password)
        smtp.send_message(msg)


# ─── 通知履歴 ──────────────────────────────────────────────────────────────────

def load_history() -> dict[str, dict]:
    if HISTORY_PATH.exists():
        try:
            raw = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
            return {item["url"]: item for item in raw}
        except Exception:
            pass
    return {}


def save_history(history: dict[str, dict]) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    items = sorted(history.values(), key=lambda x: x.get("notified_at", ""))
    HISTORY_PATH.write_text(
        json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


# ─── URL 確認 ──────────────────────────────────────────────────────────────────

def _check_url_once(url: str) -> tuple[str, int]:
    """(status, http_code): status は published | not_published | error"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ErrorLog-PublishNotify/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            code = resp.getcode()
            return ("published", code) if code == 200 else ("not_published", code)
    except urllib.error.HTTPError as e:
        return "not_published", e.code
    except Exception:
        return "error", 0


def wait_for_publish(url: str) -> tuple[str, int, int]:
    """URL が 200 になるまでポーリング。(status, http_code, retries_used) を返す。"""
    last_code = 0
    for attempt in range(MAX_RETRIES + 1):
        status, code = _check_url_once(url)
        last_code = code
        if status == "published":
            return status, code, attempt
        if attempt < MAX_RETRIES:
            print(
                f"[publish-notify] {url} → HTTP {code} "
                f"(attempt {attempt + 1}/{MAX_RETRIES}), "
                f"retry in {RETRY_SECONDS}s"
            )
            time.sleep(RETRY_SECONDS)
    return "not_published", last_code, MAX_RETRIES


# ─── fact check レポート ────────────────────────────────────────────────────────

def find_fact_check_report(stem: str) -> dict | None:
    """記事 stem に対応する最新の fact check レポートを返す。見つからなければ None。"""
    for reports_dir in (REPORTS_NEW, REPORTS_EXISTING):
        if not reports_dir.exists():
            continue
        candidates = sorted(reports_dir.glob("*.json"), reverse=True)
        for rp in candidates[:100]:
            try:
                data = json.loads(rp.read_text(encoding="utf-8"))
                if Path(data.get("path", "")).stem == stem:
                    if "report_path" not in data or not data["report_path"]:
                        data["report_path"] = str(rp.relative_to(BASE).as_posix())
                    return data
            except Exception:
                continue
    return None


# ─── メール本文構築 ────────────────────────────────────────────────────────────

def _format_fact_check(report: dict | None) -> tuple[str, str, str]:
    """(fact_check_status, subject_suffix, body_section) を返す。"""
    if report is None:
        section = "Fact check:\n* status: unknown\n* reason: レポートが見つかりませんでした\n"
        return "unknown", "（fact check: unknown）", section

    status = report.get("status", "unknown")
    evaluator = report.get("evaluator", "unknown")
    scores = report.get("scores") or {}
    sources = report.get("sources") or []
    unsupported = report.get("unsupported_claims") or []
    required_actions = report.get("required_actions") or []
    improvement_suggestions = report.get("improvement_suggestions") or []
    score_valid = report.get("score_valid", True)
    report_path = report.get("report_path", "")
    parse_error = report.get("parse_error", "")
    error = report.get("error", "")

    lines = ["Fact check:"]
    lines.append(f"* status: {status}")
    lines.append(f"* evaluator: {evaluator}")

    if status == "fact_check_unavailable":
        lines.append(f"* reason: {error or 'unavailable'}")
        if parse_error:
            lines.append(f"* parse_error: {parse_error}")
    elif status == "failed_fact_check":
        if parse_error:
            lines.append(f"* parse_error: {parse_error}")
        if error:
            lines.append(f"* error: {error}")
    else:
        lines.append(f"* factual_score: {scores.get('factual_score', 'N/A')}")
        lines.append(f"* freshness_score: {scores.get('freshness_score', 'N/A')}")
        lines.append(f"* citation_coverage: {scores.get('citation_coverage', 'N/A')}")
        lines.append(f"* risk_score: {scores.get('risk_score', 'N/A')}")
        lines.append(f"* score_valid: {score_valid}")

    lines.append(f"* sources: {len(sources)}")
    lines.append(f"* unsupported_claims: {len(unsupported)}")
    lines.append(f"* report: {report_path}")

    lines.append("")
    lines.append("Required actions:")
    if required_actions:
        for action in required_actions:
            lines.append(f"* {action}")
    else:
        lines.append("* なし")

    lines.append("")
    lines.append("Improvement suggestions:")
    if improvement_suggestions:
        for s in improvement_suggestions:
            lines.append(f"* {s}")
    else:
        lines.append("* なし")

    if status == "pass":
        suffix = ""
    elif status == "fact_check_unavailable":
        suffix = "（fact check: unavailable）"
    elif status == "unknown":
        suffix = "（fact check: unknown）"
    else:
        suffix = f"（fact check: {status}）"

    return status, suffix, "\n".join(lines) + "\n"


def _build_subject(title: str, source_type: str, suffix: str) -> str:
    prefix = "[ErrorLog] RSS記事公開完了" if source_type == "rss" else "[ErrorLog] 記事公開完了"
    return f"{prefix}{suffix}: {title}"


def _build_body(
    title: str, url: str, path_str: str, source_type: str,
    http_status: int, checked_at: str, fact_check_section: str,
) -> str:
    return "\n".join([
        "記事が公開されました。",
        "",
        f"Title: {title}",
        f"URL: {url}",
        f"Source: {source_type}",
        f"Path: {path_str}",
        "",
        "Publish check:",
        "* status: published",
        f"* http_status: {http_status}",
        f"* checked_at: {checked_at}",
        "",
        fact_check_section,
        f"通知時刻: {checked_at}",
    ])


# ─── ユーティリティ ────────────────────────────────────────────────────────────

def _read_frontmatter_title(path_str: str) -> str:
    try:
        p = BASE / path_str if not Path(path_str).is_absolute() else Path(path_str)
        content = p.read_text(encoding="utf-8")
        if content.startswith("---"):
            end = content.find("\n---\n", 3)
            if end != -1:
                for line in content[4:end].splitlines():
                    if line.startswith("title:"):
                        return line.split(":", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return Path(path_str).stem.replace("_", " ")


def _article_url(stem: str) -> str:
    return f"{SITE_BASE}/{stem}/"


# ─── 記事検出 ─────────────────────────────────────────────────────────────────

def _articles_from_session(session_file: str) -> list[dict]:
    p = Path(session_file)
    if not p.is_absolute():
        p = BASE / session_file
    if not p.exists():
        print(f"[publish-notify] session file not found: {p}")
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[publish-notify] session file parse error: {e}")
        return []


def _articles_from_git_diff(source_type: str) -> list[dict]:
    """直前のコミットで追加された content/posts/*.md を検出する。"""
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD~1", "--name-only", "--diff-filter=A", "--", "content/posts/"],
            capture_output=True, text=True, check=True, cwd=BASE,
        )
        paths = [p.strip() for p in result.stdout.splitlines() if p.strip().endswith(".md")]
        return [
            {"path": p, "title": _read_frontmatter_title(p), "source_type": source_type}
            for p in paths
        ]
    except subprocess.CalledProcessError as e:
        print(f"[publish-notify] git diff failed: {e.stderr}")
        return []
    except Exception as e:
        print(f"[publish-notify] git diff error: {e}")
        return []


# ─── メイン処理 ───────────────────────────────────────────────────────────────

def _notify_article(article: dict, history: dict[str, dict]) -> str:
    """
    "notified" | "already_notified" | "skipped" | "failed" を返す。
    history は破壊的に更新される。
    """
    path_str = article["path"]
    title = article.get("title") or _read_frontmatter_title(path_str)
    source_type = article.get("source_type", "unknown")
    stem = Path(path_str).stem
    url = _article_url(stem)

    if url in history:
        print(f"[publish-notify] already_notified: {url}")
        return "already_notified"

    status, http_code, retries = wait_for_publish(url)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if status != "published":
        print(
            f"[publish-notify] publish_notify_skipped "
            f"reason=url_not_published url={url} retries={retries}"
        )
        return "skipped"

    report = find_fact_check_report(stem)
    fact_check_status, subject_suffix, fact_check_section = _format_fact_check(report)

    subject = _build_subject(title, source_type, subject_suffix)
    body = _build_body(title, url, path_str, source_type, http_code, now_str, fact_check_section)

    try:
        _send_gmail(subject, body)
        print(f"[publish-notify] notified: {url}")
        history[url] = {
            "url": url,
            "path": path_str,
            "title": title,
            "source_type": source_type,
            "notified_at": now_str,
            "fact_check_status": fact_check_status,
        }
        return "notified"
    except Exception as e:
        print(f"[publish-notify] gmail send failed: {e}")
        if FAIL_ON_ERROR:
            raise
        return "failed"


def main() -> None:
    parser = argparse.ArgumentParser(description="公開済み記事URLを確認してGmail通知を送る")
    parser.add_argument("--session-file", help="記事リストJSONファイルパス（daily用）")
    parser.add_argument("--source-type", default="unknown", choices=["daily", "rss", "unknown"],
                        help="記事の出所")
    parser.add_argument("--detect-from-commit", action="store_true",
                        help="直前の git commit から新規記事を検出する（RSS用）")
    args = parser.parse_args()

    if args.session_file:
        articles = _articles_from_session(args.session_file)
    elif args.detect_from_commit:
        articles = _articles_from_git_diff(args.source_type)
    else:
        print("[publish-notify] --session-file または --detect-from-commit を指定してください")
        sys.exit(0)

    if not articles:
        print("[publish-notify] 通知対象記事なし")
        return

    history = load_history()

    checked = published = notified = already_notified = skipped = failed = 0

    for article in articles:
        checked += 1
        outcome = _notify_article(article, history)
        if outcome == "notified":
            notified += 1
            published += 1
        elif outcome == "already_notified":
            already_notified += 1
        elif outcome == "skipped":
            skipped += 1
        elif outcome == "failed":
            failed += 1
            published += 1

    save_history(history)

    print(
        f"[publish-notify] "
        f"checked={checked} published={published} notified={notified} "
        f"already_notified={already_notified} skipped={skipped} failed={failed}"
    )

    if failed > 0 and FAIL_ON_ERROR:
        sys.exit(1)


if __name__ == "__main__":
    main()
