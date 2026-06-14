---
title: "Vercel の 504 エラー：原因と解決策"
date: 2026-06-08
description: "Vercelのサーバーレス関数の実行がタイムアウトした。Vercel 504 エラーの原因と解決策を解説します。"
tags: ["Vercel"]
errorCode: "504"
service: "Vercel"
error_type: "504"
components: []
related_services: ["API", "Dashboard"]
trend_incident: true
lastmod: 2026-06-14
---
## エラーの概要

Vercel の 504 [エラー](/glossary/エラー/)は、[デプロイ](/glossary/デプロイ/)された[サーバーレス](/glossary/サーバーレス/)関数の実行時間が設定された[タイムアウト](/glossary/タイムアウト/)制限を超えたときに発生するゲートウェイタイムアウトエラーです。Hobby プランではデフォルト 300 秒（5 分）で、Pro プラン以上ではデフォルト 300 秒、Fluid Compute を有効にすると最大 800 秒（約 13 分）まで延長可能です。[API](/glossary/api/) 呼び出し、データベースクエリ、外部 [API](/glossary/api/) 連携など、応答待ちが長引く処理で頻繁に発生します。

## 実際のエラーメッセージ例

**Vercel [ダッシュボード](/glossary/ダッシュボード/)表示：**

```
504
Gateway Timeout
```

**関数[ログ](/glossary/ログ/)（Vercel Dashboard [ロール](/glossary/ロール/)）：**

```json
{
  "errorCode": "FUNCTION_INVOCATION_TIMEOUT",
  "message": "The function exceeded the timeout duration",
  "functionName": "api/users",
  "executionDurationMs": 300000,
  "maxDurationMs": 300000,
  "timestamp": "2024-01-15T10:30:45.123Z"
}
```

**cURL または [HTTP](/glossary/http/) クライアントでの応答：**

```
HTTP/1.1 504 Gateway Timeout
Content-Type: application/json

{
  "error": {
    "code": "INTERNAL_FUNCTION_TIMEOUT",
    "message": "Function timed out after 300000ms"
  }
}
```

## よくある原因と解決手順

### 原因 1: 外部 API への応答待ちが長い

外部サービス（[データベース](/glossary/データベース/)、第三者 [API](/glossary/api/) など）の[レスポンス](/glossary/レスポンス/)が遅れていることが最も一般的な原因です。[ネットワーク](/glossary/ネットワーク/)遅延やサービスの過負荷により、[タイムアウト](/glossary/タイムアウト/)に達する前に結果が返されません。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
// pages/api/fetch-user.js
export default async function handler(req, res) {
  const response = await fetch('https://external-api.example.com/user', {
    method: 'GET'
  });
  const data = await response.json();
  res.status(200).json(data);
}
```

**After（修正後）：**

```javascript
// pages/api/fetch-user.js
export default async function handler(req, res) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 8000); // 8秒でタイムアウト

  try {
    const response = await fetch('https://external-api.example.com/user', {
      method: 'GET',
      signal: controller.signal
    });
    clearTimeout(timeoutId);
    const data = await response.json();
    res.status(200).json(data);
  } catch (error) {
    if (error.name === 'AbortError') {
      res.status(504).json({ error: 'External service timeout' });
    } else {
      res.status(500).json({ error: 'Internal server error' });
    }
  }
}
```

### 原因 2: タイムアウト制限が処理の実行時間に不適切

複雑なデータ処理やループ処理が実行時間内に完了していない場合があります。大量データの変換やファイル処理など、CPU 集約的なタスクが関数の実行時間を超過させます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
// pages/api/process-data.js
export default async function handler(req, res) {
  const items = req.body.items; // 100,000 件以上のアイテム
  
  const processed = items.map(item => {
    // 複雑な計算処理
    return expensiveCalculation(item);
  });
  
  res.status(200).json({ processed });
}
```

**After（修正後）：**

```javascript
// vercel.json - タイムアウト設定
{
  "functions": {
    "pages/api/process-data.js": {
      "maxDuration": 120
    }
  }
}

// pages/api/process-data.js
export default async function handler(req, res) {
  const items = req.body.items;
  const BATCH_SIZE = 100;
  const processed = [];
  
  for (let i = 0; i < items.length; i += BATCH_SIZE) {
    const batch = items.slice(i, i + BATCH_SIZE);
    const batchProcessed = batch.map(item => expensiveCalculation(item));
    processed.push(...batchProcessed);
  }
  
  res.status(200).json({ processed });
}
```

### 原因 3: データベースクエリの最適化不足

未[インデックス](/glossary/インデックス/)化されたカラムへの[クエリ](/glossary/クエリ/)、複数[テーブル](/glossary/テーブル/)の結合、大量行の全スキャンなど、非効率なデータベースアクセスが[タイムアウト](/glossary/タイムアウト/)を引き起こします。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
// pages/api/get-orders.js
import prisma from '@/lib/prisma';

export default async function handler(req, res) {
  // インデックスなしのカラムで全スキャン + 複数ユーザーの注文を取得
  const orders = await prisma.order.findMany({
    where: {
      status: req.query.status, // status カラムにインデックスなし
      user: {
        region: req.query.region // JOIN + 条件が複雑
      }
    }
  });
  
  res.status(200).json(orders);
}
```

**After（修正後）：**

```javascript
// pages/api/get-orders.js
import prisma from '@/lib/prisma';

export default async function handler(req, res) {
  // インデックス化されたカラムを活用、LIMIT で最大件数制限
  const orders = await prisma.order.findMany({
    where: {
      status: req.query.status,
      userId: req.query.userId // インデックス化されたフィールド
    },
    select: {
      id: true,
      amount: true,
      createdAt: true
      // 不要なカラムは除外
    },
    take: 100, // 結果を100件に制限
    orderBy: {
      createdAt: 'desc'
    }
  });
  
  res.status(200).json(orders);
}
```

## Vercel 固有の注意点

**Hobby プランの[タイムアウト](/glossary/タイムアウト/)制限：**
Hobby プランは最大 300 秒に固定されており、`maxDuration` で延長することはできません。長時間処理が必要な場合は Pro プラン以上へのアップグレード、もしくは処理を分割する（キューイング、バッチ処理）ことが必須です。

**Fluid Compute の有効化：**
Pro プラン以上で Fluid Compute を使用している場合、800 秒までの延長が可能です。[ダッシュボード](/glossary/ダッシュボード/)の Project Settings から確認し、`vercel.json` で関数ごとに `maxDuration` を設定してください。

```json
{
  "functions": {
    "pages/api/heavy-processing.js": {
      "maxDuration": 600
    },
    "pages/api/quick-api.js": {
      "maxDuration": 30
    }
  }
}
```

**Edge Functions の活用：**
Vercel の Edge Functions は地理的に分散されており、冷起動（[デプロイ](/glossary/デプロイ/)後の初回実行遅延）が少なく、外部 [API](/glossary/api/) への応答遅延が減少することがあります。軽量な処理で頻繁な[タイムアウト](/glossary/タイムアウト/)が発生する場合、Edge Functions への移行を検討してください。

**Environment Variables の確認：**
リトライロジックや[キャッシュ](/glossary/キャッシュ/)の設定が[環境変数](/glossary/環境変数/)に依存している場合、本番環境と開発環境で値が異なると[タイムアウト](/glossary/タイムアウト/)発生パターンが変わります。Vercel [ダッシュボード](/glossary/ダッシュボード/)の Settings > Environment Variables で本番値を確認してください。

## それでも解決しない場合

**関数[ログ](/glossary/ログ/)の詳細確認：**
Vercel [ダッシュボード](/glossary/ダッシュボード/)の Logs タブで関数実行[ログ](/glossary/ログ/)を確認し、どのステップで時間がかかっているか特定してください。タイムスタンプ付きの console.log を戦略的に追加し、実行時間を計測します。

```javascript
console.log(`[${new Date().toISOString()}] Processing started`);
// ... 処理 ...
console.log(`[${new Date().toISOString()}] DB query completed`);
```

**公式ドキュメント参照：**
Vercel 公式の「Serverless Function Configuration」（https://vercel.com/docs/functions/serverless-functions/configuration）および「Limits」（https://vercel.com/docs/limits）ページで最新の制限値とベストプラクティスを確認してください。

**パフォーマンス分析ツール：**
Vercel の Observability 機能（Pro プラン以上）を有効にすると、関数の CPU 使用率、メモリ使用量、実行時間をリアルタイムで監視できます。ボトルネック特定に有効です。

**GitHub Issues・コミュニティ：**
同じ問題が Vercel GitHub Repository（https://github.com/vercel/vercel）の Issues で報告されていないか検索してください。[サーバーレス](/glossary/サーバーレス/)関数の実装、特定のライブラリとの相性問題などが記載されている場合があります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*