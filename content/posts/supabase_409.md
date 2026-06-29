---
draft: true
title: "Supabase の 409 エラー：原因と解決策"
date: 2026-06-04
description: "データの競合（一意制約違反など）が発生した"
tags: ["Supabase"]
errorCode: "409"
service: "Supabase"
error_type: "409"
components: []
related_services: ["PostgreSQL", "JavaScript"]
---
# Supabase の 409 エラー（Conflict）解説

## エラーの概要

Supabase の 409 [エラー](/glossary/エラー/)は「Conflict（競合）」を意味し、[データベース](/glossary/データベース/)のユニークネス制約や外部キー制約に違反するデータ操作を試みた際に発生します。INSERT や UPDATE 時に PRIMARY KEY の重複、UNIQUE 制約のあるカラムへの重複値挿入、または存在しない親レコードへの参照が行われた場合に返されます。特に複数クライアントからの同時書き込みやバッチ処理で頻発する典型的な[データベース](/glossary/データベース/)競合[エラー](/glossary/エラー/)です。

## 実際のエラーメッセージ例

**[JSON](/glossary/json/) [レスポンス](/glossary/レスポンス/)例：**

```json
{
  "code": "23505",
  "message": "duplicate key value violates unique constraint \"users_email_key\"",
  "details": "Key (email)=(test@example.com) already exists.",
  "hint": null,
  "hint_card": null
}
```

**JavaScript クライアント出力例：**

```javascript
{
  "message": "409 Conflict",
  "details": "duplicate key value violates unique constraint \"products_sku_key\"",
  "status": 409
}
```

## よくある原因と解決手順

### 原因 1：PRIMARY KEY または UNIQUE 制約への重複値挿入

PRIMARY KEY（通常は id）または UNIQUE 制約が付与されたカラムに、既に存在する値を挿入しようとすると競合が発生します。ユーザーのメールアドレスやユーザー名、商品の SKU コードなど、一意性が必要なデータをチェックなしで INSERT した場合に起こります。

**修正前（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
// ユーザーテーブルに既存のメールアドレスで新規挿入しようとする
const { data, error } = await supabase
  .from('users')
  .insert([
    {
      id: 1,
      email: 'duplicate@example.com',
      name: 'John Doe'
    }
  ]);

if (error) {
  console.error('409 Conflict:', error.message);
  // "duplicate key value violates unique constraint \"users_email_key\""
}
```

**修正後：**

```javascript
// UPSERT を使用して重複時は更新、新規時は挿入
const { data, error } = await supabase
  .from('users')
  .upsert(
    [
      {
        id: 1,
        email: 'duplicate@example.com',
        name: 'John Doe'
      }
    ],
    { onConflict: 'email' }
  );

if (error) {
  console.error('Error:', error.message);
} else {
  console.log('Success:', data);
}
```

または、事前にチェックしてから INSERT する方法：

```javascript
// 先に該当データが存在するかチェック
const { data: existingUser, error: selectError } = await supabase
  .from('users')
  .select('id')
  .eq('email', 'duplicate@example.com')
  .single();

if (selectError && selectError.code !== 'PGRST116') {
  console.error('Select error:', selectError);
} else if (existingUser) {
  console.log('User already exists, skipping insert');
} else {
  // 存在しない場合のみ挿入
  const { data, error } = await supabase
    .from('users')
    .insert([
      {
        email: 'duplicate@example.com',
        name: 'John Doe'
      }
    ]);
  
  if (error) console.error('Insert error:', error);
}
```

### 原因 2：外部キー制約の親レコードが存在しない

外部キー制約が設定されているカラムに、参照先[テーブル](/glossary/テーブル/)に存在しないレコードの [ID](/glossary/id/) を挿入しようとした場合に発生します。例えば、orders [テーブル](/glossary/テーブル/)の user_id が users [テーブル](/glossary/テーブル/)に存在しない [ID](/glossary/id/) を指す場合です。

**修正前（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
// 存在しないユーザー ID を参照するオーダーを作成
const { data, error } = await supabase
  .from('orders')
  .insert([
    {
      user_id: 99999,  // このユーザーは存在しない
      product_id: 1,
      quantity: 2
    }
  ]);

if (error) {
  console.error('409 Conflict:', error.message);
  // "insert or update on table \"orders\" violates foreign key constraint \"orders_user_id_fkey\""
}
```

**修正後：**

```javascript
// 先に親レコード（ユーザー）の存在を確認
const { data: userExists, error: checkError } = await supabase
  .from('users')
  .select('id')
  .eq('id', 99999)
  .single();

if (checkError && checkError.code === 'PGRST116') {
  console.error('User not found');
} else if (userExists) {
  // ユーザーが存在する場合のみオーダーを作成
  const { data, error } = await supabase
    .from('orders')
    .insert([
      {
        user_id: 99999,
        product_id: 1,
        quantity: 2
      }
    ]);
  
  if (error) console.error('Insert error:', error);
}
```

### 原因 3：同時書き込みによるトランザクション競合

複数のクライアントが同時に同じレコードを更新した場合、またはバッチ処理中に同じユニークキーを持つレコードが複数回 INSERT される場合に競合します。特にリアルタイムアプリケーションやインポート処理で発生しやすくなります。

**修正前（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
// バッチ処理で複数レコードを一括挿入する際、重複キーがあると競合
const recordsToInsert = [
  { email: 'user1@example.com', name: 'User 1' },
  { email: 'user2@example.com', name: 'User 2' },
  { email: 'user1@example.com', name: 'User 1 Duplicate' }  // 重複キー
];

const { data, error } = await supabase
  .from('users')
  .insert(recordsToInsert);

if (error) {
  console.error('409 Conflict during batch:', error.message);
  // バッチ全体がロールバックされる
}
```

**修正後：**

```javascript
// UPSERT を使用してバッチ処理時の競合を回避
const recordsToInsert = [
  { email: 'user1@example.com', name: 'User 1' },
  { email: 'user2@example.com', name: 'User 2' },
  { email: 'user1@example.com', name: 'User 1 Updated' }
];

const { data, error } = await supabase
  .from('users')
  .upsert(recordsToInsert, { onConflict: 'email' });

if (error) {
  console.error('Error:', error.message);
} else {
  console.log('Batch processed:', data);
}
```

または、事前に重複を削除する方法：

```javascript
// ユニークキーでグループ化して重複を排除
const recordsToInsert = [
  { email: 'user1@example.com', name: 'User 1' },
  { email: 'user2@example.com', name: 'User 2' },
  { email: 'user1@example.com', name: 'User 1 Duplicate' }
];

const uniqueRecords = Array.from(
  new Map(recordsToInsert.map(r => [r.email, r])).values()
);

const { data, error } = await supabase
  .from('users')
  .insert(uniqueRecords);

if (error) console.error('Insert error:', error);
```

## Supabase ツール固有の注意点

**[エラーレスポンス](/glossary/エラーレスポンス/)の details フィールド確認：** Supabase が返す 409 [エラーレスポンス](/glossary/エラーレスポンス/)の `details` フィールドには、競合しているカラム名や値が含まれています。この情報から原因を特定できます。例えば `"Key (email)=(test@example.com) already exists."` という記載があれば、email カラムの重複が原因です。

**RLS（Row Level Security）との関係：** RLS [ポリシー](/glossary/ポリシー/)が有効な場合、[ポリシー](/glossary/ポリシー/)違反で 403 [エラー](/glossary/エラー/)が返されることもあります。409 [エラー](/glossary/エラー/)が返される場合は、RLS ではなく実データの制約違反と判断できます。

**Supabase [ダッシュボード](/glossary/ダッシュボード/)での制約確認：** Supabase [ダッシュボード](/glossary/ダッシュボード/)のテーブルエディターで「Primary Keys」「Unique Constraints」「Foreign Keys」タブを開き、どのカラムにどのような制約が設定されているかを確認できます。事前にここで制約定義を把握しておくと、409 [エラー](/glossary/エラー/)を事前に防げます。

**Realtime 機能との相性：** Realtime リスナーを有効にしている[テーブル](/glossary/テーブル/)で競合が発生した場合、INSERT/UPDATE がロールバックされたことを[リアルタイム](/glossary/リアルタイム/)で検知できます。クライアント側で[エラーハンドリング](/glossary/エラーハンドリング/)とリトライロジックを組み込むことを推奨します。

## それでも解決しない場合

Supabase [ダッシュボード](/glossary/ダッシュボード/)の「Logs」セクション（Settings > Logs）でデータベースレベルの[エラーログ](/glossary/エラーログ/)を確認できます。[SQL](/glossary/sql/) [エラー](/glossary/エラー/)がより詳細に記録されており、正確な制約名や競合値を確認可能です。

以下の[コマンド](/glossary/コマンド/)で Supabase [CLI](/glossary/cli/) を使用してローカル環境でテーブルスキーマを確認できます：

```bash
supabase db pull
```

この[コマンド](/glossary/コマンド/)で `supabase/migrations/` ディレクトリに [SQL](/glossary/sql/) [スキーマ](/glossary/スキーマ/)が出力され、実際の制約定義を目視確認できます。

PostgreSQL の公式ドキュメントの[整合性制約](https://www.postgresql.org/docs/current/ddl-constraints.html)セクションを参照すると、UNIQUE、PRIMARY KEY、FOREIGN KEY の詳細な動作を理解できます。

また、Supabase の公式ガイド「[Constraints and validations](https://supabase.com/docs/guides/database/constraints)」に制約設計のベストプラクティスが記載されていますので、[アプリケーション](/glossary/アプリケーション/)設計段階で参考にすることを推奨します。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*