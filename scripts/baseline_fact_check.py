#!/usr/bin/env python3
"""Baseline fact-check scoring batch.

Modes
-----
  default      Score all content/posts/*.md once and append to JSONL.
  --repeat-set Stratified 30-article set, 3 rounds round-robin.

Identified in JSONL with workflow="baseline" (set unconditionally below).
Side effects limited to: data/fact_check_score_history.jsonl, progress files.
reports/ / rewrite_candidates.json / unavailable_history.json are NOT written.
"""
from __future__ import annotations

# Set workflow identifier before importing fact_check so append_score_history()
# records workflow="baseline" for every evaluation in this batch.
import os
os.environ["GITHUB_WORKFLOW"] = "baseline"

import argparse
import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from fact_check import (
    BASE as FC_BASE,
    POSTS_DIR,
    FactCheckResult,
    evaluate_content,
    save_report,
    split_frontmatter,
)

# ── Paths ────────────────────────────────────────────────────────────────────

PROGRESS_PATH = BASE / "data" / "baseline_progress.json"
REPEAT_SET_PATH = BASE / "data" / "baseline_repeat_set.json"

# ── Constants ────────────────────────────────────────────────────────────────

STRATIFY_DAILY = 20
STRATIFY_RSS = 10
STRATIFY_TOOL_MAX = 2
STRATIFY_EXTREME_N = 2
REPEAT_ROUNDS = 3
MAX_RETRIES = 3


# ── Utilities ────────────────────────────────────────────────────────────────

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_tool(path: Path) -> str:
    """First tag value, used as the tool bucket for stratification."""
    try:
        fm, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        raw = fm.get("tags", "")
        return re.sub(r"[\[\]\"\'()]", "", raw.split(",")[0]).strip()
    except Exception:
        return path.stem.rsplit("_", 1)[0]


def get_body_len(path: Path) -> int:
    """Character count of article body (frontmatter excluded)."""
    try:
        _, body = split_frontmatter(path.read_text(encoding="utf-8"))
        return len(body)
    except Exception:
        return 0


# ── Stratified sampling ──────────────────────────────────────────────────────

def _stratify_pool(
    pool: list[Path],
    n: int,
    tool_fn: Callable[[Path], str],
    len_fn: Callable[[Path], int],
    tool_max: int,
    extreme_n: int,
    seed: int,
) -> list[Path]:
    """Select n articles from pool with tool diversity and length extremes."""
    if not pool or n <= 0:
        return []

    by_len = sorted(pool, key=len_fn)

    # Force-include extreme_n shortest and extreme_n longest articles.
    must: list[Path] = []
    seen: set[Path] = set()
    for p in by_len[:extreme_n]:
        if p not in seen:
            must.append(p)
            seen.add(p)
    for p in by_len[-extreme_n:]:
        if p not in seen:
            must.append(p)
            seen.add(p)

    tool_count: dict[str, int] = {}
    selected: list[Path] = []

    for p in must:
        t = tool_fn(p)
        if tool_count.get(t, 0) < tool_max:
            selected.append(p)
            tool_count[t] = tool_count.get(t, 0) + 1

    rng = random.Random(seed)
    remaining = [p for p in pool if p not in set(selected)]
    rng.shuffle(remaining)

    for p in remaining:
        if len(selected) >= n:
            break
        t = tool_fn(p)
        if tool_count.get(t, 0) < tool_max:
            selected.append(p)
            tool_count[t] = tool_count.get(t, 0) + 1

    return selected[:n]


def stratify_repeat_set(
    daily: list[Path],
    rss: list[Path],
    seed: int = 42,
    _tool_fn: Callable[[Path], str] | None = None,
    _len_fn: Callable[[Path], int] | None = None,
) -> list[Path]:
    """Stratify STRATIFY_DAILY from daily pool + STRATIFY_RSS from RSS pool.

    _tool_fn / _len_fn can be injected for unit testing without file I/O.
    """
    tool_fn = _tool_fn or get_tool
    len_fn = _len_fn or get_body_len
    daily_sel = _stratify_pool(daily, STRATIFY_DAILY, tool_fn, len_fn, STRATIFY_TOOL_MAX, STRATIFY_EXTREME_N, seed)
    rss_sel = _stratify_pool(rss, STRATIFY_RSS, tool_fn, len_fn, STRATIFY_TOOL_MAX, STRATIFY_EXTREME_N, seed)
    return daily_sel + rss_sel


# ── Scoring with retry ────────────────────────────────────────────────────────

def score_with_retry(path: Path, sleep_seconds: float) -> FactCheckResult:
    """Evaluate one article; exponential backoff on unavailable (max MAX_RETRIES attempts)."""
    if not path.exists():
        rel = str(path.relative_to(FC_BASE).as_posix())
        return FactCheckResult(
            path=rel,
            title=path.stem,
            mode="existing",
            scores={},
            passed=False,
            critical=False,
            reasons=["File not found — deleted after selection."],
            required_actions=[],
            detected_at=utc_now_iso(),
            status="failed_fact_check",
            score_valid=False,
            error_detail="file not found (deleted after selection)",
        )

    base_delay = max(sleep_seconds, 30.0)
    last: FactCheckResult | None = None
    for attempt in range(MAX_RETRIES):
        rel = path.relative_to(FC_BASE)
        result = evaluate_content(rel, path.read_text(encoding="utf-8"), "existing")
        last = result
        if result.status not in {"fact_check_unavailable"}:
            return result
        if attempt < MAX_RETRIES - 1:
            wait = base_delay * (2 ** attempt)
            print(f"    [retry {attempt + 1}/{MAX_RETRIES - 1}] unavailable, waiting {wait:.0f}s ...")
            time.sleep(wait)
    return last  # type: ignore[return-value]


# ── Progress tracking ─────────────────────────────────────────────────────────

def load_progress(mode: str) -> set[str]:
    """Return set of already-completed keys (rel_path or rel_path::round_idx)."""
    if not PROGRESS_PATH.exists():
        return set()
    try:
        data = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
        if data.get("mode") != mode:
            return set()
        return set(data.get("scored", []))
    except Exception:
        return set()


def save_progress(mode: str, scored: list[str], started_at: str) -> None:
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_PATH.write_text(
        json.dumps(
            {"mode": mode, "scored": scored, "started_at": started_at, "last_updated": utc_now_iso()},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


# ── CLI helpers ───────────────────────────────────────────────────────────────

def confirm_or_exit(msg: str, yes: bool) -> None:
    if yes:
        print(f"{msg}  (--yes, proceeding)")
        return
    answer = input(f"{msg}  Continue? [y/N] ").strip().lower()
    if answer not in ("y", "yes"):
        print("Aborted.")
        sys.exit(0)


def _exec_status(result: FactCheckResult) -> str:
    return result.status if result.status in {"fact_check_unavailable", "failed_fact_check"} else "ok"


def _score_line(result: FactCheckResult) -> str:
    s = result.scores
    if result.score_valid:
        return f"factual={s['factual_score']} risk={s['risk_score']}"
    return "factual=null risk=null"


def _filter_existing_paths(paths: list[Path], label: str) -> list[Path]:
    existing = [p for p in paths if p.exists()]
    missing = [p for p in paths if not p.exists()]
    if missing:
        print(f"[baseline] Skipping {len(missing)} missing {label} path(s):")
        for p in missing:
            try:
                rel = p.relative_to(FC_BASE).as_posix()
            except ValueError:
                rel = str(p)
            print(f"           missing: {rel}")
    return existing


# ── Full run ──────────────────────────────────────────────────────────────────

def run_full(args: argparse.Namespace) -> int:
    posts = sorted(POSTS_DIR.glob("*.md"))
    if args.limit:
        posts = posts[: args.limit]

    n = len(posts)
    est_s = n * (args.sleep + 15)
    print(f"[baseline] Full run: {n} articles  est. ~{est_s // 60} min  (sleep={args.sleep}s)")
    confirm_or_exit(f"Score {n} articles?", args.yes)

    already = load_progress("full") if args.resume else set()
    if already:
        print(f"[baseline] Resuming: {len(already)} done, {n - len(already)} remaining")

    started_at = utc_now_iso()
    scored: list[str] = list(already)
    counts: dict[str, int] = {"ok": 0, "fact_check_unavailable": 0, "failed_fact_check": 0}
    todo = [p for p in posts if str(p.relative_to(FC_BASE).as_posix()) not in already]
    t0 = time.monotonic()

    for i, path in enumerate(todo, 1):
        rel = str(path.relative_to(FC_BASE).as_posix())
        if not path.exists():
            print(f"[baseline] ({i}/{len(todo)}) {rel}  skipped  missing file")
            scored.append(rel)
            save_progress("full", scored, started_at)
            continue
        if i > 1:
            time.sleep(args.sleep)
        result = score_with_retry(path, args.sleep)
        save_report(result, write_report=False)
        st = _exec_status(result)
        counts[st] = counts.get(st, 0) + 1
        print(f"[baseline] ({i}/{len(todo)}) {rel}  {st}  {_score_line(result)}")
        if st != "ok" and result.error_detail:
            print(f"           error_detail: {result.error_detail}")
        scored.append(rel)
        save_progress("full", scored, started_at)

    elapsed = time.monotonic() - t0
    print(
        f"\n[baseline-summary] mode=full  total={len(todo)}"
        f"  ok={counts['ok']}  unavailable={counts['fact_check_unavailable']}"
        f"  failed={counts['failed_fact_check']}  elapsed={elapsed:.0f}s"
    )
    return 0


# ── Repeat-set run ────────────────────────────────────────────────────────────

def run_repeat_set(args: argparse.Namespace) -> int:
    posts = sorted(POSTS_DIR.glob("*.md"))
    daily = [p for p in posts if not p.stem.startswith("auto_")]
    rss = [p for p in posts if p.stem.startswith("auto_")]

    # Load or create repeat set
    if REPEAT_SET_PATH.exists():
        data = json.loads(REPEAT_SET_PATH.read_text(encoding="utf-8"))
        repeat_paths = _filter_existing_paths([FC_BASE / p for p in data["paths"]], "repeat-set")
        print(
            f"[baseline] Loaded repeat set ({len(repeat_paths)} articles) from {REPEAT_SET_PATH.name}"
            f"  daily={data.get('daily_count')}  rss={data.get('rss_count')}"
        )
    else:
        selected = stratify_repeat_set(daily, rss)
        repeat_paths = selected
        daily_n = sum(1 for p in repeat_paths if not p.stem.startswith("auto_"))
        rss_n = sum(1 for p in repeat_paths if p.stem.startswith("auto_"))
        set_data = {
            "created_at": utc_now_iso(),
            "paths": [str(p.relative_to(FC_BASE).as_posix()) for p in repeat_paths],
            "daily_count": daily_n,
            "rss_count": rss_n,
        }
        REPEAT_SET_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPEAT_SET_PATH.write_text(json.dumps(set_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            f"[baseline] Created repeat set: {len(repeat_paths)} articles saved to {REPEAT_SET_PATH.name}"
            f"  daily={daily_n}  rss={rss_n}"
        )

    n = len(repeat_paths)
    total = n * REPEAT_ROUNDS
    est_s = total * (args.sleep + 15)
    print(
        f"[baseline] Repeat set: {n} articles × {REPEAT_ROUNDS} rounds = {total} requests"
        f"  est. ~{est_s // 60} min  (sleep={args.sleep}s)"
    )
    confirm_or_exit(f"Score {total} evaluations?", args.yes)

    # Round-robin job list: [round1_all, round2_all, round3_all]
    all_jobs: list[tuple[Path, int]] = [
        (path, round_idx)
        for round_idx in range(1, REPEAT_ROUNDS + 1)
        for path in repeat_paths
    ]
    already = load_progress("repeat") if args.resume else set()
    todo = [
        (path, ri)
        for path, ri in all_jobs
        if f"{path.relative_to(FC_BASE).as_posix()}::{ri}" not in already
    ]
    if already:
        print(f"[baseline] Resuming: {len(already)} done, {len(todo)} remaining")

    started_at = utc_now_iso()
    scored_keys: list[str] = list(already)
    counts: dict[str, int] = {"ok": 0, "fact_check_unavailable": 0, "failed_fact_check": 0}
    hash_by_path: dict[str, set[str]] = {}
    t0 = time.monotonic()

    for i, (path, round_idx) in enumerate(todo, 1):
        rel = str(path.relative_to(FC_BASE).as_posix())
        if not path.exists():
            print(f"[baseline] ({i}/{len(todo)}) round={round_idx}  {rel}  skipped  missing file")
            scored_keys.append(f"{rel}::{round_idx}")
            save_progress("repeat", scored_keys, started_at)
            continue
        if i > 1:
            time.sleep(args.sleep)
        result = score_with_retry(path, args.sleep)
        save_report(result, write_report=False)
        st = _exec_status(result)
        counts[st] = counts.get(st, 0) + 1
        if result.article_hash:
            hash_by_path.setdefault(rel, set()).add(result.article_hash)
        print(f"[baseline] ({i}/{len(todo)}) round={round_idx}  {rel}  {st}  {_score_line(result)}")
        if st != "ok" and result.error_detail:
            print(f"           error_detail: {result.error_detail}")
        scored_keys.append(f"{rel}::{round_idx}")
        save_progress("repeat", scored_keys, started_at)

    elapsed = time.monotonic() - t0

    # article_hash consistency self-verification
    mismatches = {p: h for p, h in hash_by_path.items() if len(h) > 1}
    if mismatches:
        print(f"\n[baseline] WARNING: article_hash mismatch in {len(mismatches)} articles (content changed during run):")
        for p, hashes in sorted(mismatches.items()):
            print(f"  {p}: {sorted(hashes)}")
    else:
        print(f"\n[baseline] article_hash consistency: OK  (all {len(hash_by_path)} articles unchanged across rounds)")

    print(
        f"[baseline-summary] mode=repeat  total={len(todo)}"
        f"  ok={counts['ok']}  unavailable={counts['fact_check_unavailable']}"
        f"  failed={counts['failed_fact_check']}"
        f"  hash_mismatches={len(mismatches)}  elapsed={elapsed:.0f}s"
    )
    return 0


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Baseline fact-check scoring batch")
    parser.add_argument("--repeat-set", action="store_true", help="Run stratified 30-article × 3-round set")
    parser.add_argument("--limit", type=int, default=0, help="Limit article count (full mode only, for smoke-test)")
    parser.add_argument("--sleep", type=float, default=10.0, help="Seconds between requests (default 10)")
    parser.add_argument("--resume", action="store_true", help="Skip already-scored articles (reads progress file)")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    if args.repeat_set:
        raise SystemExit(run_repeat_set(args))
    raise SystemExit(run_full(args))


if __name__ == "__main__":
    main()
