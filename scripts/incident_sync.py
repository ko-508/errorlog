"""
Phase 4: 障害速報 Front Matter 付与スクリプト

incident_flags.json（rss_pipeline.py が生成）を読み込み、
content/posts/ 記事の Front Matter の service / components と照合して
一致した記事に trend_incident: true を付与する。

24時間経過後は trend_incident を除去する（cleanup モード）。

Usage:
  python scripts/incident_sync.py          # 付与 + 古いフラグのクリーンアップ
  python scripts/incident_sync.py --clean  # フラグ除去のみ
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE             = Path(__file__).parent.parent
SCRIPTS_DIR      = Path(__file__).parent
POSTS_DIR        = BASE / "content" / "posts"
INCIDENT_FILE    = SCRIPTS_DIR / "incident_flags.json"

INCIDENT_TTL_SEC = int(os.getenv("INCIDENT_TTL_SEC", str(86400)))  # デフォルト24時間


def load_incidents() -> list[dict]:
    """incident_flags.json を読み込む。有効期限内のものだけ返す。"""
    if not INCIDENT_FILE.exists():
        return []
    try:
        data = json.loads(INCIDENT_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] incident_flags.json 読み込みエラー: {e}")
        return []

    now_ts  = datetime.now(timezone.utc).timestamp()
    cutoff  = now_ts - INCIDENT_TTL_SEC
    active  = []
    for inc in data:
        try:
            ts = datetime.fromisoformat(inc["detected_at"]).timestamp()
            if ts > cutoff:
                active.append(inc)
        except (KeyError, ValueError):
            pass
    return active


def _parse_fm_list(value: str) -> list[str]:
    """Front Matter の YAML リスト文字列をパースして list[str] を返す。
    例: '["IAM", "STS"]'  または  '[IAM, STS]'
    """
    value = value.strip()
    if value.startswith("["):
        try:
            return json.loads(value)
        except Exception:
            inner = value.strip("[]")
            return [s.strip().strip('"\'') for s in inner.split(",") if s.strip()]
    return []


def _matches_incident(fm_text: str, incidents: list[dict]) -> bool:
    """記事の Front Matter テキストが active なインシデントと一致するか判定。

    一致条件:
      - service フィールドがインシデントの service と一致
      - または components のいずれかがインシデントの keywords に含まれる
    """
    service_m    = re.search(r'^service:\s*"?([^"\n]+)"?\s*$', fm_text, re.MULTILINE)
    components_m = re.search(r'^components:\s*(\[.*?\])', fm_text, re.MULTILINE)

    article_service    = service_m.group(1).strip().lower() if service_m else ""
    article_components = [c.lower() for c in _parse_fm_list(components_m.group(1) if components_m else "")]

    for inc in incidents:
        inc_service  = inc.get("service", "").lower()
        inc_keywords = [k.lower() for k in inc.get("keywords", [])]

        if inc_service and (inc_service in article_service or article_service in inc_service):
            return True
        if any(c in inc_keywords for c in article_components):
            return True

    return False


def apply_trend_incident(incidents: list[dict]) -> int:
    """一致した記事に trend_incident: true を付与する。戻り値: 付与件数。"""
    applied = 0
    for md in POSTS_DIR.glob("*.md"):
        try:
            text = md.read_text(encoding="utf-8")
        except Exception:
            continue

        fm_match = re.match(r'^(---\n)(.*?)(\n---\n)', text, re.DOTALL)
        if not fm_match:
            continue
        fm_text = fm_match.group(2)

        if _matches_incident(fm_text, incidents):
            if "trend_incident:" in fm_text:
                continue  # 既に付与済み
            new_fm_text = fm_text + "\ntrend_incident: true"
            new_text    = fm_match.group(1) + new_fm_text + fm_match.group(3) + text[fm_match.end():]
            md.write_text(new_text, encoding="utf-8")
            print(f"  [+] trend_incident: {md.name}")
            applied += 1

    return applied


def cleanup_trend_incident(incidents: list[dict]) -> int:
    """期限切れのインシデントと一致しなくなった記事から trend_incident フラグを除去。
    戻り値: 除去件数。
    """
    removed = 0
    for md in POSTS_DIR.glob("*.md"):
        try:
            text = md.read_text(encoding="utf-8")
        except Exception:
            continue

        if "trend_incident:" not in text:
            continue

        fm_match = re.match(r'^(---\n)(.*?)(\n---\n)', text, re.DOTALL)
        if not fm_match:
            continue
        fm_text = fm_match.group(2)

        # アクティブなインシデントと一致しなくなった場合はフラグ除去
        if not _matches_incident(fm_text, incidents):
            new_fm_text = re.sub(r'(?m)^trend_incident:.*\n?', '', fm_text)
            new_text    = fm_match.group(1) + new_fm_text + fm_match.group(3) + text[fm_match.end():]
            md.write_text(new_text, encoding="utf-8")
            print(f"  [-] trend_incident 除去: {md.name}")
            removed += 1

    return removed


def main() -> None:
    clean_only = "--clean" in sys.argv

    incidents = load_incidents()
    print(f"アクティブなインシデント: {len(incidents)} 件")
    for inc in incidents:
        print(f"  - {inc['service']}: {inc.get('title', '')[:60]}")

    if not clean_only and incidents:
        applied = apply_trend_incident(incidents)
        print(f"trend_incident 付与: {applied} 件")

    removed = cleanup_trend_incident(incidents)
    print(f"trend_incident 除去: {removed} 件")


if __name__ == "__main__":
    main()
