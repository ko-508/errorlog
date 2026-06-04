---
title: "Supabase の 404 エラー：原因と解決策"
date: 2026-06-04
description: "指定したテーブル・行・ストレージオブジェクトが見つからない。Supabase 404 エラーの原因と解決策を解説します。"
tags: ["Supabase"]
errorCode: "404"
---
## エラーの概要

Supabase の 404 エラーは、クライアント側からのリクエストが指定したテーブル・行・ストレージオブジェクト・Functions エンドポイントが見つからないことを示します。データベース操作、ファイルアップロード、カスタム関数呼び出しなどの様々な場面で発生し、多くの場合はリソース名の指定ミスが原因です。

## 実際のエラーメッセージ例

**データベースクエリでの 404 エラー：**

```json
{
  "code": "404",
  "message": "Not Found",
  "hint": "The resource you are requesting does not exist. It may have been deleted or the table name might be incorrect.",
  "details": null
}
```

**ストレージ操作での 404 エラー：**

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

Supabase のテーブル名は大文字小文字を区別します。データベースに `users` テーブルが存在しても、`Users` や `USERS` でクエリを実行すると 404 エラーが発生します。また、テーブル名にタイポがあると同様の結果になります。

**修正前（エラーが起きるコード）：**

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

Supabase Dashboard のテーブルエディタで表示されている正確なテーブル名をコピーして使用することで、この問題を確実に回避できます。

### 原因2：ストレージのバケット名またはファイルパスの誤指定

Storage オブジェクトをダウンロード・削除する際に、バケット名やファイルパスの指定が間違っていると 404 が返されます。パスの先頭スラッシュの有無や、ネストされたフォルダー構造の指定ミスもよくある原因です。

**修正前（エラーが起きるコード）：**

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

Dashboard の Storage セクションでバケット一覧を開き、各バケット内のファイル構造を確認すると、正確なパスを特定できます。

### 原因3：Supabase Functions エンドポイントの URL が不正確

カスタム関数を呼び出す際に、エンドポイント URL が完全でない、または関数名を誤って指定した場合に 404 が発生します。特にローカル開発環境とプロダクション環境でエンドポイントが異なることに気づかずミスが起きます。

**修正前（エラーが起きるコード）：**

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

プロジェクトの Functions セクションにアクセスし、対象の関数をクリックすると、デプロイ済みエンドポイントの正確な URL が表示されます。

## Supabase 固有の注意点

Supabase は PostgreSQL データベースをラッパーしているため、行レベルセキュリティ（RLS）が有効なテーブルでは、認証ユーザーでもアクセス権限がないとクエリ結果が空になり、実質的に 404 と同じ現象が起きます。この場合、エラーメッセージは返されず `data: []` または `data: null` が返されるため、テーブル名やカラム名が正確でもデータが取得できません。RLS ルールと認証状態を確認してください。

また、Supabase Functions をローカルで開発する際は、`supabase start` コマンドで起動したローカルエミュレーター のポート番号（通常は 54321）が実行環境によって変わることがあります。本番環境にデプロイする前に、必ずダッシュボード上の実際のエンドポイント URL で動作確認を行ってください。

Storage のバケット削除後に古いバケット名でリクエストを送ると 404 が返されます。バケットを再作成した場合、新しいバケット名を明示的に指定する必要があります。

## それでも解決しない場合

以下の手順でデバッグを進めてください。

**Supabase Dashboard での確認：**

1. ページ上部のプロジェクト名をクリックし、ダッシュボードのホームに戻る
2. 左サイドメニューの「Tables」を開き、テーブル一覧で対象テーブルが存在し、正確な名前を確認
3. 「Storage」セクションを開き、バケット一覧とその中身を確認
4. 「Functions」セクションで関数がデプロイ済みか、エンドポイント URL が表示されているか確認

**ブラウザの開発者ツールでのネットワーク確認：**

```bash
# リクエストの詳細を確認
# F12キーで開発者ツール → Network タブを見て、
# 404 を返しているリクエストの URL と Headers、Response を確認
```

**Supabase JavaScript クライアントのデバッグ出力：**

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