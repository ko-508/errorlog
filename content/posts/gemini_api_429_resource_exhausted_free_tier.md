---
draft: true
title: "Gemini API の 429 エラー：無料枠クォータ枯渇と解決策"
date: 2026-05-30
lastmod: 2026-06-14
description: "gemini-2.0-flashの無料枠を自動化パイプラインで使い切りRESOURCE_EXHAUSTEDが発生。モデル切り替えとリトライ実装で解決します。"
tags: ["GCP"]
service: "Google Gemini API"
error_type: "429 RESOURCE_EXHAUSTED"
errorCode: "429"
components: []
related_services: ["Google API Key", "RSS"]
top_queries:
- 'free_quota_exhausted'
- 'generate_content_free_tier_requests'
---

## エラーの概要

Gemini [API](/glossary/api/)の429[エラー](/glossary/エラー/)は、[API](/glossary/api/)呼び出しのクォータ制限に達したことを示す標準的な[HTTP](/glossary/http/)[ステータスコード](/glossary/ステータスコード/)です。Gemini [API](/glossary/api/)では無料枠に1分あたりの[リクエスト](/glossary/リクエスト/)数制限と1日あたりの[リクエスト](/glossary/リクエスト/)数制限が設定されており、これを超過すると[サーバー](/glossary/サーバー/)側が[リクエスト](/glossary/リクエスト/)を拒否します。特に自動スクリプトやバッチ処理で複数の[リクエスト](/glossary/リクエスト/)を並列実行する場合、瞬時にクォータを枯渇させることがあります。

## 実際のエラーメッセージ例

**Pythonライブラリ使用時：**

```
429 RESOURCE_EXHAUSTED. {
  'error': {
    'code': 429,
    'message': 'You exceeded your current quota, please check your plan and billing details.\n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 0, model: gemini-2.0-flash\n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_tokens'
  }
}
```

**[REST](/glossary/rest/) [API](/glossary/api/)直接呼び出し時：**

```json
{
  "error": {
    "code": 429,
    "message": "Resource exhausted",
    "status": "RESOURCE_EXHAUSTED",
    "details": [
      {
        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
        "violations": [
          {
            "subject": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
            "description": "Quota exceeded for metric"
          }
        ]
      }
    ]
  }
}
```

## よくある原因と解決手順

### 原因1: 無料枠の1分あたりのリクエスト上限超過

Gemini [API](/glossary/api/)の無料枠は1分間に最大60[リクエスト](/glossary/リクエスト/)という制限があります。ループ処理やバッチスクリプトで短時間に大量[リクエスト](/glossary/リクエスト/)を送信すると、この上限に即座に達します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
import google.generativeai as genai

genai.configure(api_key="<your-api-key>")
model = genai.GenerativeModel("gemini-2.0-flash")

# 複数のプロンプトを連続実行
prompts = [f"質問{i}" for i in range(100)]
for prompt in prompts:
    response = model.generate_content(prompt)
    print(response.text)
```

**After（修正後）：**

```python
import google.generativeai as genai
import time

genai.configure(api_key="<your-api-key>")
model = genai.GenerativeModel("gemini-2.0-flash")

# 1分60リクエスト制限に対応：リクエスト間隔を1秒確保
prompts = [f"質問{i}" for i in range(100)]
for prompt in prompts:
    response = model.generate_content(prompt)
    print(response.text)
    time.sleep(1)  # 1秒待機（60リクエスト/分以下に制御）
```

### 原因2: 無料枠の1日あたりのリクエスト上限超過

無料枠では1日あたり15,000[リクエスト](/glossary/リクエスト/)という上限があります。開発[テスト](/glossary/テスト/)やデータ取得に使用し続けると、翌日まで利用できなくなります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
import google.generativeai as genai
from concurrent.futures import ThreadPoolExecutor

genai.configure(api_key="<your-api-key>")
model = genai.GenerativeModel("gemini-2.0-flash")

prompts = [f"テスト{i}" for i in range(2000)]

# 並列実行で短時間に15,000リクエストを超過
def call_api(prompt):
    return model.generate_content(prompt)

with ThreadPoolExecutor(max_workers=50) as executor:
    results = executor.map(call_api, prompts)
    for result in results:
        print(result.text)
```

**After（修正後）：**

```python
import google.generativeai as genai
import time
from datetime import datetime

genai.configure(api_key="<your-api-key>")
model = genai.GenerativeModel("gemini-2.0-flash")

prompts = [f"テスト{i}" for i in range(2000)]
REQUEST_LIMIT_PER_DAY = 15000
daily_request_count = 0

def call_api_with_limit(prompt):
    global daily_request_count
    if daily_request_count >= REQUEST_LIMIT_PER_DAY:
        print(f"[{datetime.now()}] 本日のリクエスト上限に達しました")
        return None
    
    response = model.generate_content(prompt)
    daily_request_count += 1
    return response

# 並列実行を避け、制御可能な処理に変更
for prompt in prompts:
    result = call_api_with_limit(prompt)
    if result:
        print(result.text)
    time.sleep(0.1)  # リクエスト間隔調整
```

### 原因3: 有料プランへの移行漏れ

無料枠では限られた[トークン](/glossary/トークン/)数しか使用できません。[トークン](/glossary/トークン/)数が多い長文生成やテキスト埋め込みを頻繁に行うと、クォータが枯渇します。有料プランに移行していないと、月間の制限に達すると429[エラー](/glossary/エラー/)が返されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
import google.generativeai as genai

genai.configure(api_key="<your-api-key>")
model = genai.GenerativeModel("gemini-2.0-flash")

# 大量の長文生成リクエスト（1トークン = 約4文字相当）
for i in range(500):
    prompt = "以下のテーマについて詳細に3000字以上で説明してください：" + "テーマ" * 100
    response = model.generate_content(prompt)
    print(response.text)
```

**After（修正後）：**

```python
import google.generativeai as genai
from google.api_core import exceptions

genai.configure(api_key="<your-api-key>")
model = genai.GenerativeModel("gemini-2.0-flash")

# トークン数を推定して事前チェック
def estimate_tokens(prompt):
    # 日本語は約3文字 = 1トークン、英語は約4文字 = 1トークン
    return len(prompt) // 3

# 有料プランに移行するか、リクエスト数と長さを調整
for i in range(50):  # リクエスト数を削減
    prompt = "テーマについて500字程度で説明してください"
    
    try:
        # トークン数が見積もりで制限内か確認
        tokens = estimate_tokens(prompt)
        if tokens > 1000:
            print(f"トークン数が大きい({tokens})ため、スキップします")
            continue
            
        response = model.generate_content(prompt)
        print(response.text)
    except exceptions.ResourceExhausted:
        print("クォータ超過。有料プランの利用を検討してください")
        break
```

## ツール固有の注意点

### Google Cloud Consoleでのクォータ監視

Gemini [API](/glossary/api/)のクォータ状況はGoogle Cloud Consoleで確認できます。`APIs & Services` > `Quotas` から `generativelanguage.googleapis.com` を検索し、現在の[リクエスト](/glossary/リクエスト/)数と[トークン](/glossary/トークン/)数を[リアルタイム](/glossary/リアルタイム/)で確認してください。無料枠では日次リセットが午前0時（UTC）に行われます。

### 有料プランの段階的な価格設定

無料枠を超える場合は、有料プラン（従量課金制）への移行が必要です。Gemini 2.0 Flashは1ドル = 400,000入力[トークン](/glossary/トークン/) / 1,200,000出力[トークン](/glossary/トークン/)で課金されます。毎月1ドル分の無料枠が付与されるため、軽度の利用であれば実質無料で続行できます。

### リトライロジックの実装

429[エラー](/glossary/エラー/)が返された場合、Exponential Backoffを用いた[リトライ](/glossary/リトライ/)が有効です。ただし無料枠枯渇の場合は、[リトライ](/glossary/リトライ/)しても日時リセット（UTC午前0時）まで解決しません。

**リトライロジック例：**

```python
import time
import google.generativeai as genai
from google.api_core import exceptions

genai.configure(api_key="<your-api-key>")
model = genai.GenerativeModel("gemini-2.0-flash")

def call_with_retry(prompt, max_retries=3):
    for attempt in range(max_retries):
        try:
            return model.generate_content(prompt)
        except exceptions.ResourceExhausted:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 指数バックオフ：1秒、2秒、4秒
                print(f"クォータ超過。{wait_time}秒後に再試行します")
                time.sleep(wait_time)
            else:
                raise

response = call_with_retry("テストプロンプト")
```

## それでも解決しない場合

### 確認すべき項目とログ

1. **Google Cloud Consoleのクォータ表示**：Quotasセクションで `generativelanguage.googleapis.com/generate_content_free_tier_requests` と `generativelanguage.googleapis.com/generate_content_free_tier_tokens` の現在値を確認してください。

2. **[API](/glossary/api/)キーの有効性確認**：複数の[API](/glossary/api/)キーを使用している場合、別のキーで試行して、キー単位のクォータ制限か全体の制限かを判別します。

3. **リージョン別制限**：Gemini [API](/glossary/api/)は全リージョン共通のクォータを持つため、複数プロジェクトやリージョンからの同時[リクエスト](/glossary/リクエスト/)は累算されます。

### 公式リソース

- [Google Gemini API公式ドキュメント：Rate limits and quotas](https://ai.google.dev/gemini-api/docs/rate-limits)
- [Google Cloud Console：Quotas and System Limits](https://cloud.google.com/docs/quotas)
- [Gemini API有料プラン詳細](https://ai.google.dev/pricing)

### コミュニティサポート

Gemini [API](/glossary/api/)に関する問題は、[Google AI Stack Overflow](https://stackoverflow.com/questions/tagged/gemini-api)や[Google Cloud Community Forums](https://www.googlecloudcommunity.com/)で質問できます。スクリーンショット付きで現在のクォータ使用状況を共有すると、より的確な回答が得られます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*