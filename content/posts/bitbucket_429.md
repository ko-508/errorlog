---
draft: true
title: "Bitbucket の 429 エラー：原因と解決策"
date: 2026-06-16
description: "Bitbucket APIのレート制限に達した"
tags: ["Bitbucket"]
errorCode: "429"
service: "Bitbucket"
error_type: "429"
components: ["Bitbucket Cloud", "Bitbucket API", "Bitbucket Pipelines"]
related_services: ["Jenkins", "CI/CD"]
---
## エラーの概要

[HTTP](/glossary/http/) 429 [エラー](/glossary/エラー/)は「Too Many Requests」を意味し、Bitbucket [API](/glossary/api/)に対して短時間に送信された[リクエスト](/glossary/リクエスト/)が制限数を超過した場合に発生します。Bitbucket Cloud [API](/glossary/api/)は[レート制限](/glossary/レート制限/)を設けており、この上限に到達すると以降の[リクエスト](/glossary/リクエスト/)はすべて429[レスポンス](/glossary/レスポンス/)で拒否されます。デフォルトでは1時間あたり1000[リクエスト](/glossary/リクエスト/)ですが、[ワークスペース](/glossary/ワークスペース/)のプランや有料ユーザー数に応じてより高い制限が適用される場合があります。特に[CI/CD](/glossary/ci-cd/)パイプライン内で複数の並列ジョブが[API](/glossary/api/)呼び出しを実行する場合や、スクリプト内のループ処理で次々と[リクエスト](/glossary/リクエスト/)を送信する場合に頻繁に発生する現象です。

## 実際のエラーメッセージ例

Bitbucket [API](/glossary/api/)から返却される典型的な429[エラーレスポンス](/glossary/エラーレスポンス/)は以下のとおりです。

```json
{
  "type": "error",
  "error": {
    "message": "Rate limit exceeded"
  },
  "status": 429
}
```

curl[コマンド](/glossary/コマンド/)で確認した場合の[HTTP](/glossary/http/)[ヘッダー](/glossary/ヘッダー/)例は以下のようになります。

```bash
HTTP/1.1 429 Too Many Requests
X-RateLimit-Limit: 1000
X-RateLimit-Resource: core
X-RateLimit-NearLimit: false
Content-Type: application/json
```

## よくある原因と解決手順

### 原因1：短時間に多数のAPIリクエストを送信している

Bitbucket [API](/glossary/api/)への[リクエスト](/glossary/リクエスト/)を制御なく連続送信すると、すぐに[レート制限](/glossary/レート制限/)に引っかかります。特にスクリプトやバッチ処理で大量の[リポジトリ](/glossary/リポジトリ/)情報やプルリクエストを取得する際に発生しやすい現象です。各[リクエスト](/glossary/リクエスト/)間に待機時間を設けずに処理すると、数秒で1000[リクエスト](/glossary/リクエスト/)に達する可能性があります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
import requests

headers = {
    "Authorization": f"Bearer <your-bitbucket-api-token>"
}

# 制御なしで次々とAPIリクエストを送信
for repo_id in range(1, 101):
    response = requests.get(
        f"https://api.bitbucket.org/2.0/repositories/<workspace>/<repo-{repo_id}>",
        headers=headers
    )
    print(f"Repo {repo_id}: {response.status_code}")
```

**After（修正後）：**

```python
import requests
import time

headers = {
    "Authorization": f"Bearer <your-bitbucket-api-token>"
}

# リクエスト間に遅延を挟む
for repo_id in range(1, 101):
    response = requests.get(
        f"https://api.bitbucket.org/2.0/repositories/<workspace>/<repo-{repo_id}>",
        headers=headers
    )
    
    # 429エラーの場合はリセット時刻まで待機
    if response.status_code == 429:
        reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
        wait_seconds = max(reset_time - time.time(), 0)
        print(f"Rate limited. Waiting {wait_seconds} seconds...")
        time.sleep(wait_seconds + 1)
        # 再試行
        response = requests.get(
            f"https://api.bitbucket.org/2.0/repositories/<workspace>/<repo-{repo_id}>",
            headers=headers
        )
    
    # 正常に取得できた場合のみリクエスト間隔を短く
    if response.status_code == 200:
        time.sleep(0.1)  # 100ms待機
    
    print(f"Repo {repo_id}: {response.status_code}")
```

### 原因2：CI/CDパイプライン内で複数のジョブが同時にAPI呼び出しを実行している

Bitbucket Pipelines や GitHub Actions、Jenkins 等の[CI/CD](/glossary/ci-cd/)ツール内で複数の並列ジョブが同時に同じBitbucket [API](/glossary/api/)を呼び出す場合、個別のジョブは少量の[リクエスト](/glossary/リクエスト/)でも、全体では瞬時に制限に達します。例えば50個の並列ジョブがそれぞれ20[リクエスト](/glossary/リクエスト/)送信すれば、1000[リクエスト](/glossary/リクエスト/)上限に達してしまいます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
image: atlassian/default-image:latest

pipelines:
  branches:
    main:
      - parallel:
        - step:
            name: Job 1
            script:
              - curl -H "Authorization: Bearer <your-bitbucket-api-token>" \
                https://api.bitbucket.org/2.0/repositories/<workspace>/<repo>/pullrequests
        - step:
            name: Job 2
            script:
              - curl -H "Authorization: Bearer <your-bitbucket-api-token>" \
                https://api.bitbucket.org/2.0/repositories/<workspace>/<repo>/pullrequests
        - step:
            name: Job 3
            script:
              - curl -H "Authorization: Bearer <your-bitbucket-api-token>" \
                https://api.bitbucket.org/2.0/repositories/<workspace>/<repo>/pullrequests
```

**After（修正後）：**

```yaml
image: atlassian/default-image:latest

pipelines:
  branches:
    main:
      - step:
          name: Fetch PR Info
          script:
            # 各ステップで呼び出しを順序付ける、または1つのステップで全情報取得
            - curl -H "Authorization: Bearer <your-bitbucket-api-token>" \
              https://api.bitbucket.org/2.0/repositories/<workspace>/<repo>/pullrequests?pagelen=50 \
              | tee pr_data.json
            - sleep 2
            - bash process_prs.sh < pr_data.json
      - step:
          name: Other Tasks
          script:
            - echo "Running after API calls complete"
```

### 原因3：ページネーション未対応で全件取得時に大量のリクエストが発生している

Bitbucket [API](/glossary/api/)の一覧取得[エンドポイント](/glossary/エンドポイント/)（例：プルリクエスト一覧、[コミット](/glossary/コミット/)一覧）はデフォルトで10件または30件単位のページネーション応答を返します。これを1件単位で別々の[API](/glossary/api/)[リクエスト](/glossary/リクエスト/)で取得していると、数百件のデータ取得時点で瞬く間に[レート制限](/glossary/レート制限/)に達します。ページサイズを最大値に設定し、必要に応じてカーソルベースの非同期取得に変更すべきです。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
const axios = require('axios');

async function getAllPullRequests() {
    const headers = {
        'Authorization': `Bearer <your-bitbucket-api-token>`
    };
    
    let allPRs = [];
    // APIのデフォルトは10件/ページのため、100件取得時に10リクエスト必要
    for (let page = 1; page <= 100; page++) {
        const response = await axios.get(
            `https://api.bitbucket.org/2.0/repositories/<workspace>/<repo>/pullrequests?page=${page}`,
            { headers }
        );
        allPRs = allPRs.concat(response.data.values);
    }
    
    return allPRs;
}
```

**After（修正後）：**

```javascript
const axios = require('axios');

async function getAllPullRequests() {
    const headers = {
        'Authorization': `Bearer <your-bitbucket-api-token>`
    };
    
    let allPRs = [];
    let nextPageUrl = `https://api.bitbucket.org/2.0/repositories/<workspace>/<repo>/pullrequests?pagelen=50`;
    
    // ページサイズを50に設定してリクエスト数を削減
    while (nextPageUrl) {
        try {
            const response = await axios.get(nextPageUrl, { headers });
            allPRs = allPRs.concat(response.data.values);
            nextPageUrl = response.data.pagingfilters?.next || null;
        } catch (error) {
            if (error.response?.status === 429) {
                const resetTime = parseInt(error.response.headers['x-ratelimit-reset']);
                const waitMs = (resetTime * 1000) - Date.now() + 1000;
                console.log(`Rate limited. Waiting ${waitMs}ms...`);
                await new Promise(resolve => setTimeout(resolve, Math.max(waitMs, 0)));
                // 同じURLで再試行
                continue;
            }
            throw error;
        }
    }
    
    return allPRs;
}
```

## ツール固有の注意点

Bitbucket Cloud の[レート制限](/glossary/レート制限/)は[ワークスペース](/glossary/ワークスペース/)単位ではなく、**[認証](/glossary/認証/)ユーザー・[トークン](/glossary/トークン/)単位**で適用されます。そのため同一[トークン](/glossary/トークン/)を複数の[CI/CD](/glossary/ci-cd/)ジョブやスクリプトで共有している場合、各プロセスの負荷が累積されます。本番環境では専用の[API](/glossary/api/)[トークン](/glossary/トークン/)を作成し、必要に応じて複数[トークン](/glossary/トークン/)を用意して負荷分散することが推奨されます。

また、Bitbucket Server（オンプレミス版）を使用している場合は、[レート制限](/glossary/レート制限/)がデフォルトで無効である場合が多いため、この429[エラー](/glossary/エラー/)は発生しにくいです。一方、Bitbucket Cloud [API](/glossary/api/) v2.0 を使用している場合は必ず[レート制限](/glossary/レート制限/)の対象となるため、[リクエスト](/glossary/リクエスト/)設計の段階で考慮する必要があります。

429[レスポンス](/glossary/レスポンス/)が返却された場合は、指数[バックオフ](/glossary/バックオフ/)を実装して待機することが推奨されます。異なるアクセス[トークン](/glossary/トークン/)を使用するか、一定期間待機してから[リクエスト](/glossary/リクエスト/)を再度送信してください。単純に固定時間待機するのではなく、段階的に待機時間を延長することで、より効率的に対応できます。

## それでも解決しない場合

まずBitbucket の[API](/glossary/api/)[リクエスト](/glossary/リクエスト/)[ログ](/glossary/ログ/)を確認し、実際の送信数を把握してください。ブラウザの開発者ツールネットワークタブや、`curl -v` で詳細[ヘッダー](/glossary/ヘッダー/)を確認することで、[レート制限](/glossary/レート制限/)に関する詳細情報（X-RateLimit-* [ヘッダー](/glossary/ヘッダー/)）が表示されます。

```bash
curl -v -H "Authorization: Bearer <your-bitbucket-api-token>" \
  https://api.bitbucket.org/2.0/repositories/<workspace>/<repo> 2>&1 | grep -i "x-ratelimit"
```

複数の[トークン](/glossary/トークン/)を用いた負荷分散を検討している場合、各[トークン](/glossary/トークン/)の[レート制限](/glossary/レート制限/)が[ワークスペース](/glossary/ワークスペース/)内で独立して管理されていることを確認してください。[CI/CD](/glossary/ci-cd/)パイプラインの設定を見直し、並列実行の数を削減するか、[リクエスト](/glossary/リクエスト/)送信を直列化することで、安定した運用が実現できます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*