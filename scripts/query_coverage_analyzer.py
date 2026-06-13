"""
Content Gap Detector:
GSCクエリと既存記事を照合し、未記事化テーマを発見する。
新規記事候補の自動発見ツール（リライトには使用しない）。

入力:
  GSC API ["query"] dimension  — ライブデータ（認証あり時）
  data/search_queries.json     — オフラインフォールバック
  content/posts/*.md           — 既存記事 Front Matter

出力:
  data/content_gap.json              — coverage分析
  scripts/content_gap_candidates.json — 上位候補
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

# ─── パス ──────────────────────────────────────────────────────────
BASE        = Path(__file__).parent.parent
SCRIPTS_DIR = Path(__file__).parent
POSTS_DIR   = BASE / "content" / "posts"
DATA_DIR    = BASE / "data"

TODAY    = date.today()
SITE_URL = os.getenv("GSC_SITE_URL", "https://errorlog.jp/")

# ─── 閾値 ──────────────────────────────────────────────────────────
MIN_IMPRESSIONS   = int(os.getenv("MIN_IMPRESSIONS_FOR_GAP", "50"))
COVERED_THRESHOLD = float(os.getenv("COVERED_THRESHOLD",  "0.60"))
PARTIAL_THRESHOLD = float(os.getenv("PARTIAL_THRESHOLD",  "0.25"))
TOP_CANDIDATES    = int(os.getenv("TOP_GAP_CANDIDATES",   "20"))

# ─── 出力ファイル ──────────────────────────────────────────────────
CONTENT_GAP_FILE = DATA_DIR / "content_gap.json"
CANDIDATES_FILE  = SCRIPTS_DIR / "content_gap_candidates.json"

# ─── テキスト処理 ──────────────────────────────────────────────────
_STOP_EN = frozenset({
    "a", "an", "the", "in", "on", "at", "for", "to", "of", "and", "or",
    "is", "are", "was", "be", "with", "by", "from", "as", "it", "i",
    "not", "how", "what", "why", "when", "where", "error", "vs",
    "get", "cannot", "can", "could", "that", "this", "these", "those",
    "using", "use", "via", "make", "do", "did", "does", "my",
})
# サービスフィールドのトークン化で除外する汎用語
_SERVICE_GENERIC = frozenset({"api", "service", "app", "cli", "sdk"})


def _tokenize(text: str) -> frozenset[str]:
    # ASCII↔CJK の境界でもスペースを挿入（例: "401エラー" → "401 エラー"）
    text = re.sub(r'([a-zA-Z0-9])([^\x00-\x7F])', r'\1 \2', text)
    text = re.sub(r'([^\x00-\x7F])([a-zA-Z0-9])', r'\1 \2', text)
    tokens = set()
    for t in re.split(r'[\s\-_./,\(\)\[\]"\':]+', text.lower()):
        if len(t) >= 2 and t not in _STOP_EN:
            tokens.add(t)
    return frozenset(tokens)


# ─── サービス名・コンポーネント推定マップ ────────────────────────
_SERVICE_MAP: dict[str, str] = {
    "aws":        "AWS",
    "amazon":     "AWS",
    "terraform":  "Terraform",
    "azure":      "Azure",
    "gcp":        "GCP",
    "firebase":   "Firebase",
    "firestore":  "Firebase",
    "docker":     "Docker",
    "kubernetes": "Kubernetes",
    "k8s":        "Kubernetes",
    "kubectl":    "Kubernetes",
    "helm":       "Kubernetes",
    "nginx":      "Nginx",
    "github":     "GitHub API",
    "gitlab":     "GitLab",
    "openai":     "OpenAI API",
    "chatgpt":    "OpenAI API",
    "gemini":     "Gemini API",
    "fastapi":    "FastAPI",
    "flask":      "Flask",
    "django":     "Django",
    "redis":      "Redis",
    "postgres":   "PostgreSQL",
    "postgresql": "PostgreSQL",
    "mysql":      "MySQL",
    "mongodb":    "MongoDB",
    "minikube":   "Minikube",
    "ansible":    "Ansible",
    "jenkins":    "Jenkins",
    "circleci":   "CircleCI",
    "vercel":     "Vercel",
    "netlify":    "Netlify",
    "supabase":   "Supabase",
    "stripe":     "Stripe",
}

_COMPONENT_MAP: dict[str, str] = {
    "iam":        "IAM",
    "s3":         "S3",
    "ec2":        "EC2",
    "lambda":     "Lambda",
    "rds":        "RDS",
    "cloudfront": "CloudFront",
    "vpc":        "VPC",
    "oidc":       "OIDC",
    "jwt":        "JWT",
    "oauth":      "OAuth",
    "cors":       "CORS",
    "ssl":        "SSL",
    "tls":        "TLS",
    "compose":    "Compose",
    "registry":   "Registry",
    "ingress":    "Ingress",
    "rbac":       "RBAC",
    "actions":    "Actions",
    "webhook":    "Webhook",
    "sts":        "STS",
    "graphql":    "GraphQL",
    "grpc":       "gRPC",
}

_ERROR_CODE_RE = re.compile(r"\b([1-5]\d{2})\b")


# ─── Front Matter パーサー ─────────────────────────────────────────

def _fm_str(fm: str, field: str) -> str:
    m = re.search(rf'^{field}:\s*"?([^"\n]+?)"?\s*$', fm, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _fm_list(fm: str, field: str) -> list[str]:
    m = re.search(rf'^{field}:\s*\[([^\]]*)\]', fm, re.MULTILINE)
    if m:
        return [s.strip().strip('"\'') for s in m.group(1).split(",") if s.strip()]
    m = re.search(rf'^{field}:\s*\n((?:[ \t]*-[ \t]+[^\n]*\n?)+)', fm, re.MULTILINE)
    if m:
        return [
            re.sub(r'^[ \t]*-[ \t]+', '', ln).strip().strip('"\'')
            for ln in m.group(1).splitlines()
            if ln.strip()
        ]
    return []


# ─── 記事インデックス構築 ──────────────────────────────────────────

def _build_article_index() -> list[dict]:
    """全記事を読み込み、マッチング用トークンインデックスを構築する。"""
    articles = []
    for md in sorted(POSTS_DIR.glob("*.md")):
        text  = md.read_text(encoding="utf-8-sig")
        fm_m  = re.match(r'^---\n(.*?)\n---', text, re.DOTALL)
        if not fm_m:
            continue
        fm = fm_m.group(1)

        service          = _fm_str(fm, "service")
        error_type       = _fm_str(fm, "error_type")
        error_code       = _fm_str(fm, "errorCode")
        code             = error_type or error_code
        components       = _fm_list(fm, "components")
        related_services = _fm_list(fm, "related_services")
        tags             = _fm_list(fm, "tags")
        title            = _fm_str(fm, "title")
        top_queries      = _fm_list(fm, "top_queries")

        # サービスフィールドは汎用語を除外してトークン化
        svc_tok = _tokenize(service) - _SERVICE_GENERIC

        articles.append({
            "slug":    md.stem,
            "title":   title,
            "service": service,
            "code":    code,
            "svc_tok":   svc_tok,
            "code_tok":  frozenset({code.lower()}) if code else frozenset(),
            "comp_tok":  frozenset(t for c in components for t in _tokenize(c)),
            "rel_tok":   frozenset(
                t for r in related_services
                for t in (_tokenize(r) - _SERVICE_GENERIC)
            ),
            "tag_tok":   frozenset(t for tg in tags for t in _tokenize(tg)),
            "title_tok": _tokenize(title),
            "tq_tok":    frozenset(t for q in top_queries for t in _tokenize(q)),
        })
    return articles


# ─── カバレッジスコアリング ────────────────────────────────────────

def _coverage_score(q_tok: frozenset[str], art: dict) -> float:
    """クエリトークンと記事の一致スコア（0.0〜1.0）を返す。

    採点基準（最大 14.5 点）:
      サービス名  5.0  — 最重要: 記事が対象サービスのものか
      エラーコード 4.0  — 記事が対象コードのものか
      コンポーネント 最大2.0
      タグ        1.0
      タイトル単語 最大1.0
      関連サービス  0.5
      top_queries  1.0 ボーナス
    """
    score = 0.0
    if art["svc_tok"] and (art["svc_tok"] & q_tok):
        score += 5.0
    if art["code_tok"] and (art["code_tok"] & q_tok):
        score += 4.0
    score += min(len(art["comp_tok"] & q_tok), 2)
    if art["tag_tok"] & q_tok:
        score += 1.0
    score += min(len(art["title_tok"] & q_tok) * 0.3, 1.0)
    if art["rel_tok"] & q_tok:
        score += 0.5
    if art["tq_tok"] & q_tok:
        score += 1.0
    return score / 14.5


def _classify(query: str, articles: list[dict]) -> tuple[str, str, float]:
    """クエリを covered / partial / uncovered に分類する。

    Returns:
        (coverage, best_match_slug, best_score)
    """
    q_tok      = _tokenize(query)
    best_score = 0.0
    best_slug  = ""
    for art in articles:
        s = _coverage_score(q_tok, art)
        if s > best_score:
            best_score = s
            best_slug  = art["slug"]

    if best_score >= COVERED_THRESHOLD:
        return "covered", best_slug, best_score
    if best_score >= PARTIAL_THRESHOLD:
        return "partial", best_slug, best_score
    return "uncovered", best_slug, best_score


# ─── Opportunity スコア ───────────────────────────────────────────

def _opportunity_score(impressions: int, ctr: float, position: float) -> float:
    """未対応クエリの機会スコアを計算する。

    score = impressions*0.6 + (1-ctr)*100*0.2 + position*0.2
    impressions < MIN_IMPRESSIONS の場合は 0 を返す。
    """
    if impressions < MIN_IMPRESSIONS:
        return 0.0
    return round(impressions * 0.6 + (1.0 - ctr) * 100 * 0.2 + position * 0.2, 2)


# ─── タイトル・サービス推定 ────────────────────────────────────────

def _infer_service(q_tok: frozenset[str]) -> str:
    for token in q_tok:
        if token in _SERVICE_MAP:
            return _SERVICE_MAP[token]
    return ""


def _infer_components(q_tok: frozenset[str]) -> list[str]:
    return [_COMPONENT_MAP[t] for t in sorted(q_tok) if t in _COMPONENT_MAP][:3]


def _suggest_title(query: str, service: str = "") -> str:
    """検索クエリからルールベースで記事タイトルを生成する。"""
    words  = query.strip().split()
    capped = " ".join(
        w.upper() if len(w) <= 3 and w.isalpha() else w.capitalize()
        for w in words
    )
    q_lower = query.lower()

    if _ERROR_CODE_RE.search(query):
        return f"{capped} エラー：原因と解決策"
    if any(k in q_lower for k in ["access denied", "permission", "forbidden", "unauthorized", "auth"]):
        return f"{capped} 認証・権限エラー：原因と解決策"
    if any(k in q_lower for k in ["timeout", "connection", "refused", "unreachable", "connect"]):
        return f"{capped} 接続・タイムアウトエラー：解決方法"
    if any(k in q_lower for k in ["not found", "missing", "404"]):
        return f"{capped} Not Found エラー：原因と解決策"
    if any(k in q_lower for k in ["rate limit", "quota", "throttl", "429"]):
        return f"{capped} レート制限エラー：対処法"
    if any(k in q_lower for k in ["ssl", "tls", "certificate", "cert"]):
        return f"{capped} SSL/TLS エラー：解決方法"
    return f"{capped} エラー：トラブルシューティングガイド"


# ─── クエリ取得 ────────────────────────────────────────────────────

def _load_queries_from_gsc() -> list[dict]:
    """GSC API から全クエリデータを取得する（dimensions=["query"]）。"""
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        from fetch_search_console import _build_service, _query as _gsc_query
    except ImportError as e:
        print(f"  [WARN] fetch_search_console import failed: {e}")
        return []
    try:
        service = _build_service()
    except Exception as e:
        print(f"  [WARN] GSC auth failed: {e}")
        return []
    rows   = _gsc_query(service, ["query"])
    result = [
        {
            "query":       r.get("query", "").strip(),
            "impressions": int(r.get("impressions", 0)),
            "ctr":         float(r.get("ctr", 0.0)),
            "position":    float(r.get("position", 0.0)),
        }
        for r in rows
        if r.get("query", "").strip()
    ]
    print(f"  [GSC] queries fetched: {len(result)}")
    return result


def _load_queries_from_cache() -> list[dict]:
    """data/search_queries.json からクエリを読み込む（オフラインフォールバック）。

    impressions は不明なため 0 を設定する。
    per-query opportunity_score は計算されないが coverage 分析は機能する。
    """
    sq_file = DATA_DIR / "search_queries.json"
    if not sq_file.exists():
        return []
    data = json.loads(sq_file.read_text(encoding="utf-8"))
    seen: dict[str, dict] = {}
    for slug_data in data.values():
        avg_ctr = float(slug_data.get("avg_ctr", 0.0))
        avg_pos = float(slug_data.get("avg_position", 0.0))
        for q in slug_data.get("top_queries", []):
            q = q.strip()
            if q and q not in seen:
                seen[q] = {
                    "query":       q,
                    "impressions": 0,
                    "ctr":         avg_ctr,
                    "position":    avg_pos,
                }
    result = list(seen.values())
    print(f"  [CACHE] queries loaded: {len(result)} (impressions=0, no opportunity_score)")
    return result


# ─── メイン分析 ────────────────────────────────────────────────────

def analyze(queries: list[dict], articles: list[dict]) -> dict:
    """クエリ × 記事インデックスの全件カバレッジ分析を実行する。"""
    covered_items:   list[dict] = []
    partial_items:   list[dict] = []
    uncovered_items: list[dict] = []

    for q_data in queries:
        query       = q_data["query"]
        impressions = int(q_data.get("impressions", 0))
        ctr         = float(q_data.get("ctr", 0.0))
        position    = float(q_data.get("position", 0.0))
        opp         = _opportunity_score(impressions, ctr, position)

        coverage, best_slug, score = _classify(query, articles)

        item = {
            "query":             query,
            "impressions":       impressions,
            "ctr":               round(ctr, 6),
            "position":          round(position, 2),
            "coverage":          coverage,
            "best_match_slug":   best_slug,
            "match_score":       round(score, 3),
            "opportunity_score": opp,
        }
        if coverage == "covered":
            covered_items.append(item)
        elif coverage == "partial":
            partial_items.append(item)
        else:
            uncovered_items.append(item)

    total    = len(queries)
    n_cov    = len(covered_items)
    n_par    = len(partial_items)
    n_unc    = len(uncovered_items)
    cov_rate = n_cov / total if total else 0.0

    uncovered_items.sort(key=lambda x: -x["opportunity_score"])
    partial_items.sort(key=lambda x: -x["opportunity_score"])

    return {
        "generated_at": TODAY.isoformat(),
        "uncovered":    uncovered_items,
        "partial":      partial_items,
        "summary": {
            "total_queries":  total,
            "covered":        n_cov,
            "partial":        n_par,
            "uncovered":      n_unc,
            "coverage_rate":  round(cov_rate, 4),
        },
    }


def _save_content_gap(result: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    CONTENT_GAP_FILE.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    s = result["summary"]
    print(
        f"  data/content_gap.json: total={s['total_queries']}, "
        f"covered={s['covered']}({s['coverage_rate']:.1%}), "
        f"partial={s['partial']}, uncovered={s['uncovered']}"
    )


def _save_candidates(result: dict) -> None:
    """opportunity_score 上位 TOP_CANDIDATES 件の新規記事候補を保存する。"""
    all_gaps = sorted(
        [i for i in result["uncovered"] if i["opportunity_score"] > 0]
        + [i for i in result["partial"]  if i["opportunity_score"] > 0],
        key=lambda x: -x["opportunity_score"],
    )

    candidates = []
    for item in all_gaps[:TOP_CANDIDATES]:
        q_tok   = _tokenize(item["query"])
        service = _infer_service(q_tok)
        comps   = _infer_components(q_tok)
        candidates.append({
            "query":           item["query"],
            "coverage":        item["coverage"],
            "score":           item["opportunity_score"],
            "suggested_title": _suggest_title(item["query"], service),
            "service":         service,
            "components":      comps,
            "impressions":     item["impressions"],
            "ctr":             item["ctr"],
            "position":        item["position"],
        })

    SCRIPTS_DIR.mkdir(exist_ok=True)
    CANDIDATES_FILE.write_text(
        json.dumps(candidates, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  content_gap_candidates.json: {len(candidates)} 件")

    if candidates:
        print("\n=== 新規記事候補 ===")
        for i, c in enumerate(candidates, 1):
            print(
                f"  {i:2}. [{c['coverage']:9s}] Score={c['score']:7.1f}"
                f"  {c['query'][:45]}"
                f"\n      → {c['suggested_title']}"
            )
    else:
        print("  (no candidates with opportunity_score > 0 - run with GSC credentials for live data)")


# ─── Entry point ──────────────────────────────────────────────────

def main() -> None:
    print(f"=== Content Gap Analyzer ({TODAY}) ===")

    articles = _build_article_index()
    print(f"  articles indexed: {len(articles)}")

    gsc_available = bool(
        os.environ.get("GSC_SERVICE_ACCOUNT_KEY", "").strip()
        or os.environ.get("GA4_SERVICE_ACCOUNT_KEY", "").strip()
        or (
            os.environ.get("GA4_OAUTH_CLIENT_ID", "").strip()
            and os.environ.get("GA4_OAUTH_REFRESH_TOKEN", "").strip()
        )
    )

    if gsc_available:
        print("  [1/3] GSC API からクエリを取得中...")
        queries = _load_queries_from_gsc()
    else:
        print("  [1/3] GSC auth not set - using cache (data/search_queries.json)")
        queries = _load_queries_from_cache()

    if not queries:
        print("  [WARN] クエリデータがありません。fetch_search_console.py を先に実行してください。")
        return

    print(f"  [2/3] カバレッジ分析中 ({len(queries)} queries × {len(articles)} articles)...")
    result = analyze(queries, articles)

    print("  [3/3] 結果を保存中...")
    _save_content_gap(result)
    _save_candidates(result)

    print("\nDone.")


if __name__ == "__main__":
    main()
