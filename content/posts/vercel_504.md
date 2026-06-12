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
---
## エラーの概要

Vercel の 504 エラーは、デプロイされたサーバーレス関数の実行がタイムアウトに達したことを示します。実行時間の上限はプランと設定によって異なります。Hobby プランではデフォルト 300 秒（5 分）で、`maxDuration` を設定することで最大 300 秒までの範囲内で設定可能です。Pro プラン以上ではデフォルト 300 秒（5 分）で、Fluid Compute を有効にすると最大 800 秒（約 13 分）まで延長可能です。制限を超えると 504 Gateway Timeout レスポンスが返されます。一般的に、API 呼び出しやデータベースクエリの応答待ちが長引く場合に発生しやすいエラーです。

## 実際のエラーメッセージ例

**Vercel のブラウザー表示：**

```
504
Gateway Timeout
```

**関数ログ（Vercel Dashboard）：**

```json
{
  "errorCode": "FUNCTION_INVOCATION_TIMEOUT",
  "message": "The function exceeded the timeout duration",
  "functionName": "api/users",
  "executionDurationMs": 10000,
  "region": "sfo1"
}
```

**curl レスポンス：**

```
HTTP/1.1 504 Gateway Timeout
Server: Vercel
Content-Type: text/html
Connection: close

504 - Gateway Timeout
```

## よくある原因と解決手順

### 原因1：関数の実行時間が制限値に達している

Vercel のサーバーレス関数には、プランごとの実行時間制限があります。Hobby プランではデフォルト 300 秒（5 分）、Pro プランではデフォルト 300 秒が上限です。特に外部 API の呼び出しやデータベースアクセスが複数含まれる関数では、容易にこの上限に達する可能性があります。

**修正前（エラーが起きるコード）：**

```javascript
// api/getUserData.js
export default async function handler(req, res) {
  // 外部APIを3つ順次実行（各3秒）→ 合計9秒
  const user = await fetch('https://api.example.com/user/123').then(r => r.json());
  const posts = await fetch('https://api.example.com/posts/123').then(r => r.json());
  const comments = await fetch('https://api.example.com/comments/123').then(r => r.json());
  
  res.status(200).json({ user, posts, comments });
}
```

**修正後（API 呼び出しの並列実行）：**

```javascript
// api/getUserData.js
export default async function handler(req, res) {
  // 複数APIを並列実行（合計3秒に短縮）
  const [user, posts, comments] = await Promise.all([
    fetch('https://api.example.com/user/123').then(r => r.json()),
    fetch('https://api.example.com/posts/123').then(r => r.json()),
    fetch('https://api.example.com/comments/123').then(r => r.json())
  ]);
  
  res.status(200).json({ user, posts, comments });
}
```

**修正後（maxDuration の設定）：**

実行時間を延長する場合、`maxDuration` を明示的に設定できます：

```javascript
// vercel.json
{
  "functions": {
    "api/getUserData.js": {
      "maxDuration": 300
    }
  }
}
```

Hobby プランの場合も Pro プラン同様にデフォルト 300 秒まで設定可能です。

### 原因2：Vercel Fluid Compute を有効にしていない

Pro プラン以上を使用している場合、Vercel Fluid Compute を有効にすることで、関数の実行時間上限を 300 秒から 800 秒（約 13 分）に延長できます。Vercel Dashboard の「Settings」→「Functions」から有効化してください。

また、`maxDuration` を設定してさらに細かく制御することもできます：

```javascript
// vercel.json
{
  "functions": {
    "api/heavyProcessing.js": {
      "maxDuration": 800
    }
  }
}
```

### 原因3：外部 API・データベース接続にタイムアウトが設定されていない

外部サービスへのリクエストがハング状態に陥ると、関数全体が待機し続けて 504 に陥ります。特にネットワークが不安定な環境では、接続先が応答しなくなるケースが頻繁に発生します。

**修正前（エラーが起きるコード）：**

```javascript
// api/fetchUserProfile.js
import fetch from 'node-fetch';

export default async function handler(req, res) {
  // タイムアウト指定がない → 無限待ち可能性
  const response = await fetch('https://slow-api.example.com/profile');
  const data = await response.json();
  
  res.status(200).json(data);
}
```

**修正後：**

```javascript
// api/fetchUserProfile.js
import fetch from 'node-fetch';

export default async function handler(req, res) {
  // 5秒のタイムアウトを設定
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 5000);
  
  try {
    const response = await fetch('https://slow-api.example.com/profile', {
      signal: controller.signal
    });
    clearTimeout(timeoutId);
    const data = await response.json();
    res.status(200).json(data);
  } catch (error) {
    if (error.name === 'AbortError') {
      res.status(408).json({ error: 'API request timeout' });
    } else {
      res.status(500).json({ error: error.message });
    }
  }
}
```

### 原因4：重い同期的なデータ処理を関数内で実行している

画像リサイズ、CSV 解析、機械学習推論など、CPU 集約的な処理を直接関数内で行うと、瞬く間にタイムアウトに達します。これらの処理は関数の責務外に切り出し、キューイングシステムで非同期実行するべきです。

**修正前（エラーが起きるコード）：**

```javascript
// api/processImage.js
import sharp from 'sharp';
import fs from 'fs';

export default async function handler(req, res) {
  // 10MBの画像を複数フォーマットで変換（5秒以上かかる）
  const imageBuffer = fs.readFileSync('/tmp/large-image.jpg');
  
  const webp = await sharp(imageBuffer).webp().toBuffer();
  const avif = await sharp(imageBuffer).avif().toBuffer();
  const thumb = await sharp(imageBuffer).resize(200, 200).toBuffer();
  
  res.status(200).json({ success: true });
}
```

**修正後（バックグラウンド処理の利用）：**

```javascript
// api/processImage.js
export default async function handler(req, res) {
  // バックグラウンド処理を開始し、即座に返す
  event.waitUntil(processImageInBackground(req.body.imageId));
  
  res.status(202).json({ 
    message: 'Image processing started',
    jobId: req.body.imageId
  });
}

async function processImageInBackground(imageId) {
  // 重い処理はバックグラウンドで実行
  const imageBuffer = await fetchImage(imageId);
  await Promise.all([
    convertToWebP(imageBuffer),
    convertToAVIF(imageBuffer),
    createThumbnail(imageBuffer)
  ]);
}
```

キューイングシステム（Redis、Bull など）を使用する方法もあります：

```javascript
// api/processImage.js
import { Queue } from 'bullmq';
import redis from 'redis';

const connection = redis.createClient({
  host: process.env.REDIS_HOST,
  port: process.env.REDIS_PORT
});

const imageQueue = new Queue('image-processing', { connection });

export default async function handler(req, res) {
  // 処理をキューに追加して即座に返す
  await imageQueue.add('convert', {
    imageId: req.body.imageId,
    formats: ['webp', 'avif', 'thumbnail']
  });
  
  res.status(202).json({ 
    message: 'Image processing queued',
    jobId: 'pending'
  });
}
```

別途ワーカープロセスで非同期に処理を実行し、Redis などで進捗を管理します。

## Vercel 固有の注意点

Vercel のサーバーレス関数にはプランごとの実行時間制限のほか、メモリー上限やコールドスタート時間も性能に影響します。以下の点に留意してください：

- **Hobby プラン：実行時間デフォルト 300 秒（最大 300 秒）、メモリー上限 3008MB**
- **Pro プラン以上：実行時間デフォルト 300 秒、Fluid Compute で最大 800 秒、メモリー上限 3008MB**
- **同時実行数制限：1000（Hobby プランは優先度が低い）**

Vercel の `vercel logs` コマンドでリアルタイムログを確認できます：

```bash
vercel logs <your-project-name> --follow
```

このログで関数の実際の実行時間を確認し、制限値に近づいていないか監視するとよいでしょう。

## トラブルシューティング手順

Vercel Dashboard の「Deployments」タブで該当デプロイメントのログを確認してください。「Functions」セクションで実行時間の詳細が表示されます。以下のコマンドでローカルテストも有効です：

```bash
vercel dev
```

この環境ではタイムアウト上限なく関数を実行でき、実際の処理時間を計測できます。関数内に `console.log()` を仕込んで各処理の経過時間を記録し、ボトルネックを特定してください。

原因不明の場合は、Vercel の公式ドキュメント（https://vercel.com/docs/functions/serverless-functions/limitations）を参照するか、Vercel サポートに問い合わせてください。エンタープライズ契約がある場合は、優先サポートが利用可能です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*