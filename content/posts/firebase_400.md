---
title: "Firebase の 400 エラー：原因と解決策"
date: 2026-01-01
description: "Firebase の 400 エラーは、クライアントからのリクエストが不正な形式または無効なパラメータを含んでいることを示します。"
tags: ["Firebase"]
errorCode: "400"
lastmod: 2026-06-05
service: "Firebase"
error_type: "400"
components: ["Firestore", "Auth", "Realtime Database"]
related_services: ["SDK", "REST API", "JavaScript SDK"]
---

## エラーの概要

Firebase の 400 [エラー](/glossary/エラー/)は、クライアント（使用しているアプリケーション）から送信された[リクエスト](/glossary/リクエスト/)が不正な形式または無効な[パラメータ](/glossary/パラメータ/)を含んでいることを示します。この[エラー](/glossary/エラー/)は[サーバー](/glossary/サーバー/)側の障害ではなく、送信されたデータの形式、認証情報、[クエリ](/glossary/クエリ/)条件、または[リクエスト](/glossary/リクエスト/)[ヘッダー](/glossary/ヘッダー/)に問題があることを意味します。Firebase を使用する際に最も頻繁に遭遇する[エラー](/glossary/エラー/)の一つであり、原因の特定と修正が必須です。

## 実際のエラーメッセージ例

Firebase [SDK](/glossary/sdk/)（ソフトウェア開発キット）からの典型的な[エラーレスポンス](/glossary/エラーレスポンス/)は以下のような形式です。

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

[REST](/glossary/rest/) [API](/glossary/api/)（外部サービスとのやり取り口）呼び出しの場合：

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

Firestore では、複数フィールドに対する複合フィルタリング条件がある場合、事前に[インデックス](/glossary/インデックス/)（[データベース](/glossary/データベース/)の検索最適化機能）を作成する必要があります。また、2 つ以上のフィールドで不等式フィルタ（`<`, `>`, `<=`, `>=`）を使用することはできません。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

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

複合フィルタが必要な場合は、Firebase [コンソール](/glossary/コンソール/)（管理画面）から自動提示される[インデックス](/glossary/インデックス/)を作成します。

### 原因2：認証情報の形式が無効

Firebase Authentication（ユーザー認証機能）で不正な形式のメールアドレスや[パスワード](/glossary/パスワード/)、または[認証](/glossary/認証/)[トークン](/glossary/トークン/)（[認証](/glossary/認証/)に用いる[暗号化](/glossary/暗号化/)されたデータ）が渡された場合に 400 [エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
firebase.auth().createUserWithEmailAndPassword('user@', 'password123')
  .catch(error => console.error(error));
```

**After（修正後）：**

```javascript
firebase.auth().createUserWithEmailAndPassword('user@example.com', 'password123')
  .catch(error => console.error(error));
```

[パスワード](/glossary/パスワード/)は最低 6 文字である必要があります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

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

Firestore や Realtime Database へのデータ書き込み時に、期待される型と異なるデータ型が渡されると 400 [エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

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

循環参照（あるデータが自分自身を参照すること）を含むオブジェクトも不正です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

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

Firebase [REST](/glossary/rest/) [API](/glossary/api/)（外部からの[通信](/glossary/通信/)インターフェース）を直接呼び出す場合、Content-Type [ヘッダー](/glossary/ヘッダー/)（データ形式を指定する設定）や[認証](/glossary/認証/)[ヘッダー](/glossary/ヘッダー/)が不正だと 400 [エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

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

ドキュメント ID として使用できない文字列（スラッシュなど）を含む場合、400 [エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
db.collection('users').doc('user/123').set({ name: 'John' });
```

**After（修正後）：**

```javascript
db.collection('users').doc('user_123').set({ name: 'John' });
```