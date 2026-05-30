---
title: "Firebase の 400 エラー：原因と解決策"
date: 2026-01-01
description: "Firebase の 400 エラーは、クライアントからのリクエストが不正な形式または無効なパラメータを含んでいることを示します。"
tags: ["Firebase"]
errorCode: "400"
lastmod: 2026-05-31
---

## エラーの概要

Firebase の 400 エラーは、クライアントからの[リクエスト](/glossary/リクエスト/)が不正な形式または無効な[パラメータ](/glossary/パラメータ/)を含んでいることを示します。このエラーはサーバー側の障害ではなく、送信されたデータの形式、認証情報、クエリ条件、またはリクエストヘッダーに問題があることを意味します。Firebase を使用する際に最も頻繁に遭遇するエラーの一つであり、原因の特定と修正が必須です。

## 実際のエラーメッセージ例

Firebase [SDK](/glossary/sdk/) からの典型的な[エラーレスポンス](/glossary/エラーレスポンス/)は以下のような形式です。

```json
{
  "error": {
    "code": 400,
    "message": "Invalid JSON payload received. Unable to parse the request body.",
    "errors": [
      {
        "domain": "global",
        "reason": "invalidArgument",
        "message": "Invalid JSON payload received. Unable to parse the request body."
      }
    ]
  }
}
```

JavaScript [SDK](/glossary/sdk/) では以下のような[コンソール](/glossary/コンソール/)出力が表示されます。

```
Firebase: Error (auth/invalid-email).
```

[REST](/glossary/rest/) [API](/glossary/api/) 呼び出しの場合：

```
POST /v1/projects/<project-id>/databases/(default)/documents:query
400 Bad Request
{
  "error": {
    "code": 400,
    "message": "Invalid query. Firestore: Inequality filters are limited to at most one field."
  }
}
```

## よくある原因と解決手順

### 原因1：Firestore クエリの複合インデックス不足または複数不等式フィルタ

Firestore では、複数フィールドに対する複合フィルタリング条件がある場合、事前に[インデックス](/glossary/インデックス/)を作成する必要があります。また、2 つ以上のフィールドで不等式フィルタ（`<`, `>`, `<=`, `>=`）を使用することはできません。

**Before（複数フィールドで不等式を使用）：**

```javascript
db.collection('users')
  .where('age', '>', 18)
  .where('score', '<', 100)
  .get();
```

**After（修正後）：**

```javascript
db.collection('users')
  .where('age', '>', 18)
  .where('status', '==', 'active')
  .get();
```

複合フィルタが必要な場合は、Firebase [コンソール](/glossary/コンソール/)から自動提示される[インデックス](/glossary/インデックス/)を作成します。

### 原因2：認証情報の形式が無効

Firebase Authentication で不正な形式のメールアドレスやパスワード、または[認証](/glossary/認証/)[トークン](/glossary/トークン/)が渡された場合に 400 エラーが発生します。

**Before（無効なメールアドレス形式）：**

```javascript
firebase.auth().createUserWithEmailAndPassword('user@', 'password123')
  .catch(error => console.error(error));
```

**After（修正後）：**

```javascript
firebase.auth().createUserWithEmailAndPassword('user@example.com', 'password123')
  .catch(error => console.error(error));
```

パスワードは最低 6 文字である必要があります。

**Before（パスワードが短すぎる）：**

```javascript
firebase.auth().createUserWithEmailAndPassword('user@example.com', '123')
  .catch(error => console.error(error));
```

**After（修正後）：**

```javascript
firebase.auth().createUserWithEmailAndPassword('user@example.com', 'securePassword123')
  .catch(error => console.error(error));
```

### 原因3：SDK メソッドに渡すデータ型が不正

Firestore や Realtime Database へのデータ書き込み時に、期待される型と異なるデータ型が渡されると 400 エラーが発生します。

**Before（undefined を含むオブジェクト）：**

```javascript
const userData = {
  name: 'John',
  email: undefined,
  age: 30
};
db.collection('users').doc('user1').set(userData);
```

**After（修正後）：**

```javascript
const userData = {
  name: 'John',
  email: null,
  age: 30
};
db.collection('users').doc('user1').set(userData);
```

循環参照を含むオブジェクトも不正です。

**Before（循環参照）：**

```javascript
const obj = { name: 'test' };
obj.self = obj;  // 循環参照
db.collection('items').doc('item1').set(obj);
```

**After（修正後）：**

```javascript
const obj = { name: 'test', parent: 'root' };
db.collection('items').doc('item1').set(obj);
```

### 原因4：REST API のリクエストヘッダーが不正

Firebase [REST](/glossary/rest/) [API](/glossary/api/) を直接呼び出す場合、Content-Type [ヘッダー](/glossary/ヘッダー/)や[認証](/glossary/認証/)[ヘッダー](/glossary/ヘッダー/)が不正だと 400 エラーが発生します。

**Before（Content-Type が誤っている）：**

```bash
curl -X POST https://www.googleapis.com/identitytoolkit/v3/relyingparty/signupNewUser \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d '{"email":"user@example.com","password":"password123"}'
```

**After（修正後）：**

```bash
curl -X POST https://www.googleapis.com/identitytoolkit/v3/relyingparty/signupNewUser \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password123","returnSecureToken":true}'
```

### 原因5：Firestore ドキュメント ID の不正な形式

ドキュメント ID として使用できない文字列（スラッシュなど）を含む場合、400 エラーが発生します。

**Before（スラッシュを含むドキュメント ID）：**

```javascript
db.collection('users').doc('user/123').set({ name: 'John' });
```

**After（修正後）：**

```javascript
db.collection('users').doc('user_123').set({ name: 'John' });
```

## Firebase ツール固有の注意点

### Realtime Database でのデータ構造の制限

Realtime Database は [JSON](/glossary/json/) で表現できる値のみをサポートしており、Date オブジェクトなどの JavaScript 固有のオブジェクトを直接書き込むことができません。

**Before（Date オブジェクトを直接書き込み）：**

```javascript
const data = {
  name: 'John',
  createdAt: new Date()
};
db.ref('users/user1').set(data);

// ✅ 修正後：タイムスタンプに変換
const data = {
  name: 'John',
  createdAt: Date.now()
};
db.ref('users/user1').set(data);
```

### Cloud Functions のリクエストボディパース

Cloud Functions の[HTTP](/glossary/http/) トリガーで[リクエストボディ](/glossary/リクエストボディ/)が正しくパースされていない場合も 400 エラーが発生します。Express フレームワークを使用する際は、ボディパーサーミドルウェアを明示的に設定する必要があります。

**Before（ボディパーサーなし）：**

```javascript
const functions = require('firebase-functions');
const express = require('express');
const app = express();

app.post('/api/users', (req, res) => {
  console.log(req.body);  // undefined
  res.send('OK');
});
```

**After（修正後）：**

```javascript
const functions = require('firebase-functions');
const express = require('express');
const app = express();

app.use(express.json());
app.post('/api/users', (req, res) => {
  console.log(req.body);  // 正しくパース済み
  res.send('OK');
});

exports.api = functions.https.onRequest(app);
```

### Security Rules での認証トークン検証

Firebase Security Rules が厳しく設定されている場合、有効な[認証](/glossary/認証/)[トークン](/glossary/トークン/)がない、または期限切れの[トークン](/glossary/トークン/)を使用していると 400 エラーが発生する可能性があります。ID [トークン](/glossary/トークン/)の有効期限は 1 時間であるため、定期的にリフレッシュが必要です。

**After（修正後）：**

```javascript
firebase.auth().currentUser.getIdToken(true)
  .then(idToken => {
    // 最新のトークンを使用
    return db.collection('users').doc('user1').get();
  });
```

## それでも解決しない場合

### デバッグ方法

ブラウザの開発者ツールのネットワークタブで、実際に送信されている[リクエスト](/glossary/リクエスト/)とレスポンスボディを確認します。Firebase [コンソール](/glossary/コンソール/)のログで詳細なエラーメッセージを確認してください。

```bash
# Cloud Functions のログ確認
gcloud functions describe <function-name> --region us-central1
gcloud functions logs read <function-name> --region us-central1 --limit 50
```

### 公式リソース

- [Firebase Authentication エラーコード](https://firebase.google.com/docs/auth/troubleshooting)
- [Firestore クエリの制限とベストプラクティス](https://firebase.google.com/docs/firestore/query-data/queries)
- [Firestore インデックスの作成](https://firebase.google.com/docs/firestore/indexes)
- [Firebase REST API リファレンス](https://firebase.google.com/docs/reference/rest/auth)

### コミュニティリソース

- [Firebase GitHub Issues](https://github.com/firebase/firebase-js-sdk/issues)
- [Stack Overflow の firebase タグ](https://stackoverflow.com/questions/tagged/firebase)
- [Firebase Google グループ](https://groups.google.com/forum/#!forum/firebase-talk)

エラーメッセージの詳細ログを取得し、上記の公式ドキュメントと照合することで、ほとんどの 400 エラーは解決できます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*