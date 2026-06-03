---
title: "Supabase の 401 エラー：原因と解決策"
date: 2026-06-03
description: "Supabaseへの認証トークンが無効または期限切れになっている。Supabase 401 エラーの原因と解決策を解説します。"
tags: ["Supabase"]
errorCode: "401"
---
# Supabase の 401 エラー解説

## エラーの概要

Supabase の 401 エラーは、API リクエストに含まれる認証トークンが無効であるか、有効期限が切れていることを示します。Supabase ではすべてのデータベースアクセスと認証が必要な API 呼び出しに JWT トークンを使用します。クライアント側で認証情報が正しく設定されていない、または有効期限切れのトークンでリクエストを送信した場合に発生します。

## 実際のエラーメッセージ例

**JavaScript/TypeScript クライアントでの出力：**

```json
{
  "error": "Unauthorized",
  "message": "Invalid or expired JWT",
  "status": 401
}
```

**REST API 経由でのエラーレスポンス：**

```json
{
  "code": "PGRST301",
  "message": "Unauthorized",
  "details": null,
  "hint": null
}
```

## よくある原因と解決手順

### 原因 1：anon キーまたは service role キーが間違っている

Supabase プロジェクトには複数の認証キーが存在します。anonymous キー（anon key）はクライアント側で使用するもので、service role キーはバックエンド限定です。キーの値が誤っていたり、異なるプロジェクトのキーを混在させると 401 エラーが発生します。

**Before（エラーが起きるコード）：**

```javascript
import { createClient } from '@supabase/supabase-js';

// キーが間違っているか、タイプミスがある
const supabase = createClient(
  'https://your-project.supabase.co',
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImsxYWd0bWRidXFlYWpjYXh1d2ZvIiwicm9sZSI6ImFub24iLCJpYXQiOjE2MDMzMzIwMDAsImV4cCI6MjAzMzMzMjAwMH0.wrong_key_here'
);

// この呼び出しで 401 エラーが返される
const { data, error } = await supabase
  .from('users')
  .select('*');
```

**After（修正後）：**

```javascript
import { createClient } from '@supabase/supabase-js';

// Supabase Dashboard から正しい anon key をコピーする
const supabase = createClient(
  'https://<your-project>.supabase.co',
  '<correct-anon-key-from-dashboard>'
);

// 正しいキーを設定すればリクエスト成功
const { data, error } = await supabase
  .from('users')
  .select('*');

if (error) console.error('Error:', error);
else console.log('Success:', data);
```

### 原因 2：JWT トークンの有効期限が切れている

Supabase の JWT トークンにはデフォルトで 1 時間の有効期限があります。ユーザーがログイン後、時間が経過してセッションが切れた状態でリクエストを送信すると 401 エラーが返されます。特にモバイルアプリやバックグラウンドで長時間実行されるアプリケーションで頻出します。

**Before（エラーが起きるコード）：**

```javascript
// ユーザーがログインしてから1時間以上経過している
const { data: { user } } = await supabase.auth.getUser();

// セッションの確認なしに API を呼び出す
const { data, error } = await supabase
  .from('user_profiles')
  .select('*')
  .eq('user_id', user.id);

// トークンが期限切れのため 401 エラー
if (error) console.error(error); // "Invalid or expired JWT"
```

**After（修正後）：**

```javascript
// セッション情報を取得して有効期限を確認
const { data: { session } } = await supabase.auth.getSession();

// セッションが存在し、かつ有効な場合のみ API を実行
if (session && session.access_token) {
  // トークンが期限切れの場合は更新
  if (new Date(session.expires_at * 1000) < new Date()) {
    const { data, error } = await supabase.auth.refreshSession();
    if (error) {
      console.error('Session refresh failed:', error);
      // ログイン画面へリダイレクト
      return;
    }
  }

  // 有効なトークンでリクエスト実行
  const { data, error } = await supabase
    .from('user_profiles')
    .select('*')
    .eq('user_id', session.user.id);

  if (error) console.error(error);
  else console.log('Data:', data);
} else {
  console.log('No active session');
}
```

### 原因 3：supabase.auth.getSession() を呼ばずに API を実行しようとしている

Supabase の JavaScript クライアントを初期化しても、セッション情報を明示的に取得しないと、後続の API リクエストにトークンが含まれません。ページ遷移やコンポーネント マウント後にセッションの初期化が完了する前に API を呼び出すと 401 エラーが発生します。

**Before（エラーが起きるコード）：**

```javascript
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(
  'https://<your-project>.supabase.co',
  '<anon-key>'
);

// React コンポーネント例
export function UserList() {
  const [users, setUsers] = useState([]);

  useEffect(() => {
    // セッション取得を待たずに即座に API を呼び出す
    async function fetchUsers() {
      const { data, error } = await supabase
        .from('users')
        .select('*');
      
      // セッションがまだ初期化されていないため 401 エラー
      if (error) console.error(error);
      else setUsers(data);
    }

    fetchUsers();
  }, []);

  return <div>{users.map(u => <p key={u.id}>{u.name}</p>)}</div>;
}
```

**After（修正後）：**

```javascript
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(
  'https://<your-project>.supabase.co',
  '<anon-key>'
);

// React コンポーネント例
export function UserList() {
  const [users, setUsers] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function fetchUsers() {
      try {
        // セッションが初期化されるまで待機
        const { data: { session } } = await supabase.auth.getSession();

        if (!session) {
          console.log('User not authenticated');
          setIsLoading(false);
          return;
        }

        // セッションが確立されてから API を呼び出す
        const { data, error } = await supabase
          .from('users')
          .select('*');

        if (error) console.error('Fetch error:', error);
        else setUsers(data || []);
      } finally {
        setIsLoading(false);
      }
    }

    fetchUsers();
  }, []);

  if (isLoading) return <p>Loading...</p>;
  return <div>{users.map(u => <p key={u.id}>{u.name}</p>)}</div>;
}
```

## ツール固有の注意点

### 認証キーの使い分け

Supabase プロジェクトの Settings > API で複数のキーが公開されています。**anon key（匿名キー）** はブラウザやモバイルアプリなど、クライアント側での使用を想定しています。一方、**service role key** はバックエンド（Node.js サーバー、Lambda 関数など）での限定的な使用を前提としており、クライアント側に露出させてはいけません。`SUPABASE_ANON_KEY` と `SUPABASE_SERVICE_ROLE_KEY` を環境変数で厳密に分け、クライアント側には anon key のみを渡してください。

### Row Level Security（RLS）ポリシーとの相互作用

Supabase でテーブルに RLS ポリシー（行レベルセキュリティ）が有効になっている場合、認証トークンの user_id が正しくないと、データ取得可能でも 401 エラーのように見える 403 エラーが返されることがあります。RLS ポリシーが設定されているテーブルへのアクセスは、`auth.uid()` や `auth.role()` を使用して現在のユーザー情報が正しく紐づけられていることを確認してください。

### マルチタブ・マルチデバイスでのセッション管理

Supabase の JavaScript クライアントはブラウザの LocalStorage にセッション情報を保存します。複数のタブやデバイスからアクセスする場合、各環境で独立したセッションが存在します。セッションがリフレッシュされても他のタブに自動同期されないため、ページリロード後に 401 エラーが発生することがあります。`supabase.auth.onAuthStateChange()` リスナーを設定して、セッション変更を監視し、UI を動的に更新することを推奨します。

## それでも解決しない場合

### ログ確認の手順

Supabase Dashboard の Authentication セクションで、「Logs」タブを開き、エラーレスポンスの詳細確認ができます。リクエストのタイムスタンプとユーザー ID を照合し、実際にどのトークンが拒否されたかを確認してください。

### デバッグコマンド

ブラウザの開発者ツール（DevTools）の Application タブで、Local Storage に保存されたセッション情報を確認してください：

```javascript
// ブラウザコンソールで実行
const session = JSON.parse(localStorage.getItem('sb-<your-project>-auth-token'));
console.log('Access Token:', session?.access_token);
console.log('Expires At:', session?.expires_at);
console.log('Now:', Math.floor(Date.now() / 1000));
```

トークンの有効期限が切れていないか確認してください。expires_at がタイムスタンプ（秒単位）で表示され、現在時刻より後の値になっていれば有効です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*