"""
content/posts/ 配下の全 Markdown Front Matter を検証する。
エラーがあれば stderr に出力して exit(1) → CI を止める。

チェック項目:
  1. YAML ブロック（---）の存在
  2. yaml.safe_load によるパース成功
  3. 必須フィールド（title, date, description, tags）の存在・非空
  4. tags がリスト型であること
  5. date / lastmod が ISO 8601 形式であること
  6. 文字列フィールドに制御文字・タブが混入していないこと
"""

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    # GitHub Actions ubuntu-latest には pyyaml がプリインストール済み
    # ローカル未インストール時は pip install pyyaml
    print("ERROR: pyyaml が必要です: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

POSTS_DIR    = Path("content/posts")
REQUIRED     = {"title", "date", "description", "tags"}
DATE_RE      = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FM_RE        = re.compile(r"^---\r?\n(.+?)\r?\n---", re.DOTALL)
CONTROL_RE   = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")  # タブ・改行を除く制御文字


def validate(path: Path) -> list[str]:
    errors = []

    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        return [f"{path.name}: 読み込みエラー: {e}"]

    # 1. Front Matter ブロックの存在確認
    m = FM_RE.match(text)
    if not m:
        return [f"{path.name}: Front Matter が見つからない（--- ブロックが存在しない）"]

    fm_raw = m.group(1)

    # 2. YAML パース
    try:
        fm = yaml.safe_load(fm_raw)
    except yaml.YAMLError as e:
        return [f"{path.name}: YAML 構文エラー: {e}"]

    if not isinstance(fm, dict):
        return [f"{path.name}: Front Matter が辞書型でない"]

    # 3. 必須フィールドの存在・非空
    for key in REQUIRED:
        val = fm.get(key)
        if val is None:
            errors.append(f"{path.name}: 必須フィールド '{key}' が欠落")
        elif val == "" or val == [] or val == [""] or val == [""]:
            errors.append(f"{path.name}: 必須フィールド '{key}' が空")

    # 4. tags がリスト型
    tags = fm.get("tags")
    if tags is not None and not isinstance(tags, list):
        errors.append(f"{path.name}: 'tags' がリスト型でない（値: {tags!r}）")

    # 5. date / lastmod の形式確認
    for date_field in ("date", "lastmod"):
        val = fm.get(date_field)
        if val is not None:
            date_str = str(val)
            if not DATE_RE.match(date_str):
                errors.append(f"{path.name}: '{date_field}' の形式が不正: {date_str!r}")

    # 6. 文字列フィールドへの制御文字混入
    str_fields = ("title", "description", "error_cause", "error_remedy")
    for field in str_fields:
        val = fm.get(field)
        if isinstance(val, str) and CONTROL_RE.search(val):
            errors.append(f"{path.name}: '{field}' に制御文字が混入")

    return errors


def main() -> int:
    if not POSTS_DIR.exists():
        print(f"ERROR: {POSTS_DIR} が見つかりません", file=sys.stderr)
        return 1

    files  = sorted(POSTS_DIR.glob("*.md"))
    errors = []
    for md in files:
        errors.extend(validate(md))

    if errors:
        print(f"❌ Front Matter バリデーション失敗 — {len(errors)} 件のエラー:\n", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    print(f"✅ {len(files)} ファイル検証完了 — 問題なし")
    return 0


if __name__ == "__main__":
    sys.exit(main())
