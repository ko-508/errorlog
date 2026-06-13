---
title: "Azure の 429 エラー：原因と解決策"
date: 2026-06-02
description: "Azure APIのスロットリング制限に達した。Azure 429 エラーの原因と解決策を解説します。"
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

429 Too Many Requests エラーは、Azure API がスロットリング制限に達したことを示す HTTP ステータスコードです。Azure では、各サブスクリプションと API に対して一定期間内のリクエスト数に上限を設定しており、この制限を超えたときに発生します。特に、自動化スクリプトやバッチ処理でループ内から大量のリクエストを送信する場合に頻繁に見られます。

## 実際のエラーメッセージ例

Azure REST API の直接呼び出しで見られる典型的なレスポンス：

```json
{
  "error": {
    "code": "SubscriptionThrottled",
    "message": "The subscription is throttled for the following operation: Microsoft.Compute/virtualMachines/write. Please try after 30 seconds."
  }
}
```

Azure SDK（Python）で発生した場合のコンソール出力：

```
azure.core.exceptions.HttpResponseError: (429) Throttling error. Subscription has exceeded throttling limits for operation 'Microsoft.Storage/storageAccounts/write'. Retry after 60 seconds.
```

## よくある原因と解決手順

### 原因1：リクエストレートが上限を超えている

Azure には、API ごと・操作ごと（例：仮想マシン作成、ストレージ読み書き）に一定秒あたりのリクエスト数制限があります。制限値はサブスクリプション、リージョン、リソースの種類によって異なり、ループ内で連続して API を呼び出すと瞬時に制限に達します。

**Before（エラーが起きるコード）：**

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

Azure API が 429 を返す際、必ず `Retry-After` レスポンスヘッダーに推奨される再試行待機時間を含めます。このヘッダーを無視して即座にリトライすると、さらにスロットリングが重くなります。

**Before（エラーが起きるコード）：**

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

Azure 関数、Logic Apps、Data Factory など、複数の処理が並列実行される環境では、複合的なスロットリングが発生しやすくなります。特にマネージドサービスでの自動スケーリング時に、大量のワーカーが同時に同じ API を呼び出すと瞬時に制限に達します。

**Before（エラーが起きるコード）：**

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

ストレージアカウントには、BLOB、Table、Queue などのサービスごとに独立した制限があります。標準アカウントのスケーラビリティ目標は、単一アカウントあたり秒間 20,000 リクエスト程度ですが、特定の操作（例：PutBlock）はさらに低い制限を持ちます。大規模なアップロード・ダウンロード時は、複数ストレージアカウントに分散させるか、Azure Data Lake Storage Gen2 への移行を検討してください。

### Azure App Service・Function App での 429

Azure Function App でバージョン 4 ランタイムを使用している場合、デフォルトの HTTP 接続数制限（`http.connectionLimit`）により、外部 API へのアウトバウンド呼び出しがスロットルされることがあります。このとき、Azure の REST API ではなく、呼び出し先の外部サービスの 429 が返される可能性も高いため、エラーメッセージで `microsoft.com` を含むか確認し、実際にどのサービスが制限を返しているかを特定してください。

### Azure DevOps の API レート制限

Azure DevOps（旧 VSTS）で Pipelines、Work Items、Repos API を大量に呼び出す場合、認証方式によって制限が異なります。PAT（Personal Access Token）では秒間 200 リクエスト、アプリケーション認証では秒間 6,000 リクエストが目安です。CI/CD で多数のジョブを並列実行する際は、リトライロジックと指数バックオフの実装が必須です。

### Azure Resource Graph のクエリ制限

Resource Graph では、複雑な KQL クエリや大規模なサブスクリプション横断検索の際に 429 が発生しやすくなります。クエリの複雑性スコアを `$skip` トークンで段階的に削減し、バッチサイズを最大 1,000 件に制限してください。

## それでも解決しない場合

### ログとデバッグ情報の確認

Azure CLI で診断ログを有効化：

```bash
az monitor diagnostic-settings create \
  --name <setting_name> \
  --resource <resource_id> \
  --logs '[{"category":"ServiceFabricSystemEventTable","enabled":true}]' \
  --workspace <workspace_id>
```

Python SDK でデバッグレベルのログを有効化し、リクエスト・レスポンスヘッダーを確認：

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Azure SDK ログを有効化
azure_logger = logging.getLogger("azure")
azure_logger.setLevel(logging.DEBUG)
```

### 公式リファレンスの確認

以下のドキュメントで、各 Azure サービスの具体的なスロットリング制限値を確認してください：

- **Azure Subscription and service limits, quotas, and constraints**
  https://learn.microsoft.com/ja-jp/azure/azure-resource-manager/management/azure-subscription-service-limits

- **Handling Throttling Errors in Azure**
  https://learn.microsoft.com/ja-jp/azure/architecture/best-practices/retry-service-specific

- **Azure SDK for Python - Troubleshooting**
  https://github.com/Azure/azure-sdk-for-python/wiki/Troubleshooting

### コミュニティサポート

Azure SDK のリトライ実装に関する既知の問題や解決方法は、公式 GitHub リポジトリで確認できます：

- https://github.com/Azure/azure-sdk-for-python/issues
- https://github.com/Azure/azure-sdk-for-java/issues
- https://github.com/Azure/azure-sdk-for-js/issues

問題が特定の SDK バージョンやサービスに限定される場合は、リージョンの状態ページ（https://status.azure.com）も確認し、Azure 側のインシデント有無を確認してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*