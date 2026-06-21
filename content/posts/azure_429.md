---
title: "Azure の 429 エラー：原因と解決策"
date: 2026-06-02
description: "Azure APIのスロットリング制限に達した"
tags: ["Azure"]
errorCode: "429"
service: "Azure"
error_type: "429"
components: ["REST API", "Virtual Machines", "Compute"]
related_services: ["PowerShell", "Azure CLI"]
trend_incident: true
lastmod: 2026-06-13
---

## エラーの概要

429 Too Many Requests [エラー](/glossary/エラー/)は、Azure [API](/glossary/api/) が[スロットリング](/glossary/スロットリング/)制限に達したことを示す [HTTP](/glossary/http/) [ステータスコード](/glossary/ステータスコード/)です。Azure では、各サブスクリプションと [API](/glossary/api/) に対して一定期間内の[リクエスト](/glossary/リクエスト/)数に上限を設定しており、この制限を超えたときに発生します。特に、自動化スクリプトやバッチ処理でループ内から大量の[リクエスト](/glossary/リクエスト/)を送信する場合に頻繁に見られます。

## 実際のエラーメッセージ例

Azure [REST](/glossary/rest/) [API](/glossary/api/) の直接呼び出しで見られる典型的な[レスポンス](/glossary/レスポンス/)：

```json
{
  "error": {
    "code": "SubscriptionThrottled",
    "message": "The subscription is throttled for the following operation: Microsoft.Compute/virtualMachines/write. Please try after 30 seconds."
  }
}
```

Azure [SDK](/glossary/sdk/)（Python）で発生した場合の[コンソール](/glossary/コンソール/)出力：

```
azure.core.exceptions.HttpResponseError: (429) Throttling error. Subscription has exceeded throttling limits for operation 'Microsoft.Storage/storageAccounts/write'. Retry after 60 seconds.
```

## よくある原因と解決手順

### 原因1：リクエストレートが上限を超えている

Azure には、[API](/glossary/api/) ごと・操作ごと（例：仮想マシン作成、ストレージ読み書き）に一定秒あたりの[リクエスト](/glossary/リクエスト/)数制限があります。制限値はサブスクリプション、リージョン、リソースの種類によって異なり、ループ内で連続して [API](/glossary/api/) を呼び出すと瞬時に制限に達します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient

credential = DefaultAzureCredential()
client = ComputeManagementClient(credential, "<subscription_id>")

# 50 台の VM を一気に作成しようとする
for i in range(50):
    client.virtual_machines.begin_create_or_update(
        "<resource_group>",
        f"vm-{i}",
        vm_config
    )
```

**After（修正後）：**

```python
import time
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient

credential = DefaultAzureCredential()
client = ComputeManagementClient(credential, "<subscription_id>")

# リクエスト間に遅延を挿入
for i in range(50):
    try:
        client.virtual_machines.begin_create_or_update(
            "<resource_group>",
            f"vm-{i}",
            vm_config
        )
    except Exception as e:
        if "429" in str(e) or "throttled" in str(e).lower():
            # Retry-After ヘッダーから推奨待機時間を取得
            retry_after = 60
            print(f"スロットリング検出。{retry_after} 秒待機します")
            time.sleep(retry_after)
            # リトライ処理を含める
            client.virtual_machines.begin_create_or_update(
                "<resource_group>",
                f"vm-{i}",
                vm_config
            )
        else:
            raise
    
    # 各リクエスト間に 2 秒の遅延を設定
    time.sleep(2)
```

### 原因2：Retry-After ヘッダーを無視している

Azure [API](/glossary/api/) が 429 を返す際、必ず `Retry-After` レスポンスヘッダーに推奨される再試行待機時間を含めます。この[ヘッダー](/glossary/ヘッダー/)を無視して即座に[リトライ](/glossary/リトライ/)すると、さらに[スロットリング](/glossary/スロットリング/)が重くなります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
const { ComputeManagementClient } = require("@azure/arm-compute");
const { DefaultAzureCredential } = require("@azure/identity");

async function createVMs() {
    const credential = new DefaultAzureCredential();
    const client = new ComputeManagementClient(credential, "<subscription_id>");
    
    // Retry-After を無視した単純なリトライ
    let retries = 0;
    while (retries < 5) {
        try {
            await client.virtualMachines.beginCreateOrUpdateAndWait(
                "<resource_group>",
                "vm-1",
                vmConfig
            );
            break;
        } catch (err) {
            retries++;
            // 固定時間でリトライ（推奨時間を無視）
            await new Promise(r => setTimeout(r, 1000));
        }
    }
}
```

**After（修正後）：**

```javascript
const { ComputeManagementClient } = require("@azure/arm-compute");
const { DefaultAzureCredential } = require("@azure/identity");

async function createVMs() {
    const credential = new DefaultAzureCredential();
    const client = new ComputeManagementClient(credential, "<subscription_id>");
    
    let retries = 0;
    while (retries < 5) {
        try {
            await client.virtualMachines.beginCreateOrUpdateAndWait(
                "<resource_group>",
                "vm-1",
                vmConfig
            );
            break;
        } catch (err) {
            // Retry-After ヘッダーから待機時間を取得
            let retryAfter = 60;
            if (err.response && err.response.headers) {
                const headerValue = err.response.headers["retry-after"];
                if (headerValue) {
                    retryAfter = parseInt(headerValue, 10);
                }
            }
            
            console.log(`429 エラー。${retryAfter} 秒後に再試行します`);
            await new Promise(r => setTimeout(r, retryAfter * 1000));
            retries++;
        }
    }
}
```

### 原因3：複数の操作を同時実行している

Azure 関数、Logic Apps、Data Factory など、複数の処理が並列実行される環境では、複合的な[スロットリング](/glossary/スロットリング/)が発生しやすくなります。特にマネージドサービスでの自動スケーリング時に、大量のワーカーが同時に同じ [API](/glossary/api/) を呼び出すと瞬時に制限に達します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
import asyncio
from azure.identity import DefaultAzureCredential
from azure.mgmt.storage import StorageManagementClient

async def delete_storage_accounts():
    credential = DefaultAzureCredential()
    client = StorageManagementClient(credential, "<subscription_id>")
    
    # 20 個のストレージアカウントを同時削除
    tasks = []
    for account_name in storage_accounts:
        task = asyncio.create_task(
            asyncio.to_thread(
                client.storage_accounts.delete,
                "<resource_group>",
                account_name
            )
        )
        tasks.append(task)
    
    # すべてのタスクを同時実行
    await asyncio.gather(*tasks)
```

**After（修正後）：**

```python
import asyncio
from azure.identity import DefaultAzureCredential
from azure.mgmt.storage import StorageManagementClient

async def delete_storage_accounts():
    credential = DefaultAzureCredential()
    client = StorageManagementClient(credential, "<subscription_id>")
    
    # 同時実行数を制限（並行数 3）
    semaphore = asyncio.Semaphore(3)
    
    async def delete_with_limit(account_name):
        async with semaphore:
            try:
                await asyncio.to_thread(
                    client.storage_accounts.delete,
                    "<resource_group>",
                    account_name
                )
            except Exception as e:
                if "429" in str(e):
                    print(f"スロットリング。30 秒待機してからリトライします")
                    await asyncio.sleep(30)
                    await asyncio.to_thread(
                        client.storage_accounts.delete,
                        "<resource_group>",
                        account_name
                    )
                else:
                    raise
    
    tasks = [delete_with_limit(acc) for acc in storage_accounts]
    await asyncio.gather(*tasks)
```

## ツール固有の注意点

### Azure ストレージアカウントのスロットリング制限

ストレージアカウントには、BLOB、Table、Queue などのサービスごとに独立した制限があります。標準[アカウント](/glossary/アカウント/)のスケーラビリティ目標は、単一[アカウント](/glossary/アカウント/)あたり秒間 20,000 [リクエスト](/glossary/リクエスト/)程度ですが、特定の操作（例：PutBlock）はさらに低い制限を持ちます。大規模なアップロード・ダウンロード時は、複数ストレージアカウントに分散させるか、Azure Data Lake Storage Gen2 への移行を検討してください。

### Azure App Service・Function App での 429

Azure Function App で[バージョン](/glossary/バージョン/) 4 ランタイムを使用している場合、デフォルトの [HTTP](/glossary/http/) 接続数制限（`http.connectionLimit`）により、外部 [API](/glossary/api/) へのアウトバウンド呼び出しがスロットルされることがあります。このとき、Azure の [REST](/glossary/rest/) [API](/glossary/api/) ではなく、呼び出し先の外部サービスの 429 が返される可能性も高いため、[エラーメッセージ](/glossary/エラーメッセージ/)で `microsoft.com` を含むか確認し、実際にどのサービスが制限を返しているかを特定してください。

### Azure DevOps の API レート制限

Azure DevOps（旧 VSTS）で Pipelines、Work Items、Repos [API](/glossary/api/) を大量に呼び出す場合、認証方式によって制限が異なります。PAT（Personal Access Token）では秒間 200 [リクエスト](/glossary/リクエスト/)、アプリケーション[認証](/glossary/認証/)では秒間 6,000 [リクエスト](/glossary/リクエスト/)が目安です。[CI/CD](/glossary/ci-cd/) で多数のジョブを並列実行する際は、リトライロジックと指数[バックオフ](/glossary/バックオフ/)の実装が必須です。

### Azure Resource Graph のクエリ制限

Resource Graph では、複雑な KQL [クエリ](/glossary/クエリ/)や大規模なサブスクリプション横断検索の際に 429 が発生しやすくなります。[クエリ](/glossary/クエリ/)の複雑性スコアを `$skip` [トークン](/glossary/トークン/)で段階的に削減し、バッチサイズを最大 1,000 件に制限してください。

## それでも解決しない場合

### ログとデバッグ情報の確認

Azure [CLI](/glossary/cli/) で診断[ログ](/glossary/ログ/)を有効化：

```bash
az monitor diagnostic-settings create \
  --name <setting_name> \
  --resource <resource_id> \
  --logs '[{"category":"ServiceFabricSystemEventTable","enabled":true}]' \
  --workspace <workspace_id>
```

Python [SDK](/glossary/sdk/) でデバッグレベルの[ログ](/glossary/ログ/)を有効化し、[リクエスト](/glossary/リクエスト/)・レスポンスヘッダーを確認：

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Azure SDK ログを有効化
azure_logger = logging.getLogger("azure")
azure_logger.setLevel(logging.DEBUG)
```

### 公式リファレンスの確認

以下のドキュメントで、各 Azure サービスの具体的な[スロットリング](/glossary/スロットリング/)制限値を確認してください：

- **Azure Subscription and service limits, quotas, and constraints**
  https://learn.microsoft.com/ja-jp/azure/azure-resource-manager/management/azure-subscription-service-limits

- **Handling Throttling Errors in Azure**
  https://learn.microsoft.com/ja-jp/azure/architecture/best-practices/retry-service-specific

- **Azure [SDK](/glossary/sdk/) for Python - Troubleshooting**
  https://github.com/Azure/azure-sdk-for-python/wiki/Troubleshooting

### コミュニティサポート

Azure [SDK](/glossary/sdk/) の[リトライ](/glossary/リトライ/)実装に関する既知の問題や解決方法は、公式 GitHub [リポジトリ](/glossary/リポジトリ/)で確認できます：

- https://github.com/Azure/azure-sdk-for-python/issues
- https://github.com/Azure/azure-sdk-for-java/issues
- https://github.com/Azure/azure-sdk-for-js/issues

問題が特定の [SDK](/glossary/sdk/) [バージョン](/glossary/バージョン/)やサービスに限定される場合は、リージョンの状態ページ（https://status.azure.com）も確認し、Azure 側のインシデント有無を確認してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*