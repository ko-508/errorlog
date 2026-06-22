"""
content/posts/ の記事を定期的にチェックし、古くなったものを
Gemini（リサーチ） → Claude（ライティング） → Claude（セルフレビュー） の3段階で更新する。
3ヶ月（90日）に一度 GitHub Actions から実行される想定。

動作：
  1. 全記事のフロントマターから date / lastmod を確認
  2. REFRESH_DAYS 日以上更新されていない記事を抽出
  3. Gemini が Google検索で最新情報をリサーチ
  4. Claude がリサーチ結果をもとに記事をリライト
  5. 独立したレビューエージェントが品質を検証（PASS のみ保存）
  6. frontmatter の lastmod を今日の日付に更新して保存
"""

import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

import anthropic
from google import genai as google_genai
from google.genai import types as genai_types

# expand_articles の expand_with_claude / body_char_count を再利用
sys.path.insert(0, str(Path(__file__).parent))
from expand_articles import expand_with_claude as _expand_thin, body_char_count as _body_char_count

REFRESH_DAYS         = int(os.getenv("REFRESH_DAYS", "90"))
MAX_REFRESH          = int(os.getenv("MAX_REFRESH", "20"))
MAX_RETRIES          = 1  # レビュー失敗時の再生成回数
THIN_CHAR_THRESHOLD  = int(os.getenv("THIN_CHAR_THRESHOLD", "1200"))

BASE               = Path(__file__).parent
POSTS_DIR          = BASE.parent / "content" / "posts"
PRIORITY_FILE      = BASE / "rewrite_priority.json"
DELETED_FILE       = BASE.parent / "data" / "deleted_articles.json"
COMPETITOR_FILE    = BASE / "competitor_analysis.json"
REFRESH_MANIFEST   = BASE / "refresh_manifest.json"
REWRITE_REPORT_FILE = BASE / "rewrite_report.json"  # Phase 4: リライト前後比較
REVIEW_ERROR_HISTORY_PATH = BASE.parent / "data" / "refresh_review_errors.json"


# ─── 競合コンテキスト ─────────────────────────────────────

def _load_deleted_paths() -> set[str]:
    """Return set of paths recorded in data/deleted_articles.json."""
    if not DELETED_FILE.exists():
        return set()
    try:
        data = json.loads(DELETED_FILE.read_text(encoding="utf-8"))
        return {e["path"] for e in data if isinstance(e, dict) and "path" in e}
    except Exception:
        return set()


def _load_competitor_context(title: str) -> str:
    """
    competitor_analysis.json から記事タイトルに関連するクエリを探し、
    競合の見出し構造をプロンプト用テキストで返す。
    ファイルが存在しない・読み込み失敗・データなしの場合は空文字を返す。
    """
    if not COMPETITOR_FILE.exists():
        return ""
    try:
        data    = json.loads(COMPETITOR_FILE.read_text(encoding="utf-8"))
        results = data.get("results", [])
        if not results:
            return ""

        title_lower = title.lower()

        # タイトルのトークンと top_query が重複するエントリを優先
        best: dict | None = None
        for r in results:
            query_terms = set((r.get("query") or "").lower().split())
            if any(t in title_lower for t in query_terms if len(t) > 2):
                best = r
                break
        if best is None:
            best = results[0]  # マッチなければ先頭エントリを使用

        competitors = [c for c in best.get("competitors", []) if not c.get("error")]
        if not competitors:
            return ""

        lines = [
            f"## 競合サイトの見出し構造（参考クエリ: {best.get('query', '')}）",
            "以下の競合サイトの見出し構造（ファクト）を参考に、"
            "自社記事に足りない専門的な要素や解決ステップを網羅した本文を生成してください。",
            "",
        ]
        for i, c in enumerate(competitors, 1):
            lines.append(f"【競合{i}】{c.get('title', '')}")
            if c.get("h2"):
                lines.append("H2: " + " / ".join(c["h2"][:6]))
            if c.get("h3"):
                lines.append("H3: " + " / ".join(c["h3"][:8]))
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        print(f"  [competitor] コンテキスト読み込みエラー（スキップ）: {e}")
        return ""


# ─── 薄い記事リスト ───────────────────────────────────────

def _load_thin_titles() -> set[str]:
    """rewrite_priority.json から is_thin: true の記事タイトルを返す。"""
    if not PRIORITY_FILE.exists():
        return set()
    try:
        entries: list[dict] = json.loads(PRIORITY_FILE.read_text(encoding="utf-8"))
        return {e["title"] for e in entries if e.get("is_thin")}
    except Exception as e:
        print(f"  [thin] rewrite_priority.json 読み込みエラー（スキップ）: {e}")
        return set()


def _load_top_queries() -> dict[str, str]:
    """rewrite_priority.json から title → top_query の辞書を返す（Phase 5）。"""
    if not PRIORITY_FILE.exists():
        return {}
    try:
        entries: list[dict] = json.loads(PRIORITY_FILE.read_text(encoding="utf-8"))
        return {e["title"]: e["top_query"] for e in entries if e.get("top_query")}
    except Exception as e:
        print(f"  [top_query] rewrite_priority.json 読み込みエラー（スキップ）: {e}")
        return {}


def _load_gsc_ctr() -> dict[str, dict]:
    """rewrite_priority.json から title → {ctr, impressions, position} の辞書を返す。"""
    if not PRIORITY_FILE.exists():
        return {}
    try:
        entries: list[dict] = json.loads(PRIORITY_FILE.read_text(encoding="utf-8"))
        return {
            e["title"]: {
                "ctr":         e.get("gsc_ctr", 0.0),
                "impressions": e.get("gsc_impressions", 0),
                "position":    e.get("position", 0.0),
            }
            for e in entries
            if e.get("gsc_ctr") is not None
        }
    except Exception as e:
        print(f"  [gsc_ctr] rewrite_priority.json 読み込みエラー（スキップ）: {e}")
        return {}


# ─── Phase 2: search_queries.json ローダー ───────────────────

def _load_search_queries_file() -> dict[str, list[str]]:
    """data/search_queries.json から slug → top_queries list の辞書を返す（Phase 2）。"""
    sq_file = BASE.parent / "data" / "search_queries.json"
    if not sq_file.exists():
        return {}
    try:
        data = json.loads(sq_file.read_text(encoding="utf-8"))
        return {slug: v.get("top_queries", []) for slug, v in data.items()}
    except Exception as e:
        print(f"  [search_queries] 読み込みエラー（スキップ）: {e}")
        return {}


# ─── Phase 5: priority_score ローダー ────────────────────────

def _load_priority_scores() -> dict[str, float]:
    """rewrite_priority.json から title → priority_score の辞書を返す（Phase 5）。"""
    if not PRIORITY_FILE.exists():
        return {}
    try:
        entries: list[dict] = json.loads(PRIORITY_FILE.read_text(encoding="utf-8"))
        return {e["title"]: float(e.get("priority_score", 0.0)) for e in entries}
    except Exception as e:
        print(f"  [priority_scores] 読み込みエラー（スキップ）: {e}")
        return {}


# ─── Phase 4: リライトレポート ────────────────────────────────

def _save_rewrite_report(entry: dict) -> None:
    """scripts/rewrite_report.json へリライト結果を追記する（slug+rewrite_date で重複排除）。"""
    records: list[dict] = []
    if REWRITE_REPORT_FILE.exists():
        try:
            records = json.loads(REWRITE_REPORT_FILE.read_text(encoding="utf-8"))
        except Exception:
            records = []

    slug = entry.get("slug", "")
    rewrite_date = entry.get("rewrite_date", "")
    records = [
        r for r in records
        if not (r.get("slug") == slug and r.get("rewrite_date") == rewrite_date)
    ]
    records.append(entry)
    REWRITE_REPORT_FILE.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ─── フロントマター操作 ────────────────────────────────────

def parse_frontmatter(text: str) -> dict:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return {}
    fm = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip().strip('"')
    return fm


def get_body(text: str) -> str:
    match = re.match(r"^---\n.*?\n---\n\n?", text, re.DOTALL)
    return text[match.end():] if match else text


def get_frontmatter_block(text: str) -> str:
    match = re.match(r"^(---\n.*?\n---\n)", text, re.DOTALL)
    return match.group(1) if match else ""


def _load_refresh_manifest() -> dict:
    """scripts/refresh_manifest.json を読み込む。存在しなければ空 dict。"""
    if not REFRESH_MANIFEST.exists():
        return {}
    try:
        return json.loads(REFRESH_MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_refresh_manifest(manifest: dict) -> None:
    REFRESH_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )


def needs_refresh(fm: dict, stem: str, threshold_days: int, manifest: dict) -> bool:
    """マニフェストを優先して最終リライト日を判定する。

    - refresh_due: true が frontmatter に存在: 即 True（薄い記事フラグ）
    - マニフェストあり: このスクリプトが最後にリライトした日 >= threshold_days 前なら True
    - マニフェストなし（初回/未リライト）: 記事の date で判定
    他スクリプトが lastmod を更新しても影響を受けない。
    """
    if fm.get("refresh_due") is True:
        return True
    if stem in manifest:
        try:
            last = datetime.strptime(manifest[stem], "%Y-%m-%d").date()
            return (date.today() - last).days >= threshold_days
        except (ValueError, TypeError):
            pass
    # 未登録の場合は記事の date を参照（lastmod は他スクリプトが更新するため使わない）
    date_key = fm.get("date")
    if not date_key:
        return True
    try:
        last_date = datetime.strptime(date_key, "%Y-%m-%d").date()
        return (date.today() - last_date).days >= threshold_days
    except ValueError:
        return True


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


# ─── Step 1: Gemini でリサーチ ─────────────────────────────

def research_with_gemini(
    gemini_model,
    title: str,
    old_body: str,
    competitor_context: str = "",
) -> str:
    """Gemini + Google検索で記事テーマの最新情報を収集する。"""
    competitor_hint = (
        f"\n\n## 競合サイトが扱っている見出し（参考）\n{competitor_context}\n"
        "上記競合が扱っているが現記事に欠けているトピックも調査してください。"
        if competitor_context else ""
    )

    prompt = f"""以下のタイトルの技術記事を最新版にアップデートするためのリサーチをしてください。

## 記事タイトル
{title}

## 現在の記事内容
{old_body[:800]}

## リサーチしてほしいこと
1. 記事に登場するコマンドや設定が現在も正しいか確認する
2. 公式ドキュメントの最新URLや推奨手順を調べる
3. このエラーに関して最近変更された点・新しい解決策があれば調べる
4. 現在の標準的な対処方法をまとめる{competitor_hint}

調査結果を箇条書きでまとめてください。日本語で回答してください。"""

    try:
        response = gemini_model.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())]
            ),
        )
        return response.text
    except Exception as e:
        print(f"    Gemini リサーチエラー: {e}")
        return ""


# ─── Step 2: Claude でリライト ─────────────────────────────

def rewrite_with_claude(
    claude_client: anthropic.Anthropic,
    title: str,
    old_body: str,
    research: str,
    review_feedback: str = "",
    competitor_context: str = "",
    top_query: str = "",
    gsc_ctr: float | None = None,
    gsc_impressions: int | None = None,
    top_queries: list[str] | None = None,
) -> str:
    """Geminiのリサーチ結果をもとに Claude が記事をリライトする。

    Phase 2: top_queries（複数クエリ）が指定された場合は CTR向上を主目的とした
    H1 / H2 最適化指示を追加する。
    Phase 3: CTR最適化指示に良い例・悪い例を追加。
    """
    research_section = f"""
## Gemini による最新情報リサーチ結果
{research}
""" if research else "（リサーチ結果なし：元の内容を改善してください）"

    feedback_section = f"""
## 前回レビューの指摘事項（必ず修正すること）
{review_feedback}
""" if review_feedback else ""

    # Phase 2: 複数クエリ対応（top_queries 優先、フォールバックで top_query）
    _all_queries: list[str] = []
    if top_queries:
        _all_queries = [q for q in top_queries if q][:5]
    elif top_query:
        _all_queries = [top_query]

    search_query_section = ""
    if _all_queries:
        query_bullets = "\n".join(f"- {q}" for q in _all_queries)
        search_query_section = f"""
## 実際の検索クエリ（Search Console より）
ユーザーはこの記事に以下のクエリで流入している:
{query_bullets}
→ H1 / H2 見出しを、これらのクエリに含まれる具体的な語句に近づけること。
→ 最初の H2 見出しにエラーコード・サービス名・症状を含めること。
"""

    # Phase 3: CTR向上最適化指示（低CTR記事のみ）、良い例・悪い例を追加
    ctr_section = ""
    if gsc_ctr is not None and gsc_impressions is not None and gsc_ctr < 0.01 and gsc_impressions > 100:
        ctr_section = f"""
## CTR最適化指示（現在 CTR={gsc_ctr:.1%} / インプレッション={gsc_impressions}）
この記事はインプレッション数が多いにもかかわらず CTR が極めて低い。
**H1 / H2 見出しの改善が最優先**。以下の方針で修正すること:

- 曖昧な表現は禁止（例: 「エラーが発生する」→「403 Forbidden: Access Denied on S3」）
- 実際のエラーメッセージに含まれる語句を H1 相当の見出しに含める
- H1 の良い例（具体的）:
  「Terraform 403 Forbidden on S3 Bucket — 原因と解決策」
  「Terraform Access Denied Error: IAM ポリシー修正ガイド」
- H1 の悪い例（禁止）:
  「Terraform エラーガイド」「Terraform トラブルシューティング」「Terraform の問題を完全解決」
- description は「なぜ起きるか」「何をすれば直るか」を 40 文字以内で断言する
"""

    prompt = f"""あなたは日本人向けの技術記事ライターです。
以下の「元の記事」を、「最新情報リサーチ結果」をもとに最新版にリライトしてください。

{research_section}{feedback_section}{search_query_section}{ctr_section}

## 元の記事
{old_body}

## リライトの要件
- リサーチ結果で判明した最新情報・変更点を記事に反映する
- 古くなったコマンドや手順を最新の書き方に修正する
- 読者はIT初心者・非エンジニアも含むため、平易な日本語にする
- 専門用語には括弧で補足説明を加える（例：「API（外部サービスとのやり取り口）」）
- Markdown形式を維持する（H2見出し、コードブロックなど）
- H1タイトル行は含めない
- 構成（見出し構造）は変えずに内容を更新する
- 文字数は元の記事と同程度（±20%以内）
- 必ず以下の5セクションを含めること:
  1. エラーの概要
  2. 実際のエラーメッセージ例（コードブロック付き）
  3. よくある原因と解決手順（Before/Afterコード対比を含む）
  4. ツール固有の注意点
  5. それでも解決しない場合
- Before/Afterラベルは必ず **Before（エラーが起きるコード）：** と **After（修正後）：** の形式で記述する
- 末尾に免責事項フッターを付ける
- プレースホルダーは `<your-xxx>` 形式で書くこと
- コード例の変数値・ヘッダー値・文字列リテラルとして、認証トークンやAPIキーを
  実際の値らしい形式で記述しないこと（Before例・After例・失効例すべてに適用）。
  プレフィックス文字列(xoxb-、sk-proj-、pk_live_、AKIA、ghp_、glpat- など)を
  値の先頭に付けた形も書かないこと。トークン部分は必ず `<your-xxx>` 形式にすること
{f'''
{competitor_context}
''' if competitor_context else ''}
リライト後の本文のみを出力してください（前置き・説明は不要）。"""

    message = claude_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


# ─── Phase 3: SEO メタデータ最適化 ────────────────────────

def generate_seo_metadata(
    claude_client: anthropic.Anthropic,
    title: str,
    description: str,
    top_queries: list[str],
    gsc_ctr: float | None = None,
) -> dict:
    """CTR改善のために title と description を最適化する（Phase 3）。

    本文内容は変更しない。改善対象は title と description のみ。

    Returns:
        {"title": "...", "description": "..."} or {} on error
    """
    query_bullets = "\n".join(f"- {q}" for q in top_queries[:5])
    ctr_hint = f"（現在 CTR: {gsc_ctr:.1%}）" if gsc_ctr is not None else ""

    prompt = f"""以下の技術記事の SEO タイトルと description を CTR 改善のために最適化してください。{ctr_hint}

## 現在のタイトル
{title}

## 現在の description
{description}

## ユーザーの実際の検索クエリ（Search Console より）
{query_bullets}

## 改善要件
- 検索クエリに含まれる語句をタイトルと description に反映する
- エラーコード・サービス名・具体的な症状を明示する
- タイトルは 60 文字以内
- description は 120 文字以内で「原因と解決策」が一目でわかるよう断言する
- 元の言語（日本語）を維持する

## 良いタイトルの例
- 「Terraform 403 Forbidden on S3 Bucket — 原因と解決策」
- 「Terraform Access Denied Error: IAM ポリシー修正ガイド」

## 悪いタイトルの例（禁止）
- 「Terraform エラーガイド」（内容不明）
- 「Terraform トラブルシューティング完全版」（曖昧）
- 「Terraform の問題を完全解決」（誇大）

以下の JSON 形式のみで回答してください（前置きや説明は不要）:
{{"title": "改善後のタイトル", "description": "改善後の description"}}"""

    try:
        message = claude_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            parsed = json.loads(m.group())
            # title / description のみを返す（不明フィールドは無視）
            result = {}
            if parsed.get("title"):
                result["title"] = str(parsed["title"])[:70]
            if parsed.get("description"):
                result["description"] = str(parsed["description"])[:160]
            return result
        return {}
    except Exception as e:
        print(f"    [seo_meta] 生成エラー（スキップ）: {e}")
        return {}


# ─── Step 3: Claude でセルフレビュー ─────────────────────

_REVIEW_SYSTEM = (
    "あなたは技術記事のQAレビュアーです。"
    "指定された記事Markdownを評価し、必ず RESULT: PASS または RESULT: FAIL で回答してください。"
    "コンテンツを変更・補完せず、判定と問題点の指摘のみを行うこと。"
)


def _utc_now_iso() -> str:
    from datetime import timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _record_review_error(article_path: str, error_msg: str, error_attempts: int) -> None:
    """Record review-agent errors to data/refresh_review_errors.json.

    error_attempts: how many review calls returned "review agent error" this run.
    count: cumulative occurrences across all runs (incremented each call).
    """
    try:
        history: dict = {}
        if REVIEW_ERROR_HISTORY_PATH.exists():
            try:
                history = json.loads(REVIEW_ERROR_HISTORY_PATH.read_text(encoding="utf-8"))
            except Exception:
                history = {}
        entry = history.get(article_path, {})
        history[article_path] = {
            "path": article_path,
            "last_error_at": _utc_now_iso(),
            "error": error_msg[:300],
            "error_attempts": error_attempts,
            "count": entry.get("count", 0) + 1,
        }
        REVIEW_ERROR_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        REVIEW_ERROR_HISTORY_PATH.write_text(
            json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except Exception as exc:
        print(f"    [review_error_record] WARNING: 書き込み失敗: {exc}")


def review_with_claude(
    claude_client: anthropic.Anthropic,
    title: str,
    body: str,
) -> tuple[bool, str]:
    """独立したレビューエージェントで生成コンテンツの品質を検証する。

    Returns:
        (passed, feedback_text)
    """
    prompt = f"""記事「{title}」のQAレビューを実施してください。

## チェック項目

### 1. セクション構成（5セクション必須）
以下のH2相当の見出しがすべて存在するか（表現の多少の違いは許容）:
- エラーの概要 / 概要
- 実際のエラーメッセージ例
- よくある原因と解決手順（H3の原因が最低1つ存在するか）
- ツール固有の注意点 / ツール固有の特性
- それでも解決しない場合 / 解決しない場合

### 2. Before/Afterコード対比
- `**Before（エラーが起きるコード）：**` と `**After（修正後）：**` が最低1組存在するか
- Beforeはエラー状態を示し、Afterはその修正として論理的に一致しているか
- コードブロックに言語名が指定されているか（例: ```python）
- 明らかな構文エラーや論理矛盾がないか

### 3. 免責事項フッター
末尾付近に「免責事項」テキストが存在するか

## 記事本文
{body}

## 回答フォーマット（必ずこの形式のみで回答）
問題がない場合:
RESULT: PASS

問題がある場合:
RESULT: FAIL
ISSUES:
- （具体的な問題点を箇条書き）"""

    try:
        message = claude_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=_REVIEW_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        response = message.content[0].text.strip()
        passed = response.startswith("RESULT: PASS")
        return passed, response
    except Exception as e:
        print(f"    レビューエージェントエラー: {e}")
        return False, f"RESULT: FAIL (review agent error: {e})"


# ─── メイン ───────────────────────────────────────────────

def main() -> None:
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    gemini_key    = os.getenv("GEMINI_API_KEY")

    if not anthropic_key:
        print("エラー: ANTHROPIC_API_KEY が設定されていません。")
        return
    if not gemini_key:
        print("エラー: GEMINI_API_KEY が設定されていません。")
        return

    claude_client = anthropic.Anthropic(api_key=anthropic_key)
    gemini_client = google_genai.Client(api_key=gemini_key)

    md_files = sorted(POSTS_DIR.glob("*.md"))
    if not md_files:
        print("記事がありません。")
        return

    # マニフェスト読み込み（他スクリプトの lastmod 更新に影響されない判定）
    manifest = _load_refresh_manifest()
    print(f"refresh_manifest: {len(manifest)} 件登録済み")

    # Phase 5: priority_score と search_queries を事前ロード
    priority_scores = _load_priority_scores()
    sq_map          = _load_search_queries_file()  # slug → top_queries list

    deleted_paths = _load_deleted_paths()

    # 更新対象を抽出（古い順 → priority_score で上書きソート）
    targets_raw: list[tuple[str, Path, str]] = []
    for md_path in md_files:
        rel = str(md_path.relative_to(BASE.parent).as_posix())
        if rel in deleted_paths:
            continue
        text = md_path.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if needs_refresh(fm, md_path.stem, REFRESH_DAYS, manifest):
            check_date = manifest.get(md_path.stem) or fm.get("date") or "不明"
            title_tmp  = fm.get("title", md_path.stem)
            targets_raw.append((check_date, md_path, title_tmp))

    # priority_score 降順 → 同スコア内は日付昇順（古い順）
    targets_raw.sort(
        key=lambda x: (-priority_scores.get(x[2], 0.0), x[0])
    )
    targets = [(t[0], t[1]) for t in targets_raw[:MAX_REFRESH]]

    print(f"更新対象: {len(targets)} 件（閾値: {REFRESH_DAYS}日）\n")
    if not targets:
        print("更新が必要な記事はありません。")
        return

    today       = date.today().isoformat()
    thin_titles = _load_thin_titles()
    top_queries = _load_top_queries()   # Phase 5: 実際の検索クエリ（単一, 後方互換）
    gsc_ctr_map = _load_gsc_ctr()      # Phase 2: CTR最適化
    if thin_titles:
        print(f"拡張対象フラグ (is_thin): {len(thin_titles)} 件\n")
    if top_queries:
        print(f"top_query 取得済み: {len(top_queries)} 件\n")
    if sq_map:
        print(f"search_queries.json: {len(sq_map)} slugs 読み込み済み\n")

    refreshed, skipped = [], []

    for last_date, md_path in targets:
        text     = md_path.read_text(encoding="utf-8")
        fm       = parse_frontmatter(text)
        title    = fm.get("title", md_path.stem)
        old_body = get_body(text)

        print(f"  処理中: {md_path.name}（最終更新: {last_date}）")

        # 競合コンテキストを取得（存在する場合のみ）
        competitor_ctx = _load_competitor_context(title)
        if competitor_ctx:
            print(f"    [competitor] 競合データをプロンプトに注入します")

        # Phase 5: 実際の検索クエリを取得（単一: 後方互換）
        top_query = top_queries.get(title, "")

        # Phase 2: search_queries.json から複数クエリを取得（slug 単位）
        slug_top_queries: list[str] = sq_map.get(md_path.stem, [])
        if not slug_top_queries and top_query:
            slug_top_queries = [top_query]  # フォールバック

        if slug_top_queries:
            print(f"    [top_queries] {slug_top_queries}")
        elif top_query:
            print(f"    [top_query] {top_query!r}")

        # Phase 2: CTRデータを取得
        gsc_data       = gsc_ctr_map.get(title, {})
        gsc_ctr        = gsc_data.get("ctr")
        gsc_impressions = gsc_data.get("impressions")
        if gsc_ctr is not None and gsc_ctr < 0.01 and (gsc_impressions or 0) > 100:
            print(f"    [ctr_opt] CTR={gsc_ctr:.1%} imp={gsc_impressions} → CTR最適化モード")

        # Step 1: Gemini でリサーチ
        print(f"    [1/3] Gemini がリサーチ中...")
        research = research_with_gemini(gemini_client, title, old_body, competitor_ctx)

        # Step 2: Claude でリライト
        print(f"    [2/3] Claude がリライト中...")
        try:
            new_body = rewrite_with_claude(
                claude_client, title, old_body, research,
                competitor_context=competitor_ctx,
                top_query=top_query,
                gsc_ctr=gsc_ctr,
                gsc_impressions=gsc_impressions,
                top_queries=slug_top_queries,
            )
        except Exception as e:
            print(f"    Claude エラー: {e}")
            skipped.append(md_path.name)
            continue

        new_body = normalize_before_after(new_body)

        # Step 3: セルフレビュー（最大 MAX_RETRIES 回リトライ）
        print(f"    [3/3] レビューエージェントが検証中...")
        passed, feedback = review_with_claude(claude_client, title, new_body)
        _review_error_count = 1 if "review agent error" in feedback else 0

        if not passed:
            for retry in range(1, MAX_RETRIES + 1):
                print(f"    [3/3] FAIL → リトライ {retry}/{MAX_RETRIES}")
                try:
                    new_body = rewrite_with_claude(
                        claude_client, title, old_body, research, feedback,
                        competitor_context=competitor_ctx,
                        top_query=top_query,
                        gsc_ctr=gsc_ctr,
                        gsc_impressions=gsc_impressions,
                        top_queries=slug_top_queries,
                    )
                except Exception as e:
                    print(f"    リトライ中の Claude エラー: {e}")
                    break
                new_body = normalize_before_after(new_body)
                passed, feedback = review_with_claude(claude_client, title, new_body)
                if "review agent error" in feedback:
                    _review_error_count += 1
                if passed:
                    break

        if not passed:
            print(f"    [3/3] FAIL（リトライ上限到達）— スキップ")
            print(f"    フィードバック: {feedback[:300]}")
            if "review agent error" in feedback:
                rel_path = str(md_path.relative_to(BASE.parent).as_posix())
                _record_review_error(rel_path, feedback, _review_error_count)
            skipped.append(md_path.name)
            continue

        print(f"    [3/3] PASS — 保存")

        # 薄い記事の拡張（is_thin フラグ または 文字数チェック）
        needs_expand = title in thin_titles or _body_char_count(new_body) < THIN_CHAR_THRESHOLD
        if needs_expand:
            em   = re.match(r'^(.+?) の (\d+) エラー', title)
            tool = em.group(1) if em else fm.get("tags", md_path.stem)
            code = em.group(2) if em else fm.get("errorCode", "")
            print(f"    [expand] 薄い記事を拡張中（{_body_char_count(new_body)}文字 → 目標1500文字以上）...")
            try:
                expanded = _expand_thin(claude_client, title, tool, code, new_body)
                expanded = normalize_before_after(expanded)
                new_body = expanded
                print(f"    [expand] 完了: {_body_char_count(new_body)}文字")
            except Exception as e:
                print(f"    [expand] 拡張エラー（リライト結果で保存）: {e}")

        # lastmod を更新して保存（refresh_due フラグも除去）
        fm_block = get_frontmatter_block(text)
        if "lastmod:" in fm_block:
            new_fm = re.sub(r"lastmod:.*", f"lastmod: {today}", fm_block)
        else:
            new_fm = re.sub(r"\n---\n$", f"\nlastmod: {today}\n---\n", fm_block)
        new_fm = re.sub(r"(?m)^refresh_due:.*\n", "", new_fm)

        # Phase 3: top_queries がある場合は title / description を SEO 最適化
        new_title       = title
        old_description = fm.get("description", "")
        new_description = old_description
        if slug_top_queries:
            print(f"    [seo_meta] title/description 最適化中...")
            seo = generate_seo_metadata(
                claude_client, title, old_description,
                slug_top_queries, gsc_ctr,
            )
            if seo.get("title") and seo["title"] != title:
                new_title = seo["title"]
                new_fm = re.sub(r'(?m)^title:.*', f'title: "{new_title}"', new_fm)
                print(f"    [seo_meta] title: {title!r} → {new_title!r}")
            if seo.get("description") and seo["description"] != old_description:
                new_description = seo["description"]
                new_fm = re.sub(r'(?m)^description:.*', f'description: "{new_description}"', new_fm)
                print(f"    [seo_meta] description 更新")

        md_path.write_text(new_fm + "\n" + new_body, encoding="utf-8")
        manifest[md_path.stem] = today  # マニフェストに今日の日付を記録

        # Phase 4: rewrite_report.json に before/after を記録
        _save_rewrite_report({
            "slug":               md_path.stem,
            "rewrite_date":       today,
            "old_title":          title,
            "new_title":          new_title,
            "old_description":    old_description,
            "new_description":    new_description,
            "before_ctr":         gsc_data.get("ctr", 0.0),
            "before_position":    gsc_data.get("position", 0.0),
            "before_impressions": gsc_data.get("impressions", 0),
            "top_queries":        slug_top_queries,
        })

        print(f"    完了: {new_title if new_title != title else title}")
        refreshed.append(md_path.name)

    _save_refresh_manifest(manifest)
    print(f"\n完了: 更新 {len(refreshed)} 件 / スキップ {len(skipped)} 件")
    if skipped:
        print(f"スキップ: {', '.join(skipped)}")


if __name__ == "__main__":
    main()
