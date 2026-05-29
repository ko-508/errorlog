---
title: "OpenAI API の 502 エラー：原因と解決策"
date: 2026-05-24
description: "OpenAI API の 502 エラーの原因と解決策をわかりやすく解説します。"
tags: ["OpenAI API"]
errorCode: "502"
lastmod: 2026-05-29
---

## エラーの概要

502 Bad Gateway は、OpenAI [API](/glossary/api/) の[リクエスト](/glossary/リクエスト/)がOpenAIのサーバーに到達したものの、バックエンドサーバーから無効な応答が返された、または[タイムアウト](/glossary/タイムアウト/)したことを示します。このエラーはOpenAI側のインフラストラクチャ問題、[ネットワーク](/glossary/ネットワーク/)接続の問題、または[リクエスト](/glossary/リクエスト/)自体の問題が原因となります。OpenAI [API](/glossary/api/) を使用するアプリケーションではランダムに発生することがあり、一時的な問題であることが多いです。

## 実際のエラーメッセージ例

```json
{
  "error": {
    "message": "The server had an error while processing your request. Unexpected end of JSON input",
    "type": "server_error",
    "param": null,
    "code": "502"
  }
}
```

```bash
curl -X POST https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4","messages":[{"role":"user","content":"Hello"}]}'
# HTTP/1.1 502 Bad Gateway
# {"error":{"message":"BadGateway","type":"server_error","code":"502"}}
```

## よくある原因と解決手順

### 原因1：OpenAI側のサーバーメンテナンスまたは障害

**なぜ発生するか：** OpenAIは定期的にシステムメンテナンスを実施しており、その間は[API](/glossary/api/)全体が 502 を返すことがあります。また、予期しないサービス障害が発生することもあります。

**Before（エラーが起きる状態）：**
```python
import openai

openai.api_key = "sk-xxxxx"
response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}]
)
# 502 BadGateway エラー発生
```

**After（修正後）：**
```python
import openai
import time
from requests.exceptions import HTTPError

openai.api_key = "sk-xxxxx"

def call_openai_with_retry(max_retries=3, backoff_factor=2):
    for attempt in range(max_retries):
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "user", "content": "Hello"}]
            )
            return response
        except openai.error.APIError as e:
            if e.http_status == 502 and attempt < max_retries - 1:
                wait_time = backoff_factor ** attempt
                print(f"502エラー。{wait_time}秒後に再試行します")
                time.sleep(wait_time)
            else:
                raise

response = call_openai_with_retry()
```

解決手順：OpenAI のステータスページ（https://status.openai.com）を確認し、現在メンテナンス中かどうか確認してください。メンテナンス中の場合は、サービスが復旧するまで数分から数時間待機が必要です。

### 原因2：APIリクエストのタイムアウトまたは大型ペイロード

**なぜ発生するか：** OpenAI [API](/glossary/api/) のデフォルトタイムアウトは30秒です。[レスポンス](/glossary/レスポンス/)の生成に時間がかかる[リクエスト](/glossary/リクエスト/)、または非常に大きなテキストを含む[リクエスト](/glossary/リクエスト/)は、[バックエンド](/glossary/バックエンド/)が[タイムアウト](/glossary/タイムアウト/)してしまい 502 を返します。

**Before（エラーが起きる設定）：**
```python
import openai

# 非常に長いプロンプトを送信
long_prompt = "Tell me a story " * 5000

response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[{"role": "user", "content": long_prompt}],
    timeout=10  # タイムアウトが短すぎる
)
```

**After（修正後）：**
```python
import openai

# プロンプトを適切なサイズに分割
prompt = "Tell me a story " * 500  # 適切なサイズに調整

response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[{"role": "user", "content": prompt}],
    timeout=60,  # タイムアウトを十分に確保
    temperature=0.7
)
```

解決手順：リクエストペイロードを確認し、プロンプトの[トークン](/glossary/トークン/)数が models の上限内であることを確認してください。`max_tokens` [パラメータ](/glossary/パラメータ/)を明示的に設定し、予期しない応答生成の遅延を避けてください。

### 原因3：API キーの有効期限切れまたは無効な認証情報

**なぜ発生するか：** OpenAI [API](/glossary/api/) キーが無効、期限切れ、または権限がない場合、ゲートウェイレベルで処理が中断され 502 が返されることがあります。特に組織のシステム管理によって [API](/glossary/api/) キーが無効化された場合に発生します。

**Before（問題のあるコード）：**
```python
import openai

# 古いまたは無効なAPIキー
openai.api_key = "sk-oldkey123456"

response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}]
)
# 認証エラー → 502で返される可能性
```

**After（修正後）：**
```python
import openai
import os
from datetime import datetime

# 環境変数から取得し、有効性を確認
api_key = os.getenv("OPENAI_API_KEY")
if not api_key or len(api_key) < 20:
    raise ValueError("OPENAI_API_KEY が設定されていないか無効です")

openai.api_key = api_key

# リクエスト前に簡易検証
try:
    openai.Model.list()  # API キーの有効性確認
except openai.error.AuthenticationError:
    print("API キーが無効です。新しいキーを取得してください")
    raise

response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}]
)
```

解決手順：OpenAI の Web [コンソール](/glossary/コンソール/)（https://platform.openai.com/api-keys）にアクセスし、API キーの有効性を確認してください。必要に応じて新しいキーを生成し、[環境変数](/glossary/環境変数/)を更新してください。

## ツール固有の注意点

### OpenAI API 固有の原因と対策

**[レート制限](/glossary/レート制限/)との混同：** 429（Too Many Requests）ではなく 502 が返される場合、[リクエスト](/glossary/リクエスト/)間隔の設定を見直してください。同時に複数の[リクエスト](/glossary/リクエスト/)を送信していないか確認し、シーケンシャル処理に変更してください。

```python
import openai
import time

messages_list = [
    [{"role": "user", "content": "Question 1"}],
    [{"role": "user", "content": "Question 2"}]
]

for messages in messages_list:
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=messages
    )
    print(response.choices[0].message.content)
    time.sleep(1)  # リクエスト間隔を確保
```

**ネットワークプロキシの設定：** 企業[ネットワーク](/glossary/ネットワーク/)経由でアクセスする場合、[プロキシ](/glossary/プロキシ/)設定が502を引き起こすことがあります。

```python
import openai
import os

# プロキシ設定を明示
os.environ['HTTP_PROXY'] = 'http://proxy.company.com:8080'
os.environ['HTTPS_PROXY'] = 'http://proxy.company.com:8080'

openai.api_key = "sk-xxxxx"
response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}]
)
```

## それでも解決しない場合

**ログ確認とデバッグ方法：**

OpenAI Python [SDK](/glossary/sdk/) の詳細ログを有効にして、実際の[HTTP](/glossary/http/)[リクエスト](/glossary/リクエスト/)を確認してください。

```python
import openai
import logging

logging.basicConfig(level=logging.DEBUG)
openai.api_key = "sk-xxxxx"

# 以下のリクエストで詳細なHTTPログが出力される
response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}]
)
```

**確認すべき項目：**
- OpenAI のステータスページ（https://status.openai.com）で全体障害の有無を確認
- [API](/glossary/api/) キーの有効性を OpenAI [コンソール](/glossary/コンソール/)で確認
- 料金がマイナスになっていないか確認（課金の停止）
- [リクエスト](/glossary/リクエスト/)のコンテンツサイズと含まれる[トークン](/glossary/トークン/)数を確認

**公式ドキュメント参照：**
- Error Codes ページ（https://platform.openai.com/docs/guides/error-codes）
- [API](/glossary/api/) Reference（https://platform.openai.com/docs/api-reference）

**コミュニティリソース：**
- OpenAI Community Forum（https://community.openai.com）
- GitHub Issues（openai/openai-python [リポジトリ](/glossary/リポジトリ/)）

一時的な 502 エラーは通常、指数[バックオフ](/glossary/バックオフ/)を含む再試行ロジックで自動的に解決します。何度も発生する場合は、OpenAI のサポートに問い合わせてください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*