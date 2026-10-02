#!/usr/bin/env python3
"""スマホからアップロードされた新規記事を検証・公開用コミットに変換する。"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

try:
    from scripts.article_og_image import generate_article_og_image
    from scripts.publish_article import (
        ensure_article_og_image_param,
        parse_frontmatter_for_x_post,
        update_review_status,
    )
except ModuleNotFoundError:
    from article_og_image import generate_article_og_image
    from publish_article import (
        ensure_article_og_image_param,
        parse_frontmatter_for_x_post,
        update_review_status,
    )


BASE = Path(__file__).resolve().parent.parent
LINT_REPORTS = ["data/lint_report.json", "reports/lint/lint_summary.md"]
SLUG_RE = re.compile(r"[a-z0-9_+-]+")
ZERO_SHA = "0" * 40
PUBLISH_FIELDS = ("publish_slug", "publish_note", "publish_zenn")


@dataclass(frozen=True)
class PublishMetadata:
    slug: str
    note: str
    zenn: bool
    article_text: str


def die(msg: str) -> None:
    print(f"[停止] {msg}", file=sys.stderr)
    raise SystemExit(1)


def run_cmd(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        cmd,
        cwd=BASE,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        die(
            f"コマンドが失敗しました: {cmd}\n"
            f"終了コード: {result.returncode}\n"
            f"標準出力:\n{result.stdout}\n"
            f"標準エラー:\n{result.stderr}"
        )
    return result


def dirty_files() -> set[str]:
    return {
        line[3:].strip().strip('"').replace("\\", "/")
        for line in run_cmd(["git", "status", "--porcelain"], check=False).stdout.splitlines()
        if line[:2] != "??"
    }


def slug_from_draft_path(path: Path) -> str:
    slug = path.stem
    if not SLUG_RE.fullmatch(slug):
        die(f"ファイル名から取得した slug に使用できない文字があります: {slug}（ファイル: {path.as_posix()}）")
    return slug


def changed_drafts_from_name_status(output: str) -> list[Path]:
    drafts: list[Path] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) != 2:
            die(f"git diff --name-status の出力形式が不正です: {line!r}")
        status, name = parts
        path = Path(name)
        if status in {"A", "M"} and path.suffix == ".md":
            drafts.append(path)
    return drafts


def require_single_changed_draft(output: str) -> Path:
    drafts = changed_drafts_from_name_status(output)
    names = ", ".join(path.as_posix() for path in drafts) if drafts else "（なし）"
    if len(drafts) != 1:
        die(f"push 差分内の A/M の drafts/*.md はちょうど1件必要です。件数: {len(drafts)}、ファイル: {names}")
    return drafts[0]


def draft_from_push(before: str, after: str) -> Path:
    if before == ZERO_SHA:
        die(f"push 前の SHA が40桁のゼロです。新規ブランチの push は処理できません: before={before}")
    result = run_cmd(
        ["git", "diff", "--name-status", before, after, "--", "drafts/"],
        check=False,
    )
    if result.returncode != 0:
        die(
            "push 差分を取得できませんでした。"
            f"before={before}, after={after}, 終了コード={result.returncode}\n"
            f"標準出力:\n{result.stdout}\n標準エラー:\n{result.stderr}"
        )
    return require_single_changed_draft(result.stdout)


def draft_from_dispatch(slug: str) -> Path:
    if not SLUG_RE.fullmatch(slug):
        die(f"workflow_dispatch の slug に使用できない文字があります: {slug}")
    path = Path("drafts") / f"{slug}.md"
    if not (BASE / path).is_file():
        die(f"{path.as_posix()} が存在しません。先に記事ファイルをアップロードしてください。")
    return path


def _parse_quoted_string(field: str, raw_value: str) -> str:
    if not re.fullmatch(r'"(?:[^"\\]|\\["\\/bfnrt]|\\u[0-9a-fA-F]{4})*"', raw_value):
        die(f"{field} は空でない二重引用符付き文字列で指定してください。値: {raw_value!r}")
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        die(f"{field} の二重引用符付き文字列を解析できません: {exc}。値: {raw_value!r}")
    if not isinstance(value, str) or not value.strip():
        die(f"{field} は空でない二重引用符付き文字列で指定してください。値: {raw_value!r}")
    return value


def parse_publish_metadata(raw: bytes, filename_slug: str) -> PublishMetadata:
    if raw.startswith(b"\xef\xbb\xbf"):
        die("記事ファイルの先頭に UTF-8 BOM があります。先頭は BOM なしの '---\\n' にしてください。")
    if raw.startswith(b"---\r\n"):
        die("記事ファイルの先頭が CRLF です。先頭は LF のみの '---\\n' にしてください。")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        die(f"記事ファイルを UTF-8 として読めません: {exc}")
    if not text.startswith("---\n"):
        die("記事ファイルの先頭が '---\\n' ではありません。BOM なし・LF 改行の frontmatter にしてください。")

    lines = text.splitlines(keepends=True)
    closing_index = next(
        (index for index, line in enumerate(lines[1:], start=1) if line == "---\n"),
        None,
    )
    if closing_index is None:
        die("frontmatter の終了行 '---' が LF 改行付きで見つかりません。")

    values: dict[str, str] = {}
    removal_indexes: set[int] = set()
    for index in range(1, closing_index):
        line = lines[index]
        for field in PUBLISH_FIELDS:
            prefix = f"{field}:"
            if line.startswith(prefix):
                if field in values:
                    die(f"frontmatter に {field} が複数あります。")
                if not line.endswith("\n"):
                    die(f"frontmatter の {field} 行が LF で終わっていません。")
                values[field] = line[len(prefix):].strip(" ").removesuffix("\n")
                removal_indexes.add(index)
                break

    missing = [field for field in PUBLISH_FIELDS if field not in values]
    if missing:
        die("frontmatter に公開用必須フィールドがありません: " + ", ".join(missing))

    publish_slug = _parse_quoted_string("publish_slug", values["publish_slug"])
    publish_note = _parse_quoted_string("publish_note", values["publish_note"])
    raw_zenn = values["publish_zenn"]
    if raw_zenn not in {"true", "false"}:
        die(f"publish_zenn は引用符なしの true または false のみ指定できます。値: {raw_zenn!r}")
    publish_zenn = raw_zenn == "true"

    if publish_slug != filename_slug:
        die(
            "publish_slug とファイル名の slug が一致しません。"
            f"publish_slug={publish_slug!r}, filename_slug={filename_slug!r}"
        )

    article_text = "".join(
        line for index, line in enumerate(lines) if index not in removal_indexes
    )
    return PublishMetadata(publish_slug, publish_note, publish_zenn, article_text)


def write_outputs(path: Path, title: str, slug: str, zenn: bool) -> None:
    try:
        with path.open("a", encoding="utf-8", newline="\n") as output:
            output.write(f"title<<TITLE_EOF\n{title}\nTITLE_EOF\n")
            output.write(f"slug={slug}\n")
            output.write(f"zenn={'true' if zenn else 'false'}\n")
    except OSError as exc:
        die(f"GITHUB_OUTPUT に結果を書き込めません: path={path}, error={exc}")


def process(draft_rel: Path, output_path: Path) -> None:
    draft = BASE / draft_rel
    if not draft.is_file():
        die(f"対象の記事ファイルが存在しません: {draft_rel.as_posix()}")
    slug = slug_from_draft_path(draft_rel)
    metadata = parse_publish_metadata(draft.read_bytes(), slug)

    article = BASE / "content" / "posts" / f"{slug}.md"
    rel = f"content/posts/{slug}.md"
    if article.exists():
        die(
            f"{rel} がすでに存在します。このワークフローは新規公開専用です。"
            "既存記事の書き直しは PC から scripts/publish_article.py を実行してください。"
        )

    article.parent.mkdir(parents=True, exist_ok=True)
    article.write_bytes(metadata.article_text.encode("utf-8"))
    run_cmd(["git", "add", "--", rel])
    print(f"コピー完了: {draft_rel.as_posix()} → {rel}（publish_* 3行を除去）")

    text = metadata.article_text
    title, _tags, service = parse_frontmatter_for_x_post(text)
    og_rel = generate_article_og_image(slug, title, service)
    updated = ensure_article_og_image_param(text, og_rel)
    if updated != text:
        article.write_text(updated, encoding="utf-8", newline="\n")
        text = updated
    print(f"OGP 生成 OK: {og_rel}")

    Path("/tmp/validated_article.md").write_text(text, encoding="utf-8", newline="\n")

    if "免責事項：本記事の内容は" not in text:
        die("免責事項の定型文が見つかりません。")
    print("免責事項 OK")

    before_dirty = dirty_files()
    lint_result = run_cmd(
        [sys.executable, "scripts/lint_articles.py", "--path", rel],
        check=False,
    )
    try:
        report = json.loads((BASE / "data" / "lint_report.json").read_text(encoding="utf-8"))
        fails = report["articles"][0]["fails"]
        warns = report["articles"][0]["warns"]
    except Exception as exc:
        die(
            f"lint レポートを読めませんでした: {exc}\n"
            f"lint 終了コード: {lint_result.returncode}\n"
            f"標準出力:\n{lint_result.stdout}\n標準エラー:\n{lint_result.stderr}"
        )

    after_dirty = dirty_files()
    to_restore = [path for path in LINT_REPORTS if path in after_dirty and path not in before_dirty]
    if to_restore:
        run_cmd(["git", "restore", "--", *to_restore])
        print(f"lint レポート復元: {to_restore}")
    if fails:
        die("lint FAIL: " + "; ".join(f"{item['rule']}: {item['detail']}" for item in fails))
    warn_note = "（WARN: " + ", ".join(item["rule"] for item in warns) + "）" if warns else ""
    print(f"lint OK{warn_note}")

    frontmatter_result = run_cmd(
        [sys.executable, "scripts/validate_frontmatter.py"],
        check=False,
    )
    if frontmatter_result.returncode != 0:
        die(
            "Front Matter バリデーションに失敗しました。"
            f"終了コード: {frontmatter_result.returncode}\n"
            f"標準出力:\n{frontmatter_result.stdout}\n標準エラー:\n{frontmatter_result.stderr}"
        )
    print("Front Matter バリデーション OK")

    hugo_result = run_cmd(["hugo", "--minify", "--quiet"], check=False)
    if hugo_result.returncode != 0:
        die(
            f"Hugo ビルドに失敗しました。終了コード: {hugo_result.returncode}\n"
            f"標準出力:\n{hugo_result.stdout}\n標準エラー:\n{hugo_result.stderr[-1500:]}"
        )
    public_article = BASE / "public" / "posts" / slug / "index.html"
    if not public_article.is_file():
        die(
            f"Hugo ビルド後も {public_article.relative_to(BASE).as_posix()} が存在しません。"
            "date が未来（UTC 基準）または draft: true の可能性があります。"
        )
    print(f"Hugo ビルド・公開対象確認 OK: {public_article.relative_to(BASE).as_posix()}")

    update_review_status(rel, metadata.note, date.today())
    print(f"検証記録 OK: {rel}")

    current_dirty = dirty_files()
    allowed = {rel, "data/article_review_status.json", f"static/{og_rel}", draft_rel.as_posix()}
    unexpected = current_dirty - allowed
    if unexpected:
        die(f"想定外のファイルが変更されています: {', '.join(sorted(unexpected))}")

    run_cmd(["git", "add", "--", rel, "data/article_review_status.json", f"static/{og_rel}"])
    run_cmd(["git", "rm", "--", draft_rel.as_posix()])
    run_cmd(["git", "commit", "-m", f"post: {slug} 記事を新規作成（スマホから公開）"])
    print("commit OK")
    write_outputs(output_path, title, slug, metadata.zenn)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="スマホ公開用の記事を検証してコミットする")
    parser.add_argument("--slug", help="workflow_dispatch で処理する drafts/<slug>.md の slug")
    parser.add_argument("--before", help="push 前のコミット SHA")
    parser.add_argument("--after", help="push 後のコミット SHA")
    args = parser.parse_args()

    dispatch_mode = args.slug is not None
    push_mode = args.before is not None or args.after is not None
    if dispatch_mode == push_mode:
        parser.error("--slug、または --before と --after の組のどちらか一方だけを指定してください。")
    if push_mode and (args.before is None or args.after is None):
        parser.error("push モードでは --before と --after の両方が必要です。")
    return args


def main() -> None:
    args = parse_args()
    output_file = os.environ.get("GITHUB_OUTPUT", "")
    if not output_file:
        die("GITHUB_OUTPUT が設定されていません。GitHub Actions の process ステップで実行してください。")

    if args.slug is not None:
        draft_rel = draft_from_dispatch(args.slug)
    else:
        draft_rel = draft_from_push(args.before, args.after)
    process(draft_rel, Path(output_file))


if __name__ == "__main__":
    main()
