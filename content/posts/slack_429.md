---
title: "Slack の 429 エラー：原因と解決策"
date: 2026-05-28
description: "短時間に送ったリクエスト数がSlack APIのレート制限を超えた。ループ処理の中でAPIを呼び出す間隔を設けていないなど、Slack 429 エラーの原因と解決策を解説。"
tags: ["Slack"]
errorCode: "429"
---
## Slack 429 エラーの原因と解決策

Slack [API](/glossary/api/)への[リクエスト](/glossary/リクエスト/)が短時間に集中し、[レート制限](/glossary/レート制限/)を超えた場合に発生するエラーです。429[レスポンス](/glossary/レスポンス/)が返された場合、一時的に再試行を延期する必要があります。

## よくある原因

**ループ処理内での [API](/glossary/api/) 呼び出し間隔がない**

ループで複数のメッセージ送信やユーザー情報取得を行う際、各[リクエスト](/glossary/リクエスト/)の間に待機時間を設けないと、短時間に大量の[リクエスト](/glossary/リクエスト/)が Slack [API](/glossary/api/) に到達します。Slack [API](/glossary/api/) の[レート制限](/glossary/レート制限/)は一般的にメソッドごと、時間帯ごとに設定されており、例えば chat.postMessage は 1 分間に数十～数百[リクエスト](/glossary/リクエスト/)の上限があります。待機なしで 100 件のメッセージを送信しようとすると、ほぼ確実に 429 エラーが発生します。

**[API](/glossary/api/) Tier に応じた呼び出し頻度を超過している**

Slack [API](/glossary/api/) の各メソッドは複数の Tier（Tier1 から 4 など）に分類されており、Tier ごとに分あたりの[リクエスト](/glossary/リクエスト/)上限が異なります。例えば高頻度で呼び出される Tier3 メソッドは上限が厳しく、定時実行のバッチ処理や大量ユーザー取得時に超過しやすくなります。公式ドキュメントで確認しないまま実装すると、本番環境で突然 429 エラーが増加します。

**非同期処理なしで一気に[リクエスト](/glossary/リクエスト/)を送信している**

Promise.all や for-of ループで複数の [API](/glossary/api/) 呼び出しを並列実行すると、すべての[リクエスト](/glossary/リクエスト/)がほぼ同時刻に Slack [サーバー](/glossary/サーバー/)に到達します。これは単純な順序実行よりも効率的に見えますが、Slack 側の[レート制限](/glossary/レート制限/)はセッション単位で集計されるため、並列数が多いほど制限に引っかかりやすくなります。

## 解決手順

**Retry-After [ヘッダー](/glossary/ヘッダー/)を確認して待機する**

429 [レスポンス](/glossary/レスポンス/)には Retry-After [ヘッダー](/glossary/ヘッダー/)が含まれており、何秒待つべきかが明記されています。この[ヘッダー](/glossary/ヘッダー/)値を読み出し、その秒数待ってから再試行してください。

```javascript
// Node.js + axios の例
async function callSlackAPIWithRetry(url, data) {
  try {
    const response = await axios.post(url, data, {
      headers: { Authorization: `Bearer <your-bot-token>` }
    });
    return response.data;
  } catch (error) {
    if (error.response?.status === 429) {
      const retryAfter = parseInt(error.response.headers['retry-after'], 10);
      console.log(`レート制限に達しました。${retryAfter}秒待機します。`);
      await new Promise(resolve => setTimeout(resolve, retryAfter * 1000));
      return callSlackAPIWithRetry(url, data); // 再試行
    }
    throw error;
  }
}
```

**各メソッドの [API](/glossary/api/) Tier を確認し、呼び出し間隔を設定する**

Slack 公式ドキュメント（https://api.slack.com/methods）で対象メソッドの Tier を確認し、推奨呼び出し頻度に合わせて間隔を設けます。例えば Tier2 メソッドの場合、1 [リクエスト](/glossary/リクエスト/)あたり最低 100～200 ミリ秒の間隔を目安にしてください。

```python
# Python + slack-sdk の例
import time
from slack_sdk import WebClient

client = WebClient(token='<your-bot-token>')
user_ids = ['U123456', 'U234567', 'U345678']

# Tier2 メソッドの場合、200 ミリ秒の間隔を設定
for user_id in user_ids:
    try:
        response = client.users_info(user=user_id)
        print(f"取得成功: {response['user']['name']}")
    except Exception as e:
        print(f"エラー: {e}")
    
    time.sleep(0.2)  # 200 ミリ秒待機
```

**メッセージ送信をキューで処理する**

大量のメッセージ送信が必要な場合、キューイング方式を導入し、複数の[リクエスト](/glossary/リクエスト/)を連続的に（並列でなく）処理します。これにより短時間のピークを避けられます。

```python
# Python + asyncio を使用した例
import asyncio
from slack_sdk.web.async_client import AsyncWebClient

async def send_messages_with_queue(channel_ids, message):
    client = AsyncWebClient(token='<your-bot-token>')
    
    for channel in channel_ids:
        try:
            await client.chat_postMessage(channel=channel, text=message)
            print(f"送信成功: {channel}")
        except Exception as e:
            print(f"エラー: {e}")
        
        # 各送信後に 500 ミリ秒待機
        await asyncio.sleep(0.5)

# 使用例
channels = ['C123456', 'C234567', 'C345678']
asyncio.run(send_messages_with_queue(channels, 'Hello Slack'))
```

## それでも解決しない場合

Retry-After [ヘッダー](/glossary/ヘッダー/)の値を正しく読み込んでいるか確認してください。また、複数のボットやアプリケーションが同一[ワークスペース](/glossary/ワークスペース/)の Slack [API](/glossary/api/) を呼び出している場合、合計の[リクエスト](/glossary/リクエスト/)数が制限を超える可能性があります。その場合は、[API](/glossary/api/) 呼び出し側の集約や Slack [API](/glossary/api/) の使用パターン見直しが必要です。Slack 公式サポート（https://slack.com/help）に詳細なレート制限情報を問い合わせることもできます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*