---
title: "Grafana の 400 エラー：原因と解決策"
date: 2026-06-22
description: "Grafana APIへのリクエストの形式または内容に誤りがある。"
tags: ["Grafana"]
errorCode: "400"
service: "Grafana"
error_type: "400"
components: []
related_services: ["Prometheus"]
conclusion: "Grafana の 400 エラーは、API リクエストの JSON 形式の誤りか必須フィールドの欠落が原因です。エラーレスポンスの `message` フィールドを確認し、公式ドキュメントで必須フィールドを照らし合わせることで解決できます。"
---

## エラーの概要

Grafana の 400 Bad Request [エラー](/glossary/エラー/)は、[API](/glossary/api/) へ送信された[リクエスト](/glossary/リクエスト/)の形式や内容が Grafana の仕様に合致していないことを示します。[ダッシュボード](/glossary/ダッシュボード/)作成、アラートルール設定、データソース登録など、[API](/glossary/api/) 経由で Grafana を操作する際に頻繁に発生します。この[エラー](/glossary/エラー/)が出た場合、[リクエスト](/glossary/リクエスト/)自体が Grafana [サーバー](/glossary/サーバー/)に正しく理解されていないため、[レスポンス](/glossary/レスポンス/)の詳細メッセージを確認することが解決の第一歩となります。

## 実際のエラーメッセージ例

**例1：[ダッシュボード](/glossary/ダッシュボード/)作成時の 400 [エラー](/glossary/エラー/)**

```json
{
  "code": 400,
  "message": "Failed to create dashboard: missing required field \"title\"",
  "status": "Bad Request"
}
```

**例2：アラートルール設定時の 400 [エラー](/glossary/エラー/)**

```json
{
  "message": "invalid request body",
  "details": "validation failed: For condition: condition 0, evaluator type 'gt' requires threshold to be numeric",
  "traceID": "00000000000000001234567890abcdef"
}
```

**例3：不正な [JSON](/glossary/json/) フォーマット**

```bash
curl -X POST http://localhost:3000/api/dashboards/db \
  -H "Authorization: Bearer <your-api-token>" \
  -H "Content-Type: application/json" \
  -d '{invalid json without closing brace'
```

[レスポンス](/glossary/レスポンス/)：
```json
{
  "message": "Invalid request body",
  "code": 400
}
```

## よくある原因と解決手順

### 原因1：ダッシュボード JSON に必須フィールドが欠けている

[ダッシュボード](/glossary/ダッシュボード/)を [API](/glossary/api/) 経由で作成または更新する際、`title`、`panels`、`uid` など必須フィールドが不足していると 400 [エラー](/glossary/エラー/)が発生します。Grafana の各[バージョン](/glossary/バージョン/)で要求される必須フィールドが異なる場合もあります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```json
{
  "dashboard": {
    "panels": [
      {
        "id": 1,
        "title": "Sample Panel",
        "targets": []
      }
    ],
    "tags": ["monitoring"],
    "timezone": "browser"
  },
  "overwrite": false
}
```

**After（修正後）：**

```json
{
  "dashboard": {
    "id": null,
    "uid": "sample-dashboard-uid",
    "title": "My Dashboard",
    "panels": [
      {
        "id": 1,
        "title": "Sample Panel",
        "type": "graph",
        "targets": [],
        "gridPos": {
          "h": 8,
          "w": 12,
          "x": 0,
          "y": 0
        }
      }
    ],
    "tags": ["monitoring"],
    "timezone": "browser",
    "version": 0
  },
  "overwrite": false
}
```

主な必須フィールドは以下の通りです：
- `dashboard.title`：[ダッシュボード](/glossary/ダッシュボード/)名（必須）
- `dashboard.panels`：パネルの配列（最低1つ必須）
- `dashboard.panels[].type`：パネルタイプ（graph、stat など）
- `dashboard.panels[].gridPos`：パネルの配置情報
- `dashboard.version`：現在の[ダッシュボード](/glossary/ダッシュボード/)版（新規は 0）

### 原因2：API リクエストボディの JSON フォーマットが不正

ダブルクォート、カンマ、括弧の書き忘れなど、[JSON](/glossary/json/) の構文[エラー](/glossary/エラー/)があると 400 [エラー](/glossary/エラー/)が発生します。ツールで [JSON](/glossary/json/) 検証をしないまま [API](/glossary/api/) 呼び出しをするとこの問題に直面します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
curl -X POST http://localhost:3000/api/datasources \
  -H "Authorization: Bearer <your-api-token>" \
  -H "Content-Type: application/json" \
  -d '
  {
    "name": "Prometheus",
    "type": "prometheus",
    "url": "http://prometheus:9090"
    "access": "proxy",
    "isDefault": true
  }
  '
```

**After（修正後）：**

```bash
curl -X POST http://localhost:3000/api/datasources \
  -H "Authorization: Bearer <your-api-token>" \
  -H "Content-Type: application/json" \
  -d '
  {
    "name": "Prometheus",
    "type": "prometheus",
    "url": "http://prometheus:9090",
    "access": "proxy",
    "isDefault": true
  }
  '
```

**修正のポイント：**
- [JSON](/glossary/json/) 内の各[プロパティ](/glossary/プロパティ/)間に `,` を忘れずに付ける
- 値は必ずダブルクォートで囲む（文字列の場合）
- オンライン [JSON](/glossary/json/) バリデーター（jsonlint.com など）で事前チェック

### 原因3：アラートルール設定値が範囲外またはデータ型が不正

アラートルールの `threshold`（閾値）や `evaluator`（評価式）の設定値が、Grafana が期待するデータ型や値の範囲から外れている場合、400 [エラー](/glossary/エラー/)が返されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```json
{
  "uid": "alert-rule-1",
  "title": "High CPU Alert",
  "condition": "A",
  "data": [
    {
      "refId": "A",
      "queryType": "",
      "datasourceUid": "prometheus-uid",
      "model": {
        "expr": "up{job=\"prometheus\"}"
      }
    }
  ],
  "noDataState": "NoData",
  "execErrState": "Alerting",
  "conditions": [
    {
      "evaluator": {
        "params": ["cpu_threshold"],
        "type": "gt"
      },
      "operator": {
        "type": "and"
      }
    }
  ]
}
```

**After（修正後）：**

```json
{
  "uid": "alert-rule-1",
  "title": "High CPU Alert",
  "condition": "A",
  "data": [
    {
      "refId": "A",
      "queryType": "",
      "datasourceUid": "prometheus-uid",
      "model": {
        "expr": "up{job=\"prometheus\"}"
      }
    }
  ],
  "noDataState": "NoData",
  "execErrState": "Alerting",
  "for": "5m",
  "conditions": [
    {
      "evaluator": {
        "params": [85],
        "type": "gt"
      },
      "operator": {
        "type": "and"
      },
      "query": {
        "params": ["A"]
      },
      "type": "query"
    }
  ]
}
```

**修正のポイント：**
- `threshold`（`params` 配列）には数値を文字列ではなく数値型で設定
- `evaluator.type` は `gt`、`lt`、`eq` など Grafana が認識する文字列のみ
- `for` フィールド（アラート状態継続時間）は `5m`、`10m` など有効な期間形式
- `conditions` には `type` と `query` フィールドが必須

## ツール固有の注意点

**Grafana [バージョン](/glossary/バージョン/)差異への対応**

Grafana 8.0 以前と 9.0 以降ではアラート設定の[スキーマ](/glossary/スキーマ/)が大きく変わります。[API](/glossary/api/) ドキュメントを使用している Grafana [バージョン](/glossary/バージョン/)に合わせて確認してください。[バージョン](/glossary/バージョン/) 9.0 以降を使用している場合、レガシーアラートではなく新しい `Alerting` [API](/glossary/api/) を使用してください。

**[エラーメッセージ](/glossary/エラーメッセージ/)の詳細確認**

[エラーレスポンス](/glossary/エラーレスポンス/)の `message` フィールドには、問題箇所を指す有用な情報が含まれています。例えば `"missing required field \"title\""` と表示されれば、その時点で[ダッシュボード](/glossary/ダッシュボード/) の title フィールドが不足していることが直ちに判明します。

**Content-Type [ヘッダー](/glossary/ヘッダー/)の確認**

[API](/glossary/api/) [リクエスト](/glossary/リクエスト/)送信時は必ず `Content-Type: application/json` [ヘッダー](/glossary/ヘッダー/)を付与してください。この[ヘッダー](/glossary/ヘッダー/)がないと、Grafana が[リクエストボディ](/glossary/リクエストボディ/)を [JSON](/glossary/json/) と認識せず、パースエラーが発生します。

## それでも解決しない場合

**1. Grafana [ログファイル](/glossary/ログファイル/)の確認**

Grafana [サーバー](/glossary/サーバー/)の[ログファイル](/glossary/ログファイル/)（通常 `/var/log/grafana/grafana.log` または `<grafana-installation>/data/log/grafana.log`）を確認してください。[API](/glossary/api/) [リクエスト](/glossary/リクエスト/)の詳細なバリデーションエラーが記録されている場合があります。

```bash
tail -f /var/log/grafana/grafana.log | grep "Bad Request"
```

**2. [API](/glossary/api/) [リクエスト](/glossary/リクエスト/)の[デバッグ](/glossary/デバッグ/)**

`curl` [コマンド](/glossary/コマンド/)に `-v` フラグを追加し、[リクエスト](/glossary/リクエスト/)と[レスポンス](/glossary/レスポンス/)の全詳細を確認してください。

```bash
curl -v -X POST http://localhost:3000/api/dashboards/db \
  -H "Authorization: Bearer <your-api-token>" \
  -H "Content-Type: application/json" \
  -d @dashboard.json
```

**3. 公式ドキュメントの確認**

Grafana 公式の [API](/glossary/api/) ドキュメント（https://grafana.com/docs/grafana/latest/developers/http_api/）では、各エンドポイントごとに必須フィールド、リクエスト形式、レスポンス例が詳述されています。使用しているエンドポイントに対応するセクションを確認し、自身のリクエスト形式と比較してください。

**4. [JSON](/glossary/json/) スキーマバリデーション**

複雑な[ダッシュボード](/glossary/ダッシュボード/) [JSON](/glossary/json/) の場合、オンライン [JSON](/glossary/json/) スキーマバリデーター（json-schema.org）を活用し、Grafana の期待する[スキーマ](/glossary/スキーマ/)に合致しているか事前検証することが有効です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
