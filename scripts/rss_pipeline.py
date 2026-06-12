"""
RSS pipeline for GitHub Actions.
- Reads feeds from scripts/rss_feeds.json
- Tracks processed articles in scripts/rss_processed.json
- Scores articles with Gemini, generates errorlog-format drafts
- Saves drafts (draft: true) to content/posts/auto_YYYY-MM-DD_*.md

Usage:
  python scripts/rss_pipeline.py
  SCORE_THRESHOLD=70 python scripts/rss_pipeline.py
"""

import asyncio
import hashlib
import json
import logging
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Set

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("rss_pipeline")

# ── Paths ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR     = Path(__file__).parent
REPO_ROOT      = SCRIPT_DIR.parent
FEEDS_FILE     = SCRIPT_DIR / "rss_feeds.json"
PROCESSED_FILE = SCRIPT_DIR / "rss_processed.json"
POSTS_DIR      = REPO_ROOT / "content" / "posts"

# ── Config ────────────────────────────────────────────────────────────────────

SCORE_THRESHOLD = int(os.getenv("SCORE_THRESHOLD", "60"))
MAX_SCORE_CYCLE = int(os.getenv("MAX_SCORE_CYCLE", "20"))
API_DELAY       = float(os.getenv("API_DELAY", "4.0"))
MAX_PROCESSED   = 15_000

# Increment when scoring prompt logic changes (used to identify historical records).
RSS_SCORE_PROMPT_VERSION = "2"
SCORE_HISTORY_FILE = REPO_ROOT / "run" / "rss_score_history.jsonl"

INCIDENT_FLAGS_FILE = SCRIPT_DIR / "incident_flags.json"

# 障害検知用キーワード（ステータスフィード向け）
INCIDENT_KEYWORDS = {
    "incident", "outage", "degraded", "disruption", "investigating",
    "partial outage", "major outage", "service disruption",
    "障害", "停止", "サービス停止", "調査中", "復旧", "影響",
}

# ステータスフィードの feed_id（category="status" として識別）
STATUS_CATEGORIES = {"status", "Status"}

TECH_KEYWORDS = {
    "docker", "firebase", "aws", "github", "kubernetes", "k8s",
    "terraform", "hashicorp", "gcp", "google cloud", "cloudflare",
    "vercel", "nextjs", "openai", "anthropic", "llm",
    "ci/cd", "github actions", "nginx", "redis", "postgresql", "postgres",
}

ERROR_SIGNALS = {
    "error", "failed", "failure", "exception", "bug", "crash", "broken",
    "issue", "fix", "patch", "vulnerability", "cve", "incident", "outage",
    "timeout", "deadlock", "memory leak", "regression", "hotfix",
    "panic", "oom", "rate limit", "429", "500", "503",
    "エラー", "失敗", "不具合", "バグ", "障害", "脆弱性",
}

# ── Article template system prompt (matches daily_publish.py) ─────────────────

_DRAFT_SYSTEM = """あなたは「ErrorLog（errorlog.jp）」専任のテクニカルライターです。
日本人エンジニア向けに、HTTPエラーの原因と解決策を実用的に解説する記事を執筆します。

## スキップ条件（最優先）
ソース記事に具体的なエラーメッセージ・例外名・HTTPステータスコード・exit code が一切含まれない場合は、
記事を書かず以下の1行のみを出力すること:
[[SKIP: no specific error found]]

## 必須セクション（この順番で記述）

### 1. エラーの概要（H2）
このエラーの公式な意味と、対象ツールでの典型的な発生状況を2〜3文で説明する。

### 2. 実際のエラーメッセージ例（H2）
対象ツールが実際に出力するエラーログ・JSONレスポンス・コンソール出力をコードブロックで1〜2個示す。

### 3. よくある原因と解決手順（H2）
原因ごとに「### 原因N：〇〇」(H3)で区切り、各原因に必ず以下のセットを含める:
- なぜ発生するかの説明
- Before/Afterコード対比（下記の厳密な形式で記述すること）:

**Before（エラーが起きるコード）：**

```言語名
# エラーが発生するコードや設定
```

**After（修正後）：**

```言語名
# 修正後のコードや設定
```

原因は最低3つ挙げる。

### 4. ツール固有の注意点（H2）
ツールの特性に応じた深掘りを記述する。

### 5. それでも解決しない場合（H2）
確認すべきログの場所・デバッグコマンド・公式ドキュメントへの参照。

## 品質要件
- 全体で1500文字以上（日本語本文のみ）
- H1タイトルは含めない
- コードブロックには必ず言語名を指定
- プレースホルダーは `<your-xxx>` 形式
- ですます調・断定的に書く
- 末尾に免責事項フッターを付ける:

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*

記事本文のみ出力してください。前置きは不要です。"""

# ── Before/After label normalization ─────────────────────────────────────────

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


# ── Gemini client ─────────────────────────────────────────────────────────────

def _get_gemini():
    from google import genai
    from google.genai import types
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY が未設定です")
    return genai.Client(api_key=api_key), types


async def _gemini_call(client, types, model: str, system: str, prompt: str,
                       temp: float = 0.2, max_tokens: int = 4096,
                       max_retries: int = 2, response_mime_type: str = None) -> str:
    for attempt in range(max_retries + 1):
        try:
            cfg_kwargs = dict(
                system_instruction=system,
                temperature=temp,
                max_output_tokens=max_tokens,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            )
            if response_mime_type:
                cfg_kwargs["response_mime_type"] = response_mime_type
            resp = await asyncio.to_thread(
                client.models.generate_content,
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(**cfg_kwargs),
            )
            text = resp.text
            if not text:
                raise ValueError("empty response from Gemini")
            return text
        except Exception as e:
            if "429" in str(e) and attempt < max_retries:
                m = re.search(r"retry in (\d+)", str(e))
                wait = int(m.group(1)) + 3 if m else 65
                log.warning("429 rate-limit – waiting %ds (attempt %d/%d)", wait, attempt + 1, max_retries)
                await asyncio.sleep(wait)
                continue
            raise

# ── Feed fetching ─────────────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()

def _entry_id(feed_id: str, entry) -> str:
    raw = getattr(entry, "id", None) or getattr(entry, "link", "") or entry.get("title", "")
    return hashlib.md5(f"{feed_id}:{raw}".encode()).hexdigest()

async def fetch_feed(feed: dict) -> List[dict]:
    import feedparser, httpx
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            r = await client.get(feed["url"], headers={"User-Agent": "rss-reader/2.0"})
            r.raise_for_status()
            parsed = feedparser.parse(r.text)
    except Exception as e:
        log.warning("[%s] fetch failed: %s", feed["name"], e)
        return []

    articles = []
    for entry in parsed.entries:
        aid = _entry_id(feed["id"], entry)
        title   = _strip_html(getattr(entry, "title", ""))
        link    = getattr(entry, "link", "")
        summary = _strip_html(getattr(entry, "summary", "") or getattr(entry, "description", ""))
        articles.append({"id": aid, "title": title, "link": link,
                         "summary": summary, "feed_name": feed["name"]})
    return articles

# ── Article text extraction ────────────────────────────────────────────────────

async def extract_text(url: str, fallback: str = "") -> str:
    try:
        import trafilatura, httpx
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            text = trafilatura.extract(r.text, include_comments=False,
                                       include_tables=True, no_fallback=False)
            if text and len(text) > 200:
                return text[:12000]
    except Exception as e:
        log.debug("trafilatura failed for %s: %s", url, e)
    return fallback[:3000]

# ── Stage 1: keyword filter ────────────────────────────────────────────────────

def stage1_filter(articles: List[dict]) -> List[dict]:
    out = []
    for a in articles:
        text = f"{a['title']} {a['summary']}".lower()
        if any(kw in text for kw in TECH_KEYWORDS) and \
           any(sig in text for sig in ERROR_SIGNALS):
            out.append(a)
    return out

# ── Phase 4: Incident detection ───────────────────────────────────────────────

def _extract_service_from_feed(feed_name: str) -> str:
    """フィード名からサービス名を抽出する（例: 'GitHub Status' → 'GitHub'）。"""
    return re.sub(r'\s*(Status|Blog|Changelog|News)\s*$', '', feed_name, flags=re.IGNORECASE).strip()


def detect_incidents(articles: List[dict], feeds: List[dict]) -> List[dict]:
    """24時間以内の障害情報を検知して incident リストを返す。

    ステータスフィード（category='status'）または障害キーワードを含む記事を対象とする。
    """
    feed_category: dict[str, str] = {f["name"]: f.get("category", "") for f in feeds}
    now_ts = datetime.now(timezone.utc).timestamp()
    cutoff = now_ts - 86400  # 24時間以内

    incidents = []
    seen_services: set[str] = set()

    for a in articles:
        cat  = feed_category.get(a.get("feed_name", ""), "")
        text = f"{a['title']} {a['summary']}".lower()

        is_status_feed   = cat.lower() in STATUS_CATEGORIES or "status" in a.get("feed_name", "").lower()
        has_incident_kw  = any(kw in text for kw in INCIDENT_KEYWORDS)

        if not (is_status_feed or has_incident_kw):
            continue

        service = _extract_service_from_feed(a.get("feed_name", "Unknown"))
        if service in seen_services:
            continue
        seen_services.add(service)

        # キーワード抽出（タイトル・サマリーから名詞句を簡易抽出）
        keywords = [
            w for w in re.findall(r'\b[A-Z][a-zA-Z]+\b', a["title"])
            if w not in {"The", "An", "A", "In", "On", "Is", "Are", "Was", "Has"}
        ][:5]

        incidents.append({
            "service":     service,
            "keywords":    keywords,
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "title":       a["title"],
            "link":        a.get("link", ""),
            "feed_name":   a.get("feed_name", ""),
        })
        log.info("INCIDENT detected: %s — %s", service, a["title"][:60])

    return incidents


def save_incident_flags(incidents: List[dict]) -> None:
    """incident_flags.json を生成する。既存データとマージして24時間以内のみ保持。"""
    existing: List[dict] = []
    if INCIDENT_FLAGS_FILE.exists():
        try:
            existing = json.loads(INCIDENT_FLAGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    # 24時間以上前のエントリを除去
    cutoff = datetime.now(timezone.utc).timestamp() - 86400
    existing = [
        e for e in existing
        if datetime.fromisoformat(e["detected_at"]).timestamp() > cutoff
    ]

    # 同一サービスの重複を除去（新しい方を優先）
    merged_by_service: dict[str, dict] = {e["service"]: e for e in existing}
    for inc in incidents:
        merged_by_service[inc["service"]] = inc

    result = list(merged_by_service.values())
    INCIDENT_FLAGS_FILE.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("incident_flags.json: %d active incidents", len(result))


# ── Stage 2: AI scoring ────────────────────────────────────────────────────────

def _keyword_score(title: str, body: str) -> int:
    """Gemini unavailable 時のキーワードベース代替スコアリング。"""
    text = f"{title} {body[:1000]}".lower()
    score = 0
    if re.search(r'\b[45]\d\d\b', text):
        score += 30
    error_hits = sum(1 for sig in ERROR_SIGNALS if sig in text)
    score += min(error_hits * 8, 40)
    tech_hits = sum(1 for kw in TECH_KEYWORDS if kw in text)
    score += min(tech_hits * 10, 30)
    return min(score, 100)


async def score_article(client, types, title: str, body: str) -> tuple[bool, int]:
    """Score article. Returns (eligible, score).

    eligible=False → reject regardless of score (hard gate).
    Prompt version: RSS_SCORE_PROMPT_VERSION.
    """
    prompt = (
        "Evaluate this technical article in two steps.\n\n"
        "Step 1 — Eligibility check:\n"
        "Does this article describe a specific, reproducible technical error? "
        "(HTTP status code, exception name, exit code, crash, or concrete failure condition)\n"
        "Answer eligible: YES or eligible: NO.\n"
        "If NO, score must be 0–30.\n\n"
        "Step 2 — Relevance score (0–100) for DevOps/backend engineers:\n"
        "High (65+): debugging guides, error/failure/outage analysis, troubleshooting, "
        "configuration fixes.\n"
        "Medium (40–64): architecture/setup with operational depth, error handling patterns, "
        "incident post-mortems.\n"
        "Low (0–39): general tutorials, conceptual overviews, opinion pieces, "
        "migration stories without specific errors, announcements.\n\n"
        'Return ONLY JSON: {"eligible": "YES", "score": 72}\n\n'
        f"Title: {title}\n\nBody (first 600 chars):\n{body[:600]}"
    )
    try:
        raw = await _gemini_call(client, types, "gemini-2.5-flash",
                                 "You are a tech article evaluator.", prompt,
                                 temp=0.1, max_tokens=60,
                                 response_mime_type="application/json")
        em = re.search(r'"eligible"\s*:\s*"(YES|NO)"', raw, re.IGNORECASE)
        eligible = (em.group(1).upper() == "YES") if em else True
        sm = re.search(r'"score"\s*:\s*(\d+)', raw)
        if sm:
            score = min(100, max(0, int(sm.group(1))))
        else:
            nums = re.findall(r'\b(\d{2,3})\b', raw)
            score = min(100, max(0, int(nums[0]))) if nums else _keyword_score(title, body)
        return eligible, score
    except Exception as e:
        log.warning("Score failed: %s — falling back to keyword score", e)
        return True, _keyword_score(title, body)


def append_rss_score_history(
    *,
    scored_at: str,
    source_url: str,
    title: str,
    eligible: bool,
    score: int,
    adopted: bool,
    skipped_at_generation: bool = False,
    gemini_model: str = "gemini-2.5-flash",
) -> None:
    """Append one scoring record to data/rss_score_history.jsonl."""
    record = {
        "scored_at": scored_at,
        "source_url": source_url,
        "title": title,
        "eligible": eligible,
        "score": score,
        "adopted": adopted,
        "skipped_at_generation": skipped_at_generation,
        "gemini_model": gemini_model,
        "prompt_version": RSS_SCORE_PROMPT_VERSION,
    }
    SCORE_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SCORE_HISTORY_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

# ── Draft generation ───────────────────────────────────────────────────────────

async def generate_draft(client, types, article: dict, body: str) -> tuple[str, bool]:
    """Generate article draft. Returns (content, skipped).

    skipped=True when model outputs [[SKIP: no specific error found]],
    meaning the generation gate rejected the source material.
    """
    today = date.today().isoformat()
    tool  = article["feed_name"].replace(" Blog", "").replace(" News", "")
    prompt = (
        f"以下のソース記事を元に、errorlog.jp 向けの技術記事を作成してください。\n\n"
        f"=== ソース: {article['title']} ({article['feed_name']}) ===\n"
        f"URL: {article['link']}\n\n{body[:10000]}\n\n"
        f"フロントマターを先頭に付けること:\n"
        f"---\n"
        f'title: ""\n'
        f"date: {today}\n"
        f"lastmod: {today}\n"
        f"draft: false\n"
        f'description: ""\n'
        f'tags: ["{tool}"]\n'
        f"---\n"
    )
    content = await _gemini_call(client, types, "gemini-2.5-flash",
                                 _DRAFT_SYSTEM, prompt, temp=0.3, max_tokens=8192)
    if "[[SKIP" in content:
        return content, True
    return content, False

# ── Processed IDs ─────────────────────────────────────────────────────────────

def load_processed() -> Set[str]:
    if PROCESSED_FILE.exists():
        try:
            return set(json.loads(PROCESSED_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return set()

def save_processed(ids: Set[str]):
    bounded = list(ids)[-MAX_PROCESSED:]
    tmp = PROCESSED_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(bounded), encoding="utf-8")
    tmp.replace(PROCESSED_FILE)

# ── Main pipeline ─────────────────────────────────────────────────────────────

async def run():
    log.info("── RSS pipeline start ──")

    feeds = json.loads(FEEDS_FILE.read_text(encoding="utf-8"))
    log.info("Feeds: %d", len(feeds))

    # Fetch all feeds concurrently
    results = await asyncio.gather(*[fetch_feed(f) for f in feeds], return_exceptions=True)
    all_articles: List[dict] = []
    for r in results:
        if not isinstance(r, Exception):
            all_articles.extend(r)
    log.info("Fetched: %d articles total", len(all_articles))

    # Filter new only
    processed = load_processed()
    new_articles = [a for a in all_articles if a["id"] not in processed]
    log.info("New: %d articles", len(new_articles))

    # Mark all as processed immediately
    for a in new_articles:
        processed.add(a["id"])
    save_processed(processed)

    if not new_articles:
        log.info("Nothing new – done")
        return

    # Phase 4: 障害検知（全新規記事を対象、Stage 1 フィルタ前）
    incidents = detect_incidents(new_articles, feeds)
    if incidents:
        save_incident_flags(incidents)

    # Stage 1: keyword filter
    candidates = stage1_filter(new_articles)
    log.info("Stage-1 candidates: %d", len(candidates))
    if not candidates:
        return

    # Gemini client
    client, types = _get_gemini()

    to_score = candidates[:MAX_SCORE_CYCLE]
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    drafted = 0

    for i, article in enumerate(to_score):
        if i > 0:
            await asyncio.sleep(API_DELAY)

        body = await extract_text(article["link"], article["summary"])
        scored_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        eligible, score = await score_article(client, types, article["title"], body)
        log.info("Score %3d/100  eligible=%-3s  %s",
                 score, "YES" if eligible else "NO", article["title"][:60])

        if not eligible:
            log.info("✗ eligible=NO — rejected at scoring gate")
            append_rss_score_history(
                scored_at=scored_at, source_url=article["link"],
                title=article["title"], eligible=eligible,
                score=score, adopted=False,
            )
            continue

        if score < SCORE_THRESHOLD:
            log.info("✗ score %d below threshold %d", score, SCORE_THRESHOLD)
            append_rss_score_history(
                scored_at=scored_at, source_url=article["link"],
                title=article["title"], eligible=eligible,
                score=score, adopted=False,
            )
            continue

        log.info("★ Threshold hit – generating draft …")
        await asyncio.sleep(API_DELAY)

        try:
            draft, skipped = await generate_draft(client, types, article, body)
        except Exception as e:
            log.error("Draft generation failed: %s", e)
            append_rss_score_history(
                scored_at=scored_at, source_url=article["link"],
                title=article["title"], eligible=eligible,
                score=score, adopted=False,
            )
            continue

        if skipped:
            log.info("✗ [[SKIP]] – generation gate rejected (no specific error in source)")
            append_rss_score_history(
                scored_at=scored_at, source_url=article["link"],
                title=article["title"], eligible=eligible,
                score=score, adopted=False, skipped_at_generation=True,
            )
            continue

        # Save draft
        slug = re.sub(r"[^\w]", "-", article["title"].lower())
        slug = re.sub(r"-+", "-", slug).strip("-")[:50]
        filename = f"auto_{date.today().strftime('%Y-%m-%d')}_{slug}.md"
        filepath = POSTS_DIR / filename
        draft = normalize_before_after(draft)
        filepath.write_text(draft, encoding="utf-8")
        log.info("SAVED  score=%d  file=%s", score, filename)
        append_rss_score_history(
            scored_at=scored_at, source_url=article["link"],
            title=article["title"], eligible=eligible,
            score=score, adopted=True,
        )
        drafted += 1

    log.info("── Pipeline end: %d drafts generated ──", drafted)


if __name__ == "__main__":
    asyncio.run(run())
