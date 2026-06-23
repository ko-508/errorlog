"""
薄いコンテンツ（1200文字未満）の記事を Claude で拡張するスクリプト。

各記事に以下を必ず追加:
  - 実際のエラーメッセージ例（コードブロック）
  - Before/After コード例
  - ツール固有の深掘り解説

実行:
  ANTHROPIC_API_KEY=xxx python scripts/expand_articles.py
  MAX_EXPAND=10 ANTHROPIC_API_KEY=xxx python scripts/expand_articles.py
  FORCE=1 MAX_EXPAND=5 ANTHROPIC_API_KEY=xxx python scripts/expand_articles.py

--from-lint モード（needs_rewrite 対象）:
  python scripts/expand_articles.py --from-lint --limit 5
  ↑ data/lint_report.json の needs_rewrite 記事を対象にする。
    1200字フィルタは無効化し、生成後に Lint 検証ループ（最大2回リトライ）を実施。
"""

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import anthropic

BASE      = Path(__file__).parent
POSTS_DIR = BASE.parent / "content" / "posts"
DELETED_FILE        = BASE.parent / "data" / "deleted_articles.json"
LINT_REPORT_PATH    = BASE.parent / "data" / "lint_report.json"
EXPAND_FAILURES_FILE = BASE.parent / "data" / "expand_failures.json"

MAX_EXPAND      = int(os.getenv("MAX_EXPAND", "10"))
FORCE           = os.getenv("FORCE", "0") == "1"
MIN_CHARS       = 1200
MAX_LINT_RETRIES = 2   # --from-lint モードでのリトライ上限

# tool-guide 記事の除外フィルタ（lint_articles.classify_article と同ロジック）
# tool-guide 記事（non_error_article）はエラー解決記事が安定するまで一時的に処理対象外。
# 再開する場合は _is_error_article() のフィルタ条件を調整する。
_NUMERIC_CODE_IN_STEM = re.compile(r"_\d{3}(?:[^0-9]|$)")


def _is_error_article(path: Path, fm: dict) -> bool:
    """エラー解決記事かどうかを判定する（lint_articles.classify_article と同一ロジック）。"""
    if fm.get("errorCode", "").strip():
        return True
    if _NUMERIC_CODE_IN_STEM.search(path.stem):
        return True
    return False

_SYSTEM = """\
あなたは「ErrorLog（errorlog.jp）」専任のテクニカルライターです。
日本人エンジニア向けに、HTTPエラーの原因と解決策を実用的に解説する記事を執筆します。

## 必須セクション（この順番で記述）

### 1. エラーの概要（H2）
このエラーの公式な意味と、対象ツールでの典型的な発生状況を2〜3文で説明する。

### 2. 実際のエラーメッセージ例（H2）
対象ツールが実際に出力するエラーログ・JSONレスポンス・コンソール出力を
コードブロックで1〜2個示す。実在しそうなリアルな例を記述すること。

コードブロックの直後に必ず **エラーメッセージの読み方：** という太字ラベルを付け、
エラー文の主要な構成要素を Markdown リストで 3〜5 項目に分解して説明する。
各項目は `要素` → 意味の説明 の形式で書く。
分解できる構成要素が少ない場合でも 1〜2 項目で要素の意味を説明すること。

### 3. よくある原因と解決手順（H2）
各原因について:
- 「なぜ発生するか」の説明
- 必ず以下の**厳密な形式**でBefore/Afterを記述する（太字ラベルが必須）:

  **Before（エラーが起きるコード）：**

  ```言語名
  # エラーが発生するコードや設定
  ```

  **After（修正後）：**

  ```言語名
  # 修正後のコードや設定
  ```

  After ブロックの直後に必ず以下の形式で確認ステップを記述すること：

  ✅ 修正後の確認：

  ```言語名
  # 修正が反映されたかを確認するコマンドまたは手順
  ```

  修正が成功した場合に期待される動作・出力を 1 文で説明する。
  コマンドで確認できない場合はコードブロックを省略し 1 文で記述すること。

を必ずセットで記述する。原因は最低3つ挙げる。

### 4. ツール固有の注意点（H2）
ツールの特性に応じた深掘りを記述する。例:
- AWS: API Gateway / S3 / Cognito / Lambda など頻出サービスごとの原因
- Docker: Compose設定 / レジストリ認証 / ネットワーク設定
- Kubernetes: RBAC / ServiceAccount / Namespace の設定ミス
- Nginx: location設定 / upstream設定 / プロキシヘッダー
- Stripe: APIバージョン / Webhookの署名検証 / 冪等性キー
など、そのツールで実際によく起きるパターンを解説する。

### 5. それでも解決しない場合（H2）
- 確認すべきログの場所やデバッグコマンド
- 公式ドキュメントへの参照（具体的なページ名）
- コミュニティリソース（GitHub Issues等）

## 品質要件
- 全体で1500文字以上2500文字以下（日本語本文のみ。マークダウン記号・URL・コードは除いてカウント）
- H1タイトルは含めない
- コードブロックには必ず言語名を指定（bash, json, yaml, python, javascript等）
- コードブロックは必ず ``` で開き、``` で閉じること（閉じ忘れ厳禁）
- プレースホルダーは `<your-xxx>` 形式
- ですます調・断定的に書く
- ふりがな補足は不要（「デプロイ（展開）」のような自明な言い換えは書かない）
- 「まとめ」セクションは不要

## 保持制約（既存記事を参考にする場合）
- 「実際のエラーメッセージ例」セクションに既存の具体的なエラー文字列・エラーコード・
  レスポンス例がある場合、それらは要約・短縮・改変せず原文のまま保持すること。
  構造の再編や情報の整理を理由に削除・省略してはならない。

## セキュリティ制約
- 認証トークン・パスワード・APIキー等の秘密情報を平文で出力・表示・デコードするコマンド
  （例: `base64 -d` で auth フィールドを復号して画面に出力する、`cat` で credentials ファイルを
  表示する等）を解決手順に含めないこと。
- 秘密情報の確認が必要な場合も、値を画面に出力しない方法（存在確認のみ・ファイルパーミッション
  確認・ログイン再実行等）を示すこと。

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
    """Before/After labels are normalized to canonical format outside code blocks."""
    parts = re.split(r'(```[\s\S]*?```)', text)
    for i, part in enumerate(parts):
        if i % 2 == 0:
            part = _BEFORE_LABEL_RE.sub(_BEFORE_NORM, part)
            part = _AFTER_LABEL_RE.sub(_AFTER_NORM, part)
            parts[i] = part
    return ''.join(parts)


# ─── データロード ──────────────────────────────────────────────

def _load_deleted_paths() -> set[str]:
    """Return set of paths recorded in data/deleted_articles.json."""
    if not DELETED_FILE.exists():
        return set()
    try:
        data = json.loads(DELETED_FILE.read_text(encoding="utf-8"))
        return {e["path"] for e in data if isinstance(e, dict) and "path" in e}
    except Exception:
        return set()


def _load_needs_rewrite() -> list[dict]:
    """data/lint_report.json の needs_rewrite 記事エントリを返す。

    needs_rewrite = error_article かつ FAIL あり かつ B2 なし

    各エントリ: {"path": str, "fail_rules": list[str]}
    順序: A3のみFAIL（文字数不足）→ A1含むFAIL（旧テンプレート）
    """
    if not LINT_REPORT_PATH.exists():
        print(f"  [warn] lint_report.json が見つかりません: {LINT_REPORT_PATH}", file=sys.stderr)
        return []
    try:
        data = json.loads(LINT_REPORT_PATH.read_text(encoding="utf-8"))
        entries = []
        for r in data.get("articles", []):
            cat = r.get("category", "error_article")
            fail_rules = [f["rule"] for f in r.get("fails", [])]
            fail_set = set(fail_rules)
            if cat == "error_article" and fail_set and "B2" not in fail_set:
                entries.append({"path": r["path"], "fail_rules": fail_rules})
        # A3のみ（文字数不足）を先に、A1含む（旧テンプレート）を後に
        entries.sort(key=lambda e: "A1" in e["fail_rules"])
        return entries
    except Exception as e:
        print(f"  [warn] lint_report.json 読み込みエラー: {e}", file=sys.stderr)
        return []


def _filter_pending(
    entries: list[dict],
    base_path: Path,
    deleted_paths: set[str],
) -> list[tuple[Path, list[str]]]:
    """needs_rewrite エントリから既に clean な記事・削除済み記事を除外する。

    ライブ Lint チェックを実施するため、expand 実行後でも正確に未処理記事のみを返す。
    これにより日次バッチで「同じ記事を再処理」する問題を防ぐ。

    戻り値: [(Path, fail_rules), ...] — _load_needs_rewrite の順序（A3先・A1後）を保持
    """
    pending = []
    for entry in entries:
        rel = entry["path"]
        p = base_path / rel
        if not p.exists() or rel in deleted_paths:
            continue
        passed, _ = _lint_check(p)
        if not passed:
            pending.append((p, entry["fail_rules"]))
    return pending


# ─── Lint 検証 ────────────────────────────────────────────────

def _lint_check(path: Path) -> tuple[bool, list[str]]:
    """lint_articles.lint_article() を呼んで (passed, fail_detail_list) を返す。

    fail_detail_list の各要素は "RULE: detail" 形式。
    """
    _scripts_dir = str(Path(__file__).parent)
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)
    from lint_articles import lint_article  # type: ignore
    result = lint_article(path)
    fails = result.get("fails", [])
    details = [f"{f['rule']}: {f['detail']}" for f in fails]
    return not fails, details


def _format_lint_feedback(fail_details: list[str]) -> str:
    """FAIL 詳細を Claude 向けフィードバック文字列に変換する。"""
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
        elif rule == "A6":
            lines.append(f"・{detail}")
            lines.append("  → フロントマターに不足フィールドを追加すること（本文への記述は不要）。")
        else:
            lines.append(f"・{detail}")
    return "\n".join(lines)


# ─── 失敗ログ ─────────────────────────────────────────────────

def _save_expand_failure(path_str: str, fail_details: list[str], attempts: int) -> None:
    """expand_failures.json にリトライ超過記事を記録する。path で重複排除。"""
    records: list[dict] = []
    if EXPAND_FAILURES_FILE.exists():
        try:
            records = json.loads(EXPAND_FAILURES_FILE.read_text(encoding="utf-8"))
        except Exception:
            records = []
    records = [r for r in records if r.get("path") != path_str]
    records.append({
        "path": path_str,
        "failed_at": date.today().isoformat(),
        "attempts": attempts,
        "remaining_fails": fail_details,
    })
    EXPAND_FAILURES_FILE.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ─── フロントマター操作 ────────────────────────────────────────

def parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm_text = text[3:end].strip()
    body    = text[end + 4:].lstrip("\n")
    fm: dict = {}
    for line in fm_text.splitlines():
        m = re.match(r'^(\w+):\s*(.+)', line)
        if m:
            fm[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return fm, body


def get_frontmatter_block(text: str) -> str:
    m = re.match(r"^(---\n.*?\n---\n)", text, re.DOTALL)
    return m.group(1) if m else ""


# ─── 文字数計算 ───────────────────────────────────────────────

def body_char_count(body: str) -> int:
    text = re.sub(r'```[\s\S]*?```', '', body)       # コードブロック除去
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # リンク→テキストのみ
    text = re.sub(r'[#\-*`>\[\]()!]', '', text)
    return len(text.replace(' ', '').replace('\n', ''))


def needs_expand(body: str) -> bool:
    return body_char_count(body) < MIN_CHARS


# ─── Claude 生成 ──────────────────────────────────────────────

def expand_with_claude(
    client: anthropic.Anthropic,
    title: str,
    tool: str,
    code: str,
    old_body: str,
    lint_feedback: str = "",
) -> str:
    """記事本文を Claude で完全再生成する。

    lint_feedback が指定された場合、前回 Lint で検出された問題をプロンプトに
    含めて再生成を促す（自己修復ループ用）。
    """
    feedback_section = ""
    if lint_feedback:
        feedback_section = f"""

## 前回生成で検出された構造エラー（必ず全て修正すること）
{lint_feedback}

上記エラーを修正する際の注意:
- コードブロックは必ず ``` 言語名 で開き、独立した行の ``` で閉じること
- セクション見出しは ## (H2) で記述すること
- 5セクション全てが揃っているか最終確認すること
"""

    prompt = f"""## 記事情報
- タイトル: {title}
- ツール: {tool}
- エラーコード: {code}

## 現在の記事（参考）
{old_body[:600]}
{feedback_section}
## 執筆依頼
上記の「{tool} の {code} エラー」について、必須セクションをすべて含む完全な記事を執筆してください。
現在の記事の内容は参考程度に活用し、より詳細・実用的な内容に拡張してください。"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4000,
        system=[{
            "type": "text",
            "text": _SYSTEM,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


# ─── メイン ───────────────────────────────────────────────────

_DISCLAIMER = (
    "\n\n---\n\n"
    "*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。"
    "ソフトウェアの仕様は予告なく変更されることがあります。"
    "最新の情報は各ツールの公式サポートページをご確認ください。"
    "本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*"
)


def main() -> None:
    parser = argparse.ArgumentParser(description="薄い記事・needs_rewrite 記事を Claude で拡張する")
    parser.add_argument(
        "--from-lint",
        action="store_true",
        help="data/lint_report.json の needs_rewrite 記事を対象にする。"
             "1200字フィルタを無効化し、生成後に Lint 検証ループ（最大2回リトライ）を実施する。",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="処理する記事数の上限（少数検証用）。省略時は MAX_EXPAND 環境変数または 10 件。",
    )
    parser.add_argument(
        "--paths",
        type=str,
        default=None,
        metavar="FILE1,FILE2",
        help="対象ファイル名をカンマ区切りで指定（例: docker_401.md,azure_429.md）。"
             "--from-lint と併用可能。指定ファイルが対象リストにない場合はスキップ。",
    )
    args = parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("エラー: ANTHROPIC_API_KEY が設定されていません。")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    today  = date.today().isoformat()
    deleted_paths = _load_deleted_paths()

    # ── 対象記事の選定 ──────────────────────────────────────
    if args.from_lint:
        nrw_entries = _load_needs_rewrite()
        if not nrw_entries:
            print("needs_rewrite 記事が見つかりませんでした。lint_report.json を確認してください。")
            return

        # ライブ Lint で既に clean な記事を除外（日次バッチの重複処理防止）
        print(f"  残り記事を確認中（lint_report.json: {len(nrw_entries)} 件）...", end="", flush=True)
        pending = _filter_pending(nrw_entries, BASE.parent, deleted_paths)
        print(" 完了")

        if not pending:
            print("未処理の needs_rewrite 記事はありません。全件 Lint PASS 済みです。")
            return

        a3_only = [(p, fr) for p, fr in pending if "A1" not in fr]
        has_a1  = [(p, fr) for p, fr in pending if "A1" in fr]

        limit = args.limit if args.limit is not None else MAX_EXPAND
        to_process = pending[:limit]

        today_a3 = [(p, fr) for p, fr in to_process if "A1" not in fr]
        today_a1 = [(p, fr) for p, fr in to_process if "A1" in fr]

        print(f"\n--from-lint モード:")
        print(f"  残り未処理: {len(pending)} 件"
              f"  （文字数不足: {len(a3_only)} / 旧テンプレート: {len(has_a1)}）")
        print(f"  今回処理:   {len(to_process)} 件"
              f"  （文字数不足: {len(today_a3)} / 旧テンプレート: {len(today_a1)}）")
        print(f"  Lint 検証ループ: 最大 {MAX_LINT_RETRIES} 回リトライ\n")

        targets = [p for p, _ in to_process]
    else:
        posts = sorted(POSTS_DIR.glob("*.md"), key=lambda p: p.name)
        targets = []
        for src in posts:
            if src.name.startswith("_"):
                continue
            rel = f"content/posts/{src.name}"
            if rel in deleted_paths:
                continue
            text = src.read_text(encoding="utf-8")
            fm, body = parse_frontmatter(text)
            if fm.get("draft", "").lower() == "true":
                continue
            # tool-guide 記事（non_error_article）は一時的に除外。
            # 再開する場合は下記 _is_error_article() フィルタを外す。
            if not _is_error_article(src, fm):
                continue
            if FORCE or needs_expand(body):
                targets.append(src)
        limit = args.limit if args.limit is not None else MAX_EXPAND
        targets = targets[:limit]
        print(f"拡張対象: {len(targets)} 件（閾値: {MIN_CHARS}文字未満）\n")

    # --paths: 指定ファイルのみに絞り込む
    if args.paths:
        specified = {Path(p).name for p in args.paths.split(",")}
        targets = [t for t in targets if t.name in specified]
        if not targets:
            print(f"  [warn] --paths の指定ファイルが対象リストに見つかりません: {args.paths}")
            return
        print(f"  --paths フィルタ適用: {[t.name for t in targets]}\n")

    # ── 処理ループ ───────────────────────────────────────────
    expanded = 0
    skipped  = 0

    for src in targets:
        original_text = src.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(original_text)
        title = fm.get("title", src.stem)

        # ツール名とエラーコードをタイトルから抽出
        m = re.match(r'^(.+?) の (\d+) エラー', title)
        if m:
            tool = m.group(1)
            code = m.group(2)
        else:
            tool = fm.get("tags", src.stem.split("_")[0] if "_" in src.stem else src.stem)
            code = fm.get("errorCode", "")

        print(f"  処理中: {src.name}")

        # frontmatter に lastmod を追加/更新
        fm_block = get_frontmatter_block(original_text)
        if "lastmod:" in fm_block:
            new_fm = re.sub(r"lastmod:.*", f"lastmod: {today}", fm_block)
        else:
            new_fm = re.sub(r"\n---\n$", f"\nlastmod: {today}\n---\n", fm_block)

        # --from-lint: Lint 検証ループ付き生成
        # 通常モード: 1回生成して保存
        use_lint_loop = args.from_lint
        lint_fails: list[str] = []
        lint_passed = False
        succeeded = False

        for attempt in range(MAX_LINT_RETRIES + 1 if use_lint_loop else 1):
            feedback = _format_lint_feedback(lint_fails) if lint_fails else ""
            label = f"[試行{attempt + 1}/{MAX_LINT_RETRIES + 1}]" if use_lint_loop else ""

            try:
                new_body = expand_with_claude(client, title, tool, code, body, feedback)
            except Exception as e:
                print(f"  {label} Claude エラー: {e}")
                break

            # Claude が末尾に免責事項を含める場合は除去（_DISCLAIMER で統一追加するため）
            _disc_marker = "\n\n---\n\n*免責事項"
            if _disc_marker in new_body:
                new_body = new_body[:new_body.rfind(_disc_marker)].rstrip()

            char_count = body_char_count(new_body)
            new_body = normalize_before_after(new_body)
            new_content = new_fm + "\n" + new_body + _DISCLAIMER
            src.write_text(new_content, encoding="utf-8")

            if use_lint_loop:
                lint_passed, lint_fails = _lint_check(src)
                status = "PASS" if lint_passed else f"FAIL({', '.join(d.split(':')[0] for d in lint_fails[:3])})"
                print(f"  {label} {char_count}字 lint:{status}")
                if lint_fails:
                    for d in lint_fails:
                        print(f"    {d}")
                if lint_passed:
                    succeeded = True
                    break
                # 最終リトライで FAIL なら次の if で処理
            else:
                print(f"  → {char_count} 文字")
                succeeded = True
                break

        if use_lint_loop and not succeeded:
            # 元の内容に戻す
            src.write_text(original_text, encoding="utf-8")
            rel_path = f"content/posts/{src.name}"
            _save_expand_failure(rel_path, lint_fails, MAX_LINT_RETRIES + 1)
            print(f"  → スキップ (expand_failures.json に記録)")
            skipped += 1
        elif succeeded:
            expanded += 1
        else:
            # Claude エラーで break した場合（ファイル未変更 or 途中まで書き込まれた可能性）
            src.write_text(original_text, encoding="utf-8")
            skipped += 1

    # ── サマリ ───────────────────────────────────────────────
    print(f"\n完了: {expanded} 件拡張・保存 / {skipped} 件スキップ")
    if args.from_lint and skipped > 0:
        print(f"  スキップ詳細: data/expand_failures.json を参照")


if __name__ == "__main__":
    main()
