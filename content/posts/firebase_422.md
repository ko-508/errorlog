---
title: "Firebase の 422 エラー：原因と解決策"
date: 2026-05-24
description: "Firebase で 422 エラーが返される場合、HTTP リクエスト自体は正しい形式ですが、送信されたデータが Firebase のセキュリティルールまたは検証ルールを満たしていないことを意味します。"
tags: ["Firebase"]
errorCode: "422"
lastmod: 2026-05-29
---

## エラーの概要

Firebase で 422 エラーが返される場合、[HTTP](/glossary/http/) [リクエスト](/glossary/リクエスト/)自体は正しい形式ですが、送信されたデータが Firebase のセキュリティルールまたは検証ルールを満たしていないことを意味します。Realtime Database、Cloud Firestore、Authentication、Cloud Functions など複数のサービスで発生する可能性があり、データベースのルール違反やスキーマ検証エラーが主な原因です。

## 実際のエラーメッセージ例

Realtime Database の [REST](/glossary/rest/) [API](/glossary/api/) から返されるエラー：

```json
{
  "error": "Permission denied",
  "code": 422,
  "message": "The data written does not comply with the security rules defined in your database"
}
```

Cloud Firestore [SDK](/glossary/sdk/) (JavaScript) でのエラー：

```
FirebaseError: [firestore/permission-denied]: Missing or insufficient permissions.
(code: 422)
```

## よくある原因と解決手順

### 原因1：Realtime Database のセキュリティルール違反

なぜ発生するかというと、Firebase Realtime Database では `.write` や `.validate` ルールで書き込み権限やデータ形式を厳密に定義しており、これを満たさないデータを送信すると 422 エラーが返されます。

**Before（エラーが起きる設定）**

```json
{
  "rules": {
    "users": {
      "$uid": {
        ".write": "$uid === auth.uid",
        ".validate": "newData.hasChildren(['name', 'email', 'age'])"
      }
    }
  }
}
```

上記のルール下で、必須フィールド `age` を含めずにデータを書き込もうとします：

```javascript
firebase.database().ref('users/' + uid).set({
  name: 'Taro',
  email: 'taro@example.com'
  // age フィールドが不足している
});
```

**After（修正後）**

```javascript
firebase.database().ref('users/' + uid).set({
  name: 'Taro',
  email: 'taro@example.com',
  age: 25  // 必須フィールドを追加
});
```

### 原因2：Cloud Firestore のドキュメントスキーマ検証エラー

Firestore でセキュリティルールに `allow write if request.resource.data.keys().hasAll(['requiredField'])` のような検証を設定している場合、要求されるフィールドが不足していると 422 エラーが返されます。

**Before（エラーが起きるコード）**

```yaml
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /products/{document=**} {
      allow write if request.resource.data.keys().hasAll(['name', 'price', 'category']);
    }
  }
}
```

```javascript
await db.collection('products').add({
  name: 'Widget',
  price: 1000
  // category が不足
});
```

**After（修正後）**

```javascript
await db.collection('products').add({
  name: 'Widget',
  price: 1000,
  category: 'Electronics'  // 必須フィールドを追加
});
```

### 原因3：Firebase Authentication の入力値検証エラー

Firebase Authentication では、メールアドレスやパスワードの形式、長さが検証されており、これを満たさないと 422 エラーが返されることがあります。特にカスタム[認証](/glossary/認証/)[トークン](/glossary/トークン/)や弱いパスワード設定で発生します。

**Before（エラーが起きるコード）**

```javascript
firebase.auth().createUserWithEmailAndPassword(
  'invalid-email',  // メールアドレスとして不正な形式
  '123'  // パスワードが短すぎる（最小6文字）
).catch(error => console.error(error));
```

**After（修正後）**

```javascript
firebase.auth().createUserWithEmailAndPassword(
  'user@example.com',  // 正しいメールアドレス形式
  'SecurePassword123'  // 最小6文字以上
).catch(error => console.error(error));
```

## ツール固有の注意点

### Realtime Database の REST API 使用時

[REST](/glossary/rest/) [API](/glossary/api/) で直接書き込む場合、`Content-Type: application/json` [ヘッダー](/glossary/ヘッダー/)が正しく設定されていないと 422 が返ることがあります。また、`.validate` ルールで `newData.isNumber()` や `newData.isString()` のようなデータ型チェックが厳密に定義されている場合、型が一致しないデータを送信すると即座にエラーが返されます。

```bash
# Before: ヘッダーなしで送信（エラーが出やすい）
curl -X PUT https://<your-project>.firebaseio.com/users/user1.json -d '{"name":"Taro"}'

# After: 正しいヘッダーとデータ型で送信
curl -X PUT https://<your-project>.firebaseio.com/users/user1.json \
  -H "Content-Type: application/json" \
  -d '{"name":"Taro","age":25}'
```

### Cloud Functions でのバリデーション

Cloud Functions から Firestore にデータを書き込む場合、関数内で入力値のバリデーションが不十分だと、ルール検証で 422 が返されます。関数側で事前に値を検証することが重要です。

```javascript
// Before: バリデーションなしで書き込み
exports.createUser = functions.https.onCall(async (data) => {
  await admin.firestore().collection('users').add(data);
});

// After: 事前にバリデーション
exports.createUser = functions.https.onCall(async (data) => {
  if (!data.email || !data.email.includes('@')) {
    throw new functions.https.HttpsError('invalid-argument', 'Invalid email');
  }
  if (!data.name || data.name.length < 2) {
    throw new functions.https.HttpsError('invalid-argument', 'Name too short');
  }
  await admin.firestore().collection('users').add(data);
});
```

## それでも解決しない場合

### デバッグ手順

Firebase Console のセキュリティルールタブでシミュレーター機能を使い、実際の書き込み[リクエスト](/glossary/リクエスト/)をテストしましょう。ここで「許可」か「拒否」かが明確に表示され、拒否理由も確認できます。

ローカル環境では Firebase Emulator Suite を起動して、ルール違反の詳細ログを確認します：

```bash
firebase emulators:start --inspect-functions
```

### 確認すべきログ

Cloud Functions のログは Google Cloud Console で以下のパスで確認できます：
- **Cloud Logging** > **ログエクスプローラー** > `resource.type="cloud_function"`

Realtime Database の書き込み失敗ログは Firebase Console の **Realtime Database** > **ルール** > **シミュレーター** で再現テストを実施できます。

### 公式ドキュメント参照

- [Realtime Database セキュリティルール](https://firebase.google.com/docs/database/security?hl=ja)
- [Cloud Firestore セキュリティルール](https://firebase.google.com/docs/firestore/security?hl=ja)
- [Firebase Authentication のベストプラクティス](https://firebase.google.com/docs/auth/best-practices?hl=ja)

### コミュニティリソース

Firebase の公式 GitHub [リポジトリ](/glossary/リポジトリ/)で同様のイシューが報告されていないか確認してください：https://github.com/firebase/firebase-js-sdk/issues

Stack Overflow の `firebase` タグで過去の質問を検索することも有効です。特に「422 validation」や「security rules validation error」で検索すると、具体的な解決事例が見つかりやすいです。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*