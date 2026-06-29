---
draft: true
title: "Datadog の 403 エラー：原因と解決策"
date: 2026-06-24
description: "Datadog APIへのアクセス権限がないか、アプリケーションキーのスコープが不足している場合に発生する403エラー。"
tags: ["Datadog"]
errorCode: "403"
urgency: "medium"
service: "Datadog"
error_type: "403"
components: []
related_services: ["API", "Organization Settings"]
---

## エラーの概要

Datadog [API](/glossary/api/) への[アクセス権限](/glossary/アクセス権限/)がない、またはアプリケーションキーに対象リソースへのアクセスに必要な[スコープ](/glossary/スコープ/)がない場合に発生します。ユーザーに対して該当リソースの[アクセス権限](/glossary/アクセス権限/)がないか、オーガニゼーションレベルのアクセス制御で制限されていることが原因です。

## 実際のエラーメッセージ例

```json
{
  "errors": [
    "Insufficient permissions"
  ]
}
```

```json
{
  "status": 403,
  "error": "User does not have access to this resource"
}
```

**[エラーメッセージ](/glossary/エラーメッセージ/)の読み方：**

- `403` → [HTTP](/glossary/http/) [ステータスコード](/glossary/ステータスコード/)：[リクエスト](/glossary/リクエスト/)は到達したが、[サーバー](/glossary/サーバー/)がアクセスを拒否した
- `Insufficient permissions` → アプリケーションキーに必要な[スコープ](/glossary/スコープ/)（読み取り・書き込み[権限](/glossary/権限/)）が不足していることを示す
- `User does not have access to this resource` → ユーザーまたはキーがそのリソースへの[アクセス権限](/glossary/アクセス権限/)を持っていないことを示す [JSON](/glossary/json/) メッセージ

## よくある原因と解決手順

### 原因1：アプリケーションキーのスコープが不足している

Datadog のアプリケーションキーは、細粒度の[スコープ](/glossary/スコープ/)（権限設定）を持ちます。[API](/glossary/api/) 呼び出しに必要な[スコープ](/glossary/スコープ/)がキーに割り当てられていない場合、403 [エラー](/glossary/エラー/)が返されます。例えば、[ダッシュボード](/glossary/ダッシュボード/)作成 [API](/glossary/api/) を呼び出す際に「[ダッシュボード](/glossary/ダッシュボード/)読み取り」[スコープ](/glossary/スコープ/)のみがあると、書き込み操作は拒否されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# ダッシュボード作成に必要な「dashboards_write」スコープのないキーを使用
curl -X POST "https://api.datadoghq.com/api/v1/dashboard" \
  -H "DD-API-KEY: <your-api-key>" \
  -H "DD-APPLICATION-KEY: <restricted-app-key-without-write-scope>" \
  -H "Content-Type: application/json" \
  -d '{"title":"My Dashboard"}'
# 応答: 403 Insufficient permissions
```

**After（修正後）：**

```bash
# ダッシュボード作成に必要な「dashboards_write」スコープを持つキーを使用
curl -X POST "https://api.datadoghq.com/api/v1/dashboard" \
  -H "DD-API-KEY: <your-api-key>" \
  -H "DD-APPLICATION-KEY: <your-app-key-with-dashboards-write>" \
  -H "Content-Type: application/json" \
  -d '{"title":"My Dashboard"}'
# 応答: 200 OK
```

✅ 修正後の確認：

Datadog の Organization Settings → Application Keys で該当キーを選択し、必要な[スコープ](/glossary/スコープ/)（例：`dashboards_write`、`monitors_write`）にチェックマークが付いているか確認してください。チェックが入っていれば、[スコープ](/glossary/スコープ/)割り当てが成功しています。

### 原因2：ユーザーロールに対象リソースへのアクセス権限がない

アプリケーションキーを生成したユーザーの[ロール](/glossary/ロール/)が、その操作に必要な[権限](/glossary/権限/)を持っていない場合に発生します。オーガニゼーション管理者は多くの[スコープ](/glossary/スコープ/)にアクセスできますが、カスタムロールや制限された[ロール](/glossary/ロール/)（例：Monitor Editor）ではリソースごとのアクセスが限定されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
# Monitor Editor ロールのユーザーが生成したキーで、
# Monitor Read-Only 権限しかないリソースを編集しようとする
from datadog import initialize, api

options = {
    'api_key': '<your-api-key>',
    'app_key': '<your-app-key>'
}

initialize(**options)

# Monitor 編集操作を試行
api.Monitor.update(123456, query="avg:system.cpu{*} > 0.8")
# 応答: 403 User does not have access to this resource
```

**After（修正後）：**

```python
# 必要な権限を持つロールに変更するか、
# Organization Settings で該当ユーザーに権限を付与する
from datadog import initialize, api

options = {
    'api_key': '<your-api-key>',
    'app_key': '<your-app-key-from-admin-user>'
}

initialize(**options)

# Monitor 編集操作が成功
api.Monitor.update(123456, query="avg:system.cpu{*} > 0.8")
# 応答: 200 OK
```

✅ 修正後の確認：

Datadog の Organization Settings → Users で該当ユーザーを選択し、割り当てられている[ロール](/glossary/ロール/)を確認してください。必要な操作に対応した[ロール](/glossary/ロール/)（例：Monitor Editor、Admin）が割り当てられていれば成功です。

### 原因3：API キーと Application Key の混同

Datadog には [API](/glossary/api/) Key と Application Key の 2 種類のキーが存在します。一部の [API](/glossary/api/) [エンドポイント](/glossary/エンドポイント/)は両方が必要で、一方のみを提供した場合や誤ったキーを使用した場合に 403 [エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# Application Key が必要な操作に API Key のみを使用
curl -X GET "https://api.datadoghq.com/api/v1/dashboard" \
  -H "DD-API-KEY: <your-api-key>" \
  -H "Content-Type: application/json"
# 応答: 403 Insufficient permissions
```

**After（修正後）：**

```bash
# 両方のキーを正しいヘッダーで提供
curl -X GET "https://api.datadoghq.com/api/v1/dashboard" \
  -H "DD-API-KEY: <your-api-key>" \
  -H "DD-APPLICATION-KEY: <your-application-key>" \
  -H "Content-Type: application/json"
# 応答: 200 OK
```

✅ 修正後の確認：

```bash
# キーの種類を確認するコマンド
curl -X GET "https://api.datadoghq.com/api/v1/validate" \
  -H "DD-API-KEY: <your-api-key>" \
  -H "DD-APPLICATION-KEY: <your-application-key>"
```

[HTTP](/glossary/http/) 200 が返されれば両キーが正しく認識されています。

### 原因4：Application Key が削除または無効化されている

組織の管理者が[セキュリティ](/glossary/セキュリティ/)上の理由でアプリケーションキーを削除した場合、そのキーを使用するすべての [API](/glossary/api/) 呼び出しが 403 [エラー](/glossary/エラー/)になります。キーが Active な状態でなくなると、たとえ[スコープ](/glossary/スコープ/)が正しくても拒否されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# 削除されたまたは無効化されたキーを使用
curl -X GET "https://api.datadoghq.com/api/v1/monitor" \
  -H "DD-API-KEY: <your-api-key>" \
  -H "DD-APPLICATION-KEY: <deleted-or-revoked-app-key>"
# 応答: 403 Insufficient permissions
```

**After（修正後）：**

```bash
# Organization Settings で新しいキーを生成し使用
curl -X GET "https://api.datadoghq.com/api/v1/monitor" \
  -H "DD-API-KEY: <your-api-key>" \
  -H "DD-APPLICATION-KEY: <your-newly-generated-app-key>"
# 応答: 200 OK
```

✅ 修正後の確認：

Datadog の Organization Settings → Application Keys にアクセスし、使用しているキーが「Active」ステータスで表示されているか確認してください。削除済みキーのリストに含まれていなければ成功です。

## 解決策の早見表

| 解決策 | 実装難易度 | 再起動要否 | 対応[OS](/glossary/os/) |
|--------|-----------|-----------|-------|
| [スコープ](/glossary/スコープ/)追加 | 低 | 不要 | 全[OS](/glossary/os/) |
| [ロール](/glossary/ロール/)権限付与 | 中 | 不要 | 全[OS](/glossary/os/) |
| キー種別確認 | 低 | 不要 | 全[OS](/glossary/os/) |
| キー再生成 | 低 | 不要 | 全[OS](/glossary/os/) |

## ツール固有の注意点

Datadog では、[API](/glossary/api/) Key と Application Key が異なる目的で使い分けられます。[API](/glossary/api/) Key は[メトリクス](/glossary/メトリクス/)送信や[ログ](/glossary/ログ/)送信に使用され、Application Key は機密性の高い [API](/glossary/api/)（ユーザー管理、組織設定、[ダッシュボード](/glossary/ダッシュボード/)操作など）に必要です。Terraform Provider for Datadog を使用する場合は、`api_key` と `app_key` の両方を[環境変数](/glossary/環境変数/)または[設定ファイル](/glossary/設定ファイル/)で明示的に指定する必要があります。

また、KEDA（[Kubernetes](/glossary/kubernetes/) Event-based Autoscaling）で Datadog をメトリクスプロバイダーとして使用する場合、ScaledObject の `authenticationRef` で指定される Secret に、両方のキーが正しく含まれていることを確認してください。[Kubernetes](/glossary/kubernetes/) Secret で `api-key` と `app-key` というキー名で保存し、KEDA の設定では `apiKey` と `appKey` のフィールドで参照するという対応も重要です。

オーガニゼーション内に複数のサイト（US/EU など）がある場合、[API](/glossary/api/) [エンドポイント](/glossary/エンドポイント/)の URL も `api.datadoghq.com`（US）と `api.datadoghq.eu`（EU）で異なります。間違ったサイトのキーで異なるサイトの [API](/glossary/api/) にアクセスしようとすると 403 [エラー](/glossary/エラー/)が返されるため、環境に応じた URL 設定が必須です。

## それでも解決しない場合

**[ログ](/glossary/ログ/)の確認：**

- [Kubernetes](/glossary/kubernetes/) を使用している場合、`kubectl logs <pod-name>` で Pod の[ログ](/glossary/ログ/)を確認し、[API](/glossary/api/) 呼び出しのレスポンスコードを確認してください
- Terraform を使用している場合、`TF_LOG=DEBUG terraform apply` でデバッグログを有効化し、[API](/glossary/api/) [リクエスト](/glossary/リクエスト/)・[レスポンス](/glossary/レスポンス/)の詳細を確認してください

**デバッグコマンド：**

```bash
# キーの

> **調査について**　この記事の解決策は、GitHub Issues・Stack Overflow への公開報告を Gemini + Google Search で検索・精査し、実効性の高いものを整理したものです。参照元の URL は Editor's Note に記載しています。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
