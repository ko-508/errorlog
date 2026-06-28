---
title: "Firebase の 504 エラー：原因と解決策"
date: 2026-05-28
description: "Firebase HostingまたはCloud Functionsがバックエンドからの応…"
tags: ["Firebase"]
errorCode: "504"
service: "Firebase"
error_type: "504"
components: ["Hosting", "Cloud Functions", "Realtime Database"]
related_services: ["Firebase Console", "gcloud"]
lastmod: 2026-06-14
---

## エラーの概要

Firebase HostingまたはCloud Functionsの[バックエンド](/glossary/バックエンド/)処理が[タイムアウト](/glossary/タイムアウト/)し、クライアントに504 Gateway Timeout[エラー](/glossary/エラー/)が返される状況です。この[エラー](/glossary/エラー/)は、[リクエスト](/glossary/リクエスト/)に対して指定時間内に[レスポンス](/glossary/レスポンス/)が返されなかったことを示します。Firebase環境では、Cloud Functionsの実行時間制限やHostingの統合[タイムアウト](/glossary/タイムアウト/)（通常60秒）を超過した場合に発生することが多く、本番環境で多くのユーザーに影響を与える可能性があります。

## 実際のエラーメッセージ例

**ブラウザの[コンソール](/glossary/コンソール/)出力例：**

```json
{
  "error": {
    "code": 504,
    "message": "The service you requested timed out and did not complete before the deadline. This typically indicates the service is overloaded or not responding quickly enough."
  }
}
```

**Cloud Functions の[ログ](/glossary/ログ/)例：**

```
Function execution took 61234ms, exceeding the 60000ms timeout.
```

**[HTTP](/glossary/http/) [レスポンス](/glossary/レスポンス/)例：**

```
HTTP/1.1 504 Gateway Timeout
Content-Type: application/json

{
  "error": "deadline_exceeded",
  "message": "Cloud Functions did not complete execution within the timeout period"
}
```

## よくある原因と解決手順

### 1. Cloud Functionsの処理時間がタイムアウト制限を超えている

Cloud Functionsの実行時間が[タイムアウト](/glossary/タイムアウト/)値を超えると504[エラー](/glossary/エラー/)が発生します。Firebase Hostingからの[リクエスト](/glossary/リクエスト/)はデフォルトでHosting側の60秒制限があり、この間にCloud Functionsが応答を返す必要があります。データベースクエリの遅延、外部[API](/glossary/api/)の呼び出し遅延、処理の複雑さが原因となります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
exports.slowFunction = functions.https.onRequest(async (req, res) => {
  // 複雑で遅い処理（改善前）
  const result = await db.collection('users').get(); // 大量データを同期取得
  let totalTime = 0;
  for (let user of result.docs) {
    const data = await fetchExternalAPI(user.id); // 各ユーザーごとに逐次APIコール
    totalTime += data.processingTime;
  }
  res.json({ total: totalTime });
});
```

**After（修正後）：**

```javascript
exports.fastFunction = functions.https.onRequest(async (req, res) => {
  // 並列処理とクエリ最適化（改善後）
  const result = await db.collection('users').limit(100).get(); // ページネーション導入
  const promises = result.docs.map(user => 
    fetchExternalAPI(user.id).catch(err => ({ processingTime: 0 }))
  ); // 並列実行
  const data = await Promise.all(promises);
  res.json({ total: data.reduce((sum, d) => sum + d.processingTime, 0) });
});
```

### 2. コールドスタート時の初期化処理に時間がかかっている

Cloud Functionsの関数が一定期間実行されていない場合、起動時にメモリ確保やライブラリの読み込みが必要になります。大規模なライブラリの読み込みや[データベース](/glossary/データベース/)接続の初期化が[コールドスタート](/glossary/コールドスタート/)中に実行されると、[タイムアウト](/glossary/タイムアウト/)に達しやすくなります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
const admin = require('firebase-admin');
const serviceAccount = require('./serviceAccountKey.json'); // 関数の起動時に読み込み
const tf = require('@tensorflow/tfjs'); // 大規模ライブラリを毎回初期化
const model = require('@tensorflow/tfjs-node');

exports.mlFunction = functions.https.onRequest(async (req, res) => {
  // コールドスタート時にTensorFlowをロードするため時間がかかる
  const prediction = await model.predict(req.body.data);
  res.json({ result: prediction });
});
```

**After（修正後）：**

```javascript
const admin = require('firebase-admin');
const serviceAccount = require('./serviceAccountKey.json');
let tf = null;
let model = null;
let initialized = false;

exports.mlFunction = functions.https.onRequest(async (req, res) => {
  // グローバルスコープで初期化（ウォームスタート時は再利用）
  if (!initialized) {
    tf = require('@tensorflow/tfjs');
    const tfNode = require('@tensorflow/tfjs-node');
    model = await tf.loadLayersModel('indexeddb://my-model');
    initialized = true;
  }
  const prediction = await model.predict(req.body.data);
  res.json({ result: prediction });
});
```

### 3. Cloud Functionsのメモリ割り当てが不足している

メモリ割り当てが少ないと、CPUの性能も制限され、同じ処理でも実行時間が延びます。デフォルトの256MBから512MB以上に増やすことで、処理速度が向上し、[タイムアウト](/glossary/タイムアウト/)を回避できます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
# firebase.json
{
  "functions": {
    "source": "functions",
    "memory": 256  # デフォルト設定（低いメモリ割り当て）
  }
}
```

**After（修正後）：**

```yaml
# firebase.json
{
  "functions": {
    "source": "functions",
    "memory": 2048,  # 2GB に増加（処理速度が向上）
    "timeoutSeconds": 540  # 必要に応じてタイムアウトも延長
  }
}
```

### 4. データベースクエリの効率性が低い

Firestoreへの大量のドキュメント読み込みやN+1クエリパターンは、処理時間を大幅に増加させます。[クエリ](/glossary/クエリ/)の最適化やバッチ処理、[インデックス](/glossary/インデックス/)設定により改善できます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
exports.getOrdersWithUsers = functions.https.onRequest(async (req, res) => {
  const orders = await db.collection('orders').get();
  const results = [];
  for (const order of orders.docs) {
    const user = await db.collection('users').doc(order.data().userId).get();
    results.push({ ...order.data(), user: user.data() });
  }
  res.json(results);
});
```

**After（修正後）：**

```javascript
exports.getOrdersWithUsers = functions.https.onRequest(async (req, res) => {
  // ページネーションとバッチ読み込みを利用
  const orders = await db.collection('orders').limit(50).get();
  const userIds = [...new Set(orders.docs.map(o => o.data().userId))];
  const users = await db.getAll(...userIds.map(id => db.collection('users').doc(id)));
  const userMap = new Map(users.map(u => [u.id, u.data()]));
  
  const results = orders.docs.map(o => ({
    ...o.data(),
    user: userMap.get(o.data().userId)
  }));
  res.json(results);
});
```

## Firebase特有の注意点

**Cloud Functionsの[タイムアウト](/glossary/タイムアウト/)設定**

Firebase [CLI](/glossary/cli/)で[デプロイ](/glossary/デプロイ/)する際、`firebase.json`で[タイムアウト](/glossary/タイムアウト/)秒数を明示的に設定できます。デフォルトは60秒ですが、最大540秒（9分）まで延長可能です。ただし長すぎる[タイムアウト](/glossary/タイムアウト/)は本質的な問題を隠すため、根本的な最適化を優先してください。

**Realtime DatabaseとFirestoreの遅延**

Realtime Databaseへの大量書き込みやFirestoreの[トランザクション](/glossary/トランザクション/)処理が遅い場合、Pub/Sub経由での非同期処理への移行を検討してください。[HTTP](/glossary/http/)[リクエスト](/glossary/リクエスト/)を受け付ける関数から長時間の処理を切り離すことで、504[エラー](/glossary/エラー/)を回避できます。

**Firebase Hostingの統合[タイムアウト](/glossary/タイムアウト/)**

Hostingから呼び出すCloud Functionsは、Hosting層での[タイムアウト](/glossary/タイムアウト/)（通常60秒）に加えて、Cloud Functions自体の[タイムアウト](/glossary/タイムアウト/)制限の両方の影響を受けます。どちらかが先に達するかを意識して調整が必要です。

## それでも解決しない場合

**[ログ](/glossary/ログ/)の確認方法**

```bash
gcloud functions describe <関数名> --runtime nodejs18
gcloud functions logs read <関数名> --limit 50
```

または、Firebase Consoleで「関数」>「[ログ](/glossary/ログ/)」タブから実行[ログ](/glossary/ログ/)を確認してください。各[リクエスト](/glossary/リクエスト/)の実行時間と完了状況を確認でき、504の発生パターンが明らかになります。

**[パフォーマンス](/glossary/パフォーマンス/)分析**

Cloud Profilerを有効化することで、CPUとメモリの使用状況を[リアルタイム](/glossary/リアルタイム/)で監視できます。Firebase ConsoleまたはCloud Consoleで「[パフォーマンス](/glossary/パフォーマンス/)分析」セクションを確認し、ボトルネック箇所を特定してください。

**公式ドキュメント**

- 「Cloud Functionsの[タイムアウト](/glossary/タイムアウト/)とメモリ管理」（Firebase公式）
- 「Firestoreの[パフォーマンス](/glossary/パフォーマンス/)最適化ガイド」
- 「Cloud Functionsの[コールドスタート](/glossary/コールドスタート/)削減」

問題が解決しない場合は、Firebase Support（有償[アカウント](/glossary/アカウント/)の場合）またはGitHub上の[firebase-tools issues](https://github.com/firebase/firebase-tools/issues)で類似事例を検索してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*