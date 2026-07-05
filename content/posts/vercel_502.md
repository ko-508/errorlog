---
draft: true
title: "Vercel の 502 エラー：原因と解決策"
date: 2026-06-07
description: "VercelのEdge NetworkがバックエンドのOriginから不正な応答を受け取った"
tags: ["Vercel"]
errorCode: "502"
service: "Vercel"
error_type: "502"
components: []
related_services: ["Node.js", "Next.js"]
trend_incident: true
top_queries:
- 'bad gateway error code 502'
---
## エラーの概要

Vercel の 502 Bad Gateway [エラー](/glossary/エラー/)は、Edge Network が[バックエンド](/glossary/バックエンド/)（Serverless Function またはフレームワークの [API](/glossary/api/)）から不正な応答を受け取った、または[タイムアウト](/glossary/タイムアウト/)（応答待機時間超過）が発生したことを示します。つまり、[リクエスト](/glossary/リクエスト/)はVercel の[ネットワーク](/glossary/ネットワーク/)に到達しても、実際の処理を担当する関数や[サーバー](/glossary/サーバー/)が期待通りの応答を返していない状況です。この[エラー](/glossary/エラー/)が発生すると、ユーザーには「502 Bad Gateway」という [HTTP](/glossary/http/) [ステータスコード](/glossary/ステータスコード/)が返され、[アプリケーション](/glossary/アプリケーション/)の機能停止に直結します。

## 実際のエラーメッセージ例

ブラウザには以下のように表示されます：

```
502 Bad Gateway
```

Vercel [ダッシュボード](/glossary/ダッシュボード/)の[ログ](/glossary/ログ/)、または `vercel logs` [コマンド](/glossary/コマンド/)では：

```json
{
  "statusCode": 502,
  "message": "Bad Gateway",
  "details": "The server did not return a valid response"
}
```

また、関数の[コンソール](/glossary/コンソール/)出力に以下のようなメッセージが表示される場合もあります：

```
FunctionError: Code execution timed out.
```

## よくある原因と解決手順

### 原因1：Serverless Function がレスポンスを返さずに終了している

Node.js の Serverless Function では、リクエストハンドラーが必ず `response.send()`、`response.end()`、または return 文で[レスポンス](/glossary/レスポンス/)を返す必要があります。これらが呼ばれずに関数が終了すると、Vercel は有効な[レスポンス](/glossary/レスポンス/)を受け取れず、502 [エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

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

非同期処理の場合、Promise の完了を待たずに[レスポンス](/glossary/レスポンス/)を返すと、[バックエンド](/glossary/バックエンド/)処理の不完全さや未処理の[エラー](/glossary/エラー/)が原因で Vercel が不正な応答と見なす可能性があります：

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

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

### 原因2：バックエンドのオリジンサービスがクラッシュまたは不正な応答を返している

Next.js のページ内で[バックエンド](/glossary/バックエンド/) [API](/glossary/api/) 呼び出しを行う際、外部 [API](/glossary/api/) や[データベース](/glossary/データベース/)が正常に応答していない、または[タイムアウト](/glossary/タイムアウト/)が発生している場合に 502 [エラー](/glossary/エラー/)が起こります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

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

`vercel build` または `npm run build` でビルドが正常に完了していない場合、実際のアプリケーションコードが本番環境に存在しないため、502 [エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

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

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

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

Vercel での 502 [エラー](/glossary/エラー/)は、環境によって表現が異なります。本番環境（Production）では即座にエラーページが返されますが、プレビュー環境（Preview）では関数の[ログ](/glossary/ログ/)が詳細に表示されることがあります。

**Serverless Function の[タイムアウト](/glossary/タイムアウト/)設定**：デフォルトでは最大 10 秒の[タイムアウト](/glossary/タイムアウト/)が設定されています（Pro プラン以上で最大 900 秒）。より長い処理が必要な場合、Pro 以上のプランであれば `vercel.json` で[タイムアウト](/glossary/タイムアウト/)時間を延長できます：

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

**Next.js の [API](/glossary/api/) Routes の場合**：`/pages/api/` ディレクトリー配下のファイルが正しく[デプロイ](/glossary/デプロイ/)されているか、`vercel inspect` [コマンド](/glossary/コマンド/)で確認できます。

**ミドルウェア層の確認**：Next.js の `middleware.ts` が大量のリソースを消費している場合、Serverless Function の実行前に失敗することがあります。

## それでも解決しない場合

### ログの確認

`vercel logs` [コマンド](/glossary/コマンド/)でリアルタイムログを確認します：

```bash
vercel logs <url> --follow
```

特定のプロダクションデプロイメントの[ログ](/glossary/ログ/)を見る場合：

```bash
vercel logs <your-production-url> --follow
```

### ローカルテスト

`vercel dev` でローカル環境で Vercel のシミュレーション環境を起動し、本番と同じ条件で動作確認を行います：

```bash
vercel dev
```

この際、ローカルでは動作するが本番で 502 が出ている場合、以下を確認してください：

- [環境変数](/glossary/環境変数/)が本番環境で正しく設定されているか（Vercel [ダッシュボード](/glossary/ダッシュボード/)の Settings > Environment Variables）
- 関数のメモリー設定が不足していないか
- 外部 [API](/glossary/api/) のホワイトリスト設定に本番[ドメイン](/glossary/ドメイン/)が含まれているか

### 公式ドキュメントの参照

- [Vercel Serverless Functions Documentation](https://vercel.com/docs/functions/serverless-functions)
- [Error Status Codes](https://vercel.com/docs/errors)
- [Building and Deploying with Vercel](https://vercel.com/docs/projects/overview)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*