---
title: "DynamoDBからAurora PostgreSQL Serverless v2への移行：広告運用監視ワークロードにおける選択の理由"
date: 2026-06-12
lastmod: 2026-06-12
draft: false
description: "広告運用監視ワークロードにおいて、DynamoDBからAurora PostgreSQL Serverless v2へ移行した事例を解説します。複雑なクエリ、時系列分析、柔軟なデータモデルが求められる場合に、リレーショナルデータベースがどのように優位性を持つか、具体的なコード例を交えて説明します。"
tags: ["Dev.to - AWS"]
trend_incident: true
---

## エラーの概要

この記事では、特定のHTTPエラーコードを直接扱うわけではありませんが、データベース選定の誤りがアプリケーションのパフォーマンス低下や開発効率の悪化につながる「設計上のエラー」として捉えることができます。特に、NoSQLデータベースであるDynamoDBを、リレーショナルな特性が強く求められるワークロードに適用しようとした際に発生する、開発の複雑性や非効率性が本質的なエラーです。これは、特定のクエリが期待通りに機能しない、あるいは極めて複雑な実装を要するといった形で顕在化します。

## 実際のエラーメッセージ例

直接的なエラーメッセージは発生しませんが、DynamoDBで複雑なクエリを実行しようとした際に、アプリケーションコードが肥大化したり、パフォーマンスが低下したりする状況がこれに相当します。例えば、以下のような擬似的なエラー状況が考えられます。

**アプリケーションログ（DynamoDBで複雑な集計を試みた場合）:**

```
[ERROR] 2026-06-12T10:00:00.123Z <request-id> Lambda function timed out after 30000 ms.
[INFO] 2026-06-12T10:00:00.120Z <request-id> DynamoDB scan operation completed with 100000 items, processing time: 28500 ms.
[INFO] 2026-06-12T10:00:00.121Z <request-id> Starting in-memory aggregation for time-series data...
```

**開発時のコンソール出力（DynamoDBのGSI設計の複雑性）:**

```
Error: Failed to create GSI 'my-gsi-index'. The projection type 'ALL' is not suitable for this access pattern. Consider 'KEYS_ONLY' or 'INCLUDE' with specific attributes.
```

## よくある原因と解決手順

### 原因1：複数エンティティにまたがる結合（JOIN）が必要な場合

DynamoDBは単一アイテムアクセスパターンに最適化されており、複数テーブル（コレクション）を結合する機能はネイティブには提供されていません。広告運用監視のようなワークロードでは、アカウント、キャンペーン、広告セット、広告、時間ごとのインサイト、アラートといった複数のエンティティを関連付けて分析する必要があります。DynamoDBでこれを実現しようとすると、アプリケーション側で複数のクエリを発行し、結果を結合するロジックを実装する必要があり、複雑性が増大します。

**Before（エラーが起きるコード）：**

```javascript
// DynamoDBで複数エンティティを結合する擬似コード
async function getAdSetInsightsWithCampaigns(accountId, adSetId) {
  // 1. ad_setの情報を取得
  const adSet = await dynamoDb.get({
    TableName: 'ad_sets',
    Key: { id: adSetId }
  }).promise();

  // 2. ad_setに関連するキャンペーン情報を取得 (別途GSIが必要か、または全スキャン)
  const campaign = await dynamoDb.get({
    TableName: 'campaigns',
    Key: { id: adSet.campaignId } // campaignIdがad_setに格納されている前提
  }).promise();

  // 3. insights_hourlyの情報を取得 (adSetIdでフィルタリング)
  const insights = await dynamoDb.query({
    TableName: 'insights_hourly',
    IndexName: 'adSetId-windowStart-index', // GSIが必要
    KeyConditionExpression: 'adSetId = :adSetId',
    ExpressionAttributeValues: { ':adSetId': adSetId }
  }).promise();

  // アプリケーション側で結合ロジックを実装
  return {
    adSet: adSet.Item,
    campaign: campaign.Item,
    insights: insights.Items
  };
}
```

**After（修正後）：**

```sql
-- Aurora PostgreSQL Serverless v2で複数エンティティを結合するSQL
SELECT
  a.name AS account_name,
  c.name AS campaign_name,
  ads.name AS ad_set_name,
  ih.window_start,
  ih.spend,
  ih.impressions,
  ih.clicks
FROM accounts a
JOIN campaigns c ON a.id = c.account_id
JOIN ad_sets ads ON c.id = ads.campaign_id
JOIN insights_hourly ih ON ads.id = ih.entity_meta_id AND ih.level = 'ad_set'
WHERE a.id = $1 AND ads.id = $2
ORDER BY ih.window_start DESC;
```

### 原因2：時系列データのウィンドウ関数（集計）が必要な場合

広告運用監視では、過去N期間の平均値やトレンドと比較して現在のパフォーマンスを評価する「時系列ウィンドウ関数」が頻繁に利用されます。例えば、過去7日間の平均フリークエンシーを算出し、現在のフリークエンシーと比較するといった分析です。DynamoDBでこのような処理を行うには、アプリケーション側でデータを取得し、手動で集計ロジックを実装するか、複雑なGSI設計とLambdaステップを組み合わせる必要があります。これは開発コストと実行コストの両面で非効率です。

**Before（エラーが起きるコード）：**

```javascript
// DynamoDBで時系列ウィンドウ関数をシミュレートする擬似コード
async function calculateRollingAverage(entityMetaId, windowSizeHours) {
  const now = new Date();
  const sevenDaysAgo = new Date(now.getTime() - (7 * 24 * 60 * 60 * 1000));

  // 過去7日間のデータを取得 (GSIとQueryが必要)
  const insights = await dynamoDb.query({
    TableName: 'insights_hourly',
    IndexName: 'entityMetaId-windowStart-index',
    KeyConditionExpression: 'entityMetaId = :entityId AND windowStart BETWEEN :start AND :end',
    ExpressionAttributeValues: {
      ':entityId': entityMetaId,
      ':start': sevenDaysAgo.toISOString(),
      ':end': now.toISOString()
    },
    ScanIndexForward: true // 時系列順にソート
  }).promise();

  // アプリケーション側でローリング平均を計算
  const frequencies = insights.Items.map(item => item.frequency);
  let sum = 0;
  let count = 0;
  const rollingAverages = [];

  for (let i = 0; i < frequencies.length; i++) {
    sum += frequencies[i];
    count++;
    if (i >= windowSizeHours) {
      sum -= frequencies[i - windowSizeHours];
      count--;
    }
    rollingAverages.push(sum / count);
  }
  return rollingAverages;
}
```

**After（修正後）：**

```sql
-- Aurora PostgreSQL Serverless v2で時系列ウィンドウ関数を使用するSQL
SELECT
  entity_meta_id,
  window_start,
  frequency,
  AVG(frequency) OVER (
    PARTITION BY entity_meta_id
    ORDER BY window_start
    ROWS BETWEEN 336 PRECEDING AND 1 PRECEDING -- 14日 × 24時間 = 336行
  ) AS freq_7d_baseline,
  AVG(ctr) OVER (
    PARTITION BY entity_meta_id
    ORDER BY window_start
    ROWS BETWEEN 336 PRECEDING AND 1 PRECEDING
  ) AS ctr_7d_baseline
FROM insights_hourly
WHERE level = 'ad_set'
  AND account_meta_id = $1
  AND window_start >= NOW() - INTERVAL '7 days'
ORDER BY entity_meta_id, window_start;
```

### 原因3：進化するクエリパターンと柔軟なデータモデルが必要な場合

広告運用監視ツールは、新しいアラートルールやダッシュボードの要件に応じて、クエリパターンが頻繁に変化する可能性があります。DynamoDBは事前にアクセスパターンを計画し、それに基づいてプライマリキーやGSIを設計する必要があります。クエリパターンが進化するたびにGSIの再設計やアプリケーションコードの変更が必要となり、開発の柔軟性が損なわれます。Aurora PostgreSQLのようなリレーショナルデータベースであれば、アドホックなSQLクエリで柔軟に対応できます。

**Before（エラーが起きるコード）：**

```javascript
// DynamoDBで新しいクエリパターンに対応する擬似コード
// 新しいアラートルール「CTRが過去3日間の平均よりX%低いキャンペーン」を追加する場合

// 既存のGSIでは対応できないため、新しいGSIの追加を検討
// GSI: campaignId-windowStart-index (CTRもProjectionに含める)
// または、アプリケーション側で全スキャン後にフィルタリング・集計

// 新しいGSIの定義（CloudFormationやCDKで定義）
// Resources:
//   InsightsHourlyTable:
//     Type: AWS::DynamoDB::Table
//     Properties:
//       TableName: insights_hourly
//       AttributeDefinitions:
//         - AttributeName: id
//           AttributeType: S
//         - AttributeName: campaignId
//           AttributeType: S
//         - AttributeName: windowStart
//           AttributeType: S
//       KeySchema:
//         - AttributeName: id
//           KeyType: HASH
//       GlobalSecondaryIndexes:
//         - IndexName: campaignId-windowStart-index
//           KeySchema:
//             - AttributeName: campaignId
//               KeyType: HASH
//             - AttributeName: windowStart
//               KeyType: RANGE
//           Projection:
//             ProjectionType: INCLUDE
//             NonKeyAttributes:
//               - ctr
//               - impressions
//           ProvisionedThroughput:
//             ReadCapacityUnits: 5
//             WriteCapacityUnits: 5
```

**After（修正後）：**

```sql
-- Aurora PostgreSQL Serverless v2でアドホックなSQLクエリを使用
-- 新しいアラートルール「CTRが過去3日間の平均よりX%低いキャンペーン」に対応
SELECT
  entity_meta_id,
  window_start,
  ctr,
  AVG(ctr) OVER (
    PARTITION BY entity_meta_id
    ORDER BY window_start
    ROWS BETWEEN 72 PRECEDING AND 1 PRECEDING -- 3日 × 24時間 = 72行
  ) AS ctr_3d_baseline
FROM insights_hourly
WHERE level = 'campaign'
  AND account_meta_id = $1
  AND window_start >= NOW() - INTERVAL '3 days'
ORDER BY entity_meta_id, window_start;

-- 必要に応じてインデックスを追加するだけで対応可能
-- CREATE INDEX idx_insights_hourly_level_account_window ON insights_hourly (level, account_meta_id, window_start);
```

## ツール固有の注意点

Aurora PostgreSQL Serverless v2は、その名の通りサーバーレスで、ワークロードに応じて自動的にキャパシティをスケーリングします。これにより、アイドル状態のコストを抑えつつ、急なトラフィック増加にも対応できます。特に、15分ごとのポーリングのようなバースト的なワークロードには最適です。

ただし、Vercel Fluid ComputeのようなFaaS環境でAurora PostgreSQLを使用する場合、コネクションプーリングの管理が重要になります。PostgreSQLプロトコルはTCP/TLSハンドシェイクを伴うため、関数呼び出しごとに新しいコネクションを確立すると、データベースのコネクション制限にすぐに達してしまいます。

この問題を解決するには、`postgres-js`のようなライブラリを使用し、以下の設定を適用することが推奨されます。

```javascript
import postgres from 'postgres';

const sql = postgres(process.env.DATABASE_URL!, {
  prepare: false,     // Vercel Fluid Computeはインスタンスを再利用するため、ステートフルなプリペアドステートメントは避ける
  max: 1,             // ウォームなインスタンスごとに1つのコネクションを維持し、再利用する
});
```

`prepare: false`は、Vercel Fluid Computeが関数インスタンスを再利用する際に、プリペアドステートメントの状態がリークするのを防ぎます。`max: 1`は、各関数インスタンスがデータベースへのウォームなコネクションを1つだけ保持し、そのインスタンスへの後続のリクエストで再利用されるようにします。これにより、RDS Proxyや外部のpgBouncerなしで、効率的なコネクションプーリングを実現できます。

## それでも解決しない場合

上記の手順を試しても問題が解決しない場合は、以下の点を確認してください。

1.  **Aurora PostgreSQLのログの確認:**
    *   AWSマネジメントコンソールからAuroraクラスターを選択し、「ログとイベント」タブでエラーログやスロークエリログを確認します。
    *   特に、実行に時間がかかっているクエリや、リソース不足を示す警告がないかを確認します。
2.  **Vercelのデプロイログと関数ログの確認:**
    *   Vercelダッシュボードでデプロイログと各関数の実行ログを確認し、データベース接続エラーやタイムアウトが発生していないかを確認します。
3.  **データベース接続文字列の確認:**
    *   `DATABASE_URL`環境変数が正しく設定されており、Aurora PostgreSQLクラスターにアクセスできることを確認します。セキュリティグループやIAMロールの設定も再確認してください。
4.  **SQLクエリのEXPLAIN分析:**
    *   実行に時間がかかるSQLクエリに対して`EXPLAIN ANALYZE`コマンドを実行し、クエリプランを分析します。これにより、インデックスが適切に使用されているか、非効率なスキャンが発生していないかなどを特定できます。
5.  **公式ドキュメントの参照:**
    *   AWS Aurora PostgreSQL Serverless v2の公式ドキュメント: [https://aws.amazon.com/jp/rds/aurora/serverless/](https://aws.amazon.com/jp/rds/aurora/serverless/)
    *   Vercel Fluid Computeの公式ドキュメント: [https://vercel.com/docs/functions/runtimes/node-js#fluid-compute](https://vercel.com/docs/functions/runtimes/node-js#fluid-compute)
    *   `postgres-js`ライブラリのドキュメント: [https://github.com/porsager/postgres](https://github.com/porsager/postgres)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*