---
title: "GitLab の 429 エラー：原因と解決策"
date: 2026-06-14
description: "GitLab APIのレート制限に達した。GitLab 429 エラーの原因と解決策を解説します。"
tags: ["GitLab"]
errorCode: "429"
service: "GitLab"
error_type: "429"
components: ["API", "CI/CD", "Projects", "Groups", "Merge Requests", "Pipelines", "Jobs", "Artifacts"]
related_services: ["curl", "Python requests"]
top_queries:
- 'リモート サーバー が エラー を 返し まし た 429'
---
## エラーの概要

GitLabの429[エラー](/glossary/エラー/)（Too Many Requests）は、GitLab [API](/glossary/api/)の[レート制限](/glossary/レート制限/)に達したことを示します。ユーザーまたは[CI/CD](/glossary/ci-cd/)パイプラインが短時間に許可された上限を超える[API](/glossary/api/)[リクエスト](/glossary/リクエスト/)を送信した場合に発生します。デフォルトの[レート制限](/glossary/レート制限/)は[エンドポイント](/glossary/エンドポイント/)や[インスタンス](/glossary/インスタンス/)の構成によって異なり、一般的には[認証](/glossary/認証/)ユーザーは1分間に600[リクエスト](/glossary/リクエスト/)、未認証の場合は300[リクエスト](/glossary/リクエスト/)程度とされていますが、パッケージレジストリ[API](/glossary/api/)など特定の[エンドポイント](/glossary/エンドポイント/)ではより高い制限が適用される場合もあります。

## 実際のエラーメッセージ例

GitLab [API](/glossary/api/)[レスポンス](/glossary/レスポンス/)：

```json
{
  "message": "429 Too Many Requests",
  "retry_after": 60,
  "ratelimit_limit": 600,
  "ratelimit_remaining": 0,
  "ratelimit_reset": 1699564800
}
```

curl[コマンド](/glossary/コマンド/)での[レスポンス](/glossary/レスポンス/)：

```bash
$ curl -H "PRIVATE-TOKEN: <your-access-token>" https://gitlab.example.com/api/v4/projects
HTTP/1.1 429 Too Many Requests
RateLimit-Limit: 600
RateLimit-Remaining: 0
RateLimit-Reset: 1699564800
Retry-After: 60

{"message":"429 Too Many Requests"}
```

## よくある原因と解決手順

### 原因1：短時間に多数のAPIリクエストを送出する処理

スクリプトやツールが迅速に連続した[API](/glossary/api/)コールを実行する際、GitLabの[レート制限](/glossary/レート制限/)に即座に到達します。例えば、多数のプロジェクトやグループの[メタデータ](/glossary/メタデータ/)を一括取得する場合、ループ処理で制限を超えやすくなります。

**解決策：ページング機能を使用して効率的に取得する**

```python
import requests
import time

TOKEN = "<your-access-token>"
GITLAB_URL = "https://gitlab.example.com"
headers = {"PRIVATE-TOKEN": TOKEN}

# ページング機能を使用して効率的に取得
page = 1
while True:
    response = requests.get(
        f"{GITLAB_URL}/api/v4/projects",
        headers=headers,
        params={"page": page, "per_page": 100}
    )
    
    if response.status_code == 429:
        reset_time = int(response.headers.get("RateLimit-Reset", 0))
        current_time = int(time.time())
        wait_seconds = reset_time - current_time
        print(f"Rate limit hit. Waiting {wait_seconds} seconds...")
        time.sleep(max(wait_seconds + 1, 0))
        continue
    
    if response.status_code != 200:
        break
    
    for project in response.json():
        print(f"Project: {project['name']}")
    
    if "next" not in response.links:
        break
    page += 1
```

### 原因2：CI/CDパイプラインが短時間に大量のAPIコールを実行している

GitLabの[CI/CD](/glossary/ci-cd/)パイプラインで複数のジョブが並行実行される場合、各ジョブが独立して[API](/glossary/api/)を呼び出すと累積的に[レート制限](/glossary/レート制限/)に達します。特に、依存関係の解決やアーティファクトダウンロードで多数の[API](/glossary/api/)呼び出しが発生する環境では顕著です。

**解決策：ページング機能を活用し、複数の[API](/glossary/api/)コールを逐次実行する**

```yaml
stages:
  - build
  - deploy

build_job:
  stage: build
  script:
    - |
      # ページング機能を活用して単一のリクエストに集約
      curl -H "PRIVATE-TOKEN: $CI_JOB_TOKEN" \
           "https://gitlab.example.com/api/v4/projects/$CI_PROJECT_ID/jobs?per_page=100&pagination=keyset&order_by=id&sort=desc"

deploy_job:
  stage: deploy
  script:
    - |
      # 複数のAPIコールを1つのスクリプト内で逐次実行し、遅延を挿入
      API_URL="https://gitlab.example.com/api/v4/projects/$CI_PROJECT_ID"
      TOKEN="$CI_JOB_TOKEN"
      
      curl -H "PRIVATE-TOKEN: $TOKEN" "$API_URL/merge_requests?per_page=100"
      sleep 2
      curl -H "PRIVATE-TOKEN: $TOKEN" "$API_URL/pipelines?per_page=100"
      sleep 2
      curl -H "PRIVATE-TOKEN: $TOKEN" "$API_URL/issues?per_page=100"
```

### 原因3：レスポンスヘッダーの確認なしに即座に再試行している

429[エラー](/glossary/エラー/)を受け取った後、RateLimit-Reset[ヘッダー](/glossary/ヘッダー/)を確認せず、すぐに再試行するとさらに制限に抵触します。適切な待機時間を設定することが重要です。

**解決策：RateLimit-Reset[ヘッダー](/glossary/ヘッダー/)から次のリセット時刻を取得して待機する**

```javascript
async function fetchProjectData(projectId) {
  const token = "<your-access-token>";
  const maxRetries = 5;
  
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      const response = await fetch(
        `https://gitlab.example.com/api/v4/projects/${projectId}`,
        { headers: { "PRIVATE-TOKEN": token } }
      );
      
      if (response.status === 429) {
        // RateLimit-Resetヘッダーから次のリセット時刻を取得
        const resetTime = parseInt(response.headers.get("RateLimit-Reset") || Date.now() / 1000 + 60);
        const currentTime = Math.floor(Date.now() / 1000);
        const waitSeconds = Math.max(resetTime - currentTime, 1);
        
        console.log(`Rate limited. Waiting ${waitSeconds} seconds until ${new Date(resetTime * 1000).toISOString()}...`);
        await new Promise(resolve => setTimeout(resolve, waitSeconds * 1000 + 500));
        continue;
      }
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      return await response.json();
    } catch (error) {
      console.error(error);
      if (attempt < maxRetries - 1) {
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
    }
  }
}
```

## GitLab固有の注意点

GitLabの[レート制限](/glossary/レート制限/)は、[トークン](/glossary/トークン/)の[スコープ](/glossary/スコープ/)やユーザーの[ロール](/glossary/ロール/)、[エンドポイント](/glossary/エンドポイント/)によって異なります。個人用アクセストークン（Personal Access Token）を使用する場合、該当する[トークン](/glossary/トークン/)に関連付けられたユーザーの制限が適用されます。GitLab管理者は、`/api/v4/admin/application_settings`[エンドポイント](/glossary/エンドポイント/)を通じて[インスタンス](/glossary/インスタンス/)全体の[レート制限](/glossary/レート制限/)を確認・調整可能です。

また、[CI/CD](/glossary/ci-cd/)パイプライン内で使用する`$CI_JOB_TOKEN`はジョブ固有の[トークン](/glossary/トークン/)で、個人用アクセストークンとは独立した[レート制限](/glossary/レート制限/)が適用される場合があります。[GraphQL](/glossary/graphql/) [API](/glossary/api/)を使用する場合、[REST](/glossary/rest/) [API](/glossary/api/)とは異なる[クエリ](/glossary/クエリ/)の複雑さに基づいた[モデル](/glossary/モデル/)が採用されているため注意が必要です。

バッチ処理への転換では、`per_page`パラメーターを100（最大値）に設定し、ページネーション機能を活用することで、単位時間あたりの[リクエスト](/glossary/リクエスト/)数を大幅に削減できます。

## それでも解決しない場合

まず、GitLab[インスタンス](/glossary/インスタンス/)の管理画面から現在のレート制限設定を確認してください。[管理者権限](/glossary/管理者権限/)がある場合、以下の[コマンド](/glossary/コマンド/)でインスタンスレベルの制限を確認できます：

```bash
curl -H "PRIVATE-TOKEN: <admin-token>" \
     "https://gitlab.example.com/api/v4/admin/application_settings" | grep -i rate
```

ユーザーレベルの制限状況は、任意の[API](/glossary/api/)呼び出しのレスポンスヘッダーから確認できます：

```bash
curl -i -H "PRIVATE-TOKEN: <your-access-token>" \
     "https://gitlab.example.com/api/v4/user" | grep -i "ratelimit"
```

継続的に429[エラー](/glossary/エラー/)が発生する場合は、GitLab管理者に以下の情報とともに相談してください：

- [エラー](/glossary/エラー/)が発生する時間帯と頻度
- 使用している[API](/glossary/api/)[エンドポイント](/glossary/エンドポイント/)
- [リクエスト](/glossary/リクエスト/)送信元のIP アドレスや[トークン](/glossary/トークン/)種別
- [インスタンス](/glossary/インスタンス/)のGitLab [バージョン](/glossary/バージョン/)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*