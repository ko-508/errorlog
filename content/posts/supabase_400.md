---
title: "Supabase の 400 エラー：原因と解決策"
date: 2026-06-03
description: "Supabase APIへのリクエストの形式または内容に誤りがある。Supabase 400 エラーの原因と解決策を解説します。"
tags: ["Supabase"]
errorCode: "400"
---
## エラーの概要

Supabase の 400 エラーは、[API](/glossary/api/) への[リクエスト](/glossary/リクエスト/)の形式または内容に誤りがあることを示します。PostgREST [クエリ](/glossary/クエリ/)のフィルタ構文の誤り、必須[ヘッダー](/glossary/ヘッダー/)の不足、[認証](/glossary/認証/) [API](/glossary/api/) [パラメータ](/glossary/パラメータ/)の型ミスなど、クライアント側の問題が主な原因です。このエラーが返された場合、[リクエスト](/glossary/リクエスト/)自体を修正する必要があり、サーバーの状態ではなく送信側の実装を見直すべき合図です。

## 実際のエラーメッセージ例

**Supabase JavaScript クライアントでの例：**

```json
{
  "error": "400 Bad Request",
  "message": "Invalid filter: Column 'user_id' must use one of the following operators: eq, neq, gt, gte, lt, lte, like, ilike, is, in, cs, cd, sl, sr, nxl, nxr, adj, not, or, and",
  "status": 400
}
```

**cURL での直接[リクエスト](/glossary/リクエスト/)例：**

```bash
curl -X GET "https://<your-project>.supabase.co/rest/v1/users?status=eq.active&age=gt.25" \
  -H "apikey: <your-api-key>" \
  -H "Content-Type: application/json"
```

上記のように正しいフィルタ構文を使用しない場合、400 が返ります。

## よくある原因と解決手順

### 原因 1：PostgREST フィルタ構文の誤り

Supabase は PostgreSQL の高度なフィルタリング機能を提供していますが、正しい演算子と記号を使わなければ 400 エラーが返ります。`>` や `<` などの SQL 記号をそのまま[クエリ](/glossary/クエリ/)に含めると、URL エンコーディングの問題やパーサーエラーが発生します。

**Before（エラーが起きるコード）：**

```javascript
// ❌ 不正な演算子 > を直接使用
const { data, error } = await supabase
  .from('users')
  .select('*')
  .filter('age > 25');
```

**After（修正後）：**

```javascript
// ✅ 正しい PostgREST 演算子 gt を使用
const { data, error } = await supabase
  .from('users')
  .select('*')
  .gt('age', 25);
```

別の例として、複数条件の指定時に誤った区切り文字を使う場合もあります。

**Before（エラーが起きるコード）：**

```javascript
// ❌ URL クエリパラメータで不正な構文
const { data, error } = await supabase
  .from('posts')
  .select('*')
  .filter('status=published AND user_id=5');
```

**After（修正後）：**

```javascript
// ✅ メソッドチェーンで正しく複数条件を指定
const { data, error } = await supabase
  .from('posts')
  .select('*')
  .eq('status', 'published')
  .eq('user_id', 5);
```

### 原因 2：必須リクエストヘッダーの不足

Supabase [API](/glossary/api/) へのすべての[リクエスト](/glossary/リクエスト/)には `Content-Type` と `apikey` [ヘッダー](/glossary/ヘッダー/)が必須です。特に POST や PATCH [リクエスト](/glossary/リクエスト/)で [JSON](/glossary/json/) ボディを送信する場合、`Content-Type: application/json` を明記しないと 400 が返ります。

**Before（エラーが起きるコード）：**

```bash
# ❌ Content-Type ヘッダーが指定されていない
curl -X POST "https://<your-project>.supabase.co/rest/v1/users" \
  -H "apikey: <your-api-key>" \
  -d '{"name":"John","email":"john@example.com"}'
```

**After（修正後）：**

```bash
# ✅ Content-Type を明示的に指定
curl -X POST "https://<your-project>.supabase.co/rest/v1/users" \
  -H "apikey: <your-api-key>" \
  -H "Content-Type: application/json" \
  -d '{"name":"John","email":"john@example.com"}'
```

JavaScript クライアントライブラリを使う場合は、通常自動的に[ヘッダー](/glossary/ヘッダー/)が付与されます。

**Before（エラーが起きるコード）：**

```javascript
// ❌ 標準 fetch API 使用時、ヘッダーが省略されている
const response = await fetch('https://<your-project>.supabase.co/rest/v1/users', {
  method: 'POST',
  body: JSON.stringify({ name: 'John', email: 'john@example.com' })
});
```

**After（修正後）：**

```javascript
// ✅ Supabase クライアントを使用するか、明示的にヘッダー指定
const response = await fetch('https://<your-project>.supabase.co/rest/v1/users', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'apikey': '<your-api-key>'
  },
  body: JSON.stringify({ name: 'John', email: 'john@example.com' })
});
```

### 原因 3：Auth API パラメータの型ミスまたは無効な値

Supabase Auth [API](/glossary/api/)（ユーザー登録・ログイン）では、メールアドレスやパスワード、その他メタデータの[パラメータ](/glossary/パラメータ/)が厳密に検証されます。必須フィールドが欠けていたり、データ型が違ったり、無効な形式だったりすると 400 が返ります。

**Before（エラーが起きるコード）：**

```javascript
// ❌ パスワードが 6 文字未満、またはメールアドレスの形式が不正
const { data, error } = await supabase.auth.signUp({
  email: 'invalid-email',
  password: '12345'
});

if (error) {
  console.log('400 エラー:', error.message);
}
```

**After（修正後）：**

```javascript
// ✅ 正しい形式でパラメータを指定（デフォルトでは 6 文字以上のパスワード）
const { data, error } = await supabase.auth.signUp({
  email: 'user@example.com',
  password: 'secure-password-123'
});

if (error) {
  console.log('エラー:', error.message);
}
```

メタデータの追加時にオブジェクト以外の値を渡す場合も同様です。

**Before（エラーが起きるコード）：**

```javascript
// ❌ user_metadata が文字列で指定されている
const { data, error } = await supabase.auth.signUp({
  email: 'user@example.com',
  password: 'secure-password-123',
  options: {
    data: 'invalid-metadata'  // ❌ 文字列ではなくオブジェクト必須
  }
});
```

**After（修正後）：**

```javascript
// ✅ user_metadata をオブジェクトで指定
const { data, error } = await supabase.auth.signUp({
  email: 'user@example.com',
  password: 'secure-password-123',
  options: {
    data: { role: 'user', company: 'ACME Inc' }  // ✅ オブジェクト形式
  }
});
```

## ツール固有の注意点

Supabase は[エラーレスポンス](/glossary/エラーレスポンス/)の `message` フィールドに詳細な情報を含めます。400 エラーが返された場合、その message を確認することが問題解決の第一歩です。例えば「Invalid filter」と明記されれば PostgREST フィルタの誤り、「Invalid credentials」なら[認証](/glossary/認証/)[パラメータ](/glossary/パラメータ/)の誤りなど、原因が特定しやすくなります。

また、Supabase ダッシュボードの「Table Editor」機能を活用して、[クエリ](/glossary/クエリ/)を直接ブラウザで試すことで、フィルタ構文の正確さを確認できます。正しく動作する[クエリ](/glossary/クエリ/)がダッシュボードで作成できれば、それと同じロジックをコード側に実装することで 400 エラーを防げます。

さらに、JavaScript クライアントライブラリは頻繁に更新されており、古いバージョンを使用していると [API](/glossary/api/) の変更に追従できず、正規の[リクエスト](/glossary/リクエスト/)まで 400 が返されることがあります。`npm install @supabase/supabase-js@latest` で常に最新版を保つようにしてください。

## それでも解決しない場合

まずはブラウザーの開発者ツール（F12）のネットワークタブで、実際に送信されているリクエストヘッダーと URL を確認します。Supabase ダッシュボードの「Logs」セクションでは、[API](/glossary/api/) に到達した[リクエスト](/glossary/リクエスト/)の詳細[ログ](/glossary/ログ/)が記録されており、どの部分が不正と判定されたかを追跡できます。

以下のコマンドで、[リクエスト](/glossary/リクエスト/)の詳細を verbose モードで確認することも有効です。

```bash
curl -v -X GET "https://<your-project>.supabase.co/rest/v1/users?status=eq.active" \
  -H "apikey: <your-api-key>" \
  -H "Content-Type: application/json"
```

`-v` フラグにより、送受信される[ヘッダー](/glossary/ヘッダー/)と[レスポンス](/glossary/レスポンス/)全体が表示されます。

また、Supabase の公式ドキュメント（https://supabase.com/docs/reference/javascript/select）で PostgREST フィルタ演算子の完全なリストを確認し、使用している演算子が正しいものであることを再度確認してください。Auth [API](/glossary/api/) の[パラメータ](/glossary/パラメータ/)についても公式リファレンス（https://supabase.com/docs/reference/javascript/auth-signup）で仕様を熟読することで、型や形式の誤りを防げます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*