---
title: "GitHub API の 429 エラー：原因と解決策"
date: 2026-01-01
description: "GitHub APIの429エラーは「Too Many Requests」を意味し、レート制限に達したことを示します。GitHubは不正アクセスやDDoS攻撃から保護するため、APIリクエスト数に制限を設けており、この上限を超えると429が"
tags: ["GitHub API"]
errorCode: "429"
lastmod: 2026-05-31
---

## エラーの概要

GitHub [API](/glossary/api/)の429エラーは「Too Many Requests」を意味し、[レート制限](/glossary/レート制限/)に達したことを示します。GitHubは不正アクセスやDDoS攻撃から保護するため、[API](/glossary/api/)[リクエスト](/glossary/リクエスト/)数に制限を設けており、この上限を超えると429が返されます。[認証](/glossary/認証/)の有無や[エンドポイント](/glossary/エンドポイント/)、時間窓によって制限値が異なるため、適切な対策が必須です。

## 実際のエラーメッセージ例

```json
{
  "message": "API rate limit exceeded for user ID <user-id>.",
  "documentation_url": "https://docs.github.com/rest/overview/resources-in-the-rest-api#rate-limiting"
}
```

```bash
curl -i https://api.github.com/user
HTTP/1.1 429 Too Many Requests
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1234567890
```

## よくある原因と解決手順

### 原因1：認証なしでAPIを呼び出している

**なぜ発生するか：** [認証](/glossary/認証/)なし（匿名）での[リクエスト](/glossary/リクエスト/)は時間当たり60回に制限されます。スクリプトやアプリが複数回実行されると、すぐに上限に達してしまいます。

**Before（エラーが起きる状態）：**
```bash
# 認証なしでリクエスト
curl https://api.github.com/user/repos
```

**After（修正後）：**
```bash
# Personal Access Token(PAT)を使用して認証
curl -H "Authorization: token <your-personal-access-token>" \
  https://api.github.com/user/repos
```

### 原因2：ポーリング間隔が短すぎる

**なぜ発生するか：** 定期的に[API](/glossary/api/)を監視する際に、十分な間隔を設けずに[リクエスト](/glossary/リクエスト/)を送り続けると、あっという間に制限に達します。認証済みでも時間当たり5,000[リクエスト](/glossary/リクエスト/)が上限です。

**Before（エラーが起きる状態）：**
```python
import requests
import time

token = "<your-personal-access-token>"
headers = {"Authorization": f"token {token}"}

# 1秒ごとにポーリング（60秒で60リクエスト = 上限到達）
while True:
    response = requests.get(
        "https://api.github.com/repos/<owner>/<repo>/pulls",
        headers=headers
    )
    print(response.status_code)
    time.sleep(1)  # 間隔が短すぎる
```

**After（修正後）：**
```python
import requests
import time

token = "<your-personal-access-token>"
headers = {"Authorization": f"token {token}"}

# 重要：X-RateLimit-Reset ヘッダーを確認して待機
while True:
    response = requests.get(
        "https://api.github.com/repos/<owner>/<repo>/pulls",
        headers=headers
    )
    
    if response.status_code == 429:
        reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
        wait_time = reset_time - int(time.time())
        print(f"Rate limit reached. Waiting {wait_time} seconds...")
        time.sleep(max(wait_time, 0))
    else:
        print(response.status_code)
    
    time.sleep(10)  # 適切な間隔を設定
```

### 原因3：GraphQL APIとREST APIの混用で制限を誤解している

**なぜ発生するか：** [GraphQL](/glossary/graphql/) [API](/glossary/api/)はポイント制（Rate Limit Points）で管理されるため、[REST](/glossary/rest/) [API](/glossary/api/)とは異なる制限ロジックです。複雑な[クエリ](/glossary/クエリ/)は複数ポイントを消費するため、[REST](/glossary/rest/) [API](/glossary/api/)と同じ感覚で使うとすぐに上限に達します。

**Before（エラーが起きる状態）：**
```graphql
# GraphQLで複数リポジトリの全情報を一度に取得
query {
  viewer {
    repositories(first: 100) {
      edges {
        node {
          name
          issues(first: 50) {
            edges {
              node {
                title
                comments(first: 50) {
                  totalCount
                }
              }
            }
          }
        }
      }
    }
  }
}
```

**After（修正後）：**
```graphql
# ページネーション + レート制限ポイント確認
query {
  viewer {
    repositories(first: 10) {  # 取得数を削減
      edges {
        node {
          name
        }
      }
    }
  }
  rateLimit {
    limit
    remaining
    resetAt
  }
}
```

### 原因4：キャッシュを活用していない

**なぜ発生するか：** 同じデータを何度も取得するのは無駄です。特に[CI/CD](/glossary/ci-cd/)パイプラインやバッチ処理では、[キャッシュ](/glossary/キャッシュ/)なしだと数秒で制限に達することもあります。

**Before（エラーが起きる状態）：**
```javascript
// 毎回APIを呼び出す
async function getRepoData(owner, repo) {
  const response = await fetch(
    `https://api.github.com/repos/${owner}/${repo}`,
    { headers: { "Authorization": `token ${process.env.GITHUB_TOKEN}` } }
  );
  return response.json();
}

// ループで何度も呼び出し
for (let i = 0; i < 1000; i++) {
  const data = await getRepoData("torvalds", "linux");
  console.log(data.stargazers_count);
}
```

**After（修正後）：**
```javascript
// キャッシュで最初の呼び出しだけ実行
const cache = new Map();

async function getRepoData(owner, repo) {
  const key = `${owner}/${repo}`;
  if (cache.has(key)) {
    return cache.get(key);
  }
  
  const response = await fetch(
    `https://api.github.com/repos/${owner}/${repo}`,
    { headers: { "Authorization": `token ${process.env.GITHUB_TOKEN}` } }
  );
  const data = await response.json();
  cache.set(key, data);
  return data;
}

for (let i = 0; i < 1000; i++) {
  const data = await getRepoData("torvalds", "linux");
  console.log(data.stargazers_count);
}
```

## GitHub API固有の注意点

### レート制限の種類を理解する

GitHub [API](/glossary/api/)には複数の[レート制限](/glossary/レート制限/)が存在します：

- **Primary Rate Limit**：認証済みで時間当たり5,000[リクエスト](/glossary/リクエスト/)、[認証](/glossary/認証/)なしで60[リクエスト](/glossary/リクエスト/)
- **Secondary Rate Limit**：短時間の集中的な[リクエスト](/glossary/リクエスト/)に対する追加制限（通常1秒で複数[リクエスト](/glossary/リクエスト/)は制限される）
- **Abuse Rate Limit**：極度に多くのデータを[リクエスト](/glossary/リクエスト/)した場合の即時制限

Secondary Rate Limitに引っかかった場合、`Retry-After`[ヘッダー](/glossary/ヘッダー/)で待機秒数が指定されます。

### Personal Access Token（PAT）のスコープと制限

PATを使用する場合、[スコープ](/glossary/スコープ/)によって制限が変わることはありませんが、[トークン](/glossary/トークン/)の[権限](/glossary/権限/)がない操作を試みると関連エラーが発生します。PAT作成時は必要最小限の[スコープ](/glossary/スコープ/)を設定してください。

### GitHubアプリとOAuthアプリの制限の違い

GitHubアプリを使うと、ユーザーごとに制限が独立するため、複数ユーザーの[リクエスト](/glossary/リクエスト/)を扱う場合に有利です。一方、[OAuth](/glossary/oauth/)アプリはアプリケーション全体で制限が共有されます。

## それでも解決しない場合

### レート制限の現在状態を確認する

```bash
curl -H "Authorization: token <your-personal-access-token>" \
  https://api.github.com/rate_limit | jq '.'
```

このコマンドで`remaining`が0になっていないか、`reset`までの時間を確認してください。

### ログから問題を特定する

アプリケーションに以下を追加して詳細[ログ](/glossary/ログ/)を記録します：

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# すべてのHTTPリクエストをログ
import http.client
http.client.HTTPConnection.debuglevel = 1
```

### 公式ドキュメントを参照する

- **GitHub [REST](/glossary/rest/) [API](/glossary/api/) [レート制限](/glossary/レート制限/)**：https://docs.github.com/en/rest/overview/resources-in-the-rest-api?apiVersion=2022-11-28#rate-limiting
- **[GraphQL](/glossary/graphql/) [API](/glossary/api/) [レート制限](/glossary/レート制限/)**：https://docs.github.com/en/graphql/overview/rate-limits-and-node-limits-in-the-graphql-api
- **Best Practices**：https://docs.github.com/en/rest/guides/best-practices-for-using-the-rest-api

### コミュニティに相談する

同じ問題に直面した開発者の事例がGitHub Community Discussionsにあります：
https://github.com/orgs/community/discussions

また、具体的なライブラリ（PyGithub、Octokitなど）を使用している場合は、該当プロジェクトのIssue Trackerも確認してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*