---
title: "GitHub API の 409 エラー：原因と解決策"
date: 2026-05-24
description: "GitHub APIの409（Conflict）は、リクエストの内容がGitHubのリソース現在の状態と矛盾していることを示すステータスコードです。"
tags: ["GitHub API"]
errorCode: "409"
lastmod: 2026-06-13
service: "GitHub API"
error_type: "409"
components: []
related_services: ["Octokit"]
trend_incident: true
---

## エラーの概要

GitHub APIの409（Conflict）は、リクエストの内容がGitHubのリソースの現在の状態と矛盾していることを示すステータスコードです。ブランチの作成、プルリクエストの作成、リリースの公開など、状態が重要な操作時に頻繁に発生します。このエラーは単なる一時的な失敗ではなく、リクエスト自体を見直す必要があることを示唆しています。

## 実際のエラーメッセージ例

```json
{
  "message": "Validation Failed",
  "errors": [
    {
      "message": "Reference already exists",
      "resource": "Reference",
      "field": "ref"
    }
  ],
  "documentation_url": "https://docs.github.com/rest/git/refs#create-a-reference"
}
```

```json
{
  "message": "Pull Request creation failed.",
  "errors": [
    {
      "message": "No commits between main and feature-branch",
      "resource": "PullRequest",
      "field": "head"
    }
  ],
  "documentation_url": "https://docs.github.com/rest/pulls#create-a-pull-request"
}
```

## よくある原因と解決手順

### 原因1：ブランチまたはタグがすでに存在する

ブランチやタグを作成しようとしたときに、同じ名前のリファレンスが既に存在する場合、409エラーが発生します。これは特に自動化スクリプトやCI/CDパイプラインで複数回実行される際に起こりやすい問題です。

**Before（エラーが起きるコード）：**

```python
import requests

headers = {
    "Authorization": "token <your-github-token>",
    "Accept": "application/vnd.github.v3+json"
}

# ブランチを作成する（既に存在していても409エラーになる）
response = requests.post(
    "https://api.github.com/repos/<owner>/<repo>/git/refs",
    headers=headers,
    json={
        "ref": "refs/heads/feature-branch",
        "sha": "abc123def456"
    }
)

if response.status_code == 409:
    print("ブランチ作成に失敗しました")
```

**After（修正後）：**

```python
import requests

headers = {
    "Authorization": "token <your-github-token>",
    "Accept": "application/vnd.github.v3+json"
}

# 先にブランチの存在を確認する
check_response = requests.get(
    "https://api.github.com/repos/<owner>/<repo>/git/refs/heads/feature-branch",
    headers=headers
)

if check_response.status_code == 404:
    # ブランチが存在しないので作成
    response = requests.post(
        "https://api.github.com/repos/<owner>/<repo>/git/refs",
        headers=headers,
        json={
            "ref": "refs/heads/feature-branch",
            "sha": "abc123def456"
        }
    )
    print(f"ブランチを作成しました: {response.status_code}")
else:
    print("ブランチは既に存在します")
```

### 原因2：プルリクエストのheadとbaseが同じ、または変更が存在しない

プルリクエストを作成する際に、baseとheadが同じブランチを指しているか、またはhead側に新しいコミットがない場合、409エラーが発生します。これは特にフィーチャーブランチが最新であると信じ込んでいる場合に起こります。

**Before（エラーが起きるコード）：**

```javascript
const octokit = require("@octokit/rest")({
  auth: "<your-github-token>"
});

// mainブランチと同じコミット位置のブランチからPRを作成しようとする
octokit.pulls.create({
  owner: "<owner>",
  repo: "<repo>",
  title: "Fix bug",
  head: "main",  // baseと同じブランチを指している！
  base: "main"
}).catch(err => {
  console.error("PR作成失敗:", err.response.data.message);
});
```

**After（修正後）：**

```javascript
const octokit = require("@octokit/rest")({
  auth: "<your-github-token>"
});

// 先にブランチの最新コミットを確認
const headBranch = await octokit.repos.getBranch({
  owner: "<owner>",
  repo: "<repo>",
  branch: "feature-branch"
});

const baseBranch = await octokit.repos.getBranch({
  owner: "<owner>",
  repo: "<repo>",
  branch: "main"
});

// コミットSHAが異なる場合のみPRを作成
if (headBranch.data.commit.sha !== baseBranch.data.commit.sha) {
  const pr = await octokit.pulls.create({
    owner: "<owner>",
    repo: "<repo>",
    title: "Fix bug",
    head: "feature-branch",
    base: "main"
  });
  console.log("PR作成完了:", pr.data.number);
} else {
  console.log("変更が存在しないため、PRは作成できません");
}
```

### 原因3：リリース(Release)のタグが既に存在している

リリースを作成する際に、指定したタグが既に存在する場合、409エラーが発生します。特に再度同じバージョンでリリースを作成しようとした場合に起こります。

**Before（エラーが起きるコード）：**

```bash
curl -X POST \
  https://api.github.com/repos/<owner>/<repo>/releases \
  -H "Authorization: token <your-github-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "tag_name": "v1.0.0",
    "name": "Version 1.0.0",
    "body": "Release notes"
  }'
# すでにv1.0.0タグが存在していると409が返る
```

**After（修正後）：**

```bash
# 先にタグが存在するか確認
tag_exists=$(curl -s \
  https://api.github.com/repos/<owner>/<repo>/git/refs/tags/v1.0.0 \
  -H "Authorization: token <your-github-token>" \
  -w "%{http_code}" -o /dev/null)

if [ "$tag_exists" = "404" ]; then
  # タグが存在しない場合のみリリースを作成
  curl -X POST \
    https://api.github.com/repos/<owner>/<repo>/releases \
    -H "Authorization: token <your-github-token>" \
    -H "Content-Type: application/json" \
    -d '{
      "tag_name": "v1.0.0",
      "name": "Version 1.0.0",
      "body": "Release notes"
    }'
else
  echo "タグ v1.0.0 は既に存在します"
fi
```

## GitHub API固有の注意点

### コンフリクト検出の厳密性

GitHub APIは様々なリソースで409エラーを返すため、エラーレスポンスの`errors`フィールドの内容を必ず確認してください。`message`フィールドだけでなく、`resource`と`field`を組み合わせることで、どのリソースのどのフィールドが原因かを特定できます。例えば、Referenceリソースの場合は`"ref"`フィールド、PullRequestリソースの場合は`"head"`または`"base"`フィールドに関する情報が含まれます。

### ステータスコードの見落とし

API呼び出し時に、HTTPステータスコードの確認を習慣づけてください。特にバッチ処理やループ内での複数リクエスト時に、成功判定を`201`または`200`のみに限定しがちです。409を含むエラーコードを事前に把握して処理フローを設計することが重要です。

### 冪等性への対応

自動化スクリプトではリトライロジックが一般的ですが、409エラーはリトライで解決しません。むしろ既存リソースの確認と条件判定を組み込んだ冪等な設計を心がけてください。`GET`リクエストで存在確認後に`POST`/`PATCH`を実行する流れが推奨されます。

## それでも解決しない場合

### デバッグステップ

1. `curl -v`でリクエスト・レスポンスヘッダをすべて確認し、実際の409レスポンスボディを表示させる
2. GitHub APIのリソース状態を手動で確認する（Web UIで同じブランチ・PRが存在しないか目視確認）
3. APIレスポンスの`documentation_url`フィールドに記載されたドキュメントを参照し、そのリソースの409発生条件を再確認する

### 公式リソース

- [GitHub REST API エラーハンドリング](https://docs.github.com/ja/rest?apiVersion=2022-11-28)
- [Git Refs API ドキュメント](https://docs.github.com/rest/git/refs)
- [Pulls API ドキュメント](https://docs.github.com/rest/pulls)
- [Releases API ドキュメント](https://docs.github.com/rest/releases)

### コミュニティリソース

GitHub公式リポジトリの[Discussions](https://github.com/github/feedback/discussions)やStack Overflowの`github-api`タグで、同様の事例が報告されていないか検索してください。特にアクセス権限周辺の問題の場合、GitHub Supportへの問い合わせが最も確実です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*