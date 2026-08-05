#!/usr/bin/env python3
"""Anthropic API で ErrorLog 記事を1件生成し、draft として保存する。

既存の公開処理は行わない。公開は scripts/publish_article.py に任せる。

使用例:
  python scripts/anthropic_generate_article.py --queue-index 0 --slug trial_gitlab_502 --dry-run
  python scripts/anthropic_generate_article.py --queue-index 0 --slug trial_gitlab_502 --run-quality
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


BASE = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = BASE / "config" / "anthropic_article_generation.yml"
API_TIMEOUT_SECONDS = 1200
ARTICLE_SPEC = BASE / "docs" / "article_spec.md"
DISCLAIMER = (
    "\n\n---\n\n"
    "*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。"
    "ソフトウェアの仕様は予告なく変更されることがあります。"
    "最新の情報は各ツールの公式サポートページをご確認ください。"
    "本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*"
)

TOOL_TAGS = {
    "docker_compose": "Docker Compose",
    "docker": "Docker",
    "aws_s3": "AWS S3",
    "aws_lambda": "AWS Lambda",
    "aws": "AWS",
    "firebase": "Firebase",
    "github_actions": "GitHub Actions",
    "github_api": "GitHub API",
    "openai_api": "OpenAI API",
    "kubernetes": "Kubernetes",
    "nginx": "Nginx",
    "stripe": "Stripe",
    "slack": "Slack",
    "gcp": "GCP",
    "podman": "Podman",
    "minikube": "Minikube",
    "azure": "Azure",
    "supabase": "Supabase",
    "vercel": "Vercel",
    "terraform": "Terraform",
    "ansible": "Ansible",
    "gitlab": "GitLab",
    "bitbucket": "Bitbucket",
    "postman": "Postman",
    "jenkins": "Jenkins",
    "circleci": "CircleCI",
    "prometheus": "Prometheus",
    "grafana": "Grafana",
    "datadog": "Datadog",
}

DEFAULT_EVIDENCE_URLS = {
    "Kubernetes": [
        "https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/",
        "https://kubernetes.io/docs/concepts/extend-kubernetes/compute-storage-net/network-plugins/",
        "https://kubernetes.io/docs/setup/production-environment/container-runtimes/",
        "https://github.com/containerd/containerd/blob/main/docs/cri/config.md",
    ],
}

_BEFORE_LABEL_RE = re.compile(
    r"(?m)^(?:#{1,4}[ \t]+|\*\*)?(?:Before|before|修正前|エラーが起きる[^ \t\n（(]*)"
    r"(?:[ \t]*[（(][^）)\n]*[）)])?[ \t]*[：:]?[ \t]*\*{0,2}[ \t]*$"
)
_AFTER_LABEL_RE = re.compile(
    r"(?m)^(?:#{1,4}[ \t]+|\*\*)?(?:After|after|修正後[^ \t\n（(]*)"
    r"(?:[ \t]*[（(][^）)\n]*[）)])?[ \t]*[：:]?[ \t]*\*{0,2}[ \t]*$"
)
_TRAILING_DISCLAIMER_RE = re.compile(r"\n*---\n*\*免責事項[\s\S]*$")
_INTRO_BOILERPLATE_RE = re.compile(
    r"(?m)(^|[。！？]\s*)([^。\n]{1,80}?\s+\d{3}\s*エラーの原因と解決策を解説します。)"
)
_INTERNAL_NOTE_PREFIX_RE = re.compile(
    r"^(?:まず本日の日付を確認|検索結果が空|生の応答を確認|公式仕様を照合|調査を開始)[^\n]*\n+"
)


def normalize_before_after(text: str) -> str:
    parts = re.split(r"(```[\s\S]*?```)", text)
    for i, part in enumerate(parts):
        if i % 2 == 0:
            part = _BEFORE_LABEL_RE.sub("**Before（エラーが起きるコード）：**", part)
            part = _AFTER_LABEL_RE.sub("**After（修正後）：**", part)
            parts[i] = part
    return "".join(parts)


def strip_trailing_disclaimer(text: str) -> str:
    while True:
        new_text = _TRAILING_DISCLAIMER_RE.sub("", text).rstrip()
        if new_text == text.rstrip():
            return new_text
        text = new_text


def strip_intro_boilerplate(text: str) -> str:
    while True:
        new_text = _INTRO_BOILERPLATE_RE.sub(lambda m: m.group(1), text)
        new_text = re.sub(r"[ \t]+\n", "\n", new_text)
        if new_text == text:
            return text
        text = new_text


def strip_internal_notes(text: str) -> str:
    while True:
        new_text = _INTERNAL_NOTE_PREFIX_RE.sub("", text.lstrip())
        if new_text == text.lstrip():
            return new_text
        text = new_text


def build_description(row: dict[str, str], tool: str, code: str) -> str:
    meaning = row["official_meaning"].strip().rstrip("。．")
    if len(meaning) <= 90:
        return meaning + "。"
    summary = meaning.split("、")[0].split("。")[0].strip()
    if not summary:
        summary = f"{tool} の {code}"
    return f"{summary}。実際のメッセージ、設定、実行環境を順に確認して原因を切り分けます。"


def generate_methodology_note(row: dict[str, str]) -> str:
    source_urls = [u.strip() for u in (row.get("source_urls") or "").split("|") if u.strip()]
    if not source_urls:
        return ""
    return (
        "\n\n> **調査について**　この記事の解決策は、公式文書・実装・Issue・公開報告を"
        "照合し、実効性の高いものを整理したものです。\n"
    )


def fetch_text(url: str) -> tuple[str, str]:
    req = urllib.request.Request(url, headers={"user-agent": "errorlog-anthropic-generator/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            raw = res.read(1_000_000)
            content_type = res.headers.get("content-type", "")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"{type(exc).__name__}: {exc}") from exc
    text = raw.decode("utf-8", errors="replace")
    if "html" in content_type.lower() or text.lstrip().startswith("<"):
        parser = TextExtractor()
        parser.feed(text)
        return parser.title, " ".join(parser.parts)
    first = text.splitlines()[0].strip() if text.splitlines() else ""
    return first[:120], text


def default_evidence_urls(tool: str) -> list[str]:
    return DEFAULT_EVIDENCE_URLS.get(tool, [])


def build_evidence(
    row: dict[str, str],
    evidence_urls: list[str],
    *,
    fetch_enabled: bool,
) -> dict[str, Any]:
    urls = evidence_urls or [u.strip() for u in (row.get("source_urls") or "").split("|") if u.strip()]
    if not urls:
        urls = default_evidence_urls(row["tool"].strip())
    claims = [
        {
            "claim": "FailedCreatePodSandbox は kubelet が Pod sandbox 作成に失敗した段階のイベントで、アプリコンテナ起動前の問題です。",
            "source_urls": ["https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/"],
        },
        {
            "claim": "Pod sandbox 作成失敗では CNI プラグインやネットワーク設定を優先して確認します。",
            "source_urls": ["https://kubernetes.io/docs/concepts/extend-kubernetes/compute-storage-net/network-plugins/"],
        },
        {
            "claim": "container runtime と pause/sandbox image の設定は sandbox 作成失敗の切り分け対象です。",
            "source_urls": [
                "https://kubernetes.io/docs/setup/production-environment/container-runtimes/",
                "https://github.com/containerd/containerd/blob/main/docs/cri/config.md",
            ],
        },
    ]
    sources: list[dict[str, Any]] = []
    for url in dict.fromkeys(urls):
        item: dict[str, Any] = {"url": url, "title": "", "excerpt": "", "status": "not_fetched"}
        if fetch_enabled:
            try:
                title, text = fetch_text(url)
                item.update({
                    "title": title,
                    "excerpt": re.sub(r"\s+", " ", text).strip()[:1200],
                    "status": "fetched",
                })
            except RuntimeError as exc:
                item.update({"status": "fetch_failed", "error": str(exc)})
        sources.append(item)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tool": row["tool"].strip(),
        "error_code": row["status_code"].strip(),
        "sources": sources,
        "claim_source_map": claims,
    }


@dataclass(frozen=True)
class GenerationResult:
    article: str
    response_json: dict[str, Any]
    usage: dict[str, Any]
    cost: dict[str, Any]


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self._in_title = False
        self._skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "nav", "footer", "header"}:
            self._skip += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "nav", "footer", "header"} and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        text = re.sub(r"\s+", " ", data).strip()
        if not text:
            return
        if self._in_title:
            self.title = (self.title + " " + text).strip()
        elif self._skip == 0:
            self.parts.append(text)


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"エラー: 設定ファイルが見つかりません: {path}")
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text) if yaml is not None else load_strict_yaml_subset(text, path)
    if not isinstance(data, dict):
        raise SystemExit(f"エラー: 設定ファイルのルートが辞書ではありません: {path}")
    return data


def parse_scalar(value: str, path: Path, line_no: int) -> Any:
    value = value.strip()
    if value == "[]":
        return []
    if value in {"true", "false"}:
        return value == "true"
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    if value:
        return value
    raise SystemExit(f"エラー: {path}:{line_no} の値を解析できません。")


def load_strict_yaml_subset(text: str, path: Path) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for line_no, raw_line in enumerate(text.splitlines(), 1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent % 2 != 0:
            raise SystemExit(f"エラー: {path}:{line_no} のインデントは2スペース単位で指定してください。")
        line = raw_line.strip()
        if ":" not in line:
            raise SystemExit(f"エラー: {path}:{line_no} は key: value 形式ではありません。")
        key, value = line.split(":", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]+", key):
            raise SystemExit(f"エラー: {path}:{line_no} のキー名が不正です: {key}")
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            raise SystemExit(f"エラー: {path}:{line_no} の階層を解析できません。")
        parent = stack[-1][1]
        if value.strip() == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = parse_scalar(value, path, line_no)
    return root


def require_dict(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise SystemExit(f"エラー: config の {key} が辞書ではありません。")
    return value


def model_config(config: dict[str, Any]) -> dict[str, Any]:
    return require_dict(config, "anthropic")


def pricing_config(config: dict[str, Any]) -> dict[str, Any]:
    return require_dict(model_config(config), "pricing")


def budget_config(config: dict[str, Any]) -> dict[str, Any]:
    return require_dict(model_config(config), "budget")


def apply_runtime_overrides(config: dict[str, Any], args: argparse.Namespace) -> None:
    cfg = model_config(config)
    if args.max_tokens is not None:
        if args.max_tokens < 1000:
            raise SystemExit("エラー: --max-tokens は 1000 以上で指定してください。")
        cfg["max_tokens"] = args.max_tokens
    if args.web_search_max_uses is not None:
        if args.web_search_max_uses < 0:
            raise SystemExit("エラー: --web-search-max-uses は 0 以上で指定してください。")
        web_search = require_dict(cfg, "web_search")
        web_search["max_uses"] = args.web_search_max_uses
        web_search["enabled"] = args.web_search_max_uses > 0


def load_queue_row(queue_path: Path, queue_index: int) -> dict[str, str]:
    if not queue_path.exists():
        raise SystemExit(f"エラー: queue.csv が見つかりません: {queue_path}")
    with queue_path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if queue_index < 0 or queue_index >= len(rows):
        raise SystemExit(f"エラー: --queue-index が範囲外です: {queue_index} / rows={len(rows)}")
    row = rows[queue_index]
    required = ("tool", "status_code", "official_meaning", "causes", "solutions")
    missing = [name for name in required if not row.get(name, "").strip()]
    if missing:
        raise SystemExit("エラー: queue 行に必須値がありません: " + ", ".join(missing))
    return row


def manual_row(tool: str, error_code: str, official_meaning: str, causes: str, solutions: str) -> dict[str, str]:
    required = {
        "--tool": tool,
        "--error-code": error_code,
        "--official-meaning": official_meaning,
        "--causes": causes,
        "--solutions": solutions,
    }
    missing = [name for name, value in required.items() if not value.strip()]
    if missing:
        raise SystemExit("エラー: 手動テーマ指定には次の引数が必要です: " + ", ".join(missing))
    return {
        "tool": tool,
        "status_code": error_code,
        "official_meaning": official_meaning,
        "causes": causes,
        "solutions": solutions,
        "source_urls": "",
        "reported_versions": "",
        "actual_error_messages": "",
        "alternatives": "",
    }


def safe_slug(value: str) -> str:
    slug = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9_][a-z0-9_-]*", slug):
        raise SystemExit("エラー: --slug は英小文字/数字/_/- のみで指定してください。")
    return slug


def tags_for_tool(tool: str, slug: str) -> list[str]:
    stem = slug.lower()
    for prefix, label in TOOL_TAGS.items():
        if stem.startswith(prefix):
            return [label]
    return [tool]


def urgency_from_code(code: str) -> str:
    return "high" if code.startswith("5") or code in {"429", "408"} else "medium"


def json_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def build_research_prompt(
    row: dict[str, str],
    slug: str,
    editorial_context: str,
    editorial_context_meta: str,
    article_spec: str,
    evidence: dict[str, Any] | None = None,
) -> str:
    source_urls = [u.strip() for u in (row.get("source_urls") or "").split("|") if u.strip()]
    parts = [
        "ErrorLogの記事を書く前段として、調査だけを行ってください。記事本文は書かないでください。",
        "最初に編集コンテキストを読み、その判断基準に従ってからWeb検索を開始してください。",
        "",
        "## ErrorLog編集コンテキスト",
        editorial_context,
        "",
        "## 編集コンテキストのメタ情報",
        editorial_context_meta,
        "",
        "## 共通記事仕様",
        article_spec,
        "",
        "## 調査対象",
        f"- slug: {slug}",
        f"- tool: {row['tool'].strip()}",
        f"- status_code: {row['status_code'].strip()}",
        f"- official_meaning: {row['official_meaning'].strip()}",
        f"- causes: {row['causes'].strip()}",
        f"- solutions: {row['solutions'].strip()}",
    ]
    if source_urls:
        parts.extend(["- supplied_source_urls:", *[f"  - {url}" for url in source_urls]])
    if evidence:
        parts.extend(["", "## 取得済みevidence", json.dumps(evidence, ensure_ascii=False, indent=2)])
    parts.extend([
        "",
        "## 調査レポートの必須項目",
        "- 記事の対象範囲と既存記事との境界",
        "- エラーを生成するシステム・コンポーネント・処理段階",
        "- 主張ごとの根拠URLと、根拠内で確認した内容",
        "- 原因ごとの判別条件、確認方法、安全な対処",
        "- 似ているが別のエラーとの判別方法",
        "- Editor's Noteに使える実在の記録（日付・状態・対象バージョンを含む）",
        "- 未確認事項と、記事に書いてはいけない事項",
        "",
        "Markdownの調査レポートだけを出力してください。完成記事、front matter、前置き、自己評価は禁止です。",
    ])
    return "\n".join(parts)


def build_user_prompt(
    row: dict[str, str],
    slug: str,
    editorial_context: str,
    editorial_context_meta: str,
    rules: str,
    article_spec: str,
    research_report: str,
    evidence: dict[str, Any] | None = None,
) -> str:
    tool = row["tool"].strip()
    code = row["status_code"].strip()
    source_urls = [u.strip() for u in (row.get("source_urls") or "").split("|") if u.strip()]
    reported_vers = [v.strip() for v in (row.get("reported_versions") or "").split("|") if v.strip()]
    actual_msgs = [m.strip() for m in (row.get("actual_error_messages") or "").split("|") if m.strip()]
    alternatives = [a.strip() for a in (row.get("alternatives") or "").split("|") if a.strip()]

    parts = [
        "以下の queue 情報をもとに ErrorLog の下書き記事を1件生成してください。",
        "",
        "## 指示の優先順位",
        "1. このプロンプト末尾の『重要な出力条件』",
        "2. 『現在のAPI生成ルール』",
        "3. 『ErrorLog編集コンテキスト』",
        "4. 『共通記事仕様』",
        "競合時は上位を優先してください。特に下書き生成では draft: true を必須とします。",
        "",
        "## ErrorLog編集コンテキスト",
        editorial_context,
        "",
        "## 編集コンテキストのメタ情報",
        editorial_context_meta,
        "",
        "## 現在のAPI生成ルール",
        rules,
        "",
        "## 共通記事仕様",
        article_spec,
        "",
        "## 事前調査レポート",
        research_report,
        "",
        "このレポートにない事実を推測で補わないでください。追加のWeb検索は行わず、未確認事項は本文へ含めないでください。",
        "",
        "## 生成対象",
        f"- slug: {slug}",
        f"- title: {tool} の {code} エラー：原因と解決策",
        f"- tool: {tool}",
        f"- status_code: {code}",
        f"- official_meaning: {row['official_meaning'].strip()}",
        "- causes:",
        *[f"  - {c.strip()}" for c in row["causes"].split("|") if c.strip()],
        "- solutions:",
        *[f"  - {s.strip()}" for s in row["solutions"].split("|") if s.strip()],
    ]
    if source_urls:
        parts.extend(["- source_urls:", *[f"  - {u}" for u in source_urls]])
    if reported_vers:
        parts.append("- reported_versions: " + ", ".join(reported_vers))
    if actual_msgs:
        parts.extend(["- actual_error_messages:", *[f"  - {m}" for m in actual_msgs]])
    if alternatives:
        parts.append("- alternatives: " + ", ".join(alternatives))
    if evidence:
        parts.extend(["", "## 確認済み evidence（URL と主張の対応）"])
        for source in evidence.get("sources", []):
            if not isinstance(source, dict):
                continue
            parts.append(f"- URL: {source.get('url', '')}")
            if source.get("title"):
                parts.append(f"  title: {source.get('title')}")
            if source.get("excerpt"):
                parts.append(f"  excerpt: {source.get('excerpt')}")
        parts.append("")
        parts.append("## claim_source_map")
        for item in evidence.get("claim_source_map", []):
            if not isinstance(item, dict):
                continue
            parts.append(f"- claim: {item.get('claim', '')}")
            for url in item.get("source_urls", []):
                parts.append(f"  - {url}")
    parts.extend([
        "",
        "## 重要な出力条件",
        "- Markdown だけを出力してください。前置き、説明、コードフェンスでの囲みは禁止です。",
        "- front matter の draft は true のままにしてください。",
        "- date は今日の日付を YYYY-MM-DD で書いてください。",
        "- 根拠不足の内容は書かず、確認方法へ誘導してください。",
        "- Editor's Note は、上記 claim_source_map の URL と主張だけを根拠にしてください。",
    ])
    return "\n".join(parts)


def response_to_dict(message: Any) -> dict[str, Any]:
    if hasattr(message, "model_dump"):
        return message.model_dump()
    if hasattr(message, "dict"):
        return message.dict()
    raise SystemExit("エラー: Anthropic SDK の response を JSON 化できません。")


def post_anthropic_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("エラー: ANTHROPIC_API_KEY が設定されていません。")
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.anthropic.com/v1/{path}",
        data=data,
        headers={
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
            "x-api-key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=API_TIMEOUT_SECONDS) as res:
            body = res.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"エラー: Anthropic API HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"エラー: Anthropic API に接続できません: {exc}") from exc
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise SystemExit("エラー: Anthropic API response がオブジェクトではありません。")
    return parsed


def text_from_response(response_json: dict[str, Any]) -> str:
    content = response_json.get("content")
    if not isinstance(content, list):
        raise SystemExit("エラー: Anthropic response.content が配列ではありません。")
    texts = [block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"]
    article = "\n".join(t for t in texts if t).strip()
    if not article:
        raise SystemExit("エラー: Anthropic response に text content がありません。")
    return article


def usage_from_response(response_json: dict[str, Any]) -> dict[str, Any]:
    usage = response_json.get("usage")
    if not isinstance(usage, dict):
        raise SystemExit("エラー: Anthropic response.usage がありません。")
    return usage


def extract_web_search_requests(usage: dict[str, Any]) -> int:
    server_tool_use = usage.get("server_tool_use") if isinstance(usage.get("server_tool_use"), dict) else {}
    return int(server_tool_use.get("web_search_requests") or 0)


def cost_breakdown(
    pricing: dict[str, Any],
    *,
    model: str,
    effort: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
    web_search_requests: int = 0,
    estimated_cost_usd: float | None = None,
    maximum_cost_usd: float | None = None,
) -> dict[str, Any]:
    input_cost = input_tokens / 1_000_000 * float(pricing["input_mtok_usd"])
    output_cost = output_tokens / 1_000_000 * float(pricing["output_mtok_usd"])
    cache_cost = (
        cache_creation_input_tokens / 1_000_000 * float(pricing["cache_write_5m_mtok_usd"])
        + cache_read_input_tokens / 1_000_000 * float(pricing["cache_read_mtok_usd"])
    )
    web_cost = web_search_requests * float(pricing["web_search_request_usd"])
    total = input_cost + output_cost + cache_cost + web_cost
    return {
        "model": model,
        "effort": effort,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_input_tokens": cache_creation_input_tokens,
        "cache_read_input_tokens": cache_read_input_tokens,
        "web_search_requests": web_search_requests,
        "input_cost_usd": round(input_cost, 6),
        "output_cost_usd": round(output_cost, 6),
        "cache_cost_usd": round(cache_cost, 6),
        "web_search_cost_usd": round(web_cost, 6),
        "total_cost_usd": round(total, 6),
        "estimated_cost_usd": round(estimated_cost_usd if estimated_cost_usd is not None else total, 6),
        "maximum_cost_usd": round(maximum_cost_usd if maximum_cost_usd is not None else total, 6),
    }


def usage_cost(config: dict[str, Any], usage: dict[str, Any], estimated: dict[str, Any], maximum: dict[str, Any]) -> dict[str, Any]:
    cfg = model_config(config)
    return cost_breakdown(
        pricing_config(config),
        model=str(cfg["model"]),
        effort=str(cfg.get("effort") or ""),
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        cache_creation_input_tokens=int(usage.get("cache_creation_input_tokens") or 0),
        cache_read_input_tokens=int(usage.get("cache_read_input_tokens") or 0),
        web_search_requests=extract_web_search_requests(usage),
        estimated_cost_usd=float(estimated["total_cost_usd"]),
        maximum_cost_usd=float(maximum["total_cost_usd"]),
    )


def combine_phase_costs(research: dict[str, Any], writing: dict[str, Any]) -> dict[str, Any]:
    additive_fields = (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
        "web_search_requests",
        "input_cost_usd",
        "output_cost_usd",
        "cache_cost_usd",
        "web_search_cost_usd",
        "total_cost_usd",
        "estimated_cost_usd",
        "maximum_cost_usd",
    )
    combined: dict[str, Any] = {
        "model": writing["model"],
        "effort": writing["effort"],
    }
    for field in additive_fields:
        value = float(research[field]) + float(writing[field])
        combined[field] = int(value) if field.endswith("tokens") or field == "web_search_requests" else round(value, 6)
    combined["phases"] = {"research": research, "writing": writing}
    return combined


def estimate_scenario(config: dict[str, Any], input_tokens: int, output_tokens: int, web_search_requests: int) -> dict[str, Any]:
    cfg = model_config(config)
    return cost_breakdown(
        pricing_config(config),
        model=str(cfg["model"]),
        effort=str(cfg.get("effort") or ""),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        web_search_requests=web_search_requests,
    )


def print_cost(label: str, cost: dict[str, Any]) -> None:
    print(
        f"{label}: input={cost['input_tokens']} output={cost['output_tokens']} "
        f"web={cost['web_search_requests']} total=${cost['total_cost_usd']:.6f} "
        f"(input=${cost['input_cost_usd']:.6f}, output=${cost['output_cost_usd']:.6f}, "
        f"cache=${cost['cache_cost_usd']:.6f}, web=${cost['web_search_cost_usd']:.6f})"
    )


def print_requested_cost_table(config: dict[str, Any]) -> None:
    cfg = model_config(config)
    configured_max_tokens = int(cfg["max_tokens"])
    output_scenarios = [10000, 15000]
    if configured_max_tokens not in output_scenarios:
        output_scenarios.append(configured_max_tokens)
    print(f"\n料金表（{cfg['model']} {cfg['effort']} / キャッシュなし）")
    print("| input_tokens | output_tokens | web_search | total_usd | input | output | web |")
    print("|---:|---:|---:|---:|---:|---:|---:|")
    for input_tokens in (30000, 60000):
        for output_tokens in output_scenarios:
            for web_search_requests in (5, 10):
                cost = estimate_scenario(config, input_tokens, output_tokens, web_search_requests)
                print(
                    f"| {input_tokens} | {output_tokens} | {web_search_requests} | "
                    f"${cost['total_cost_usd']:.4f} | ${cost['input_cost_usd']:.4f} | "
                    f"${cost['output_cost_usd']:.4f} | ${cost['web_search_cost_usd']:.4f} |"
                )


def build_tools(web_search: dict[str, Any]) -> list[dict[str, Any]]:
    if not web_search.get("enabled"):
        return []
    tool: dict[str, Any] = {
        "type": str(web_search.get("type") or "web_search_20250305"),
        "name": "web_search",
        "max_uses": int(web_search["max_uses"]),
    }
    response_inclusion = str(web_search.get("response_inclusion") or "").strip()
    if response_inclusion:
        tool["response_inclusion"] = response_inclusion
    allowed = web_search.get("allowed_domains") or []
    if allowed:
        if not isinstance(allowed, list) or not all(isinstance(x, str) and x for x in allowed):
            raise SystemExit("エラー: web_search.allowed_domains は文字列配列で指定してください。")
        tool["allowed_domains"] = allowed
    return [tool]


def build_request(
    config: dict[str, Any],
    prompt: str,
    *,
    max_tokens: int | None = None,
    enable_web_search: bool = True,
) -> dict[str, Any]:
    anthropic_config = model_config(config)
    request: dict[str, Any] = {
        "model": anthropic_config["model"],
        "max_tokens": max_tokens if max_tokens is not None else int(anthropic_config["max_tokens"]),
        "messages": [{"role": "user", "content": prompt}],
        "system": [{
            "type": "text",
            "text": "あなたは ErrorLog 専任の日本語テクニカルライターです。確認できる根拠に基づいて下書き記事を生成します。",
            "cache_control": {"type": "ephemeral"},
        }],
    }
    effort = str(anthropic_config.get("effort") or "").strip()
    if effort:
        request["output_config"] = {"effort": effort}
    thinking = require_dict(anthropic_config, "thinking")
    thinking_type = str(thinking.get("type") or "").strip()
    if thinking_type:
        request["thinking"] = {"type": thinking_type}
        display = str(thinking.get("display") or "").strip()
        if display:
            request["thinking"]["display"] = display
    tools = build_tools(require_dict(anthropic_config, "web_search")) if enable_web_search else []
    if tools:
        request["tools"] = tools
    return request


def load_anthropic_client() -> Any:
    try:
        import anthropic
    except ImportError:
        return None

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("エラー: ANTHROPIC_API_KEY が設定されていません。")
    return anthropic.Anthropic(api_key=api_key)


def count_input_tokens(client: Any, request: dict[str, Any]) -> int:
    kwargs = {k: v for k, v in request.items() if k not in {"max_tokens", "tools"}}
    if client is None:
        data = post_anthropic_json("messages/count_tokens", kwargs)
        return int(data.get("input_tokens") or 0)
    counted = client.messages.count_tokens(**kwargs)
    data = response_to_dict(counted)
    return int(data.get("input_tokens") or 0)


def maximum_cost_for_request(config: dict[str, Any], input_tokens: int, request: dict[str, Any]) -> dict[str, Any]:
    cfg = model_config(config)
    web_search = require_dict(cfg, "web_search")
    return estimate_scenario(
        config,
        input_tokens=input_tokens,
        output_tokens=int(request["max_tokens"]),
        web_search_requests=int(request["tools"][0]["max_uses"]) if request.get("tools") else 0,
    )


def expected_cost_for_request(config: dict[str, Any], input_tokens: int, request: dict[str, Any]) -> dict[str, Any]:
    cfg = model_config(config)
    expected_output = int(cfg.get("expected_output_tokens") or min(int(request["max_tokens"]), 15000))
    web_search = require_dict(cfg, "web_search")
    expected_web = int(web_search.get("expected_uses") or min(int(web_search.get("max_uses") or 0), 5))
    return estimate_scenario(
        config,
        input_tokens=input_tokens,
        output_tokens=expected_output,
        web_search_requests=expected_web if request.get("tools") else 0,
    )


def enforce_budget(
    config: dict[str, Any],
    maximum: dict[str, Any],
    request: dict[str, Any],
    confirm_over_budget: bool,
    *,
    spent_cost_usd: float = 0.0,
) -> None:
    budget = budget_config(config)
    configured_hard = float(budget["hard_limit_usd"])
    hard = configured_hard - spent_cost_usd
    if hard <= 0:
        raise SystemExit(f"エラー: 既使用額が hard_limit_usd に達しています: ${spent_cost_usd:.6f} >= ${configured_hard:.6f}")
    if float(maximum["total_cost_usd"]) <= hard:
        return
    action = str(budget.get("hard_limit_action") or "stop")
    if action == "stop":
        raise SystemExit(
            "エラー: 累計最大料金が hard_limit_usd を超える可能性があります: "
            f"${spent_cost_usd + float(maximum['total_cost_usd']):.6f} > ${configured_hard:.6f}"
        )
    if action == "confirm":
        if not confirm_over_budget:
            raise SystemExit("エラー: 最大料金が hard_limit_usd を超えるため --confirm-over-budget が必要です。")
        return
    if action == "shrink":
        cfg = model_config(config)
        pricing = pricing_config(config)
        input_tokens = int(maximum["input_tokens"])
        web_search = require_dict(cfg, "web_search")
        max_web = int(web_search["max_uses"]) if web_search.get("enabled") else 0
        for web_uses in range(max_web, -1, -1):
            remaining = hard - estimate_scenario(config, input_tokens, 0, web_uses)["total_cost_usd"]
            output_tokens = max(1000, int((remaining / float(pricing["output_mtok_usd"])) * 1_000_000))
            if output_tokens <= int(cfg["max_tokens"]):
                request["max_tokens"] = output_tokens
                if request.get("tools"):
                    request["tools"][0]["max_uses"] = web_uses
                print(f"budget shrink: max_tokens={output_tokens} web_search.max_uses={web_uses}")
                return
        raise SystemExit("エラー: shrink しても hard_limit_usd 内に収まりません。")
    raise SystemExit(f"エラー: budget.hard_limit_action が不正です: {action}")


def call_anthropic(
    config: dict[str, Any],
    prompt: str,
    confirm_over_budget: bool,
    *,
    phase: str,
    max_tokens: int | None = None,
    enable_web_search: bool = True,
    spent_cost_usd: float = 0.0,
) -> GenerationResult:
    request = build_request(config, prompt, max_tokens=max_tokens, enable_web_search=enable_web_search)
    client = load_anthropic_client()
    input_tokens = count_input_tokens(client, request)
    expected = expected_cost_for_request(config, input_tokens, request)
    maximum = maximum_cost_for_request(config, input_tokens, request)
    expected_total = spent_cost_usd + float(expected["total_cost_usd"])
    print_cost(f"{phase} 想定料金", expected)
    print_cost(f"{phase} 最大料金", maximum)
    if expected_total >= float(budget_config(config)["warning_usd"]):
        print(f"warning: 累計想定料金が warning_usd を超えています: ${expected_total:.6f}")
    enforce_budget(config, maximum, request, confirm_over_budget, spent_cost_usd=spent_cost_usd)

    if client is None:
        response_json = post_anthropic_json("messages", request)
    else:
        message = client.messages.create(**request)
        response_json = response_to_dict(message)
    stop_reason = response_json.get("stop_reason")
    if stop_reason == "max_tokens":
        raise SystemExit("エラー: max_tokens に達して出力が途中で切れました。記事は保存しません。")
    if stop_reason in {"refusal", "pause_turn"}:
        raise SystemExit(f"エラー: Anthropic stop_reason={stop_reason} のため記事は保存しません。")
    usage = usage_from_response(response_json)
    cost = usage_cost(config, usage, expected, maximum)
    print_cost(f"{phase} 実行後の実料金", cost)
    cumulative_cost = spent_cost_usd + float(cost["total_cost_usd"])
    hard_limit = float(budget_config(config)["hard_limit_usd"])
    cost["cumulative_cost_usd"] = round(cumulative_cost, 6)
    cost["hard_limit_exceeded"] = cumulative_cost > hard_limit
    return GenerationResult(
        article=text_from_response(response_json),
        response_json=response_json,
        usage=usage,
        cost=cost,
    )


def split_frontmatter(content: str) -> tuple[str, str]:
    if not content.startswith("---\n"):
        raise SystemExit("エラー: 生成結果に front matter がありません。")
    end = content.find("\n---", 4)
    if end == -1:
        raise SystemExit("エラー: 生成結果の front matter が閉じていません。")
    return content[: end + 4], content[end + 4:].lstrip("\n")


def ensure_frontmatter(article: str, row: dict[str, str], slug: str) -> str:
    tool = row["tool"].strip()
    code = row["status_code"].strip()
    title = f"{tool} の {code} エラー：原因と解決策"
    tags = tags_for_tool(tool, slug)
    if article.startswith("---\n"):
        _fm, body = split_frontmatter(article)
    else:
        body = article
    body = strip_internal_notes(body)
    body = normalize_before_after(body)
    body = strip_intro_boilerplate(body)
    body = strip_trailing_disclaimer(body)
    methodology = generate_methodology_note(row)
    if methodology and "## Editor" not in body:
        body = body.rstrip() + methodology
    frontmatter = (
        "---\n"
        f"title: {json_string(title)}\n"
        f"date: {date.today().isoformat()}\n"
        "draft: true\n"
        f"description: {json_string(build_description(row, tool, code))}\n"
        f"tags: {json.dumps(tags, ensure_ascii=False)}\n"
        f"errorCode: {json_string(code)}\n"
        f"urgency: {json_string(urgency_from_code(code))}\n"
        f"service: {json_string(tool)}\n"
        f"error_type: {json_string(code)}\n"
        "components: []\n"
        "related_services: []\n"
        "---\n\n"
    )
    return frontmatter + body.rstrip() + DISCLAIMER + "\n"


def insert_editor_note(article: str, evidence: dict[str, Any]) -> str:
    if re.search(r"(?mi)^##\s*Editor's Note\b", article):
        return article
    claims = [c for c in evidence.get("claim_source_map", []) if isinstance(c, dict)]
    fetched_urls = {
        s.get("url")
        for s in evidence.get("sources", [])
        if isinstance(s, dict) and s.get("status") == "fetched"
    }
    usable_claims = [
        c for c in claims
        if any(url in fetched_urls for url in c.get("source_urls", []))
    ]
    if len(usable_claims) < 2:
        return article
    urls = []
    for claim in usable_claims[:2]:
        for url in claim.get("source_urls", []):
            if url in fetched_urls and url not in urls:
                urls.append(url)
                break
    if len(urls) < 2:
        return article
    note = (
        "## Editor's Note\n\n"
        "このエラーはアプリコンテナの失敗ではなく、kubelet が sandbox を作る前段で止まる点が重要です。"
        f"Kubernetes の Pod デバッグ手順はイベント確認を起点にしており（[公式ドキュメント]({urls[0]})）、"
        f"ネットワーク実装は CNI プラグインが担うため（[Network Plugins]({urls[1]})）、"
        "現場では `desc =` 以降の文言から CNI か runtime かを先に分けるのが有効です。"
    )
    marker = "\n\n---\n\n*免責事項"
    idx = article.find(marker)
    if idx == -1:
        return article.rstrip() + "\n\n" + note + "\n"
    return article[:idx].rstrip() + "\n\n" + note + article[idx:]


def write_new_file(path: Path, content: str, dry_run: bool) -> None:
    if path.exists():
        raise SystemExit(f"エラー: 既存記事を上書きしないため停止します: {path}")
    if dry_run:
        print(f"[dry-run] write skipped: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{uuid.uuid4().hex}")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def save_run_report(report_dir: Path, payload: dict[str, Any], dry_run: bool) -> Path:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:8]
    out_dir = report_dir / str(payload["slug"]) / run_id
    if dry_run:
        print(f"[dry-run] report skipped: {out_dir}")
        return out_dir
    out_dir.mkdir(parents=True, exist_ok=False)
    (out_dir / "prompt.md").write_text(str(payload["prompt"]), encoding="utf-8")
    if payload.get("research_prompt") is not None:
        (out_dir / "research_prompt.md").write_text(str(payload["research_prompt"]), encoding="utf-8")
    if payload.get("research_report") is not None:
        (out_dir / "research_report.md").write_text(str(payload["research_report"]), encoding="utf-8")
    (out_dir / "usage.json").write_text(
        json.dumps(payload["usage"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if payload.get("evidence") is not None:
        (out_dir / "web_search_evidence.json").write_text(
            json.dumps(payload["evidence"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if payload.get("response_json") is not None:
        (out_dir / "response.json").write_text(
            json.dumps(payload["response_json"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if payload.get("research_response_json") is not None:
        (out_dir / "research_response.json").write_text(
            json.dumps(payload["research_response_json"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    article_name = "quarantined_article.md" if payload.get("quarantined") else "article.md"
    (out_dir / article_name).write_text(str(payload["article"]), encoding="utf-8")
    return out_dir


def save_research_checkpoint(
    report_dir: Path,
    slug: str,
    prompt: str,
    result: GenerationResult,
) -> Path:
    checkpoint_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:8]
    out_dir = report_dir / slug / "research_checkpoints" / checkpoint_id
    out_dir.mkdir(parents=True, exist_ok=False)
    (out_dir / "research_prompt.md").write_text(prompt, encoding="utf-8")
    (out_dir / "research_report.md").write_text(result.article, encoding="utf-8")
    (out_dir / "usage.json").write_text(
        json.dumps(result.cost, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "response.json").write_text(
        json.dumps(result.response_json, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return out_dir


def run_quality(article_path: Path, config: dict[str, Any], run_fact_check: bool) -> bool:
    quality = require_dict(config, "quality")
    rel = article_path.relative_to(BASE).as_posix()
    if quality.get("run_lint"):
        subprocess.run([sys.executable, "scripts/lint_articles.py", "--path", rel], cwd=BASE, check=True)
    if run_fact_check or quality.get("run_fact_check"):
        result = subprocess.run(
            [sys.executable, "scripts/fact_check.py", "--mode", "new", rel],
            cwd=BASE,
            check=False,
        )
        return result.returncode == 0
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Anthropic API で ErrorLog 記事を draft 生成")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="設定 YAML")
    parser.add_argument("--queue-index", type=int, help="scripts/queue.csv の 0 始まり行番号")
    parser.add_argument("--slug", required=True, help="保存する slug（content/posts/<slug>.md）")
    parser.add_argument("--tool", default="", help="queue を使わず手動指定するツール名")
    parser.add_argument("--error-code", default="", help="queue を使わず手動指定するエラー名/コード")
    parser.add_argument("--official-meaning", default="", help="queue を使わず手動指定する公式上の意味")
    parser.add_argument("--causes", default="", help="queue を使わず手動指定する原因。複数は | 区切り")
    parser.add_argument("--solutions", default="", help="queue を使わず手動指定する解決策。複数は | 区切り")
    parser.add_argument("--evidence-url", action="append", default=[], help="確認済み evidence URL。複数指定可")
    parser.add_argument("--skip-evidence-fetch", action="store_true", help="evidence URL の本文取得を行わない")
    parser.add_argument("--add-editor-note-only", action="store_true", help="既存 draft に evidence 由来の Editor's Note だけ追加する")
    parser.add_argument("--dry-run", action="store_true", help="API 呼び出しとファイル書き込みを行わない")
    parser.add_argument("--cost-table", action="store_true", help="代表条件の料金表を出力する")
    parser.add_argument("--confirm-over-budget", action="store_true", help="hard_limit_action=confirm の場合に実行を許可する")
    parser.add_argument("--max-tokens", type=int, help="config の max_tokens をこの実行だけ上書きする")
    parser.add_argument("--web-search-max-uses", type=int, help="config の Web検索上限をこの実行だけ上書きする")
    parser.add_argument("--run-quality", action="store_true", help="保存後に既存品質ゲートを実行する")
    parser.add_argument("--run-fact-check", action="store_true", help="--run-quality 時に Gemini fact-check まで実行する")
    args = parser.parse_args()

    config = load_config(Path(args.config))
    apply_runtime_overrides(config, args)
    paths = require_dict(config, "paths")
    slug = safe_slug(args.slug)
    queue_path = BASE / str(paths["queue"])
    posts_dir = BASE / str(paths["posts_dir"])
    report_dir = BASE / str(paths["report_dir"])
    rules_path = BASE / str(paths["rules"])
    editorial_context_path = BASE / str(paths["editorial_context"])
    editorial_context_meta_path = BASE / str(paths["editorial_context_meta"])

    if args.queue_index is not None:
        row = load_queue_row(queue_path, args.queue_index)
    else:
        row = manual_row(
            args.tool,
            args.error_code,
            args.official_meaning,
            args.causes,
            args.solutions,
        )
    article_path = posts_dir / f"{slug}.md"
    if article_path.exists():
        if not args.add_editor_note_only:
            raise SystemExit(f"エラー: 既存記事を上書きしないため停止します: {article_path}")
    if not rules_path.exists():
        raise SystemExit(f"エラー: 記事ルールが見つかりません: {rules_path}")
    if not editorial_context_path.exists():
        raise SystemExit(f"エラー: 編集コンテキストが見つかりません: {editorial_context_path}")
    if not editorial_context_meta_path.exists():
        raise SystemExit(f"エラー: 編集コンテキストのメタ情報が見つかりません: {editorial_context_meta_path}")
    if not ARTICLE_SPEC.exists():
        raise SystemExit(f"エラー: 共通記事仕様が見つかりません: {ARTICLE_SPEC}")

    evidence = build_evidence(
        row,
        args.evidence_url,
        fetch_enabled=not args.skip_evidence_fetch and not args.dry_run,
    )
    if args.add_editor_note_only:
        article = article_path.read_text(encoding="utf-8")
        updated = insert_editor_note(article, evidence)
        if updated == article:
            raise SystemExit("エラー: Editor's Note を追加できませんでした。evidence の取得状態を確認してください。")
        if args.dry_run:
            print("[dry-run] Editor's Note 追加は行いません。")
            print_requested_cost_table(config) if args.cost_table else None
            return 0
        article_path.write_text(updated, encoding="utf-8")
        report_path = save_run_report(
            report_dir,
            {
                "slug": slug,
                "prompt": "",
                "article": updated,
                "usage": {},
                "evidence": evidence,
                "response_json": None,
            },
            dry_run=False,
        )
        run_quality(article_path, config, False)
        print(f"Editor's Note 追加完了: {article_path.relative_to(BASE).as_posix()}")
        print(f"report: {report_path.relative_to(BASE).as_posix()}")
        return 0
    editorial_context = editorial_context_path.read_text(encoding="utf-8")
    editorial_context_meta = editorial_context_meta_path.read_text(encoding="utf-8")
    article_spec = ARTICLE_SPEC.read_text(encoding="utf-8")
    research_prompt = build_research_prompt(
        row=row,
        slug=slug,
        editorial_context=editorial_context,
        editorial_context_meta=editorial_context_meta,
        article_spec=article_spec,
        evidence=evidence,
    )
    dry_run_prompt = build_user_prompt(
        row=row,
        slug=slug,
        editorial_context=editorial_context,
        editorial_context_meta=editorial_context_meta,
        rules=rules_path.read_text(encoding="utf-8"),
        article_spec=article_spec,
        research_report="<調査APIの出力をここへ挿入>",
        evidence=evidence,
    )
    if args.cost_table:
        print_requested_cost_table(config)
    if args.dry_run:
        print("[dry-run] Anthropic API は呼びません。")
        print(f"[dry-run] target: {article_path}")
        print(f"[dry-run] tool/code: {row['tool']} {row['status_code']}")
        print(f"[dry-run] research_prompt_chars: {len(research_prompt)}")
        print(f"[dry-run] writing_prompt_chars_without_report: {len(dry_run_prompt)}")
        return 0

    research_config = require_dict(config, "research")
    research_result = call_anthropic(
        config,
        research_prompt,
        args.confirm_over_budget,
        phase="調査",
        max_tokens=int(research_config["max_tokens"]),
        enable_web_search=True,
    )
    research_checkpoint = save_research_checkpoint(
        report_dir,
        slug,
        research_prompt,
        research_result,
    )
    print(f"research checkpoint: {research_checkpoint.relative_to(BASE).as_posix()}")
    if research_result.cost["hard_limit_exceeded"]:
        print(
            "エラー: 調査だけで hard_limit_usd を超えました。"
            "調査結果はチェックポイントへ保存し、執筆は実行しません。"
        )
        return 1
    prompt = build_user_prompt(
        row=row,
        slug=slug,
        editorial_context=editorial_context,
        editorial_context_meta=editorial_context_meta,
        rules=rules_path.read_text(encoding="utf-8"),
        article_spec=article_spec,
        research_report=research_result.article,
        evidence=evidence,
    )
    result = call_anthropic(
        config,
        prompt,
        args.confirm_over_budget,
        phase="執筆",
        enable_web_search=False,
        spent_cost_usd=float(research_result.cost["total_cost_usd"]),
    )
    combined_cost = combine_phase_costs(research_result.cost, result.cost)
    article = ensure_frontmatter(result.article, row, slug)
    hard_limit = float(budget_config(config)["hard_limit_usd"])
    if float(combined_cost["total_cost_usd"]) > hard_limit:
        combined_cost["hard_limit_exceeded"] = True
        report_path = save_run_report(
            report_dir,
            {
                "slug": slug,
                "prompt": prompt,
                "article": article,
                "usage": combined_cost,
                "evidence": evidence,
                "research_prompt": research_prompt,
                "research_report": research_result.article,
                "research_response_json": research_result.response_json,
                "response_json": result.response_json,
                "quarantined": True,
            },
            dry_run=False,
        )
        print(
            f"エラー: 累計実料金が hard_limit_usd を超えました: "
            f"${combined_cost['total_cost_usd']:.6f} > ${hard_limit:.6f}"
        )
        print(f"隔離保存: {report_path.relative_to(BASE).as_posix()}/quarantined_article.md")
        return 1
    combined_cost["hard_limit_exceeded"] = False
    write_new_file(article_path, article, dry_run=False)
    fact_check_passed = False
    if args.run_quality:
        fact_check_passed = run_quality(article_path, config, args.run_fact_check)
        if args.run_fact_check and fact_check_passed:
            article_with_note = insert_editor_note(article_path.read_text(encoding="utf-8"), evidence)
            if article_with_note != article_path.read_text(encoding="utf-8"):
                article_path.write_text(article_with_note, encoding="utf-8")
                subprocess.run([sys.executable, "scripts/lint_articles.py", "--path", article_path.relative_to(BASE).as_posix()], cwd=BASE, check=True)
    report_path = save_run_report(
        report_dir,
        {
            "slug": slug,
            "prompt": prompt,
            "article": article,
            "usage": combined_cost,
            "evidence": evidence,
            "research_prompt": research_prompt,
            "research_report": research_result.article,
            "research_response_json": research_result.response_json,
            "fact_check_passed_before_editor_note": fact_check_passed,
            "response_json": result.response_json,
        },
        dry_run=False,
    )
    print(f"生成完了: {article_path.relative_to(BASE).as_posix()}")
    print(
        f"usage: input={combined_cost['input_tokens']} output={combined_cost['output_tokens']} "
        f"cost=${combined_cost['total_cost_usd']:.6f}"
    )
    print(f"report: {report_path.relative_to(BASE).as_posix()}")
    if not args.run_quality:
        print("品質ゲートは未実行です。実行する場合は --run-quality を付けてください。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
