#!/usr/bin/env python3
"""
errlog — ターミナル完結型エラーコードデコーダー

使用法:
  python scripts/cli_errlog.py <tool> <error_code>
  python scripts/cli_errlog.py docker 503
  python scripts/cli_errlog.py github_api 422

データソース（優先順）:
  1. content/posts/{tool}_{code}.md  （公開済み記事のフロントマター）
  2. scripts/queue.csv               （生成キュー内の未公開記事）
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

BASE       = Path(__file__).parent.parent
SCRIPTS    = Path(__file__).parent
QUEUE_PATH = SCRIPTS / "queue.csv"
TOOLS_PATH = SCRIPTS / "tools.json"
POSTS_DIR  = BASE / "content" / "posts"
SITE_BASE  = "https://errorlog.jp"

# Unicode arrow / separator — fall back to ASCII when the console encoding
# (e.g. Windows CP932) cannot represent them.
_enc  = (getattr(sys.stdout, "encoding", None) or "ascii").lower()
_SAFE = _enc in ("utf-8", "utf-16", "utf-32")
_ARR  = "➜" if _SAFE else "->"   # ➔
_SEP  = "›" if _SAFE else ">"    # ›


# ── Helpers ───────────────────────────────────────────────────────────────────

def _slug(name: str) -> str:
    """ツール名をファイルスラグに変換する（replenish_queue.py と同一ロジック）。"""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _parse_frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip('"')
    return fm


def _find_published(tool_slug: str, code: str) -> dict | None:
    """公開済み記事ファイルから現象・URL を取得する。"""
    md = POSTS_DIR / f"{tool_slug}_{code}.md"
    if not md.exists():
        return None
    text = md.read_text(encoding="utf-8")
    fm   = _parse_frontmatter(text)
    return {
        "source":      "published",
        "title":       fm.get("title",       ""),
        "description": fm.get("description", ""),
        "causes":      [],
        "solutions":   [],
    }


def _find_in_queue(tool_slug: str, code: str) -> dict | None:
    """scripts/queue.csv から一致する行を返す。"""
    if not QUEUE_PATH.exists():
        return None
    with open(QUEUE_PATH, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if _slug(row["tool"]) == tool_slug and row["status_code"].strip() == code:
                return {
                    "source":      "queue",
                    "title":       f"{row['tool']} の {code} エラー：原因と解決策",
                    "description": row["official_meaning"].strip(),
                    "causes":      [c.strip() for c in row["causes"].split("|") if c.strip()],
                    "solutions":   [s.strip() for s in row["solutions"].split("|") if s.strip()],
                }
    return None


def _load_known_tools() -> list[str]:
    if not TOOLS_PATH.exists():
        return []
    try:
        return json.loads(TOOLS_PATH.read_text(encoding="utf-8")).get("tools", [])
    except Exception:
        return []


# ── Rendering ─────────────────────────────────────────────────────────────────

def _hr(width: int = 52) -> str:
    return "─" * width


def _render(tool_input: str, code: str, data: dict) -> str:
    tool_slug = _slug(tool_input)
    url       = f"{SITE_BASE}/posts/{tool_slug}_{code}/"
    lines     = []

    # ヘッダー
    lines += [
        _hr(),
        f"  {tool_input}  {_SEP}  {code}",
        _hr(),
        "",
    ]

    # 現象
    lines += [
        "現象",
        f"  {data['description'] or '（説明なし）'}",
        "",
    ]

    # 原因（queue データがある場合のみ）
    if data["causes"]:
        lines.append("原因")
        for i, c in enumerate(data["causes"][:4], 1):
            lines.append(f"  {i}. {c}")
        lines.append("")

    # 対策
    if data["solutions"]:
        lines.append("対策")
        for i, s in enumerate(data["solutions"][:4], 1):
            lines.append(f"  {i}. {s}")
        lines.append("")

    # 公開済みの場合は全詳細が記事にある旨を表示
    if data["source"] == "published" and not data["causes"]:
        lines += [
            "  詳細な原因・Before/After コード対比は記事をご確認ください。",
            "",
        ]

    # 導線 URL
    lines += [
        _hr(),
        "Before/After の修正コードを含む詳細な検証ログを確認する",
        f"  {_ARR}  {url}",
        _hr(),
    ]

    return "\n".join(lines)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="errlog",
        description="エラーコードをターミナルで即解読する CLI デコーダー",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  python scripts/cli_errlog.py docker 503
  python scripts/cli_errlog.py github_api 422
  python scripts/cli_errlog.py aws 403
""",
    )
    parser.add_argument("tool",  help="ツール名（例: docker, aws, firebase）")
    parser.add_argument("code",  help="HTTPステータスコード（例: 404, 503）")
    args = parser.parse_args()

    tool_slug = _slug(args.tool)
    code      = args.code.strip()

    # データ検索（公開済み → キュー の順）
    data = _find_published(tool_slug, code) or _find_in_queue(tool_slug, code)

    if data is None:
        known = _load_known_tools()
        slug_map = {_slug(t): t for t in known}
        canonical = slug_map.get(tool_slug)
        if canonical:
            print(f"  '{canonical} {code}' の記事はまだ存在しません。")
        else:
            print(f"  ツール '{args.tool}' は登録されていません。")
            if known:
                sample = ", ".join(known[:8])
                print(f"  登録済みツール例: {sample} ...")
        print(f"\n  {_ARR}  {SITE_BASE}/posts/{tool_slug}_{code}/")
        sys.exit(1)

    print(_render(args.tool, code, data))


if __name__ == "__main__":
    main()
