---
title: "GitHub API の 503 エラー：原因と解決策"
date: 2026-01-01
description: "GitHub APIにおける503エラーは、GitHubのサービスが一時的に利用不可の状態にあることを示します。このエラーはGitHub側のメンテナンス、過負荷、またはAPIレート制限に達した場合に発生します。"
tags: ["GitHub API"]
errorCode: "503"
lastmod: 2026-06-13
service: "GitHub API"
error_type: "503"
components: []
related_services: ["GraphQL API"]
trend_incident: true
---

## エラーの概要

GitHub APIにおける503エラーは、GitHubのサービスが一時的に利用不可の状態にあることを示します。このエラーはGitHub側のメンテナンス、インフラストラクチャの過負荷、またはAPI呼び出しの集中に達した場合に発生します。503エラーが返される際には、通常`Retry-After`ヘッダーが含まれており、どのくらい待つべきかの秒数目安が提示されます。

## 実際のエラーメッセージ例

GitHub APIから返される実際の503レスポンスの例を以下に示します。

```json
{
  "message": "Service Unavailable",
  "documentation_url": "https://docs.github.com/rest/overview/resources-in-the-rest-api"
}
```

cURLやPythonのrequestsライブラリを使用した場合のコンソール出力例：

```bash
curl -H "Authorization: token <your-github-token>" \
  https://api.github.com/user/repos

# レスポンス
HTTP/1.1 503 Service Unavailable
Retry-After: 60
Content-Type: application/json

{"message":"Service Unavailable"}
```

## よくある原因と解決手順

### 原因1：GitHub側のメンテナンスまたはシステム障害

GitHubが定期メンテナンスやシステム障害の最中にAPI呼び出しを行うと503エラーが発生します。この場合、ユーザー側では対応できず、GitHub側の復旧を待つ必要があります。

**Before（エラーが起きるコード）：**

```python
import requests

response = requests.get(
    'https://api.github.com/user/repos',
    headers={'Authorization': f'token <your-github-token>'}
)
print(response.json())  # 503エラーで処理が停止
```

**After（修正後）：**

```python
import requests
import time

def fetch_with_retry(url, token, max_retries=3):
    headers = {'Authorization': f'token {token}'}
    retry_count = 0
    
    while retry_count < max_retries:
        response = requests.get(url, headers=headers)
        
        if response.status_code == 503:
            retry_after = int(response.headers.get('Retry-After', 60))
            print(f"503エラー。{retry_after}秒後に再試行します")
            time.sleep(retry_after)
            retry_count += 1
        elif response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"エラー: {response.status_code}")
    
    raise Exception("最大再試行回数に達しました")

result = fetch_with_retry('https://api.github.com/user/repos', '<your-github-token>')
print(result)
```

### 原因2：APIレート制限への抵触

GitHub APIには時間ごとの呼び出し回数制限があります。認証ユーザーは1時間あたり5,000リクエスト、未認証ユーザーは60リクエストに制限されています。この制限に達すると429エラーが返されますが、その直後の集中アクセスによって503エラーが発生する可能性があります。

**Before（エラーが起きるコード）：**

```python
import requests

token = '<your-github-token>'
headers = {'Authorization': f'token {token}'}

# ページネーション処理で連続リクエスト
for page in range(1, 100):
    response = requests.get(
        f'https://api.github.com/repos/<owner>/<repo>/issues',
        headers=headers,
        params={'page': page, 'per_page': 100}
    )
    if response.status_code != 200:
        print(f"エラー: {response.status_code}")  # 503で停止
```

**After（修正後）：**

```python
import requests
import time

token = '<your-github-token>'
headers = {'Authorization': f'token {token}'}

def check_rate_limit(headers):
    response = requests.get('https://api.github.com/rate_limit', headers=headers)
    data = response.json()
    return data['resources']['core']

def fetch_paginated(url, token):
    headers = {'Authorization': f'token {token}'}
    results = []
    page = 1
    
    while True:
        rate_limit = check_rate_limit(headers)
        
        if rate_limit['remaining'] < 10:  # 残り10リクエスト以下ならリセット待機
            reset_time = rate_limit['reset']
            sleep_time = reset_time - int(time.time())
            if sleep_time > 0:
                print(f"レート制限に接近。{sleep_time}秒待機します")
                time.sleep(sleep_time + 1)
        
        response = requests.get(
            url,
            headers=headers,
            params={'page': page, 'per_page': 100}
        )
        
        if response.status_code == 200:
            data = response.json()
            if not data:
                break
            results.extend(data)
            page += 1
        elif response.status_code == 503:
            print("503エラー。60秒待機して再試行します")
            time.sleep(60)
        else:
            raise Exception(f"エラー: {response.status_code}")
    
    return results

issues = fetch_paginated(
    'https://api.github.com/repos/<owner>/<repo>/issues',
    '<your-github-token>'
)
```

### 原因3：不適切な並行リクエスト処理

複数の非同期タスクやマルチスレッドで同時に大量のAPI呼び出しを行うと、GitHub側に過大な負荷をかけて503エラーをトリガーする可能性があります。

**Before（エラーが起きるコード）：**

```python
import asyncio
import aiohttp

async def fetch_repos_concurrent(usernames, token):
    async with aiohttp.ClientSession() as session:
        tasks = []
        for username in usernames:
            task = session.get(
                f'https://api.github.com/users/{username}/repos',
                headers={'Authorization': f'token {token}'}
            )
            tasks.append(task)
        
        # 全タスク一気に実行 → 503エラーの可能性が高い
        return await asyncio.gather(*tasks)

asyncio.run(fetch_repos_concurrent(['user1', 'user2', ..., 'user100'], '<your-github-token>'))
```

**After（修正後）：**

```python
import asyncio
import aiohttp

async def fetch_repos_with_limit(usernames, token, max_concurrent=5):
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def fetch(session, username):
        async with semaphore:
            await asyncio.sleep(0.5)  # リクエスト間に遅延を挿入
            async with session.get(
                f'https://api.github.com/users/{username}/repos',
                headers={'Authorization': f'token {token}'}
            ) as response:
                return await response.json()
    
    async with aiohttp.ClientSession() as session:
        tasks = [fetch(session, username) for username in usernames]
        return await asyncio.gather(*tasks)

results = asyncio.run(
    fetch_repos_with_limit(['user1', 'user2', ..., 'user100'], '<your-github-token>')
)
```

## ツール固有の注意点

### GitHub Actions内での503エラー対応

GitHub Actionsでは、ワークフロー実行中にGitHub APIを呼び出す際に503エラーが発生することがあります。`actions/github-script`アクションを使用する場合、内部的にはOctokitライブラリが使用されるため、リトライロジックを明示的に組み込む必要があります。

```yaml
name: Fetch Issues with Retry

on: [push]

jobs:
  fetch-issues:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/github-script@v7
        with:
          script: |
            const MAX_RETRIES = 3;
            let retries = 0;
            
            while (retries < MAX_RETRIES) {
              try {
                const issues = await github.rest.issues.listForRepo({
                  owner: context.repo.owner,
                  repo: context.repo.repo
                });
                console.log(issues.data);
                break;
              } catch (error) {
                if (error.status === 503) {
                  retries++;
                  const waitTime = Math.pow(2, retries) * 1000;
                  console.log(`503エラー。${waitTime}ms待機して再試行します`);
                  await new Promise(resolve => setTimeout(resolve, waitTime));
                } else {
                  throw error;
                }
              }
            }
```

### Webhookシステム への影響

GitHubのWebhook配信システムが503を経験している場合、イベント配信の遅延が発生します。Webhook受信側では、失敗時の再試行メカニズムが3時間以内に発動されるため、一時的な503は通常問題になりません。ただし、受信側サーバーが503に応答するように設定されている場合、GitHubからの再試行が繰り返される可能性があります。

### REST API vs GraphQL APIの選択

大量データ取得が必要な場合、GraphQL APIを使用するとリクエスト数を削減でき、503エラーのリスクを低減できます。

**REST API（複数リクエスト必要）：**

```bash
curl -H "Authorization: token <your-github-token>" \
  https://api.github.com/repos/<owner>/<repo>/issues
curl -H "Authorization: token <your-github-token>" \
  https://api.github.com/repos/<owner>/<repo>/pulls
```

**GraphQL API（単一リクエスト）：**

```bash
curl -H "Authorization: token <your-github-token>" \
  -X POST https://api.github.com/graphql \
  -d '{"query":"query { repository(owner:\"<owner>\", name:\"<repo>\") { issues(first:100) { edges { node { number title } } } pullRequests(first:100) { edges { node { number title } } } } }"}'
```

## それでも解決しない場合

### 確認すべきポイント

1. **GitHub Status Pageの確認**：https://www.githubstatus.com で現在のGitHubサービス状態をリアルタイムで確認してください。システム障害が継続中の場合は復旧待機が必要です。

2. **APIレスポンスヘッダーの詳細確認**：
```bash
curl -v -H "Authorization: token <your-github-token>" \
  https://api.github.com/user/repos 2>&1 | grep -E "(HTTP/|Retry-After|X-RateLimit)"
```
このコマンドでHTTPステータス、Retry-Afterヘッダー、レート制限情報を確認できます。

3. **公式ドキュメント**：https://docs.github.com/en/rest/overview/resources-in-the-rest-api?apiVersion=2022-11-28#rate-limiting の「Exceeding the rate limit」セクションで、レート制限と503エラーの関係を確認してください。

4. **コミュニティリソース**：GitHub APIに関する既知の503問題は、https://github.com/orgs/github/discussions で報告・議論されていることがあります。検索してみてください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*