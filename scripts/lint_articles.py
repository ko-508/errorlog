#!/usr/bin/env python3
"""lint_articles.py — 決定論的ルールによる記事品質スキャナ。

LLM/API・外部ツール不使用。Python 標準ライブラリのみ。
検出のみ行い、記事ファイルは変更しない。

使用例:
  python scripts/lint_articles.py              # 全件スキャン
  python scripts/lint_articles.py --path content/posts/docker_404.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent.parent
POSTS_DIR = BASE / "content" / "posts"
LINT_REPORT_PATH = BASE / "data" / "lint_report.json"
LINT_SUMMARY_DIR = BASE / "reports" / "lint"
LINT_SUMMARY_PATH = LINT_SUMMARY_DIR / "lint_summary.md"

# ── 必須セクション正規表現 ────────────────────────────────────────────────────
# 各パターンは re.IGNORECASE なし（日本語）。H2/H3 どちらでも許容（^#{1,4}\s*）。
REQUIRED_SECTIONS: list[tuple[str, re.Pattern[str]]] = [
    # 1. エラーの概要
    ("エラーの概要", re.compile(r"^#{1,4}\s*エラーの概要", re.MULTILINE)),
    # 2. エラーメッセージ例（「実際の」有無を吸収）
    ("エラーメッセージ例", re.compile(r"^#{1,4}\s*(?:実際の)?エラーメッセージ例", re.MULTILINE)),
    # 3. 原因と解決手順（「よくある」有無を吸収）
    ("原因と解決手順", re.compile(r"^#{1,4}\s*(?:よくある)?原因と解決手順", re.MULTILINE)),
    # 4. 注意点（「ツール/サービス固有の」等、任意のプレフィックスを吸収）
    ("注意点", re.compile(r"^#{1,4}\s*[^#\n]*注意点", re.MULTILINE)),
    # 5. それでも解決しない場合
    ("それでも解決しない場合", re.compile(r"^#{1,4}\s*それでも解決しない場合", re.MULTILINE)),
]

# 判定に使うセクションの順序インデックス（A2チェック用）
SECTION_ORDER = [label for label, _ in REQUIRED_SECTIONS]

# ── B1 エラーパターン辞書 ─────────────────────────────────────────────────────
# 各エントリは (カテゴリ名, pattern)。追加しやすいよう定数リスト化。
ERROR_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("http_status",    re.compile(r"\b[45]\d{2}\b")),
    ("exception_name", re.compile(r"\w+(?:Error|Exception)\b")),
    ("exit_code",      re.compile(r"exit\s+code\s+\d+|\bexit\s+\d+\b", re.IGNORECASE)),
    ("errno",          re.compile(r"\berrno\b", re.IGNORECASE)),
    ("posix_errno",    re.compile(r"\bE[A-Z]{2,}\b")),   # EACCES, ENOENT 等
    ("signal",         re.compile(r"\bSIG[A-Z]+\b")),
    # 自然言語エラーメッセージ（例: "Error response from daemon: ..."）
    ("error_word",     re.compile(r"\bError[:\s]", re.IGNORECASE)),
    ("failed_word",    re.compile(r"\bFailed\b", re.IGNORECASE)),
    ("denied_word",    re.compile(r"\bdenied\b", re.IGNORECASE)),
    ("not_found",      re.compile(r"\bnot\s+found\b", re.IGNORECASE)),
    ("unauthorized",   re.compile(r"\bunauthorized\b", re.IGNORECASE)),
    # JSON エラーレスポンスフィールド（GitHub/OpenAI/Stripe/AWS 等、大文字小文字不問）
    ("json_code",      re.compile(r'"[Cc]ode"\s*:')),
    ("json_error",     re.compile(r'"[Ee]rror"\s*:')),
    ("json_message",   re.compile(r'"[Mm]essage"\s*:')),
    # 日本語エラー表現
    ("jp_error",       re.compile(r'(?:エラー|失敗)(?:が|は|：|:)')),
]

# ── B2 不適格マーカー表現 ─────────────────────────────────────────────────────
# 由来: RSS 取り込み記事で「エラーがないのに記事化した」際に確認された表現。
# 正規表現は今後追加する前提で定数リスト化。
B2_DISQUALIFIER_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # 「直接的なエラー（コード|メッセージ）を扱うわけではない」系
    (
        "error_not_directly_handled",
        re.compile(
            r"直接的?な?(?:HTTP)?エラー(?:コード|メッセージ)?(?:を)?(?:直接)?扱(?:う|っている)?わけではありませ(?:ん|んが)",
        ),
    ),
    # 「エラーとして捉えることができ」系
    (
        "soft_error_framing",
        re.compile(r"エラーとして捉えることができ(?:る|ます)"),
    ),
    # 「特定の（HTTP）エラーコードを直接」系
    (
        "no_specific_error_code",
        re.compile(r"特定の(?:HTTP)?エラーコードを直接"),
    ),
    # 「HTTPステータスコードに直結するものではなく」系
    (
        "not_http_status_related",
        re.compile(r"HTTP(?:ステータス)?コードに直結するものではなく"),
    ),
    # 「直接的なエラーメッセージとして現れること」— RSS記事の典型フレーズ
    (
        "indirect_error_message",
        re.compile(r"直接的なエラーメッセージとして現れること"),
    ),
]

# ── D1 URL ドメイン分類 ───────────────────────────────────────────────────────
_OFFICIAL_DOMAINS = frozenset({
    "docs.docker.com", "docs.github.com", "docs.gitlab.com",
    "docs.aws.amazon.com", "aws.amazon.com",
    "cloud.google.com", "firebase.google.com",
    "learn.microsoft.com", "docs.microsoft.com", "azure.microsoft.com",
    "kubernetes.io", "helm.sh",
    "docs.ansible.com",
    "nginx.org", "nginx.com",
    "docs.python.org", "devdocs.io",
    "developer.mozilla.org",
    "vercel.com", "docs.vercel.com",
    "supabase.com", "docs.supabase.com",
    "stripe.com", "docs.stripe.com",
    "openai.com", "platform.openai.com",
    "developers.google.com",
    "registry.terraform.io", "developer.hashicorp.com",
})
_OFFICIAL_PREFIXES = ("docs.", "developer.", "developers.", "dev.", "learn.")
_SEMI_OFFICIAL = frozenset({
    "ietf.org", "w3.org", "rfc-editor.org", "whatwg.org",
})
_COMMUNITY = frozenset({
    "stackoverflow.com", "superuser.com", "serverfault.com",
    "github.com", "gitlab.com", "reddit.com",
})
_PERSONAL = frozenset({
    "qiita.com", "zenn.dev", "dev.to",
    "note.com", "medium.com",
})
_PERSONAL_SUFFIXES = (".hatenablog.com", ".hatenablog.jp", ".hatena.ne.jp")
_GROUNDING_REDIRECT_DOMAINS = frozenset({
    "vertexaisearch.cloud.google.com",
})
_GROUNDING_REDIRECT_PREFIXES = ("vertexaisearch.",)


def classify_domain(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
        host = host.lower().lstrip("www.")
    except Exception:
        return "other"
    if any(host.startswith(p) for p in _GROUNDING_REDIRECT_PREFIXES) or host in _GROUNDING_REDIRECT_DOMAINS:
        return "grounding_redirect"
    if host in _OFFICIAL_DOMAINS or any(host.startswith(p) for p in _OFFICIAL_PREFIXES):
        return "official"
    if host in _SEMI_OFFICIAL:
        return "semi_official"
    if host in _COMMUNITY:
        return "community"
    if host in _PERSONAL or any(host.endswith(s) for s in _PERSONAL_SUFFIXES):
        return "personal"
    return "other"


# ── ユーティリティ ────────────────────────────────────────────────────────────

def split_frontmatter(content: str) -> tuple[dict[str, str], str]:
    if not content.startswith("---"):
        return {}, content
    end = content.find("\n---\n", 3)
    if end == -1:
        return {}, content
    raw = content[4:end]
    body = content[end + 5:]
    fm: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        fm[key.strip()] = val.strip().strip('"').strip("'")
    return fm, body


def body_char_count(body: str) -> int:
    """本文の実質文字数（コードブロック・URL・MD記号を除外）。expand_articles.py と同ロジック。"""
    text = re.sub(r"```[\s\S]*?```", "", body)                   # フェンスドコードブロック除去
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)         # リンク→テキストのみ
    text = re.sub(r"https?://\S+", "", text)                      # 裸URL除去
    text = re.sub(r"[#\-*`>\[\]()!]", "", text)                   # MD記号除去
    return len(text.replace(" ", "").replace("\n", ""))


def extract_urls(text: str) -> list[str]:
    """テキスト中のすべての URL を返す（Markdown リンク含む）。"""
    # [text](url) 形式
    md_urls = re.findall(r"\]\((\S+?)\)", text)
    # 裸URL
    bare_urls = re.findall(r"https?://\S+", text)
    return md_urls + bare_urls


def extract_fenced_code_blocks(text: str) -> list[tuple[str, str]]:
    """(language, code_body) のリストを返す。language は空文字列の場合もある。"""
    results = []
    for m in re.finditer(r"```([^\n]*)\n([\s\S]*?)```", text):
        lang = m.group(1).strip()
        code = m.group(2)
        results.append((lang, code))
    return results


def get_section_content(body: str, section_pattern: re.Pattern[str]) -> str | None:
    """セクション見出しにマッチする最初のセクションの本文を返す（次の同レベル見出しまで）。"""
    m = section_pattern.search(body)
    if not m:
        return None
    start = m.end()
    # 同レベル（同じ # 数）の次の見出しまで
    heading_text = m.group(0).lstrip()
    level = len(heading_text) - len(heading_text.lstrip("#"))
    next_heading = re.compile(r"^#{1," + str(level) + r"}\s", re.MULTILINE)
    nm = next_heading.search(body, start)
    end = nm.start() if nm else len(body)
    return body[start:end]


# ── ルールチェック関数 ────────────────────────────────────────────────────────

Issue = tuple[str, str]  # (rule_id, detail)


def check_a1(body: str) -> list[Issue]:
    """A1 [FAIL] 必須5セクションの見出しが全て存在する。"""
    issues: list[Issue] = []
    for label, pattern in REQUIRED_SECTIONS:
        if not pattern.search(body):
            issues.append(("A1", f"必須セクション欠落: {label}"))
    return issues


def check_a2(body: str) -> list[Issue]:
    """A2 [WARN] 必須セクションが規定順に並んでいる。"""
    positions: list[tuple[int, str]] = []
    for label, pattern in REQUIRED_SECTIONS:
        m = pattern.search(body)
        if m:
            positions.append((m.start(), label))
    positions.sort()
    actual_order = [label for _, label in positions]
    expected_order = [label for label in SECTION_ORDER if label in actual_order]
    if actual_order != expected_order:
        return [("A2", f"セクション順序違反: {actual_order} (期待: {expected_order})")]
    return []


def check_a3(body: str) -> list[Issue]:
    """A3 [FAIL] 日本語本文が1,500字以上（コード・URL・MD記号を除外）。"""
    count = body_char_count(body)
    if count < 1500:
        return [("A3", f"本文が{count}字（基準: 1,500字以上）")]
    return []


def check_a4(body: str) -> list[Issue]:
    """A4 [WARN] 全フェンスドコードブロックに言語名が指定されている。"""
    blocks = extract_fenced_code_blocks(body)
    unnamed = sum(1 for lang, _ in blocks if not lang)
    if unnamed:
        return [("A4", f"言語名なしのコードブロックが{unnamed}件")]
    return []


def check_a5(body: str) -> list[Issue]:
    """A5 [WARN] プレースホルダーが <your-xxx> 形式（大文字・山括弧なし形式を警告）。"""
    issues: list[Issue] = []
    # YOUR_ 大文字形式
    upper = re.findall(r"\bYOUR_[A-Z_]+\b", body)
    if upper:
        issues.append(("A5", f"プレースホルダーが大文字形式: {upper[:3]}"))
    # <XXX> ではなく {{XXX}} や PLACEHOLDER など（山括弧なし系）
    placeholder_no_bracket = re.findall(r"\{\{[^}]+\}\}", body)
    if placeholder_no_bracket:
        issues.append(("A5", f"プレースホルダーが {{{{ }}}} 形式: {placeholder_no_bracket[:3]}"))
    return issues


def check_a6(fm: dict[str, str], body: str) -> list[Issue]:
    """A6 [FAIL] フロントマター必須フィールド（errorCode・tags・title）と description 重複チェック。"""
    issues: list[Issue] = []
    for field in ("errorCode", "tags", "title"):
        val = fm.get(field, "").strip()
        if not val or val in ("[]", '""', "''"):
            issues.append(("A6", f"フロントマター必須フィールド欠落または空: {field}"))
    desc = fm.get("description", "")
    if "。。" in desc:
        issues.append(("A6", 'description に「。。」重複'))
    return issues


def check_b1(body: str) -> list[Issue]:
    """B1 [FAIL] エラーメッセージ例セクションのコードブロックに実在エラーパターンが1件以上。"""
    section_pat = re.compile(r"^#{1,4}\s*(?:実際の)?エラーメッセージ例", re.MULTILINE)
    section_body = get_section_content(body, section_pat)
    if section_body is None:
        # A1 で既に検出されるので B1 はスキップ
        return []
    blocks = extract_fenced_code_blocks(section_body)
    if not blocks:
        return [("B1", "エラーメッセージ例セクションにコードブロックなし")]
    for _, code in blocks:
        for _cat, pat in ERROR_PATTERNS:
            if pat.search(code):
                return []  # 1件でもマッチすれば OK
    return [("B1", "エラーメッセージ例のコードブロックに実在エラーパターンなし")]


def check_b2(body: str) -> list[Issue]:
    """B2 [FAIL] 不適格マーカー表現を本文で検出。"""
    issues: list[Issue] = []
    for label, pat in B2_DISQUALIFIER_PATTERNS:
        m = pat.search(body)
        if m:
            excerpt = m.group(0)[:60]
            issues.append(("B2", f"不適格マーカー({label}): 「{excerpt}」"))
    return issues


def check_b3(body: str) -> list[Issue]:
    """B3 [WARN] 解決手順セクションにコードブロックが2件以上（Before/After 近似）。"""
    section_pat = re.compile(r"^#{1,4}\s*(?:よくある)?原因と解決手順", re.MULTILINE)
    section_body = get_section_content(body, section_pat)
    if section_body is None:
        return []
    blocks = extract_fenced_code_blocks(section_body)
    if len(blocks) < 2:
        return [("B3", f"解決手順内のコードブロックが{len(blocks)}件（Before/After 推奨: 2件以上）")]
    return []


def check_d1_d2(body: str) -> tuple[dict[str, int], list[Issue]]:
    """D1 [INFO] URL ドメイン分類、D2 [WARN] grounding_redirect > 50% なら警告。"""
    urls = extract_urls(body)
    tiers: Counter[str] = Counter(classify_domain(u) for u in urls)
    tier_dict = dict(tiers)
    issues: list[Issue] = []
    total = sum(tiers.values())
    if total > 0:
        gr = tiers.get("grounding_redirect", 0)
        if gr / total > 0.5:
            issues.append(("D2", f"grounding_redirect が全URLの{gr}/{total}件（50%超）"))
    return tier_dict, issues


# ── 記事 1 件をスキャン ───────────────────────────────────────────────────────

def lint_article(path: Path) -> dict[str, Any]:
    try:
        rel = str(path.relative_to(BASE).as_posix())
    except ValueError:
        rel = str(path.as_posix())
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as exc:
        return {"path": rel, "fails": [{"rule": "SYS", "detail": str(exc)}], "warns": [], "infos": [], "source_tiers": {}}

    fm, body = split_frontmatter(content)
    fails: list[dict] = []
    warns: list[dict] = []
    infos: list[dict] = []

    def _add(severity: str, issues: list[Issue]) -> None:
        for rule, detail in issues:
            entry = {"rule": rule, "detail": detail}
            if severity == "FAIL":
                fails.append(entry)
            elif severity == "WARN":
                warns.append(entry)
            else:
                infos.append(entry)

    _add("FAIL", check_a1(body))
    _add("WARN", check_a2(body))
    _add("FAIL", check_a3(body))
    _add("WARN", check_a4(body))
    _add("WARN", check_a5(body))
    _add("FAIL", check_a6(fm, body))
    _add("FAIL", check_b1(body))
    _add("FAIL", check_b2(body))
    _add("WARN", check_b3(body))

    tier_dict, d_issues = check_d1_d2(body)
    _add("WARN", d_issues)
    if tier_dict:
        infos.append({"rule": "D1", "detail": "URL domain tiers", "source_tiers": tier_dict})

    return {"path": rel, "fails": fails, "warns": warns, "infos": infos, "source_tiers": tier_dict}


# ── レポート出力 ──────────────────────────────────────────────────────────────

def write_json_report(results: list[dict]) -> None:
    LINT_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    LINT_REPORT_PATH.write_text(
        json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "articles": results},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_summary(results: list[dict]) -> None:
    LINT_SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    total = len(results)
    fail_arts = [r for r in results if r["fails"]]
    warn_arts = [r for r in results if r["warns"] and not r["fails"]]
    clean_arts = [r for r in results if not r["fails"] and not r["warns"]]

    rule_fails: Counter[str] = Counter()
    rule_warns: Counter[str] = Counter()
    for r in results:
        for f in r["fails"]:
            rule_fails[f["rule"]] += 1
        for w in r["warns"]:
            rule_warns[w["rule"]] += 1

    b1b2_fails = [
        r for r in results
        if any(f["rule"] in ("B1", "B2") for f in r["fails"])
    ]

    lines: list[str] = [
        "# Lint Summary",
        f"\n生成日時: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')}",
        f"\n## 総括",
        f"| 区分 | 件数 |",
        f"|------|------|",
        f"| 総記事数 | {total} |",
        f"| FAIL あり | {len(fail_arts)} |",
        f"| WARN のみ | {len(warn_arts)} |",
        f"| クリーン | {len(clean_arts)} |",
        "",
        "## ルール別違反件数",
        "",
        "### FAIL",
        "| ルール | 件数 |",
        "|--------|------|",
    ]
    for rule, cnt in rule_fails.most_common():
        lines.append(f"| {rule} | {cnt} |")
    lines += [
        "",
        "### WARN",
        "| ルール | 件数 |",
        "|--------|------|",
    ]
    for rule, cnt in rule_warns.most_common():
        lines.append(f"| {rule} | {cnt} |")

    lines += ["", "## B1/B2 FAIL — エラー実在性なし疑い記事", ""]
    if b1b2_fails:
        lines.append("| 記事 | ルール |")
        lines.append("|------|--------|")
        for r in b1b2_fails:
            rules = ", ".join(sorted({f["rule"] for f in r["fails"] if f["rule"] in ("B1", "B2")}))
            lines.append(f"| {r['path']} | {rules} |")
    else:
        lines.append("なし")

    lines += ["", "## FAIL 記事一覧（全ルール）", ""]
    if fail_arts:
        lines.append("| 記事 | FAIL ルール |")
        lines.append("|------|------------|")
        for r in fail_arts:
            rules = ", ".join(sorted({f["rule"] for f in r["fails"]}))
            lines.append(f"| {r['path']} | {rules} |")
    else:
        lines.append("なし（全記事クリーン）")

    LINT_SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── エントリポイント ──────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="記事品質 Lint スキャナ")
    parser.add_argument("--path", help="単一記事の相対/絶対パス。省略時は全件スキャン。")
    args = parser.parse_args()

    if args.path:
        p = Path(args.path)
        if not p.is_absolute():
            p = BASE / p
        paths = [p]
    else:
        paths = sorted(POSTS_DIR.glob("*.md"))

    print(f"[lint] スキャン: {len(paths)} 記事", file=sys.stderr)
    results = [lint_article(p) for p in paths]

    fail_count = sum(1 for r in results if r["fails"])
    print(f"[lint] FAIL: {fail_count} / {len(results)}", file=sys.stderr)

    write_json_report(results)
    write_summary(results)
    print(f"[lint] → {LINT_REPORT_PATH}", file=sys.stderr)
    print(f"[lint] → {LINT_SUMMARY_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
