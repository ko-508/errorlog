---
title: "Azure の 400 エラー：原因と解決策"
date: 2026-05-31
description: "Azure APIへのリクエストにパラメータの誤りがある。Azure 400 エラーの原因と解決策を解説します。"
tags: ["Azure"]
errorCode: "400"
---
## エラーの概要

Azure 400[エラー](/glossary/エラー/)は「Bad Request」を意味し、Azure [API](/glossary/api/)への[リクエスト](/glossary/リクエスト/)に含まれる[パラメータ](/glossary/パラメータ/)や値に誤りがある場合に発生します。これは[認証](/glossary/認証/)[エラー](/glossary/エラー/)ではなく、[リクエスト](/glossary/リクエスト/)の内容そのものが仕様に違反していることを示す重要な信号です。Azure PortalやAzure [CLI](/glossary/cli/)、[REST](/glossary/rest/) [API](/glossary/api/)を通じてリソースを作成・更新する際に頻繁に遭遇する[エラー](/glossary/エラー/)であり、適切な対応により確実に解決できます。

## 実際のエラーメッセージ例

**Azure [REST](/glossary/rest/) [API](/glossary/api/)の[レスポンス](/glossary/レスポンス/)例：**

```json
{
  "error": {
    "code": "BadRequest",
    "message": "The value of parameter 'vmName' is invalid.",
    "details": [
      {
        "code": "InvalidParameterValue",
        "message": "The name 'my-vm-123456789-toolongname' is longer than the maximum allowed length of 15 characters."
      }
    ]
  }
}
```

**Azure [CLI](/glossary/cli/)の出力例：**

```bash
$ az vm create --resource-group myRG --name "invalid@vm#name" --image UbuntuLTS
(BadRequest) The name 'invalid@vm#name' does not match the allowed pattern.
```

## よくある原因と解決手順

### 原因1：必須パラメータの不足または型の不正

[リクエスト](/glossary/リクエスト/)に必須の[パラメータ](/glossary/パラメータ/)が含まれていないか、指定した値が[API](/glossary/api/)が期待するデータ型と異なっている場合に発生します。例えば、リソースIDは文字列型で指定が必須であるのに対し、数値型で送信された場合などが該当します。Azure [API](/glossary/api/)の仕様では厳密な型チェックが行われるため、[JSON](/glossary/json/)[ペイロード](/glossary/ペイロード/)の構造確認は必須です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
import requests

payload = {
    "properties": {
        "adminUsername": "azureuser",
        # adminUserPassword が不足している
        "osProfile": {
            "computerName": "myvm"
        }
    }
}

response = requests.put(
    "https://management.azure.com/subscriptions/<subscription-id>/resourceGroups/myRG/providers/Microsoft.Compute/virtualMachines/myVM?api-version=2021-07-01",
    headers={"Authorization": f"Bearer {token}"},
    json=payload
)
```

**After（修正後）：**

```python
import requests

payload = {
    "properties": {
        "adminUsername": "azureuser",
        "adminUserPassword": "P@ssw0rd!Secure123",  # 必須パラメータを追加
        "osProfile": {
            "computerName": "myvm"
        }
    }
}

response = requests.put(
    "https://management.azure.com/subscriptions/<subscription-id>/resourceGroups/myRG/providers/Microsoft.Compute/virtualMachines/myVM?api-version=2021-07-01",
    headers={"Authorization": f"Bearer {token}"},
    json=payload
)
print(response.status_code)
```

### 原因2：リソース名の命名規則違反

Azure リソース名には文字数制限および使用可能文字に関する厳格なルールが存在します。仮想マシンは最大15文字で英数字とハイフンのみ使用可能、ストレージアカウントは最大24文字で小文字英数字のみという具合に、リソースの種類ごとに異なる規則が適用されます。これらの規則を超えたり違反する文字を含めたりすると400[エラー](/glossary/エラー/)が返されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# VM名が命名規則違反（15文字超過＆ハイフン以外の特殊文字）
az vm create \
  --resource-group myRG \
  --name "my-virtual-machine@2024_production" \
  --image UbuntuLTS
```

**After（修正後）：**

```bash
# VM名を命名規則に準拠させる（15文字以内、英数字＆ハイフンのみ）
az vm create \
  --resource-group myRG \
  --name "my-vm-prod-2024" \
  --image UbuntuLTS
```

### 原因3：プロパティ値が許容範囲外

Azure リソースのプロパティには有効な値の範囲が定義されています。例えば、ストレージアカウントのレプリケーション種別には「Standard_LRS」「Standard_GRS」などの定義された値のみが許可され、任意の値を指定することはできません。また、VNetのアドレス空間やサブネットのサイズなど、[ネットワーク](/glossary/ネットワーク/)設定でも有効な範囲チェックが厳密に行われます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# SKU が無効な値
az storage account create \
  --resource-group myRG \
  --name mystorageacct \
  --sku "Premium_Maximum"  # 実在しないSKU値
```

**After（修正後）：**

```bash
# SKU に有効な値を指定
az storage account create \
  --resource-group myRG \
  --name mystorageacct \
  --sku "Standard_LRS"  # 実在するSKU値
```

## ツール固有の注意点

**Azure [REST](/glossary/rest/) [API](/glossary/api/)の場合**：[エラーレスポンス](/glossary/エラーレスポンス/)の `details` フィールドを必ず確認してください。ここに具体的な問題[パラメータ](/glossary/パラメータ/)と制約条件が記載されます。複数の[パラメータ](/glossary/パラメータ/)に問題がある場合も、`details` 配列内に全て列挙されることがあります。また、[API](/glossary/api/)バージョン（`api-version` クエリパラメータ）が古すぎたり新しすぎたりする場合も400[エラー](/glossary/エラー/)になるため、Microsoft公式ドキュメントで対象リソースの最新[API](/glossary/api/)バージョンを確認することが重要です。

**Azure [CLI](/glossary/cli/)の場合**：`--debug` フラグを付与することで、送信される[ペイロード](/glossary/ペイロード/)全体を[コンソール](/glossary/コンソール/)に出力できます。これにより、[CLI](/glossary/cli/)が実際に何を送信しているかを検証でき、[デバッグ](/glossary/デバッグ/)が格段に容易になります。例えば `az vm create ... --debug` とすると、[REST](/glossary/rest/) [API](/glossary/api/)の完全な[リクエストボディ](/glossary/リクエストボディ/)が表示されます。

**Azure Portalの場合**：ブラウザーの開発者ツール（F12キー）でネットワークタブを開き、失敗した[リクエスト](/glossary/リクエスト/)の[レスポンス](/glossary/レスポンス/)を確認することで、エラーメッセージ全文を取得できます。

## それでも解決しない場合

以下の手順でさらに詳細な[デバッグ](/glossary/デバッグ/)を進めてください。

**Azure [CLI](/glossary/cli/)での詳細確認**：

```bash
# 詳細ログを出力
az vm create --resource-group myRG --name myvm --image UbuntuLTS --debug

# コマンドのヘルプで全パラメータと型を確認
az vm create --help | grep -A 5 "adminUsername"
```

**[REST](/glossary/rest/) [API](/glossary/api/)での[デバッグ](/glossary/デバッグ/)**：[リクエストボディ](/glossary/リクエストボディ/)を[JSON](/glossary/json/)形式で整形・検証してから送信します。[JSON](/glossary/json/)スキーマバリデーターを使用し、構造の正確性を事前確認することをお勧めします。

**Azure [SDK](/glossary/sdk/)（Python）での詳細確認**：

```python
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.core.exceptions import HttpResponseError

credential = DefaultAzureCredential()
client = ComputeManagementClient(credential, subscription_id="<subscription-id>")

try:
    vm_params = {
        "location": "japaneast",
        "os_profile": {"computer_name": "myvm", "admin_username": "azureuser"},
        # adminUserPassword をこのようにSDKで指定する場合、型と値が正しいか確認
    }
    client.virtual_machines.begin_create_or_update("myRG", "myvm", vm_params)
except HttpResponseError as e:
    print(f"Status Code: {e.status_code}")
    print(f"Error Message: {e.message}")
    print(f"Error Details: {e.error}")
```

**公式リファレンス**：以下から対象リソースの最新仕様を確認してください。
- [Azure REST API Reference](https://learn.microsoft.com/en-us/rest/api/azure/)
- [Azure CLI コマンドリファレンス](https://learn.microsoft.com/en-us/cli/azure/reference-index)
- [リソース名の命名規則](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/naming-and-tagging)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*