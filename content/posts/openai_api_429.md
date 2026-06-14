---
title: "OpenAI API の 429 エラー：原因と解決策"
date: 2026-05-24
description: "429エラーは、OpenAI APIのレート制限に達したときに返されるToo Many Requestsを意味します。OpenAI APIは、API キーごとにTPM（1分あたりのトークン数）やRPM（1分あたりのリクエスト数）に上限を設定"
tags: ["OpenAI API"]
errorCode: "429"
lastmod: 2026-06-14
service: "OpenAI API"
error_type: "429"
components: []
related_services: []
---

## エラーの概要

429エラーは、OpenAI APIのレート制限に達したときに返される**Too Many Requests**を意味します。OpenAI APIは、APIキーごとにTPM（1分あたりのトークン数）やRPM（1分あたりのリクエスト数）に上限を設定しており、この制限を超過するとこのエラーが発生します。本番環境での動作停止につながるため、早期の対応が重要です。

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
RateLimitError: Error code: 429 - {'error': {'message': 'You exceeded your current quota, please check your plan and billing settings.', 'type': 'server_error', 'param': None, 'code': 'quota_limit_exceeded'}}
```

## よくある原因と解決手順

### 原因1：短時間に過度なリクエストを送信している

複数のユーザーリクエストを同時並行処理したり、バッチ処理で大量のAPI呼び出しを行ったりすると、RPM（1分あたりのリクエスト数）制限に引っかかります。特に、ループ内で無制限にAPIを呼び出す実装が該当します。

**Before（エラーが起きるコード）：**

```python
import openai

# 大量のテキストを一気に処理
texts = ["質問1", "質問2", "質問3", ... "質問100"]
for text in texts:
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": text}]
    )
    print(response)
```

**After（修正後）：**

```python
import openai
import time

texts = ["質問1", "質問2", "質問3", ... "質問100"]
for i, text in enumerate(texts):
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": text}]
    )
    print(response)
    
    # リクエスト間に遅延を挿入（例：0.5秒）
    if i < len(texts) - 1:
        time.sleep(0.5)
```

### 原因2：トークン数の制限を超過している

RPM制限に引っかからなくても、TPM（1分あたりのトークン数）制限に到達することがあります。長いコンテキストを含むリクエストや、複数の並行リクエストで累積トークン数が上限を超える場合です。

**Before（エラーが起きるコード）：**

```python
import openai
from concurrent.futures import ThreadPoolExecutor

# 長い文脈を同時に複数送信
long_context = "..." * 1000  # 非常に長い文脈

def call_api(prompt):
    return openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": long_context + prompt}]
    )

# 10個のスレッドで同時実行
with ThreadPoolExecutor(max_workers=10) as executor:
    results = list(executor.map(call_api, prompts))
```

**After（修正後）：**

```python
import openai
import time

# 文脈をチャンクに分割し、逐次処理
chunks = [long_context[i:i+500] for i in range(0, len(long_context), 500)]

for chunk in chunks:
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": chunk}]
    )
    print(response)
    time.sleep(1)  # リクエスト間に遅延を設定
```

### 原因3：アカウントの利用上限（クォータ）に達している

APIキーのクォータが設定額に達したり、無料トライアルの期限が切れたりすると、「quota_limit_exceeded」というコードで429エラーが返されます。

**Before（エラーが起きるコード）：**

```python
import openai

# 利用上限に達したまま実行
response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}]
)
```

**After（修正後）：**

```python
# 1. OpenAI Dashboardでクォータと利用状況を確認
# https://platform.openai.com/account/billing/overview

# 2. 必要に応じて有料プランにアップグレード
# または月額使用上限を引き上げる

# 3. Retry-Afterヘッダーを参照して自動リトライアロジックを実装
import openai
import time

max_retries = 3
retry_count = 0

while retry_count < max_retries:
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}]
        )
        break
    except openai.error.RateLimitError as e:
        # レスポンスヘッダーからRetry-Afterを取得
        retry_after = int(e.headers.get("retry-after", 60))
        print(f"{retry_after}秒待機してリトライします")
        time.sleep(retry_after)
        retry_count += 1
```

## OpenAI API固有の注意点

### レート制限の段階的な引き上げ

OpenAIの無料トライアルアカウントやPaymentMethodを登録していないアカウントは、デフォルトで低いRPM/TPM制限が設定されています。実運用環境では、OpenAI Dashboard（https://platform.openai.com/account/rate-limits）でリクエスト上限をリアルタイム確認し、必要に応じてサポートに増加を申請してください。有料プランでも、利用量が少ないうちは自動的に上限が引き上げられます。

### exponential backoff の実装推奨

OpenAI公式ドキュメントでは、429エラーの際に**Exponential Backoff**（指数バックオフ）を用いたリトライアロジックを推奨しています。単純な固定遅延ではなく、試行回数に応じて待機時間を増加させることで、サーバー負荷を軽減しつつ成功率を高めます。

```python
import openai
import random
import time

def create_completion_with_backoff(prompt, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}]
            )
            return response
        except openai.error.RateLimitError:
            if attempt == max_retries - 1:
                raise
            # 2^attempt秒 + ランダムな遅延
            wait_time = 2 ** attempt + random.uniform(0, 1)
            print(f"Attempt {attempt + 1}: {wait_time:.2f}秒待機")
            time.sleep(wait_time)
```

### APIバージョンの確認

openai-python ライブラリのバージョンが古い場合、レート制限に関する情報が正しく返されないことがあります。`pip install --upgrade openai` で最新版に更新してください。v1.0以降では、例外処理のAPI仕様が変わっているため注意が必要です。

## それでも解決しない場合

### デバッグ方法

1. **現在のレート制限を確認**：OpenAI Dashboard の Rate Limits ページで、APIキーのTPM/RPM設定値と実際の利用状況をリアルタイム確認してください。

2. **リクエストログを有効化**：openai-python ライブラリで、以下の環境変数を設定するとHTTPリクエスト/レスポンスの詳細がログに出力されます：

```bash
export OPENAI_LOG=debug
```

3. **Retry-Afterヘッダーを確認**：レスポンスヘッダーに含まれる`Retry-After`値に従い、そこまで待機してからリトライしてください。

### 公式リソース

- **OpenAI Rate Limit ドキュメント**：https://platform.openai.com/docs/guides/rate-limits
- **API ステータスページ**：https://status.openai.com/ （システム障害を確認）
- **請求ページ**：https://platform.openai.com/account/billing/overview （クォータと使用状況を確認）
- **GitHub Issues**：openai-python リポジトリのissueセクション（同じ問題の報告や回避策の議論を参照）

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*