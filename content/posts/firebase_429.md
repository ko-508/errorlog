---
title: "Firebase の 429 エラー：原因と解決策"
date: 2026-01-01
description: "429 Too Many Requests は、Firebase のレート制限に達したことを示す HTTP ステータスコードです。"
tags: ["Firebase"]
errorCode: "429"
lastmod: 2026-05-31
service: "Firebase"
error_type: "429"
components: ["Firestore", "Cloud Functions", "Authentication", "Realtime Database"]
related_services: ["Spark プラン", "Blaze プラン"]
---

## エラーの概要

429 Too Many Requests は、Firebase の[レート制限](/glossary/レート制限/)に達したことを示す [HTTP](/glossary/http/) [ステータスコード](/glossary/ステータスコード/)です。Firestore の[データベース](/glossary/データベース/)操作、Cloud Functions の実行、Authentication メール送信、Realtime Database へのアクセスなど、様々な Firebase サービスで発生します。無料プランでは特に厳しい制限があり、本番環境への移行時やトラフィック増加時に顕著になります。

## 実際のエラーメッセージ例

```json
{
  "error": {
    "code": 429,
    "message": "Too many requests or insufficient resources for quota. Please retry after some time."
  }
}
```

```bash
Error: Too many requests. Please retry the request after some time.
at /path/to/node_modules/firebase-admin/lib/firestore.js:123
Code: RESOURCE_EXHAUSTED
```

## よくある原因と解決手順

### 原因 1: Firestore 読み取り・書き込み上限の超過（Spark プラン）

Spark プラン（無料）では 1 日あたりの読み取り・書き込み回数が制限されています。大量のドキュメント操作や頻繁なリアルタイムリスナー登録により、この上限をすぐに達してしまいます。

**Before（制限を受ける実装）**

```javascript
// リアルタイムリスナーが複数クライアントで常時動作
const unsubscribe = db.collection("users").onSnapshot(snapshot => {
  snapshot.docs.forEach(doc => {
    console.log(doc.id, doc.data());
  });
});

// バッチ書き込みで大量データを一度に投入
async function uploadManyDocs() {
  const batch = db.batch();
  for (let i = 0; i < 10000; i++) {
    const ref = db.collection("items").doc(`item-${i}`);
    batch.set(ref, { name: `Item ${i}` });
  }
  await batch.commit(); // 10000 件の書き込み = 制限超過
}
```

**After（修正後）**

```javascript
// クエリを絞り込み、必要なフィールドのみ取得
const unsubscribe = db.collection("users")
  .limit(10)
  .onSnapshot(snapshot => {
    snapshot.docs.forEach(doc => {
      console.log(doc.id, doc.data());
    });
  });

// 有料プラン（Blaze）へ移行するか、バッチ処理を小分けにする
async function uploadManyDocsOptimized() {
  const batchSize = 500;
  const items = [];
  for (let i = 0; i < 10000; i++) {
    items.push({ name: `Item ${i}` });
  }
  
  for (let i = 0; i < items.length; i += batchSize) {
    const batch = db.batch();
    items.slice(i, i + batchSize).forEach((item, idx) => {
      const ref = db.collection("items").doc(`item-${i + idx}`);
      batch.set(ref, item);
    });
    await batch.commit();
    await new Promise(resolve => setTimeout(resolve, 1000)); // 遅延
  }
}
```

### 原因 2: Cloud Functions の呼び出し頻度が上限を超過

Spark プラン では Cloud Functions の月間呼び出し回数が 200 万回に制限されています。短時間での大量呼び出しやポーリング実装により、この制限に即座に達します。

**Before（制限を受ける実装）**

```javascript
// クライアント側で頻繁に関数を呼び出す
async function checkStatusPolling() {
  setInterval(async () => {
    const response = await firebase.functions().httpsCallable("getStatus")({});
    console.log(response.data);
  }, 1000); // 1秒ごとに呼び出し → すぐに上限到達
}

// Cloud Function 側で処理が遅い
exports.slowFunction = functions.https.onCall(async (data, context) => {
  const result = await expensiveDbQuery(); // 時間がかかる
  return result;
});
```

**After（修正後）**

```javascript
// リアルタイムデータベースやPub/Subを活用
const statusRef = db.collection("status").doc("current");
statusRef.onSnapshot(doc => {
  console.log(doc.data());
}); // リアルタイムリスナーで変更を監視（読み取り効率的）

// Cloud Function をキャッシュ戦略で最適化
exports.optimizedFunction = functions.https.onCall(async (data, context) => {
  const cacheKey = `status-${data.userId}`;
  const cached = await admin.database().ref(cacheKey).get();
  if (cached.exists()) {
    return cached.val();
  }
  
  const result = await expensiveDbQuery();
  await admin.database().ref(cacheKey).set(result, { priority: 3 });
  return result;
});
```

### 原因 3: Authentication メール送信の上限超過

Spark プラン では Authentication メール送信数が 100 件/日に制限されています。パスワードリセットやメール確認の実装で短時間に大量送信すると制限に達します。

**Before（制限を受ける実装）**

```javascript
// ユーザー登録時に確認メールを即座に送信（制限なし）
async function registerUser(email, password) {
  const user = await admin.auth().createUser({
    email: email,
    password: password
  });
  
  // 登録直後にメール送信リクエストが殺到
  await admin.auth().sendPasswordResetEmail(email);
  await admin.auth().sendSignInLinkToEmail(email);
  
  return user;
}
```

**After（修正後）**

```javascript
// キューイングシステムで送信を制御
const admin = require("firebase-admin");

async function registerUserOptimized(email, password) {
  const user = await admin.auth().createUser({
    email: email,
    password: password
  });
  
  // Cloud Tasks/Pub/Sub でメール送信をスケジュール
  await admin.firestore()
    .collection("mail")
    .add({
      to: email,
      template: "verification",
      createdAt: new Date(),
      status: "pending"
    });
  
  return user;
}
```

## ツール固有の注意点

### Firestore での 429 対策

Firestore では「読み取り」「書き込み」「削除」がそれぞれカウントされます。Spark プラン では日次 5 万件の読み取り、1 万件の書き込み、1 万件の削除が上限です。複数ユーザーからの同時アクセスが見込まれる場合は、早期に **Blaze プラン（従量課金制）** への移行を検討してください。

### Realtime Database での制限

Firebase Realtime Database でも 429 が発生します。`.limitToFirst()``.limitToLast()` で[クエリ](/glossary/クエリ/)結果を制限し、不要なデータ転送を削減してください。

### Cloud Storage のダウンロード制限

Cloud Storage では Spark プラン で 1GB/日のダウンロード上限があります。大容量ファイルの配信には **Signed URL** を使用し、キャッシング層（[CDN](/glossary/cdn/)）を導入してください。

## それでも解決しない場合

### ログの確認

Firebase Console の「Quotas」タブで現在の使用状況を確認します。`firebase-admin` を使用している場合は、関数の実行[ログ](/glossary/ログ/)を Cloud Logging で確認してください。

```bash
gcloud functions logs read <function-name> --limit 50
```

### 公式ドキュメント

- [Firestore のクォータと制限](https://firebase.google.com/docs/firestore/quotas)
- [Cloud Functions の価格と割り当て](https://firebase.google.com/docs/functions/quotas)
- [Firebase Authentication のレート制限](https://firebase.google.com/docs/auth/limits)

### サポートへの問い合わせ

Blaze プラン の有料顧客は Firebase Support から詳細な制限内容や一時的な上限引き上げを[リクエスト](/glossary/リクエスト/)できます。GitHub Issues や Stack Overflow でも同様の問題事例が多く報告されており、参考になります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*