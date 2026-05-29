---
title: "Firebase の 502 エラー：原因と解決策"
date: 2026-05-24
description: "Firebase の 502 エラーの原因と解決策をわかりやすく解説します。"
tags: ["Firebase"]
errorCode: "502"
lastmod: 2026-05-29
---

## エラーの概要

Firebase（Cloud FunctionsやHosting）で502エラーが発生するのは、Firebaseの中継サーバーが上流の[バックエンド](/glossary/バックエンド/)（Cloud Functionsやカスタムオリジンサーバー）から不正な形式の[レスポンス](/glossary/レスポンス/)を受け取ったか、[リクエスト](/glossary/リクエスト/)が[タイムアウト](/glossary/タイムアウト/)した場合です。このエラーはクライアント側の問題ではなく、サーバー側の設定やコードに原因があることがほとんどです。

## 実際のエラーメッセージ例

```
Error: 502 Bad Gateway
The request failed because the origin is unreachable. This can happen if the origin server is down or if the origin server is configured incorrectly.
```

```json
{
  "error": {
    "code": 502,
    "message": "Bad Gateway",
    "status": "UNAVAILABLE"
  }
}
```

## よくある原因と解決手順

### 原因1：Cloud Functionsが応答を返さずに終了している

Cloud Functionsの関数が`res.send()`や`res.json()`などの[レスポンス](/glossary/レスポンス/)送信メソッドを呼び出さずに終了すると、Firebaseは[レスポンス](/glossary/レスポンス/)を受け取れず502エラーを返します。

**Before（エラーが起きる設定）:**
```javascript
exports.helloWorld = functions.https.onRequest((req, res) => {
  // 処理を実行
  const result = req.query.value * 2;
  console.log(result);
  // レスポンスを送信していない！
});
```

**After（修正後）:**
```javascript
exports.helloWorld = functions.https.onRequest((req, res) => {
  const result = req.query.value * 2;
  res.json({ result: result });
});
```

### 原因2：Cloud Functionsが実行時エラーで例外をスローしている

関数内で`throw new Error()`が実行されたり、未処理の非同期エラーが発生すると、関数は正常に終了せず502エラーになります。

**Before（エラーが起きる設定）:**
```javascript
exports.processData = functions.https.onRequest((req, res) => {
  const data = JSON.parse(req.body);
  // dataがnullの場合、次の行で例外が発生する
  const value = data.id.toString();
  res.json({ success: true });
});
```

**After（修正後）:**
```javascript
exports.processData = functions.https.onRequest((req, res) => {
  try {
    const data = JSON.parse(req.body);
    if (!data || !data.id) {
      return res.status(400).json({ error: "Invalid input" });
    }
    const value = data.id.toString();
    res.json({ success: true });
  } catch (error) {
    console.error("Error:", error);
    res.status(500).json({ error: "Internal server error" });
  }
});
```

### 原因3：Cloud Functionsがタイムアウトしている

Cloud Functionsの[タイムアウト](/glossary/タイムアウト/)時間（デフォルト60秒）を超える処理を実行すると、実行がキャンセルされて502エラーが返されます。

**Before（エラーが起きる設定）:**
```bash
gcloud functions deploy slowFunction \
  --runtime nodejs18 \
  --trigger-http
```

```javascript
exports.slowFunction = functions.https.onRequest(async (req, res) => {
  // 90秒かかる処理
  await new Promise(resolve => setTimeout(resolve, 90000));
  res.json({ message: "Done" });
});
```

**After（修正後）:**
```bash
gcloud functions deploy slowFunction \
  --runtime nodejs18 \
  --trigger-http \
  --timeout 300s
```

```javascript
exports.slowFunction = functions.https.onRequest(async (req, res) => {
  // 処理を分割するか、非同期ジョブとして実装する
  const taskRef = await admin.firestore()
    .collection('tasks')
    .add({ status: 'pending', createdAt: admin.firestore.FieldValue.serverTimestamp() });
  
  res.json({ taskId: taskRef.id });
  
  // 別途処理を実行（背景ジョブ）
});
```

### 原因4：Firebase HostingのリライトルールがCloud Functionsを指していない、または存在しない

firebase.jsonのリライトルール設定が間違っていると、Hostingが存在しない[バックエンド](/glossary/バックエンド/)に接続しようとして502エラーを返します。

**Before（エラーが起きる設定）:**
```json
{
  "hosting": {
    "rewrites": [
      {
        "source": "/api/**",
        "function": "nonExistentFunction"
      }
    ]
  }
}
```

**After（修正後）:**
```json
{
  "hosting": {
    "rewrites": [
      {
        "source": "/api/**",
        "function": "myApiFunction"
      }
    ]
  }
}
```

## Firebase固有の注意点

### Cloud Functionsのメモリと CPU設定

Cloud Functionsのメモリ割り当てが小さすぎると、大量のデータ処理中にプロセスがクラッシュして502エラーになることがあります。Firebase Consoleまたはgcloud [CLI](/glossary/cli/)で設定を確認してください。

```bash
gcloud functions deploy myFunction \
  --memory 512MB \
  --runtime nodejs18 \
  --trigger-http
```

### Firebase Hostingとカスタムオリジンの接続

Firebase Hostingでカスタムオリジンをリワイトルールに指定している場合、そのオリジンが不可達または応答が遅いと502エラーが返されます。Cloud Load BalancingやCloud Armorを経由している場合は、ファイアウォール設定も確認してください。

```json
{
  "hosting": {
    "rewrites": [
      {
        "source": "/api/**",
        "run": {
          "serviceId": "<your-cloud-run-service>"
        }
      }
    ]
  }
}
```

### CORS設定とプリフライトリクエスト

Cloud Functionsで[CORS](/glossary/cors/)対応が不十分だと、ブラウザのプリフライトOPTIONS[リクエスト](/glossary/リクエスト/)が失敗して502エラーになる場合があります。

```javascript
exports.corsFunction = functions.https.onRequest((req, res) => {
  res.set('Access-Control-Allow-Origin', '*');
  res.set('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE');
  res.set('Access-Control-Allow-Headers', 'Content-Type');
  
  if (req.method === 'OPTIONS') {
    return res.status(204).send('');
  }
  
  res.json({ message: "Success" });
});
```

## それでも解決しない場合

### ログの確認

Firebase Consoleのログ機能または以下のコマンドでCloud Functionsの詳細なエラーログを確認してください。

```bash
gcloud functions logs read <your-function-name> --limit 50
```

Cloud Loggingで詳しく検索する場合：

```bash
gcloud logging read "resource.type=cloud_function AND resource.labels.function_name=<your-function-name>" --limit 50
```

### デプロイと権限の確認

関数が[デプロイ](/glossary/デプロイ/)されているか、[IAM](/glossary/iam/)権限が正しく設定されているか確認してください。

```bash
gcloud functions list
gcloud functions describe <your-function-name>
```

### 公式ドキュメント参照

- Cloud Functionsトラブルシューティング：https://firebase.google.com/docs/functions/troubleshooting
- [HTTP](/glossary/http/)関数のベストプラクティス：https://firebase.google.com/docs/functions/http-events
- Firebase Hostingリライト設定：https://firebase.google.com/docs/hosting/full-config

### コミュニティリソース

Firebase GitHub Issues（https://github.com/firebase/firebase-tools/issues）やStack Overflowの`firebase`タグで同様の事例を検索すると、より詳しい情報が得られることがあります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*