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
    # Docker コンテナ終了コード（スペイン語等の非英語記事対応）
    ("exited_code",    re.compile(r"Exited\s*\(\d+\)")),
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


# ── 記事カテゴリ判定 ─────────────────────────────────────────────────────────
# エラー記事: errorCode が FM にある、またはファイル名に 3桁以上の数字コードを含む
_NUMERIC_CODE_IN_STEM = re.compile(r"_\d{3}(?:[^0-9]|$)")

ARTICLE_CATEGORY_ERROR = "error_article"
ARTICLE_CATEGORY_NON_ERROR = "non_error_article"


def classify_article(path: Path, fm: dict[str, str]) -> str:
    """エラー記事か規格外ページかを判定する。"""
    if fm.get("errorCode", "").strip():
        return ARTICLE_CATEGORY_ERROR
    if _NUMERIC_CODE_IN_STEM.search(path.stem):
        return ARTICLE_CATEGORY_ERROR
    return ARTICLE_CATEGORY_NON_ERROR


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


def _mask_code_blocks(text: str) -> str:
    """見出し検索用にフェンスドコードブロックの内部を無害化する。

    コードブロック内の各文字（改行を除く）を 'x' に置換し、文字数・改行位置を
    元の文字列と完全に一致させる。これにより置換後の文字列上で求めたオフセットを
    そのまま元の文字列のスライスに使える。コードブロック内の `# コメント` 等が
    Markdown 見出しと誤認されることを防ぐ。
    """
    def _mask(m: re.Match[str]) -> str:
        return "".join("\n" if ch == "\n" else "x" for ch in m.group(0))
    return re.sub(r"```[\s\S]*?```", _mask, text)


def get_section_content(body: str, section_pattern: re.Pattern[str]) -> str | None:
    """セクション見出しにマッチする最初のセクションの本文を返す（次の同レベル見出しまで）。

    見出し検索はコードブロック内部を無害化したテキスト上で行うため、コードブロック内の
    `# コメント` 等を見出しと誤認しない。返すセクション本文は元のコードブロックを
    含む内容（マスクされていない元の body のスライス）。
    """
    masked = _mask_code_blocks(body)
    m = section_pattern.search(masked)
    if not m:
        return None
    start = m.end()
    # 同レベル（同じ # 数）の次の見出しまで
    heading_text = m.group(0).lstrip()
    level = len(heading_text) - len(heading_text.lstrip("#"))
    next_heading = re.compile(r"^#{1," + str(level) + r"}\s", re.MULTILINE)
    nm = next_heading.search(masked, start)
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


def check_a6(fm: dict[str, str], body: str, require_error_code: bool = True) -> list[Issue]:
    """A6 [FAIL] フロントマター必須フィールド（errorCode・tags・title）と description 重複チェック。"""
    issues: list[Issue] = []
    fields = ("errorCode", "tags", "title") if require_error_code else ("tags", "title")
    for field in fields:
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


# ── C1 認証トークン・APIキー検出 ──────────────────────────────────────────────
# コードブロック内のみ対象。<your-xxx> 形式のプレースホルダーは除外する。

_PLACEHOLDER_WORDS = frozenset({
    # 明示的プレースホルダー語
    "your", "xxx", "xxxx", "here", "placeholder", "example", "dummy",
    "sample", "redacted",
    # トークン構成要素として使われる一般的な語（全て小文字で比較）
    "api", "key", "bot", "token", "user", "secret", "auth", "access",
    "admin", "app", "client", "server", "test", "prod", "dev", "old",
    "new", "expired", "invalid", "bad", "good", "jwt", "bearer",
    "oauth", "pass", "password", "value", "string", "name", "id",
    "type", "scope", "role", "slug", "mytoken", "mykey", "myapp",
})

# (ルールID, 表示名, プレフィックス正規表現, サフィックス最小長)
_TOKEN_PREFIX_PATTERNS: list[tuple[str, str, re.Pattern[str], int]] = [
    ("C1:slack_bot",      "Slack Bot Token (xoxb-)",          re.compile(r'xoxb-'),          8),
    ("C1:slack_user",     "Slack User Token (xoxp-)",         re.compile(r'xoxp-'),          8),
    ("C1:slack_app",      "Slack App Token (xapp-)",          re.compile(r'xapp-'),          8),
    ("C1:openai_proj",    "OpenAI API Key (sk-proj-)",        re.compile(r'sk-proj-'),      20),
    ("C1:openai",         "OpenAI API Key (sk-)",             re.compile(r'sk-(?!proj-)'),  30),
    ("C1:stripe_sk_live", "Stripe Secret Key (sk_live_)",     re.compile(r'sk_live_'),      10),
    ("C1:stripe_pk_live", "Stripe Publishable Key (pk_live_)", re.compile(r'pk_live_'),     10),
    ("C1:stripe_rk_live", "Stripe Restricted Key (rk_live_)", re.compile(r'rk_live_'),     10),
    ("C1:stripe_sk_test", "Stripe Test Secret Key",           re.compile(r'sk_test_'),      10),
    ("C1:stripe_pk_test", "Stripe Test Publishable Key",      re.compile(r'pk_test_'),      10),
    ("C1:aws_access",     "AWS Access Key (AKIA)",            re.compile(r'AKIA'),          16),
    ("C1:github_token",   "GitHub PAT (ghp_)",                re.compile(r'ghp_'),          10),
    ("C1:github_pat",     "GitHub Fine-grained PAT",          re.compile(r'github_pat_'),   10),
    ("C1:gitlab",         "GitLab PAT (glpat-)",              re.compile(r'glpat-'),        10),
]


def _is_placeholder_suffix(suffix: str, min_len: int) -> bool:
    """サフィックスが明らかなプレースホルダーなら True（検出しない）。

    判定優先順位:
      (1) <で始まる（xoxb-<your-token>）→ プレースホルダー
      (2) 長さ不足（min_len未満）→ プレースホルダー
      (3) 全セグメントが既知のプレースホルダー語 → プレースホルダー
      (4) それ以外 → 実トークン風（検出する）
    """
    if suffix.startswith("<"):
        return True
    m = re.match(r'[A-Za-z0-9_\-]+', suffix)
    if not m:
        return True
    token_part = m.group(0)
    if len(token_part) < min_len:
        return True
    segments = [s for s in re.split(r'[-_]', token_part) if s]
    for seg in segments:
        seg_lower = seg.lower()
        if re.fullmatch(r'x+', seg_lower) and len(seg_lower) >= 3:
            continue
        if seg_lower in _PLACEHOLDER_WORDS:
            continue
        if len(seg) <= 3:
            continue
        return False  # 実値の可能性あり
    return True


def check_secret_token(body: str) -> list[Issue]:
    """C1 [FAIL] コードブロック内の実トークン風の認証トークン・APIキーを検出する。"""
    code_blocks = extract_fenced_code_blocks(body)
    if not code_blocks:
        return []
    code_content = "\n".join(code for _, code in code_blocks)

    issues: list[Issue] = []
    seen_labels: set[str] = set()

    for rule_id, display_name, prefix_pat, min_len in _TOKEN_PREFIX_PATTERNS:
        if rule_id in seen_labels:
            continue
        for m in prefix_pat.finditer(code_content):
            suffix = code_content[m.end():]
            if not _is_placeholder_suffix(suffix, min_len):
                seen_labels.add(rule_id)
                issues.append(("C1", f"実トークン風の値: {display_name}"))
                break
    return issues


# ── C1 AWSシークレットアクセスキー検出（文脈限定）────────────────────────────
# コードブロック内のみ対象。AWS関連の変数名の直後に来る35〜45文字の形式を検出する。
# 明確なプレフィックスがないため、変数名コンテキストを必須とすることで誤検知を抑制する。

_AWS_SECRET_CONTEXT_RE = re.compile(
    r'(?:aws_secret_access_key|aws_secret_key|secret_access_key'
    r'|secretAccessKey|SecretAccessKey|AWS_SECRET_ACCESS_KEY|secret_key)'
    r'\s*(?:[=:]+|=>)\s*["\']?'       # 代入演算子・区切り・任意のクォート
    r'([A-Za-z0-9/+]{35,45})'         # キー本体: 35〜45文字の英数字+/+
    r'(?![A-Za-z0-9/+])',              # 末尾直後が非base64文字（長い文字列を除外）
    re.IGNORECASE,
)


def _is_aws_secret_placeholder(value: str) -> bool:
    """AWSシークレット候補値がプレースホルダーなら True（検出しない）。"""
    v_lower = value.lower()
    # 山かっこ形式（通常はregexが捕捉しないが念のため）
    if value.startswith("<"):
        return True
    # 先頭がプレースホルダー語
    if v_lower.startswith(("your", "placeholder", "example", "dummy", "sample", "redacted")):
        return True
    # 単一文字の繰り返し（例: xxxx...）
    if len(set(v_lower.replace("/", "").replace("+", ""))) <= 2:
        return True
    return False


def check_aws_secret_key(body: str) -> list[Issue]:
    """C1 [FAIL] コードブロック内のAWSシークレットアクセスキー形式を文脈限定で検出する。"""
    code_blocks = extract_fenced_code_blocks(body)
    if not code_blocks:
        return []
    code_content = "\n".join(code for _, code in code_blocks)

    for m in _AWS_SECRET_CONTEXT_RE.finditer(code_content):
        value = m.group(1)
        if _is_aws_secret_placeholder(value):
            continue
        return [("C1", f"実トークン風の値: AWS Secret Access Key ({value[:12]}...)")]
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
        return {"path": rel, "category": ARTICLE_CATEGORY_ERROR, "fails": [{"rule": "SYS", "detail": str(exc)}], "warns": [], "infos": [], "source_tiers": {}}

    fm, body = split_frontmatter(content)
    category = classify_article(path, fm)
    is_error = category == ARTICLE_CATEGORY_ERROR

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

    if is_error:
        # A1/A2/A3/B1/B3: エラー記事にのみ適用
        # A3（1500字基準）はエラー解決記事の5セクション規格から導かれるため error_article 限定。
        # tool-guide 記事（non_error_article）は除外。glossary が別ディレクトリで除外されているのと同じ一貫性。
        # tool-guide 記事への適用を再開する場合はこのブロックから A3 を外へ移す。
        _add("FAIL", check_a1(body))
        _add("WARN", check_a2(body))
        _add("FAIL", check_a3(body))
        _add("FAIL", check_b1(body))
        _add("WARN", check_b3(body))

    # A4/A5/A6/B2/C1/D: 全記事に適用
    _add("WARN", check_a4(body))
    _add("WARN", check_a5(body))
    _add("FAIL", check_a6(fm, body, require_error_code=is_error))
    _add("FAIL", check_b2(body))
    _add("FAIL", check_secret_token(body))
    _add("FAIL", check_aws_secret_key(body))

    tier_dict, d_issues = check_d1_d2(body)
    _add("WARN", d_issues)
    if tier_dict:
        infos.append({"rule": "D1", "detail": "URL domain tiers", "source_tiers": tier_dict})

    return {"path": rel, "category": category, "fails": fails, "warns": warns, "infos": infos, "source_tiers": tier_dict}


# ── レポート出力 ──────────────────────────────────────────────────────────────

def write_json_report(results: list[dict]) -> None:
    LINT_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    LINT_REPORT_PATH.write_text(
        json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "articles": results},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _classify_result(r: dict) -> str:
    """lint_article の結果を最終分類に振り分ける。"""
    if r.get("category") == ARTICLE_CATEGORY_NON_ERROR:
        return "skipped"
    fail_rules = {f["rule"] for f in r["fails"]}
    if "B2" in fail_rules:
        return "ineligible"
    if fail_rules:
        return "needs_rewrite"
    return "clean"


def write_summary(results: list[dict]) -> None:
    LINT_SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    total = len(results)

    # スコープ分離後の集計（skipped 記事は FAIL/WARN カウントから除外）
    error_arts = [r for r in results if r.get("category") == ARTICLE_CATEGORY_ERROR]
    skipped_arts = [r for r in results if r.get("category") == ARTICLE_CATEGORY_NON_ERROR]

    fail_arts = [r for r in error_arts if r["fails"]]
    warn_arts = [r for r in error_arts if r["warns"] and not r["fails"]]
    clean_arts = [r for r in error_arts if not r["fails"] and not r["warns"]]

    rule_fails: Counter[str] = Counter()
    rule_warns: Counter[str] = Counter()
    for r in error_arts:
        for f in r["fails"]:
            rule_fails[f["rule"]] += 1
        for w in r["warns"]:
            rule_warns[w["rule"]] += 1

    b2_arts = [r for r in error_arts if any(f["rule"] == "B2" for f in r["fails"])]

    # 最終分類
    classified: dict[str, list[dict]] = {"clean": [], "needs_rewrite": [], "ineligible": [], "skipped": []}
    for r in results:
        classified[_classify_result(r)].append(r)

    lines: list[str] = [
        "# Lint Summary",
        f"\n生成日時: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')}",
        "",
        "## 最終分類（エラー記事スコープ）",
        "",
        "| 分類 | 件数 | 説明 |",
        "|------|------|------|",
        f"| clean | {len(classified['clean'])} | 全ルール合格 |",
        f"| needs_rewrite | {len(classified['needs_rewrite'])} | エラー記事だが規格未満（旧テンプレート等） |",
        f"| ineligible | {len(classified['ineligible'])} | B2マーカー検出：エラー記事でない疑い |",
        f"| skipped | {len(classified['skipped'])} | 規格外ページ（tool_* / errorCodeなし） |",
        f"| **合計** | **{total}** | |",
        "",
        "## エラー記事の内訳",
        f"| 区分 | 件数 |",
        f"|------|------|",
        f"| エラー記事数 | {len(error_arts)} |",
        f"| FAIL あり | {len(fail_arts)} |",
        f"| WARN のみ | {len(warn_arts)} |",
        f"| クリーン | {len(clean_arts)} |",
        f"| （規格外ページ） | {len(skipped_arts)} |",
        "",
        "## ルール別違反件数（エラー記事のみ）",
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

    # needs_rewrite リスト
    lines += ["", "## needs_rewrite — 規格未満のエラー記事", ""]
    nrw = classified["needs_rewrite"]
    if nrw:
        lines.append("| 記事 | FAIL ルール |")
        lines.append("|------|------------|")
        for r in sorted(nrw, key=lambda x: x["path"]):
            rules = ", ".join(sorted({f["rule"] for f in r["fails"]}))
            lines.append(f"| {r['path']} | {rules} |")
    else:
        lines.append("なし")

    # ineligible リスト
    lines += ["", "## ineligible — エラー記事でない疑い（B2検出）", ""]
    inel = classified["ineligible"]
    if inel:
        lines.append("| 記事 | FAIL ルール |")
        lines.append("|------|------------|")
        for r in sorted(inel, key=lambda x: x["path"]):
            rules = ", ".join(sorted({f["rule"] for f in r["fails"]}))
            lines.append(f"| {r['path']} | {rules} |")
    else:
        lines.append("なし")

    # skipped リスト
    lines += ["", "## skipped — 規格外ページ", ""]
    skip = classified["skipped"]
    if skip:
        for r in sorted(skip, key=lambda x: x["path"]):
            lines.append(f"- {r['path']}")
    else:
        lines.append("なし")

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
