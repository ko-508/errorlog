"""Fact/freshness/citation/risk checks for the existing quality workflow.

New articles are gated before publication. Existing articles are sampled in
small batches and marked as rewrite candidates instead of being edited here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import sys
import time
import http.client
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


BASE = Path(__file__).resolve().parent.parent
POSTS_DIR = BASE / "content" / "posts"
REPORTS_DIR = BASE / "reports" / "fact_check"
REWRITE_CANDIDATES_PATH = BASE / "data" / "rewrite_candidates.json"
NEW_ARTICLE_FAILURES_PATH = BASE / "data" / "fact_check_new_article_failures.json"
SCORE_HISTORY_PATH = BASE / "data" / "fact_check_score_history.jsonl"
UNAVAILABLE_HISTORY_PATH = BASE / "data" / "fact_check_unavailable_history.json"
EVIDENCE_DIR = BASE / "data" / "evidence"

# path.stem がサイドカーファイル名として安全かを検証する正規表現
_SAFE_STEM_RE = re.compile(r"^[A-Za-z0-9_-]+$")

EXISTING_LIMIT = int(os.getenv("FACT_CHECK_EXISTING_LIMIT", "1"))
MIN_FACTUAL = int(os.getenv("FACT_CHECK_MIN_FACTUAL", "75"))
MIN_FRESHNESS = int(os.getenv("FACT_CHECK_MIN_FRESHNESS", "50"))
MIN_CITATION = int(os.getenv("FACT_CHECK_MIN_CITATION", "15"))
MAX_RISK = int(os.getenv("FACT_CHECK_MAX_RISK", "55"))
CRITICAL_RISK = int(os.getenv("FACT_CHECK_CRITICAL_RISK", "85"))
REPORT_RETENTION_DAYS = int(os.getenv("FACT_CHECK_REPORT_RETENTION_DAYS", "30"))
REPORT_RETENTION_COUNT = int(os.getenv("FACT_CHECK_REPORT_RETENTION_COUNT", "500"))
FAIL_ON_EXISTING_CRITICAL = os.getenv("FACT_CHECK_FAIL_ON_EXISTING_CRITICAL", "").lower() == "true"
NEW_ARTICLE_MAX_RETRIES = int(os.getenv("FACT_CHECK_NEW_ARTICLE_MAX_RETRIES", "3"))
URL_CHECK_ENABLED = os.getenv("FACT_CHECK_URL_CHECK", "true").lower() != "false"
URL_CHECK_TIMEOUT = float(os.getenv("FACT_CHECK_URL_CHECK_TIMEOUT", "3"))
GEMINI_TIMEOUT_SECONDS = float(os.getenv("FACT_CHECK_GEMINI_TIMEOUT_SECONDS", "300"))
GEMINI_RETRY_ON_PARSE_ERROR = int(os.getenv("FACT_CHECK_GEMINI_RETRY_ON_PARSE_ERROR", "1"))
MAX_UNAVAILABLE_RATIO = float(os.getenv("FACT_CHECK_MAX_UNAVAILABLE_RATIO", "0.6"))
MAX_INPUT_CHARS = int(os.getenv("FACT_CHECK_MAX_INPUT_CHARS", "12000"))
GEMINI_DELAY_SECONDS = float(os.getenv("FACT_CHECK_GEMINI_DELAY_SECONDS", "0"))
GEMINI_TIMEOUT_COOLDOWN_SECONDS = float(os.getenv("FACT_CHECK_GEMINI_TIMEOUT_COOLDOWN_SECONDS", "30"))
UNAVAILABLE_RETRY_AFTER_HOURS = float(os.getenv("FACT_CHECK_UNAVAILABLE_RETRY_AFTER_HOURS", "24"))
RECENTLY_CHECKED_SKIP_HOURS = float(os.getenv("FACT_CHECK_RECENTLY_CHECKED_SKIP_HOURS", "168"))
# 新記事ゲートの多数決回数。1 で従来単発と同等（既存記事サンプリングは常に 1 回）
FACT_CHECK_VOTE_COUNT = int(os.getenv("FACT_CHECK_VOTE_COUNT", "3"))
PASS_AUDIT_ENABLED = os.getenv("FACT_CHECK_PASS_AUDIT_ENABLED", "true").lower() != "false"
PASS_AUDIT_WINDOW_DAYS = int(os.getenv("FACT_CHECK_PASS_AUDIT_WINDOW_DAYS", "14"))

SCORE_KEYS = ("factual_score", "freshness_score", "citation_coverage", "risk_score")

# プロンプト本文を変更した場合はこの値を手動でインクリメントしてください。
FACT_CHECK_PROMPT_VERSION = "1"

GEMINI_QUOTA_PATTERNS = (
    "RESOURCE_EXHAUSTED",
    "quota exceeded",
    "rate limit",
    "billing",
    "429",
)
GEMINI_MODEL_PATTERNS = (
    "NOT_FOUND",
    "model is not found",
    "not supported for generateContent",
    "API key not valid",
    "permission denied",
)
GEMINI_API_PATTERNS = (
    "Tool use with a response mime type",
    "response mime type",
    "application/json is unsupported",
    "INVALID_ARGUMENT",
    "external fact check unavailable",
    "gemini_error",
)
GEMINI_TIMEOUT_PATTERNS = (
    "Timeout",
    "ReadTimeout",
    "ConnectTimeout",
    "TimeoutException",
    "RetryError",
    "ConnectionError",
    "timed out",
    "gemini timeout",
)

HIGH_CHANGE_TERMS = [
    "api", "cloud", "aws", "azure", "gcp", "firebase", "openai", "gemini",
    "security", "oauth", "iam", "kubernetes", "docker", "terraform", "stripe",
    "pricing", "price", "law", "legal", "incident", "料金", "価格", "法律",
    "法令", "障害", "セキュリティ", "クラウド", "認証",
]

CRITICAL_TERMS = [
    "law", "legal", "finance", "medical", "investment", "diagnosis",
    "vulnerability", "credential", "secret", "private key", "access token",
    "法律", "金融", "医療", "投資", "診断", "脆弱性",
]

DANGEROUS_PATTERNS = [
    r"rm\s+-rf\s+/",
    r"chmod\s+777",
    r"curl\s+[^|]+[|]\s*(?:sh|bash)",
    r"--no-check-certificate",
    r"verify\s*=\s*false",
]

# ── ドメイン分類テーブル ──────────────────────────────────────────────────────

TOOL_OFFICIAL_DOMAINS: dict[str, list[str]] = {
    "Docker":        ["docs.docker.com", "docker.com"],
    "Docker Compose": ["docs.docker.com", "docker.com"],
    "Firebase":      ["firebase.google.com", "cloud.google.com"],
    "AWS":           ["docs.aws.amazon.com", "aws.amazon.com"],
    "GitHub API":    ["docs.github.com", "github.blog"],
    "OpenAI API":    ["platform.openai.com", "developers.openai.com", "help.openai.com"],
    "Azure":         ["learn.microsoft.com", "azure.microsoft.com"],
    "GCP":           ["cloud.google.com", "developers.google.com"],
    "GitLab":        ["docs.gitlab.com"],
    "Supabase":      ["supabase.com"],
    "Vercel":        ["vercel.com"],
    "Nginx":         ["nginx.org", "docs.nginx.com"],
    "Stripe":        ["docs.stripe.com", "stripe.com"],
    "Terraform":     ["developer.hashicorp.com", "registry.terraform.io"],
    "Ansible":       ["docs.ansible.com"],
    "Kubernetes":    ["kubernetes.io"],
    "Minikube":      ["minikube.sigs.k8s.io"],
    "Podman":        ["podman.io", "docs.podman.io", "podman-desktop.io"],
    "Slack":         ["api.slack.com", "docs.slack.dev", "slack.dev"],
    "Bitbucket":     ["support.atlassian.com", "developer.atlassian.com"],
}

# 全ツールの公式ドメインを統合したセット（サブドメイン一致検索用）
_ALL_OFFICIAL_DOMAINS: frozenset[str] = frozenset(
    d for domains in TOOL_OFFICIAL_DOMAINS.values() for d in domains
)

VENDOR_COMMUNITY_DOMAINS: list[str] = [
    "repost.aws", "community.openai.com", "community.atlassian.com",
    "discuss.google.dev", "community.crowdin.com",
]

# ドット区切り先頭ラベルがこれらに完全一致するドメインは vendor_community（official より優先）
VENDOR_COMMUNITY_PREFIXES: tuple[str, ...] = ("forums.", "discuss.", "community.")

COMMUNITY_BLOG_DOMAINS: list[str] = [
    "stackoverflow.com", "qiita.com", "zenn.dev", "medium.com",
    "github.com", "dev.to",
]

# HTTP 200 を返すが Gemini grounding でコンテンツ照合ができないドメイン。
# Editor's Note の引用源として使用禁止。
UNVERIFIABLE_DOMAINS: frozenset[str] = frozenset({
    "reddit.com",
    "redd.it",
    "vertexaisearch.cloud.google.com",
})

OTHER_DOMAINS: list[str] = ["youtube.com", "youtu.be"]


def _domain_ends_with(domain: str, suffix: str) -> bool:
    """domain が suffix と完全一致、またはサブドメインとして suffix を末尾に持つか。"""
    return domain == suffix or domain.endswith("." + suffix)


def _has_vendor_community_prefix(domain: str) -> bool:
    """先頭ラベルが forums/discuss/community に完全一致するか（mycommunity. は除外）。"""
    first_label = domain.split(".")[0] + "."
    return any(first_label == prefix for prefix in VENDOR_COMMUNITY_PREFIXES)


def _classify_resolved_domain(domain: str) -> str:
    """着地ドメインを official/vendor_community/community_blog/other/unknown に分類。"""
    if not domain:
        return "unknown"
    # フォーラム・コミュニティ系接頭辞を official より先に判定
    if _has_vendor_community_prefix(domain):
        return "vendor_community"
    if any(_domain_ends_with(domain, d) for d in VENDOR_COMMUNITY_DOMAINS):
        return "vendor_community"
    if any(_domain_ends_with(domain, d) for d in _ALL_OFFICIAL_DOMAINS):
        return "official"
    if any(_domain_ends_with(domain, d) for d in UNVERIFIABLE_DOMAINS):
        return "unverifiable"
    if any(_domain_ends_with(domain, d) for d in COMMUNITY_BLOG_DOMAINS):
        return "community_blog"
    if any(_domain_ends_with(domain, d) for d in OTHER_DOMAINS):
        return "other"
    return "unknown"


def _resolve_gemini_model() -> str:
    return os.getenv("FACT_CHECK_GEMINI_MODEL", "gemini-2.5-flash")


def gemini_unavailable_category(error: str) -> str:
    lower = error.lower()
    if any(pattern.lower() in lower for pattern in GEMINI_QUOTA_PATTERNS):
        return "quota"
    if any(pattern.lower() in lower for pattern in GEMINI_MODEL_PATTERNS):
        return "model"
    if any(pattern.lower() in lower for pattern in GEMINI_TIMEOUT_PATTERNS):
        return "timeout"
    if any(pattern.lower() in lower for pattern in GEMINI_API_PATTERNS):
        return "api"
    return ""


@dataclass
class GeminiEvaluation:
    status: str
    scores: dict[str, int] | None = None
    reasons: list[str] = field(default_factory=list)
    required_actions: list[str] = field(default_factory=list)
    sources: list[dict[str, str]] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
    citation_mismatches: list[dict[str, str]] = field(default_factory=list)
    error: str = ""
    error_category: str = ""
    raw_response_excerpt: str = ""
    parse_error: str = ""


@dataclass
class FactCheckResult:
    path: str
    title: str
    mode: str
    scores: dict[str, int]
    passed: bool
    critical: bool
    reasons: list[str]
    required_actions: list[str]
    detected_at: str
    status: str
    critical_level: str = ""
    report_path: str = ""
    evaluator: str = "heuristic"
    sources: list[dict[str, Any]] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
    citation_mismatches: list[dict[str, str]] = field(default_factory=list)
    improvement_suggestions: list[str] = field(default_factory=list)
    error: str = ""
    score_history_appended: bool = False
    score_valid: bool = True
    raw_response_excerpt: str = ""
    parse_error: str = ""
    url_checked: int = 0
    url_skipped: int = 0
    url_invalid: int = 0
    gemini_error_category: str = ""
    original_chars: int = 0
    fact_check_input_chars: int = 0
    fact_check_input_truncated: bool = False
    timeout_seconds: float = GEMINI_TIMEOUT_SECONDS
    gemini_model: str = ""
    article_hash: str = ""
    error_detail: str | None = None
    # 多数決フィールド（単発採点時はデフォルト値のまま）
    vote_group_id: str = ""
    is_final_vote: bool = False
    vote_count: int = 1
    tags: list[str] = field(default_factory=list)


def split_frontmatter(content: str) -> tuple[dict[str, str], str]:
    if not content.startswith("---"):
        return {}, content
    end = content.find("\n---\n", 3)
    if end == -1:
        return {}, content
    raw = content[4:end]
    body = content[end + 5 :]
    fm: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fm[key.strip()] = value.strip().strip('"').strip("'")
    return fm, body


def extract_title(path: Path, fm: dict[str, str]) -> str:
    return fm.get("title") or path.stem.replace("_", " ")


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    value = value.strip().strip('"').split("T")[0]
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def count_citations(text: str) -> int:
    return len(extract_urls(text))


def extract_urls(text: str) -> list[str]:
    markdown_links = re.findall(r"\[[^\]]+\]\((https?://[^)]+)\)", text)
    bare_urls = re.findall(r"(?<!\()https?://[^\s)]+", text)
    urls = []
    for url in markdown_links + bare_urls:
        clean = url.rstrip(".,)")
        if clean not in urls:
            urls.append(clean)
    return urls


def source_type_value(source: dict[str, Any]) -> str:
    return str(source.get("source_type") or source.get("type") or "").strip().lower()


def is_valid_http_url(url: str) -> bool:
    if not url:
        return False
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def normalize_url_for_check(url: str) -> str | None:
    url = str(url or "")
    candidates = [url.strip()]
    without_whitespace = re.sub(r"\s+", "", url)
    if without_whitespace not in candidates:
        candidates.append(without_whitespace)

    for candidate in candidates:
        if not candidate:
            continue
        if any(ord(ch) < 32 or ord(ch) == 127 or ch.isspace() for ch in candidate):
            continue
        if is_valid_http_url(candidate):
            return candidate
    return None


def check_url_status(url: str) -> dict[str, Any]:
    if not URL_CHECK_ENABLED:
        return {"status": "skipped", "final_url": None}
    normalized = normalize_url_for_check(url)
    if normalized is None:
        return {"status": "invalid_url", "final_url": None}
    try:
        request = urllib.request.Request(normalized, method="HEAD", headers={"User-Agent": "ErrorLogFactCheck/1.0"})
        with urllib.request.urlopen(request, timeout=URL_CHECK_TIMEOUT) as response:
            return {"status": str(response.status), "final_url": getattr(response, "url", None) or normalized}
    except Exception:
        try:
            request = urllib.request.Request(normalized, method="GET", headers={"User-Agent": "ErrorLogFactCheck/1.0"})
            with urllib.request.urlopen(request, timeout=URL_CHECK_TIMEOUT) as response:
                return {"status": str(response.status), "final_url": getattr(response, "url", None) or normalized}
        except http.client.InvalidURL:
            return {"status": "error", "final_url": None}
        except (urllib.error.URLError, TimeoutError, ValueError):
            return {"status": "skipped", "final_url": None}
        except Exception:
            return {"status": "error", "final_url": None}


def validate_sources(
    sources: list[dict[str, Any]],
    article_tags: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int], int, list[str]]:
    seen_by_claim: dict[str, set[str]] = {}
    validated: list[dict[str, Any]] = []
    stats = {"checked": 0, "skipped": 0, "invalid": 0}
    quality_delta = 0
    notes: list[str] = []

    # 記事タグから tool_match 判定に使うドメインセットを構築
    tag_official_domains: frozenset[str] = frozenset(
        d
        for tag in (article_tags or [])
        for d in TOOL_OFFICIAL_DOMAINS.get(tag, [])
    )

    for source in sources:
        url = str(source.get("url", "")).strip()
        claim = str(source.get("claim", "")).strip()
        stype = source_type_value(source) or "unknown"
        if not is_valid_http_url(url):
            stats["invalid"] += 1
            notes.append("invalid source URL was ignored")
            continue
        claim_key = claim or "__general__"
        seen_urls = seen_by_claim.setdefault(claim_key, set())
        if url in seen_urls:
            stats["invalid"] += 1
            notes.append("duplicate source URL for the same claim was ignored")
            continue
        seen_urls.add(url)

        result = check_url_status(url)
        status = result["status"]
        final_url = result["final_url"]
        if status == "skipped":
            stats["skipped"] += 1
        else:
            stats["checked"] += 1

        is_gr = "vertexaisearch.cloud.google.com" in url
        # resolved_source_type / resolved_domain / tool_match を決定
        if is_gr and (not final_url or "vertexaisearch.cloud.google.com" in final_url):
            resolved_source_type = "unresolved"
            resolved_domain = None
        else:
            landing_url = final_url or url
            resolved_domain = urllib.parse.urlparse(landing_url).netloc or None
            resolved_source_type = _classify_resolved_domain(resolved_domain or "")

        tool_match = bool(
            resolved_domain
            and tag_official_domains
            and any(_domain_ends_with(resolved_domain, d) for d in tag_official_domains)
        )

        normalized = dict(source)
        normalized["url"] = url
        normalized["claim"] = claim
        normalized["source_type"] = stype
        normalized["url_check_status"] = status
        normalized["final_url"] = final_url or url
        normalized["is_grounding_redirect"] = is_gr
        normalized["resolved_source_type"] = resolved_source_type
        normalized["resolved_domain"] = resolved_domain
        normalized["tool_match"] = tool_match
        validated.append(normalized)

    if validated:
        types = {source_type_value(source) for source in validated}
        high_quality = {"official", "documentation", "government", "academic", "company"}
        low_quality = {"blog", "other", "unknown", ""}
        if types and types <= low_quality:
            quality_delta -= 20
            notes.append("citation quality is low because sources are blog/other/unknown only")
        elif types & high_quality:
            quality_delta += 10
        # resolved_source_type ベースの official URL 比率補正
        # (source_type は Gemini 申告値; resolved_source_type は URL 実解決値で別信号)
        official_count = sum(1 for s in validated if s.get("resolved_source_type") == "official")
        official_ratio = official_count / len(validated)
        if official_ratio == 0:
            quality_delta -= 10
            notes.append("no URLs resolved to known official domains")
        elif official_ratio >= 0.5:
            quality_delta += 5
            notes.append(f"high official URL ratio ({official_ratio:.0%})")
    return validated, stats, quality_delta, notes


def estimate_claims(text: str) -> int:
    body = re.sub(r"```[\s\S]*?```", "", text)
    sentences = re.split(r"[。\n.!?]+", body)
    claim_like = 0
    for sentence in sentences:
        s = sentence.strip()
        if len(s) < 24:
            continue
        if re.search(r"\b(?:must|should|can|will|error|status|api|token|security)\b", s, re.I):
            claim_like += 1
        elif re.search(r"(です|ます|必要|原因|解決|設定|認証|権限|エラー|できます)", s):
            claim_like += 1
        elif re.search(r"\b\d{3}\b|\b20\d{2}\b|v\d+(?:\.\d+)?", s):
            claim_like += 1
    return max(1, claim_like)


IMPORTANT_SENTENCE_RE = re.compile(
    r"(概要|原因|解決|注意|権限|認証|セキュリティ|削除|料金|価格|API|仕様|"
    r"error|cause|solution|security|permission|delete|remove|pricing|version|"
    r"\b\d{3}\b|20\d{2}|v\d+(?:\.\d+)?|必ず|絶対|must|should|never|always)",
    re.IGNORECASE,
)


def truncate_code_block(match: re.Match[str]) -> str:
    lang = (match.group(1) or "").strip().lower()
    code = match.group(2)
    lines = code.splitlines()
    keep = 10 if lang in {"bash", "sh", "shell", "json", "yaml", "yml", "docker", "dockerfile"} else 6
    kept = lines[:keep]
    if len(lines) > keep:
        kept.append("... truncated ...")
    return "```" + lang + "\n" + "\n".join(kept) + "\n```"


def shorten_code_blocks(text: str) -> str:
    return re.sub(r"```([^\n`]*)\n([\s\S]*?)```", truncate_code_block, text)


def trim_to_limit(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    marker = "\n\n... fact check input truncated ...\n"
    return text[: max(0, limit - len(marker))].rstrip() + marker, True


def build_fact_check_input(title: str, fm: dict[str, str], body: str) -> tuple[str, bool]:
    body = shorten_code_blocks(body)
    frontmatter_lines = [f"title: {title}"]
    for key in ("description", "service", "errorCode", "error_type", "tags"):
        if fm.get(key):
            frontmatter_lines.append(f"{key}: {fm[key]}")

    selected: list[str] = []
    paragraphs = re.split(r"\n{2,}", body)
    for paragraph in paragraphs:
        stripped = paragraph.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            selected.append(stripped)
            continue
        heading_context = re.search(r"(概要|原因|解決|対策|注意|手順|エラー|原因|solution|cause|fix)", stripped, re.I)
        code_context = stripped.startswith("```")
        if heading_context or code_context:
            selected.append(stripped)
            continue
        sentences = re.split(r"(?<=[。.!?])\s+|\n", stripped)
        important = [s.strip() for s in sentences if s.strip() and IMPORTANT_SENTENCE_RE.search(s)]
        if important:
            selected.extend(important[:4])

    if not selected:
        selected = paragraphs[:8]

    assembled = "\n".join([
        "## Frontmatter",
        "\n".join(frontmatter_lines),
        "",
        "## Fact-check input excerpt",
        "\n\n".join(selected),
    ])
    return trim_to_limit(assembled, MAX_INPUT_CHARS)


def is_high_change(title: str, body: str) -> bool:
    haystack = f"{title}\n{body}".lower()
    return any(term.lower() in haystack for term in HIGH_CHANGE_TERMS)


def compute_freshness(fm: dict[str, str], body: str, high_change: bool) -> int:
    today = date.today()
    updated = parse_date(fm.get("lastmod") or fm.get("updated") or fm.get("date"))
    if not updated:
        return 45 if high_change else 60
    age_days = max(0, (today - updated).days)
    if age_days <= 30:
        score = 95
    elif age_days <= 90:
        score = 85
    elif age_days <= 180:
        score = 72
    elif age_days <= 365:
        score = 60
    else:
        score = 45
    if high_change and age_days > 180:
        score -= 15
    if re.search(r"20(1\d|2[0-4])|古い|廃止|deprecated|legacy", body, re.I):
        score -= 8
    return max(0, min(100, score))


def heuristic_scores(title: str, fm: dict[str, str], body: str) -> tuple[dict[str, int], list[str], list[str]]:
    citations = count_citations(body)
    claims = estimate_claims(body)
    citation_coverage = min(100, round(citations / claims * 100))
    high_change = is_high_change(title, body)
    freshness = compute_freshness(fm, body, high_change)

    factual = 86
    risk = 18
    reasons: list[str] = []
    actions: list[str] = []

    if citation_coverage < MIN_CITATION:
        factual -= 16
        risk += 15
        reasons.append("citation coverage is below the threshold")
        actions.append("Add links to official documentation or primary sources for key claims.")
    if freshness < MIN_FRESHNESS:
        factual -= 8
        risk += 10
        reasons.append("freshness score is below the threshold")
        actions.append("Review current official docs and update changed API/spec/pricing details.")
    if high_change:
        risk += 8
    if any(re.search(pattern, body, re.I) for pattern in DANGEROUS_PATTERNS):
        factual -= 20
        risk += 35
        reasons.append("potentially dangerous command or insecure setting detected")
        actions.append("Replace risky commands/settings with safer alternatives and warnings.")
    if re.search(r"(必ず|絶対|100%|完全に|always|never)", body, re.I):
        factual -= 5
        risk += 5
        reasons.append("absolute wording may overstate technical certainty")
        actions.append("Soften absolute claims unless they are directly sourced.")

    return (
        {
            "factual_score": max(0, min(100, factual)),
            "freshness_score": max(0, min(100, freshness)),
            "citation_coverage": max(0, min(100, citation_coverage)),
            "risk_score": max(0, min(100, risk)),
        },
        reasons,
        actions,
    )


def extract_json_object_text(raw: str) -> str:
    text = raw.strip()
    block = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if block:
        text = block.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return text
    return text[start:end + 1]


def raw_response_excerpt(raw: str, limit: int = 1000) -> str:
    if raw == "":
        return "<empty>"
    return raw[:limit]


def invalid_json_evaluation(error: str, raw: str) -> GeminiEvaluation:
    return GeminiEvaluation(
        status="invalid_json",
        error=error,
        raw_response_excerpt=raw_response_excerpt(raw),
        parse_error=error,
    )


def validate_gemini_payload(raw: str) -> GeminiEvaluation:
    payload = extract_json_object_text(raw)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        if raw == "":
            return invalid_json_evaluation("empty response: Gemini returned no text", raw)
        return invalid_json_evaluation(f"json_parse_error: {exc}", raw)
    if not isinstance(data, dict):
        return invalid_json_evaluation("invalid schema: root JSON value is not an object", raw)

    missing = [key for key in SCORE_KEYS if key not in data]
    if missing:
        return invalid_json_evaluation(f"missing required keys: {', '.join(missing)}", raw)

    scores: dict[str, int] = {}
    for key in SCORE_KEYS:
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            return invalid_json_evaluation(f"invalid schema: invalid type for {key}", raw)
        try:
            number = int(float(value))
        except ValueError:
            return invalid_json_evaluation(f"invalid schema: non numeric score for {key}", raw)
        if number < 0 or number > 100:
            return invalid_json_evaluation(f"invalid schema: score out of range for {key}", raw)
        scores[key] = number

    reasons = data.get("reasons", [])
    actions = data.get("required_actions", [])
    sources = data.get("sources", [])
    unsupported = data.get("unsupported_claims", [])
    citation_mismatches = data.get("citation_mismatches", [])
    claims = data.get("claims", [])

    if not isinstance(reasons, list) or not isinstance(actions, list):
        return invalid_json_evaluation("invalid schema: reasons/required_actions must be arrays", raw)
    if not isinstance(sources, list) or not isinstance(unsupported, list):
        return invalid_json_evaluation("invalid schema: sources/unsupported_claims must be arrays", raw)
    if not isinstance(citation_mismatches, list):
        citation_mismatches = []

    normalized_sources: list[dict[str, str]] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        url = str(source.get("url", "")).strip()
        normalized_sources.append({
            "url": url,
            "title": str(source.get("title", "")).strip(),
            "claim": str(source.get("claim", "")).strip(),
            "source_type": str(source.get("source_type") or source.get("type") or "").strip() or "unknown",
        })

    for claim in claims if isinstance(claims, list) else []:
        if not isinstance(claim, dict):
            continue
        claim_text = str(claim.get("text", "")).strip()
        urls = claim.get("source_urls", [])
        if claim_text and (not isinstance(urls, list) or not any(re.match(r"^https?://", str(u)) for u in urls)):
            unsupported.append(claim_text)

    normalized_citation_mismatches: list[dict[str, str]] = []
    for mismatch in citation_mismatches:
        if not isinstance(mismatch, dict):
            continue
        url = str(mismatch.get("url", "")).strip()
        claimed = str(mismatch.get("claimed", "")).strip()
        actual = str(mismatch.get("actual", "")).strip()
        if not url or not claimed or not actual:
            print(
                "[fact_check] WARNING: dropped citation_mismatch without url/claimed/actual",
                file=sys.stderr,
            )
            continue
        normalized_citation_mismatches.append({
            "url": url,
            "claimed": claimed,
            "actual": actual,
        })

    return GeminiEvaluation(
        status="ok",
        scores=scores,
        reasons=[str(item) for item in reasons],
        required_actions=[str(item) for item in actions],
        sources=normalized_sources,
        unsupported_claims=[str(item) for item in unsupported],
        citation_mismatches=normalized_citation_mismatches,
    )


def _call_gemini_api(api_key: str, model: str, prompt: str) -> str:
    """Invoke Gemini API with Google Search grounding and return response text.

    Runs in a worker thread. Any exception propagates to the caller via the Future.
    """
    from google import genai as google_genai
    from google.genai import types as genai_types

    client = google_genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
        ),
    )
    return response.text or ""


def generate_gemini_content_with_timeout(api_key: str, model: str, prompt: str) -> GeminiEvaluation:
    """Call Gemini API with a hard timeout using a worker thread.

    ThreadPoolExecutor is used instead of multiprocessing to avoid a classic
    pipe-buffer deadlock: when the response exceeds the OS pipe buffer (~4 KB on
    Windows) the child's queue.put() blocks, but the parent is in proc.join()
    waiting for the child to exit — a deadlock that manifests as a full-timeout
    hang even when Gemini responds successfully.  With threads, the result is
    shared in-process memory; no IPC pipe is involved.
    """
    mock_sleep = os.getenv("FACT_CHECK_GEMINI_MOCK_SLEEP_SECONDS")
    if mock_sleep:
        try:
            sleep_seconds = float(mock_sleep)
        except ValueError:
            sleep_seconds = 0
        if sleep_seconds > GEMINI_TIMEOUT_SECONDS:
            time.sleep(max(0, GEMINI_TIMEOUT_SECONDS))
            return GeminiEvaluation(
                status="unavailable",
                error=f"gemini timeout ({GEMINI_TIMEOUT_SECONDS:.0f}s)",
                error_category="timeout",
            )
        time.sleep(max(0, sleep_seconds))

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(_call_gemini_api, api_key, model, prompt)
    try:
        text = future.result(timeout=GEMINI_TIMEOUT_SECONDS)
    except FuturesTimeoutError:
        executor.shutdown(wait=False)
        return GeminiEvaluation(
            status="unavailable",
            error=f"gemini timeout ({GEMINI_TIMEOUT_SECONDS:.0f}s)",
            error_category="timeout",
        )
    except KeyboardInterrupt:
        executor.shutdown(wait=False)
        raise
    except Exception as exc:
        executor.shutdown(wait=False)
        error = f"gemini_error: {type(exc).__name__}: {exc}"
        return GeminiEvaluation(
            status="unavailable",
            error=error,
            error_category=gemini_unavailable_category(error),
        )
    executor.shutdown(wait=False)
    return validate_gemini_payload(text)


def retry_prompt_for_parse_error(prompt: str) -> str:
    return (
        prompt
        + "\n\nThe previous response could not be parsed as JSON. "
        "Return only a single JSON object this time. "
        "Do not use Markdown code fences. Do not include explanations. "
        "The first character must be { and the last character must be }."
    )


def evaluate_gemini_with_parse_retry(api_key: str, model: str, prompt: str) -> GeminiEvaluation:
    attempts = max(0, GEMINI_RETRY_ON_PARSE_ERROR) + 1
    current_prompt = prompt
    last_result: GeminiEvaluation | None = None
    for attempt in range(attempts):
        result = generate_gemini_content_with_timeout(api_key, model, current_prompt)
        if result.status != "invalid_json":
            return result
        last_result = result
        if attempt < attempts - 1:
            current_prompt = retry_prompt_for_parse_error(prompt)
    return last_result or invalid_json_evaluation("empty response: Gemini returned no text", "")


def gemini_scores(title: str, fact_check_input: str) -> GeminiEvaluation:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return GeminiEvaluation(status="unavailable", error="GEMINI_API_KEY is not set")

    mock_response = os.getenv("FACT_CHECK_GEMINI_MOCK_RESPONSE")
    if mock_response is not None:
        if mock_response == "__EMPTY__":
            mock_response = ""
        responses = mock_response.split("||RETRY||")
        attempts = max(0, GEMINI_RETRY_ON_PARSE_ERROR) + 1
        last_result: GeminiEvaluation | None = None
        for attempt in range(attempts):
            raw = responses[min(attempt, len(responses) - 1)]
            result = validate_gemini_payload(raw)
            if result.status != "invalid_json":
                return result
            last_result = result
        return last_result or invalid_json_evaluation("empty response: Gemini returned no text", "")
    mock_error = os.getenv("FACT_CHECK_GEMINI_MOCK_ERROR")
    if mock_error is not None:
        return GeminiEvaluation(
            status="unavailable",
            error=mock_error,
            error_category=gemini_unavailable_category(mock_error),
        )

    prompt = f"""
Evaluate this Japanese technical article for publication quality.
Use Google Search grounding. Do not rely on model memory for volatile facts.

For each important factual claim, return at least one source URL. Prefer official
documentation, vendor status pages, RFCs, standards, laws, or other primary
sources. Claims without a source URL must be listed in unsupported_claims.

Return JSON only:
No Markdown code fences.
No explanatory text before or after JSON.
Start the response with "{{" and end it with "}}".
{{
  "factual_score": 0-100,
  "freshness_score": 0-100,
  "citation_coverage": 0-100,
  "risk_score": 0-100,
  "reasons": ["short reason"],
  "required_actions": ["short action"],
  "sources": [{{"url": "https://...", "title": "source title", "claim": "claim it supports", "source_type": "official|documentation|government|academic|company|blog|other|unknown"}}],
  "unsupported_claims": ["claim with no usable source"],
  "citation_mismatches": [{{"url": "https://...", "claimed": "what the article says about this URL", "actual": "what the URL actually says"}}],
  "claims": [{{"text": "claim", "source_urls": ["https://..."]}}]
}}

For every external URL cited in the article's Editor's Note, open/check the actual
URL content and verify whether the article's statement about that URL matches it.
If the article claims something different from the URL's actual content, add an
entry to citation_mismatches with all of url, claimed, and actual. If the
Editor's Note has no cited external URLs, or all cited URL claims match, return
an empty citation_mismatches array.

Title: {title}

Article excerpt:
{fact_check_input}
"""
    try:
        return evaluate_gemini_with_parse_retry(
            api_key,
            _resolve_gemini_model(),
            prompt,
        )
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        error = f"gemini_error: {type(exc).__name__}: {exc}"
        return GeminiEvaluation(
            status="unavailable",
            error=error,
            error_category=gemini_unavailable_category(error),
        )


def failed_gemini_result(path: Path, title: str, mode: str, gemini: GeminiEvaluation) -> FactCheckResult:
    detail = gemini.error[:300]
    raw = gemini.raw_response_excerpt
    if raw and raw != "<empty>":
        detail = f"{detail} | raw:{raw[:300]}"
    return FactCheckResult(
        path=str(path.as_posix()),
        title=title,
        mode=mode,
        scores={
            "factual_score": 0,
            "freshness_score": 0,
            "citation_coverage": 0,
            "risk_score": 0,
        },
        passed=False,
        critical=False,
        reasons=[f"Gemini fact check returned invalid JSON: {gemini.error}"],
        required_actions=["Retry fact check or inspect the article manually before publication."],
        detected_at=date.today().isoformat(),
        status="failed_fact_check",
        evaluator="gemini_invalid",
        error=gemini.error,
        score_valid=False,
        raw_response_excerpt=gemini.raw_response_excerpt,
        parse_error=gemini.parse_error or gemini.error,
        error_detail=detail,
    )


def unavailable_gemini_result(
    path: Path,
    title: str,
    mode: str,
    error: str,
    category: str,
) -> FactCheckResult:
    return FactCheckResult(
        path=str(path.as_posix()),
        title=title,
        mode=mode,
        scores={
            "factual_score": 0,
            "freshness_score": 0,
            "citation_coverage": 0,
            "risk_score": 0,
        },
        passed=False,
        critical=False,
        reasons=[f"external fact check unavailable: {error}"],
        required_actions=["Retry fact check when Gemini becomes available."],
        detected_at=date.today().isoformat(),
        status="fact_check_unavailable",
        evaluator="gemini_unavailable",
        error=error,
        gemini_error_category=category,
        score_valid=False,
        error_detail=error[:300],
    )


def attach_input_metadata(
    result: FactCheckResult,
    original_chars: int,
    fact_check_input_chars: int,
    truncated: bool,
) -> FactCheckResult:
    result.original_chars = original_chars
    result.fact_check_input_chars = fact_check_input_chars
    result.fact_check_input_truncated = truncated
    result.timeout_seconds = GEMINI_TIMEOUT_SECONDS
    return result


FAILURE_REASON_PATTERNS = (
    "citation coverage is below the threshold",
    "factual score is below the threshold",
    "freshness score is below the threshold",
    "risk score is above the threshold",
    "one or more claims are unsupported or unverifiable",
)


def normalize_final_messages(
    status: str,
    evaluator: str,
    scores: dict[str, int],
    reasons: list[str],
    actions: list[str],
    unsupported_claims: list[str],
) -> tuple[list[str], list[str], list[str]]:
    clean_reasons = merge_unique([], reasons)
    clean_actions = merge_unique([], actions)
    suggestions: list[str] = []
    if status != "pass":
        return clean_reasons, clean_actions, suggestions

    failure_reasons: list[str] = []
    pass_reasons: list[str] = []
    for reason in clean_reasons:
        lower = reason.lower()
        if any(pattern in lower for pattern in FAILURE_REASON_PATTERNS):
            failure_reasons.append(reason)
        else:
            pass_reasons.append(reason)

    if unsupported_claims or failure_reasons:
        suggestions.append(
            "Optional improvement: add official or primary source URLs for unsupported or weakly sourced claims."
        )
    for action in clean_actions:
        normalized_action = action.lower().replace("optional improvement:", "").strip()
        already_covered = any(
            normalized_action in suggestion.lower() or suggestion.lower() in normalized_action
            for suggestion in suggestions
        )
        if action and not already_covered:
            suggestions.append(f"Optional improvement: {action}")

    if not pass_reasons:
        pass_reasons = [
            (
                "Fact check passed: scores met thresholds "
                f"(factual={scores['factual_score']}, freshness={scores['freshness_score']}, "
                f"citation={scores['citation_coverage']}, risk={scores['risk_score']})."
            )
        ]
        if evaluator == "gemini":
            pass_reasons.append("Gemini fact check completed successfully with URL-backed sources.")

    return pass_reasons, [], merge_unique([], suggestions)


def _attach_run_context(result: FactCheckResult, article_hash: str) -> FactCheckResult:
    result.article_hash = article_hash
    result.gemini_model = _resolve_gemini_model()
    return result


def evaluate_content(path: Path, content: str, mode: str) -> FactCheckResult:
    fm, body = split_frontmatter(content)
    title = extract_title(path, fm)
    original_chars = len(content)
    article_hash = compute_article_hash(body)
    fact_check_input, fact_check_input_truncated = build_fact_check_input(title, fm, body)
    fact_check_input_chars = len(fact_check_input)
    gemini = gemini_scores(title, fact_check_input)
    if gemini.status == "invalid_json":
        return _attach_run_context(
            attach_input_metadata(
                failed_gemini_result(path, title, mode, gemini),
                original_chars,
                fact_check_input_chars,
                fact_check_input_truncated,
            ),
            article_hash,
        )
    if gemini.status == "unavailable" and gemini.error_category:
        return _attach_run_context(
            attach_input_metadata(
                unavailable_gemini_result(path, title, mode, gemini.error, gemini.error_category),
                original_chars,
                fact_check_input_chars,
                fact_check_input_truncated,
            ),
            article_hash,
        )

    scores, reasons, actions = heuristic_scores(title, fm, body)
    sources: list[dict[str, Any]] = [
        {"url": url, "title": "", "claim": "", "source_type": "unknown"} for url in extract_urls(body)
    ]
    unsupported_claims: list[str] = []
    citation_mismatches: list[dict[str, str]] = []
    evaluator = "heuristic"

    if gemini.status == "ok" and gemini.scores:
        evaluator = "gemini"
        fallback_scores = scores
        scores = gemini.scores
        # Keep deterministic guardrails even when Gemini is available.
        scores["citation_coverage"] = min(scores["citation_coverage"], fallback_scores["citation_coverage"])
        scores["freshness_score"] = min(scores["freshness_score"], fallback_scores["freshness_score"])
        reasons = gemini.reasons + [r for r in reasons if r not in gemini.reasons]
        actions = gemini.required_actions + [a for a in actions if a not in gemini.required_actions]
        sources = gemini.sources or sources
        unsupported_claims = gemini.unsupported_claims
        citation_mismatches = gemini.citation_mismatches
        if unsupported_claims:
            scores["citation_coverage"] = min(scores["citation_coverage"], max(0, 100 - len(unsupported_claims) * 20))
            scores["risk_score"] = min(100, scores["risk_score"] + min(25, len(unsupported_claims) * 8))
            reasons.append("one or more claims are unsupported or unverifiable")
            actions.append("Add official or primary source URLs for unsupported claims.")
    elif gemini.status == "unavailable" and gemini.error:
        reasons.append(f"external fact check unavailable: {gemini.error}")

    unavailable_reason = any(
        "external fact check unavailable" in reason or "gemini_error" in reason
        for reason in reasons
    )
    if mode == "existing" and unavailable_reason:
        category = gemini.error_category or gemini_unavailable_category("; ".join(reasons))
        return _attach_run_context(
            attach_input_metadata(
                unavailable_gemini_result(
                    path,
                    title,
                    mode,
                    gemini.error or "; ".join(reasons),
                    category or "api",
                ),
                original_chars,
                fact_check_input_chars,
                fact_check_input_truncated,
            ),
            article_hash,
        )

    article_tags = re.findall(r'"([^"]+)"', fm.get("tags", ""))
    sources, url_stats, citation_quality_delta, source_notes = validate_sources(sources, article_tags)
    if citation_quality_delta < 0:
        scores["citation_coverage"] = max(0, scores["citation_coverage"] + citation_quality_delta)
    elif citation_quality_delta > 0:
        scores["citation_coverage"] = min(100, scores["citation_coverage"] + citation_quality_delta)
    for note in source_notes:
        if note not in reasons:
            reasons.append(note)

    if not sources:
        unsupported_claims.append("No URL-backed sources were available for article claims.")
        if mode == "new":
            scores["citation_coverage"] = 0
            reasons.append("new article has no URL-backed sources")
            actions.append("Add at least one official or primary source URL before publication.")

    # 判定軸は factual + risk + citation の3軸。freshness はスコア記録のみ
    passed = (
        scores["factual_score"] >= MIN_FACTUAL
        and scores["risk_score"] <= MAX_RISK
        and scores["citation_coverage"] >= MIN_CITATION
    )
    critical_topic = any(term.lower() in f"{title}\n{body}".lower() for term in CRITICAL_TERMS)
    if scores["risk_score"] >= CRITICAL_RISK:
        critical_level = "high"
    elif critical_topic and scores["factual_score"] < 55:
        critical_level = "medium"
    else:
        critical_level = ""
    critical = critical_level != ""
    if not passed and not actions:
        actions.append("Review factual claims, update stale sections, and add primary sources.")

    status = "pass"
    if critical:
        status = "critical"
    elif not passed:
        status = "reject" if mode == "new" else "needs_revision"

    reasons, actions, improvement_suggestions = normalize_final_messages(
        status,
        evaluator,
        scores,
        reasons,
        actions,
        unsupported_claims,
    )

    return _attach_run_context(
        attach_input_metadata(FactCheckResult(
            path=str(path.as_posix()),
            title=title,
            mode=mode,
            scores=scores,
            passed=passed,
            critical=critical,
            critical_level=critical_level,
            reasons=reasons,
            required_actions=actions,
            detected_at=date.today().isoformat(),
            status=status,
            evaluator=evaluator,
            sources=sources,
            unsupported_claims=unsupported_claims,
            citation_mismatches=citation_mismatches,
            improvement_suggestions=improvement_suggestions,
            url_checked=url_stats["checked"],
            url_skipped=url_stats["skipped"],
            url_invalid=url_stats["invalid"],
            tags=article_tags,
        ), original_chars, fact_check_input_chars, fact_check_input_truncated),
        article_hash,
    )


def safe_report_name(path: Path) -> str:
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:8]
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", path.stem)[:80]
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    return f"{stamp}_{slug}_{digest}.json"


def cleanup_reports() -> None:
    if not REPORTS_DIR.exists():
        return
    cutoff = datetime.now() - timedelta(days=max(0, REPORT_RETENTION_DAYS))
    for subdir in [REPORTS_DIR / "new_articles", REPORTS_DIR / "existing_articles"]:
        if not subdir.exists():
            continue
        files = sorted(subdir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for index, path in enumerate(files):
            too_old = datetime.fromtimestamp(path.stat().st_mtime) < cutoff
            too_many = REPORT_RETENTION_COUNT > 0 and index >= REPORT_RETENTION_COUNT
            if too_old or too_many:
                path.unlink(missing_ok=True)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compute_article_hash(body: str) -> str:
    """SHA256 of the article body (frontmatter excluded), first 12 hex chars."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]


def append_score_history(result: FactCheckResult) -> bool:
    """Append one JSONL record to SCORE_HISTORY_PATH.

    Fields written (23 total):
      checked_at        ISO-8601 UTC timestamp of this check run
      mode              "new" | "existing"
      path              article relative path (content/posts/...)
      title             article title string
      overall_judgement result status string (legacy alias of status)
      factual_score     0-100, or null when fact check was unavailable/failed
      freshness_score   0-100, or null (recorded but NOT used in pass/fail judgement)
      citation_coverage 0-100, or null (recorded but NOT used in pass/fail judgement)
      risk_score        0-100, or null
      critical          bool
      critical_level    "high" | "medium" | "" — critical の細分化レベル
      gemini_model      Gemini model name used (FACT_CHECK_GEMINI_MODEL env)
      workflow          GITHUB_WORKFLOW env value, or "local" if not in CI
      run_id            GITHUB_RUN_ID env value, or "local" if not in CI
      eval_id           UUID4 generated per evaluation call; primary key for repeat sets
      trigger           GITHUB_EVENT_NAME env value, or "manual"
      prompt_version    FACT_CHECK_PROMPT_VERSION constant; increment on prompt change
      status            execution status: "ok" | "fact_check_unavailable" | "failed_fact_check"
                        (scoring judgement pass/reject/etc. is in overall_judgement)
      article_hash      SHA256[:12] of article body (frontmatter excluded)
      unsupported_claims list of unsupported claim strings from Gemini evaluation
      sources           list of source dicts from Gemini evaluation
      error_detail      exception type+message (first 300 chars) on failure;
                        for JSON parse failures also includes raw response excerpt
                        ("parse_error[:300] | raw:raw_response[:300]"); null on success
      vote_group_id     UUID4 shared by all votes in a majority-vote group; "" for single-shot evals
      is_final_vote     true on the median-score record that determines the gate verdict;
                        false on raw individual votes; false for single-shot evals
      vote_count        total number of votes requested (1 for single-shot evals)
    """
    SCORE_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    scores = result.scores
    score_valid = result.score_valid
    exec_status = (
        result.status
        if result.status in {"fact_check_unavailable", "failed_fact_check"}
        else "ok"
    )
    record = {
        "checked_at": utc_now_iso(),
        "mode": result.mode,
        "path": result.path,
        "title": result.title,
        "overall_judgement": result.status,
        "factual_score": scores["factual_score"] if score_valid else None,
        "freshness_score": scores["freshness_score"] if score_valid else None,
        "citation_coverage": scores["citation_coverage"] if score_valid else None,
        "risk_score": scores["risk_score"] if score_valid else None,
        "critical": result.critical,
        "critical_level": result.critical_level,
        "gemini_model": result.gemini_model or _resolve_gemini_model(),
        "workflow": os.getenv("GITHUB_WORKFLOW", "local"),
        "run_id": os.getenv("GITHUB_RUN_ID", "local"),
        "eval_id": str(uuid.uuid4()),
        "trigger": os.getenv("GITHUB_EVENT_NAME", "manual"),
        "prompt_version": FACT_CHECK_PROMPT_VERSION,
        "status": exec_status,
        "article_hash": result.article_hash,
        "unsupported_claims": result.unsupported_claims,
        "sources": result.sources,
        "error_detail": result.error_detail,
        "vote_group_id": result.vote_group_id,
        "is_final_vote": result.is_final_vote,
        "vote_count": result.vote_count,
    }
    with SCORE_HISTORY_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    result.score_history_appended = True
    return True


def score_history_for_path(path: str) -> list[dict[str, Any]]:
    if not SCORE_HISTORY_PATH.exists():
        return []
    records: list[dict[str, Any]] = []
    with SCORE_HISTORY_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("path") == path:
                records.append(record)
    return records


def checked_recently(path: str) -> bool:
    records = score_history_for_path(path)
    if not records:
        return False
    raw = str(records[-1].get("checked_at", ""))
    if not raw:
        return False
    try:
        checked_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return False
    return datetime.now(timezone.utc) - checked_at < timedelta(hours=RECENTLY_CHECKED_SKIP_HOURS)


def latest_previous_history(result: FactCheckResult) -> dict[str, Any] | None:
    records = score_history_for_path(result.path)
    if not records:
        return None
    current = result.scores
    if len(records) >= 2:
        last = records[-1]
        last_factual = last.get("factual_score")
        last_risk = last.get("risk_score")
        if (
            last_factual is not None
            and last_risk is not None
            and int(last_factual) == current["factual_score"]
            and int(last_risk) == current["risk_score"]
            and last.get("overall_judgement") == result.status
        ):
            return records[-2]
    return records[-1]


def has_score_degraded(result: FactCheckResult) -> bool:
    previous = latest_previous_history(result)
    if not previous:
        return False
    current = result.scores
    prev_factual = previous.get("factual_score")
    prev_risk = previous.get("risk_score")
    if prev_factual is None or prev_risk is None:
        return False
    factual_drop = int(prev_factual) - current["factual_score"]
    risk_increase = current["risk_score"] - int(prev_risk)
    return factual_drop >= 10 or risk_increase >= 15


def save_evidence_sidecar(result: FactCheckResult) -> None:
    """Write per-article evidence sidecar to data/evidence/<stem>.json.

    Skips silently if the stem fails the safety check or any I/O error occurs.
    """
    stem = Path(result.path).stem
    if not _SAFE_STEM_RE.match(stem):
        print(
            f"[fact_check] WARNING: evidence sidecar skipped — unsafe stem {stem!r}",
            file=sys.stderr,
        )
        return
    try:
        sources_out = []
        for s in result.sources:
            rst = s.get("resolved_source_type", "unknown")
            sources_out.append({
                "final_url": s.get("final_url") or s.get("url", ""),
                "resolved_domain": s.get("resolved_domain"),
                "resolved_source_type": rst,
                "tool_match": bool(s.get("tool_match")),
                "title": s.get("title", ""),
                "is_unresolved": rst == "unresolved",
            })

        summary: dict[str, int] = {}
        for s in sources_out:
            key = s["resolved_source_type"]
            summary[key] = summary.get(key, 0) + 1

        sidecar = {
            "article_id": stem,
            "article_path": result.path,
            "tags": result.tags,
            "fact_checked_at": utc_now_iso(),
            "prompt_version": FACT_CHECK_PROMPT_VERSION,
            "sources": sources_out,
            "citation_mismatches": result.citation_mismatches,
            "evidence_summary": summary,
        }
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        out = EVIDENCE_DIR / f"{stem}.json"
        # 多層防御: resolve() 後に EVIDENCE_DIR 配下であることを最終確認
        out_resolved = out.resolve()
        if not out_resolved.is_relative_to(EVIDENCE_DIR.resolve()):
            print(
                f"[fact_check] WARNING: evidence sidecar skipped — resolved path {out_resolved}"
                f" is outside EVIDENCE_DIR",
                file=sys.stderr,
            )
            return
        out.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        print(
            f"[fact_check] WARNING: evidence sidecar write failed for {result.path!r}: {exc}",
            file=sys.stderr,
        )


def save_report(result: FactCheckResult, *, write_report: bool = True) -> FactCheckResult:
    """Score history は常に追記する。write_report=False でレポートファイル書き込みを抑制。

    baseline_fact_check.py など副作用を遮断したい呼び出し元は write_report=False を渡す。
    日次・fact_check_existing の既存経路はデフォルト(True)のままなので挙動は変わらない。
    """
    append_score_history(result)
    save_evidence_sidecar(result)
    if not write_report:
        return result
    subdir = "new_articles" if result.mode == "new" else "existing_articles"
    out_dir = REPORTS_DIR / subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / safe_report_name(Path(result.path))
    result.report_path = str(out.relative_to(BASE).as_posix())
    out.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    cleanup_reports()
    return result


def candidate_priority(result: FactCheckResult) -> str:
    scores = result.scores
    if result.critical or has_score_degraded(result) or scores["risk_score"] >= 70 or scores["factual_score"] < 55:
        return "high"
    if scores["freshness_score"] < MIN_FRESHNESS or scores["citation_coverage"] < MIN_CITATION:
        return "medium"
    return "low"


def merge_unique(old: list[Any], new: list[Any]) -> list[Any]:
    merged: list[Any] = []
    for item in old + new:
        if item and item not in merged:
            merged.append(item)
    return merged


def update_rewrite_candidates(results: list[FactCheckResult]) -> int:
    candidates = []
    if REWRITE_CANDIDATES_PATH.exists():
        try:
            loaded = json.loads(REWRITE_CANDIDATES_PATH.read_text(encoding="utf-8"))
            candidates = loaded if isinstance(loaded, list) else []
        except json.JSONDecodeError:
            candidates = []
    by_path = {item.get("path"): item for item in candidates if isinstance(item, dict) and item.get("path")}
    changed = 0

    for result in results:
        if result.passed or result.status in {"fact_check_unavailable", "failed_fact_check"}:
            continue
        existing = by_path.get(result.path, {})
        by_path[result.path] = {
            "path": result.path,
            "title": result.title,
            "reason": "; ".join(merge_unique([existing.get("reason", "")], result.reasons)).strip("; "),
            "scores": result.scores,
            "priority": candidate_priority(result),
            "required_actions": merge_unique(existing.get("required_actions", []), result.required_actions),
            "detected_at": result.detected_at,
        }
        changed += 1

    REWRITE_CANDIDATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    ordered = sorted(by_path.values(), key=lambda item: (priority_rank.get(item.get("priority"), 9), item.get("path", "")))
    REWRITE_CANDIDATES_PATH.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return changed


def latest_gsc_weights() -> dict[str, int]:
    weights: dict[str, int] = {}
    files = sorted((BASE / "reports" / "ga4").glob("gsc_*.json"), reverse=True)
    for path in files[:3]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows: list[Any]
        if isinstance(data, list):
            rows = data
        else:
            rows = data.get("rows") or data.get("bottlenecks") or []
        for row in rows:
            url = str(row.get("page") or row.get("url") or "")
            impressions = int(float(row.get("impressions", 0) or 0))
            match = re.search(r"/posts/([^/]+)/?", url)
            if match:
                weights[match.group(1)] = max(weights.get(match.group(1), 0), impressions)
    return weights


def load_unavailable_history() -> dict[str, Any]:
    if not UNAVAILABLE_HISTORY_PATH.exists():
        return {}
    try:
        data = json.loads(UNAVAILABLE_HISTORY_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def save_unavailable_history(data: dict[str, Any]) -> None:
    UNAVAILABLE_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    UNAVAILABLE_HISTORY_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def unavailable_recent(entry: dict[str, Any]) -> bool:
    raw = str(entry.get("last_unavailable_at", ""))
    if not raw:
        return False
    try:
        last = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return False
    return datetime.now(timezone.utc) - last < timedelta(hours=UNAVAILABLE_RETRY_AFTER_HOURS)


def record_unavailable_result(result: FactCheckResult) -> None:
    if result.status != "fact_check_unavailable":
        return
    data = load_unavailable_history()
    current = data.get(result.path, {}) if isinstance(data.get(result.path), dict) else {}
    data[result.path] = {
        "path": result.path,
        "last_unavailable_at": utc_now_iso(),
        "reason": "; ".join(result.reasons) or result.error,
        "count": int(current.get("count", 0)) + 1,
    }
    save_unavailable_history(data)


def prior_low_score(path: Path) -> int:
    pattern = f"*{path.stem}*.json"
    scores = []
    for report in (REPORTS_DIR / "existing_articles").glob(pattern):
        try:
            data = json.loads(report.read_text(encoding="utf-8"))
            s = data.get("scores", {})
            scores.append(int(s.get("factual_score", 100)) - int(s.get("risk_score", 0)))
        except Exception:
            continue
    return 40 if scores and min(scores) < 35 else 0


def select_pass_audit_sample() -> Path | None:
    """score_history.jsonl から直近 PASS_AUDIT_WINDOW_DAYS 日以内に pass した記事を
    1件ランダムに返す。直近 RECENTLY_CHECKED_SKIP_HOURS 以内に再チェック済みの記事は除外。
    対象ファイルが存在しない・条件を満たす記事がない場合は None。
    """
    if not PASS_AUDIT_ENABLED or not SCORE_HISTORY_PATH.exists():
        return None
    cutoff = datetime.now(timezone.utc) - timedelta(days=PASS_AUDIT_WINDOW_DAYS)
    candidates: list[Path] = []
    latest_pass: dict[str, str] = {}
    with SCORE_HISTORY_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("overall_judgement") != "pass":
                continue
            path_str = rec.get("path", "")
            checked_at = rec.get("checked_at", "")
            if not path_str or not checked_at:
                continue
            if path_str not in latest_pass or checked_at > latest_pass[path_str]:
                latest_pass[path_str] = checked_at
    for path_str, checked_at_str in latest_pass.items():
        try:
            checked_at = datetime.fromisoformat(checked_at_str.replace("Z", "+00:00"))
        except ValueError:
            continue
        if checked_at < cutoff:
            continue
        if checked_recently(path_str):
            continue
        full_path = BASE / path_str
        if full_path.exists():
            candidates.append(full_path)
    if not candidates:
        return None
    return random.choice(candidates)


def select_existing(limit: int) -> tuple[list[Path], int, int]:
    traffic = latest_gsc_weights()
    unavailable_history = load_unavailable_history()
    scored: list[tuple[int, Path]] = []
    skipped_recent_unavailable = 0
    skipped_recently_checked = 0
    today = date.today()
    for path in POSTS_DIR.glob("*.md"):
        rel_path = str(path.relative_to(BASE).as_posix())
        if checked_recently(rel_path):
            skipped_recently_checked += 1
            continue
        history_entry = unavailable_history.get(rel_path, {})
        if isinstance(history_entry, dict) and unavailable_recent(history_entry):
            skipped_recent_unavailable += 1
            continue
        content = path.read_text(encoding="utf-8")
        fm, body = split_frontmatter(content)
        if str(fm.get("draft", "")).lower() == "true":
            continue
        published = parse_date(fm.get("date")) or date.fromtimestamp(path.stat().st_mtime)
        updated = parse_date(fm.get("lastmod") or fm.get("updated")) or date.fromtimestamp(path.stat().st_mtime)
        age = max(0, (today - published).days)
        stale = max(0, (today - updated).days)
        title = extract_title(path, fm)
        priority = age + stale
        if is_high_change(title, body):
            priority += 180
        priority += min(200, traffic.get(path.stem, 0))
        if count_citations(body) < 2:
            priority += 80
        priority += prior_low_score(path)
        scored.append((priority, path))
    ranked = sorted(scored, key=lambda item: (item[0], str(item[1])), reverse=True)
    return [path for _, path in ranked[:limit]], skipped_recent_unavailable, skipped_recently_checked


def print_summary(
    results: list[FactCheckResult],
    mode: str,
    rewrite_updates: int = 0,
    stopped_due_to_unavailable_ratio: bool = False,
    skipped_recent_unavailable: int = 0,
    skipped_recently_checked: int = 0,
    selected_articles: list[str] | None = None,
) -> None:
    checked = len(results)
    passed = sum(1 for result in results if result.passed)
    needs_revision = sum(1 for result in results if result.status == "needs_revision")
    failed_fact_check = sum(1 for result in results if result.status == "failed_fact_check")
    reject = sum(1 for result in results if result.status == "reject")
    critical = sum(1 for result in results if result.critical)
    unavailable = sum(1 for result in results if result.status == "fact_check_unavailable")
    gemini_quota_errors = sum(1 for result in results if result.gemini_error_category == "quota")
    gemini_model_errors = sum(1 for result in results if result.gemini_error_category == "model")
    gemini_api_errors = sum(1 for result in results if result.gemini_error_category == "api")
    gemini_timeout_errors = sum(1 for result in results if result.gemini_error_category == "timeout")
    history_appended = sum(1 for result in results if result.score_history_appended)
    url_checked = sum(result.url_checked for result in results)
    url_skipped = sum(result.url_skipped for result in results)
    url_invalid = sum(result.url_invalid for result in results)
    total_input_chars = sum(result.fact_check_input_chars for result in results)
    avg_input_chars = round(total_input_chars / checked) if checked else 0
    max_input_chars = max((result.fact_check_input_chars for result in results), default=0)
    selected_article = ",".join(selected_articles or [result.path for result in results]) or "-"
    print(
        "[fact-check-summary] "
        f"mode={mode} checked={checked} pass={passed} needs_revision={needs_revision} "
        f"selected_article={selected_article} "
        f"failed_fact_check={failed_fact_check} reject={reject} critical={critical} rewrite_candidate_updates={rewrite_updates} "
        f"fact_check_unavailable={unavailable} gemini_quota_errors={gemini_quota_errors} "
        f"gemini_model_errors={gemini_model_errors} gemini_api_errors={gemini_api_errors} "
        f"gemini_timeout_errors={gemini_timeout_errors} "
        f"score_history_appended={history_appended} url_checked={url_checked} "
        f"url_skipped={url_skipped} url_invalid={url_invalid} "
        f"avg_fact_check_input_chars={avg_input_chars} max_fact_check_input_chars={max_input_chars} "
        f"delay_seconds={GEMINI_DELAY_SECONDS:g} timeout_cooldown_seconds={GEMINI_TIMEOUT_COOLDOWN_SECONDS:g} "
        f"skipped_recently_checked={skipped_recently_checked} "
        f"skipped_recent_unavailable={skipped_recent_unavailable} "
        f"stopped_due_to_unavailable_ratio={1 if stopped_due_to_unavailable_ratio else 0}"
    )
    for result in results:
        s = result.scores
        score_text = (
            "score_valid=false"
            if not result.score_valid
            else (
                f"factual={s['factual_score']} freshness={s['freshness_score']} "
                f"citation={s['citation_coverage']} risk={s['risk_score']}"
            )
        )
        print(
            f"[fact-check] {result.status.upper()} {result.path} "
            f"{score_text} "
            f"sources={len(result.sources)} unsupported={len(result.unsupported_claims)} "
            f"report={result.report_path}"
        )
        if mode == "existing" and result.critical:
            level = result.critical_level or "high"
            print(f"::warning::Critical[{level}] misinformation risk detected in existing article: {result.path}")
        if (
            mode == "existing"
            and result.score_valid
            and result.scores["freshness_score"] < MIN_FRESHNESS
        ):
            print(
                f"::warning::Low freshness score ({result.scores['freshness_score']}) "
                f"in existing article: {result.path}"
            )


def resolve_target_path(target_path: str | None) -> Path | None:
    if not target_path:
        return None
    path = Path(target_path)
    if not path.is_absolute():
        path = BASE / path
    if not path.exists():
        raise FileNotFoundError(f"target_path not found: {target_path}")
    return path


def check_existing(limit: int, target_path: str | None = None) -> list[FactCheckResult]:
    results: list[FactCheckResult] = []
    stopped = False
    skipped_recent_unavailable = 0
    skipped_recently_checked = 0
    target = resolve_target_path(target_path)
    if target:
        targets = [target]
        unavailable_stop_count = 1
    else:
        unavailable_stop_count = max(1, math.ceil(limit * MAX_UNAVAILABLE_RATIO))
        targets, skipped_recent_unavailable, skipped_recently_checked = select_existing(limit)
        audit_sample = select_pass_audit_sample()
        if audit_sample is not None and audit_sample not in targets:
            targets = list(targets) + [audit_sample]
            unavailable_stop_count = max(1, math.ceil(len(targets) * MAX_UNAVAILABLE_RATIO))
    for index, path in enumerate(targets):
        if index > 0 and GEMINI_DELAY_SECONDS > 0:
            time.sleep(GEMINI_DELAY_SECONDS)
        result = evaluate_content(path.relative_to(BASE), path.read_text(encoding="utf-8"), "existing")
        results.append(save_report(result))
        record_unavailable_result(result)
        if result.gemini_error_category == "timeout" and GEMINI_TIMEOUT_COOLDOWN_SECONDS > 0:
            time.sleep(GEMINI_TIMEOUT_COOLDOWN_SECONDS)
        unavailable = sum(1 for item in results if item.status == "fact_check_unavailable")
        if unavailable >= unavailable_stop_count:
            stopped = True
            break
    rewrite_updates = update_rewrite_candidates(results)
    print_summary(
        results,
        "existing",
        rewrite_updates,
        stopped,
        skipped_recent_unavailable,
        skipped_recently_checked,
        [str(path.relative_to(BASE).as_posix()) for path in targets],
    )
    return results


def check_new_paths(paths: list[Path]) -> list[FactCheckResult]:
    results: list[FactCheckResult] = []
    for raw_path in paths:
        path = raw_path if raw_path.is_absolute() else BASE / raw_path
        rel = path.relative_to(BASE) if path.is_relative_to(BASE) else path
        result = evaluate_content(rel, path.read_text(encoding="utf-8"), "new")
        results.append(save_report(result))
    print_summary(results, "new")
    return results


def evaluate_new_article(path: Path, content: str) -> FactCheckResult:
    """New-article gate with optional majority-vote scoring.

    When FACT_CHECK_VOTE_COUNT >= 2, runs evaluate_content N times and adopts
    per-axis median scores to reduce flip rate. Each raw vote is saved to JSONL
    with is_final_vote=False; the median-derived final result is saved with
    is_final_vote=True. Both share the same vote_group_id.

    When FACT_CHECK_VOTE_COUNT == 1 (or any unavailable result makes valid
    votes < 2), falls back to single-shot behaviour.
    """
    import statistics
    import dataclasses

    n_votes = FACT_CHECK_VOTE_COUNT
    if n_votes <= 1:
        result = evaluate_content(path, content, "new")
        return save_report(result)

    group_id = str(uuid.uuid4())
    raw: list[FactCheckResult] = []
    for _ in range(n_votes):
        r = evaluate_content(path, content, "new")
        r.vote_group_id = group_id
        r.is_final_vote = False
        r.vote_count = n_votes
        save_report(r)
        raw.append(r)

    valid = [r for r in raw if r.score_valid]
    if len(valid) < 2:
        # Not enough valid votes to take a meaningful median; return last raw result
        last = raw[-1]
        last.is_final_vote = True
        return last

    # Per-axis median (integer)
    median_scores: dict[str, int] = {
        key: int(statistics.median(r.scores[key] for r in valid))
        for key in SCORE_KEYS
    }

    # Recompute gate verdict from median scores (3-axis: factual + risk + citation)
    m_passed = (
        median_scores["factual_score"] >= MIN_FACTUAL
        and median_scores["risk_score"] <= MAX_RISK
        and median_scores["citation_coverage"] >= MIN_CITATION
    )
    if median_scores["risk_score"] >= CRITICAL_RISK:
        m_critical_level = "high"
    elif (
        any(r.critical_level == "medium" for r in valid)
        and median_scores["factual_score"] < 55
    ):
        m_critical_level = "medium"
    else:
        m_critical_level = ""
    m_critical = m_critical_level != ""

    if m_critical:
        m_status = "critical"
    elif not m_passed:
        m_status = "reject"
    else:
        m_status = "pass"

    # Use the vote whose factual_score is closest to the median as the narrative template
    template = min(valid, key=lambda r: abs(r.scores["factual_score"] - median_scores["factual_score"]))
    citation_mismatches_by_url: dict[str, dict[str, str]] = {}
    for result in valid:
        for mismatch in result.citation_mismatches:
            url = str(mismatch.get("url", "")).strip()
            if url and url not in citation_mismatches_by_url:
                citation_mismatches_by_url[url] = mismatch

    final = dataclasses.replace(
        template,
        scores=median_scores,
        passed=m_passed,
        critical=m_critical,
        critical_level=m_critical_level,
        status=m_status,
        citation_mismatches=list(citation_mismatches_by_url.values()),
        vote_group_id=group_id,
        is_final_vote=True,
        vote_count=n_votes,
        score_history_appended=False,  # ensure save_report appends fresh
    )

    # Structured vote log
    f_vals = [r.scores["factual_score"] for r in valid]
    r_vals = [r.scores["risk_score"] for r in valid]
    print(
        f"[vote] {path} "
        f"factual={f_vals}→median={median_scores['factual_score']} "
        f"risk={r_vals}→median={median_scores['risk_score']} "
        f"verdict={'pass' if m_passed else 'fail'}"
    )

    return save_report(final)


def new_article_key(slug: str, row: dict[str, Any]) -> str:
    source = {
        "slug": slug,
        "tool": row.get("tool", ""),
        "status_code": row.get("status_code", ""),
        "official_meaning": row.get("official_meaning", ""),
    }
    return hashlib.sha1(json.dumps(source, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def load_new_article_failures() -> dict[str, Any]:
    if not NEW_ARTICLE_FAILURES_PATH.exists():
        return {}
    try:
        data = json.loads(NEW_ARTICLE_FAILURES_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def save_new_article_failures(data: dict[str, Any]) -> None:
    NEW_ARTICLE_FAILURES_PATH.parent.mkdir(parents=True, exist_ok=True)
    NEW_ARTICLE_FAILURES_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def record_new_article_failure(slug: str, row: dict[str, Any], result: FactCheckResult) -> dict[str, Any]:
    data = load_new_article_failures()
    key = new_article_key(slug, row)
    current = data.get(key, {}) if isinstance(data.get(key), dict) else {}
    failure_count = int(current.get("failure_count", 0)) + 1
    status = "needs_manual_review" if failure_count >= NEW_ARTICLE_MAX_RETRIES else "retry"
    entry = {
        "slug": slug,
        "tool": row.get("tool", ""),
        "status_code": row.get("status_code", ""),
        "failure_count": failure_count,
        "status": status,
        "last_failure_reason": "; ".join(result.reasons) or result.status,
        "last_scores": result.scores,
        "last_checked_at": result.detected_at,
        "report_path": result.report_path,
    }
    data[key] = entry
    save_new_article_failures(data)
    return entry


def clear_new_article_failure(slug: str, row: dict[str, Any]) -> None:
    data = load_new_article_failures()
    key = new_article_key(slug, row)
    if key in data:
        del data[key]
        save_new_article_failures(data)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["new", "existing"], default="existing")
    parser.add_argument("--limit", type=int, default=EXISTING_LIMIT)
    parser.add_argument("--target-path", default="")
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()

    if args.mode == "existing":
        results = check_existing(args.limit, args.target_path)
        if FAIL_ON_EXISTING_CRITICAL and any(result.critical for result in results):
            return 1
        return 0

    if not args.paths:
        print("[fact-check] --mode new requires one or more paths", file=sys.stderr)
        return 2
    results = check_new_paths([Path(p) for p in args.paths])
    if any(result.critical for result in results):
        return 1
    if any(not result.passed for result in results):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
