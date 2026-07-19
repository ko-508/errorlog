---
draft: true
title: "Supabase の 422 エラー：原因と解決策"
date: 2026-06-05
description: "リクエストのデータが検証ルールを満たしていない"
tags: ["Supabase"]
errorCode: "422"
service: "Supabase"
error_type: "422"
components: ["Auth"]
related_services: ["JavaScript", "REST API", "SendGrid", "Mailgun", "Gmail"]
---
## エラーの概要

Supabaseの422[エラー](/glossary/エラー/)は「Unprocessable Entity」を意味し、[リクエスト](/glossary/リクエスト/)の構文は正しいものの、[サーバー](/glossary/サーバー/)がデータの検証ルール違反を検出したときに発生します。Supabaseの[認証](/glossary/認証/)（Auth）機能では、[パスワード](/glossary/パスワード/)やメールアドレスの形式チェック、カスタムSMTP設定の検証で特に頻繁に見られます。この[エラー](/glossary/エラー/)が返されると、ユーザー登録や[パスワード](/glossary/パスワード/)変更などの認証処理が失敗します。

## 実際のエラーメッセージ例

Supabase JavaScript[クライアント](/glossary/クライアント/)から返される[エラーレスポンス](/glossary/エラーレスポンス/)：

```json
{
  "error": "invalid_grant",
  "error_description": "Invalid login credentials",
  "status": 422
}
```

または[REST](/glossary/rest/) [API](/glossary/api/)を直接呼び出した場合：

```json
{
  "code": "422",
  "message": "Validation failed",
  "details": "Password should be at least 6 characters"
}
```

## よくある原因と解決手順

### 原因1：パスワードが最低文字数を満たしていない

Supabaseのデフォルト設定では、[パスワード](/glossary/パスワード/)は**最低6文字以上**である必要があります。これより短い[パスワード](/glossary/パスワード/)でユーザー登録や[パスワード](/glossary/パスワード/)変更を試みると、422[エラー](/glossary/エラー/)が返されます。ユーザー入力の検証を行わずに[API](/glossary/api/)に送信している場合に発生することが多いです。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
const { data, error } = await supabase.auth.signUp({
  email: 'user@example.com',
  password: '12345'  // 5文字 - 最低要件を満たさない
});

if (error) {
  console.error('422エラー:', error.message);
}
```

**After（修正後）：**

```javascript
const password = 'secure_password_123';  // 6文字以上

if (password.length < 6) {
  console.error('パスワードは最低6文字以上である必要があります');
  return;
}

const { data, error } = await supabase.auth.signUp({
  email: 'user@example.com',
  password: password
});

if (error) {
  console.error('認証エラー:', error.message);
}
```

### 原因2：メールアドレスの形式が不正

Supabaseは送信前にメールアドレス形式を厳密に検証します。スペースが含まれている、@記号が複数ある、[ドメイン](/glossary/ドメイン/)部分が不完全など、[RFC](/glossary/rfc/) 5322標準から外れたアドレス形式では422[エラー](/glossary/エラー/)が発生します。ユーザー入力を整形せずに送信している場合や、テストデータに誤りがある場合に多く見られます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
const email = 'user @example.com';  // スペースを含む不正な形式

const { data, error } = await supabase.auth.signUp({
  email: email,
  password: 'secure_password_123'
});

if (error) {
  console.error('422エラー:', error.message);
}
```

**After（修正後）：**

```javascript
const email = 'user@example.com'.trim().toLowerCase();  // 前後のスペース削除と小文字化

const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
if (!emailRegex.test(email)) {
  console.error('メールアドレス形式が不正です');
  return;
}

const { data, error } = await supabase.auth.signUp({
  email: email,
  password: 'secure_password_123'
});

if (error) {
  console.error('認証エラー:', error.message);
}
```

### 原因3：Supabase AuthのカスタムSMTP設定またはメールテンプレート設定に問題がある

Supabase Dashboardでカスタムメールプロバイダー（SendGrid、Mailgun等）を設定した場合、認証情報の誤り、テンプレート[変数](/glossary/変数/)の不一致、またはメール送信設定の検証ルール違反で422[エラー](/glossary/エラー/)が発生することがあります。特に[環境変数](/glossary/環境変数/)の値が不完全であったり、テンプレート内の[変数](/glossary/変数/)が不正な形式である場合に顕著です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
# Supabase Authのカスタムメール設定（不正な例）
SMTP_HOST: smtp.gmail.com
SMTP_PORT: 587
SMTP_USER: <incomplete-email>  # 値が不完全
SMTP_PASS: 
# パスワードが空

SMTP_FROM_EMAIL: noreply@example.com
SMTP_FROM_NAME: MyApp

# メールテンプレートの確認漏れ
# パスワードリセットテンプレートに {{ .ConfirmationURL }} が含まれていない
```

**After（修正後）：**

```yaml
# 修正後のカスタムメール設定（正規の例）
SMTP_HOST: smtp.gmail.com
SMTP_PORT: 587
SMTP_USER: your-email@gmail.com
SMTP_PASS: your-app-password  # App PasswordまたはOAuth認証を使用

SMTP_FROM_EMAIL: noreply@example.com
SMTP_FROM_NAME: MyApp

# メールテンプレートの例（確認メールテンプレート）
# メール本文に必須変数 {{ .ConfirmationURL }} を含める
<h1>メール認証</h1>
<p>以下のリンクをクリックして認証を完了してください。</p>
<a href="{{ .ConfirmationURL }}">認証リンク</a>
```

またはJavaScriptでメール検証設定を確認する場合：

```javascript
// Supabaseクライアント初期化時に認証設定を確認
const supabase = createClient(
  '<your-project-url>',
  '<your-anon-key>',
  {
    auth: {
      autoRefreshToken: true,
      persistSession: true,
      // メールプロバイダーが正しく設定されているか確認
    }
  }
);

// ユーザー登録前にメール設定の妥当性をチェック
const { data, error } = await supabase.auth.signUp({
  email: 'test@example.com',
  password: 'valid_password_123'
  // ここでエラーが返される場合、Dashboard設定を再確認
});
```

## ツール固有の注意点

Supabaseの422[エラー](/glossary/エラー/)は**プロジェクト設定の違いで挙動が異なります**。以下の点を確認してください。

**Authentication > Providers > メール設定の確認：**
Supabase Dashboardの「Authentication」→「Providers」→「Email」で、以下の項目を確認しましょう。
- 「Confirm email」が有効になっている場合、メールアドレス形式の検証がより厳密になります。
- 「Double confirm change」を有効にしている場合、メール変更時の追加検証が動作します。

**カスタムSMTP vs Supabase標準メール：**
Supabaseの標準メール機能を使用している場合、制限が異なります。SendGridやMailgunなどを統合している場合は、各プロバイダー側の検証ルールも確認が必要です。

**パスワードポリシーの設定：**
Supabase Dashboardの「Authentication」→「Policies」で、[パスワード](/glossary/パスワード/)の最小文字数、複雑性要件、有効期限などをカスタマイズできます。デフォルトより厳しい設定にしている場合は、そのルールに合わせた[バリデーション](/glossary/バリデーション/)を[フロントエンド](/glossary/フロントエンド/)に実装してください。

```javascript
// ダッシュボード設定に基づいてバリデーション関数を作成
const validatePassword = (password) => {
  const minLength = 6;  // デフォルト設定
  const hasNumber = /\d/.test(password);
  const hasSpecialChar = /[!@#$%^&*]/.test(password);
  
  if (password.length < minLength) {
    return { valid: false, message: `最低${minLength}文字必要です` };
  }
  // カスタムポリシーに合わせて条件を追加
  return { valid: true };
};
```

## それでも解決しない場合

**Supabase Logsの確認：**
Supabase Dashboardの「Logs」セクションで、[リアルタイム](/glossary/リアルタイム/)の[エラーログ](/glossary/エラーログ/)を確認できます。`Status: 422`でフィルタリングすると、詳細な[エラーメッセージ](/glossary/エラーメッセージ/)が表示されます。

**[REST](/glossary/rest/) [API](/glossary/api/)での詳細な[デバッグ](/glossary/デバッグ/)：**

```bash
# curlコマンドでメール検証エラーの詳細を確認
curl -X POST 'https://<your-project-ref>.supabase.co/auth/v1/signup' \
  -H 'apikey: <your-anon-key>' \
  -H 'Content-Type: application/json' \
  -d '{
    "email": "test@example.com",
    "password": "short"
  }' \
  -w '\nStatus: %{http_code}\n'

# レスポンスに詳細なエラー理由が含まれます
```

**公式リソースへのアクセス：**
- [Supabase Auth Documentation](https://supabase.com/docs/guides/auth)
- [Supabase メール設定ガイド](https://supabase.com/docs/guides/auth/auth-smtp)
- [Supabase GitHub Issues](https://github.com/supabase/supabase/issues)

プロジェクト設定や[API](/glossary/api/)キーに関わる部分は、Supabaseサポートに直接問い合わせることも有効です。Dashboardの「Help」→「Support」から公式サポートチャネルにアクセスできます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*