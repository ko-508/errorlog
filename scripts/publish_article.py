#!/usr/bin/env python3
"""記事1件の検証・コミット・プッシュを定型実行する。

これまで Codex に依頼していた定型手順の置き換え。判断を伴う作業
（調査・執筆・レビュー）はチャット側、機械的な検証と反映はこのスクリプト。

実行例:
  python scripts/publish_article.py nginx_504 --marker "上流"
  python scripts/publish_article.py nginx_504 --marker "上流" --no-push   # push直前まで
  python scripts/publish_article.py nginx_504 --marker "上流" --zenn      # push後にZenn同期も起動

手順（途中で条件を満たさなければ即停止し、何も変更しない）:
  1. 作業ツリーの安全確認（変更が対象記事と許容リスト以外にないこと）
  2. 配置確認（--marker の文字列が対象記事に存在すること）
  3. lint（FAIL ゼロ。実行で変わったレポートファイルは復元）
  4. hugo があればビルド確認（なければスキップして報告）
  5. 対象1ファイルのみ add してコミット
  6. 許容リストの未コミット変更を stash 退避 → pull --rebase → push → 復元
     （rebase や stash pop の衝突は自動解決せず停止）
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

# コミットせずに残っていてもよい既知のファイル（push 時に stash 退避する）
ALLOWED_DIRTY = [
    "CLAUDE.md",
    ".github/workflows/weekly_ga4.yml",
    "scripts/fetch_search_console.py",
    "scripts/weekly_report.py",
]

# lint 実行で変更されうるレポートファイル（tracked なら実行後に復元）
LINT_REPORTS = [
    "data/lint_report.json",
    "reports/lint/lint_summary.md",
]


def run(cmd: list[str], check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=BASE, check=check, capture_output=capture, text=True, encoding="utf-8")


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


def main() -> None:
    ap = argparse.ArgumentParser(description="記事1件の検証・コミット・プッシュ")
    ap.add_argument("slug", help="記事の slug（content/posts/<slug>.md）")
    ap.add_argument("--marker", required=True, help="配置確認用の文字列（新版に必ず含まれるもの）")
    ap.add_argument("--message", default="", help="コミットメッセージ（省略時は定型文）")
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
    if args.marker not in text:
        die(f"目印文字列が見つかりません: {args.marker}\n旧版のままの可能性があります。")
    if "免責事項：本記事の内容は" not in text:
        die("免責事項の定型文が見つかりません。")
    print(f"[1/6] 配置確認 OK（{'新規' if is_new else '書き直し'}: {rel}）")

    # ── 3. lint ──────────────────────────────────────────────────────────
    r = run([sys.executable, "scripts/lint_articles.py", "--path", rel], check=False)
    import json
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
    print(f"[2/6] lint OK{warn_note}")

    # ── 4. hugo ビルド確認（任意） ────────────────────────────────────────
    if shutil.which("hugo"):
        b = run(["hugo", "--gc", "--minify", "--quiet"], check=False)
        if b.returncode != 0:
            die(f"hugo ビルド失敗:\n{b.stderr[-1500:]}")
        print("[3/6] hugo ビルド OK")
    else:
        print("[3/6] hugo なし → ビルド確認スキップ")

    # ── 5. コミット ──────────────────────────────────────────────────────
    if args.message:
        msg = args.message
    elif is_new:
        msg = f"post: {args.slug} 記事を新規作成（確立済みの型・照合済みソースで執筆）"
    else:
        msg = f"rewrite: {args.slug} 記事を新しい質の型で書き直し"
    run(["git", "add", "--", rel])
    run(["git", "commit", "-m", msg])
    print(f"[4/6] コミット OK: {msg}")

    # ── 6. push（許容リストを退避） ───────────────────────────────────────
    if args.no_push:
        print("[5/6] --no-push 指定のため終了（push は未実行）")
        return
    to_stash = [p for p in ALLOWED_DIRTY if p in git_dirty_files()]
    stashed = False
    if to_stash:
        run(["git", "stash", "push", "--"] + to_stash)
        stashed = True
        print(f"[5/6] 退避: {', '.join(to_stash)}")
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
    print(f"[6/6] push OK: {head}")

    if args.zenn:
        if shutil.which("gh"):
            z = run(["gh", "workflow", "run", "zenn_sync.yml", "-f", f"slugs={args.slug}"], check=False)
            print("Zenn 同期を起動しました" if z.returncode == 0 else f"Zenn 同期の起動に失敗: {z.stderr}")
        else:
            print("gh CLI がないため Zenn 同期はスキップ（Actions から手動起動してください）")


if __name__ == "__main__":
    main()