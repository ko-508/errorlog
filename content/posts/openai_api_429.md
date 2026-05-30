---
title: "OpenAI API の 429 エラー：原因と解決策"
date: 2026-05-24
description: "429エラーは、OpenAI APIのレート制限に達したときに返されるToo Many Requestsを意味します。OpenAI APIは、API キーごとにTPM（1分あたりのトークン数）やRPM（1分あたりのリクエスト数）に上限を設定"
tags: ["OpenAI API"]
errorCode: "429"
lastmod: 2026-05-31
---

## エラーの概要

429エラーは、OpenAI [API](/glossary/api/)の[レート制限](/glossary/レート制限/)に達したときに返される**Too Many Requests**を意味します。OpenAI [API](/glossary/api/)は、[API](/glossary/api/) キーごとにTPM（1分あたりの[トークン](/glossary/トークン/)数）やRPM（1分あたりの[リクエスト](/glossary/リクエスト/)数）に上限を設定しており、この制限を超過するとこのエラーが発生します。本番環境での動作停止につながるため、早期の対応が重要です。

## 実際のエラーメッセージ例

```json
{
  "error": {
    "message": "Rate limit exceeded. Retrying after 10 seconds. 100 requests per minute limit reached.",
    "type": "rate_limit_error",
    "param": null,
    "code": "rate_limit_exceeded"
  }
}
```

```python
openai.error.RateLimitError: Rate limit exceeded for gpt-4 in organization <your-org-id> on tokens per min. Limit: 40000, Used: 40200, Requested: 500. Please try again in 1m2s.
```

## よくある原因と解決手順

### 原因1：1分間のトークン数制限（TPM）超過

OpenAI [API](/glossary/api/)の有料プランでは、1分あたりの利用[トークン](/glossary/トークン/)数に上限があります。長いテキストの一括処理や並行[リクエスト](/glossary/リクエスト/)が多いと、この制限に達します。

**Before（エラーが起きるコード）**
```python
import openai

messages = [{"role": "user", "content": very_long_text} for _ in range(100)]

for msg in messages:
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[msg],
        max_tokens=2000
    )
    print(response)
```

**After（修正後）**
```python
import openai
import time

messages = [{"role": "user", "content": very_long_text} for _ in range(100)]

for i, msg in enumerate(messages):
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[msg],
        max_tokens=2000
    )
    print(response)
    
    if (i + 1) % 10 == 0:
        time.sleep(60)  # 1分待機してTPMリセット
```

### 原因2：リクエスト数上限（RPM）超過

OpenAI [API](/glossary/api/)のフリープランでは、1分あたりの[リクエスト](/glossary/リクエスト/)数が制限されています。並行処理やループ処理で多くの[リクエスト](/glossary/リクエスト/)を短時間に送信するとこの制限に達します。

**Before（エラーが起きるコード）**
```python
import concurrent.futures
import openai

def call_api(prompt):
    return openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )

prompts = [f"質問{i}" for i in range(50)]

with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
    results = list(executor.map(call_api, prompts))
```

**After（修正後）**
```python
import openai
import time

def call_api_with_retry(prompt, max_retries=3):
    for attempt in range(max_retries):
        try:
            return openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}]
            )
        except openai.error.RateLimitError:
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) + 1  # 指数バックオフ
                time.sleep(wait_time)
            else:
                raise

prompts = [f"質問{i}" for i in range(50)]

for prompt in prompts:
    result = call_api_with_retry(prompt)
    time.sleep(1.2)  # RPM制限を考慮して遅延
```

### 原因3：APIキーが異なる組織に属している

複数の組織に属する[API](/glossary/api/)キーを使う場合、リクエストヘッダーで指定した組織の[レート制限](/glossary/レート制限/)が適用されます。期待する組織ではなく別の組織として認識されると、その組織の低い制限に引っかかります。

**Before（エラーが起きるコード）**
```python
import openai

openai.api_key = "<your-api-key>"
# 組織を指定していない場合、デフォルト組織の制限が適用される

response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}]
)
```

**After（修正後）**
```python
import openai

openai.api_key = "<your-api-key>"
openai.organization = "<your-org-id>"  # 明示的に組織を指定

response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}]
)
```

## OpenAI API 固有の注意点

**[レート制限](/glossary/レート制限/)の種類の確認**
OpenAI [API](/glossary/api/)には複数の制限レイヤーがあります。`x-ratelimit-limit-tokens`、`x-ratelimit-remaining-tokens`、`x-ratelimit-reset-tokens`の各レスポンスヘッダーを確認することで、現在の利用状況を把握できます。

```python
response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "test"}]
)

# レート制限情報を確認
print(f"Remaining tokens: {response['headers'].get('x-ratelimit-remaining-tokens')}")
print(f"Reset time: {response['headers'].get('x-ratelimit-reset-tokens')}")
```

**[モデル](/glossary/モデル/)ごとの異なる制限**
`gpt-4`、`gpt-3.5-turbo`、`text-embedding-3-large`など、[モデル](/glossary/モデル/)によってレート制限値が異なります。設定ページで各[モデル](/glossary/モデル/)の現在の制限を確認し、使用する[モデル](/glossary/モデル/)を選択してください。

**[リクエスト](/glossary/リクエスト/)単位の[トークン](/glossary/トークン/)削減**
長文を処理する際は、事前に`max_tokens`[パラメータ](/glossary/パラメータ/)を調整するか、入力テキストを分割して複数回の[リクエスト](/glossary/リクエスト/)に分散させることで、1回あたりの[トークン](/glossary/トークン/)消費を削減できます。

## それでも解決しない場合

**ログとメトリクスの確認**
OpenAI [API](/glossary/api/)[ダッシュボード](/glossary/ダッシュボード/)の「Usage」ページで、実際の使用[トークン](/glossary/トークン/)数と制限値をリアルタイムで確認できます。エラーが発生した時間帯のグラフから、何がトリガーになったかを特定しましょう。

**公式ドキュメント**
[Rate limits - OpenAI API](https://platform.openai.com/docs/guides/rate-limits)では、プラン別の具体的な制限値と対処方法が記載されています。

**サポートへの問い合わせ**
制限値の引き上げが必要な場合は、OpenAI [API](/glossary/api/)の[ダッシュボード](/glossary/ダッシュボード/)内の「Help」セクションから公式サポートに連絡できます。利用用途と予想利用量を明記することで、上限引き上げの審査が加速します。

**GitHub Issues**
同じ問題を抱えるエンジニア同士が情報を共有できるOpenAI Python ライブラリの[Issues](https://github.com/openai/openai-python/issues)では、より詳細な回避策が議論されていることがあります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*