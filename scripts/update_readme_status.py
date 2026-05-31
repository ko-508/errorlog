"""
README.md のステータスブロックを最新の集計データで自動更新する。

置換対象:
  <!-- STATUS_BEGIN --> … <!-- STATUS_END -->

集計内容:
  - content/posts/ の公開済み記事数（draft: true を除外）
  - フロントマターの tags から抽出した一意なツール名一覧
"""

import re
import sys
from pathlib import Path

BASE      = Path(__file__).parent.parent
POSTS_DIR = BASE / "content" / "posts"
README    = BASE / "README.md"

_STATUS_RE = re.compile(
    r"<!-- STATUS_BEGIN -->.*?<!-- STATUS_END -->",
    re.DOTALL,
)


# ツール一覧から除外するタグ（カテゴリ・ジャンルタグ等）
_EXCLUDE_TAGS = {"tool-guide"}


def collect_stats() -> tuple[int, list[str]]:
    """公開済み記事数と対応ツール一覧を集計する。"""
    published = 0
    tools: set[str] = set()

    for md in POSTS_DIR.glob("*.md"):
        text = md.read_text(encoding="utf-8")

        # フロントマター抽出
        fm_match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
        if not fm_match:
            continue
        fm = fm_match.group(1)

        # draft: true はスキップ
        if re.search(r"(?m)^draft:\s*true\s*$", fm):
            continue

        published += 1

        # tags フィールドからツール名を抽出
        # 形式例: tags: ["Docker"] または tags:\n  - Docker
        inline = re.search(r'(?m)^tags:\s*\[([^\]]+)\]', fm)
        if inline:
            for t in re.findall(r'"([^"]+)"|\'([^\']+)\'', inline.group(1)):
                name = t[0] or t[1]
                if name not in _EXCLUDE_TAGS:
                    tools.add(name)
        else:
            block = re.search(r'(?m)^tags:\s*\n((?:[ \t]+-[^\n]+\n?)+)', fm)
            if block:
                for t in re.findall(r'-\s*"?([^"\n]+)"?', block.group(1)):
                    name = t.strip()
                    if name not in _EXCLUDE_TAGS:
                        tools.add(name)

    return published, sorted(tools)


def build_status_block(published: int, tools: list[str]) -> str:
    tool_str = " / ".join(tools) if tools else "-"
    return (
        "<!-- STATUS_BEGIN -->\n"
        f"公開記事数: **{published} 件** ／ 対応ツール数: **{len(tools)} 種**\n\n"
        f"{tool_str}\n"
        "<!-- STATUS_END -->"
    )


def update_readme(published: int, tools: list[str]) -> bool:
    """README.md のステータスブロックを更新する。変更があれば True を返す。"""
    text = README.read_text(encoding="utf-8")
    new_block = build_status_block(published, tools)
    new_text = _STATUS_RE.sub(new_block, text)

    if new_text == text:
        print("README.md: 変更なし")
        return False

    README.write_text(new_text, encoding="utf-8")
    print(f"README.md: 更新完了（公開記事 {published} 件 / ツール {len(tools)} 種）")
    return True


def main() -> None:
    if not POSTS_DIR.exists():
        print(f"[ERROR] {POSTS_DIR} が見つかりません。", file=sys.stderr)
        sys.exit(1)
    if not README.exists():
        print(f"[ERROR] {README} が見つかりません。", file=sys.stderr)
        sys.exit(1)

    published, tools = collect_stats()
    print(f"集計: 公開記事 {published} 件 / ツール {len(tools)} 種")
    update_readme(published, tools)


if __name__ == "__main__":
    main()
