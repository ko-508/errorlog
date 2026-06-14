"""Build data/manual_review_queue.json from evidence sidecars.

Scans data/evidence/*.json and flags articles that meet any of:
  Condition 1: official + vendor_community source count == 0
  Condition 2: tool_match=True source count == 0
  Condition 3: unresolved source ratio >= REVIEW_UNRESOLVED_THRESHOLD

Sidecars with sources==0 (Gemini unavailable during fact check) are skipped.

Usage:
  python scripts/build_review_queue.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = BASE / "data" / "evidence"
OUTPUT_PATH = BASE / "data" / "manual_review_queue.json"

# 暫定値、サンプル蓄積後に分布を見て調整。
# 0.5 = 50%以上のsourceがgrounding-redirect未解決の場合にフラグ。
#
# 【16件サンプル時点の観察メモ】
# unresolved比率の高い記事（docker_401:32%、slack_429:29%等）はいずれも
# 条件1・2（公式根拠ゼロ・自ツール公式根拠ゼロ）に非該当で根拠は揃っている。
# unresolvedの高さは記事の質ではなくfact check実行時のリダイレクト解決の
# 取りこぼしを反映している可能性が高い。
# そのため条件3の閾値を下げてもレビュー対象の質の低い記事の検出には寄与しない
# と判断し、据え置いた。条件3の意味づけ（レビュー条件として残すか、観察指標に
# 変えるか）はサンプルがさらに蓄積してから再検討する。
REVIEW_UNRESOLVED_THRESHOLD: float = 0.5


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def evaluate_sidecar(data: dict) -> list[str]:
    """Return list of triggered condition keys, empty if no conditions met."""
    sources = data.get("sources", [])
    if not sources:
        return []  # unavailable / no data — skip

    summary = data.get("evidence_summary", {})
    official_vc = summary.get("official", 0) + summary.get("vendor_community", 0)
    tool_match_count = sum(1 for s in sources if s.get("tool_match"))
    unresolved = summary.get("unresolved", 0)
    total = len(sources)
    unresolved_ratio = unresolved / total if total else 0.0

    triggered: list[str] = []
    if official_vc == 0:
        triggered.append("no_official_or_vendor_community_sources")
    if tool_match_count == 0:
        triggered.append("no_tool_match_sources")
    if unresolved_ratio >= REVIEW_UNRESOLVED_THRESHOLD:
        triggered.append(
            f"high_unresolved_ratio:{unresolved}/{total}={unresolved_ratio:.0%}"
            f"(threshold={REVIEW_UNRESOLVED_THRESHOLD:.0%})"
        )
    return triggered


def build_queue() -> tuple[list[dict], list[dict]]:
    """Return (review_queue, incomplete_list).

    review_queue: articles with sources > 0 that triggered at least one condition.
    incomplete_list: articles whose sidecar has sources == 0 (fact check did not complete).
    """
    if not EVIDENCE_DIR.exists():
        print(f"[build_review_queue] EVIDENCE_DIR not found: {EVIDENCE_DIR}")
        return [], []

    files = sorted(EVIDENCE_DIR.glob("*.json"))
    print(f"Scanning {len(files)} sidecars in {EVIDENCE_DIR.relative_to(BASE)}")

    queue: list[dict] = []
    incomplete: list[dict] = []

    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  SKIP (parse error): {f.name}: {exc}")
            continue

        sources = data.get("sources", [])
        if not sources:
            incomplete.append({
                "article_id": data.get("article_id", f.stem),
                "article_path": data.get("article_path", ""),
                "fact_checked_at": data.get("fact_checked_at", ""),
            })
            continue

        triggered = evaluate_sidecar(data)
        if not triggered:
            continue

        queue.append({
            "article_id": data.get("article_id", f.stem),
            "article_path": data.get("article_path", ""),
            "tags": data.get("tags", []),
            "triggered_conditions": triggered,
            "evidence_summary": data.get("evidence_summary", {}),
            "fact_checked_at": data.get("fact_checked_at", ""),
            "evaluated_at": _utc_now_iso(),
        })

    print(f"  fact_check_incomplete (sources=0): {len(incomplete)}")
    print(f"  review queue entries: {len(queue)}")
    return queue, incomplete


def main() -> None:
    from collections import Counter

    queue, incomplete = build_queue()

    cond_counter: Counter[str] = Counter()
    for entry in queue:
        for cond in entry["triggered_conditions"]:
            cond_counter[cond.split(":")[0]] += 1

    output = {
        "generated_at": _utc_now_iso(),
        "threshold_unresolved": REVIEW_UNRESOLVED_THRESHOLD,
        "total_entries": len(queue),
        "entries": queue,
        "fact_check_incomplete": {
            "total": len(incomplete),
            "articles": incomplete,
        },
    }
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Written: {OUTPUT_PATH.relative_to(BASE)}")

    if cond_counter:
        print("\nCondition breakdown:")
        for cond, count in cond_counter.most_common():
            print(f"  {cond}: {count}")


if __name__ == "__main__":
    main()
