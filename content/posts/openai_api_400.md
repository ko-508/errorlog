---
title: "OpenAI API の 400 エラー：原因と解決策"
date: 2026-05-24
description: "OpenAI APIで400エラーが返される場合、リクエストの形式または内容に問題があることを示します。これは「Bad Request」と呼ばれ、サーバー側の問題ではなく、クライアント（あなたのコード）から送信されたリクエストが仕様に合致し"
tags: ["OpenAI API"]
errorCode: "400"
lastmod: 2026-05-31
---

## エラーの概要

OpenAI [API](/glossary/api/)で400エラーが返される場合、[リクエスト](/glossary/リクエスト/)の形式または内容に問題があることを示します。これは「Bad Request」と呼ばれ、[サーバー](/glossary/サーバー/)側の問題ではなく、クライアント（あなたのコード）から送信された[リクエスト](/glossary/リクエスト/)が仕様に合致していないことを意味しています。OpenAI [API](/glossary/api/)では、[リクエストボディ](/glossary/リクエストボディ/)の[JSON](/glossary/json/)形式の誤りや必須[パラメータ](/glossary/パラメータ/)の欠落、不正なフィールド値などが主な原因です。

## 実際のエラーメッセージ例

```json
{
  "error": {
    "message": "Invalid request body",
    "type": "invalid_request_error",
    "param": null,
    "code": "invalid_request_error"
  }
}
```

```json
{
  "error": {
    "message": "This model_version does not exist",
    "type": "invalid_request_error",
    "param": "model",
    "code": "invalid_request_error"
  }
}
```

## よくある原因と解決手順

### 原因1：JSONの構文エラーまたはフィールド名の誤字

[リクエストボディ](/glossary/リクエストボディ/)の[JSON](/glossary/json/)が不正な形式になっていたり、OpenAI [API](/glossary/api/)が定義していないフィールド名を使用したりすると400エラーが発生します。

**Before（エラーが起きるコード）**
```python
import openai

openai.api_key = "<your-api-key>"

response = openai.ChatCompletion.create(
    model="gpt-4",
    mesages=[  # ← typo: "mesages" は誤字
        {"role": "user", "content": "Hello"}
    ]
)
```

**After（修正後）**
```python
import openai

openai.api_key = "<your-api-key>"

response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[  # ← 正しいフィールド名
        {"role": "user", "content": "Hello"}
    ]
)
```

### 原因2：サポートされていないモデル名の指定

存在しない[モデル](/glossary/モデル/)IDや、サポートが終了した[モデル](/glossary/モデル/)を指定すると400エラーが発生します。

**Before（エラーが起きるコード）**
```bash
curl https://api.openai.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-api-key>" \
  -d '{
    "model": "gpt-4-turbo",
    "messages": [{"role": "user", "content": "Hi"}]
  }'
```

**After（修正後）**
```bash
curl https://api.openai.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-api-key>" \
  -d '{
    "model": "gpt-4-turbo-preview",
    "messages": [{"role": "user", "content": "Hi"}]
  }'
```

### 原因3：temperature、top_p、max_tokensなどのパラメータが範囲外

これらの[パラメータ](/glossary/パラメータ/)は値の範囲が定められており、範囲外の値を指定すると400エラーになります。

**Before（エラーが起きるコード）**
```javascript
const response = await fetch('https://api.openai.com/v1/chat/completions', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer <your-api-key>`
  },
  body: JSON.stringify({
    model: 'gpt-4',
    messages: [{role: 'user', content: 'test'}],
    temperature: 2.5  // ← 範囲外（0～2.0）
  })
});
```

**After（修正後）**
```javascript
const response = await fetch('https://api.openai.com/v1/chat/completions', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer <your-api-key>`
  },
  body: JSON.stringify({
    model: 'gpt-4',
    messages: [{role: 'user', content: 'test'}],
    temperature: 1.5  // ← 正しい範囲内
  })
});
```

### 原因4：messagesパラメータが空または不正な構造

messagesは配列で、各要素は必ず「role」と「content」フィールドを持つ必要があります。

**Before（エラーが起きるコード）**
```python
response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[
        {"role": "user"}  # ← "content" フィールドが欠落
    ]
)
```

**After（修正後）**
```python
response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[
        {"role": "user", "content": "What is the capital of France?"}
    ]
)
```

## OpenAI API固有の注意点

OpenAI [API](/glossary/api/)で400エラーが出る場合、以下のポイントを確認してください。

**[API](/glossary/api/)キーのフォーマット**：[API](/glossary/api/)キーがちゃんと[環境変数](/glossary/環境変数/)から読み込まれているか、文字列の前後に余計なスペースが含まれていないか確認してください。

**リクエストヘッダーの指定**：`Content-Type: application/json`と`Authorization: Bearer <api-key>`の2つの[ヘッダー](/glossary/ヘッダー/)は必須です。オフィシャルのOpenAI Pythonライブラリを使っている場合は自動で設定されますが、curlやNode.jsで直接[API](/glossary/api/)を呼び出すときは明示的に指定する必要があります。

**新しい[モデル](/glossary/モデル/)の確認**：OpenAI [API](/glossary/api/)は頻繁に新しい[モデル](/glossary/モデル/)が追加され、古い[モデル](/glossary/モデル/)はサポートが終了します。`gpt-3.5-turbo`や`gpt-4-turbo-preview`など、常に最新の有効な[モデル](/glossary/モデル/)IDを使用してください。

**streaming [パラメータ](/glossary/パラメータ/)の指定時**：`stream: true`を指定した場合、[レスポンス](/glossary/レスポンス/)の形式が異なります。ストリーミングレスポンスを正しく処理していない場合も400が発生することがあります。

## それでも解決しない場合

OpenAI [API](/glossary/api/)の公式ドキュメント「[Error codes and types](https://platform.openai.com/docs/guides/error-handling/error-codes)」で、より詳細なエラーコードと対応方法を確認できます。

また、curlで直接[API](/glossary/api/)を叩いてみることで、問題がクライアントライブラリの設定なのか、[リクエスト](/glossary/リクエスト/)自体の問題なのかを特定できます。

```bash
curl -v https://api.openai.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-api-key>" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "test"}]
  }'
```

[API](/glossary/api/)[レスポンス](/glossary/レスポンス/)の`error.param`フィールドに問題のある[パラメータ](/glossary/パラメータ/)名が記載されていることが多いため、そこから原因を特定することができます。それでも不明な場合は、OpenAI Communityフォーラムで同様の事例がないか検索するか、最新の[GitHub Issues](https://github.com/openai/openai-python/issues)を確認してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*