---
title: "Firebase の 401 エラー：原因と解決策"
date: 2026-01-01
description: "Firebase の 401 エラーは、Firebaseサーバーへのリクエストに対して「認証情報が不足している、または無効である」という応答です。"
tags: ["Firebase"]
errorCode: "401"
lastmod: 2026-05-31
service: "Firebase"
error_type: "401"
components: ["Firestore", "Auth", "Realtime Database"]
related_services: ["Node.js", "Python", "Cloud Firestore", "Firebase Console"]
top_queries:
- '401 とは'
---

## エラーの概要

Firebase の 401 [エラー](/glossary/エラー/)は、Firebase[サーバー](/glossary/サーバー/)への[リクエスト](/glossary/リクエスト/)に対して「認証情報が不足している、または無効である」という応答です。[ID](/glossary/id/)[トークン](/glossary/トークン/)の有効期限切れ、[サービスアカウント](/glossary/サービスアカウント/)認証鍵の誤り、セキュリティルールの設定ミスなど、複数の原因が考えられます。この[エラー](/glossary/エラー/)が発生した場合、認証周りの設定を段階的に確認することで、ほとんどの場合は短時間で解決できます。

## 実際のエラーメッセージ例

```json
{
  "error": {
    "code": 401,
    "message": "Unauthorized",
    "errors": [
      {
        "domain": "global",
        "reason": "unauthorized",
        "message": "The caller does not have permission"
      }
    ]
  }
}
```

```bash
Error: Failed to get document (401): The caller does not have permission
    at Object.catch (/app/node_modules/firebase/firestore.js:123)
```

## よくある原因と解決手順

### 原因 1: IDトークンの有効期限が切れている

Firebase Authentication では、[ID](/glossary/id/)[トークン](/glossary/トークン/)は発行後 1 時間で自動的に無効になります。長時間アクティビティがないセッションでこの[エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）**

```javascript
// トークンをキャッシュして使い続けている
const cachedToken = localStorage.getItem('firebaseToken');
const response = await fetch('https://firestore.googleapis.com/v1/projects/<project-id>/databases/(default)/documents/users', {
  headers: {
    'Authorization': `Bearer ${cachedToken}`
  }
});
```

**After（修正後）**

```javascript
// 常に最新のトークンを取得する
const user = firebase.auth().currentUser;
const freshToken = await user.getIdToken(true); // true で強制リフレッシュ
const response = await fetch('https://firestore.googleapis.com/v1/projects/<project-id>/databases/(default)/documents/users', {
  headers: {
    'Authorization': `Bearer ${freshToken}`
  }
});
```

### 原因 2: サービスアカウント認証鍵ファイルが無効または古い

Node.js や Python でサーバーサイド処理を行う場合、[サービスアカウント](/glossary/サービスアカウント/)の [JSON](/glossary/json/) 鍵ファイルが削除されたり、ローテーションされたりすると 401 が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）**

```python
# 旧い鍵ファイルを参照している
import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate('/path/to/old-key.json')
firebase_admin.initialize_app(cred)
db = firestore.client()
doc = db.collection('users').document('user1').get()
```

**After（修正後）**

```python
# Firebase Console から最新の鍵ファイルをダウンロード
import firebase_admin
from firebase_admin import credentials, firestore
import os

key_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
if not key_path:
    raise ValueError('GOOGLE_APPLICATION_CREDENTIALS env var not set')

cred = credentials.Certificate(key_path)
firebase_admin.initialize_app(cred)
db = firestore.client()
doc = db.collection('users').document('user1').get()
```

### 原因 3: セキュリティルールが拒否設定になっている

Cloud Firestore / Realtime Database のセキュリティルールが、そのユーザーに対して読み取り/書き込みを禁止していると 401 が返されます。

**Before（[エラー](/glossary/エラー/)が起きるルール）**

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /{document=**} {
      allow read, write: if false; // すべてのアクセスを拒否
    }
  }
}
```

**After（修正後）**

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /users/{userId} {
      allow read, write: if request.auth.uid == userId; // ユーザー本人のみアクセス可
    }
    match /public/{document=**} {
      allow read: if request.auth != null; // 認証済みユーザーは読み取り可
    }
  }
}
```

### 原因 4: 環境変数 GOOGLE_APPLICATION_CREDENTIALS が未設定

[サーバー](/glossary/サーバー/)環境で `GOOGLE_APPLICATION_CREDENTIALS` が正しく設定されていないと、[SDK](/glossary/sdk/) が認証情報を見つけられず 401 が発生します。

**Before（[エラー](/glossary/エラー/)が起きる設定）**

```bash
# .env ファイルに記述しているだけで、実際には読み込まれていない
GOOGLE_APPLICATION_CREDENTIALS=./serviceAccountKey.json
```

**After（修正後）**

```bash
# シェル環境で明示的にエクスポート
export GOOGLE_APPLICATION_CREDENTIALS=$(pwd)/serviceAccountKey.json
node app.js

# または Docker での実行
docker run -e GOOGLE_APPLICATION_CREDENTIALS=/app/serviceAccountKey.json \
  -v $(pwd)/serviceAccountKey.json:/app/serviceAccountKey.json \
  my-app:latest
```

## Firebase 固有の注意点

### Cloud Firestore / Realtime Database のセキュリティルール検証

セキュリティルールの構文[エラー](/glossary/エラー/)や論理ミスは 401 として表面化します。Firebase Console の「ルール」タブでシミュレーター機能を使い、特定のユーザー[ID](/glossary/id/) と操作（read/write）の組み合わせで実際にアクセス可能か[テスト](/glossary/テスト/)してください。

```
// Firebase Console のシミュレーター実行例
リクエスト: read
コレクション: /users/user123
認証ユーザーID: user123
結果: ✅ Allow
```

### Firebase Authentication の状態確認

クライアント側でユーザーが正しく[認証](/glossary/認証/)されているか確認します。[認証](/glossary/認証/)されていないユーザーでも [SDK](/glossary/sdk/) が[リクエスト](/glossary/リクエスト/)を送信してしまい、401 が返される場合があります。

```javascript
firebase.auth().onAuthStateChanged((user) => {
  if (user) {
    console.log('User authenticated:', user.uid);
  } else {
    console.log('No user authenticated');
    // ここで 401 が出ている場合が多い
  }
});
```

### REST API の Authorization ヘッダー形式

Firebase [REST](/glossary/rest/) [API](/glossary/api/) を直接呼び出す場合、Authorization [ヘッダー](/glossary/ヘッダー/)のフォーマットが正確でないと 401 が返されます。

```bash
# 正しい形式
curl -H "Authorization: Bearer <ID_TOKEN>" \
  https://firestore.googleapis.com/v1/projects/<project-id>/databases/(default)/documents/users

# 誤った形式（スペース忘れなど）
curl -H "Authorization:Bearer <ID_TOKEN>" \
  # ❌ スペースなし
```

## それでも解決しない場合

### ログの確認方法

Firebase Console の「[ログ](/glossary/ログ/)」セクション、または Cloud Logging で詳細な[エラーメッセージ](/glossary/エラーメッセージ/)を確認します。

```bash
# gcloud CLI で Firestore アクセスログを確認
gcloud logging read "resource.type=cloud_firestore_instance" --limit=50 --format=json

# Cloud Functions のログを確認
gcloud functions log read <function-name> --limit=50
```

### デバッグ用のセキュリティルール（開発環境のみ）

本番環境では使用禁止ですが、開発中の一時的な[デバッグ](/glossary/デバッグ/)には以下のルールが有効です。

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /{document=**} {
      allow read, write: if request.auth != null; // 開発環境デバッグ用
    }
  }
}
```

### 公式ドキュメント参照

- [Cloud Firestore セキュリティルール](https://firebase.google.com/docs/firestore/security/get-started)
- [Firebase Authentication トークンの管理](https://firebase.google.com/docs/auth/admin/manage-sessions)
- [Service Account キーの管理](https://cloud.google.com/iam/docs/keys-create-delete)

### コミュニティリソース

Firebase コミュニティ StackOverflow の `firebase` タグ、または [firebase-tools GitHub Issues](https://github.com/firebase/firebase-tools/issues) で同様の事例を検索し、解決策を参照することをお勧めします。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*