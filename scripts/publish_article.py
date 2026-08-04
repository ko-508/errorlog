#!/usr/bin/env python3
"""記事1件の検証・コミット・プッシュを定型実行する。

これまで Codex に依頼していた定型手順の置き換え。判断を伴う作業
（調査・執筆・レビュー）はチャット側、機械的な検証と反映はこのスクリプト。

実行例:
  python scripts/publish_article.py nginx_504 --marker "上流"
  python scripts/publish_article.py nginx_504 --marker "上流" --no-push   # push直前まで
  python scripts/publish_article.py nginx_504 --marker "上流" --zenn      # push後にZenn同期も起動
  python scripts/publish_article.py nginx_504 --marker "上流" --note "公式文書で確認"

手順（途中で条件を満たさなければ即停止し、何も変更しない）:
  1. 作業ツリーの安全確認（変更が対象記事と許容リスト以外にないこと）
  2. 配置確認（--marker の文字列が対象記事に存在すること）
  3. lint（FAIL ゼロ。実行で変わったレポートファイルは復元）
  4. hugo があればビルド確認（なければスキップして報告）
  5. 検証記録 JSON を更新
  6. 対象記事と検証記録 JSON のみ add してコミット
  7. 許容リストの未コミット変更を stash 退避 → pull --rebase → push → 復元
     （rebase や stash pop の衝突は自動解決せず停止）
  8. --zenn 指定時は Zenn 同期の完了を待ち、X 投稿用の title/url/hashtags を出力
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

# コミットせずに残っていてもよい既知のファイル（push 時に stash 退避する）
ALLOWED_DIRTY = [
    "CLAUDE.md",
    ".github/workflows/weekly_ga4.yml",
    "scripts/fetch_search_console.py",
    "scripts/publish_article.py",
    "scripts/weekly_report.py",
]

# lint 実行で変更されうるレポートファイル（tracked なら実行後に復元）
LINT_REPORTS = [
    "data/lint_report.json",
    "reports/lint/lint_summary.md",
]

REVIEW_STATUS_REL = "data/article_review_status.json"
SITE_BASE = "https://errorlog.jp"


def run(cmd: list[str], check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    """サブプロセス実行。Windows では子プロセスの日本語出力が CP932 になる
    ことがあるため、UTF-8 で読み、復号できないバイトは置換して落ちないようにする。
    Python の子プロセスには UTF-8 出力を強制する。"""
    import os
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    return subprocess.run(
        cmd, cwd=BASE, check=check, capture_output=capture,
        text=True, encoding="utf-8", errors="replace", env=env,
    )


def git_dirty_files() -> set[str]:
    """tracked の変更ファイル一覧（ステージ済み・未ステージの両方）。"""
    out = run(["git", "status", "--porcelain"]).stdout
    dirty = set()
    for line in out.splitlines():
        status, path = line[:2], line[3:].strip().strip('"')
        if status != "??":  # 未追跡は対象外（触らない）
            dirty.add(path.replace("\\", "/"))
    return dirty


def die(msg: str) -> None:
    print(f"\n[停止] {msg}")
    sys.exit(1)


def parse_frontmatter_for_x_post(text: str) -> tuple[str, list[str]]:
    if not text.startswith("---\n"):
        die("記事の front matter 開始行が見つかりません。")
    end = text.find("\n---", 4)
    if end == -1:
        die("記事の front matter 終了行が見つかりません。")

    title = ""
    tags: list[str] = []
    for line in text[4:end].splitlines():
        m_title = re.match(r'^title:\s*(.+)\s*$', line)
        if m_title:
            try:
                parsed_title = ast.literal_eval(m_title.group(1))
            except (SyntaxError, ValueError) as e:
                die(f"title を解析できませんでした: {e}")
            if not isinstance(parsed_title, str) or not parsed_title:
                die("title が空、または文字列ではありません。")
            title = parsed_title
            continue

        m_tags = re.match(r'^tags:\s*(\[.+\])\s*$', line)
        if m_tags:
            try:
                parsed_tags = ast.literal_eval(m_tags.group(1))
            except (SyntaxError, ValueError) as e:
                die(f"tags を解析できませんでした: {e}")
            if not isinstance(parsed_tags, list) or not parsed_tags:
                die("tags が空、または配列ではありません。")
            if not all(isinstance(tag, str) and tag for tag in parsed_tags):
                die("tags には空でない文字列だけを指定してください。")
            tags = parsed_tags

    if not title:
        die("front matter に title がありません。")
    if not tags:
        die("front matter に tags がありません。")
    return title, tags


def make_hashtags(tags: list[str]) -> str:
    hashtags = []
    for tag in tags:
        body = re.sub(r"[^\w]", "", tag, flags=re.UNICODE)
        if not body:
            die(f"X 投稿用ハッシュタグに変換できないタグがあります: {tag}")
        hashtags.append(f"#{body}")
    return " ".join(hashtags)


def print_x_post_fields(slug: str, title: str, tags: list[str]) -> None:
    print("\nX 投稿用")
    print(f"title: {title}")
    print(f"url: {SITE_BASE}/posts/{slug}/")
    print(f"hashtags: {make_hashtags(tags)}")


def wait_zenn_workflow(head_sha: str, branch: str) -> None:
    run_id = ""
    for _ in range(30):
        listed = run([
            "gh", "run", "list",
            "--workflow", "zenn_sync.yml",
            "--branch", branch,
            "--event", "workflow_dispatch",
            "--json", "databaseId,headSha,status,conclusion",
            "--limit", "20",
        ], check=False)
        if listed.returncode != 0:
            die(f"Zenn 同期 run の確認に失敗しました。\n{listed.stdout}\n{listed.stderr}")
        try:
            runs = json.loads(listed.stdout)
        except json.JSONDecodeError as e:
            die(f"Zenn 同期 run の一覧を JSON として解析できませんでした: {e}\n{listed.stdout}")
        for item in runs:
            if item.get("headSha") == head_sha:
                run_id = str(item.get("databaseId", ""))
                break
        if run_id:
            break
        time.sleep(2)

    if not run_id:
        die(f"Zenn 同期 run が見つかりませんでした。branch={branch}, head={head_sha}")

    watched = run(["gh", "run", "watch", run_id, "--exit-status"], check=False, capture=False)
    if watched.returncode != 0:
        die(f"Zenn 同期 run が失敗しました。run_id={run_id}")


def normalize_review_status(data: dict) -> dict:
    """既存の平坦な検証記録を history 形式へ移行する。"""
    normalized = {}
    for key, entry in data.items():
        if not isinstance(entry, dict):
            die(f"{REVIEW_STATUS_REL} の {key} がオブジェクトではありません。")

        if "history" not in entry:
            if "verified_at" not in entry or "note" not in entry:
                die(f"{REVIEW_STATUS_REL} の {key} に verified_at または note がありません。")
            verified_at = entry["verified_at"]
            note = entry["note"]
            if not isinstance(verified_at, str) or not isinstance(note, str):
                die(f"{REVIEW_STATUS_REL} の {key} の verified_at/note が文字列ではありません。")
            normalized[key] = {
                "verified": entry.get("verified"),
                "verified_at": verified_at,
                "last_verified_at": verified_at,
                "history": [
                    {"date": verified_at, "note": note},
                ],
            }
            continue

        required = ["verified", "verified_at", "last_verified_at", "history"]
        missing = [name for name in required if name not in entry]
        if missing:
            die(f"{REVIEW_STATUS_REL} の {key} に必要キーがありません: {', '.join(missing)}")
        if not isinstance(entry["verified_at"], str) or not isinstance(entry["last_verified_at"], str):
            die(f"{REVIEW_STATUS_REL} の {key} の日付が文字列ではありません。")
        if not isinstance(entry["history"], list):
            die(f"{REVIEW_STATUS_REL} の {key} の history が配列ではありません。")
        for i, item in enumerate(entry["history"]):
            if not isinstance(item, dict) or not isinstance(item.get("date"), str) or not isinstance(item.get("note"), str):
                die(f"{REVIEW_STATUS_REL} の {key} の history[{i}] が {{date, note}} 形式ではありません。")
        normalized[key] = {
            "verified": entry["verified"],
            "verified_at": entry["verified_at"],
            "last_verified_at": entry["last_verified_at"],
            "history": entry["history"],
        }
    return normalized


def update_review_status(rel: str, note: str, today: date) -> None:
    path = BASE / REVIEW_STATUS_REL
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            die(f"{REVIEW_STATUS_REL} を解析できませんでした。既存記録を保護するため停止します: {e}")
        if not isinstance(loaded, dict):
            die(f"{REVIEW_STATUS_REL} のルートがオブジェクトではありません。")
        status = normalize_review_status(loaded)
    else:
        status = {}

    today_text = today.isoformat()
    if rel in status:
        entry = status[rel]
        entry["verified"] = True
        entry["last_verified_at"] = today_text
        entry["history"].append({"date": today_text, "note": note})
    else:
        status[rel] = {
            "verified": True,
            "verified_at": today_text,
            "last_verified_at": today_text,
            "history": [
                {"date": today_text, "note": note},
            ],
        }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="記事1件の検証・コミット・プッシュ")
    ap.add_argument("slug", help="記事の slug（content/posts/<slug>.md）")
    ap.add_argument("--marker", required=True, help="配置確認用の文字列（新版に必ず含まれるもの）")
    ap.add_argument("--message", default="", help="コミットメッセージ（省略時は定型文）")
    ap.add_argument("--note", default="全面書き直し", help="検証内容の説明")
    ap.add_argument("--no-push", action="store_true", help="コミットまでで止める（push しない）")
    ap.add_argument("--zenn", action="store_true", help="push 後に gh CLI で Zenn 同期を起動する")
    args = ap.parse_args()

    article = BASE / "content" / "posts" / f"{args.slug}.md"
    rel = f"content/posts/{args.slug}.md"

    # ── 1. 作業ツリーの安全確認 ───────────────────────────────────────────
    if not article.exists():
        die(f"{rel} が存在しません。書き直し版の配置を確認してください。")

    dirty = git_dirty_files()
    is_new = rel not in dirty and not run(
        ["git", "ls-files", "--error-unmatch", rel], check=False
    ).returncode == 0
    unexpected = dirty - set(ALLOWED_DIRTY) - {rel}
    if unexpected:
        die("対象外の tracked ファイルに変更があります: " + ", ".join(sorted(unexpected)))
    if not is_new and rel not in dirty:
        die(f"{rel} に変更がありません。書き直し版の上書きを確認してください。")

    # ── 2. 配置確認（目印文字列） ─────────────────────────────────────────
    text = article.read_text(encoding="utf-8")
    x_title, x_tags = parse_frontmatter_for_x_post(text)
    if args.marker not in text:
        die(f"目印文字列が見つかりません: {args.marker}\n旧版のままの可能性があります。")
    if "免責事項：本記事の内容は" not in text:
        die("免責事項の定型文が見つかりません。")
    print(f"[1/7] 配置確認 OK（{'新規' if is_new else '書き直し'}: {rel}）")

    # ── 3. lint ──────────────────────────────────────────────────────────
    r = run([sys.executable, "scripts/lint_articles.py", "--path", rel], check=False)
    report_path = BASE / "data" / "lint_report.json"
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        fails = report["articles"][0]["fails"]
        warns = report["articles"][0]["warns"]
    except Exception as e:  # noqa: BLE001
        die(f"lint レポートを読めませんでした: {e}\n{r.stdout}\n{r.stderr}")
    # レポートファイルが tracked 変更になっていたら復元
    now_dirty = git_dirty_files()
    to_restore = [p for p in LINT_REPORTS if p in now_dirty and p not in dirty]
    if to_restore:
        run(["git", "restore", "--"] + to_restore)
    if fails:
        die("lint FAIL: " + "; ".join(f"{f['rule']}: {f['detail']}" for f in fails))
    warn_note = "（WARN: " + ", ".join(w["rule"] for w in warns) + "）" if warns else ""
    print(f"[2/7] lint OK{warn_note}")

    # ── 4. hugo ビルド確認（任意） ────────────────────────────────────────
    if shutil.which("hugo"):
        b = run(["hugo", "--gc", "--minify", "--quiet"], check=False)
        if b.returncode != 0:
            die(f"hugo ビルド失敗:\n{b.stderr[-1500:]}")
        print("[3/7] hugo ビルド OK")
    else:
        print("[3/7] hugo なし → ビルド確認スキップ")

    # ── 5. 検証記録 ─────────────────────────────────────────────────────
    update_review_status(rel, args.note, date.today())
    print(f"[4/7] 検証記録 OK: {REVIEW_STATUS_REL}")

    # ── 6. コミット ──────────────────────────────────────────────────────
    if args.message:
        msg = args.message
    elif is_new:
        msg = f"post: {args.slug} 記事を新規作成（確立済みの型・照合済みソースで執筆）"
    else:
        msg = f"rewrite: {args.slug} 記事を新しい質の型で書き直し"
    run(["git", "add", "--", rel, REVIEW_STATUS_REL])
    run(["git", "commit", "-m", msg])
    print(f"[5/7] コミット OK: {msg}")

    # ── 7. push（許容リストを退避） ───────────────────────────────────────
    if args.no_push:
        print("[6/7] --no-push 指定のため終了（push は未実行）")
        return
    to_stash = [p for p in ALLOWED_DIRTY if p in git_dirty_files()]
    stashed = False
    if to_stash:
        run(["git", "stash", "push", "--"] + to_stash)
        stashed = True
        print(f"[6/7] 退避: {', '.join(to_stash)}")
    pr = run(["git", "pull", "--rebase"], check=False)
    if pr.returncode != 0:
        die(f"pull --rebase が失敗しました。自動解決はしません。手動で確認してください。\n{pr.stdout}\n{pr.stderr}")
    ps = run(["git", "push"], check=False)
    if ps.returncode != 0:
        die(f"push が失敗しました。\n{ps.stdout}\n{ps.stderr}")
    if stashed:
        pp = run(["git", "stash", "pop"], check=False)
        if pp.returncode != 0:
            die(f"stash pop で競合しました。自動解決はしません。手動で確認してください。\n{pp.stdout}\n{pp.stderr}")
    head = run(["git", "rev-parse", "--short", "HEAD"]).stdout.strip()
    head_full = run(["git", "rev-parse", "HEAD"]).stdout.strip()
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    print(f"[7/7] push OK: {head}")

    if args.zenn:
        if branch == "HEAD":
            die("detached HEAD のため Zenn 同期 run を特定できません。通常のブランチ上で実行してください。")
        if shutil.which("gh"):
            z = run(["gh", "workflow", "run", "zenn_sync.yml", "--ref", branch, "-f", f"slugs={args.slug}"], check=False)
            if z.returncode != 0:
                die(f"Zenn 同期の起動に失敗しました。\n{z.stdout}\n{z.stderr}")
            print("Zenn 同期を起動しました。完了を待ちます。")
            wait_zenn_workflow(head_full, branch)
            print("Zenn 同期が完了しました")
        else:
            die("gh CLI がないため Zenn 同期を起動できません。")

    print_x_post_fields(args.slug, x_title, x_tags)


if __name__ == "__main__":
    main()
