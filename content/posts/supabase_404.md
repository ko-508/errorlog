---
draft: true
title: "Supabase の 404 エラー：原因と解決策"
date: 2026-06-04
description: "指定したテーブル・行・ストレージオブジェクトが見つからない"
tags: ["Supabase"]
errorCode: "404"
service: "Supabase"
error_type: "404"
components: ["Storage", "Functions", "Dashboard"]
related_services: ["JavaScript"]
---
## エラーの概要

Supabase の 404 [エラー](/glossary/エラー/)は、クライアント側からの[リクエスト](/glossary/リクエスト/)が指定した[テーブル](/glossary/テーブル/)・行・ストレージオブジェクト・Functions [エンドポイント](/glossary/エンドポイント/)が見つからないことを示します。[データベース](/glossary/データベース/)操作、ファイルアップロード、カスタム関数呼び出しなどの様々な場面で発生し、多くの場合はリソース名の指定ミスが原因です。

## 実際のエラーメッセージ例

**データベースクエリでの 404 [エラー](/glossary/エラー/)：**

```json
{
  "code": "404",
  "message": "Not Found",
  "hint": "The resource you are requesting does not exist. It may have been deleted or the table name might be incorrect.",
  "details": null
}
```

**ストレージ操作での 404 [エラー](/glossary/エラー/)：**

```json
{
  "statusCode": 404,
  "error": "NotFound",
  "message": "The resource was not found"
}
```

**JavaScript クライアントコンソール出力：**

```bash
Error: Failed to fetch
TypeError: 404 Not Found
```

## よくある原因と解決手順

### 原因1：テーブル名の綴りミスまたは大文字小文字の混在

Supabase の[テーブル](/glossary/テーブル/)名は大文字小文字を区別します。[データベース](/glossary/データベース/)に `users` [テーブル](/glossary/テーブル/)が存在しても、`Users` や `USERS` で[クエリ](/glossary/クエリ/)を実行すると 404 [エラー](/glossary/エラー/)が発生します。また、[テーブル](/glossary/テーブル/)名にタイポがあると同様の結果になります。

**修正前（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
const { data, error } = await supabase
  .from('Users')  // テーブル名が大文字で始まっている
  .select('*')
  .eq('id', 1);

if (error) {
  console.log('エラー:', error.message);  // 404 Not Found
}
```

**修正後：**

```javascript
const { data, error } = await supabase
  .from('users')  // 正確なテーブル名に統一
  .select('*')
  .eq('id', 1);

if (error) {
  console.log('エラー:', error.message);
} else {
  console.log('取得データ:', data);
}
```

Supabase Dashboard のテーブルエディタで表示されている正確な[テーブル](/glossary/テーブル/)名をコピーして使用することで、この問題を確実に回避できます。

### 原因2：ストレージのバケット名またはファイルパスの誤指定

Storage [オブジェクト](/glossary/オブジェクト/)を[ダウンロード](/glossary/ダウンロード/)・削除する際に、[バケット](/glossary/バケット/)名やファイルパスの指定が間違っていると 404 が返されます。パスの先頭スラッシュの有無や、ネストされたフォルダー構造の指定ミスもよくある原因です。

**修正前（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
// バケット名またはパスが誤っている
const { data, error } = await supabase
  .storage
  .from('avatars')  // バケット名が異なる可能性
  .download('user-123/profile.jpg');  // ファイルパスが存在しない

if (error) {
  console.log('ダウンロードエラー:', error.message);  // 404 Not Found
}
```

**修正後：**

```javascript
// Supabase Dashboard の Storage 画面で確認したバケット名とパスを使用
const { data, error } = await supabase
  .storage
  .from('profile-pictures')  // 正確なバケット名
  .download('users/user-123/profile.jpg');  // 実際に存在するパス

if (error) {
  console.log('ダウンロードエラー:', error.message);
} else {
  console.log('ファイル取得成功:', data);
}
```

Dashboard の Storage セクションで[バケット](/glossary/バケット/)一覧を開き、各[バケット](/glossary/バケット/)内のファイル構造を確認すると、正確なパスを特定できます。

### 原因3：Supabase Functions エンドポイントの URL が不正確

カスタム関数を呼び出す際に、[エンドポイント](/glossary/エンドポイント/) URL が完全でない、または関数名を誤って指定した場合に 404 が発生します。特にローカル開発環境とプロダクション環境で[エンドポイント](/glossary/エンドポイント/)が異なることに気づかずミスが起きます。

**修正前（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
// 不完全な URL またはローカル環境での不正確なエンドポイント
const response = await fetch('http://localhost:54321/functions/v1/send-email', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${supabase.auth.session().access_token}`,
  },
  body: JSON.stringify({ email: 'user@example.com' }),
});

if (!response.ok) {
  console.log('Functions エラー:', response.status);  // 404
}
```

**修正後：**

```javascript
// Supabase Dashboard の Functions 一覧からコピーしたエンドポイントを使用
const functionUrl = 'https://<your-project-id>.supabase.co/functions/v1/send-email';

const response = await fetch(functionUrl, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${(await supabase.auth.getSession()).data.session.access_token}`,
  },
  body: JSON.stringify({ email: 'user@example.com' }),
});

if (!response.ok) {
  console.log('Functions エラー:', response.status);
} else {
  const result = await response.json();
  console.log('実行結果:', result);
}
```

プロジェクトの Functions セクションにアクセスし、対象の関数をクリックすると、[デプロイ](/glossary/デプロイ/)済み[エンドポイント](/glossary/エンドポイント/)の正確な URL が表示されます。

## Supabase 固有の注意点

Supabase は PostgreSQL [データベース](/glossary/データベース/)をラッパーしているため、行レベルセキュリティ（RLS）が有効な[テーブル](/glossary/テーブル/)では、[認証](/glossary/認証/)ユーザーでも[アクセス権限](/glossary/アクセス権限/)がないと[クエリ](/glossary/クエリ/)結果が空になり、実質的に 404 と同じ現象が起きます。この場合、[エラーメッセージ](/glossary/エラーメッセージ/)は返されず `data: []` または `data: null` が返されるため、[テーブル](/glossary/テーブル/)名やカラム名が正確でもデータが取得できません。RLS ルールと認証状態を確認してください。

また、Supabase Functions をローカルで開発する際は、`supabase start` [コマンド](/glossary/コマンド/)で起動したローカルエミュレーター の[ポート](/glossary/ポート/)番号（通常は 54321）が実行環境によって変わることがあります。本番環境に[デプロイ](/glossary/デプロイ/)する前に、必ず[ダッシュボード](/glossary/ダッシュボード/)上の実際の[エンドポイント](/glossary/エンドポイント/) URL で動作確認を行ってください。

Storage の[バケット](/glossary/バケット/)削除後に古い[バケット](/glossary/バケット/)名で[リクエスト](/glossary/リクエスト/)を送ると 404 が返されます。[バケット](/glossary/バケット/)を再作成した場合、新しい[バケット](/glossary/バケット/)名を明示的に指定する必要があります。

## それでも解決しない場合

以下の手順で[デバッグ](/glossary/デバッグ/)を進めてください。

**Supabase Dashboard での確認：**

1. ページ上部のプロジェクト名をクリックし、[ダッシュボード](/glossary/ダッシュボード/)のホームに戻る
2. 左サイドメニューの「Tables」を開き、[テーブル](/glossary/テーブル/)一覧で対象[テーブル](/glossary/テーブル/)が存在し、正確な名前を確認
3. 「Storage」セクションを開き、[バケット](/glossary/バケット/)一覧とその中身を確認
4. 「Functions」セクションで関数が[デプロイ](/glossary/デプロイ/)済みか、[エンドポイント](/glossary/エンドポイント/) URL が表示されているか確認

**ブラウザの開発者ツールでの[ネットワーク](/glossary/ネットワーク/)確認：**

```bash
# リクエストの詳細を確認
# F12キーで開発者ツール → Network タブを見て、
# 404 を返しているリクエストの URL と Headers、Response を確認
```

**Supabase JavaScript クライアントの[デバッグ](/glossary/デバッグ/)出力：**

```javascript
// クエリ実行前に以下を追加し、実際に送信される SQL を確認
const { data, error } = await supabase
  .from('users')
  .select('*');

console.log('実行 SQL:', supabase.sql);  // 実際のクエリを出力
console.log('エラーオブジェクト:', error);  // 詳細なエラー情報
```

それでも解決しない場合は、Supabase の公式ドキュメント（https://supabase.com/docs）のテーブル、Storage、Functions のセクションを参照するか、GitHub Issues（https://github.com/supabase/supabase）でコミュニティに相談してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*