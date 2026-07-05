---
title: "Azure の 401 エラー：原因と解決策"
date: 2026-06-01
description: "Azureへの認証情報が無効または期限切れになっている"
tags: ["Azure"]
errorCode: "401"
service: "Azure"
error_type: "401"
components: []
related_services: ["Azure CLI", "Azure SDK", "Azure Virtual Machine", "Azure Functions", "App Service", "Azure Portal"]
top_queries:
- '401エラー'
- 'azure 401'
---
## エラーの概要

Azure への [API](/glossary/api/) [リクエスト](/glossary/リクエスト/)や[コマンド](/glossary/コマンド/)実行時に 401 Unauthorized [エラー](/glossary/エラー/)が返される場合、認証情報が無効であるか期限切れになっていることを示しています。この[エラー](/glossary/エラー/)が発生すると、Azure リソースへのアクセスが完全にブロックされ、[デプロイ](/glossary/デプロイ/)やリソース管理の操作が実行できなくなります。Azure [CLI](/glossary/cli/)、[SDK](/glossary/sdk/)、マネージド [ID](/glossary/id/) など複数の認証方式で発生する可能性があります。

## 実際のエラーメッセージ例

**Azure [CLI](/glossary/cli/) での出力例：**

```bash
$ az group list
ERROR: The command failed with an unexpected status code: 401 (Unauthorized).
The command failed with an error. (AuthenticationFailed) Authentication failed. The `Credentials` object was not initialized. Please call `Credentials.Initialize()` before making any requests.
```

**[REST](/glossary/rest/) [API](/glossary/api/) [レスポンス](/glossary/レスポンス/)例：**

```json
{
  "error": {
    "code": "AuthenticationFailed",
    "message": "Authentication failed. The user or application is not authorized to access the resource.",
    "details": [
      {
        "code": "Unauthorized",
        "message": "The request requires authentication information."
      }
    ]
  }
}
```

## よくある原因と解決手順

### 原因1：az login のセッションが期限切れになっている

Azure [CLI](/glossary/cli/) の[認証](/glossary/認証/)セッションには有効期限があります。特に長時間セッションを保持していたり、PC のスリープ後に再度[コマンド](/glossary/コマンド/)を実行したりする場合、自動的にセッションが無効化されることがあります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# 前回のセッションから時間が経過した状態で実行
$ az vm list --resource-group myResourceGroup
ERROR: The command failed with an unexpected status code: 401 (Unauthorized).
```

**After（修正後）：**

```bash
# セッションを更新する
$ az login

# または、対話形式で再ログインする場合
$ az login --use-device-code

# その後、コマンドを実行
$ az vm list --resource-group myResourceGroup
```

`az login` [コマンド](/glossary/コマンド/)を実行すると、ブラウザが起動して Azure ポータルへの[ログイン](/glossary/ログイン/)が求められます。完了後、[CLI](/glossary/cli/) セッションが更新され、その後の[コマンド](/glossary/コマンド/)が正常に実行できるようになります。

### 原因2：サービスプリンシパルのシークレットが期限切れになっている

[CI/CD](/glossary/ci-cd/) パイプラインやスクリプト自動化でサービスプリンシパル[認証](/glossary/認証/)を使用している場合、設定したシークレット（またはクライアントシークレット）の有効期限が切れると 401 [エラー](/glossary/エラー/)が発生します。Azure では[セキュリティ](/glossary/セキュリティ/)上の理由から、デフォルトでシークレットに 1 ～ 2 年の有効期限が設定されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# 期限切れのシークレットで認証を試みる
$ az login --service-principal \
  -u <client-id> \
  -p <expired-client-secret> \
  --tenant <tenant-id>
ERROR: The command failed with an unexpected status code: 401 (Unauthorized).
Authentication failed. The credentials provided do not grant access to the resource.
```

**After（修正後）：**

```bash
# 1. 新しいシークレットを生成する
$ az ad sp credential reset \
  --id <client-id> \
  --years 2

# 出力例:
# {
#   "appId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
#   "password": "new-secret-value",
#   "tenant": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
# }

# 2. 新しいシークレットで再度ログインする
$ az login --service-principal \
  -u <client-id> \
  -p <new-client-secret> \
  --tenant <tenant-id>
```

新しいシークレットを生成後、[CI/CD](/glossary/ci-cd/) [環境変数](/glossary/環境変数/)や自動化スクリプトに設定される秘密情報を更新することを忘れずに行ってください。

### 原因3：マネージド ID が有効になっていないリソースで使用しようとしている

Azure Virtual Machine、Azure Functions、App Service などのリソースでマネージド [ID](/glossary/id/) [認証](/glossary/認証/)を使用する場合、対象のリソースでマネージド [ID](/glossary/id/) 機能が有効化されていないと 401 [エラー](/glossary/エラー/)が発生します。マネージド [ID](/glossary/id/) は Azure が自動的に管理する認証方式で、シークレット管理の手間を削減します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
# マネージドIDが無効なVMで実行される Python スクリプト
from azure.identity import ManagedIdentityCredential
from azure.storage.blob import BlobServiceClient

# マネージドIDが無効な場合、ここで 401 エラーが発生
credential = ManagedIdentityCredential()
blob_client = BlobServiceClient(
    account_url="https://<storage-account>.blob.core.windows.net",
    credential=credential
)
blobs = blob_client.list_blobs(container_name="mycontainer")
# ERROR: Azure Identity: ManagedIdentityCredential - Failed to get token. 
# Status code: 401
```

**After（修正後）：**

```bash
# 1. Azure Portal で VM のマネージド ID を有効化
# または Azure CLI で実施:
$ az vm identity assign \
  --resource-group <resource-group> \
  --name <vm-name> \
  --identities [system]

# 2. ストレージアカウントのアクセス権限をマネージド ID に付与
$ az role assignment create \
  --role "Storage Blob Data Reader" \
  --assignee-object-id <managed-identity-principal-id> \
  --scope /subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.Storage/storageAccounts/<storage-account>

# 3. Python スクリプトは同じコードで動作するようになる
# (マネージドIDが有効になっているため、認証が成功)
```

Python スクリプト本体の修正は不要です。リソース側のマネージド [ID](/glossary/id/) 設定を有効化すれば、Azure [SDK](/glossary/sdk/) が自動的に[認証](/glossary/認証/)を処理します。

## ツール固有の注意点

**Azure [CLI](/glossary/cli/) の複数[アカウント](/glossary/アカウント/)管理：** 複数の Azure [サブスクリプション](/glossary/サブスクリプション/)やテナントにアクセスしている場合、`az account show` でアクティブな[アカウント](/glossary/アカウント/)を確認し、`az account set --subscription <subscription-id>` で対象[サブスクリプション](/glossary/サブスクリプション/)に切り替えてください。誤った[アカウント](/glossary/アカウント/)で[認証](/glossary/認証/)されている場合も 401 [エラー](/glossary/エラー/)が発生します。

**[環境変数](/glossary/環境変数/)による[認証](/glossary/認証/)：** `AZURE_CLIENT_ID`、`AZURE_CLIENT_SECRET`、`AZURE_TENANT_ID` などの[環境変数](/glossary/環境変数/)を使用する場合、これらが正しい値で設定されているか確認してください。特に自動[デプロイ](/glossary/デプロイ/)環境では、[環境変数](/glossary/環境変数/)の値が古いままになっていることが原因の 1 つです。

**マネージド [ID](/glossary/id/) と Role-Based Access Control（[RBAC](/glossary/rbac/)）の組み合わせ：** マネージド [ID](/glossary/id/) を有効化した後、リソースが実際にアクセスしたい対象（ストレージアカウント、キーボルト など）に対する [RBAC](/glossary/rbac/) [ロール](/glossary/ロール/)を割り当てる必要があります。マネージド [ID](/glossary/id/) の有効化だけでは[権限](/glossary/権限/)が付与されないため注意が必要です。

## それでも解決しない場合

**Azure のアクティビティログを確認：** Azure ポータルの「アクティビティログ」セクションで、失敗した操作の詳細を確認してください。具体的な[認証](/glossary/認証/)[エラー](/glossary/エラー/)の理由が記録されていることがあります。

**Azure [SDK](/glossary/sdk/) のデバッグログを有効化：** Python や Node.js でログレベルを設定し、詳細な認証情報を出力します：

```python
import logging
logging.basicConfig(level=logging.DEBUG)

from azure.identity import DefaultAzureCredential
credential = DefaultAzureCredential()
```

このコードで、どの認証方式が試行され、どこで失敗しているかを特定できます。

**公式ドキュメント参照：** Azure [認証](/glossary/認証/)について詳しくは、[Microsoft Learn の Azure 認証ガイド](https://learn.microsoft.com/ja-jp/azure/developer/python/sdk/authentication-overview) および [Azure CLI ドキュメント](https://learn.microsoft.com/ja-jp/cli/azure/) を参照してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*