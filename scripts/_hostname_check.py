"""
一時診断スクリプト: GA4プロパティのhostName別PV・ユーザー内訳を確認する。
zenn.devや予期しないホストが混入していないかを把握するためのもの。
確認後は削除してよい。

実行:
  python scripts/_hostname_check.py

環境変数 (weekly_ga4.yml と同じ認証情報を使用):
  GA4_PROPERTY_ID
  GA4_SERVICE_ACCOUNT_KEY  (優先)
  GA4_OAUTH_CLIENT_ID / GA4_OAUTH_CLIENT_SECRET / GA4_OAUTH_REFRESH_TOKEN  (フォールバック)
"""

import json
import os
import sys
from datetime import date, timedelta

TODAY = date.today()
END   = (TODAY - timedelta(days=3)).strftime("%Y-%m-%d")
START = (TODAY - timedelta(days=9)).strftime("%Y-%m-%d")

PROPERTY_ID = os.environ.get("GA4_PROPERTY_ID", "").strip()
if not PROPERTY_ID:
    print("[ERROR] GA4_PROPERTY_ID が設定されていません。", file=sys.stderr)
    sys.exit(1)


def _build_client():
    from google.analytics.data_v1beta import BetaAnalyticsDataClient

    sa_json = os.environ.get("GA4_SERVICE_ACCOUNT_KEY", "").strip()
    if sa_json:
        from google.oauth2.service_account import Credentials
        creds = Credentials.from_service_account_info(
            json.loads(sa_json),
            scopes=["https://www.googleapis.com/auth/analytics.readonly"],
        )
        return BetaAnalyticsDataClient(credentials=creds)

    from google.oauth2.credentials import Credentials
    creds = Credentials(
        token=None,
        refresh_token=os.environ.get("GA4_OAUTH_REFRESH_TOKEN", ""),
        client_id=os.environ.get("GA4_OAUTH_CLIENT_ID", ""),
        client_secret=os.environ.get("GA4_OAUTH_CLIENT_SECRET", ""),
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/analytics.readonly"],
    )
    return BetaAnalyticsDataClient(credentials=creds)


def main():
    from google.analytics.data_v1beta.types import (
        DateRange, Dimension, Metric, RunReportRequest,
    )

    client = _build_client()

    print(f"集計期間: {START} 〜 {END}")
    print(f"GA4プロパティ: {PROPERTY_ID}\n")

    resp = client.run_report(RunReportRequest(
        property=f"properties/{PROPERTY_ID}",
        dimensions=[Dimension(name="hostName")],
        metrics=[
            Metric(name="screenPageViews"),
            Metric(name="activeUsers"),
            Metric(name="sessions"),
        ],
        date_ranges=[DateRange(start_date=START, end_date=END)],
        limit=50,
    ))

    rows = []
    for row in resp.rows:
        host = row.dimension_values[0].value
        pv   = int(float(row.metric_values[0].value))
        uu   = int(float(row.metric_values[1].value))
        sess = int(float(row.metric_values[2].value))
        rows.append({"host": host, "pv": pv, "uu": uu, "sessions": sess})

    rows.sort(key=lambda r: -r["pv"])

    total_pv   = sum(r["pv"]   for r in rows) or 1
    total_uu   = sum(r["uu"]   for r in rows) or 1
    total_sess = sum(r["sessions"] for r in rows) or 1

    print(f"{'ホスト名':<35} {'PV':>8} {'PV%':>6}  {'UU':>8} {'UU%':>6}  {'セッション':>10}")
    print("-" * 85)
    for r in rows:
        pv_pct   = r["pv"]   / total_pv   * 100
        uu_pct   = r["uu"]   / total_uu   * 100
        flag = " ← zenn混入" if "zenn" in r["host"] else ""
        flag = flag or (" ← 要確認" if r["host"] not in ("errorlog.jp", "www.errorlog.jp") else "")
        print(
            f"{r['host']:<35} {r['pv']:>8,} {pv_pct:>5.1f}%  "
            f"{r['uu']:>8,} {uu_pct:>5.1f}%  {r['sessions']:>10,}{flag}"
        )
    print("-" * 85)
    print(
        f"{'合計':<35} {total_pv:>8,} {'100.0%':>6}  "
        f"{total_uu:>8,} {'100.0%':>6}  {total_sess:>10,}"
    )

    errorlog_pv = sum(r["pv"] for r in rows if "errorlog.jp" in r["host"])
    other_pv    = total_pv - errorlog_pv
    print(f"\nerrorlog.jp 系 PV: {errorlog_pv:,} ({errorlog_pv/total_pv*100:.1f}%)")
    print(f"それ以外の PV:      {other_pv:,} ({other_pv/total_pv*100:.1f}%)")

    if any("zenn" in r["host"] for r in rows):
        zenn_pv = sum(r["pv"] for r in rows if "zenn" in r["host"])
        print(f"\n⚠️  zenn.dev 系が混入しています: {zenn_pv:,} PV ({zenn_pv/total_pv*100:.1f}%)")
    else:
        print("\n✅ zenn.dev の混入は確認されませんでした。")


if __name__ == "__main__":
    main()
