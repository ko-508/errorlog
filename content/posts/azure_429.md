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
---
## エラーの概要

429 Too Many Requests [エラー](/glossary/エラー/)は、Azure [API](/glossary/api/)が[スロットリング](/glossary/スロットリング/)制限に達したことを示す[HTTP](/glossary/http/)[ステータスコード](/glossary/ステータスコード/)です。Azure では、各サブスクリプションと [API](/glossary/api/) に対して一定期間内の[リクエスト](/glossary/リクエスト/)数に上限を設定しており、この制限を超えたときに発生します。特に、自動化スクリプトやバッチ処理でループ内から大量の[リクエスト](/glossary/リクエスト/)を送信する場合に頻繁に見られます。

## 実際のエラーメッセージ例

Azure [REST](/glossary/rest/) [API](/glossary/api/) の直接呼び出しで見られる典型的な[レスポンス](/glossary/レスポンス/)：

```json
{
  "error": {
    "code": "SubscriptionThrottled",
    "message": "The subscription is throttled for the following operation: Microsoft.Compute/virtualMachines/read. Please retry after 60 seconds."
  },
  "statusCode": 429,
  "x-ms-ratelimit-remaining-subscription-reads": "0",
  "x-ms-ratelimit-remaining-subscription-writes": "4999",
  "x-ms-ratelimit-remaining-requests-timeout": "00:00:60"
}
```

PowerShell で Azure [CLI](/glossary/cli/) を使用した場合の[コンソール](/glossary/コンソール/)出力例：

```bash
Response status code does not indicate success: 429 (Too Many Requests).
The subscription is throttled for the following operation.
Retry-After: 60
```

## よくある原因と解決手順

### 原因1：短時間に多数のAPIリクエストを送信した

複数のリソースを一括取得・更新する際に、ループ内で同期的に[リクエスト](/glossary/リクエスト/)を送信し続けると、Azure の[スロットリング](/glossary/スロットリング/)制限に達します。Azure はサブスクリプション単位で読み取り上限（デフォルト：毎秒 200 回）、書き込み上限（デフォルト：毎秒 100 回）を適用しています。特に、リソースが多数存在する環境では容易に制限を超えます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
import requests
import json

subscription_id = "<your-subscription-id>"
resource_group = "<your-resource-group>"
token = "<your-access-token>"

# 複数のVMを同期的に列挙
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

for i in range(500):  # 500個のVM情報を連続取得
    url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Compute/virtualMachines/vm-{i}?api-version=2021-07-01"
    response = requests.get(url, headers=headers)
    if response.status_code == 429:
        print("スロットリングに達した")
    data = response.json()
```

**After（修正後）：**

```python
import requests
import json
import time
import asyncio
import aiohttp

subscription_id = "<your-subscription-id>"
resource_group = "<your-resource-group>"
token = "<your-access-token>"

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

# 非同期処理で複数リクエストを並行実行（ただしレート制限内で）
async def fetch_vm(session, vm_id):
    url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Compute/virtualMachines/vm-{vm_id}?api-version=2021-07-01"
    async with session.get(url, headers=headers) as response:
        if response.status == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            print(f"{retry_after}秒後に再試行します")
            await asyncio.sleep(retry_after)
            return await fetch_vm(session, vm_id)  # 再試行
        return await response.json()

async def fetch_all_vms():
    async with aiohttp.ClientSession() as session:
        # 並行数を制限（Azure推奨：最大10-20同時リクエスト）
        tasks = [fetch_vm(session, i) for i in range(500)]
        semaphore = asyncio.Semaphore(10)
        
        async def sem_task(task):
            async with semaphore:
                return await task
        
        results = await asyncio.gather(*[sem_task(task) for task in tasks])
        return results

# 実行
results = asyncio.run(fetch_all_vms())
```

### 原因2：サブスクリプションレベルの読み取り/書き込み上限を超えた

Azure は、[API](/glossary/api/) の種別（読み取り vs 書き込み）ごとに異なる[スロットリング](/glossary/スロットリング/)制限を適用します。読み取り上限は毎秒 200 [リクエスト](/glossary/リクエスト/)、書き込み上限は毎秒 100 [リクエスト](/glossary/リクエスト/)が標準ですが、リソースプロバイダーによって異なる場合があります。複数の異なる [API](/glossary/api/) を同時に呼び出すと、これらの上限を細かく管理する必要があります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
import requests

token = "<your-access-token>"
subscription_id = "<your-subscription-id>"

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

# 監視目的でずっと読み取りリクエストを送り続ける
for iteration in range(1000):
    # 複数リソースプロバイダーから同時に読み取り
    providers = [
        "Microsoft.Compute/virtualMachines",
        "Microsoft.Network/virtualNetworks",
        "Microsoft.Storage/storageAccounts"
    ]
    
    for provider in providers:
        url = f"https://management.azure.com/subscriptions/{subscription_id}/providers/{provider}?api-version=2021-04-01"
        response = requests.get(url, headers=headers)
        data = response.json()
        print(f"Found {len(data.get('value', []))} resources")
```

**After（修正後）：**

```python
import requests
import time
from datetime import datetime, timedelta

token = "<your-access-token>"
subscription_id = "<your-subscription-id>"

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

def check_rate_limit_headers(response):
    """レート制限の残数とリセット時間を確認"""
    remaining_reads = response.headers.get("x-ms-ratelimit-remaining-subscription-reads", "N/A")
    remaining_writes = response.headers.get("x-ms-ratelimit-remaining-subscription-writes", "N/A")
    reset_time = response.headers.get("x-ms-ratelimit-remaining-requests-timeout", "N/A")
    
    print(f"[{datetime.now().isoformat()}] 残り読取: {remaining_reads}, 残り書込: {remaining_writes}, リセット時間: {reset_time}")
    return remaining_reads, remaining_writes

def fetch_with_backoff(url, max_retries=5):
    """指数バックオフによる再試行を実装"""
    for attempt in range(max_retries):
        response = requests.get(url, headers=headers)
        
        # レート制限情報を常に確認
        remaining_reads, remaining_writes = check_rate_limit_headers(response)
        
        if response.status_code == 429:
            # Retry-After ヘッダーを優先、なければ指数バックオフ
            retry_after = int(response.headers.get("Retry-After", 2 ** attempt))
            print(f"429エラー。{retry_after}秒後に再試行します（試行 {attempt + 1}/{max_retries}）")
            time.sleep(retry_after)
            continue
        elif response.status_code == 200:
            return response.json()
        else:
            print(f"予期しないエラー: {response.status_code}")
            break
    
    return None

# リソースを段階的に取得（同時リクエスト数を制限）
providers = [
    "Microsoft.Compute/virtualMachines",
    "Microsoft.Network/virtualNetworks",
    "Microsoft.Storage/storageAccounts"
]

for provider in providers:
    url = f"https://management.azure.com/subscriptions/{subscription_id}/providers/{provider}?api-version=2021-04-01"
    data = fetch_with_backoff(url)
    
    if data:
        print(f"{provider}: {len(data.get('value', []))} 件のリソースを取得")
    
    # プロバイダー間で遅延を挿入（レート制限を回避）
    time.sleep(1)
```

### 原因3：ARM APIのレート制限に達した

Azure Resource Manager（ARM）は、リソースグループごと、リソースプロバイダーごと、さらにはテナントレベルでも段階的な[スロットリング](/glossary/スロットリング/)制限を適用しています。特に、ネストされた複数の [API](/glossary/api/) 呼び出しが連鎖的に発生する自動化では、これらの複数レイヤーの制限に同時に引っかかることがあります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```powershell
# PowerShellで複数のリソースグループに対して一括操作を実行
$token = "YOUR_ACCESS_TOKEN"
$subscriptionId = "YOUR_SUBSCRIPTION_ID"

$headers = @{
    "Authorization" = "Bearer $token"
    "Content-Type"  = "application/json"
}

# 複数のリソースグループ内のすべてのVMを再起動（同期実行）
$resourceGroups = Get-AzResourceGroup

foreach ($rg in $resourceGroups) {
    $vms = Get-AzVM -ResourceGroupName $rg.ResourceGroupName
    
    foreach ($vm in $vms) {
        # 各VM再起動時にARM APIを呼び出し
        $url = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$($rg.ResourceGroupName)/providers/Microsoft.Compute/virtualMachines/$($vm.Name)/restart?api-version=2021-07-01"
        
        $response = Invoke-RestMethod -Uri $url -Headers $headers -Method Post
        Write-Host "Restarted: $($vm.Name)"
    }
}
```

**After（修正後）：**

```powershell
# PowerShellで段階的・制御されたリクエストを実行
$token = "YOUR_ACCESS_TOKEN"
$subscriptionId = "YOUR_SUBSCRIPTION_ID"
$maxConcurrentRequests = 5  # 同時リクエスト数を制限
$delayBetweenBatches = 2    # バッチ間遅延（秒）

$headers = @{
    "Authorization" = "Bearer $token"
    "Content-Type"  = "application/json"
}

$resourceGroups = Get-AzResourceGroup
$vmList = @()

# 全VM情報を事前に収集
foreach ($rg in $resourceGroups) {
    $vms = Get-AzVM -ResourceGroupName $rg.ResourceGroupName
    foreach ($vm in $vms) {
        $vmList += @{
            Name = $vm.Name
            ResourceGroupName = $rg.ResourceGroupName
        }
    }
}

# バッチ処理で段階的に実行
for ($i = 0; $i -lt $vmList.Count; $i += $maxConcurrentRequests) {
    $batch = $vmList[$i..([Math]::Min($i + $maxConcurrentRequests - 1, $vmList.Count - 1))]
    
    foreach ($vm in $batch) {
        $url = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$($vm.ResourceGroupName)/providers/Microsoft.Compute/virtualMachines/$($vm.Name)/restart?api-version=2021-07-01"
        
        try {
            $response = Invoke-RestMethod -Uri $url -Headers $headers -Method Post
            Write-Host "Restarted: $($vm.Name)"
        } catch {
            if ($_.Exception.Response.StatusCode -eq 429) {
                $retryAfter = $_.Exception.Response.Headers["Retry-After"]
                Write-Host "レート制限に達しました。$retryAfter 秒待機します"
                Start-Sleep -Seconds $retryAfter
                # 再試行
                $response = Invoke-RestMethod -Uri $url -Headers $headers -Method Post
                Write-Host "Restarted: $($vm.Name)"
            } else {
                Write-Host "エラー: $($_.Exception.Message)"
            }
        }
    }
    
    # バッチ間で遅延を挿入
    if ($i + $maxConcurrentRequests -lt $vmList.Count) {
        Write-Host "次のバッチまで $delayBetweenBatches 秒待機します"
        Start-Sleep -Seconds $delayBetweenBatches
    }
}
```

## 解決策のまとめ

| 対策方法 | 詳細 | 推奨度 |
|---------|------|--------|
| 並行数制限 | 同時[リクエスト](/glossary/リクエスト/)数を5～10程度に制限する | ★★★★★ |
| リトライロジック | Retry-After[ヘッダー](/glossary/ヘッダー/)に従って自動再試行を実装する | ★★★★★ |
| 指数[バックオフ](/glossary/バックオフ/) | 再試行時に待機時間を段階的に増やす | ★★★★☆ |
| バッチ処理 | リソースをグループ化して段階的に処理する | ★★★★☆ |
| レート監視 | x-ms-ratelimit-*[ヘッダー](/glossary/ヘッダー/)で制限状況を常に確認する | ★★★☆☆ |
| リソース キャッシング | 頻繁にアクセスするリソースを[キャッシュ](/glossary/キャッシュ/)する | ★★★☆☆ |

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*