---
title: "Azure の 403 エラー：原因と解決策"
date: 2026-06-01
description: "Azureリソースへのアクセスが拒否された。Azure 403 エラーの原因と解決策を解説します。"
tags: ["Azure"]
errorCode: "403"
service: "Azure"
error_type: "403"
components: ["RBAC", "Azure Policy", "Virtual Machine Contributor", "Azure SQL Database", "Azure Portal", "Azure CLI"]
related_services: []
---
## エラーの概要

Azure リソースへのアクセスが拒否されたことを示す HTTP 403 エラーです。このエラーは、ユーザーやアプリケーションが認証には成功（401 ではなく）したものの、対象リソースに対する**操作権限がない**ことを意味します。Azure では RBAC（ロールベースアクセス制御）、Azure Policy、ネットワーク設定などの複数のレイヤーで権限チェックが行われるため、403 が頻繁に発生します。

## 実際のエラーメッセージ例

Azure Portal や Azure CLI を通じて 403 エラーが出力される場合、以下のような形式で表示されます。

```json
{
  "error": {
    "code": "AuthorizationFailed",
    "message": "The client 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' with object id 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' does not have authorization to perform action 'Microsoft.Compute/virtualMachines/write' over scope '/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.Compute/virtualMachines/<vm-name>'."
  }
}
```

```bash
$ az vm create --resource-group <resource-group> --name <vm-name> ...
(AuthorizationFailed) The client 'user@example.com' with object id '...' 
does not have authorization to perform action 'Microsoft.Compute/virtualMachines/write'
```

## よくある原因と解決手順

### 原因 1：RBAC で必要なロールが割り当てられていない

Azure RBAC により、ユーザーやサービスプリンシパルに対して明示的にロールを割り当てない限り、リソースへの操作は拒否されます。例えば、仮想マシンの作成には「仮想マシン共同作成者」や「共同作成者」ロールが必要です。サブスクリプションやリソースグループレベルでロールが割り当てられていなければ、その配下のすべてのリソース操作が 403 で拒否されます。

**修正例：**

```bash
# 1. ユーザーのオブジェクト ID を取得
OBJECT_ID=$(az ad user show --id user@example.com --query id -o tsv)

# 2. サブスクリプションレベルで "Virtual Machine Contributor" ロールを割り当て
az role assignment create \
  --assignee $OBJECT_ID \
  --role "Virtual Machine Contributor" \
  --scope /subscriptions/<subscription-id>

# 3. その後、VM 作成を実行
$ az vm create \
  --resource-group myResourceGroup \
  --name myVM \
  --image UbuntuLTS
```

### 原因 2：Azure Policy が操作を制限している

Azure Policy により、特定の操作やリソースタイプの作成が組織レベルで制限されていることがあります。例えば、「本番環境では D シリーズ以上の VM のみ許可」といったポリシーが適用されている場合、B シリーズ VM の作成は 403 で拒否されます。ユーザーが十分な RBAC 権限を持っていても、Policy の制約により操作は失敗します。

**修正例：**

```bash
# 1. 適用されている Policy を確認
$ az policy assignment list \
  --scope /subscriptions/<subscription-id> \
  --query "[].displayName" -o table

# 2. 制限されている操作を確認
$ az policy definition show \
  --name <policy-name> \
  --query "properties.policyRule"

# 3. ポリシーに準拠したリソース設定で実行
$ az storage account create \
  --name mystorageaccount \
  --resource-group myResourceGroup \
  --location eastus \
  --sku Standard_GRS
```

### 原因 3：リソースのネットワーク設定でアクセスが制限されている

リソースが仮想ネットワーク内に配置されていたり、プライベートエンドポイント経由のアクセスのみに制限されていたり、ファイアウォール設定で特定の IP 範囲のみを許可しているケースです。管理者側の RBAC は正しくても、ネットワークレベルで接続そのものが遮断されると、403 で拒否されます。例えば、Azure SQL Database にファイアウォール設定があり、クライアント IP が許可リストに含まれていない場合、認証後も操作は 403 となります。

**修正例：**

```bash
# 1. ファイアウォール規則を確認
$ az sql server firewall-rule list \
  --resource-group myResourceGroup \
  --server myserver

# 2. 自分のクライアント IP を許可リストに追加
$ az sql server firewall-rule create \
  --resource-group myResourceGroup \
  --server myserver \
  --name AllowMyIP \
  --start-ip-address <your-ip> \
  --end-ip-address <your-ip>

# 3. その後、SQL DB の操作を再実行
$ az sql db show \
  --resource-group myResourceGroup \
  --server myserver \
  --name mydb
```

## ツール固有の注意点

**Azure Portal での RBAC 確認方法**：
リソースに対して直接アクセス制御（IAM）を設定することで、より細粒度な権限管理が可能です。Azure Portal でリソースを選択し、左側メニューから「アクセス制御（IAM）」を開き、「ロールの割り当てを確認」をクリックすることで、現在の割り当て状況を視覚的に確認できます。

**Azure CLI での権限確認コマンド**：
```bash
# 特定ユーザーに割り当てられたすべてのロール（サブスクリプション配下）を表示
$ az role assignment list \
  --assignee <object-id-or-email> \
  --subscription <subscription-id>

# リソースグループレベルで確認する場合
$ az role assignment list \
  --assignee <object-id-or-email> \
  --scope /subscriptions/<subscription-id>/resourceGroups/<resource-group>
```

**マネージドアイデンティティの場合**：
Azure VM や App Service などがマネージドアイデンティティを使用する場合、そのマネージドアイデンティティに対して RBAC ロールを割り当てる必要があります。サービスプリンシパルのオブジェクト ID（通常は Azure AD 上の名前）を確認し、同様に `az role assignment create` でロール割り当てを行います。

**Terraform での RBAC 設定例**：
```hcl
# Terraform を使用して RBAC ロール割り当てを自動化
resource "azurerm_role_assignment" "example" {
  scope              = azurerm_resource_group.example.id
  role_definition_name = "Virtual Machine Contributor"
  principal_id       = data.azurerm_client_config.current.object_id
}
```

## それでも解決しない場合

Azure のアクティビティログを確認し、より詳細なエラーメッセージを取得してください。

```bash
# Azure Activity Log からエラーの詳細を検索
$ az monitor activity-log list \
  --resource-group <resource-group> \
  --query "[?contains(properties.eventName, 'Write')].{Time:eventTimestamp, Message:properties.statusMessage}" \
  --output table
```

Azure Portal の「監視」→「アクティビティログ」からも、リアルタイムでエラーイベントを追跡できます。403 エラーが発生した時刻を基準に、対応するログエントリを検索し、「状態」「リクエスト」タブから詳細な JSON レスポンスを確認することで、Policy が拒否しているのか、RBAC か、ネットワーク設定かを判定できます。

サービスプリンシパルやマネージドアイデンティティを使用する場合、Azure AD の Application Registration から該当オブジェクトのオブジェクト ID が正しいか再確認してください。`az ad sp show --id <client-id>` で確認できます。

最新の Azure RBAC ロール定義や Policy については、[Microsoft Learn - Azure RBAC のドキュメント](https://learn.microsoft.com/ja-jp/azure/role-based-access-control/)および [Azure Policy の公式ページ](https://learn.microsoft.com/ja-jp/azure/governance/policy/)を参照してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*