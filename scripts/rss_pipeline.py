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
from datetime import date
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


async def score_article(client, types, title: str, body: str) -> int:
    prompt = (
        "Rate how useful this tech article is for engineers facing errors (0-100).\n"
        "Criteria: specific error messages (+30), reproducible steps (+25), "
        "solution provided (+25), widely-used tools (+20).\n"
        'Return ONLY JSON: {"score": 85}\n\n'
        f"Title: {title}\n\nBody (first 600 chars):\n{body[:600]}"
    )
    try:
        raw = await _gemini_call(client, types, "gemini-2.5-flash",
                                 "You are a tech article evaluator.", prompt,
                                 temp=0.1, max_tokens=50,
                                 response_mime_type="application/json")
        m = re.search(r'"score"\s*:\s*(\d+)', raw)
        if m:
            return min(100, max(0, int(m.group(1))))
        nums = re.findall(r'\b(\d{2,3})\b', raw)
        if nums:
            return min(100, max(0, int(nums[0])))
    except Exception as e:
        log.warning("Score failed: %s — falling back to keyword score", e)
        return _keyword_score(title, body)
    return _keyword_score(title, body)

# ── Draft generation ───────────────────────────────────────────────────────────

async def generate_draft(client, types, article: dict, body: str) -> str:
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
    return await _gemini_call(client, types, "gemini-2.5-flash",
                              _DRAFT_SYSTEM, prompt, temp=0.3, max_tokens=8192)

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

        score = await score_article(client, types, article["title"], body)
        if score < 0:
            log.warning("Score parse failed: %s", article["title"][:60])
            continue

        log.info("Score %3d/100  %s", score, article["title"][:60])

        if score < SCORE_THRESHOLD:
            continue

        log.info("★ Threshold hit – generating draft …")
        await asyncio.sleep(API_DELAY)

        try:
            draft = await generate_draft(client, types, article, body)
        except Exception as e:
            log.error("Draft generation failed: %s", e)
            continue

        # Save draft
        slug = re.sub(r"[^\w]", "-", article["title"].lower())
        slug = re.sub(r"-+", "-", slug).strip("-")[:50]
        filename = f"auto_{date.today().strftime('%Y-%m-%d')}_{slug}.md"
        filepath = POSTS_DIR / filename
        draft = normalize_before_after(draft)
        filepath.write_text(draft, encoding="utf-8")
        log.info("SAVED  score=%d  file=%s", score, filename)
        drafted += 1

    log.info("── Pipeline end: %d drafts generated ──", drafted)


if __name__ == "__main__":
    asyncio.run(run())
