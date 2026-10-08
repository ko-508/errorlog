#!/usr/bin/env python3
"""Search Console のサイトマップ状態と、記事の URL 検査結果を読み取る（読み取り専用）。

使う API:
  sitemaps.list / sitemaps.get       サイトマップの最終読み込み日時・処理状態・警告・エラー
  urlInspection.index.inspect        Google のインデックスにある版の状態
                                      （ライブテストはできない API。登録リクエストもしない）

対象記事:
  content/posts/*.md のうち、現在 draft: true でなく、Git 履歴で「draft: true でない内容で最初に
  commit された日時」（初回公開日時）が --since 以降の記事。初回公開日時を特定できない記事は
  対象に含めず、unresolved として別に記録する。

結果の扱い:
  API の取得に失敗した URL は status=failed として記録する（未登録とはみなさない）。
  応答に欠けている項目は null のまま残し、missing_fields に名前を記録する。

使用例:
  python scripts/inspect_index_status.py --since 2026-07-01 --limit 3 --out-dir out
  python scripts/inspect_index_status.py --since 2026-07-01 --out-dir out
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).parent))
import gsc_client  # noqa: E402
from gsc_client import GscError  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
POSTS_REL = "content/posts"
SITE_BASE = "https://errorlog.jp"
SITEMAP_URL = f"{SITE_BASE}/sitemap.xml"

# URL 検査 API の上限は 1 サイトあたり 600 QPM・2,000 QPD（公式の Usage limits）。
# 余裕を持たせ、1 件ごとに待つ。1 回の実行の件数にも上限を置く。
INSPECT_INTERVAL_S = 0.5
MAX_INSPECTIONS_PER_RUN = 500

INDEX_STATUS_FIELDS = (
    "verdict",
    "coverageState",
    "robotsTxtState",
    "indexingState",
    "lastCrawlTime",
    "pageFetchState",
    "googleCanonical",
    "userCanonical",
    "crawledAs",
    "sitemap",
    "referringUrls",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ── 対象記事（Git 履歴）─────────────────────────────────────────────────────

def _git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args], cwd=BASE, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} が失敗しました: {result.stderr.strip()}")
    return result.stdout


def _is_draft(text: str) -> bool:
    match = re.match(r"---\r?\n(.*?)\r?\n---", text, re.S)
    if not match:
        return False
    value = re.search(r"^draft:\s*(.+)$", match.group(1), re.M)
    return bool(value) and value.group(1).strip().strip("\"'").lower() == "true"


def first_published_at(stem: str, git: Callable[[list[str]], str] = _git) -> str | None:
    """draft: true でない内容で最初に commit された日時（ISO 8601）。特定できなければ None。"""
    path = f"{POSTS_REL}/{stem}.md"
    log = git(["log", "--reverse", "--format=%H\t%aI", "--", path]).splitlines()
    for line in log:
        if "\t" not in line:
            continue
        sha, when = line.split("\t", 1)
        try:
            content = git(["show", f"{sha}:{path}"])
        except RuntimeError:
            continue  # その commit で削除されている
        if not _is_draft(content):
            return when
    return None


def select_targets(since: str, git: Callable[[list[str]], str] = _git) -> tuple[list[dict], list[dict]]:
    """(対象, 初回公開日時を特定できない記事) を返す。"""
    targets: list[dict] = []
    unresolved: list[dict] = []
    for md in sorted((BASE / POSTS_REL).glob("*.md")):
        text = md.read_text(encoding="utf-8", errors="replace")
        if _is_draft(text):
            continue
        stem = md.stem
        first = first_published_at(stem, git)
        url = f"{SITE_BASE}/posts/{stem}/"
        if first is None:
            unresolved.append({"stem": stem, "url": url})
            continue
        if first[:10] >= since:
            targets.append({"stem": stem, "url": url, "first_published_at": first})
    targets.sort(key=lambda item: item["first_published_at"])
    return targets, unresolved


# ── サイトマップ ─────────────────────────────────────────────────────────────

def fetch_sitemaps(service, site_url: str) -> dict[str, Any]:
    fetched_at = utc_now()
    try:
        listed = gsc_client.execute(service.sitemaps().list(siteUrl=site_url), what="sitemaps.list")
    except GscError as e:
        return {"status": "failed", "fetched_at": fetched_at, "error_kind": e.kind, "error": str(e)}
    entries = listed.get("sitemap") or []
    detail = None
    detail_error = None
    try:
        detail = gsc_client.execute(
            service.sitemaps().get(siteUrl=site_url, feedpath=SITEMAP_URL), what="sitemaps.get"
        )
    except GscError as e:
        detail_error = {"error_kind": e.kind, "error": str(e)}
    fields = ("path", "lastSubmitted", "lastDownloaded", "isPending", "isSitemapsIndex", "type", "warnings", "errors", "contents")
    summary = None
    if detail is not None:
        summary = {name: detail.get(name) for name in fields}
        summary["missing_fields"] = [name for name in fields if name not in detail]
        # contents[].indexed は公式に非推奨（使用しない）。submitted だけを残す
        if isinstance(summary.get("contents"), list):
            summary["contents"] = [
                {"type": c.get("type"), "submitted": c.get("submitted")} for c in summary["contents"]
            ]
    return {
        "status": "ok",
        "fetched_at": fetched_at,
        "listed": [{name: entry.get(name) for name in fields if name != "contents"} for entry in entries],
        "detail": summary,
        "detail_error": detail_error,
    }


# ── URL 検査 ─────────────────────────────────────────────────────────────────

def inspect_url(service, site_url: str, url: str) -> dict[str, Any]:
    fetched_at = utc_now()
    body = {"inspectionUrl": url, "siteUrl": site_url, "languageCode": "ja"}
    try:
        response = gsc_client.execute(
            service.urlInspection().index().inspect(body=body), what=f"urlInspection.index.inspect({url})"
        )
    except GscError as e:
        return {"url": url, "status": "failed", "fetched_at": fetched_at, "error_kind": e.kind, "error": str(e)}
    result = (response or {}).get("inspectionResult")
    if not isinstance(result, dict):
        return {"url": url, "status": "failed", "fetched_at": fetched_at, "error_kind": "api",
                "error": "応答に inspectionResult がありません"}
    index_status = result.get("indexStatusResult")
    if not isinstance(index_status, dict):
        return {"url": url, "status": "failed", "fetched_at": fetched_at, "error_kind": "api",
                "error": "応答に indexStatusResult がありません"}
    record: dict[str, Any] = {"url": url, "status": "ok", "fetched_at": fetched_at}
    for name in INDEX_STATUS_FIELDS:
        record[name] = index_status.get(name)
    # API は該当しない項目を省略する（例: 未クロールなら lastCrawlTime がない）。
    # 欠落は値を補わず、そのまま記録する。
    record["missing_fields"] = [name for name in INDEX_STATUS_FIELDS if name not in index_status]
    record["inspectionResultLink"] = result.get("inspectionResultLink")
    return record


# ── 出力 ─────────────────────────────────────────────────────────────────────

CSV_COLUMNS = (
    "stem", "url", "first_published_at", "status", "fetched_at", "verdict", "coverageState",
    "indexingState", "pageFetchState", "robotsTxtState", "lastCrawlTime", "userCanonical",
    "googleCanonical", "canonical_match", "crawledAs", "in_sitemap", "missing_fields", "error_kind", "error",
)


def canonical_match(record: dict) -> str:
    """Google が選んだ正規 URL とユーザー指定の正規 URL の関係。値がなければ unknown。"""
    google = record.get("googleCanonical")
    user = record.get("userCanonical")
    if record.get("status") != "ok" or not google or not user:
        return "unknown"
    return "same" if google == user else "different"


def summarize(results: list[dict]) -> dict[str, Any]:
    ok = [r for r in results if r["status"] == "ok"]
    return {
        "total": len(results),
        "fetch_status": dict(Counter(r["status"] for r in results)),
        "verdict": dict(Counter(str(r.get("verdict")) for r in ok)),
        "coverageState": dict(Counter(str(r.get("coverageState")) for r in ok)),
        "pageFetchState": dict(Counter(str(r.get("pageFetchState")) for r in ok)),
        "indexingState": dict(Counter(str(r.get("indexingState")) for r in ok)),
        "has_lastCrawlTime": dict(Counter("yes" if r.get("lastCrawlTime") else "absent" for r in ok)),
        "canonical_match": dict(Counter(canonical_match(r) for r in results)),
        "google_canonical_not_errorlog": [
            {"url": r["url"], "googleCanonical": r["googleCanonical"]}
            for r in ok if r.get("googleCanonical") and not str(r["googleCanonical"]).startswith(SITE_BASE)
        ],
    }


def write_outputs(out_dir: Path, payload: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index_status.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (out_dir / "index_status.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for r in payload["results"]:
            row = dict(r)
            row["canonical_match"] = canonical_match(r)
            row["in_sitemap"] = (
                "unknown" if r.get("status") != "ok" or r.get("sitemap") is None
                else ("yes" if SITEMAP_URL in (r.get("sitemap") or []) else "no")
            )
            row["missing_fields"] = ",".join(r.get("missing_fields") or [])
            writer.writerow(row)


def main(argv: list[str] | None = None, *, service=None, git: Callable[[list[str]], str] = _git) -> int:
    ap = argparse.ArgumentParser(description="サイトマップの状態と URL 検査の結果を読み取る（読み取り専用）")
    ap.add_argument("--since", required=True, help="初回公開日がこの日以降の記事を対象にする（YYYY-MM-DD）")
    ap.add_argument("--limit", type=int, default=0, help="検査する件数の上限（0 は対象全件）")
    ap.add_argument("--out-dir", required=True, help="結果の保存先")
    args = ap.parse_args(argv)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.since):
        ap.error(f"--since は YYYY-MM-DD 形式が必要です: {args.since!r}")
    site_url = os.environ.get("GSC_SITE_URL", "").strip()
    if not site_url:
        print("[ERROR] GSC_SITE_URL が設定されていません。", file=sys.stderr)
        return 1

    started_at = utc_now()
    targets, unresolved = select_targets(args.since, git)
    selected = targets[: args.limit] if args.limit > 0 else targets
    if len(selected) > MAX_INSPECTIONS_PER_RUN:
        print(f"[ERROR] 検査件数が 1 回の上限を超えます: {len(selected)} > {MAX_INSPECTIONS_PER_RUN}", file=sys.stderr)
        return 1
    print(f"対象記事: {len(targets)} 件（初回公開 {args.since} 以降）、今回検査: {len(selected)} 件、初回公開日時を特定できない記事: {len(unresolved)} 件")

    try:
        if service is None:
            print(f"auth mode: {gsc_client.auth_mode()}")
            service = gsc_client.build_service()
        permission = gsc_client.verify_property_access(service, site_url)
    except GscError as e:
        print(f"[ERROR] Search Console の認証またはプロパティの確認に失敗しました（{e.kind}）: {e}", file=sys.stderr)
        return 1
    print(f"property access: {permission}")

    sitemaps = fetch_sitemaps(service, site_url)
    print(f"sitemaps: {sitemaps['status']}")

    results: list[dict] = []
    for i, target in enumerate(selected):
        record = inspect_url(service, site_url, target["url"])
        record["stem"] = target["stem"]
        record["first_published_at"] = target["first_published_at"]
        results.append(record)
        print(f"  [{i + 1}/{len(selected)}] {target['stem']}: {record['status']} {record.get('coverageState') or record.get('error_kind', '')}")
        if i + 1 < len(selected):
            time.sleep(INSPECT_INTERVAL_S)

    payload = {
        "schema": "index_status/v1",
        "site_url": site_url,
        "property_permission": permission,
        "started_at": started_at,
        "finished_at": utc_now(),
        "since": args.since,
        "targets_total": len(targets),
        "inspected": len(selected),
        "unresolved_first_published": unresolved,
        "sitemaps": sitemaps,
        "summary": summarize(results),
        "results": results,
    }
    write_outputs(Path(args.out_dir), payload)
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    failed = sum(1 for r in results if r["status"] != "ok")
    if sitemaps["status"] != "ok" or failed:
        print(f"[ERROR] 取得に失敗した項目があります: sitemaps={sitemaps['status']}, url_failed={failed}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
