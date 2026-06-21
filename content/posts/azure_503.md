---
title: "Azure の 503 エラー：原因と解決策"
date: 2026-06-03
description: "Azureサービスが一時的に利用できない。Azure 503 エラーの原因と解決策を解説します。"
tags: ["Azure"]
errorCode: "503"
service: "Azure"
error_type: "503"
components: ["App Service", "AKS", "Blob Storage", "Auto Scale"]
related_services: ["Azure Portal", "Azure CLI"]
---
## エラーの概要

Azure 503 [エラー](/glossary/エラー/)は「Service Unavailable」を意味し、Azureサービスが一時的に利用できない状態を示します。[リクエスト](/glossary/リクエスト/)が[サーバー](/glossary/サーバー/)に到達しても、システムの過負荷、メンテナンス、[インフラ](/glossary/インフラ/)障害などによって[レスポンス](/glossary/レスポンス/)を返すことができません。この[エラー](/glossary/エラー/)は一時的な場合が多いため、[リトライ](/glossary/リトライ/)戦略を実装することが重要です。

## 実際のエラーメッセージ例

**Azure Portal の [HTTP](/glossary/http/) [レスポンス](/glossary/レスポンス/)：**

```json
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
Retry-After: 60

{
  "error": {
    "code": "ServiceUnavailable",
    "message": "The service is currently unavailable. Please try again later.",
    "target": "App Service"
  }
}
```

**Azure [CLI](/glossary/cli/) からの[エラー](/glossary/エラー/)出力：**

```bash
ERROR: (BadRequest) Service Unavailable: The service is temporarily unavailable. 
Please retry the request after some time. RequestId: abc123def456
```

## よくある原因と解決手順

### 原因1：Azureリージョンで障害が発生している

Azure のデータセンター障害やメンテナンス作業により、特定のリージョン全体がサービス停止している場合があります。この場合、アプリケーション側での修正では解決できず、Azure のサービス復旧を待つか、別リージョンへの切り替えが必要です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
# 単一のリージョンにのみデプロイされている
from azure.storage.blob import BlobServiceClient

account_url = "https://mystorageaccount.blob.core.windows.net"
blob_service_client = BlobServiceClient(account_url=account_url)

try:
    container_client = blob_service_client.get_container_client("mycontainer")
    blobs = container_client.list_blobs()
except Exception as e:
    print(f"Error: {e}")
    # リージョン障害時は対応策がない
```

**After（修正後）：**

```python
# 複数リージョンのストレージアカウントを用意し、フェイルオーバー対応
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ServiceRequestError

# プライマリとセカンダリリージョンのアカウントURL
primary_url = "https://mystorageaccount-primary.blob.core.windows.net"
secondary_url = "https://mystorageaccount-secondary.blob.core.windows.net"

def get_blob_client(primary_url, secondary_url):
    try:
        return BlobServiceClient(account_url=primary_url)
    except ServiceRequestError:
        print("Primary region unavailable, switching to secondary region")
        return BlobServiceClient(account_url=secondary_url)

blob_service_client = get_blob_client(primary_url, secondary_url)
container_client = blob_service_client.get_container_client("mycontainer")
blobs = container_client.list_blobs()
```

### 原因2：アプリケーションのスケールアウトが間に合わずリクエストを処理できない

トラフィック急増時に、App Service や AKS の[インスタンス](/glossary/インスタンス/)数が自動スケーリングの速度に追いつかず、処理可能な[リクエスト](/glossary/リクエスト/)数を超える場合があります。Auto Scaling ルールが不適切に設定されていると、スケールアウトが遅延し、[リクエスト](/glossary/リクエスト/)が処理されずに 503 を返します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
# App Service の Auto Scale ルール（設定が遅い）
apiVersion: microsoft.insights/autoscalesettings
metadata:
  name: myapp-autoscale
spec:
  profiles:
  - name: default
    capacity:
      minimum: "1"
      maximum: "5"
      default: "1"
    rules:
    - metricTrigger:
        metricName: CpuPercentage
        metricResourceUri: /subscriptions/.../myAppService
        timeGrain: PT5M  # 5分ごとに評価
        statistic: Average
        timeWindow: PT10M  # 10分間のデータを収集
        timeAggregation: Average
        operator: GreaterThan
        threshold: 80
      scaleAction:
        direction: Increase
        type: ChangeCount
        value: "1"
        cooldown: PT10M  # 10分間のクールダウン
```

**After（修正後）：**

```yaml
# 改善された Auto Scale ルール
apiVersion: microsoft.insights/autoscalesettings
metadata:
  name: myapp-autoscale
spec:
  profiles:
  - name: default
    capacity:
      minimum: "2"
      maximum: "20"
      default: "2"
    rules:
    # スケールアップルール：CPU 60% を超えたら即座に対応
    - metricTrigger:
        metricName: CpuPercentage
        metricResourceUri: /subscriptions/.../myAppService
        timeGrain: PT1M  # 1分ごとに評価
        statistic: Average
        timeWindow: PT3M  # 3分間のデータを収集
        timeAggregation: Average
        operator: GreaterThan
        threshold: 60
      scaleAction:
        direction: Increase
        type: ChangeCount
        value: "3"  # 一度に3インスタンス追加
        cooldown: PT3M  # 3分間のクールダウン
    # スケールダウンルール：CPU 30% 以下なら削減
    - metricTrigger:
        metricName: CpuPercentage
        metricResourceUri: /subscriptions/.../myAppService
        timeGrain: PT5M
        statistic: Average
        timeWindow: PT10M
        timeAggregation: Average
        operator: LessThan
        threshold: 30
      scaleAction:
        direction: Decrease
        type: ChangeCount
        value: "1"
        cooldown: PT5M
```

### 原因3：Application Gateway やロードバランサーの設定不足

バックエンドプールの正常性プローブが失敗している、またはバックエンドインスタンスの[ポート](/glossary/ポート/)設定が間違っている場合、Application Gateway が[リクエスト](/glossary/リクエスト/)をルーティングできず 503 を返します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```json
{
  "id": "/subscriptions/<subscription>/resourceGroups/myRG/providers/Microsoft.Network/applicationGateways/myAppGateway",
  "properties": {
    "backendHttpSettingsCollection": [
      {
        "name": "myBackendSettings",
        "port": 8080,
        "protocol": "Http",
        "cookieBasedAffinity": "Disabled",
        "probes": [
          {
            "name": "myProbe",
            "protocol": "Http",
            "host": "localhost",
            "path": "/status",
            "interval": 30,
            "timeout": 5,
            "unhealthyThreshold": 3
          }
        ]
      }
    ],
    "backendAddressPools": [
      {
        "name": "myBackendPool",
        "backendAddresses": [
          {
            "ipAddress": "10.0.1.10"
          }
        ]
      }
    ]
  }
}
```

**After（修正後）：**

```json
{
  "id": "/subscriptions/<subscription>/resourceGroups/myRG/providers/Microsoft.Network/applicationGateways/myAppGateway",
  "properties": {
    "backendHttpSettingsCollection": [
      {
        "name": "myBackendSettings",
        "port": 80,
        "protocol": "Http",
        "cookieBasedAffinity": "Disabled",
        "probes": [
          {
            "name": "myProbe",
            "protocol": "Http",
            "host": "10.0.1.10",
            "path": "/health",
            "interval": 30,
            "timeout": 10,
            "unhealthyThreshold": 2,
            "pickHostNameFromBackendHttpSettings": false,
            "match": {
              "statusCodes": [
                "200-299"
              ]
            }
          }
        ]
      }
    ],
    "backendAddressPools": [
      {
        "name": "myBackendPool",
        "backendAddresses": [
          {
            "ipAddress": "10.0.1.10",
            "fqdn": "backend-vm-01.example.com"
          }
        ]
      }
    ]
  }
}
```

## ツール固有の注意点

### Azure Portal でのサービス状態確認

`status.azure.com` にアクセスして、リージョン全体の障害情報を確認することが最初のステップです。特定のサービス（App Service、[SQL](/glossary/sql/) Database、Storage など）のステータスが「Degraded」または「Service Interruption」と表示されている場合、その解決を待つ必要があります。

### App Service のインスタンス数と消費プランの検討

Free プランや Shared プランでは Auto Scaling が利用できないため、ピーク時のトラフィック対応ができません。本番環境では最低でも Standard プラン以上を使用し、事前に負荷[テスト](/glossary/テスト/)を実施して[インスタンス](/glossary/インスタンス/)数を決定してください。

### リトライポリシーの実装

クライアント側では、503 [エラー](/glossary/エラー/)を受け取った場合の指数バックオフリトライポリシーを実装することが重要です。

**リトライポリシーの実装例：**

```csharp
// Azure SDK のリトライポリシー設定
var retryPolicy = new RetryPolicy(
    maxRetries: 3,
    delay: TimeSpan.FromSeconds(2),
    maxDelay: TimeSpan.FromSeconds(60)
);

var clientOptions = new BlobClientOptions
{
    Retry = retryPolicy
};

var blobClient = new BlobClient(
    new Uri("https://mystorageaccount.blob.core.windows.net/mycontainer/myblob"),
    new DefaultAzureCredential(),
    clientOptions
);
```

## それでも解決しない場合

### 確認すべきログとメトリクス

Azure Portal の「監視」セクションで、リソースの[メトリクス](/glossary/メトリクス/)を確認してください。特に以下の指標をチェックします：

- **CPU 使用率**：90% 以上が継続している場合、スケーリング設定を見直してください
- **メモリ使用率**：予期しないメモリリークがないか確認します
- **[ネットワーク](/glossary/ネットワーク/)入出力**：異常なトラフィック増加がないか確認します

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*