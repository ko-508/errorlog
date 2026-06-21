---
title: "Supabase の 403 エラー：原因と解決策"
date: 2026-06-04
description: "Row Level Security（RLS）またはポリシーによってアクセスが拒否された。Supabase 403 エラーの原因と解決策を解説します。"
tags: ["Supabase"]
errorCode: "403"
service: "Supabase"
error_type: "403"
components: ["Row Level Security", "Auth"]
related_services: ["JavaScript", "SQL"]
---
## エラーの概要

Supabase の 403 [エラー](/glossary/エラー/)は、Row Level Security（RLS）またはその[ポリシー](/glossary/ポリシー/)によって[データベース](/glossary/データベース/)へのアクセスが拒否されたことを示します。これは権限不足を意味する最も一般的な[エラー](/glossary/エラー/)で、[テーブル](/glossary/テーブル/)に設定されたセキュリティルールが、現在の[リクエスト](/glossary/リクエスト/)を許可していない状態です。特にフロントエンド側で認証済みユーザーが操作する場合に頻出します。

## 実際のエラーメッセージ例

**[レスポンス](/glossary/レスポンス/)（[JSON](/glossary/json/)）：**

```json
{
  "code": "403",
  "message": "new row violates row level security policy for table \"users\"",
  "details": "Failing row contains (id, email, name) = (uuid-value, user@example.com, John).",
  "hint": null
}
```

**JavaScript [コンソール](/glossary/コンソール/)出力：**

```javascript
{
  status: 403,
  statusText: 'Forbidden',
  error: {
    code: '42501',
    message: 'permission denied for schema "public"',
    details: null
  }
}
```

## よくある原因と解決手順

### 原因1：RLS が有効だがポリシーが設定されていない

[テーブル](/glossary/テーブル/)の Row Level Security を有効にしたものの、アクセスを許可する[ポリシー](/glossary/ポリシー/)を一つも作成していない場合、すべてのアクセスが拒否されます。RLS が有効な[テーブル](/glossary/テーブル/)には、少なくとも SELECT・INSERT・UPDATE・DELETE のいずれかを許可する[ポリシー](/glossary/ポリシー/)が必要です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```sql
-- テーブルを作成してRLSを有効にするが、ポリシーは設定しない
CREATE TABLE public.posts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  title TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT now()
);

ALTER TABLE public.posts ENABLE ROW LEVEL SECURITY;

-- ポリシーがないため、どのユーザーも読み書きできない
```

**After（修正後）：**

```sql
-- テーブルを作成してRLSを有効にする
CREATE TABLE public.posts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  title TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT now()
);

ALTER TABLE public.posts ENABLE ROW LEVEL SECURITY;

-- ユーザーが自分のデータだけを読取できるポリシーを作成
CREATE POLICY "Users can read their own posts"
  ON public.posts
  FOR SELECT
  USING (auth.uid() = user_id);

-- ユーザーが自分のデータだけを作成できるポリシーを作成
CREATE POLICY "Users can create their own posts"
  ON public.posts
  FOR INSERT
  WITH CHECK (auth.uid() = user_id);
```

### 原因2：ログイン済みユーザーが他ユーザーのデータにアクセスしようとしている

認証済みのユーザートークンで[リクエスト](/glossary/リクエスト/)を送信した場合、RLS [ポリシー](/glossary/ポリシー/)がそのユーザーに該当データへのアクセスを許可しているかが厳密にチェックされます。[ポリシー](/glossary/ポリシー/)で `auth.uid()` を使った条件が正しく設定されていないと、自分以外のデータにアクセスできず 403 [エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
// フロントエンドで認証済みユーザー（UID: abc-123）がいるとする
const { data, error } = await supabase
  .from('user_profiles')
  .select('*')
  .eq('user_id', 'def-456')  // 異なるユーザーのデータを取得しようとする
  .single();

// RLSポリシーが auth.uid() = user_id のみを許可していれば、403エラーが発生
```

**After（修正後）：**

```javascript
// 現在のユーザー自身のデータのみを取得する
const { data: { user } } = await supabase.auth.getUser();

const { data, error } = await supabase
  .from('user_profiles')
  .select('*')
  .eq('user_id', user.id)  // 認証済みユーザーのUIDと一致させる
  .single();

// または、RLSポリシーで user_id を省略し、セッションから自動判別させる設定も可
```

また、Supabase [ダッシュボード](/glossary/ダッシュボード/)で以下の[ポリシー](/glossary/ポリシー/)が正しく設定されていることを確認してください：

```sql
-- ポリシーが具体的に auth.uid() をチェックしているか確認
CREATE POLICY "Users can access own profile"
  ON public.user_profiles
  FOR SELECT
  USING (auth.uid() = user_id);  -- この条件が必須
```

### 原因3：service_role キーが必要な管理操作を anon キーで実行している

Supabase では 2 種類の [API](/glossary/api/) キーが存在します。`anon`（匿名キー）はフロントエンドで使用し、RLS [ポリシー](/glossary/ポリシー/)の制約を受けます。一方、`service_role`（サービスロールキー）は[バックエンド](/glossary/バックエンド/)限定で、RLS をバイパスして操作できます。[管理者権限](/glossary/管理者権限/)の操作（例：ユーザーの一括削除、[ポリシー](/glossary/ポリシー/)を無視したデータ更新）を anon キーで実行しようとすると 403 [エラー](/glossary/エラー/)になります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
// フロントエンドで anon キーを使用してサーバー側の操作を試みる
const supabase = createClient(
  process.env.REACT_APP_SUPABASE_URL,
  process.env.REACT_APP_SUPABASE_ANON_KEY  // anon キー
);

// ユーザーの管理者フラグを強制的に更新しようとする（RLSでブロック）
const { error } = await supabase
  .from('users')
  .update({ is_admin: true })
  .eq('id', 'target-user-id');
// → 403 エラーが発生
```

**After（修正後）：**

```javascript
// バックエンド（Node.js / Python 等）で service_role キーを使用
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_ROLE_KEY  // service_role キー（機密情報）
);

// サーバー側なら RLS をバイパスして操作可能
const { error } = await supabase
  .from('users')
  .update({ is_admin: true })
  .eq('id', 'target-user-id');

// フロントエンド側では、認可チェック付きの API エンドポイントを呼び出す
const response = await fetch('/api/promote-admin', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ userId: 'target-user-id' })
});
```

## ツール固有の注意点

**Supabase [ダッシュボード](/glossary/ダッシュボード/)での確認方法**

Supabase [ダッシュボード](/glossary/ダッシュボード/)から以下の手順で[ポリシー](/glossary/ポリシー/)を確認できます：

1. 左サイドバーから「[SQL](/glossary/sql/) Editor」を開き、目的の[テーブル](/glossary/テーブル/)名を検索
2. または「Authentication」→「Policies」タブで[テーブル](/glossary/テーブル/)ごとの[ポリシー](/glossary/ポリシー/)一覧を表示
3. 各[ポリシー](/glossary/ポリシー/)の「USING」「WITH CHECK」条件が正しいか確認

[テーブル](/glossary/テーブル/)の RLS が有効か無効かは、「Table Editor」で[テーブル](/glossary/テーブル/)を選択し、右上の「Security」セクションで「Enable RLS」がオンになっているかを確認します。

**[認証](/glossary/認証/)[トークン](/glossary/トークン/)の有効期限**

Supabase の[認証](/glossary/認証/)[トークン](/glossary/トークン/)には有効期限があります。[トークン](/glossary/トークン/)が期限切れの場合、[リクエスト](/glossary/リクエスト/)が匿名状態として扱われ、RLS [ポリシー](/glossary/ポリシー/)で保護された[テーブル](/glossary/テーブル/)へのアクセスが拒否されることがあります。[トークン](/glossary/トークン/)の自動リフレッシュが設定されているか確認してください。

```javascript
// トークンが期限切れでないか確認
const { data: { user } } = await supabase.auth.getUser();
if (!user) {
  // ユーザーが認証されていない状態 → 匿名アクセスになり403エラーのリスク
  console.log('User is not authenticated');
}
```

## それでも解決しない場合

**[ログ](/glossary/ログ/)を確認する方法**

Supabase [ダッシュボード](/glossary/ダッシュボード/)の「Logs」セクションで、403 [エラー](/glossary/エラー/)の詳細を確認できます。特に以下の情報をチェックしてください：

- **Policy name**：どの[ポリシー](/glossary/ポリシー/)が拒否したか
- **USING/WITH CHECK clause**：実際に評価された条件
- **Authenticated user UID**：[リクエスト](/glossary/リクエスト/)時のユーザー [ID](/glossary/id/)

**PostgreSQL [コマンドライン](/glossary/コマンドライン/)での[デバッグ](/glossary/デバッグ/)**

Supabase の [SQL](/glossary/sql/) エディターで、[ポリシー](/glossary/ポリシー/)の論理を[テスト](/glossary/テスト/)できます：

```sql
-- テーブルのRLS状態を確認
SELECT schemaname, tablename, rowsecurity
FROM pg_tables
WHERE tablename = 'your_table_name';

-- 特定のテーブルに設定されているすべてのポリシーを表示
SELECT * FROM pg_policies
WHERE tablename = 'your_table_name';
```

**[バックアップ](/glossary/バックアップ/)としての確認**

- フロントエンドで使用している [API](/glossary/api/) キーが本当に `anon キー` か `service_role キー` か再確認
- `auth.uid()` の代わりに硬定値で[テスト](/glossary/テスト/)し、[ポリシー](/glossary/ポリシー/)評価自体は正常に機能しているか検証
- 公式ドキュメント（https://supabase.com/docs/guides/auth/row-level-security）を参照し、最新のベストプラクティスを確認

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*