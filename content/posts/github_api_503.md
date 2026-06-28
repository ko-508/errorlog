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
top_queries:
- 'github 503'
- 'github 503 error'
- 'github error 503'
---

## エラーの概要

GitHub [API](/glossary/api/)における503[エラー](/glossary/エラー/)は、GitHubのサービスが一時的に利用不可の状態にあることを示します。この[エラー](/glossary/エラー/)はGitHub側のメンテナンス、インフラストラクチャの過負荷、または[API](/glossary/api/)呼び出しの集中に達した場合に発生します。503[エラー](/glossary/エラー/)が返される際には、通常`Retry-After`[ヘッダー](/glossary/ヘッダー/)が含まれており、どのくらい待つべきかの秒数目安が提示されます。

## 実際のエラーメッセージ例

GitHub [API](/glossary/api/)から返される実際の503[レスポンス](/glossary/レスポンス/)の例を以下に示します。

```json
{
  "message": "Service Unavailable",
  "documentation_url": "https://docs.github.com/rest/overview/resources-in-the-rest-api"
}
```

cURLやPythonのrequestsライブラリを使用した場合の[コンソール](/glossary/コンソール/)出力例：

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

GitHubが定期メンテナンスやシステム障害の最中に[API](/glossary/api/)呼び出しを行うと503[エラー](/glossary/エラー/)が発生します。この場合、ユーザー側では対応できず、GitHub側の復旧を待つ必要があります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

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

GitHub [API](/glossary/api/)には時間ごとの呼び出し回数制限があります。[認証](/glossary/認証/)ユーザーは1時間あたり5,000[リクエスト](/glossary/リクエスト/)、未認証ユーザーは60[リクエスト](/glossary/リクエスト/)に制限されています。この制限に達すると429[エラー](/glossary/エラー/)が返されますが、その直後の集中アクセスによって503[エラー](/glossary/エラー/)が発生する可能性があります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

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

複数の非同期タスクやマルチスレッドで同時に大量の[API](/glossary/api/)呼び出しを行うと、GitHub側に過大な負荷をかけて503[エラー](/glossary/エラー/)をトリガーする可能性があります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

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

GitHub Actionsでは、ワークフロー実行中にGitHub [API](/glossary/api/)を呼び出す際に503[エラー](/glossary/エラー/)が発生することがあります。`actions/github-script`アクションを使用する場合、内部的にはOctokitライブラリが使用されるため、リトライロジックを明示的に組み込む必要があります。

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

GitHubの[Webhook](/glossary/webhook/)配信システムが503を経験している場合、イベント配信の遅延が発生します。[Webhook](/glossary/webhook/)受信側では、失敗時の再試行メカニズムが3時間以内に発動されるため、一時的な503は通常問題になりません。ただし、受信側[サーバー](/glossary/サーバー/)が503に応答するように設定されている場合、GitHubからの再試行が繰り返される可能性があります。

### REST API vs GraphQL APIの選択

大量データ取得が必要な場合、[GraphQL](/glossary/graphql/) [API](/glossary/api/)を使用すると[リクエスト](/glossary/リクエスト/)数を削減でき、503[エラー](/glossary/エラー/)のリスクを低減できます。

**[REST](/glossary/rest/) [API](/glossary/api/)（複数[リクエスト](/glossary/リクエスト/)必要）：**

```bash
curl -H "Authorization: token <your-github-token>" \
  https://api.github.com/repos/<owner>/<repo>/issues
curl -H "Authorization: token <your-github-token>" \
  https://api.github.com/repos/<owner>/<repo>/pulls
```

**[GraphQL](/glossary/graphql/) [API](/glossary/api/)（単一[リクエスト](/glossary/リクエスト/)）：**

```bash
curl -H "Authorization: token <your-github-token>" \
  -X POST https://api.github.com/graphql \
  -d '{"query":"query { repository(owner:\"<owner>\", name:\"<repo>\") { issues(first:100) { edges { node { number title } } } pullRequests(first:100) { edges { node { number title } } } } }"}'
```

## それでも解決しない場合

### 確認すべきポイント

1. **GitHub Status Pageの確認**：https://www.githubstatus.com で現在のGitHubサービス状態を[リアルタイム](/glossary/リアルタイム/)で確認してください。システム障害が継続中の場合は復旧待機が必要です。

2. **[API](/glossary/api/)レスポンスヘッダーの詳細確認**：
```bash
curl -v -H "Authorization: token <your-github-token>" \
  https://api.github.com/user/repos 2>&1 | grep -E "(HTTP/|Retry-After|X-RateLimit)"
```
この[コマンド](/glossary/コマンド/)で[HTTP](/glossary/http/)ステータス、Retry-After[ヘッダー](/glossary/ヘッダー/)、レート制限情報を確認できます。

3. **公式ドキュメント**：https://docs.github.com/en/rest/overview/resources-in-the-rest-api?apiVersion=2022-11-28#rate-limiting の「Exceeding the rate limit」セクションで、[レート制限](/glossary/レート制限/)と503[エラー](/glossary/エラー/)の関係を確認してください。

4. **コミュニティリソース**：GitHub [API](/glossary/api/)に関する既知の503問題は、https://github.com/orgs/github/discussions で報告・議論されていることがあります。検索してみてください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*