---
title: "Azure の 404 エラー：原因と解決策"
date: 2026-06-01
description: "指定したAzureリソースが見つからない。Azure 404 エラーの原因と解決策を解説します。"
tags: ["Azure"]
errorCode: "404"
service: "Azure"
error_type: "404"
components: ["Virtual Machines", "Storage Accounts", "REST API", "Azure CLI", "Azure Portal", "Azure Backup"]
related_services: ["Azure Portal", "Azure CLI", "REST API"]
---
## エラーの概要

Azureの404[エラー](/glossary/エラー/)は、[API](/glossary/api/)やポータルからアクセスしようとしたリソースが見つからないことを示す[HTTP](/glossary/http/)[エラー](/glossary/エラー/)です。この[エラー](/glossary/エラー/)が発生すると、指定したリソース名、リソースID、あるいは[API](/glossary/api/)[エンドポイント](/glossary/エンドポイント/)が存在しないか、[アクセス権限](/glossary/アクセス権限/)がない状態を意味します。Azure [CLI](/glossary/cli/)や[REST](/glossary/rest/) [API](/glossary/api/)、Azure Portalを通じてリソースを操作する際に頻繁に遭遇する[エラー](/glossary/エラー/)であり、原因の特定と対処には体系的なアプローチが必要です。

## 実際のエラーメッセージ例

**Azure [CLI](/glossary/cli/)の出力例：**

```json
{
  "error": {
    "code": "ResourceNotFound",
    "message": "The Resource 'Microsoft.Compute/virtualMachines/<vm-name>' under resource group '<resource-group-name>' was not found."
  }
}
```

**[REST](/glossary/rest/) [API](/glossary/api/)[レスポンス](/glossary/レスポンス/)例：**

```json
{
  "code": "NotFound",
  "message": "The specified blob does not exist.",
  "details": []
}
```

**Azure [CLI](/glossary/cli/)標準[エラー](/glossary/エラー/)出力例：**

```bash
The resource with id /subscriptions/<subscription-id>/resourceGroups/<rg-name>/providers/Microsoft.Storage/storageAccounts/<account-name> does not exist. (Code: ResourceNotFound)
```

## よくある原因と解決手順

### 原因1：リソース名またはIDの綴りが間違っている

Azureのリソース名やリソースIDに入力ミスがあると、404[エラー](/glossary/エラー/)が発生します。特にストレージアカウント名やVirtual Machine名は大文字小文字が区別され、ハイフンやアンダースコアが混在することで綴り間違いが起きやすくなります。また、[REST](/glossary/rest/) [API](/glossary/api/)で完全修飾リソースID（例：`/subscriptions/.../resourceGroups/.../providers/...`）を指定する場合、パス内のどこかに誤字があると該当リソースが見つかりません。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
az vm show --resource-group myResourceGroup --name myVirtualMahine
```

**After（修正後）：**

```bash
az vm show --resource-group myResourceGroup --name myVirtualMachine
```

---

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
curl -X GET \
  https://management.azure.com/subscriptions/<subscription-id>/resourceGroups/myRG/providers/Microsoft.Storage/storageAccounts/mystorgeaccount/listKeys?api-version=2023-01-01 \
  -H "Authorization: Bearer <access-token>"
```

**After（修正後）：**

```bash
curl -X GET \
  https://management.azure.com/subscriptions/<subscription-id>/resourceGroups/myRG/providers/Microsoft.Storage/storageAccounts/mystorageaccount/listKeys?api-version=2023-01-01 \
  -H "Authorization: Bearer <access-token>"
```

### 原因2：リソースが別のサブスクリプションまたはリソースグループに存在する

複数のAzureサブスクリプションを管理している場合、現在の[CLI](/glossary/cli/)セッションで選択されているサブスクリプションと実際のリソースが存在するサブスクリプションが異なることがあります。同様に、リソース名は複数のリソースグループで重複する可能性があり、指定したリソースグループに該当するリソースが存在しない場合も404[エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# サブスクリプションAが選択されている状態
az vm show --resource-group myResourceGroup --name myVM
# しかし myVM はサブスクリプションBのリソースグループに存在する
```

**After（修正後）：**

```bash
# 現在のサブスクリプションを確認
az account show

# 正しいサブスクリプションに切り替える
az account set --subscription <subscription-id-or-name>

# その後、リソースを照会
az vm show --resource-group myResourceGroup --name myVM
```

---

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
az storage account show --resource-group wrongResourceGroup --name mystorageaccount
# mystorageaccount は別のリソースグループ correctResourceGroup に存在する
```

**After（修正後）：**

```bash
# まず、リソースグループを確認
az resource list --resource-group wrongResourceGroup

# 正しいリソースグループを指定
az storage account show --resource-group correctResourceGroup --name mystorageaccount
```

### 原因3：リソースがすでに削除されている

Azureでリソースを削除した後、その削除が完全に反映されるまでにはわずかな遅延が生じることがあります。削除後のリソースに対してアクセスや操作を行おうとすれば、404[エラー](/glossary/エラー/)が発生します。削除されたリソースの復旧が必要な場合、Azure Backupやリソースの再作成が必要になります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# リソースをいったん削除してから操作
az vm delete --resource-group myResourceGroup --name myVM --yes

# その直後にリソースを参照（404エラーが発生）
az vm show --resource-group myResourceGroup --name myVM
```

**After（修正後）：**

```bash
# 削除前にリソースが存在するか確認
az vm show --resource-group myResourceGroup --name myVM

# 削除後は、必要に応じて新たに作成する
az vm create --resource-group myResourceGroup --name myVM --image UbuntuLTS
```

---

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# ストレージアカウントが削除されている
az storage account show --resource-group myResourceGroup --name myDeletedAccount
```

**After（修正後）：**

```bash
# リソースリストで削除されていないか確認
az storage account list --resource-group myResourceGroup

# 削除されていた場合、新規作成
az storage account create --name mynewstorageaccount --resource-group myResourceGroup --location japaneast
```

## ツール固有の注意点

Azure環境では、複数のレイヤーで404[エラー](/glossary/エラー/)が発生する可能性があります。

**Azure Portalでの確認：** Portalから直接リソースを検索する際、左側の検索バーにリソース名を入力してもヒットしない場合、別のサブスクリプションに存在するか、既に削除されていることが大半です。Portalの場合、右上のサブスクリプションフィルターで現在の[スコープ](/glossary/スコープ/)（対象範囲）を確認することが重要です。

**Azure [CLI](/glossary/cli/)と[API](/glossary/api/)バージョン：** Azure [CLI](/glossary/cli/)でリソースを操作する際、使用している[API](/glossary/api/)バージョンが古い場合、新しいリソースタイプが認識されない可能性があります。例えば、`az vm show`の背後で使用されるCompute [API](/glossary/api/)のバージョンが古いと、新しいVMプロパティは見つからずに404的な[エラー](/glossary/エラー/)になることもあります。最新の操作には`--api-version`パラメーターで明示的にバージョンを指定することをお勧めします。

**[REST](/glossary/rest/) [API](/glossary/api/)とリソースID形式：** Azure [REST](/glossary/rest/) [API](/glossary/api/)を直接呼び出す場合、リソースIDは必ず`/subscriptions/{subscription-id}/resourceGroups/{resource-group-name}/providers/{resource-provider}/{resource-type}/{resource-name}`の形式に従う必要があります。この形式が少しでも異なると404が発生します。特に、入れ子になったリソース（例：VNet内のサブネット）では、パス構造を厳密に守る必要があります。

## それでも解決しない場合

**リソースの存在確認[コマンド](/glossary/コマンド/)：**

```bash
# 特定のリソースグループ内のすべてのリソースを一覧表示
az resource list --resource-group <resource-group-name>

# サブスクリプション全体でリソースを検索
az resource list --subscription <subscription-id>

# タイプを指定して検索（例：ストレージアカウント）
az storage account list --resource-group <resource-group-name>
```

**現在のサブスクリプション確認：**

```bash
# 現在選択されているサブスクリプションを表示
az account show

# すべてのサブスクリプションを一覧表示
az account list --output table
```

**[REST](/glossary/rest/) [API](/glossary/api/)で詳細な[エラー](/glossary/エラー/)を取得：**

```bash
# Azureへのトークン取得
TOKEN=$(az account get-access-token --query accessToken -o tsv)

# 詳細なエラーレスポンスを確認
curl -X GET \
  https://management.azure.com/subscriptions/<subscription-id>/resourceGroups/<resource-group-name>/providers/Microsoft.Compute/virtualMachines/<vm-name>?api-version=2023-03-01 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json"
```

**Azure [CLI](/glossary/cli/)の[デバッグ](/glossary/デバッグ/)出力：**

```bash
# --debug フラグを追加して、詳細なリクエスト情報を表示
az vm show --resource-group myResourceGroup --name myVM --debug
```

Azure公式ドキュメント（[Azure Resource Management API](https://learn.microsoft.com/en-us/rest/api/resources/)）では、各リソースタイプの正確な[API](/glossary/api/)形式とパスが記載されています。疑わしい場合は、リソースタイプの公式リファレンスを参照して、正しい[エンドポイント](/glossary/エンドポイント/)形式と必須パラメーターを再確認することをお勧めします。また、Azure [CLI](/glossary/cli/)のバージョンが古い可能性がある場合は、`az upgrade`で最新版に更新してから再度試行してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*