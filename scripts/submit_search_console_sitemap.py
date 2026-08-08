#!/usr/bin/env python3
"""GitHub Pages の公開後に sitemap.xml を Google Search Console へ再送信する。"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


GSC_SCOPE = "https://www.googleapis.com/auth/webmasters"
SITEMAP_URL = "https://errorlog.jp/sitemap.xml"


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"エラー: {name} が設定されていません。")
    return value


def verify_sitemap(url: str) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "ErrorLog-GSC-Submit/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = response.status
            body = response.read(4096).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"エラー: sitemap取得がHTTP {exc.code}で失敗しました: {url}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"エラー: sitemapへ接続できません: {url}: {exc}") from exc
    if status != 200:
        raise SystemExit(f"エラー: sitemap取得がHTTP {status}でした: {url}")
    if "<urlset" not in body and "<sitemapindex" not in body:
        raise SystemExit(f"エラー: sitemapのXMLルート要素を確認できません: {url}")


def build_service():
    from googleapiclient.discovery import build

    service_account_json = os.environ.get("GSC_SERVICE_ACCOUNT_KEY", "").strip()
    if service_account_json:
        from google.oauth2.service_account import Credentials

        try:
            info = json.loads(service_account_json)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"エラー: GSC_SERVICE_ACCOUNT_KEYがJSONではありません: {exc}") from exc
        credentials = Credentials.from_service_account_info(info, scopes=[GSC_SCOPE])
        return build("searchconsole", "v1", credentials=credentials, cache_discovery=False)

    client_id = os.environ.get("GSC_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GSC_OAUTH_CLIENT_SECRET", "").strip()
    refresh_token = os.environ.get("GSC_OAUTH_REFRESH_TOKEN", "").strip()
    missing = [
        name
        for name, value in (
            ("GSC_OAUTH_CLIENT_ID", client_id),
            ("GSC_OAUTH_CLIENT_SECRET", client_secret),
            ("GSC_OAUTH_REFRESH_TOKEN", refresh_token),
        )
        if not value
    ]
    if missing:
        raise SystemExit(
            "エラー: GSC認証がありません。GSC_SERVICE_ACCOUNT_KEY、またはOAuth 3項目を設定してください。"
            f" 不足: {', '.join(missing)}"
        )

    from google.oauth2.credentials import Credentials

    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=[GSC_SCOPE],
    )
    return build("searchconsole", "v1", credentials=credentials, cache_discovery=False)


def main() -> None:
    site_url = require_env("GSC_SITE_URL")
    verify_sitemap(SITEMAP_URL)
    service = build_service()
    service.sitemaps().submit(siteUrl=site_url, feedpath=SITEMAP_URL).execute()
    print(f"GSC sitemap送信 OK: property={site_url} sitemap={SITEMAP_URL}")


if __name__ == "__main__":
    main()
