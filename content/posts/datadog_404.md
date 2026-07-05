---
draft: true
title: "Datadog の 404 エラー：原因と解決策"
date: 2026-06-24
description: "Datadogの404エラーはリクエストしたリソースが見つからない場合に発生する。モニターIDやダッシュボードIDの誤りが主な原因。"
tags: ["Datadog"]
errorCode: "404"
urgency: "medium"
service: "Datadog"
error_type: "404"
components: []
related_services: ["Python", "requests", "curl", "jq"]
---

## エラーの概要

Datadog の 404 [エラー](/glossary/エラー/)は、[リクエスト](/glossary/リクエスト/)された[メトリクス](/glossary/メトリクス/)・モニター・[ダッシュボード](/glossary/ダッシュボード/)が見つからないことを示します。モニター[ID](/glossary/id/) または[ダッシュボード](/glossary/ダッシュボード/) [ID](/glossary/id/) が間違っている、存在しないリソースにアクセスしようとしている、または該当する[メトリクス](/glossary/メトリクス/)がまだ Datadog に送信されていない状況で発生します。

## 実際のエラーメッセージ例

**Datadog [API](/glossary/api/) [リクエスト](/glossary/リクエスト/)時：**

```json
{
  "errors": [
    "Not Found. Resource not found. Please verify the monitor/dashboard ID is correct."
  ]
}
```

**[ダッシュボード](/glossary/ダッシュボード/)・モニターへのアクセス時：**

```json
{
  "error": "Not Found",
  "status": 404
}
```

**[エラーメッセージ](/glossary/エラーメッセージ/)の読み方：**

- `404` → [HTTP](/glossary/http/) [ステータスコード](/glossary/ステータスコード/)：[リクエスト](/glossary/リクエスト/)されたリソースが[サーバー](/glossary/サーバー/)上に存在しない
- `Not Found` → 理由フレーズ：対象のモニター [ID](/glossary/id/) や[ダッシュボード](/glossary/ダッシュボード/) [ID](/glossary/id/) が見つからなかった
- `"Resource not found"` → リソースの不在を明示する [JSON](/glossary/json/) フィールド：[ID](/glossary/id/) が間違っているか削除済みである可能性が高い
- `"Please verify the monitor/dashboard ID is correct"` → トラブルシューティングガイダンス：入力した [ID](/glossary/id/) の正確性を確認するよう促す

## よくある原因と解決手順

### 原因1：モニター ID またはダッシュボード ID が間違っている

[API](/glossary/api/) [リクエスト](/glossary/リクエスト/)や[ダッシュボード](/glossary/ダッシュボード/) [URL](/glossary/url/) に指定したリソース [ID](/glossary/id/) が存在しないか、タイプミスがあります。[API](/glossary/api/) 呼び出しで `<your-monitor-id>` の部分に誤った数値を入力した場合、Datadog はそのリソースを特定できず 404 を返します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
curl -X GET "https://api.datadoghq.com/api/v1/monitor/9999999" \
  -H "Authorization: Bearer <your-api-key>" \
  -H "DD-APPLICATION-KEY: <your-app-key>"
```

**After（修正後）：**

```bash
# 1. Datadog WebUI でモニター一覧から正しい ID を確認する
# 2. 確認した正しい ID を使ってリクエストを実行
curl -X GET "https://api.datadoghq.com/api/v1/monitor/12345678" \
  -H "Authorization: Bearer <your-api-key>" \
  -H "DD-APPLICATION-KEY: <your-app-key>"
```

✅ 修正後の確認：

```bash
# レスポンスで モニターの詳細情報が返されることを確認
curl -s -X GET "https://api.datadoghq.com/api/v1/monitor/12345678" \
  -H "Authorization: Bearer <your-api-key>" \
  -H "DD-APPLICATION-KEY: <your-app-key>" | jq '.id'
```

正しいモニター [ID](/glossary/id/) が [JSON](/glossary/json/) [レスポンス](/glossary/レスポンス/)の `id` フィールドに返されれば成功です。

### 原因2：削除済みまたは無効なメトリクスへのアクセス

[クエリ](/glossary/クエリ/)で指定した[メトリクス](/glossary/メトリクス/)が Datadog に送信されていない、または既に削除された場合、[ダッシュボード](/glossary/ダッシュボード/)やグラフの表示時に 404 が発生します。[メトリクス](/glossary/メトリクス/)の送信が中断されたホストや[アプリケーション](/glossary/アプリケーション/)、アップグレード後に廃止された[メトリクス](/glossary/メトリクス/)名を参照しようとすると、この[エラー](/glossary/エラー/)が起こります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```json
{
  "dashboard": {
    "title": "Application Metrics",
    "widgets": [
      {
        "definition": {
          "requests": [
            {
              "q": "avg:custom.old.deprecated.metric{*}"
            }
          ]
        }
      }
    ]
  }
}
```

**After（修正後）：**

```json
{
  "dashboard": {
    "title": "Application Metrics",
    "widgets": [
      {
        "definition": {
          "requests": [
            {
              "q": "avg:system.cpu.user{*}"
            }
          ]
        }
      }
    ]
  }
}
```

✅ 修正後の確認：

```bash
# Metrics Explorer でメトリクスが実際に送信されているか確認
# WebUI の Metrics > Summary から検索バーに新しいメトリクス名を入力
# メトリクスが存在しており、グラフが描画されれば成功です
```

Datadog WebUI の **Metrics** > **Summary** タブで[メトリクス](/glossary/メトリクス/)名を検索し、データ送信中の項目が表示されていれば成功です。

### 原因3：環境やワークスペース固有のリソース参照

複数の Datadog 環境（本番・ステージング等）やサブアカウントを使用している場合、別の環境で作成したモニターや[ダッシュボード](/glossary/ダッシュボード/)の [ID](/glossary/id/) を現在の環境で[リクエスト](/glossary/リクエスト/)すると 404 が返ります。[API](/glossary/api/) キーやアプリケーションキーが異なる環境に対応していないと、リソースが見つかりません。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# 本番環境のダッシュボード ID をステージング環境の API キーで参照
curl -X GET "https://api.datadoghq.com/api/v1/dashboard/abc-123-xyz" \
  -H "DD-API-KEY: <staging-api-key>" \
  -H "DD-APPLICATION-KEY: <staging-app-key>"
```

**After（修正後）：**

```bash
# 本番環境の API キーとアプリケーションキーを使用
curl -X GET "https://api.datadoghq.com/api/v1/dashboard/abc-123-xyz" \
  -H "DD-API-KEY: <production-api-key>" \
  -H "DD-APPLICATION-KEY: <production-app-key>"
```

✅ 修正後の確認：

```bash
# リクエストが成功し、ダッシュボード情報が返されることを確認
curl -s -X GET "https://api.datadoghq.com/api/v1/dashboard/abc-123-xyz" \
  -H "DD-API-KEY: <production-api-key>" \
  -H "DD-APPLICATION-KEY: <production-app-key>" | jq '.dashboard.title'
```

[ダッシュボード](/glossary/ダッシュボード/)の title が正常に返されれば、環境が正しく指定されています。

## 解決策の早見表

| 解決策 | 実装難易度 | 再起動要否 | 対応[OS](/glossary/os/) |
|--------|-----------|-----------|-------|
| モニター/[ダッシュボード](/glossary/ダッシュボード/) [ID](/glossary/id/) の確認と修正 | 低 | 不要 | 全[OS](/glossary/os/) |
| [メトリクス](/glossary/メトリクス/)送信状況の確認・有効[メトリクス](/glossary/メトリクス/)への置換 | 中 | 不要 | 全[OS](/glossary/os/) |
| 環境・[API](/glossary/api/) キーの切り替え | 低 | 不要 | 全[OS](/glossary/os/) |

## ツール固有の注意点

**Datadog WebUI での [ID](/glossary/id/) 確認手順**

モニターや[ダッシュボード](/glossary/ダッシュボード/)の正確な [ID](/glossary/id/) を確認する最も確実な方法は Datadog WebUI を使用することです。モニター一覧画面では各行の左側に [ID](/glossary/id/) が表示されます。Python クライアントライブラリを使用している場合は、以下のコードで全モニターを列挙してから正確な [ID](/glossary/id/) を確認できます。

```python
from datadog import initialize, api

options = {
    'api_key': '<your-api-key>',
    'app_key': '<your-app-key>'
}

initialize(**options)

# 全モニターの一覧を取得
monitors = api.Monitor.get_all()
for monitor in monitors:
    print(f"Monitor ID: {monitor['id']}, Name: {monitor['name']}")
```

このスクリプトを実行すると、環境内のすべてのモニター [ID](/glossary/id/) と名前が列挙されます。[API](/glossary/api/) [リクエスト](/glossary/リクエスト/)で使用する正確な [ID](/glossary/id/) をこの出力から確認してください。

**Metrics Explorer での動作確認**

Datadog WebUI 上部の検索バーから **Metrics > Explorer** に進み、グラフを描画する[メトリクス](/glossary/メトリクス/)が本当に送信されているか確認できます。[メトリクス](/glossary/メトリクス/)名をフリーテキスト検索する際は、完全一致ではなく部分一致でも候補が表示されるため、タイプミスが疑われる場合は似た名前の[メトリクス](/glossary/メトリクス/)がないか確認してください。

## それでも解決しない場合

**確認すべき[ログ](/glossary/ログ/)・[デバッグ](/glossary/デバッグ/)手順**

1. **Datadog Agent の[ログ](/glossary/ログ/)確認**

   [メトリクス](/glossary/メトリクス/)が送信されていない場合、Agent の[設定ファイル](/glossary/設定ファイル/)を確認します。

   ```[bash](/glossary/bash/)
   # Linux/macOS
   tail -f /var/log/datadog/agent.log | grep -i "metric\|error"

   # Windows
   Get-Content "C:\ProgramData\Datadog\Logs\agent.log" -Tail 50
   ```

   Agent が正常に[メトリクス](/glossary/メトリクス/)を送信しているか、接続[エラー](/glossary/エラー/)や[タイムアウト](/glossary/タイムアウト/)が記録されていないか確認してください。

2. **[API](/glossary/api/) [リクエスト](/glossary/リクエスト/)の詳細確認**

   `-v` フラグを付けて curl [リクエスト](/glossary/リクエスト/)を実行し、[ステータスコード](/glossary/ステータスコード/)とレスポンスヘッダーを確認します。

   ```[bash](/glossary/bash/)
   curl -v -X GET "https://api.datadoghq.com/api/v1/monitor/<your-monitor-id>" \
     -H "DD-[API](/glossary/api/)-KEY: <your-api-key>" \
     -H "DD-APPLICATION-KEY: <your-app-key>"
   ```

   [レスポンス](/glossary/レスポンス/)に `< HTTP/1.1 404 Not Found` と出力される場合、リソースが本当に存在しないことが確定します。

3. **公式ドキュメント・サポートの確認**

   Datadog 公式ドキュメント（[Monitors API](https://docs.datadoghq.com/api/latest/monitors/)、[Dashboards API](https://docs.datadoghq.com/api/latest/dashboards/)）を参照し、使用中の [API](/glossary/api/) [バージョン](/glossary/バージョン/)が非推奨になっていないか確認してください。[API](/glossary/api/) のメジャーバージョンアップグレード後、旧[バージョン](/glossary/バージョン/)のエンドポ

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
