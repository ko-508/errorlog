---
title: "GitHub API の 504 エラー：原因と解決策"
date: 2026-05-24
description: "GitHub APIの504 Gateway Timeoutエラーは、GitHubのサーバーがあなたのリクエストを指定時間内に処理できなかったことを示します。"
tags: ["GitHub API"]
errorCode: "504"
lastmod: 2026-05-31
service: "GitHub API"
error_type: "504"
components: []
related_services: ["REST API", "OAuth", "Personal Access Token", "CI/CD"]
trend_incident: true
---

## エラーの概要

GitHub [API](/glossary/api/)の504 Gateway Timeout[エラー](/glossary/エラー/)は、GitHubの[サーバー](/glossary/サーバー/)があなたの[リクエスト](/glossary/リクエスト/)を指定時間内に処理できなかったことを示します。この[エラー](/glossary/エラー/)はGitHub側の[サーバー](/glossary/サーバー/)遅延、[ネットワーク](/glossary/ネットワーク/)遅延、または処理が重い操作が原因で発生することが多いです。[REST](/glossary/rest/) [API](/glossary/api/)を呼び出した際に504が返されると、[リクエスト](/glossary/リクエスト/)が完全に失敗するため、[API](/glossary/api/)統合機能が一時的に停止する状況につながります。

## 実際のエラーメッセージ例

[REST](/glossary/rest/) [API](/glossary/api/)の直接呼び出しでの504[エラーレスポンス](/glossary/エラーレスポンス/)：

```json
{
  "message": "Server Error",
  "documentation_url": "https://docs.github.com/rest"
}
```

curl[コマンド](/glossary/コマンド/)での確認例：

```bash
curl -i https://api.github.com/repos/<owner>/<repo>/pulls
# HTTP/1.1 504 Gateway Timeout
# Server: GitHub.com
# Date: Mon, 15 Jan 2024 10:30:45 GMT
```

## よくある原因と解決手順

### 原因1：大規模リポジトリへの過度なAPI呼び出し

**なぜ発生するか：** GitHubは処理時間に制限を設けており、膨大なプルリクエストやIssue一覧の取得など、[サーバー](/glossary/サーバー/)負荷が高い操作を実行すると[タイムアウト](/glossary/タイムアウト/)します。特に[コミット](/glossary/コミット/)履歴やファイル差分の取得で発生しやすいです。

**Before（[エラー](/glossary/エラー/)が起きる実装）：**

```python
import requests

headers = {"Authorization": f"token <your-github-token>"}
# 全プルリクエストを一度に取得しようとする
response = requests.get(
    "https://api.github.com/repos/<owner>/<repo>/pulls?state=all&per_page=100",
    headers=headers,
    timeout=10
)
```

**After（修正後）：**

```python
import requests
import time

headers = {"Authorization": f"token <your-github-token>"}

# ページング処理で段階的に取得
page = 1
all_pulls = []
while True:
    response = requests.get(
        f"https://api.github.com/repos/<owner>/<repo>/pulls?state=all&per_page=30&page={page}",
        headers=headers,
        timeout=15
    )
    
    if response.status_code == 504:
        print("504エラー。リトライまで10秒待機")
        time.sleep(10)
        continue
    
    if not response.json():
        break
    
    all_pulls.extend(response.json())
    page += 1
    time.sleep(1)  # API制限を避けるため1秒待機
```

### 原因2：認証トークンの有効期限切れまたは不正な設定

**なぜ発生するか：** 無効な認証情報を使用する場合、GitHubの[サーバー](/glossary/サーバー/)側で追加の検証処理が発生し、[タイムアウト](/glossary/タイムアウト/)の原因となることがあります。特にPersonal Access Tokenや[OAuth](/glossary/oauth/) tokenが期限切れの場合、[サーバー](/glossary/サーバー/)側が余計な処理を実行します。

**Before（[認証](/glossary/認証/)[エラー](/glossary/エラー/)の実装）：**

```bash
curl -H "Authorization: token <expired-token>" \
  https://api.github.com/user
```

**After（修正後）：**

```bash
# トークンの有効性を事前確認
curl -H "Authorization: token <your-valid-token>" \
  https://api.github.com/user

# または環境変数で安全に管理
export GITHUB_TOKEN="ghp_xxxxxxxxxxxx"
curl -H "Authorization: token ${GITHUB_TOKEN}" \
  https://api.github.com/user
```

### 原因3：同時多発的なAPI呼び出し

**なぜ発生するか：** 複数の[リクエスト](/glossary/リクエスト/)を短時間に大量送信すると、GitHubの[サーバー](/glossary/サーバー/)が処理しきれず504が発生します。特に[CI/CD](/glossary/ci-cd/)パイプラインやスクリプトで並列[リクエスト](/glossary/リクエスト/)を送った場合に起きやすいです。

**Before（並列[リクエスト](/glossary/リクエスト/)で504になる実装）：**

```python
import concurrent.futures
import requests

headers = {"Authorization": f"token <your-github-token>"}
repos = ["repo1", "repo2", "repo3", "repo4", "repo5"]

with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
    futures = [
        executor.submit(
            requests.get,
            f"https://api.github.com/repos/<owner>/{repo}",
            headers=headers
        )
        for repo in repos
    ]
    results = [f.result() for f in futures]
```

**After（[リクエスト](/glossary/リクエスト/)を制御する修正）：**

```python
import requests
import time

headers = {"Authorization": f"token <your-github-token>"}
repos = ["repo1", "repo2", "repo3", "repo4", "repo5"]

results = []
for repo in repos:
    response = requests.get(
        f"https://api.github.com/repos/<owner>/{repo}",
        headers=headers,
        timeout=15
    )
    
    if response.status_code == 504:
        print(f"504エラー。{repo}のリトライをスケジュール")
        time.sleep(5)
        response = requests.get(
            f"https://api.github.com/repos/<owner>/{repo}",
            headers=headers,
            timeout=15
        )
    
    results.append(response.json())
    time.sleep(1)  # Rate limit対策：リクエスト間隔を1秒
```

## ツール固有の注意点

### GraphQL APIの利用

GitHub [API](/glossary/api/)は[REST](/glossary/rest/) [API](/glossary/api/)だけでなく[GraphQL](/glossary/graphql/) [API](/glossary/api/)も提供しており、504[エラー](/glossary/エラー/)は[GraphQL](/glossary/graphql/)側でも発生します。[GraphQL](/glossary/graphql/)の場合、複雑な[クエリ](/glossary/クエリ/)や深いネストが原因になることがあります。

```python
import requests

headers = {
    "Authorization": f"token <your-github-token>",
    "Content-Type": "application/json"
}

# 複雑なクエリは分割する
query = """
query {
  repository(owner: "<owner>", name: "<repo>") {
    pullRequests(first: 100) {
      edges {
        node {
          id
          commits(last: 50) {
            nodes {
              oid
              message
            }
          }
        }
      }
    }
  }
}
"""

response = requests.post(
    "https://api.github.com/graphql",
    json={"query": query},
    headers=headers,
    timeout=20
)
```

### レート制限の確認

GitHub [API](/glossary/api/)は[レート制限](/glossary/レート制限/)が設定されており、制限に近づくと504が発生することがあります。リクエストヘッダーの`X-RateLimit-Remaining`と`X-RateLimit-Reset`を監視し、制限に余裕がある状態で処理を進めましょう。

```bash
curl -i -H "Authorization: token <your-token>" \
  https://api.github.com/rate_limit

# レスポンスヘッダーを確認
# X-RateLimit-Limit: 60
# X-RateLimit-Remaining: 59
# X-RateLimit-Reset: 1705317045
```

## それでも解決しない場合

### 確認すべきログとデバッグ方法

1. **GitHub Status ページを確認**：https://www.githubstatus.com/ にアクセスし、GitHub側でインシデントが発生していないか確認します。

2. **詳細なリクエストログを記録**：

```python
import requests
import logging

logging.basicConfig(level=logging.DEBUG)
requests_log = logging.getLogger("requests.packages.urllib3")
requests_log.setLevel(logging.DEBUG)
requests_log.propagate = True

response = requests.get(
    "https://api.github.com/repos/<owner>/<repo>",
    headers={"Authorization": f"token <your-token>"}
)
```

3. **公式ドキュメント参照**：
   - [GitHub REST API Documentation](https://docs.github.com/en/rest)
   - [API Rate Limiting Guide](https://docs.github.com/en/rest/overview/rate-limits-for-the-rest-api)
   - [Troubleshooting API Requests](https://docs.github.com/en/rest/overview/troubleshooting)

4. **コミュニティサポート**：
   - [GitHub Community Forum](https://github.community/)
   - [GitHub API Issues on GitHub](https://github.com/github/docs/issues)
   - スタックオーバーフローのgithub-apiタグで類似事例を検索

[タイムアウト](/glossary/タイムアウト/)時間を増やし、リトライロジックを実装することで多くの504[エラー](/glossary/エラー/)は回避可能です。問題が継続する場合は、[リクエスト](/glossary/リクエスト/)のサイズを削減するか、より小さな単位に分割する設計の見直しを検討してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*