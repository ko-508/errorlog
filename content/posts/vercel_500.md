---
title: "Vercel の 500 エラー：原因と解決策"
date: 2026-06-07
description: "Vercelのサーバーレス関数で内部エラーが発生した。Vercel 500 エラーの原因と解決策を解説します。"
tags: ["Vercel"]
errorCode: "500"
---
## エラーの概要

Vercel の 500 エラーは、サーバーレス関数の実行中に内部エラーが発生したことを示します。このエラーは Vercel のバックエンド側で例外がキャッチされず、クライアントにはエラー内容の詳細が返されません。デプロイは成功していても、関数の実行時にコード内のバグ、依存パッケージの問題、環境変数の欠落などが原因で発生することがほとんどです。

## 実際のエラーメッセージ例

**ブラウザでの表示：**

```json
{
  "error": "Internal Server Error",
  "statusCode": 500,
  "message": "500: Internal Server Error"
}
```

**Vercel ダッシュボードのログで表示されるエラー例：**

```bash
TypeError: Cannot read property 'db' of undefined
    at /var/task/api/database.js:15:42
    at /var/task/api/handler.js:8:5
    at Runtime.handler (/var/task/index.js:20:10)
```

## よくある原因と解決手順

### 原因1：サーバーレス関数内でキャッチされない例外が発生している

関数のコード内で例外がスローされ、try-catch で捕捉されていない場合、そのまま 500 エラーとなります。非同期処理（Promise）の reject やAsync/Await のエラーハンドリング漏れが特に起きやすいです。

**Before（エラーが起きるコード）：**

```javascript
export default async function handler(req, res) {
  const data = JSON.parse(req.body);
  const result = await fetchDatabase(data.id);
  return res.status(200).json(result);
}

async function fetchDatabase(id) {
  const response = await fetch('https://api.example.com/user/' + id);
  const json = response.json();
  return json;
}
```

**After（修正後）：**

```javascript
export default async function handler(req, res) {
  try {
    const data = JSON.parse(req.body);
    const result = await fetchDatabase(data.id);
    return res.status(200).json(result);
  } catch (error) {
    console.error('Error:', error);
    return res.status(500).json({ error: 'Internal Server Error' });
  }
}

async function fetchDatabase(id) {
  try {
    const response = await fetch('https://api.example.com/user/' + id);
    if (!response.ok) {
      throw new Error(`API returned ${response.status}`);
    }
    const json = await response.json();
    return json;
  } catch (error) {
    throw new Error('Database fetch failed: ' + error.message);
  }
}
```

### 原因2：必要なパッケージが正しくインストールされていない

`package.json` に記載されたパッケージがインストールされていない、あるいはデプロイ時にインストール段階で失敗している場合、関数内で依存モジュールを呼び出すと 500 エラーになります。

**Before（エラーが起きるコード）：**

```javascript
// package.json に記載がない、または .gitignore で node_modules が除外されている
import axios from 'axios';

export default async function handler(req, res) {
  const response = await axios.get('https://api.example.com/data');
  return res.status(200).json(response.data);
}
```

**After（修正後）：**

```bash
npm install axios
```

```javascript
// package.json に "axios": "^1.x.x" が含まれていることを確認
import axios from 'axios';

export default async function handler(req, res) {
  try {
    const response = await axios.get('https://api.example.com/data');
    return res.status(200).json(response.data);
  } catch (error) {
    console.error('Axios error:', error.message);
    return res.status(500).json({ error: 'Request failed' });
  }
}
```

デプロイ前に以下を実行してください：

```bash
npm install --production
```

### 原因3：環境変数が設定されていないことで実行時エラーが起きている

コード内で `process.env.DATABASE_URL` など環境変数を参照していても、Vercel ダッシュボードで設定されていない場合、`undefined` を参照することになり 500 エラーの原因となります。

**Before（エラーが起きるコード）：**

```javascript
import postgres from 'postgres';

const sql = postgres(process.env.DATABASE_URL);

export default async function handler(req, res) {
  try {
    const users = await sql`SELECT * FROM users`;
    return res.status(200).json(users);
  } catch (error) {
    return res.status(500).json({ error: error.message });
  }
}
```

**After（修正後）：**

```javascript
import postgres from 'postgres';

export default async function handler(req, res) {
  try {
    const databaseUrl = process.env.DATABASE_URL;
    if (!databaseUrl) {
      throw new Error('DATABASE_URL environment variable is not set');
    }
    const sql = postgres(databaseUrl);
    const users = await sql`SELECT * FROM users`;
    return res.status(200).json(users);
  } catch (error) {
    console.error('Database error:', error.message);
    return res.status(500).json({ error: 'Database connection failed' });
  }
}
```

Vercel ダッシュボードで以下の手順で環境変数を設定します：

1. プロジェクトの Settings > Environment Variables
2. `DATABASE_URL` を入力
3. 本番環境・プレビュー環境・開発環境を指定して保存

## ツール固有の注意点

### Vercel ログの確認方法

Vercel ダッシュボードから詳細なエラーログを確認することが最初のステップです。

1. **プロジェクト選択** → **Deployments** → **最新のデプロイを選択**
2. **Functions** タブをクリック
3. **エラーが発生した関数**を選択して **Logs** をクリック
4. **Runtime logs** と **Build logs** の両方を確認

Build logs では、デプロイ時の依存パッケージインストール段階のエラーが表示されます。

### ローカル開発環境での再現

Vercel の `vercel dev` コマンドを使うことで、ローカルでサーバーレス関数の動作を確認できます。これにより、本番環境にデプロイする前にエラーを発見できます。

```bash
vercel dev
```

このコマンドで立ち上がるローカル環境は、ほぼ本番環境と同じ条件で関数を実行します。ブラウザで `http://localhost:3000/api/<function-name>` にアクセスしてテストしてください。

### 環境変数のローカル設定

ローカルでも本番と同じ環境変数でテストするため、`.env.local` ファイルを作成します：

```bash
DATABASE_URL=postgres://user:pass@localhost/dbname
API_KEY=your-test-api-key
```

### Node.js ランタイムのバージョン確認

Vercel でサポートされる Node.js バージョンとプロジェクトの `package.json` に記載されたバージョンが異なる場合、互換性の問題が発生することがあります。以下で確認・指定してください：

```json
{
  "engines": {
    "node": "18.x"
  }
}
```

## それでも解決しない場合

### ログの詳細確認

Vercel ダッシュボードの Functions タブで、以下をすべて確認してください：

- **Runtime logs**：実行時のエラー内容
- **Build logs**：デプロイ時の警告・エラー
- **Stdout/Stderr**：`console.log` の出力

### デバッグ用の詳細ログ出力

関数内に詳細なログを仕込むことで、どの行で失敗しているかを特定できます：

```javascript
export default async function handler(req, res) {
  console.log('1. Request received', req.method);
  
  try {
    console.log('2. Connecting to database');
    const result = await database.query('SELECT * FROM users');
    console.log('3. Query successful', result.length);
    
    return res.status(200).json(result);
  } catch (error) {
    console.error('4. Error caught:', error.name, error.message);
    console.error('5. Stack:', error.stack);
    return res.status(500).json({ error: error.message });
  }
}
```

### 公式リソース

以下の公式ドキュメントを参照して、より詳しい設定方法を確認してください：

- [Vercel Functions Documentation](https://vercel.com/docs/functions)
- [Debugging in Vercel](https://vercel.com/docs/concepts/deployments/logs)
- [Environment Variables in Vercel](https://vercel.com/docs/concepts/projects/environment-variables)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*