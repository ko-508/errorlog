"""
Phase 2: 既存記事への知識グラフメタデータ一括付与スクリプト

対象: service が未設定、または components が存在しない記事
除外: auto_* ドラフト記事

処理内容:
  - daily_publish.extract_knowledge_graph() を再利用（ロジック重複なし）
  - Front Matter のみ更新（本文・既存フィールドは一切変更しない）
  - service / error_type / components / related_services を追記

Usage:
  ANTHROPIC_API_KEY=... python scripts/backfill_knowledge_graph.py
  API_DELAY=0.5 DRY_RUN=1 python scripts/backfill_knowledge_graph.py  # ドライラン
"""

import json
import os
import re
import sys
import time
from pathlib import Path

BASE      = Path(__file__).parent.parent
POSTS_DIR = BASE / "content" / "posts"

# dry run: ファイル書き込みをスキップして結果だけ表示
DRY_RUN   = os.getenv("DRY_RUN", "0") == "1"
API_DELAY = float(os.getenv("API_DELAY", "0.5"))   # 秒（レートリミット対策）
MAX_ARTICLES = int(os.getenv("MAX_ARTICLES", "0"))  # 0 = 全件処理

# extract_knowledge_graph を daily_publish から再利用
sys.path.insert(0, str(Path(__file__).parent))
from daily_publish import extract_knowledge_graph, TOOL_TAGS


# ── ファイル名からツール名・エラーコードを抽出 ────────────────────────────────

def _slug_to_display(slug: str) -> str:
    """ツールスラグを表示名に変換。TOOL_TAGS で未定義なら Title Case で返す。"""
    if slug in TOOL_TAGS:
        return TOOL_TAGS[slug]
    return slug.replace("_", " ").title()


def _parse_stem(stem: str) -> tuple[str, str]:
    """ファイル stem からツール名とエラーコードを返す。

    例:
      aws_403         → ("AWS", "403")
      github_api_503  → ("GitHub API", "503")
      terraform_400   → ("Terraform", "400")
      tool_firebase   → ("Firebase", "")
    """
    # tool_* ガイド記事
    m_tool = re.match(r'^tool_(.+)$', stem)
    if m_tool:
        slug = m_tool.group(1)
        return _slug_to_display(slug), ""

    # {tool_slug}_{code} 形式（code は数字始まり）
    m_err = re.match(r'^(.+?)_(\d\w*)$', stem)
    if m_err:
        slug = m_err.group(1)
        code = m_err.group(2)
        return _slug_to_display(slug), code

    return stem.title(), ""


def _extract_first_tag(fm_text: str) -> str:
    """Front Matter テキストから最初の tags 値を取得する。"""
    m = re.search(r'^tags:\s*\[?"?([^"\]\n,]+)', fm_text, re.MULTILINE)
    return m.group(1).strip() if m else ""


# ── Front Matter 操作 ────────────────────────────────────────────────────────

def _needs_backfill(fm_text: str) -> bool:
    """service が未設定 または components が存在しない記事をバックフィル対象とする。"""
    has_service    = bool(re.search(r'^service:', fm_text, re.MULTILINE))
    has_components = bool(re.search(r'^components:', fm_text, re.MULTILINE))
    return not has_service or not has_components


def _update_frontmatter(text: str, kg: dict) -> str:
    """Front Matter に知識グラフフィールドを追記する。

    規則:
      - 既存フィールドは上書きしない
      - 本文（--- 以降）は変更しない
      - service が空文字の場合は追記しない
    """
    fm_match = re.match(r'^(---\n)(.*?)(\n---\n)', text, re.DOTALL)
    if not fm_match:
        return text

    fm_text = fm_match.group(2)
    additions = []

    if not re.search(r'^service:', fm_text, re.MULTILINE):
        if kg.get("service"):
            additions.append(f'service: "{kg["service"]}"')

    if not re.search(r'^error_type:', fm_text, re.MULTILINE):
        if kg.get("error_type"):
            additions.append(f'error_type: "{kg["error_type"]}"')

    if not re.search(r'^components:', fm_text, re.MULTILINE):
        additions.append(
            f'components: {json.dumps(kg.get("components", []), ensure_ascii=False)}'
        )

    if not re.search(r'^related_services:', fm_text, re.MULTILINE):
        additions.append(
            f'related_services: {json.dumps(kg.get("related_services", []), ensure_ascii=False)}'
        )

    if not additions:
        return text

    new_fm_text = fm_text + "\n" + "\n".join(additions)
    return (
        fm_match.group(1)
        + new_fm_text
        + fm_match.group(3)
        + text[fm_match.end():]
    )


def _get_body(text: str) -> str:
    """Front Matter 以降の本文を返す。"""
    m = re.match(r'^---\n.*?\n---\n\n?', text, re.DOTALL)
    return text[m.end():] if m else text


# ── メイン ────────────────────────────────────────────────────────────────────

def main() -> None:
    import anthropic as _anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY が未設定", file=sys.stderr)
        sys.exit(1)

    client = _anthropic.Anthropic(api_key=api_key)

    md_files = sorted(POSTS_DIR.glob("*.md"))

    stats = {
        "total":                len(md_files),
        "updated":              0,
        "skipped_draft":        0,
        "skipped_no_change":    0,
        "errors":               0,
        "service_added":        0,
        "error_type_added":     0,
        "components_added":     0,
        "related_services_added": 0,
        "components_nonempty":  0,
    }

    targets = []
    for md in md_files:
        # auto_* ドラフトはスキップ
        if md.name.startswith("auto_"):
            stats["skipped_draft"] += 1
            continue

        try:
            text = md.read_text(encoding="utf-8")
        except Exception as e:
            print(f"  [ERROR] {md.name}: 読み込み失敗 — {e}")
            stats["errors"] += 1
            continue

        fm_match = re.match(r'^---\n(.*?)\n---\n', text, re.DOTALL)
        if not fm_match:
            stats["skipped_no_change"] += 1
            continue

        fm_text = fm_match.group(1)
        if not _needs_backfill(fm_text):
            stats["skipped_no_change"] += 1
            continue

        targets.append(md)

    if MAX_ARTICLES > 0:
        targets = targets[:MAX_ARTICLES]

    print(f"バックフィル対象: {len(targets)} 件 / 総記事: {stats['total']} 件")
    if DRY_RUN:
        print("[DRY_RUN] ファイル書き込みをスキップします")
    print()

    for i, md in enumerate(targets):
        text    = md.read_text(encoding="utf-8")
        fm_match = re.match(r'^---\n(.*?)\n---\n', text, re.DOTALL)
        fm_text  = fm_match.group(1)

        # ツール名・コードをファイル名から取得（first_tag も補助で使用）
        tool_from_stem, code_from_stem = _parse_stem(md.stem)
        first_tag = _extract_first_tag(fm_text)

        # タグが取れた場合は優先（例: "GitHub API" > "Github Api"）
        tool = first_tag if first_tag and first_tag != "tool-guide" else tool_from_stem
        code = code_from_stem

        body = _get_body(text)

        # title は Front Matter から取得
        title_m = re.search(r'^title:\s*"?([^"\n]+)"?\s*$', fm_text, re.MULTILINE)
        title   = title_m.group(1).strip() if title_m else md.stem

        print(f"  [{i+1}/{len(targets)}] {md.name}")

        try:
            kg = extract_knowledge_graph(client, title, body, tool, code)
        except Exception as e:
            print(f"    [ERROR] API 失敗 — {e}")
            stats["errors"] += 1
            if API_DELAY > 0:
                time.sleep(API_DELAY)
            continue

        # 結果ログ
        comp_str = f"{kg['components']}" if kg["components"] else "[]"
        print(f"    service={kg['service']!r}  error_type={kg['error_type']!r}  components={comp_str}")

        new_text = _update_frontmatter(text, kg)

        if new_text == text:
            stats["skipped_no_change"] += 1
            if API_DELAY > 0:
                time.sleep(API_DELAY)
            continue

        if not DRY_RUN:
            md.write_text(new_text, encoding="utf-8")

        stats["updated"] += 1
        if kg.get("service")    and not re.search(r'^service:',          fm_text, re.MULTILINE): stats["service_added"]          += 1
        if kg.get("error_type") and not re.search(r'^error_type:',       fm_text, re.MULTILINE): stats["error_type_added"]       += 1
        if                          not re.search(r'^components:',        fm_text, re.MULTILINE): stats["components_added"]       += 1
        if                          not re.search(r'^related_services:',  fm_text, re.MULTILINE): stats["related_services_added"] += 1
        if kg.get("components"):
            stats["components_nonempty"] += 1

        if API_DELAY > 0 and i < len(targets) - 1:
            time.sleep(API_DELAY)

    # ── 最終レポート ────────────────────────────────────────────────────────
    total_targets = len(targets)
    comp_rate = (
        f"{stats['components_nonempty'] / stats['updated'] * 100:.0f}%"
        if stats["updated"] > 0 else "N/A"
    )

    print()
    print("=" * 50)
    print("=== バックフィル完了 ===")
    print("=" * 50)
    print(f"総記事数:                  {stats['total']}")
    print(f"処理対象:                  {total_targets}")
    print(f"更新記事数:                {stats['updated']}")
    print(f"service 付与数:            {stats['service_added']}")
    print(f"error_type 付与数:         {stats['error_type_added']}")
    print(f"components 付与数:         {stats['components_added']}")
    print(f"related_services 付与数:   {stats['related_services_added']}")
    print(f"components 非空率:         {comp_rate}  ({stats['components_nonempty']}/{stats['updated']})")
    print(f"スキップ（ドラフト）:      {stats['skipped_draft']}")
    print(f"スキップ（変更不要）:      {stats['skipped_no_change']}")
    print(f"エラー数:                  {stats['errors']}")
    if DRY_RUN:
        print("\n[DRY_RUN] ファイルは変更されていません")


if __name__ == "__main__":
    main()
