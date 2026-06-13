---
title: "Vercel の 502 エラー：原因と解決策"
date: 2026-06-07
description: "VercelのEdge NetworkがバックエンドのOriginから不正な応答を受け取った。Vercel 502 エラーの原因と解決策を解説します。"
tags: ["Vercel"]
errorCode: "502"
service: "Vercel"
error_type: "502"
components: []
related_services: ["Node.js", "Next.js"]
trend_incident: true
---
## エラーの概要

Vercel の 502 Bad Gateway エラーは、Edge Network がバックエンド（Serverless Function またはフレームワークの API）から不正な応答を受け取った、またはタイムアウト（応答待機時間超過）が発生したことを示します。つまり、リクエスト（クライアントからの要求）は Vercel のネットワークに到達しても、実際の処理を担当する関数やサーバーが期待通りの応答を返していない状況です。このエラーが発生すると、ユーザーには「502 Bad Gateway」という HTTP ステータスコードが返され、アプリケーションの機能停止に直結します。

## 実際のエラーメッセージ例

ブラウザには以下のように表示されます：

```
502 Bad Gateway
```

Vercel ダッシュボードのログ、または `vercel logs` コマンドでは：

```json
{
  "statusCode": 502,
  "message": "Bad Gateway",
  "details": "The server did not return a valid response"
}
```

また、関数のコンソール出力に以下のようなメッセージが表示される場合もあります：

```
FunctionError: Code execution timed out.
```

## よくある原因と解決手順

### 原因1：Serverless Function がレスポンスを返さずに終了している

Node.js の Serverless Function では、リクエストハンドラーが必ず `response.send()`、`response.end()`、または return 文でレスポンス（サーバーからの応答）を返す必要があります。これらが呼ばれずに関数が終了すると、Vercel は有効なレスポンスを受け取れず、502 エラーが発生します。

**Before（エラーが起きるコード）：**

```javascript
export default function handler(req, res) {
  const data = fetchData();
  
  // レスポンスを返さずに関数が終了してしまう
  console.log('処理完了');
}
```

**After（修正後）：**

```javascript
export default function handler(req, res) {
  const data = fetchData();
  
  res.status(200).json({
    success: true,
    data: data
  });
}
```

非同期処理の場合、Promise（非同期処理）の完了を待たずにレスポンスを返すと、バックエンド処理の不完全さや未処理のエラーが原因で Vercel が不正な応答と見なす可能性があります：

**Before（エラーが起きるコード）：**

```javascript
export default async function handler(req, res) {
  // await がないため、Promise の完了を待たずに進む
  fetchDataAsync();
  
  res.status(200).json({ message: 'OK' });
}
```

**After（修正後）：**

```javascript
export default async function handler(req, res) {
  // 必ず await で Promise の完了を待つ
  const data = await fetchDataAsync();
  
  res.status(200).json({ message: 'OK', data: data });
}
```

### 原因2：バックエンドの Origin サービスがクラッシュまたは不正な応答を返している

Next.js のページ内でバックエンド API（サーバーのデータ提供機能）呼び出しを行う際、外部 API やデータベースが正常に応答していない、またはタイムアウトが発生している場合に 502 エラーが起こります。

**Before（エラーが起きるコード）：**

```javascript
export default async function handler(req, res) {
  try {
    // タイムアウト設定なしで無期限に待機してしまう
    const response = await fetch('https://external-api.example.com/data');
    const data = await response.json();
    
    res.status(200).json(data);
  } catch (error) {
    // エラーハンドリングがなく、レスポンスが返されない
    console.error(error);
  }
}
```

**After（修正後）：**

```javascript
export default async function handler(req, res) {
  try {
    // タイムアウトを 5 秒に設定
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    
    const response = await fetch('https://external-api.example.com/data', {
      signal: controller.signal
    });
    clearTimeout(timeoutId);
    
    if (!response.ok) {
      return res.status(502).json({ error: 'External API error' });
    }
    
    const data = await response.json();
    res.status(200).json(data);
  } catch (error) {
    console.error(error);
    // 必ずエラーレスポンスを返す
    res.status(502).json({ error: 'Internal server error' });
  }
}
```

### 原因3：ビルド成果物が不完全またはデプロイが失敗している

`vercel build` または `npm run build` でビルドが正常に完了していない場合、実際のアプリケーションコードが本番環境に存在しないため、502 エラーが発生します。

**Before（エラーが起きるコード）：**

```json
{
  "buildCommand": "npm run build",
  "outputDirectory": "wrong-directory"
}
```

**After（修正後）：**

```json
{
  "buildCommand": "npm run build",
  "outputDirectory": ".next",
  "framework": "nextjs"
}
```

または `package.json` の build スクリプトに問題がないか確認：

**Before（エラーが起きるコード）：**

```json
{
  "scripts": {
    "build": "npm run lint && next build",
    "lint": "exit 1"
  }
}
```

**After（修正後）：**

```json
{
  "scripts": {
    "build": "next build",
    "lint": "eslint ."
  }
}
```

## Vercel 固有の注意点

Vercel での 502 エラーは、環境によって表現が異なります。本番環境（Production）では即座にエラーページが返されますが、プレビュー環境（Preview）では関数のログが詳細に表示されることがあります。

**Serverless Function のタイムアウト設定**：デフォルトでは最大 30 秒のタイムアウトが設定されています。より長い処理が必要な場合、Pro 以上のプランであれば `vercel.json` でタイムアウト時間を延長できます：

```json
{
  "functions": {
    "api/**": {
      "memory": 3008,
      "maxDuration": 60
    }
  }
}
```

**Next.js の API Routes の場合**：`/pages/api/` ディレクトリー配下のファイルが正しくデプロイされているか、`vercel inspect` コマンドで確認できます。

**ミドルウェア層の確認**：Next.js の `middleware.ts` が大量のリソースを消費している場合、Serverless Function の実行前に失敗することがあります。

## それでも解決しない場合

### ログの確認

`vercel logs` コマンドでリアルタイムログを確認します：

```bash
vercel logs <url> --follow
```

特定のプロダクションデプロイメントのログを見る場合：

```bash
vercel logs <your-production-url> --follow
```

### ローカルテスト

`vercel dev` でローカル環境で Vercel のシミュレーション環境を起動し、本番と同じ条件で動作確認を行います：

```bash
vercel dev
```

この際、ローカルでは動作するが本番で 502 が出ている場合、以下を確認してください：

- 環境変数が本番環境で正しく設定されているか（Vercel ダッシュボードの Settings > Environment Variables）
- 関数のメモリー設定が不足していないか
- 外部 API のホワイトリスト設定に本番ドメインが含まれているか

### 公式ドキュメントの参照

- [Vercel Serverless Functions Documentation](https://vercel.com/docs/functions/serverless-functions)
- [Error Status Codes](https://vercel.com/docs/errors)
- [Building and Deploying with Vercel](https://vercel.com/docs/projects/overview)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*