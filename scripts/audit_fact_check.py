"""
採点器監査スクリプト — fact_check_score_history.jsonl を分析して
採点器の再現性・判別力・安定性を定量評価する。

出力:
  reports/audit/audit_summary.md
  reports/audit/audit_detail.json
  reports/audit/figures/*.png

使用方法:
  python scripts/audit_fact_check.py
  python scripts/audit_fact_check.py --since 2026-06-01 --until 2026-06-30
  python scripts/audit_fact_check.py --model gemini-2.5-flash
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import warnings
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parent.parent
JSONL_PATH      = REPO / "run" / "fact_check_score_history.jsonl"
DELETED_PATH    = REPO / "data" / "deleted_articles.json"
POSTS_DIR       = REPO / "content" / "posts"
AUDIT_DIR       = REPO / "reports" / "audit"
FIGURES_DIR     = AUDIT_DIR / "figures"
SUMMARY_PATH    = AUDIT_DIR / "audit_summary.md"
DETAIL_PATH     = AUDIT_DIR / "audit_detail.json"

# ── Score axes and thresholds ─────────────────────────────────────────────────
AXES        = ("factual_score", "freshness_score", "citation_coverage", "risk_score")
AXIS_LABELS = {
    "factual_score":     "Factual",
    "freshness_score":   "Freshness",
    "citation_coverage": "Citation Cov.",
    "risk_score":        "Risk",
}
# (direction, threshold_value): "min" = score must be >= value; "max" = score must be <= value
THRESHOLDS = {
    "factual_score":     ("min", 75),
    "freshness_score":   ("min", 50),
    "citation_coverage": ("min", 10),
    "risk_score":        ("max", 55),
}
AXIS_COLORS = {
    "factual_score":     "#4c72b0",
    "freshness_score":   "#55a868",
    "citation_coverage": "#c44e52",
    "risk_score":        "#dd8452",
}


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _rankdata(arr: np.ndarray) -> np.ndarray:
    """Average-rank (handles ties). Pure numpy, no scipy."""
    n = len(arr)
    sorted_idx = np.argsort(arr, kind="stable")
    ranks = np.empty(n, dtype=float)
    i = 0
    while i < n:
        j = i
        while j < n - 1 and arr[sorted_idx[j]] == arr[sorted_idx[j + 1]]:
            j += 1
        rank_val = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[sorted_idx[k]] = rank_val
        i = j + 1
    return ranks


def spearman_r(x: list, y: list) -> float:
    """Spearman ρ without scipy."""
    xa = np.asarray([v for v in x if v is not None], dtype=float)
    ya = np.asarray([v for v in y if v is not None], dtype=float)
    mask = np.isfinite(xa) & np.isfinite(ya)
    xa, ya = xa[mask], ya[mask]
    if len(xa) < 3:
        return float("nan")
    rx = _rankdata(xa)
    ry = _rankdata(ya)
    rx -= rx.mean()
    ry -= ry.mean()
    denom = math.sqrt((rx**2).sum() * (ry**2).sum())
    return float((rx * ry).sum() / denom) if denom > 0 else float("nan")


def percentile(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return float("nan")
    return float(np.percentile(arr, p))


def _passes_gate(rec: dict) -> bool | None:
    """Binary gate from scores. Returns None when scores are missing."""
    for ax in AXES:
        if _safe_float(rec.get(ax)) is None:
            return None
    return (
        rec["factual_score"] >= THRESHOLDS["factual_score"][1]
        and rec["freshness_score"] >= THRESHOLDS["freshness_score"][1]
        and rec["citation_coverage"] >= THRESHOLDS["citation_coverage"][1]
        and rec["risk_score"] <= THRESHOLDS["risk_score"][1]
    )


def _axis_passes(rec: dict, ax: str) -> bool | None:
    v = _safe_float(rec.get(ax))
    if v is None:
        return None
    direction, threshold = THRESHOLDS[ax]
    return v >= threshold if direction == "min" else v <= threshold


# ══════════════════════════════════════════════════════════════════════════════
# Data loading
# ══════════════════════════════════════════════════════════════════════════════

def load_records(
    since: datetime | None,
    until: datetime | None,
) -> tuple[list[dict], list[str]]:
    """Load JSONL, warn on eval_id dupes, apply date filter. Returns (records, warnings)."""
    warns: list[str] = []
    raw: dict[str, dict] = {}

    if not JSONL_PATH.exists():
        warns.append(f"JSONL not found: {JSONL_PATH}")
        return [], warns

    for lineno, line in enumerate(JSONL_PATH.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as exc:
            warns.append(f"Line {lineno}: JSON parse error — {exc}")
            continue
        eid = rec.get("eval_id") or f"_noid_{lineno}"
        if eid in raw:
            warns.append(f"Duplicate eval_id={eid!r} at line {lineno} — keeping last")
        raw[eid] = rec

    records = list(raw.values())

    # Date filter
    if since or until:
        filtered = []
        for r in records:
            ts_str = r.get("checked_at", "")
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                ts = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
            except (ValueError, AttributeError):
                filtered.append(r)
                continue
            if since and ts < since:
                continue
            if until and ts > until:
                continue
            filtered.append(r)
        records = filtered

    return records, warns


def add_deleted_flag(records: list[dict]) -> dict[str, bool]:
    """Return set of paths in deleted_articles.json, add 'deleted' key to records."""
    deleted_paths: set[str] = set()
    if DELETED_PATH.exists():
        try:
            data = json.loads(DELETED_PATH.read_text(encoding="utf-8"))
            deleted_paths = {e["path"] for e in data if isinstance(e, dict) and "path" in e}
        except Exception:
            pass
    for r in records:
        r["_deleted"] = r.get("path", "") in deleted_paths
    return deleted_paths


def add_article_type(records: list[dict]) -> None:
    """Add '_article_type' key: 'rss' for auto_* files, 'daily' otherwise."""
    for r in records:
        stem = Path(r.get("path", "")).name
        r["_article_type"] = "rss" if stem.startswith("auto_") else "daily"


def _read_tags_from_frontmatter(path: Path) -> list[str]:
    """Extract tags list from frontmatter. Returns [] on any failure."""
    try:
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            return []
        end = text.find("\n---", 3)
        if end == -1:
            return []
        fm_text = text[3:end]
        for line in fm_text.splitlines():
            m = re.match(r"^tags:\s*(.+)", line)
            if m:
                val = m.group(1).strip()
                # ["Foo", "Bar"] or [Foo, Bar]
                tags = re.findall(r'"([^"]+)"|\b([A-Za-z][A-Za-z0-9_\-\.]+)', val)
                result = [a or b for a, b in tags]
                return [t for t in result if t and t not in ("true", "false", "null")]
    except Exception:
        pass
    return []


def add_tool_name(records: list[dict]) -> None:
    """Add '_tool' key from frontmatter tags, 'deleted' if file missing."""
    _cache: dict[str, str] = {}
    for r in records:
        path_str = r.get("path", "")
        if path_str in _cache:
            r["_tool"] = _cache[path_str]
            continue
        full = REPO / path_str
        if not full.exists():
            tool = "deleted"
        else:
            tags = _read_tags_from_frontmatter(full)
            tool = tags[0] if tags else "unknown"
        _cache[path_str] = tool
        r["_tool"] = tool


def build_rescore_groups(ok_records: list[dict]) -> tuple[dict, dict, list[str]]:
    """
    Build pure rescore groups (same path + same article_hash, ≥2 records).
    Returns:
      pure_groups  : {path: [rec, ...]}  — hash-stable groups
      hash_changed : {path: int}         — paths with multiple hashes (excluded)
      notes        : informational strings
    """
    by_path: dict[str, list[dict]] = defaultdict(list)
    for r in ok_records:
        by_path[r.get("path", "")].append(r)

    pure_groups: dict[str, list[dict]] = {}
    hash_changed: dict[str, int] = {}
    notes: list[str] = []

    for path, recs in by_path.items():
        hashes = {r.get("article_hash") for r in recs}
        if len(hashes) > 1:
            hash_changed[path] = len(recs)
            notes.append(
                f"  {path}: {len(recs)} records spanning {len(hashes)} distinct hashes"
            )
        elif len(recs) >= 2:
            pure_groups[path] = recs

    return pure_groups, hash_changed, notes


# ══════════════════════════════════════════════════════════════════════════════
# Analysis A — Rescore variance
# ══════════════════════════════════════════════════════════════════════════════

def analyze_rescore_variance(pure_groups: dict[str, list[dict]]) -> dict:
    if not pure_groups:
        return {"n_groups": 0, "axes": {}, "top5_worst": []}

    axis_ranges: dict[str, list[float]] = {ax: [] for ax in AXES}
    axis_stds:   dict[str, list[float]] = {ax: [] for ax in AXES}
    worst_by_factual: list[tuple[float, str, dict]] = []

    for path, recs in pure_groups.items():
        per_ax_range = {}
        for ax in AXES:
            vals = [_safe_float(r.get(ax)) for r in recs]
            vals = [v for v in vals if v is not None]
            if len(vals) < 2:
                continue
            rng = max(vals) - min(vals)
            std = float(np.std(vals, ddof=0))
            axis_ranges[ax].append(rng)
            axis_stds[ax].append(std)
            per_ax_range[ax] = rng
        factual_range = per_ax_range.get("factual_score", 0.0)
        scores_snapshot = {ax: [_safe_float(r.get(ax)) for r in recs] for ax in AXES}
        worst_by_factual.append((factual_range, path, scores_snapshot))

    worst_by_factual.sort(key=lambda t: t[0], reverse=True)
    top5 = []
    for rng, path, scores in worst_by_factual[:5]:
        top5.append({"path": path, "factual_range": rng, "scores": scores})

    axes_summary: dict[str, dict] = {}
    for ax in AXES:
        rngs = axis_ranges[ax]
        stds = axis_stds[ax]
        if not rngs:
            axes_summary[ax] = {"n_groups": 0, "range_median": None,
                                 "range_p90": None, "range_max": None,
                                 "std_median": None, "verdict": "insufficient data"}
            continue
        med = percentile(rngs, 50)
        p90 = percentile(rngs, 90)
        mxv = max(rngs)
        axes_summary[ax] = {
            "n_groups":     len(rngs),
            "range_median": round(med, 2),
            "range_p90":    round(p90, 2),
            "range_max":    round(mxv, 2),
            "std_median":   round(percentile(stds, 50), 2),
            "verdict":      _rescore_verdict(med) if ax == "factual_score" else None,
        }

    factual_ranges = axis_ranges.get("factual_score", [])
    overall_verdict = _rescore_verdict(percentile(factual_ranges, 50)) if factual_ranges else "insufficient data"

    return {
        "n_groups":       len(pure_groups),
        "axes":           axes_summary,
        "top5_worst":     top5,
        "overall_verdict": overall_verdict,
    }


def _rescore_verdict(median_range: float) -> str:
    if math.isnan(median_range):
        return "insufficient data"
    if median_range < 5:
        return "安定 (<5)"
    if median_range <= 15:
        return "グレーゾーン多数決を検討 (5-15)"
    return "ゲート設計の見直しが必要 (>15)"


# ══════════════════════════════════════════════════════════════════════════════
# Analysis B — Pass/fail flip rate
# ══════════════════════════════════════════════════════════════════════════════

def analyze_flip_rate(
    pure_groups: dict[str, list[dict]],
    ok_records:  list[dict],
) -> dict:
    # Overall discrepancy between recalc and stored overall_judgement
    discrepancy_count = 0
    for r in ok_records:
        recalc = _passes_gate(r)
        stored = r.get("overall_judgement") == "pass"
        if recalc is not None and recalc != stored:
            discrepancy_count += 1

    if not pure_groups:
        return {
            "n_groups": 0,
            "flip_count": 0,
            "flip_rate": None,
            "axis_flip_cause": {},
            "verdict": "insufficient data",
            "judgement_discrepancy_count": discrepancy_count,
        }

    flip_count = 0
    axis_flip_cause: dict[str, int] = {ax: 0 for ax in AXES}

    for path, recs in pure_groups.items():
        verdicts = [_passes_gate(r) for r in recs]
        verdicts = [v for v in verdicts if v is not None]
        if len(verdicts) < 2:
            continue
        if len(set(verdicts)) > 1:
            flip_count += 1
            # Which axes crossed threshold between at least two records?
            for ax in AXES:
                ax_verdicts = [_axis_passes(r, ax) for r in recs]
                ax_verdicts = [v for v in ax_verdicts if v is not None]
                if len(set(ax_verdicts)) > 1:
                    axis_flip_cause[ax] += 1

    n = len(pure_groups)
    flip_rate = flip_count / n if n > 0 else None

    verdict = "insufficient data"
    if flip_rate is not None:
        if flip_rate < 0.10:
            verdict = "安定 (<10%)"
        elif flip_rate <= 0.25:
            verdict = "多数決導入を検討 (10-25%)"
        else:
            verdict = "ゲート再設計が必要 (>25%)"

    return {
        "n_groups":                     n,
        "flip_count":                   flip_count,
        "flip_rate":                    round(flip_rate, 4) if flip_rate is not None else None,
        "flip_rate_pct":                round(flip_rate * 100, 1) if flip_rate is not None else None,
        "axis_flip_cause":              axis_flip_cause,
        "verdict":                      verdict,
        "judgement_discrepancy_count":  discrepancy_count,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Analysis C — Threshold sensitivity
# ══════════════════════════════════════════════════════════════════════════════

def analyze_threshold_sensitivity(ok_records: list[dict], axis_range_medians: dict[str, float | None]) -> dict:
    # Latest record per path
    by_path: dict[str, dict] = {}
    for r in ok_records:
        path = r.get("path", "")
        existing = by_path.get(path)
        if existing is None or r.get("checked_at", "") > existing.get("checked_at", ""):
            by_path[path] = r
    latest = list(by_path.values())

    distributions: dict[str, dict] = {}
    grey_zone_rates: dict[str, float | None] = {}
    non_functional_axes: list[str] = []
    sensitivity_tables: dict[str, dict] = {}

    for ax in AXES:
        vals = [_safe_float(r.get(ax)) for r in latest]
        vals = [v for v in vals if v is not None]
        n = len(vals)
        if n == 0:
            distributions[ax] = {}
            grey_zone_rates[ax] = None
            continue

        direction, thresh = THRESHOLDS[ax]
        base_pass_rate = sum(1 for v in vals if (v >= thresh if direction == "min" else v <= thresh)) / n

        distributions[ax] = {
            "n":      n,
            "median": round(percentile(vals, 50), 1),
            "p10":    round(percentile(vals, 10), 1),
            "p90":    round(percentile(vals, 90), 1),
            "min":    round(min(vals), 1),
            "max":    round(max(vals), 1),
            "base_pass_rate": round(base_pass_rate, 4),
        }

        if base_pass_rate > 0.95:
            non_functional_axes.append(ax)

        # Grey zone: within ± median_range of threshold
        med_range = axis_range_medians.get(ax)
        if med_range is not None and med_range > 0:
            if direction == "min":
                grey = sum(1 for v in vals if thresh - med_range <= v < thresh + med_range) / n
            else:
                grey = sum(1 for v in vals if thresh - med_range < v <= thresh + med_range) / n
            grey_zone_rates[ax] = round(grey, 4)
        else:
            grey_zone_rates[ax] = None

        # Sensitivity table: ±5, ±10
        table: dict[str, dict] = {}
        for delta in (-10, -5, 0, 5, 10):
            t2 = thresh + delta
            pr = sum(1 for v in vals if (v >= t2 if direction == "min" else v <= t2)) / n
            table[str(delta)] = {"threshold": t2, "pass_rate": round(pr, 4)}
        sensitivity_tables[ax] = table

    # Overall grey zone rate (at least one axis in grey zone)
    overall_grey: float | None = None
    if latest:
        grey_vals = []
        for r in latest:
            in_grey = False
            for ax in AXES:
                v = _safe_float(r.get(ax))
                med_range = axis_range_medians.get(ax)
                if v is None or med_range is None or med_range == 0:
                    continue
                direction, thresh = THRESHOLDS[ax]
                if direction == "min":
                    if thresh - med_range <= v < thresh + med_range:
                        in_grey = True
                else:
                    if thresh - med_range < v <= thresh + med_range:
                        in_grey = True
            grey_vals.append(1 if in_grey else 0)
        overall_grey = round(sum(grey_vals) / len(grey_vals), 4) if grey_vals else None

    return {
        "n_latest":            len(latest),
        "distributions":       distributions,
        "grey_zone_rates":     grey_zone_rates,
        "overall_grey_zone":   overall_grey,
        "non_functional_axes": non_functional_axes,
        "sensitivity_tables":  sensitivity_tables,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Analysis D — Axis correlations
# ══════════════════════════════════════════════════════════════════════════════

def analyze_correlations(ok_records: list[dict]) -> dict:
    # Latest per path
    by_path: dict[str, dict] = {}
    for r in ok_records:
        path = r.get("path", "")
        if path not in by_path or r.get("checked_at", "") > by_path[path].get("checked_at", ""):
            by_path[path] = r
    latest = list(by_path.values())

    axis_vals: dict[str, list[float]] = {ax: [] for ax in AXES}
    for r in latest:
        any_missing = any(_safe_float(r.get(ax)) is None for ax in AXES)
        if any_missing:
            continue
        for ax in AXES:
            axis_vals[ax].append(_safe_float(r.get(ax)))

    n = len(axis_vals[AXES[0]])
    corr_matrix: dict[str, dict[str, float]] = {}
    redundant_pairs: list[dict] = []

    for ax1 in AXES:
        corr_matrix[ax1] = {}
        for ax2 in AXES:
            r_val = spearman_r(axis_vals[ax1], axis_vals[ax2])
            corr_matrix[ax1][ax2] = round(r_val, 3) if not math.isnan(r_val) else None

    for i, ax1 in enumerate(AXES):
        for ax2 in AXES[i+1:]:
            rv = corr_matrix[ax1].get(ax2)
            if rv is not None and abs(rv) > 0.8:
                redundant_pairs.append({"axes": [ax1, ax2], "rho": rv})

    return {
        "n":               n,
        "corr_matrix":     corr_matrix,
        "redundant_pairs": redundant_pairs,
        "axis_vals":       axis_vals,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Analysis E — Time series drift
# ══════════════════════════════════════════════════════════════════════════════

def analyze_timeseries(ok_records: list[dict], all_records: list[dict]) -> dict:
    # Detect model/version change points across ALL records
    change_points: list[dict] = []
    seen_models:   set[str] = set()
    seen_versions: set[str] = set()
    for r in sorted(all_records, key=lambda x: x.get("checked_at", "")):
        m = r.get("gemini_model", "")
        v = r.get("prompt_version", "")
        if m and m not in seen_models:
            if seen_models:
                change_points.append({"type": "model", "value": m, "at": r.get("checked_at", "")})
            seen_models.add(m)
        if v and v not in seen_versions:
            if seen_versions:
                change_points.append({"type": "prompt_version", "value": v, "at": r.get("checked_at", "")})
            seen_versions.add(v)

    # Weekly bins
    bins: dict[str, dict[str, list[float]]] = {}
    for r in ok_records:
        ts_str = r.get("checked_at", "")
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        # ISO week key
        week_key = ts.strftime("%Y-W%W")
        if week_key not in bins:
            bins[week_key] = {ax: [] for ax in AXES}
        for ax in AXES:
            v = _safe_float(r.get(ax))
            if v is not None:
                bins[week_key][ax].append(v)

    weekly: dict[str, dict] = {}
    for wk, ax_vals in sorted(bins.items()):
        weekly[wk] = {
            ax: round(float(np.median(v)), 1) if v else None
            for ax, v in ax_vals.items()
        }
        weekly[wk]["n"] = sum(len(v) for v in ax_vals.values() if v) // len(AXES)

    return {
        "n_weeks":      len(weekly),
        "weekly":       weekly,
        "change_points": change_points,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Analysis F — Segment analysis
# ══════════════════════════════════════════════════════════════════════════════

def analyze_segments(ok_records: list[dict]) -> dict:
    # Latest per path
    by_path: dict[str, dict] = {}
    for r in ok_records:
        path = r.get("path", "")
        if path not in by_path or r.get("checked_at", "") > by_path[path].get("checked_at", ""):
            by_path[path] = r
    latest = list(by_path.values())

    def _group(r: dict) -> str:
        if r.get("_deleted"):
            return "deleted"
        return r.get("_article_type", "daily")

    groups = {"daily": [], "rss": [], "deleted": []}
    for r in latest:
        groups[_group(r)].append(r)

    segment_stats: dict[str, dict] = {}
    for grp, recs in groups.items():
        n = len(recs)
        ax_stats: dict[str, dict] = {}
        for ax in AXES:
            vals = [_safe_float(r.get(ax)) for r in recs]
            vals = [v for v in vals if v is not None]
            if vals:
                ax_stats[ax] = {
                    "n":      len(vals),
                    "median": round(percentile(vals, 50), 1),
                    "p25":    round(percentile(vals, 25), 1),
                    "p75":    round(percentile(vals, 75), 1),
                    "min":    round(min(vals), 1),
                    "max":    round(max(vals), 1),
                }
            else:
                ax_stats[ax] = {"n": 0}
        segment_stats[grp] = {"n": n, "axes": ax_stats}

    # Hypothesis testing (descriptive only, n may be too small)
    hypo_risk = {}
    hypo_factual = {}
    for grp in ("daily", "rss", "deleted"):
        recs = groups[grp]
        risk_vals    = [_safe_float(r.get("risk_score")) for r in recs]
        factual_vals = [_safe_float(r.get("factual_score")) for r in recs]
        risk_vals    = [v for v in risk_vals if v is not None]
        factual_vals = [v for v in factual_vals if v is not None]
        hypo_risk[grp]    = {"n": len(risk_vals),    "median": round(percentile(risk_vals, 50), 1)    if risk_vals    else None}
        hypo_factual[grp] = {"n": len(factual_vals), "median": round(percentile(factual_vals, 50), 1) if factual_vals else None}

    # Tool-level median table (n >= 3)
    tool_buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: {ax: [] for ax in AXES})
    for r in latest:
        tool = r.get("_tool", "unknown")
        for ax in AXES:
            v = _safe_float(r.get(ax))
            if v is not None:
                tool_buckets[tool][ax].append(v)

    tool_table: dict[str, dict] = {}
    for tool, ax_vals in tool_buckets.items():
        n = max(len(v) for v in ax_vals.values()) if ax_vals else 0
        if n >= 3:
            tool_table[tool] = {
                "n": n,
                **{ax: round(percentile(v, 50), 1) if v else None for ax, v in ax_vals.items()},
            }

    # For raw box plot data (figures), include all records per segment+axis
    raw_for_plot: dict[str, dict[str, list[float]]] = {}
    for grp, recs in groups.items():
        raw_for_plot[grp] = {}
        for ax in AXES:
            vals = [_safe_float(r.get(ax)) for r in recs]
            raw_for_plot[grp][ax] = [v for v in vals if v is not None]

    return {
        "segment_stats":  segment_stats,
        "hypothesis_risk":    hypo_risk,
        "hypothesis_factual": hypo_factual,
        "tool_table":     tool_table,
        "_raw_for_plot":  raw_for_plot,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Analysis G — Execution health
# ══════════════════════════════════════════════════════════════════════════════

def analyze_execution_health(all_records: list[dict]) -> dict:
    n_total = len(all_records)
    status_counts: dict[str, int] = defaultdict(int)
    for r in all_records:
        status_counts[r.get("status", "unknown")] += 1

    # error_detail frequency (normalise patterns)
    error_patterns: dict[str, int] = defaultdict(int)
    for r in all_records:
        detail = r.get("error_detail") or ""
        if not detail:
            continue
        # Normalise to first keyword
        key = re.split(r"[\s:|\n]", detail.strip())[0][:60]
        if key:
            error_patterns[key] += 1

    # url_check_status across all sources
    url_status_counts: dict[str, int] = defaultdict(int)
    grounding_count = 0
    total_sources = 0
    for r in all_records:
        for src in r.get("sources", []):
            total_sources += 1
            status = str(src.get("url_check_status", "unknown"))
            url_status_counts[status] += 1
            url = src.get("url", "")
            if "vertexaisearch" in url or "googleapis.com/v1/grounding" in url:
                grounding_count += 1

    # unsupported_claims distribution
    claim_counts: list[int] = []
    for r in all_records:
        if r.get("status") == "ok":
            claim_counts.append(len(r.get("unsupported_claims") or []))

    return {
        "n_total":          n_total,
        "status_counts":    dict(status_counts),
        "unavailable_rate": round(status_counts.get("fact_check_unavailable", 0) / n_total, 4) if n_total else 0,
        "failed_rate":      round(status_counts.get("failed_fact_check", 0) / n_total, 4)      if n_total else 0,
        "error_patterns":   dict(sorted(error_patterns.items(), key=lambda x: -x[1])[:10]),
        "url_status_counts": dict(url_status_counts),
        "total_sources":    total_sources,
        "grounding_count":  grounding_count,
        "grounding_rate":   round(grounding_count / total_sources, 4) if total_sources else 0,
        "unsupported_claims_median": round(percentile(claim_counts, 50), 1) if claim_counts else None,
        "unsupported_claims_max":    max(claim_counts) if claim_counts else None,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Figures
# ══════════════════════════════════════════════════════════════════════════════

def _savefig(name: str, fig: plt.Figure) -> str:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURES_DIR / name
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return str(path)


def plot_rescore_range(pure_groups: dict, analysis_a: dict) -> str | None:
    axes_data: dict[str, list[float]] = {ax: [] for ax in AXES}
    for path, recs in pure_groups.items():
        for ax in AXES:
            vals = [_safe_float(r.get(ax)) for r in recs]
            vals = [v for v in vals if v is not None]
            if len(vals) >= 2:
                axes_data[ax].append(max(vals) - min(vals))

    if all(len(v) == 0 for v in axes_data.values()):
        return None

    fig, axes = plt.subplots(1, 4, figsize=(14, 3.5), sharey=False)
    for i, ax_name in enumerate(AXES):
        vals = axes_data[ax_name]
        ax = axes[i]
        if not vals:
            ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
        else:
            ax.hist(vals, bins=max(5, len(vals) // 2 + 1), color=AXIS_COLORS[ax_name],
                    edgecolor="white", linewidth=0.5)
            med = percentile(vals, 50)
            ax.axvline(med, color="black", linestyle="--", linewidth=1.2,
                       label=f"median={med:.1f}")
            ax.legend(fontsize=7)
        ax.set_title(AXIS_LABELS[ax_name], fontsize=9)
        ax.set_xlabel("Within-group range", fontsize=8)
        ax.set_ylabel("# groups" if i == 0 else "", fontsize=8)
        ax.tick_params(labelsize=7)

    fig.suptitle("Analysis A: Within-group score range (pure rescore pairs)", fontsize=10, y=1.02)
    plt.tight_layout()
    return _savefig("fig_a_rescore_range.png", fig)


def plot_score_distributions(ok_records: list[dict]) -> str | None:
    # Latest per path
    by_path: dict[str, dict] = {}
    for r in ok_records:
        p = r.get("path", "")
        if p not in by_path or r.get("checked_at", "") > by_path[p].get("checked_at", ""):
            by_path[p] = r
    latest = list(by_path.values())
    if not latest:
        return None

    fig, axes = plt.subplots(1, 4, figsize=(14, 3.5))
    for i, ax_name in enumerate(AXES):
        vals = [_safe_float(r.get(ax_name)) for r in latest]
        vals = [v for v in vals if v is not None]
        ax = axes[i]
        direction, thresh = THRESHOLDS[ax_name]
        if vals:
            ax.hist(vals, bins=20, range=(0, 100), color=AXIS_COLORS[ax_name],
                    edgecolor="white", linewidth=0.5, alpha=0.85)
        ax.axvline(thresh, color="red", linestyle="-", linewidth=1.5,
                   label=f"thresh={thresh}")
        ax.set_title(AXIS_LABELS[ax_name], fontsize=9)
        ax.set_xlabel("Score", fontsize=8)
        ax.set_ylabel("# articles" if i == 0 else "", fontsize=8)
        ax.set_xlim(0, 105)
        ax.legend(fontsize=7)
        ax.tick_params(labelsize=7)

    fig.suptitle("Analysis C: Score distributions with threshold markers (latest per article)", fontsize=10, y=1.02)
    plt.tight_layout()
    return _savefig("fig_c_distributions.png", fig)


def plot_correlations(analysis_d: dict) -> str | None:
    axis_vals = analysis_d.get("axis_vals", {})
    corr_matrix = analysis_d.get("corr_matrix", {})
    n = analysis_d.get("n", 0)
    if n < 3:
        return None

    fig, (ax_heat, ax_scatter) = plt.subplots(1, 2, figsize=(11, 4.5))

    # Heatmap
    mat = np.array([
        [corr_matrix.get(ax1, {}).get(ax2) or 0 for ax2 in AXES]
        for ax1 in AXES
    ], dtype=float)
    im = ax_heat.imshow(mat, vmin=-1, vmax=1, cmap="RdBu_r", aspect="auto")
    plt.colorbar(im, ax=ax_heat, fraction=0.046, pad=0.04)
    labels = [AXIS_LABELS[ax] for ax in AXES]
    ax_heat.set_xticks(range(len(AXES)))
    ax_heat.set_yticks(range(len(AXES)))
    ax_heat.set_xticklabels(labels, fontsize=8, rotation=30, ha="right")
    ax_heat.set_yticklabels(labels, fontsize=8)
    for i in range(len(AXES)):
        for j in range(len(AXES)):
            val = mat[i, j]
            ax_heat.text(j, i, f"{val:.2f}", ha="center", va="center",
                         fontsize=8, color="white" if abs(val) > 0.5 else "black")
    ax_heat.set_title(f"Spearman correlation (n={n})", fontsize=9)

    # Scatter: factual × risk
    x_vals = axis_vals.get("factual_score", [])
    y_vals = axis_vals.get("risk_score", [])
    if x_vals and y_vals:
        ax_scatter.scatter(x_vals, y_vals, alpha=0.6, s=30,
                           color=AXIS_COLORS["factual_score"], edgecolors="none")
        ax_scatter.axvline(THRESHOLDS["factual_score"][1], color="red", linestyle="--",
                           linewidth=1, alpha=0.7, label=f"factual≥{THRESHOLDS['factual_score'][1]}")
        ax_scatter.axhline(THRESHOLDS["risk_score"][1], color="orange", linestyle="--",
                           linewidth=1, alpha=0.7, label=f"risk≤{THRESHOLDS['risk_score'][1]}")
        ax_scatter.legend(fontsize=7)
    ax_scatter.set_xlabel("Factual score", fontsize=8)
    ax_scatter.set_ylabel("Risk score", fontsize=8)
    ax_scatter.set_title("Factual × Risk scatter", fontsize=9)
    ax_scatter.tick_params(labelsize=7)

    plt.tight_layout()
    return _savefig("fig_d_correlations.png", fig)


def plot_timeseries(analysis_e: dict) -> str | None:
    weekly = analysis_e.get("weekly", {})
    if len(weekly) < 1:
        return None

    weeks = sorted(weekly.keys())
    fig, ax = plt.subplots(figsize=(10, 4))

    for ax_name in AXES:
        ys = [weekly[wk].get(ax_name) for wk in weeks]
        ys_plot = [y if y is not None else float("nan") for y in ys]
        ax.plot(range(len(weeks)), ys_plot, marker="o", markersize=4,
                label=AXIS_LABELS[ax_name], color=AXIS_COLORS[ax_name], linewidth=1.5)

    for cp in analysis_e.get("change_points", []):
        cp_ts = cp.get("at", "")
        ax.axvline(0, color="gray", linestyle=":", linewidth=1, alpha=0.7)

    ax.set_xticks(range(len(weeks)))
    ax.set_xticklabels(weeks, rotation=30, ha="right", fontsize=7)
    ax.set_ylabel("Score median", fontsize=8)
    ax.set_ylim(0, 105)
    ax.legend(fontsize=8)
    ax.set_title("Analysis E: Weekly median scores (time-series drift)", fontsize=9)
    ax.tick_params(labelsize=7)
    plt.tight_layout()
    return _savefig("fig_e_timeseries.png", fig)


def plot_segments(analysis_f: dict) -> str | None:
    raw = analysis_f.get("_raw_for_plot", {})
    segments = ["daily", "rss", "deleted"]
    any_data = any(any(v for v in raw.get(g, {}).values()) for g in segments)
    if not any_data:
        return None

    fig, axes_row = plt.subplots(1, 4, figsize=(14, 4))
    for i, ax_name in enumerate(AXES):
        ax = axes_row[i]
        data = [raw.get(g, {}).get(ax_name, []) for g in segments]
        labels = [f"{g}\n(n={len(d)})" for g, d in zip(segments, data)]
        plot_data = [d if d else [float("nan")] for d in data]
        bp = ax.boxplot(plot_data, tick_labels=labels, patch_artist=True, notch=False,
                        medianprops={"color": "black", "linewidth": 1.5},
                        whiskerprops={"linewidth": 1},
                        capprops={"linewidth": 1},
                        flierprops={"marker": "o", "markersize": 3, "alpha": 0.5})
        colors = ["#4c72b0", "#55a868", "#c44e52"]
        for patch, color in zip(bp["boxes"], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)
        direction, thresh = THRESHOLDS[ax_name]
        ax.axhline(thresh, color="red", linestyle="--", linewidth=1, alpha=0.7,
                   label=f"thresh={thresh}")
        ax.set_title(AXIS_LABELS[ax_name], fontsize=9)
        ax.set_ylim(-5, 110)
        ax.legend(fontsize=6)
        ax.tick_params(labelsize=7)

    fig.suptitle("Analysis F: Score distribution by segment (daily / rss / deleted)", fontsize=10, y=1.01)
    plt.tight_layout()
    return _savefig("fig_f_segments.png", fig)


# ══════════════════════════════════════════════════════════════════════════════
# Report generation
# ══════════════════════════════════════════════════════════════════════════════

def _fig_link(path: str | None, label: str) -> str:
    if path is None:
        return f"*(図なし — データ不足)*"
    rel = Path(path).relative_to(AUDIT_DIR).as_posix()
    return f"![{label}]({rel})"


def write_summary_md(
    run_info:  dict,
    a: dict, b: dict, c: dict, d: dict, e: dict, f: dict, g: dict,
    fig_paths: dict[str, str | None],
) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Verdicts for conclusion
    verdict_a = a.get("overall_verdict", "insufficient data")
    verdict_b = b.get("verdict", "insufficient data")
    verdict_g_unavail = f"{g.get('unavailable_rate', 0)*100:.1f}% unavailable"

    # Main metric table
    factual_range_med = (a.get("axes", {}).get("factual_score", {}) or {}).get("range_median")
    flip_rate_pct = b.get("flip_rate_pct")
    grey_zone = c.get("overall_grey_zone")
    max_corr = max(
        (abs(v["rho"]) for v in d.get("redundant_pairs", [])),
        default=None,
    )
    unavail_rate = g.get("unavailable_rate", 0)
    non_func = c.get("non_functional_axes", [])
    n_groups_a = a.get("n_groups", 0)

    def _verdict_cell(val, ok_thresh, warn_thresh, fmt=".1f", low_is_bad=True):
        if val is None:
            return "N/A", "—"
        if low_is_bad:
            verdict = "✅" if val <= ok_thresh else ("⚠️" if val <= warn_thresh else "❌")
        else:
            verdict = "✅" if val >= ok_thresh else ("⚠️" if val >= warn_thresh else "❌")
        return f"{val:{fmt}}", verdict

    def _na(v, fmt=".1f"):
        return f"{v:{fmt}}" if v is not None else "N/A"

    lines = []
    lines.append(f"# Fact Check Scorer Audit Report")
    lines.append(f"")
    lines.append(f"生成: {now}")
    lines.append(f"")

    # 1. 実行情報
    lines.append(f"## 1. 実行情報")
    lines.append(f"")
    lines.append(f"| 項目 | 値 |")
    lines.append(f"|------|----|")
    lines.append(f"| 期間 | {run_info['since'] or '(全期間)'} 〜 {run_info['until'] or '(全期間)'} |")
    lines.append(f"| JSONL 総レコード数 | {run_info['n_total']} |")
    lines.append(f"| 分析対象 (status=ok) | {run_info['n_ok']} |")
    lines.append(f"| 除外: fact_check_unavailable | {run_info['n_unavail']} |")
    lines.append(f"| 除外: failed_fact_check | {run_info['n_failed']} |")
    lines.append(f"| hash 不一致再採点ペア (除外) | {run_info['n_hash_changed_paths']} paths |")
    lines.append(f"| 使用モデル (主分析) | {run_info['primary_model']} |")
    lines.append(f"| モデル混在 | {'⚠️ ' + run_info['model_mix_note'] if run_info['model_mixed'] else 'なし'} |")
    lines.append(f"| prompt_version 混在 | {'⚠️ ' + run_info['version_mix_note'] if run_info['version_mixed'] else 'なし'} |")
    lines.append(f"| 削除済み記事 (データには残存) | {run_info['n_deleted_in_data']} |")
    lines.append(f"")

    # 2. 結論
    lines.append(f"## 2. 結論")
    lines.append(f"")
    lines.append(f"- **再現性**: {verdict_a}")
    lines.append(f"- **判別力(フリップ率)**: {verdict_b}")
    lines.append(f"- **実行健全性**: {verdict_g_unavail}" + (
        f" — エラー詳細は分析G参照" if g.get("n_total", 0) > 0 else ""))
    lines.append(f"")

    # 3. 主要指標テーブル
    lines.append(f"## 3. 主要指標")
    lines.append(f"")
    lines.append(f"| 指標 | 値 | 判定基準 | 判定 |")
    lines.append(f"|------|----|----------|------|")

    fr_str = _na(factual_range_med) if factual_range_med is not None else f"N/A (n_groups={n_groups_a})"
    fr_verdict = _rescore_verdict(factual_range_med) if factual_range_med is not None else "insufficient data"
    lines.append(f"| factual レンジ中央値 | {fr_str} | <5 安定 / 5-15 グレー / >15 要見直し | {fr_verdict} |")

    flip_str = f"{flip_rate_pct:.1f}%" if flip_rate_pct is not None else f"N/A (n_groups={n_groups_a})"
    flip_verdict = b.get("verdict", "insufficient data")
    lines.append(f"| フリップ率 | {flip_str} | <10% 安定 / 10-25% 多数決 / >25% 再設計 | {flip_verdict} |")

    grey_str = f"{grey_zone*100:.1f}%" if grey_zone is not None else "N/A"
    lines.append(f"| グレーゾーン率 | {grey_str} | — | — |")

    corr_str = f"{max_corr:.3f}" if max_corr is not None else "なし"
    lines.append(f"| 軸間最大|ρ| | {corr_str} | >0.8 = 冗長候補 | {'⚠️ 冗長候補あり' if max_corr and max_corr > 0.8 else '✅'} |")

    lines.append(f"| unavailable 率 | {unavail_rate*100:.1f}% | <5% 正常 | {'✅' if unavail_rate < 0.05 else '⚠️'} |")

    nf_str = ", ".join(AXIS_LABELS[ax] for ax in non_func) if non_func else "なし"
    lines.append(f"| 実質無機能軸 | {nf_str} | なし = 正常 | {'⚠️ 要確認' if non_func else '✅'} |")
    lines.append(f"")

    # 4. 各分析の要約
    lines.append(f"## 4. 各分析の要約")
    lines.append(f"")

    # A
    lines.append(f"### A. 再採点分散")
    lines.append(f"")
    lines.append(f"純粋再採点グループ数: **{a.get('n_groups', 0)}**（同一記事・同一本文の複数採点）")
    lines.append(f"")
    if a.get("n_groups", 0) == 0:
        lines.append(f"> データ不足 — repeat セット蓄積後に再実行してください。")
    else:
        lines.append(f"| 軸 | レンジ中央値 | p90 | 最大 | std中央値 |")
        lines.append(f"|----|-------------|-----|------|----------|")
        for ax in AXES:
            s = a.get("axes", {}).get(ax, {})
            lines.append(
                f"| {AXIS_LABELS[ax]} "
                f"| {_na(s.get('range_median'))} "
                f"| {_na(s.get('range_p90'))} "
                f"| {_na(s.get('range_max'))} "
                f"| {_na(s.get('std_median'))} |"
            )
        lines.append(f"")
        if a.get("top5_worst"):
            lines.append(f"**factual レンジ最大5記事:**")
            for entry in a["top5_worst"]:
                scores_str = ", ".join(
                    f"{AXIS_LABELS[ax]}={entry['scores'][ax]}"
                    for ax in AXES
                )
                lines.append(f"- `{Path(entry['path']).name}` factual_range={entry['factual_range']:.1f}  [{scores_str}]")
    lines.append(f"")
    fig_a_link = _fig_link(fig_paths.get("a"), "rescore range histogram")
    lines.append(f"{fig_a_link}")
    lines.append(f"")

    # B
    lines.append(f"### B. 合否フリップ率")
    lines.append(f"")
    lines.append(f"純粋再採点グループ {b.get('n_groups',0)} 件中、判定が変わったグループ: **{b.get('flip_count',0)} 件**")
    if b.get("flip_rate_pct") is not None:
        lines.append(f"フリップ率: **{b['flip_rate_pct']:.1f}%** → {b['verdict']}")
        if any(v > 0 for v in b.get("axis_flip_cause", {}).values()):
            lines.append(f"")
            lines.append(f"反転の主因となった軸:")
            total_flips = b.get("flip_count", 0)
            for ax, cnt in b["axis_flip_cause"].items():
                if cnt > 0:
                    pct = cnt / total_flips * 100 if total_flips > 0 else 0
                    lines.append(f"- {AXIS_LABELS[ax]}: {cnt} 件 ({pct:.0f}%)")
    else:
        lines.append(f"> データ不足")
    if b.get("judgement_discrepancy_count", 0) > 0:
        lines.append(f"")
        lines.append(f"> ⚠️ スコア再計算 vs overall_judgement の不一致: **{b['judgement_discrepancy_count']} 件** — judgement に独自ロジックが存在する可能性")
    lines.append(f"")

    # C
    lines.append(f"### C. しきい値感度・グレーゾーン")
    lines.append(f"")
    lines.append(f"最新レコード使用: {c.get('n_latest', 0)} 件")
    if c.get("non_functional_axes"):
        lines.append(f"")
        lines.append(f"⚠️ **実質無機能の軸** (合格率 >95%): {', '.join(AXIS_LABELS[ax] for ax in c['non_functional_axes'])}")
    lines.append(f"")
    lines.append(f"| 軸 | 中央値 | 合格率 | グレーゾーン率 |")
    lines.append(f"|----|--------|--------|--------------|")
    for ax in AXES:
        dist = c.get("distributions", {}).get(ax, {})
        med  = _na(dist.get("median"))
        pr   = f"{dist.get('base_pass_rate', 0)*100:.1f}%" if dist.get("base_pass_rate") is not None else "N/A"
        gz   = c.get("grey_zone_rates", {}).get(ax)
        gz_s = f"{gz*100:.1f}%" if gz is not None else "N/A"
        lines.append(f"| {AXIS_LABELS[ax]} | {med} | {pr} | {gz_s} |")
    lines.append(f"")
    fig_c_link = _fig_link(fig_paths.get("c"), "score distributions")
    lines.append(f"{fig_c_link}")
    lines.append(f"")

    # D
    lines.append(f"### D. 軸間相関 (Spearman)")
    lines.append(f"")
    lines.append(f"n={d.get('n', 0)} 件（最新レコード）")
    if d.get("redundant_pairs"):
        lines.append(f"")
        lines.append(f"⚠️ **冗長候補** (|ρ|>0.8):")
        for pair in d["redundant_pairs"]:
            ax1, ax2 = pair["axes"]
            lines.append(f"- {AXIS_LABELS[ax1]} × {AXIS_LABELS[ax2]}: ρ={pair['rho']:.3f}")
    else:
        lines.append(f"冗長ペアなし (|ρ|≦0.8)")
    lines.append(f"")
    corr_mat = d.get("corr_matrix", {})
    if corr_mat:
        lines.append(f"| | {' | '.join(AXIS_LABELS[ax] for ax in AXES)} |")
        lines.append(f"|{'|'.join(['---']*(len(AXES)+1))}|")
        for ax1 in AXES:
            row = f"| {AXIS_LABELS[ax1]} |"
            for ax2 in AXES:
                v = corr_mat.get(ax1, {}).get(ax2)
                row += f" {v:.3f} |" if v is not None else " N/A |"
            lines.append(row)
    lines.append(f"")
    fig_d_link = _fig_link(fig_paths.get("d"), "correlations")
    lines.append(f"{fig_d_link}")
    lines.append(f"")

    # E
    lines.append(f"### E. 時系列ドリフト")
    lines.append(f"")
    lines.append(f"週数: {e.get('n_weeks', 0)}  （現時点のデータ期間が短いため、将来の監査に向けた枠組みとして出力）")
    if e.get("change_points"):
        lines.append(f"変化点: " + ", ".join(
            f"{cp['type']}={cp['value']} at {cp['at']}" for cp in e["change_points"]
        ))
    fig_e_link = _fig_link(fig_paths.get("e"), "timeseries")
    lines.append(f"{fig_e_link}")
    lines.append(f"")

    # F
    lines.append(f"### F. セグメント別分析")
    lines.append(f"")
    seg_stats = f.get("segment_stats", {})
    for grp in ("daily", "rss", "deleted"):
        n_grp = seg_stats.get(grp, {}).get("n", 0)
        lines.append(f"**{grp}** (n={n_grp})")
    lines.append(f"")
    lines.append(f"**仮説検証:**")
    hypo_risk    = f.get("hypothesis_risk", {})
    hypo_factual = f.get("hypothesis_factual", {})
    # Hypothesis 1: deleted group has higher risk
    del_risk_med = hypo_risk.get("deleted", {}).get("median")
    del_risk_n   = hypo_risk.get("deleted", {}).get("n", 0)
    del_fact_med = hypo_factual.get("deleted", {}).get("median")
    del_fact_n   = hypo_factual.get("deleted", {}).get("n", 0)
    daily_risk_med   = hypo_risk.get("daily", {}).get("median")
    daily_fact_med   = hypo_factual.get("daily", {}).get("median")
    rss_risk_med     = hypo_risk.get("rss", {}).get("median")
    rss_fact_med     = hypo_factual.get("rss", {}).get("median")

    def _med_str(m): return f"{m}" if m is not None else "N/A"

    lines.append(f"")
    lines.append(f"① risk 軸は不適格(deleted)群で高いか？")
    lines.append(f"  - deleted 中央値={_med_str(del_risk_med)} (n={del_risk_n}), daily={_med_str(daily_risk_med)}, rss={_med_str(rss_risk_med)}")
    if del_risk_med is not None and daily_risk_med is not None:
        if del_risk_med > daily_risk_med:
            lines.append(f"  → deleted > daily (**仮説支持**) ※ n が小さいため解釈は慎重に")
        else:
            lines.append(f"  → deleted ≦ daily (**仮説不支持** — risk で不適格を検出できていない可能性)")
    else:
        lines.append(f"  → データ不足")

    lines.append(f"")
    lines.append(f"② factual 軸は不適格群を検出できるか？")
    lines.append(f"  - deleted 中央値={_med_str(del_fact_med)} (n={del_fact_n}), daily={_med_str(daily_fact_med)}, rss={_med_str(rss_fact_med)}")
    if del_fact_med is not None and daily_fact_med is not None:
        if del_fact_med < daily_fact_med - 5:
            lines.append(f"  → deleted < daily (**仮説支持**) ※ n が小さいため解釈は慎重に")
        else:
            lines.append(f"  → deleted ≈ daily (**仮説不支持** — fact check は適格性の防衛線にならない疑いあり。n={del_fact_n})")
    else:
        lines.append(f"  → データ不足")

    lines.append(f"")
    tool_table = f.get("tool_table", {})
    if tool_table:
        lines.append(f"**ツール別スコア中央値 (n≥3のみ):**")
        lines.append(f"")
        lines.append(f"| ツール | n | Factual | Freshness | Citation | Risk |")
        lines.append(f"|--------|---|---------|-----------|----------|------|")
        for tool in sorted(tool_table.keys()):
            t = tool_table[tool]
            lines.append(
                f"| {tool} | {t['n']} "
                f"| {_na(t.get('factual_score'))} "
                f"| {_na(t.get('freshness_score'))} "
                f"| {_na(t.get('citation_coverage'))} "
                f"| {_na(t.get('risk_score'))} |"
            )
    fig_f_link = _fig_link(fig_paths.get("f"), "segment boxplots")
    lines.append(f"")
    lines.append(f"{fig_f_link}")
    lines.append(f"")

    # G
    lines.append(f"### G. 実行健全性")
    lines.append(f"")
    sc = g.get("status_counts", {})
    lines.append(f"| status | 件数 | 割合 |")
    lines.append(f"|--------|------|------|")
    n_total = g.get("n_total", 1)
    for st, cnt in sc.items():
        lines.append(f"| {st} | {cnt} | {cnt/n_total*100:.1f}% |")
    lines.append(f"")
    if g.get("error_patterns"):
        lines.append(f"**error_detail 頻度上位:**")
        for pat, cnt in g["error_patterns"].items():
            lines.append(f"- `{pat}`: {cnt} 件")
        lines.append(f"")
    usc = g.get("url_status_counts", {})
    total_src = g.get("total_sources", 0)
    if total_src:
        lines.append(f"**URL チェック結果** (総ソース {total_src} 件):")
        for st, cnt in sorted(usc.items(), key=lambda x: -x[1]):
            lines.append(f"- {st}: {cnt} ({cnt/total_src*100:.1f}%)")
        gr = g.get("grounding_count", 0)
        lines.append(f"- grounding URL (vertexaisearch等): {gr} ({g.get('grounding_rate',0)*100:.2f}%)")
    lines.append(f"")
    lines.append(f"unsupported_claims / 記事: 中央値={g.get('unsupported_claims_median')}, 最大={g.get('unsupported_claims_max')}")
    lines.append(f"")

    # 5. 推奨アクション
    lines.append(f"## 5. 推奨アクション")
    lines.append(f"")
    recommendations = []

    fr_med = (a.get("axes", {}).get("factual_score", {}) or {}).get("range_median")
    if fr_med is not None:
        if fr_med >= 15:
            recommendations.append("- ❌ factual レンジ中央値≥15 → **ゲート設計の根本見直し**が必要")
        elif fr_med >= 5:
            recommendations.append("- ⚠️ factual レンジ中央値 5-15 → **新記事ゲートの3回採点・多数決化**を推奨")

    fp_rate = b.get("flip_rate")
    if fp_rate is not None:
        if fp_rate > 0.25:
            recommendations.append("- ❌ フリップ率>25% → **ゲート再設計**が必要")
        elif fp_rate > 0.10:
            recommendations.append(f"- ⚠️ フリップ率{fp_rate*100:.1f}% → **多数決採点の導入**を推奨")

    if non_func:
        recommendations.append(
            f"- ⚠️ 実質無機能軸 ({', '.join(AXIS_LABELS[ax] for ax in non_func)}) → しきい値の見直しまたは軸の廃止を検討"
        )

    if d.get("redundant_pairs"):
        pairs_str = "; ".join(
            f"{AXIS_LABELS[p['axes'][0]]}×{AXIS_LABELS[p['axes'][1]]}"
            for p in d["redundant_pairs"]
        )
        recommendations.append(f"- ⚠️ 冗長軸ペア({pairs_str}) → 情報量の重複。軸統合を検討")

    if del_fact_med is not None and daily_fact_med is not None and del_fact_med >= daily_fact_med - 5:
        recommendations.append(
            "- ⚠️ factual 軸が不適格群(deleted)を検出できていない "
            "→ fact check は適格性フィルタの代替にならない。RSS eligibility gate の維持が重要"
        )

    if not recommendations:
        recommendations.append("- ✅ 現時点の限られたデータでは重大な問題は検出されていません。repeat セット蓄積後に再実行してください。")

    lines.extend(recommendations)
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"*このレポートは `scripts/audit_fact_check.py` により自動生成されました。*")

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"  → {SUMMARY_PATH.relative_to(REPO)}")


def write_detail_json(run_info: dict, a: dict, b: dict, c: dict, d: dict, e: dict, f: dict, g: dict) -> None:
    # Remove raw plot data before serialising
    f_clean = {k: v for k, v in f.items() if k != "_raw_for_plot"}
    d_clean = {k: v for k, v in d.items() if k != "axis_vals"}

    detail = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_info":  run_info,
        "analysis_a_rescore_variance":    a,
        "analysis_b_flip_rate":           b,
        "analysis_c_threshold_sensitivity": c,
        "analysis_d_correlations":        d_clean,
        "analysis_e_timeseries":          e,
        "analysis_f_segments":            f_clean,
        "analysis_g_execution_health":    g,
    }
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    DETAIL_PATH.write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {DETAIL_PATH.relative_to(REPO)}")


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fact-check scorer audit")
    p.add_argument("--since", metavar="YYYY-MM-DD", help="Start date (inclusive)", default=None)
    p.add_argument("--until", metavar="YYYY-MM-DD", help="End date   (inclusive)", default=None)
    p.add_argument("--model", metavar="MODEL",      help="Restrict to this Gemini model", default=None)
    return p.parse_args()


def _parse_date(s: str, end_of_day=False) -> datetime:
    dt = datetime.strptime(s, "%Y-%m-%d")
    if end_of_day:
        dt = dt.replace(hour=23, minute=59, second=59)
    return dt.replace(tzinfo=timezone.utc)


def main() -> None:
    args = parse_args()

    since = _parse_date(args.since) if args.since else None
    until = _parse_date(args.until, end_of_day=True) if args.until else None

    print("Loading records …")
    all_records, load_warns = load_records(since, until)
    for w in load_warns:
        print(f"  WARN: {w}")

    print(f"  Total records: {len(all_records)}")

    # Model filter / mixing check
    model_counts: dict[str, int] = defaultdict(int)
    for r in all_records:
        model_counts[r.get("gemini_model", "unknown")] += 1

    primary_model = max(model_counts, key=model_counts.__getitem__) if model_counts else "unknown"
    if args.model:
        primary_model = args.model
    model_mixed = len(model_counts) > 1
    model_mix_note = "; ".join(f"{m}={c}" for m, c in model_counts.items()) if model_mixed else ""

    version_counts: dict[str, int] = defaultdict(int)
    for r in all_records:
        version_counts[r.get("prompt_version", "?")] += 1
    version_mixed = len(version_counts) > 1
    version_mix_note = "; ".join(f"v{v}={c}" for v, c in version_counts.items()) if version_mixed else ""

    if model_mixed:
        print(f"  WARN: Multiple models [{model_mix_note}] using {primary_model} for main analysis")
    if version_mixed:
        print(f"  WARN: Multiple prompt versions [{version_mix_note}]")

    # Apply model filter for main analysis
    analysis_records = [r for r in all_records if r.get("gemini_model") == primary_model]

    # Preprocessing
    deleted_paths = add_deleted_flag(analysis_records)
    add_article_type(analysis_records)
    print("  Reading frontmatter for tool names …")
    add_tool_name(analysis_records)

    ok_records = [r for r in analysis_records if r.get("status") == "ok"]
    n_unavail  = sum(1 for r in analysis_records if r.get("status") == "fact_check_unavailable")
    n_failed   = sum(1 for r in analysis_records if r.get("status") == "failed_fact_check")
    n_deleted_in_data = sum(1 for r in analysis_records if r.get("_deleted"))

    print(f"  ok={len(ok_records)}, unavailable={n_unavail}, failed={n_failed}")

    pure_groups, hash_changed, hash_notes = build_rescore_groups(ok_records)
    if hash_notes:
        print(f"  Hash-changed paths ({len(hash_changed)}):")
        for note in hash_notes:
            print(note)

    run_info = {
        "since":                str(args.since) if args.since else None,
        "until":                str(args.until) if args.until else None,
        "n_total":              len(all_records),
        "n_analysis":           len(analysis_records),
        "n_ok":                 len(ok_records),
        "n_unavail":            n_unavail,
        "n_failed":             n_failed,
        "n_deleted_in_data":    n_deleted_in_data,
        "n_hash_changed_paths": len(hash_changed),
        "primary_model":        primary_model,
        "model_mixed":          model_mixed,
        "model_mix_note":       model_mix_note,
        "version_mixed":        version_mixed,
        "version_mix_note":     version_mix_note,
    }

    # Run analyses
    print("Running analyses …")
    print("  A: rescore variance")
    a = analyze_rescore_variance(pure_groups)

    print("  B: flip rate")
    b = analyze_flip_rate(pure_groups, ok_records)

    # Gather axis range medians for Analysis C
    axis_range_medians = {
        ax: (a["axes"].get(ax) or {}).get("range_median")
        for ax in AXES
    }
    print("  C: threshold sensitivity")
    c = analyze_threshold_sensitivity(ok_records, axis_range_medians)

    print("  D: correlations")
    d = analyze_correlations(ok_records)

    print("  E: timeseries")
    e = analyze_timeseries(ok_records, all_records)

    print("  F: segments")
    f = analyze_segments(ok_records)

    print("  G: execution health")
    g = analyze_execution_health(all_records)

    # Figures
    print("Generating figures …")
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig_a = plot_rescore_range(pure_groups, a)
    fig_c = plot_score_distributions(ok_records)
    fig_d = plot_correlations(d)
    fig_e = plot_timeseries(e)
    fig_f = plot_segments(f)
    fig_paths = {"a": fig_a, "c": fig_c, "d": fig_d, "e": fig_e, "f": fig_f}
    for key, path in fig_paths.items():
        if path:
            print(f"  → figures/{Path(path).name}")

    # Reports
    print("Writing reports …")
    write_summary_md(run_info, a, b, c, d, e, f, g, fig_paths)
    write_detail_json(run_info, a, b, c, d, e, f, g)

    print("\nDone.")
    print(f"  {SUMMARY_PATH.relative_to(REPO)}")
    print(f"  {DETAIL_PATH.relative_to(REPO)}")


if __name__ == "__main__":
    main()
