---
title: "Azure の 500 エラー：原因と解決策"
date: 2026-06-02
description: "Azureサービスの内部エラーが発生した"
tags: ["Azure"]
errorCode: "500"
service: "Azure"
error_type: "500"
components: ["Azure Portal", "Azure CLI", "REST API", "Azure Resource Manager", "ARM テンプレート", "Bicep テンプレート"]
related_services: ["Bash", "JSON"]
lastmod: 2026-06-14
---
## エラーの概要

Azure 500[エラー](/glossary/エラー/)は、Azureの[サーバー](/glossary/サーバー/)側で予期しない内部[エラー](/glossary/エラー/)が発生したことを示す[HTTP](/glossary/http/)[ステータスコード](/glossary/ステータスコード/)です。クライアント側に問題がなく、Azureインフラストラクチャ自体に一時的な障害が生じている状態を指します。この[エラー](/glossary/エラー/)が発生すると、リソースへのアクセスやデプロイメント、[API](/glossary/api/)呼び出しなどが中断され、進行中の処理は失敗に終わります。

## 実際のエラーメッセージ例

Azure Portal、Azure [CLI](/glossary/cli/)または[REST](/glossary/rest/) [API](/glossary/api/)を使用する際に以下のような[エラー](/glossary/エラー/)が表示されます。

```json
{
  "error": {
    "code": "InternalServerError",
    "message": "An internal error occurred while processing your request. Please try again later.",
    "details": []
  }
}
```

```bash
$ az vm create --resource-group <your-resource-group> --name <your-vm-name> --image UbuntuLTS
InternalServerError: An internal server error occurred while processing your request. Please try again later.
```

```json
{
  "error": {
    "code": "500",
    "message": "Internal Server Error",
    "target": "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.Compute/virtualMachines/<vm-name>"
  }
}
```

## よくある原因と解決手順

### 原因1：リソースプロバイダーの登録が不完全またはタイムアウト

Azureではリソースを作成する前に対応するリソースプロバイダーを登録する必要があります。登録プロセスが完了していない場合や[タイムアウト](/glossary/タイムアウト/)した場合に500[エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# リソースプロバイダーを確認せずにVM作成を試みる
az vm create --resource-group myResourceGroup --name myVM --image UbuntuLTS
```

**After（修正後）：**

```bash
# 必要なリソースプロバイダーを登録
az provider register --namespace Microsoft.Compute
az provider register --namespace Microsoft.Network
az provider register --namespace Microsoft.Storage

# 登録の完了を確認
az provider show --namespace Microsoft.Compute --query "registrationState"

# その後でリソース作成を実行
az vm create --resource-group myResourceGroup --name myVM --image UbuntuLTS
```

### 原因2：クォータ制限または容量超過

サブスクリプション内のリソース作成がクォータ制限に達していたり、特定のリージョンの容量が不足している場合に発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# クォータ確認なしに大量のVMを作成
for i in {1..100}; do
  az vm create --resource-group myResourceGroup --name myVM-$i --image UbuntuLTS
done
```

**After（修正後）：**

```bash
# 事前にクォータ使用量を確認
az vm list-usage --location eastus --query "[?name.value=='cores']"

# 必要に応じてクォータ増加をリクエスト
az support tickets create \
  --resource-group myResourceGroup \
  --title "CPU Quota Increase Request" \
  --severity minimal \
  --contact-method email

# 別のリージョンでリソース作成を検討
az vm create --resource-group myResourceGroup --name myVM --image UbuntuLTS --location westus
```

### 原因3：ARM テンプレートの構文エラーまたはスキーマの非互換性

Azure Resource Manager（ARM）テンプレートで構文[エラー](/glossary/エラー/)があったり、[API](/glossary/api/)[バージョン](/glossary/バージョン/)が古い場合に500[エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```json
{
  "$schema": "https://schema.management.azure.com/schemas/2015-01-01/deploymentTemplate.json#",
  "contentVersion": "1.0.0.0",
  "resources": [
    {
      "type": "Microsoft.Compute/virtualMachines",
      "apiVersion": "2015-06-15",
      "name": "myVM",
      "location": "[resourceGroup().location]",
      "properties": {
        "hardwareProfile": {
          "vmSize": "Standard_A0"
        }
      }
    }
  ]
}
```

**After（修正後）：**

```json
{
  "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
  "contentVersion": "1.0.0.0",
  "resources": [
    {
      "type": "Microsoft.Compute/virtualMachines",
      "apiVersion": "2023-03-01",
      "name": "myVM",
      "location": "[resourceGroup().location]",
      "properties": {
        "hardwareProfile": {
          "vmSize": "Standard_B2s"
        },
        "osProfile": {
          "computerName": "myVM",
          "adminUsername": "azureuser"
        },
        "storageProfile": {
          "imageReference": {
            "publisher": "Canonical",
            "offer": "UbuntuServer",
            "sku": "18.04-LTS",
            "version": "latest"
          }
        }
      }
    }
  ]
}
```

### 原因4：ネットワークセキュリティグループ（NSG）またはファイアウォール規則の設定ミス

NSGやAzure Firewallの設定が不適切な場合、内部通信がブロックされて500[エラー](/glossary/エラー/)が発生することがあります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# すべてのインバウンドを拒否するNSGを作成
az network nsg create --resource-group myResourceGroup --name myNSG

az network nsg rule create --resource-group myResourceGroup \
  --nsg-name myNSG \
  --name DenyAllInbound \
  --priority 100 \
  --direction Inbound \
  --access Deny \
  --protocol '*'
```

**After（修正後）：**

```bash
# 必要なトラフィックのみを許可するNSGルールを作成
az network nsg rule create --resource-group myResourceGroup \
  --nsg-name myNSG \
  --name AllowHTTP \
  --priority 100 \
  --direction Inbound \
  --access Allow \
  --protocol Tcp \
  --source-address-prefixes '*' \
  --destination-port-ranges 80

az network nsg rule create --resource-group myResourceGroup \
  --nsg-name myNSG \
  --name AllowHTTPS \
  --priority 101 \
  --direction Inbound \
  --access Allow \
  --protocol Tcp \
  --source-address-prefixes '*' \
  --destination-port-ranges 443
```

## Azure 固有の注意点

### App Service での 500 エラー

Azure App Service でアプリケーションが500[エラー](/glossary/エラー/)を返す場合、アプリケーション自体の問題とプラットフォーム側の問題を区別する必要があります。以下の[コマンド](/glossary/コマンド/)で診断設定を有効にして詳細な[ログ](/glossary/ログ/)を確認してください。

```bash
# App Service の詳細ログを有効化
az webapp log config --name <your-app-name> --resource-group <your-resource-group> \
  --web-server-logging filesystem --detailed-error-messages true

# ログをダウンロードして確認
az webapp log download --name <your-app-name> --resource-group <your-resource-group> \
  --log-file appservice.zip
```

### Azure SQL Database との接続エラー

[バックエンド](/glossary/バックエンド/)の[SQL](/glossary/sql/) Databaseに接続できない場合も500[エラー](/glossary/エラー/)が発生します。[ファイアウォール](/glossary/ファイアウォール/)規則とVNet統合設定を確認してください。

```bash
# SQL Serverのファイアウォール規則を確認
az sql server firewall-rule list --resource-group <your-resource-group> \
  --server <your-server-name>

# アプリケーションが配置されている場所からのアクセスを許可
az sql server firewall-rule create --resource-group <your-resource-group> \
  --server <your-server-name> \
  --name AllowAzureServices \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0
```

### API Management での 500 エラー

Azure [API](/glossary/api/) Managementを経由している場合、[ポリシー](/glossary/ポリシー/)設定や[バックエンド](/glossary/バックエンド/)の設定ミスが原因となります。[ポリシー](/glossary/ポリシー/)検証と[バックエンド](/glossary/バックエンド/)の[ヘルスチェック](/glossary/ヘルスチェック/)を実行してください。

```bash
# バックエンド APIのヘルスプローブ設定を確認
az apim backend show --resource-group <your-resource-group> \
  --service-name <your-apim-name> \
  --backend-id <your-backend-id>

# ポリシー設定の構文を検証
az apim api policy show --resource-group <your-resource-group> \
  --service-name <your-apim-name> \
  --api-id <your-api-id>
```

## それでも解決しない場合

### ログの確認方法

Azure Monitor を利用して詳細な[エラーログ](/glossary/エラーログ/)を確認することができます。

```bash
# Azure Monitor で過去1時間のエラーログを検索
az monitor metrics list --resource <your-resource-id> \
  --metric "FailedRequests" \
  --start-time 2024-01-01T00:00:00Z \
  --interval PT1M

# Application Insights でトレースを確認
az monitor app-insights query --app <your-app-insights-name> \
  --analytics-query "requests | where resultCode == 500 | project timestamp, name, resultCode, duration"
```

### Azure Support への相談

問題が継続する場合は、Azure サポートに問い合わせてください。事前に以下の情報を準備しておくと対応が迅速になります。

- リソースの種類（App Service、VM、[API](/glossary/api/) Management など）
- 発生時刻と時間帯
- 実行していた操作の詳細
- Azure Monitor または Application Insights からの[ログ](/glossary/ログ/)出力
- サブスクリプション [ID](/glossary/id/) とリソースグループ名

### 公式ドキュメント

以下のドキュメントを参照して詳細を確認してください。

- [Azure サービスの正常性状態を確認](https://status.azure.com/)
- [Azure トラブルシューティング ガイド](https://learn.microsoft.com/ja-jp/azure/cloud-adoption-framework/ready/consideration/connectivity-to-azure)
- [ARM テンプレートのベストプラクティス](https://learn.microsoft.com/ja-jp/azure/azure-resource-manager/templates/best-practices)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*