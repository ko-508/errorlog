---
title: "Azure の 409 エラー：原因と解決策"
date: 2026-06-02
description: "Azureリソースの現在の状態とリクエストが競合している。Azure 409 エラーの原因と解決策を解説します。"
tags: ["Azure"]
errorCode: "409"
---
## エラーの概要

Azure 409 Conflict [エラー](/glossary/エラー/)は、リソースの現在の状態と [API](/glossary/api/) [リクエスト](/glossary/リクエスト/)が競合している場合に発生します。通常、同じ名前のリソースが既に存在する、リソースがプロビジョニング途中である、または削除処理中の状態で新しい操作を実行しようとしたときに返されます。この[エラー](/glossary/エラー/)は Azure Portal、Azure [CLI](/glossary/cli/)、Azure PowerShell、[REST](/glossary/rest/) [API](/glossary/api/) など複数のインターフェースで発生する可能性があります。

## 実際のエラーメッセージ例

**Azure [REST](/glossary/rest/) [API](/glossary/api/) [レスポンス](/glossary/レスポンス/)：**

```json
{
  "error": {
    "code": "Conflict",
    "message": "The resource 'myStorageAccount' already exists in the resource group 'myResourceGroup'.",
    "status": "409"
  }
}
```

**Azure [CLI](/glossary/cli/) の出力：**

```bash
(Conflict) The storage account myStorageAccount already exists.
Code: Conflict
Message: The storage account myStorageAccount already exists.
```

## よくある原因と解決手順

### 原因1：同じ名前のリソースが既に存在する

同じ名前のリソース（ストレージアカウント、App Service、Cosmos DB など）が既に同じリソースグループ内に存在すると、新規作成時に 409 Conflict が発生します。Azure の多くのリソースはグローバルに一意な名前を要求するため、他のリソースグループや他のサブスクリプションの同名リソースも競合の原因となります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
az storage account create \
  --name myStorageAccount \
  --resource-group myResourceGroup \
  --location eastus
```

**After（修正後）：**

```bash
az storage account create \
  --name mystorageaccount123456 \
  --resource-group myResourceGroup \
  --location eastus
```

### 原因2：リソースが削除処理中で他の操作ができない状態

リソースを削除してから数秒以内に同じ名前で新しいリソースを作成しようとすると、削除処理が[バックエンド](/glossary/バックエンド/)で完全に終了していないため 409 [エラー](/glossary/エラー/)が発生します。特にストレージアカウントや App Service Plan では数秒から数分の遅延が生じることがあります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# ストレージアカウントを削除
az storage account delete \
  --name myStorageAccount \
  --resource-group myResourceGroup \
  --yes

# 直後に同じ名前で新規作成（失敗する）
az storage account create \
  --name myStorageAccount \
  --resource-group myResourceGroup \
  --location eastus
```

**After（修正後）：**

```bash
# ストレージアカウントを削除
az storage account delete \
  --name myStorageAccount \
  --resource-group myResourceGroup \
  --yes

# 数秒～1分待機
sleep 30

# 同じ名前で新規作成
az storage account create \
  --name myStorageAccount \
  --resource-group myResourceGroup \
  --location eastus
```

### 原因3：Provisioning State が Succeeded でない状態で操作を実行

リソースのプロビジョニングが進行中（Creating、Updating、Deleting）の状態で、同じリソースに対して別の操作（スケーリング、設定変更、追加リソースの[デプロイ](/glossary/デプロイ/)など）を実行すると 409 [エラー](/glossary/エラー/)が発生します。特に大規模なリソースグループへのデプロイメントでは複数のリソースが非同期にプロビジョニングされるため、依存関係がある場合に問題が生じます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# App Service Plan を作成開始
az appservice plan create \
  --name myAppPlan \
  --resource-group myResourceGroup \
  --sku S1

# プロビジョニング完了を待たずに Web App を作成（失敗する可能性がある）
az webapp create \
  --name myWebApp \
  --resource-group myResourceGroup \
  --plan myAppPlan
```

**After（修正後）：**

```bash
# App Service Plan を作成
az appservice plan create \
  --name myAppPlan \
  --resource-group myResourceGroup \
  --sku S1

# Provisioning State を確認し Succeeded まで待機
while [ "$(az appservice plan show \
  --name myAppPlan \
  --resource-group myResourceGroup \
  --query 'provisioningState' -o tsv)" != "Succeeded" ]; do
  echo "Provisioning in progress..."
  sleep 5
done

# プロビジョニング完了後に Web App を作成
az webapp create \
  --name myWebApp \
  --resource-group myResourceGroup \
  --plan myAppPlan
```

## ツール固有の注意点

**Azure Portal での確認方法：**
Azure Portal からリソースの詳細ページを開くと、「概要」タブに「Provisioning state」が表示されます。このステータスが「Succeeded」になるまで、そのリソースに対する変更操作は待機してください。

**複数リソースの[デプロイ](/glossary/デプロイ/)時の注意：**
Azure Resource Manager (ARM) テンプレートや Terraform、Bicep などで複数リソースを一括[デプロイ](/glossary/デプロイ/)する場合、`dependsOn` 属性を明示的に指定してリソース間の依存関係を定義することが重要です。これによりリソースが順序通りにプロビジョニングされ、409 [エラー](/glossary/エラー/)を防げます。

```yaml
# 例：Bicep での依存関係定義
resource appPlan 'Microsoft.Web/serverfarms@2021-02-01' = {
  name: 'myAppPlan'
  location: location
  sku: {
    name: 'S1'
  }
}

resource webApp 'Microsoft.Web/sites@2021-02-01' = {
  name: 'myWebApp'
  location: location
  properties: {
    serverFarmId: appPlan.id
  }
  dependsOn: [
    appPlan
  ]
}
```

**グローバルに一意な名前の必要性：**
ストレージアカウント、App Service、Cosmos DB、Azure [SQL](/glossary/sql/) Database など、インターネット経由でアクセスされるリソースはグローバル名前空間を共有します。同じ名前が世界中のどのリージョン・どのサブスクリプションにも存在しないことを確認してください。

## それでも解決しない場合

1. **Azure [CLI](/glossary/cli/) でのプロビジョニング状態確認：**

```bash
az resource show \
  --resource-group <your-resource-group> \
  --name <your-resource-name> \
  --resource-type <your-resource-type> \
  --query provisioningState
```

2. **Activity Log の確認：**
Azure Portal で「アクティビティ [ログ](/glossary/ログ/)」を開き、409 [エラー](/glossary/エラー/)の詳細なメッセージを確認します。「[JSON](/glossary/json/)」ビューで展開すると、競合の具体的な原因が表示される場合があります。

3. **リソース グループのロック確認：**

```bash
az group lock list \
  --resource-group <your-resource-group>
```

リソースグループやリソースレベルでロックが設定されていないか確認してください。

4. **一時的な[バックエンド](/glossary/バックエンド/)問題の可能性：**
409 [エラー](/glossary/エラー/)が断続的に発生する場合、Azure [バックエンド](/glossary/バックエンド/)の一時的な問題の可能性があります。指数[バックオフ](/glossary/バックオフ/)で数分間隔を空けて再試行してください。

5. **公式ドキュメント参照：**
- [Azure REST API エラーリファレンス](https://learn.microsoft.com/ja-jp/azure/azure-resource-manager/management/common-deployment-errors)
- [Azure Resource Manager のプロビジョニング状態](https://learn.microsoft.com/ja-jp/azure/azure-resource-manager/management/async-operations)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*