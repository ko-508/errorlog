---
title: "Supabase の 500 エラー：原因と解決策"
date: 2026-06-05
description: "Supabaseサービスの内部エラーが発生した。Supabase 500 エラーの原因と解決策を解説します。"
tags: ["Supabase"]
errorCode: "500"
service: "Supabase"
error_type: "500"
components: ["REST API", "Functions", "SQL Editor", "Dashboard"]
related_services: ["PostgreSQL", "supabase-js", "Deno"]
---
# エラーの概要

Supabaseの500[エラー](/glossary/エラー/)は、Supabase[サーバー](/glossary/サーバー/)側で予期しない内部[エラー](/glossary/エラー/)が発生したことを示します。クライアント側の[リクエスト](/glossary/リクエスト/)は正しくても、PostgreSQLの実行[エラー](/glossary/エラー/)・Functionsの例外処理漏れ・インフラストラクチャの一時的な問題など、複数の原因が考えられます。この[エラー](/glossary/エラー/)が発生した場合は、サーバーログを確認して具体的な原因を特定する必要があります。

## 実際のエラーメッセージ例

**JavaScriptクライアント（supabase-js）での出力例：**

```json
{
  "error": {
    "message": "Internal Server Error",
    "status": 500
  },
  "statusCode": 500
}
```

**Supabase [REST](/glossary/rest/) [API](/glossary/api/)の直接呼び出し時の例：**

```json
{
  "code": "PGRST500",
  "message": "relation \"public.users\" does not exist",
  "details": null,
  "hint": null
}
```

**ブラウザコンソールでの出力例：**

```javascript
Error: Internal Server Error
  at async Session.from (auth.ts:456:23)
```

## よくある原因と解決手順

### 原因1：PostgreSQLのクエリが構文エラーまたは実行時エラーになっている

Supabaseに送信する[SQL](/glossary/sql/)[クエリ](/glossary/クエリ/)に構文[エラー](/glossary/エラー/)があったり、存在しない[テーブル](/glossary/テーブル/)・カラムを参照していたりする場合、500[エラー](/glossary/エラー/)が発生します。特にRLS（Row Level Security）の[ポリシー](/glossary/ポリシー/)内で不正な[テーブル](/glossary/テーブル/)参照をしていると、[クエリ](/glossary/クエリ/)実行時に内部[エラー](/glossary/エラー/)となります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
const { data, error } = await supabase
  .from('users')
  .select('id, name, invalid_column')
  .eq('status', 'active');

if (error) {
  console.log('Error:', error.message);
}
```

**After（修正後）：**

```javascript
const { data, error } = await supabase
  .from('users')
  .select('id, name, email')
  .eq('status', 'active');

if (error) {
  console.log('Error:', error.message);
}
```

または、実際にカラムが存在することを事前確認し、[テーブル](/glossary/テーブル/)定義を正しくする必要があります。Supabase Dashboardの「[SQL](/glossary/sql/) Editor」で[クエリ](/glossary/クエリ/)を事前[テスト](/glossary/テスト/)することをお勧めします。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```sql
CREATE POLICY "users_select_policy" ON public.users
  FOR SELECT USING (
    user_id = auth.uid() AND deleted_at IS NULL
  );
```

**After（修正後）：**

```sql
CREATE POLICY "users_select_policy" ON public.users
  FOR SELECT USING (
    id = auth.uid()
  );
```

### 原因2：Supabase Functionsのコードで未処理の例外が発生している

Functionsで実装したエッジファンクション（Supabaseの別環境で実行される関数）が予期しない例外をスローしているか、try-catchで捕捉できていない[エラー](/glossary/エラー/)が発生している場合、500[エラー](/glossary/エラー/)が返されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
// supabase/functions/process-payment/index.ts
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

serve(async (req) => {
  const { amount } = await req.json();
  const result = amount / 0; // 明らかなエラーではないが、後続処理で例外が発生
  
  return new Response(JSON.stringify({ result }));
});
```

**After（修正後）：**

```javascript
// supabase/functions/process-payment/index.ts
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

serve(async (req) => {
  try {
    const { amount } = await req.json();
    
    if (!amount || amount <= 0) {
      return new Response(
        JSON.stringify({ error: "Invalid amount" }),
        { status: 400 }
      );
    }
    
    const result = amount * 0.1;
    return new Response(JSON.stringify({ result }), { status: 200 });
  } catch (error) {
    console.error("Function error:", error);
    return new Response(
      JSON.stringify({ error: "Internal server error" }),
      { status: 500 }
    );
  }
});
```

### 原因3：Supabaseインフラで一時的な障害が起きている

Subaseのバックエンドサービス（PostgreSQL、Auth、Realtimeなどのインフラストラクチャレイヤーまたはデータセンター）で一時的な障害が発生していることもあります。この場合、ユーザー側では対処できず、Supabaseサービスの復旧を待つ必要があります。

**確認方法：**

Supabase公式ステータスページ（status.supabase.com）にアクセスして、現在のサービス状態を確認します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
const { data, error } = await supabase
  .from('posts')
  .select('*');

if (error?.status === 500) {
  // すぐに再度呼び出し
  const { data: retryData } = await supabase
    .from('posts')
    .select('*');
}
```

**After（修正後）：**

```javascript
async function fetchWithRetry(maxRetries = 3, delay = 1000) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const { data, error } = await supabase
        .from('posts')
        .select('*');
      
      if (!error) {
        return data;
      }
      
      if (error.status === 500) {
        if (i < maxRetries - 1) {
          await new Promise(resolve => setTimeout(resolve, delay * Math.pow(2, i)));
          continue;
        }
      }
      
      throw error;
    } catch (err) {
      console.error(`Attempt ${i + 1} failed:`, err);
    }
  }
}

const data = await fetchWithRetry();
```

## ツール固有の注意点

### Supabase Dashboardのログ確認方法

Supabase Dashboardの「Logs」セクションは、500[エラー](/glossary/エラー/)の具体的な原因を特定するために不可欠です。

1. **[SQL](/glossary/sql/) Logs**：`Home > Logs > PostgreSQL`で、実行された[クエリ](/glossary/クエリ/)と詳細な[エラーメッセージ](/glossary/エラーメッセージ/)を確認できます。
2. **Function Logs**：`Edge Functions`の[ログ](/glossary/ログ/)から、[デプロイ](/glossary/デプロイ/)されたFunctionの[コンソール](/glossary/コンソール/)出力とエラースタックトレースを確認できます。
3. **Auth Logs**：認証絡みの[エラー](/glossary/エラー/)は`Authentication > Logs`で確認します。

### RLS（Row Level Security）ポリシーのデバッグ

RLS[ポリシー](/glossary/ポリシー/)内での[エラー](/glossary/エラー/)は特定が難しいため、デバッグモード有効化が推奨されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```sql
CREATE POLICY "check_user" ON public.posts
  FOR SELECT USING (user_id = auth.uid());
```

**After（修正後）：**

```sql
-- 開発環境でのみRLSを一時的に無効化して、実際のテーブルアクセス確認
ALTER TABLE public.posts DISABLE ROW LEVEL SECURITY;

-- その後、ポリシーをテストして有効化
ALTER TABLE public.posts ENABLE ROW LEVEL SECURITY;
```

### マルチテナント構成での500エラー

複数の[スキーマ](/glossary/スキーマ/)や[テーブル](/glossary/テーブル/)を使用する場合、権限設定が不十分だと500[エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```sql
CREATE TABLE public.users (id BIGINT PRIMARY KEY);
-- 権限付与なし
```

**After（修正後）：**

```sql
CREATE TABLE public.users (id BIGINT PRIMARY KEY);

GRANT SELECT ON public.users TO authenticated;
GRANT INSERT, UPDATE ON public.users TO authenticated;
GRANT SELECT ON public.users TO anon;
```

## それでも解決しない場合

### ステップ1：Supabaseステータスページを確認

```bash
# ブラウザで以下にアクセス
https://status.supabase.com
```

現在のインシデント情報を確認します。障害が報告されている場合は、復旧を待ちます。

### ステップ2：詳細ログを確認

Supabase Dashboard > **Logs** セクションで以下を順番に確認します：

1. PostgreSQL Logs（`SELECT * FROM ...` の実行[ログ](/glossary/ログ/)）
2. Function Logs（[デプロイ](/glossary/デプロイ/)されたFunctionの標準出力・[エラー](/glossary/エラー/)出力）
3. Auth Logs（認証関連の[エラー](/glossary/エラー/)）

### ステップ3：cURLコマンドで直接APIをテスト

```bash
# Supabase REST APIを直接呼び出して、エラーメッセージの詳細を取得
curl -X GET "https://<your-project>.supabase.co/rest/v1/users?select=*" \
  -H "apikey: <your-public-key>" \
  -H "Authorization: Bearer <your-token>"
```

[エラーレスポンス](/glossary/エラーレスポンス/)に含まれる `code` と `message` フィールドから、より詳細な原因を特定できます。

### ステップ4：ローカルでの再現テスト

```bash
# supabase-cliをインストール（未インストールの場合）
npm install -g supabase

# ローカルエミュレーターを起動
supabase start

# ローカル環境でクエリをテスト
curl -X GET "http://localhost:54321/rest/v1/users" \
  -H "apikey: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

### ステップ5：公式サポートへの問い合わせ

Supabase公式ドキュメント（https://supabase.com/docs）または、GitHub Discussions（https://github.com/supabase/supabase/discussions）で同様の問題事例を検索します。解決しない場合は、以下の情報を添付して問い合わせます：

- Project [ID](/glossary/id/)
- 発生時刻（UTC）
- [エラーメッセージ](/glossary/エラーメッセージ/)の全文
- 実行した[クエリ](/glossary/クエリ/)またはFunction名

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*