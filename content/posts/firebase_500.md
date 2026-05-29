---
title: "Firebase の 500 エラー：原因と解決策"
date: 2026-01-01
description: "Firebase の 500 エラーの原因と解決策をわかりやすく解説します。"
tags: ["Firebase"]
errorCode: "500"
lastmod: 2026-05-29
---

## エラーの概要

Firebase における 500 エラーは、Firebase サーバー側で予期しない内部エラーが発生したことを示す[HTTP](/glossary/http/) [ステータスコード](/glossary/ステータスコード/)です。Realtime Database、Firestore、Cloud Functions、Authentication など、Firebase のどのサービスでも発生する可能性があります。このエラーは、クライアント側の設定ミスではなく、サーバー側の処理失敗を意味することが多いため、段階的な調査が必要です。

## 実際のエラーメッセージ例

```json
{
  "error": {
    "code": 500,
    "message": "Internal error encountered."
  }
}
```

```
Error: Internal Server Error (500)
at FirebaseError (/functions/node_modules/firebase-admin/lib/utils/error.ts:42:37)
```

## よくある原因と解決手順

### 原因1：Cloud Functions のコード内で処理されない例外が発生している

**なぜ発生するか**  
Cloud Functions で実行されるコード内で`try-catch`で捕捉されていない例外やPromise rejection が発生すると、Firebase が 500 エラーを返します。データベースクエリの失敗、[API](/glossary/api/)呼び出しエラー、型変換ミスなどが原因となることが多いです。

**Before（エラーが起きるコード）**
```javascript
exports.processData = functions.https.onCall(async (data, context) => {
  const result = await admin.database().ref('users').once('value');
  const userData = result.val();
  return userData.toUpperCase(); // userData が null の場合、エラーが発生
});
```

**After（修正後）**
```javascript
exports.processData = functions.https.onCall(async (data, context) => {
  try {
    const result = await admin.database().ref('users').once('value');
    const userData = result.val();
    
    if (!userData) {
      throw new functions.https.HttpsError('not-found', 'User data not found');
    }
    
    return userData.toUpperCase();
  } catch (error) {
    console.error('Error in processData:', error);
    throw new functions.https.HttpsError('internal', 'Failed to process data');
  }
});
```

### 原因2：Firestore / Realtime Database のセキュリティルールが許可していない

**なぜ発生するか**  
セキュリティルールが不適切に設定されていると、クエリ実行時にルール評価エラーが発生し、500 が返される場合があります。特に複雑な条件や無限ループするルールが設定されているとき顕著です。

**Before（エラーが起きる設定）**
```yaml
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /users/{userId} {
      allow read, write: if request.auth.uid == resource.data.owner_id && resource.data.owner_id == request.auth.uid;
    }
  }
}
```

**After（修正後）**
```yaml
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /users/{userId} {
      allow read, write: if request.auth != null && request.auth.uid == resource.data.owner_id;
    }
  }
}
```

### 原因3：Realtime Database のインデックスが未作成

**なぜ発生するか**  
Realtime Database で複数フィールドを`orderByChild()`や`orderByValue()`でクエリするとき、必要な[インデックス](/glossary/インデックス/)が[コンソール](/glossary/コンソール/)で作成されていないと 500 エラーが発生します。Firestore では自動[インデックス](/glossary/インデックス/)が作成されることが多いですが、Realtime Database は明示的な作成が必要です。

**Before（[インデックス](/glossary/インデックス/)なしでのクエリ）**
```javascript
// Firebase Realtime Database のインデックスが未作成
admin.database().ref('posts')
  .orderByChild('timestamp')
  .limitToLast(10)
  .once('value', (snapshot) => {
    console.log(snapshot.val());
  });
```

**After（Firebase Console で[インデックス](/glossary/インデックス/)を作成）**
```
Firebase Console > Realtime Database > Rules タブ
以下のインデックス定義を追加：

{
  "rules": {
    "posts": {
      ".indexOn": ["timestamp"]
    }
  }
}
```

その後、コードは同じまま：
```javascript
admin.database().ref('posts')
  .orderByChild('timestamp')
  .limitToLast(10)
  .once('value', (snapshot) => {
    console.log(snapshot.val());
  });
```

## Firebase 固有の注意点

### Cloud Functions の実行タイムアウト
デフォルトの[タイムアウト](/glossary/タイムアウト/)時間は 60 秒ですが、長時間の処理が必要な場合は最大 540 秒まで延長できます。[タイムアウト](/glossary/タイムアウト/)超過時に 500 が返される場合があります。

```bash
gcloud functions deploy <function-name> --timeout=300
```

### Firebase Admin SDK のバージョン不一致
古いバージョンの Admin [SDK](/glossary/sdk/) を使用していると、新しいサービスの仕様に対応できず 500 が発生することがあります。常に最新バージョンを使用してください。

```bash
npm install firebase-admin@latest
```

### リージョン設定の欠落
Cloud Functions を複数リージョンで[デプロイ](/glossary/デプロイ/)する場合、リージョン指定が不正だと 500 が返されます。

```javascript
// Before（リージョン指定なし）
exports.myFunction = functions.https.onCall(async (data, context) => {
  // ...
});

// After（リージョン指定あり）
exports.myFunction = functions.region('asia-northeast1').https.onCall(async (data, context) => {
  // ...
});
```

### Authentication トークンの有効期限切れ
[SDK](/glossary/sdk/) が古いキャッシュトークンを使用している場合、[認証](/glossary/認証/)エラーが 500 として返される場合があります。[トークン](/glossary/トークン/)の更新メカニズムを確認してください。

```javascript
// トークンの強制更新
await firebase.auth().currentUser.getIdToken(true);
```

## それでも解決しない場合

**Cloud Functions のログを確認する**  
Firebase Console から「Functions」→「ログ」を開き、実行時の詳細エラーメッセージを確認してください。`console.error()`で出力したログも表示されます。

**gcloud [CLI](/glossary/cli/) でのログ確認**
```bash
gcloud functions logs read <function-name> --limit 50
```

**Firebase Support への問い合わせ**  
Firebase Console の「サポート」タブから公式サポートに問い合わせることで、サーバー側のログから原因を特定できる場合があります。

**公式ドキュメント**  
- [Cloud Functions トラブルシューティング](https://firebase.google.com/docs/functions/troubleshooting)
- [Firestore セキュリティルール ガイド](https://firebase.google.com/docs/firestore/security/start)
- [Realtime Database インデックス設定](https://firebase.google.com/docs/database/security/indexing)

**GitHub Issues**  
firebase-js-sdk および firebase-admin-node の[リポジトリ](/glossary/リポジトリ/)で同様のエラーが報告されていないか検索してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*