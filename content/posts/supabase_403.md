---
title: "Supabase の 403 エラー：原因と解決策"
date: 2026-06-04
description: "Row Level Security（RLS）またはポリシーによってアクセスが拒否された。Supabase 403 エラーの原因と解決策を解説します。"
tags: ["Supabase"]
errorCode: "403"
---
## エラーの概要

Supabase の 403 エラーは、Row Level Security（RLS）またはそのポリシーによってデータベースへのアクセスが拒否されたことを示します。これは権限不足を意味する最も一般的なエラーで、テーブルに設定されたセキュリティルールが、現在のリクエストを許可していない状態です。特にフロントエンド側で認証済みユーザーが操作する場合に頻出します。

## 実際のエラーメッセージ例

**レスポンス（JSON）：**

```json
{
  "code": "403",
  "message": "new row violates row level security policy for table \"users\"",
  "details": "Failing row contains (id, email, name) = (uuid-value, user@example.com, John).",
  "hint": null
}
```

**JavaScript コンソール出力：**

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

テーブルの Row Level Security を有効にしたものの、アクセスを許可するポリシーを一つも作成していない場合、すべてのアクセスが拒否されます。RLS が有効なテーブルには、少なくとも SELECT・INSERT・UPDATE・DELETE のいずれかを許可するポリシーが必要です。

**Before（エラーが起きるコード）：**

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

認証済みのユーザートークンでリクエストを送信した場合、RLS ポリシーがそのユーザーに該当データへのアクセスを許可しているかが厳密にチェックされます。ポリシーで `auth.uid()` を使った条件が正しく設定されていないと、自分以外のデータにアクセスできず 403 エラーが発生します。

**Before（エラーが起きるコード）：**

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

また、Supabase ダッシュボードで以下のポリシーが正しく設定されていることを確認してください：

```sql
-- ポリシーが具体的に auth.uid() をチェックしているか確認
CREATE POLICY "Users can access own profile"
  ON public.user_profiles
  FOR SELECT
  USING (auth.uid() = user_id);  -- この条件が必須
```

### 原因3：service role key が必要な管理操作を anon key で実行している

Supabase では 2 種類の API キーが存在します。`anon`（匿名キー）はフロントエンドで使用し、RLS ポリシーの制約を受けます。一方、`service_role`（サービスロールキー）はバックエンド限定で、RLS をバイパスして操作できます。管理者権限の操作（例：ユーザーの一括削除、ポリシーを無視したデータ更新）を anon key で実行しようとすると 403 エラーになります。

**Before（エラーが起きるコード）：**

```javascript
// フロントエンドで anon key を使用してサーバー側の操作を試みる
const supabase = createClient(
  process.env.REACT_APP_SUPABASE_URL,
  process.env.REACT_APP_SUPABASE_ANON_KEY  // anon key
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
// バックエンド（Node.js / Python 等）で service_role key を使用
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_ROLE_KEY  // service_role key（機密情報）
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

**Supabase ダッシュボードでの確認方法**

Supabase ダッシュボードから以下の手順でポリシーを確認できます：

1. 左サイドバーから「SQL Editor」を開き、目的のテーブル名を検索
2. または「Authentication」→「Policies」タブでテーブルごとのポリシー一覧を表示
3. 各ポリシーの「USING」「WITH CHECK」条件が正しいか確認

テーブルの RLS が有効か無効かは、「Table Editor」でテーブルを選択し、右上の「Security」セクションで「Enable RLS」がオンになっているかを確認します。

**認証トークンの有効期限**

Supabase の認証トークンにも有効期限があります。トークンが期限切れの場合、リクエストが匿名状態として扱われ、RLS ポリシーで保護されたテーブルへのアクセスが拒否されることがあります。トークンの自動リフレッシュが設定されているか確認してください。

```javascript
// トークンが期限切れでないか確認
const { data: { user } } = await supabase.auth.getUser();
if (!user) {
  // ユーザーが認証されていない状態 → 匿名アクセスになり403エラーのリスク
  console.log('User is not authenticated');
}
```

## それでも解決しない場合

**ログを確認する方法**

Supabase ダッシュボードの「Logs」セクションで、403 エラーの詳細を確認できます。特に以下の情報をチェックしてください：

- **Policy name**：どのポリシーが拒否したか
- **USING/WITH CHECK clause**：実際に評価された条件
- **Authenticated user UID**：リクエスト時のユーザー ID

**PostgreSQL コマンドラインでのデバッグ**

Supabase の SQL エディターで、ポリシーの論理をテストできます：

```sql
-- テーブルのRLS状態を確認
SELECT schemaname, tablename, rowsecurity
FROM pg_tables
WHERE tablename = 'your_table_name';

-- 特定のテーブルに設定されているすべてのポリシーを表示
SELECT * FROM pg_policies
WHERE tablename = 'your_table_name';
```

**バックアップとしての確認**

- フロントエンドで使用している API キーが本当に `anon key` か `service_role key` か再確認
- `auth.uid()` の代わりに硬定値でテストし、ポリシー評価自体は正常に機能しているか検証
- 公式ドキュメント（https://supabase.com/docs/guides/auth/row-level-security）を参照し、最新のベストプラクティスを確認

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*