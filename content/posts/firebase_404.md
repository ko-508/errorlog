---
draft: true
title: "Firebase の 404 エラー：原因と解決策"
date: 2026-01-01
description: "Firebaseで404エラーが返される場合、要求したリソース（Firestoreのドキュメント、Cloud Functionsのエンドポイント、Realtime Databaseのパスなど）がFirebaseプロジェクト内に存在しないこと"
tags: ["Firebase"]
errorCode: "404"
lastmod: 2026-05-31
service: "Firebase"
error_type: "404"
components: ["Firestore", "Cloud Functions", "Realtime Database", "Auth"]
related_services: ["JavaScript", "SDK", "HTTP", "RFC 9110"]
---

## エラーの概要

Firebaseで404[エラー](/glossary/エラー/)が返される場合、要求したリソース（Firestoreのドキュメント、Cloud Functionsの[エンドポイント](/glossary/エンドポイント/)、Realtime Databaseのパスなど）がFirebaseプロジェクト内に存在しないことを示しています。この[エラー](/glossary/エラー/)は[HTTP](/glossary/http/)標準仕様（[RFC](/glossary/rfc/) 9110）で定義されており、Firebaseの複数のサービスで発生する可能性があります。開発環境から本番環境への移行時、または参照パスの変更後に特に多く報告される[エラー](/glossary/エラー/)です。

## 実際のエラーメッセージ例

Firestore [SDK](/glossary/sdk/)からの[エラー](/glossary/エラー/)応答：
```json
{
  "code": 404,
  "message": "Document not found at projects/<your-project-id>/databases/(default)/documents/users/nonexistent_user_id"
}
```

Cloud Functionsの[レスポンス](/glossary/レスポンス/)：
```json
{
  "error": {
    "code": 404,
    "message": "Not Found. Could not find the specified resource. Ensure the function name and region are correct."
  }
}
```

JavaScript[コンソール](/glossary/コンソール/)出力：
```
FirebaseError: Firebase: Error (auth/operation-not-supported-in-this-environment).
GET https://firestore.googleapis.com/v1/projects/<your-project-id>/databases/(default)/documents/collections/invalid_path - 404
```

## よくある原因と解決手順

**原因1：Firestoreのドキュメントパスが誤っている**

Firestoreはドキュメント階層が厳密です。コレクション名やドキュメント[ID](/glossary/id/)の綴り間違いが404につながります。

**Before（[エラー](/glossary/エラー/)が発生するコード）:**
```javascript
const docRef = doc(db, "users", "user123");
const docSnap = await getDoc(docRef);
// データベースに "users" コレクションと "user123" ドキュメントが存在しない場合
```

**After（修正後）:**
```javascript
const docRef = doc(db, "users", "user_123"); // 正しいドキュメントID
const docSnap = await getDoc(docRef);
if (docSnap.exists()) {
  console.log("Document data:", docSnap.data());
} else {
  console.log("Document does not exist");
}
```

**原因2：Cloud Functionsのエンドポイントパスが異なる**

[デプロイ](/glossary/デプロイ/)時の関数名やリージョン指定が変わると、呼び出しURLが無効になります。

**Before（[エラー](/glossary/エラー/)が発生する呼び出し）:**
```bash
curl https://us-central1-<your-project-id>.cloudfunctions.net/getUserData?userId=123
# 実際にはこのパスが存在しない
```

**After（修正後）:**
```bash
# Firebase Consoleで正しい関数名を確認
curl https://us-central1-<your-project-id>.cloudfunctions.net/get-user-data?userId=123
```

Cloud Functionsの[デプロイ](/glossary/デプロイ/)設定の確認：
```yaml
# firebase.json
{
  "functions": {
    "source": "functions",
    "codebase": "default",
    "runtime": "nodejs18"
  }
}
```

**原因3：対象のコレクションやドキュメントが作成されていない**

Firestoreは明示的にコレクション・ドキュメントを作成する必要があります。存在しないパスへのアクセスは404になります。

**Before（[エラー](/glossary/エラー/)が発生）:**
```javascript
const usersRef = collection(db, "users");
const q = query(usersRef, where("role", "==", "admin"));
const querySnapshot = await getDocs(q);
// "users" コレクション自体が存在しない場合、404が返される可能性
```

**After（事前に初期化）:**
```javascript
// 初回データの作成
const usersRef = collection(db, "users");
await setDoc(doc(usersRef, "user_123"), {
  name: "John Doe",
  role: "admin",
  createdAt: serverTimestamp()
});

// その後、クエリを実行
const q = query(usersRef, where("role", "==", "admin"));
const querySnapshot = await getDocs(q);
```

**原因4：Realtime Databaseのパスが誤っている**

Realtime Databaseも厳密なパス指定が必要です。大文字小文字の違いも404の原因になります。

**Before（[エラー](/glossary/エラー/)が発生）:**
```javascript
const dbRef = ref(database, "Users/UserData"); // 大文字で記述
const snapshot = await get(dbRef);
```

**After（修正後）:**
```javascript
const dbRef = ref(database, "users/userData"); // Firestoreの命名規則に統一
const snapshot = await get(dbRef);
if (snapshot.exists()) {
  console.log(snapshot.val());
}
```

## ツール固有の注意点

**Firestoreセキュリティルールと404**

セキュリティルールが拒否している場合も404が返されることがあります。[権限](/glossary/権限/)がないドキュメントへのアクセス試行は、情報漏洩を防ぐため意図的に404で応答します。

```javascript
// firestore.rules で READ 権限がない場合
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /users/{userId} {
      allow read: if request.auth.uid == userId;
      allow write: if request.auth.uid == userId;
    }
  }
}
```

[認証](/glossary/認証/)ユーザーでない[リクエスト](/glossary/リクエスト/)は404を受け取ります。必ず[認証](/glossary/認証/)を実装してください。

**Cloud Functionsのリージョン指定**

関数が[デプロイ](/glossary/デプロイ/)されたリージョンと呼び出しURLが一致していない場合、404が返されます。

```javascript
// デプロイ時
import * as functions from 'firebase-functions';

export const getData = functions
  .region('us-central1')
  .https.onRequest((request, response) => {
    response.json({ message: "Success" });
  });
```

呼び出しURLは必ず `https://us-central1-<your-project-id>.cloudfunctions.net/getData` になります。異なるリージョンでのURLアクセスは404になります。

**Realtime DatabaseとHosting URLの混同**

Firebase Hostingと Realtime Database は異なる[エンドポイント](/glossary/エンドポイント/)です。Hosting経由でDatabase [API](/glossary/api/)にアクセスする場合は、正しい[エンドポイント](/glossary/エンドポイント/)を使用してください。

```javascript
// 正しい Realtime Database エンドポイント
const database = getDatabase(app, "https://<your-project-id>.firebaseio.com");

// Firebase Hosting と混同しない
// https://<your-project-id>.web.app は Hosting のエンドポイント
```

## それでも解決しない場合

**[ログ](/glossary/ログ/)確認の手順**

1. **Firebase Console** → 対象プロジェクト → **Logs** セクションを開く
2. Cloud Functionsの場合は **Functions** タブで詳細な[エラーログ](/glossary/エラーログ/)を確認
3. Firestoreの場合は **Firestore** → **Monitoring** でリアルタイムエラーを監視

**デバッグコマンド**

Firebaseエミュレータを使用してローカルで動作確認：
```bash
firebase emulators:start
```

Cloud Functionsのローカルテスト：
```bash
firebase functions:shell
> getData({userId: "test_user"})
```

**公式ドキュメント参照**

- [Firestoreのドキュメント参照](https://firebase.google.com/docs/firestore/query-data/get-data)
- [Cloud Functionsの関数デプロイ](https://firebase.google.com/docs/functions/manage-functions)
- [Realtime Databaseのデータ構造](https://firebase.google.com/docs/database/usage/bestpractices)

**GitHub Issuesとコミュニティ**

firebase-js[リポジトリ](/glossary/リポジトリ/)のIssueで類似ケースが報告されていることが多くあります。[エラーメッセージ](/glossary/エラーメッセージ/)をコピーして検索することで、既知の問題と解決策を見つけられる場合があります。Firebase公式フォーラムでも専門家による回答が得られます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*