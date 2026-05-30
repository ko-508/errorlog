---
title: "Gemini API の 429 エラー：無料枠クォータ枯渇と解決策"
date: 2026-05-30
lastmod: 2026-05-31
description: "gemini-2.0-flashの無料枠を自動化パイプラインで使い切りRESOURCE_EXHAUSTEDが発生。モデル切り替えとリトライ実装で解決します。"
tags: ["GCP"]
---

Gemini API を自動化スクリプトやバックグラウンドジョブに組み込んだ際、無料枠のクォータを短時間で使い切り `429 RESOURCE_EXHAUSTED` が連続発生するケースがあります。特に複数リクエストを並列・連続で投げる処理では、1回のバッチ実行で当日分のクォータが尽きることがあります。

## エラーの全文

```
429 RESOURCE_EXHAUSTED. {
  'error': {
    'code': 429,
    'message': 'You exceeded your current quota, please check your plan
    and billing details.\n
    * Quota exceeded for metric:
      generativelanguage.googleapis.com/generate_content_free_tier_requests,
      limit: 0, model: gemini-2.0-flash\n
    * Quota exceeded for metric:
      generativelanguage.googleapis.com/generate_content_free_tier_input_token_count,
      limit: 0, model: gemini-2.0-flash\n
    Please retry in 48.403305959s.',
    'status': 'RESOURCE_EXHAUSTED',
    'details': [{
      '@type': 'type.googleapis.com/google.rpc.RetryInfo',
      'retryDelay': '48s'
    }]
  }
}
```

`limit: 0` はクォータ残量がゼロになったことを示します。`retryDelay` にリトライまでの待機秒数が返ってきます。

## よくある原因

### 自動化パイプラインでの連続呼び出し

30分ごとに RSS フィードを取得してスコアリングするような自動パイプラインでは、1サイクルで複数記事を連続して API に送ります。無料枠の制限は以下の2軸で管理されます。

- **RPM（Requests Per Minute）**: 1分あたりのリクエスト数
- **RPD（Requests Per Day）**: 1日あたりのリクエスト数

`gemini-2.0-flash` の無料枠は RPM=15、RPD=1,500 ですが、パイプラインを短時間に複数回再起動したり、処理対象件数が急増すると RPD を早期に消費します。

### 複数プロセスが同じ API キーを共有している

開発環境とバックグラウンドサービスが同じ `GOOGLE_API_KEY` を使っている場合、片方のリクエストが他方のクォータを消費します。

### モデル別にクォータが独立している

`gemini-2.0-flash` のクォータが尽きても `gemini-1.5-flash` のクォータは別枠です。エラーメッセージに `model: gemini-2.0-flash` と明記されているため、モデルを切り替えるだけで即時回避できるケースがあります。

## 解決手順

### 方法1：モデルを切り替える（即時対応）

クォータが別枠のモデルに切り替えます。

```python
# Before（クォータ枯渇）
response = client.models.generate_content(
    model="gemini-2.0-flash",
    contents=prompt,
    config=config,
)

# After（別枠のモデルに切り替え）
response = client.models.generate_content(
    model="gemini-1.5-flash",   # 別クォータプール
    contents=prompt,
    config=config,
)
```

| モデル | 無料 RPM | 無料 RPD | 備考 |
|--------|----------|----------|------|
| gemini-2.0-flash | 15 | 1,500 | 枯渇しやすい |
| gemini-1.5-flash | 15 | 1,500 | 別枠で利用可能 |
| gemini-1.5-flash-8b | 15 | 1,500 | より軽量 |

### 方法2：429 時にリトライ待機を実装する（恒久対応）

エラーレスポンス内の `retryDelay` を読み取り、その秒数だけ待機してからリトライします。

```python
# Before（エラーをそのまま握りつぶす）
async def _call(client, model, contents, config):
    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=model,
            contents=contents,
            config=config,
        )
        return response.text
    except Exception:
        pass  # 429 も含めて無視してしまう

# After（429 のリトライ秒数を読んで待機）
async def _call(client, model, contents, config, max_retries=2):
    for attempt in range(max_retries + 1):
        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=model,
                contents=contents,
                config=config,
            )
            return response.text
        except Exception as e:
            err = str(e)
            if "429" in err and attempt < max_retries:
                m = re.search(r'retry in (\d+)', err)
                wait = int(m.group(1)) + 3 if m else 65
                logger.warning("429 rate-limit – waiting %ds", wait)
                await asyncio.sleep(wait)
                continue
            raise
```

### 方法3：1サイクルあたりの処理件数を絞る

バックグラウンドパイプラインでは1サイクルにスコアリングする記事数を制限し、API コール間に待機を挟みます。

```python
MAX_SCORE_CYCLE = 5      # 1サイクルあたり最大5件
API_DELAY       = 4.0    # 各 API コール間の待機秒数

for i, article in enumerate(candidates[:MAX_SCORE_CYCLE]):
    if i > 0:
        await asyncio.sleep(API_DELAY)  # rate-limit guard
    score = await score_article(article.title, body)
```

## クォータ残量の確認方法

Google AI Studio のダッシュボードでリアルタイムの使用量を確認できます。エラーメッセージ内のリンク先（`https://ai.dev/rate-limit`）から直接アクセスできます。

```
To monitor your current usage, head to: https://ai.dev/rate-limit
```

翌日（UTC 0:00）にクォータがリセットされるため、RPD を使い切った場合は翌日まで待つか、有料プランに移行することで即時解消します。

## それでも解決しない場合

- **有料プランへの移行**: Google Cloud の Vertex AI 経由で使用すると RPD 制限がなくなります
- **複数 API キーのローテーション**: 異なるプロジェクトの API キーを交互に使用する（利用規約の範囲内で）
- **バッチ処理を夜間に分散**: 1日の処理をまとめて深夜に実行し、RPD の消費を1回に集中させない設計に変える

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
