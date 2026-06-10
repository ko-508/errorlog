---
title: "Amazon SP-APIでHTTP 429 (Too Many Requests)を回避する実践的ガイド"
date: 2026-06-10
lastmod: 2026-06-10
draft: false
description: "Amazon Selling Partner API (SP-API)を利用する際に発生しやすいHTTP 429エラーの原因と、それを回避するための具体的な解決策を解説します。レート制限の管理、認証トークンの扱い、そしてイベント駆動型アーキテクチャへの移行など、実践的なアプローチを紹介します。"
tags: ["Dev.to - AWS"]
---

## エラーの概要

HTTP 429 (Too Many Requests) は、Amazon Selling Partner API (SP-API) に対して、一定時間内に許容されるリクエスト数を超過した場合に発生するエラーです。このエラーは、APIのレート制限に抵触したことを示し、それ以上のリクエストが一時的にブロックされます。SP-APIでは、エンドポイントごとに異なるレート制限が設定されているため、特定の操作が集中すると発生しやすくなります。

## 実際のエラーメッセージ例

SP-APIからのHTTP 429レスポンスは、通常、以下のようなJSON形式で返されます。

```json
{
  "errors": [
    {
      "code": "TooManyRequests",
      "message": "You have exceeded your request limit for this resource. Please try again after some time.",
      "details": ""
    }
  ]
}
```

または、より詳細な情報が含まれる場合もあります。

```json
{
  "errors": [
    {
      "code": "QuotaExceeded",
      "message": "The rate limit for this API has been exceeded. Please wait and retry your request.",
      "details": "Rate limit for getListingsItem is 1 req/s, burst 5 req/s. Current usage: 6 req/s."
    }
  ]
}
```

## よくある原因と解決手順

### 原因1：LWAアクセストークンの期限切れによる再試行

SP-APIの認証には、Login with Amazon (LWA) アクセストークンを使用します。このトークンは有効期限が1時間と短く、期限切れの状態でAPIリクエストを送信すると認証エラーが発生します。多くの場合、アプリケーションは認証エラーを受けてからトークンのリフレッシュを試み、その後に元のリクエストを再試行します。この「リアクティブな」アプローチは、期限切れのトークンで送信された最初のAPIコールがレート制限を消費してしまうため、非効率的です。

**Before（エラーが起きるコード）：**

```javascript
// トークンの有効期限をチェックせずにAPIコールを実行
async function callSpApi(accessToken, data) {
  try {
    const response = await axios.post('https://sellingpartnerapi-na.amazon.com/listings/2021-08-01/items', data, {
      headers: {
        'x-amz-access-token': accessToken,
        // ...その他のヘッダー
      }
    });
    return response.data;
  } catch (error) {
    if (error.response && error.response.status === 403) { // 認証エラー
      console.log("Access token expired, refreshing and retrying...");
      const newAccessToken = await refreshAccessToken(refreshToken); // トークンをリフレッシュ
      return callSpApi(newAccessToken, data); // 再試行
    }
    throw error;
  }
}
```

**After（修正後）：**

```javascript
// トークンの有効期限を事前にチェックし、プロアクティブにリフレッシュ
let cachedAccessToken = null;
let tokenExpiresAt = 0;

async function getValidAccessToken(refreshToken) {
  if (!cachedAccessToken || Date.now() >= tokenExpiresAt) {
    console.log("Refreshing access token proactively...");
    const { data } = await axios.post('https://api.amazon.com/auth/o2/token', {
      grant_type: 'refresh_token',
      refresh_token: refreshToken,
      client_id: process.env.LWA_CLIENT_ID,
      client_secret: process.env.LWA_CLIENT_SECRET,
    });
    cachedAccessToken = data.access_token;
    tokenExpiresAt = Date.now() + (data.expires_in - 60) * 1000; // 60秒早くリフレッシュ
  }
  return cachedAccessToken;
}

async function callSpApi(refreshToken, data) {
  const accessToken = await getValidAccessToken(refreshToken);
  const response = await axios.post('https://sellingpartnerapi-na.amazon.com/listings/2021-08-01/items', data, {
    headers: {
      'x-amz-access-token': accessToken,
      // ...その他のヘッダー
    }
  });
  return response.data;
}
```

### 原因2：エンドポイントごとのレート制限を考慮しない一律なAPIコール

SP-APIのレート制限は、API全体で一律に適用されるわけではなく、エンドポイントごとに個別のバーストレートとリストアレートが設定されています。例えば、`getListingsItem`と`getCompetitivePricing`では全く異なる制限があります。これを理解せず、すべてのAPIコールを同じペースで実行すると、特定の制限の厳しいエンドポイントで簡単に429エラーが発生します。

**Before（エラーが起きるコード）：**

```javascript
// すべてのAPIコールに対して一律の遅延を適用
async function processAllSkus(skus) {
  for (const sku of skus) {
    await spApi.getListingsItem({ sku: sku.seller_sku, marketplaceIds: ['<your-marketplace-id>'] });
    await new Promise(resolve => setTimeout(resolve, 500)); // 500ms待機
    await spApi.getCompetitivePricing({ asins: [sku.asin], marketplaceId: '<your-marketplace-id>' });
    await new Promise(resolve => setTimeout(resolve, 500)); // 500ms待機
  }
}
```

**After（修正後）：**

```javascript
// エンドポイントごとに独立したトークンバケットを実装
class TokenBucket {
  constructor({ burst, restoreRate }) {
    this.tokens = burst;
    this.burst = burst;
    this.restoreRate = restoreRate; // tokens per second
    this.lastRefill = Date.now();
  }

  _refill() {
    const now = Date.now();
    const elapsed = (now - this.lastRefill) / 1000;
    this.tokens = Math.min(this.burst, this.tokens + elapsed * this.restoreRate);
    this.lastRefill = now;
  }

  async consume() {
    while (true) {
      this._refill();
      if (this.tokens >= 1) {
        this.tokens -= 1;
        return true;
      }
      // トークンがない場合は待機
      await new Promise(resolve => setTimeout(resolve, 100)); // 100ms待機して再チェック
    }
  }
}

const buckets = {
  getListingsItem: new TokenBucket({ burst: 5, restoreRate: 1 }), // 例: 5バースト, 1 req/s
  getCompetitivePricing: new TokenBucket({ burst: 10, restoreRate: 0.1 }), // 例: 10バースト, 0.1 req/s
  // ...他のエンドポイントのバケット
};

async function callSpApiWithRateLimit(endpointName, apiCallFunction, ...args) {
  await buckets[endpointName].consume();
  return apiCallFunction(...args);
}

async function processAllSkus(skus) {
  for (const sku of skus) {
    await callSpApiWithRateLimit('getListingsItem', spApi.getListingsItem, { sku: sku.seller_sku, marketplaceIds: ['<your-marketplace-id>'] });
    await callSpApiWithRateLimit('getCompetitivePricing', spApi.getCompetitivePricing, { asins: [sku.asin], marketplaceId: '<your-marketplace-id>' });
  }
}
```

### 原因3：カタログ情報のポーリングによる過剰なAPIコール

在庫や価格の変更を検知するために、定期的に`Catalog Items API`などの情報をポーリングするアーキテクチャは、SKU数が多い場合に大量のAPIコールを発生させ、すぐにレート制限に達してしまいます。特に数万SKUを扱うようなシステムでは、このアプローチは持続不可能です。

**Before（エラーが起きるコード）：**

```javascript
// Cronジョブで定期的に全SKUの情報をポーリング
// cron.js (例)
const spApi = require('./spApiClient');
const db = require('./database');

async function syncInventory() {
  const allSkus = await db.getAllSkus(); // 全SKUを取得
  for (const sku of allSkus) {
    // getListingsItemはレート制限が厳しい
    const listing = await spApi.getListingsItem({ sku: sku.seller_sku, marketplaceIds: ['<your-marketplace-id>'] });
    // ...在庫情報を更新
    await new Promise(resolve => setTimeout(resolve, 1000)); // レート制限対策の遅延
  }
  console.log("Inventory sync complete.");
}

// 15分ごとに実行されるCronジョブ
setInterval(syncInventory, 15 * 60 * 1000);
```

**After（修正後）：**

```javascript
// Notifications APIとSQSを利用したイベント駆動型アーキテクチャへの移行
// 1. SQSキューの作成とSP-APIへの登録 (初回のみ)
// spApiSetup.js (例)
const SellingPartnerAPI = require('amazon-sp-api');
const spApiClient = new SellingPartnerAPI({ /* config */ });

async function setupNotifications() {
  // SQSキューのARNを環境変数から取得
  const sqsArn = process.env.SQS_ARN; 

  // SQS宛先をSP-APIに作成
  const destinationResponse = await spApiClient.notifications.createDestination({
    name: 'inventory-updates-queue',
    resourceSpecification: {
      sqs: { arn: sqsArn }
    }
  });
  const destinationId = destinationResponse.payload.destinationId;
  console.log(`Destination created: ${destinationId}`);

  // 在庫更新イベントにサブスクライブ
  await spApiClient.notifications.createSubscription({
    notificationType: 'ITEM_INVENTORY_UPDATE',
    destinationId: destinationId,
    payloadVersion: '1.0',
  });
  console.log("Subscribed to ITEM_INVENTORY_UPDATE notifications.");
}

// 2. Lambda関数でSQSキューからのイベントを処理
// lambda_handler.js (例)
const db = require('./database');

exports.handler = async (event) => {
  console.log("Received SQS event:", JSON.stringify(event, null, 2));
  const updates = event.Records.map(r => JSON.parse(r.body));

  for (const update of updates) {
    // 通知ペイロードから必要な情報を抽出
    const { sellerSku, marketplaceId, quantity } = update.payload; // payload構造は通知タイプによる

    console.log(`Processing SKU: ${sellerSku}, Quantity: ${quantity}`);
    await db.query(
      `UPDATE inventory SET quantity = $1, updated_at = NOW()
       WHERE seller_sku = $2 AND marketplace_id = $3`,
      [quantity, sellerSku, marketplaceId]
    );
  }
  console.log("Batch processing complete.");
};
```

## ツール固有の注意点

Amazon SP-APIは、他のAWSサービスとは異なる認証フロー（LWA認証）を採用しています。IAMロールと署名V4ヘッダーも必要ですが、LWAアクセストークンは`x-amz-access-token`ヘッダーで別途送信する必要があります。この二重の認証メカニズムは、AWSの一般的な認証パターンに慣れている開発者にとって混乱の元となりがちです。

また、SP-APIのサンドボックス環境は、本番環境の挙動を完全に再現するものではありません。特に、レート制限の挙動、Webhookの配信、およびエッジケースのデータ処理に関しては、サンドボックスと本番環境で大きな違いがあることがあります。認証フローやWebhookのテストは、必ず本番のテストセラーアカウントで行うことを強く推奨します。サンドボックスは、APIリクエストとレスポンスの基本的なシェイプを確認する用途に限定すべきです。

## それでも解決しない場合

上記の手順を試してもHTTP 429エラーが解決しない場合は、以下の点を確認してください。

1.  **詳細なログの確認:**
    *   ご自身のアプリケーションのログで、どのAPIエンドポイントが、どのくらいの頻度で呼び出されているかを確認してください。特に、レート制限に抵触していると疑われるエンドポイントの呼び出しパターンを分析します。
    *   SP-APIのレスポンスボディに、レート制限に関する具体的な情報（例: `Current usage: 6 req/s`）が含まれていないか確認します。
2.  **SP-APIの公式ドキュメント:**
    *   利用しているAPIエンドポイントの[公式ドキュメント](https://developer-docs.amazon.com/sp-api/docs/sp-api-reference)で、最新のレート制限情報を確認してください。レート制限は予告なく変更される可能性があります。
    *   特に、[Notifications API](https://developer-docs.amazon.com/sp-api/docs/notifications-api-v1-reference)のセクションを熟読し、イベント駆動型への移行が正しく実装されているか再確認します。
3.  **デバッグコマンド/ツール:**
    *   APIコールの前に、トークンバケットの実装が正しく機能しているか、デバッグログを追加して確認します。`tokens`の残量や`lastRefill`のタイムスタンプを追跡することで、バケットが枯渇しているタイミングを特定できます。
    *   ネットワークプロキシやAPIゲートウェイを使用している場合、それらがリクエストをバッファリングしたり、追加のレート制限を適用したりしていないか確認します。
4.  **Amazon Seller Centralのアプリケーション設定:**
    *   Seller Centralで登録したアプリケーションの設定が正しいか、特にLWAクライアントIDとクライアントシークレットがアプリケーションに正しく設定されているか確認します。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*