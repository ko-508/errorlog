---
draft: true
title: "OpenAI API の 401 エラー：原因と解決策"
date: 2026-05-24
description: "OpenAI APIで401エラーが返される場合、リクエストの認証に失敗したことを意味します。これは提供されたAPIキーが無効、期限切れ、または不正な形式であることを示しており、APIサーバーがクライアントの身元を確認できない状態です。"
tags: ["OpenAI API"]
errorCode: "401"
lastmod: 2026-05-31
service: "OpenAI API"
error_type: "401"
components: []
related_services: ["OpenAI ダッシュボード"]
top_queries:
- 'authorizationfailed: openai: 401 unauthorized: user is not authenticated'
- 'openai 401'
---

## エラーの概要

OpenAI [API](/glossary/api/)で401[エラー](/glossary/エラー/)が返される場合、[リクエスト](/glossary/リクエスト/)の[認証](/glossary/認証/)に失敗したことを意味します。これは提供された[API](/glossary/api/)キーが無効、期限切れ、または不正な形式であることを示しており、[API](/glossary/api/)[サーバー](/glossary/サーバー/)がクライアントの身元を確認できない状態です。OpenAI [API](/glossary/api/)を使用するほぼすべての[アプリケーション](/glossary/アプリケーション/)で発生する可能性があり、特に初期設定時や[環境変数](/glossary/環境変数/)の変更後に頻出します。

## 実際のエラーメッセージ例

```json
{
  "error": {
    "message": "Incorrect API key provided. You passed sk-..., but an API key should start with 'sk-' and contain 48 characters.",
    "type": "invalid_request_error",
    "param": null,
    "code": "invalid_api_key"
  }
}
```

```bash
curl https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer sk-invalid" \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}'

# レスポンス:
# {"error":{"message":"Incorrect API key provided...","type":"invalid_request_error","code":"invalid_api_key"}}
```

## よくある原因と解決手順

### 原因1：APIキーが正しくコピーされていない

OpenAI [ダッシュボード](/glossary/ダッシュボード/)からコピーした[API](/glossary/api/)キーに含まれる空白文字や改行が混在すると、[認証](/glossary/認証/)に失敗します。また、キーの一部だけをコピーすることも考えられます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**
```python
import openai

# ダッシュボードからのコピー時に空白が含まれている
openai.api_key = "sk-proj-abc123... "  # 末尾に空白がある

response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}]
)
```

**After（修正後）：**
```python
import openai

# .strip()で前後の空白を削除
api_key = "sk-proj-abc123def456ghi789".strip()
openai.api_key = api_key

response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}]
)
```

### 原因2：環境変数が正しく設定されていない

.envファイルや[環境変数](/glossary/環境変数/)の設定で、OPENAI_[API](/glossary/api/)_KEYが指定されていないか、間違った値が保存されている場合があります。

**Before（[エラー](/glossary/エラー/)が起きる設定）：**
```bash
# .env ファイル（間違い例）
OPENAI_API_KEY=sk-proj-  # 不完全
# または環境変数が設定されていない
```

**After（修正後）：**
```bash
# .env ファイル（正しい例）
OPENAI_API_KEY=<your-api-key>

# または実行時に確認
export OPENAI_API_KEY="<your-api-key>"
echo $OPENAI_API_KEY  # 値が表示されることを確認
```

### 原因3：APIキーが有効期限切れまたは削除されている

OpenAI [ダッシュボード](/glossary/ダッシュボード/)からキーを手動で削除したり、組織の管理者が無効化した場合、そのキーでの[リクエスト](/glossary/リクエスト/)は401で拒否されます。

**Before（[エラー](/glossary/エラー/)が起きる状況）：**
```javascript
// 以前作成したキーを使用している
const apiKey = "sk-proj-oldkey123"; // ダッシュボードで削除済み

const response = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
        "Authorization": `Bearer ${apiKey}`,
        "Content-Type": "application/json"
    },
    body: JSON.stringify({
        model: "gpt-4",
        messages: [{ role: "user", content: "Hello" }]
    })
});
```

**After（修正後）：**
```javascript
// OpenAI ダッシュボード (https://platform.openai.com/account/api-keys) で
// 新しいAPIキーを生成し使用する
const apiKey = "sk-proj-newkey456"; // 新規生成したキー

const response = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
        "Authorization": `Bearer ${apiKey}`,
        "Content-Type": "application/json"
    },
    body: JSON.stringify({
        model: "gpt-4",
        messages: [{ role: "user", content: "Hello" }]
    })
});

const data = await response.json();
console.log(data);
```

### 原因4：Authorizationヘッダーの形式が誤っている

OpenAI [API](/glossary/api/)は`Authorization: Bearer <api_key>`という形式を要求します。単なる`api_key`の値を[ヘッダー](/glossary/ヘッダー/)に含めるだけでは[認証](/glossary/認証/)されません。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**
```yaml
# 間違ったヘッダー形式
curl https://api.openai.com/v1/chat/completions \
  -H "Authorization: sk-proj-abc123def456" \  # Bearerが無い
  -H "Content-Type: application/json"
```

**After（修正後）：**
```yaml
# 正しいヘッダー形式
curl https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer sk-proj-abc123def456" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4","messages":[{"role":"user","content":"Hello"}]}'
```

## ツール固有の注意点

OpenAI [API](/glossary/api/)は複数の認証方法をサポートしていますが、主流のシナリオに固有の設定ポイントがあります。

**組織[ID](/glossary/id/)の設定が必要な場合：**
OpenAIの組織[アカウント](/glossary/アカウント/)配下で[API](/glossary/api/)キーを使用する場合、単なる[API](/glossary/api/)キーでは[認証](/glossary/認証/)に失敗することがあります。この場合、`OpenAI-Organization`[ヘッダー](/glossary/ヘッダー/)も同時に送信する必要があります。

```python
import openai

openai.api_key = "sk-proj-abc123..."
openai.organization = "org-xyz789"  # 組織IDを設定

response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}]
)
```

**Proxy経由での[リクエスト](/glossary/リクエスト/)：**
企業[ネットワーク](/glossary/ネットワーク/)環境で[プロキシ](/glossary/プロキシ/)を経由する場合、[プロキシ](/glossary/プロキシ/)[認証](/glossary/認証/)が必要になる場合があり、これがOpenAI [API](/glossary/api/)の[認証](/glossary/認証/)と重複して401[エラー](/glossary/エラー/)になることがあります。[プロキシ](/glossary/プロキシ/)の認証情報を適切に設定し、OpenAI [API](/glossary/api/)キーは[環境変数](/glossary/環境変数/)として分離して管理してください。

**複数キーの管理：**
[テスト](/glossary/テスト/)環境と本番環境で異なる[API](/glossary/api/)キーを使用する場合、設定を切り替え忘れて間違ったキーを使用するケースが多発します。環境別に.envファイルを分けるか、[設定ファイル](/glossary/設定ファイル/)で明示的に管理することを推奨します。

## それでも解決しない場合

**確認すべきポイント：**
1. OpenAI公式[ダッシュボード](/glossary/ダッシュボード/)（https://platform.openai.com/account/api-keys）にログインし、APIキーが有効な状態か確認してください。
2. キーの作成日時と現在日時を比較し、有効期限を超えていないか確認します。
3. [環境変数](/glossary/環境変数/)が実際に読み込まれているか、[デバッグ](/glossary/デバッグ/)で出力して確認してください。`echo $OPENAI_API_KEY`（Linux/Mac）または`echo %OPENAI_API_KEY%`（Windows）で検証できます。

**公式ドキュメント：**
OpenAI公式の「Authentication」ページ（https://platform.openai.com/docs/guides/authentication）にAPIキー管理の詳細が記載されています。特に「API keys」セクションで有効期限設定やキー作成手順を確認できます。

**コミュニティリソース：**
OpenAI Community Forum（https://community.openai.com）やGitHub Issues（https://github.com/openai/openai-python/issues）で同様の事例が報告されていることが多いため、エラーメッセージをそのまま検索すると解決策が見つかる可能性があります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*