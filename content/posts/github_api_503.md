---
title: "GitHub API の 503 エラー：原因と解決策"
date: 2026-01-01
description: "GitHub APIにおける503エラーは、GitHubのサービスが一時的に利用不可の状態にあることを示します。このエラーはGitHub側のメンテナンス、過負荷、またはAPIレート制限に達した場合に発生します。"
tags: ["GitHub API"]
errorCode: "503"
lastmod: 2026-05-29
---

## エラーの概要

GitHub [API](/glossary/api/)における503エラーは、GitHubのサービスが一時的に利用不可の状態にあることを示します。このエラーはGitHub側のメンテナンス、過負荷、または[API](/glossary/api/)[レート制限](/glossary/レート制限/)に達した場合に発生します。503エラーが返される際には、通常`Retry-After`[ヘッダー](/glossary/ヘッダー/)が含まれており、どのくらい待つべきかの目安が提示されます。

## 実際のエラーメッセージ例

GitHub [API](/glossary/api/)から返される実際の503[レスポンス](/glossary/レスポンス/)の例を示します。

```json
{
  "message": "Service Unavailable",
  "documentation_url": "https://docs.github.com/rest/overview/resources-in-the-rest-api",
  "errors": [
    {
      "message": "Server overloaded",
      "documentation_url": "https://docs.github.com/rest/overview/resources-in-the-rest-api"
    }
  ]
}
```

[HTTP](/glossary/http/)[ヘッダー](/glossary/ヘッダー/)には以下のような情報が含まれます。

```
HTTP/1.1 503 Service Unavailable
Retry-After: 60
Content-Type: application/json
```

## よくある原因と解決手順

### 原因1：GitHub側のメンテナンスまたは障害

GitHubは定期的なメンテナンスや予期しない障害によって[API](/glossary/api/)が一時的に利用できなくなることがあります。この場合、`Retry-After`[ヘッダー](/glossary/ヘッダー/)で指定された時間待機することが重要です。

**Before（エラーが起きる例）：**
```python
import requests

response = requests.get(
    'https://api.github.com/user/repos',
    headers={'Authorization': 'token <your-github-token>'}
)

if response.status_code != 200:
    print(response.json())  # メンテナンス中は503が返される
```

**After（改善後）：**
```python
import requests
import time

def fetch_with_retry(url, token, max_retries=3):
    for attempt in range(max_retries):
        response = requests.get(
            url,
            headers={'Authorization': f'token {token}'}
        )
        
        if response.status_code == 503:
            retry_after = int(response.headers.get('Retry-After', 60))
            print(f"Service unavailable. Retrying in {retry_after} seconds...")
            time.sleep(retry_after)
            continue
        
        return response
    
    raise Exception("Failed after maximum retries")

response = fetch_with_retry(
    'https://api.github.com/user/repos',
    '<your-github-token>'
)
```

### 原因2：APIレート制限に達した場合の不適切なハンドリング

GitHub [API](/glossary/api/)はユーザーごとに[レート制限](/glossary/レート制限/)を設定しており、制限を超過すると一時的に503エラーが返される場合があります。特に[認証](/glossary/認証/)なしの[リクエスト](/glossary/リクエスト/)では制限が厳しいため注意が必要です。

**Before（[認証](/glossary/認証/)なしでのアクセス）：**
```bash
curl https://api.github.com/repos/github/hello-world
# 短時間に大量のリクエストを送信すると503が返される
```

**After（認証付きでのアクセス）：**
```bash
curl -H "Authorization: token <your-github-token>" \
     https://api.github.com/repos/github/hello-world

# または GraphQL APIを使用（より効率的）
curl -X POST https://api.github.com/graphql \
  -H "Authorization: bearer <your-github-token>" \
  -d '{"query":"{ viewer { name } }"}'
```

### 原因3：レート制限の監視不足

GitHub [API](/glossary/api/)の[レート制限](/glossary/レート制限/)に近づいていることを事前に検知できていないと、予期せず503エラーに遭遇します。`X-RateLimit-*`[ヘッダー](/glossary/ヘッダー/)を監視することで未然に防げます。

**Before（[レート制限](/glossary/レート制限/)を無視）：**
```python
import requests

for i in range(1000):
    response = requests.get(
        f'https://api.github.com/repos/github/hello-world/issues',
        headers={'Authorization': f'token <your-github-token>'}
    )
    print(response.json())  # 制限に達すると503エラー
```

**After（[レート制限](/glossary/レート制限/)を監視）：**
```python
import requests
import time

def check_rate_limit(token):
    response = requests.get(
        'https://api.github.com/rate_limit',
        headers={'Authorization': f'token {token}'}
    )
    return response.json()['resources']['core']

token = '<your-github-token>'
rate_limit = check_rate_limit(token)

if rate_limit['remaining'] < 10:
    wait_time = rate_limit['reset'] - int(time.time())
    print(f"Rate limit approaching. Wait {wait_time} seconds before next request")
    time.sleep(wait_time + 1)

response = requests.get(
    'https://api.github.com/user/repos',
    headers={'Authorization': f'token {token}'}
)
```

## ツール固有の注意点

### GitHub APIバージョンによる違い

GitHub [API](/glossary/api/)には`REST API`と`GraphQL API`の2つの方式があります。[REST](/glossary/rest/) [API](/glossary/api/)の方が503エラーが発生しやすいため、複数のリソースを取得する場合は[GraphQL](/glossary/graphql/) [API](/glossary/api/)の使用を推奨します。[GraphQL](/glossary/graphql/) [API](/glossary/api/)はクエリを最適化することで、単一の[リクエスト](/glossary/リクエスト/)で複数の情報を取得でき、[レート制限](/glossary/レート制限/)の消費を大幅に削減できます。

### Personal Access Token（PAT）の有効期限

新しいPATは有効期限を設定できます。期限切れの[トークン](/glossary/トークン/)で[リクエスト](/glossary/リクエスト/)すると、[認証](/glossary/認証/)エラーを経て503に至る場合があります。定期的に[トークン](/glossary/トークン/)の有効期限を確認し、自動更新の仕組みを導入することが重要です。

### GitHub Status Pageの確認

GitHubは公式のステータスページ（https://www.githubstatus.com/）で、リアルタイムのサービス状態を公開しています。503エラーが頻発する場合は、まずこのページを確認してGitHub側で障害が発生していないか確認してください。

## それでも解決しない場合

### デバッグ方法

詳細なレスポンスヘッダーと本体をログに記録して原因を特定します。

```python
import requests
import logging

logging.basicConfig(level=logging.DEBUG)

response = requests.get(
    'https://api.github.com/user/repos',
    headers={'Authorization': f'token <your-github-token>'}
)

print(f"Status Code: {response.status_code}")
print(f"Headers: {dict(response.headers)}")
print(f"Body: {response.text}")
```

### 参照リソース

- **GitHub [REST](/glossary/rest/) [API](/glossary/api/)公式ドキュメント**: https://docs.github.com/en/rest
- **GitHub [GraphQL](/glossary/graphql/) [API](/glossary/api/)**: https://docs.github.com/en/graphql
- **Rate Limiting に関する詳細**: https://docs.github.com/en/rest/overview/resources-in-the-rest-api?apiVersion=2022-11-28#rate-limiting
- **GitHub Status**: https://www.githubstatus.com/

### コミュニティサポート

問題が解決しない場合は、GitHub Community Discussionsで相談するか、該当するPythonライブラリ（PyGithub）やNode.jsライブラリ（Octokit）のIssueセクションを確認することをお勧めします。エラーが再現可能な場合は、GitHubのサポートに直接問い合わせることもできます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*