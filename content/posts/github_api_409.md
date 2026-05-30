---
title: "GitHub API の 409 エラー：原因と解決策"
date: 2026-05-24
description: "GitHub APIの409（Conflict）は、リクエストの内容がGitHubのリソース現在の状態と矛盾していることを示すステータスコードです。"
tags: ["GitHub API"]
errorCode: "409"
lastmod: 2026-05-31
---

## エラーの概要

GitHub [API](/glossary/api/)の409（Conflict）は、[リクエスト](/glossary/リクエスト/)の内容がGitHubのリソース現在の状態と矛盾していることを示す[ステータスコード](/glossary/ステータスコード/)です。[ブランチ](/glossary/ブランチ/)の作成、プルリクエストの作成、リリースの公開など、状態が重要な操作時に頻繁に発生します。このエラーは単なる一時的な失敗ではなく、[リクエスト](/glossary/リクエスト/)自体を見直す必要があることを示唆しています。

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
  "message": "Pull Request already exists",
  "documentation_url": "https://docs.github.com/rest/pulls#create-a-pull-request"
}
```

## よくある原因と解決手順

### 原因1：ブランチが既に存在する

**なぜ発生するか**：同じ名前の[ブランチ](/glossary/ブランチ/)を作成しようとすると、既存の[ブランチ](/glossary/ブランチ/)と競合して409エラーが発生します。

**Before（エラーが起きるコード）**：
```bash
curl -X POST https://api.github.com/repos/<owner>/<repo>/git/refs \
  -H "Authorization: token <your-token>" \
  -d '{
    "ref": "refs/heads/feature-branch",
    "sha": "abc123def456"
  }'
```

**After（修正後）**：
```bash
# 事前にブランチ存在確認
curl -H "Authorization: token <your-token>" \
  https://api.github.com/repos/<owner>/<repo>/git/refs/heads/feature-branch

# 存在しない場合のみ作成
curl -X POST https://api.github.com/repos/<owner>/<repo>/git/refs \
  -H "Authorization: token <your-token>" \
  -d '{
    "ref": "refs/heads/feature-branch-v2",
    "sha": "abc123def456"
  }'
```

### 原因2：同じHEADとBASEでプルリクエストを作成しようとしている

**なぜ発生するか**：プルリクエストのヘッドブランチとベースブランチが同じ場合、またはすでに同じ組み合わせのプルリクエストが存在する場合に発生します。

**Before（エラーが起きるコード）**：
```python
import requests

headers = {"Authorization": "token <your-token>"}
data = {
    "title": "Update docs",
    "head": "main",
    "base": "main"
}

response = requests.post(
    "https://api.github.com/repos/<owner>/<repo>/pulls",
    headers=headers,
    json=data
)
```

**After（修正後）**：
```python
import requests

headers = {"Authorization": "token <your-token>"}
data = {
    "title": "Update docs",
    "head": "feature/doc-update",
    "base": "main"
}

response = requests.post(
    "https://api.github.com/repos/<owner>/<repo>/pulls",
    headers=headers,
    json=data
)

if response.status_code == 409:
    print("既存のプルリクエストを確認してください")
```

### 原因3：タグが既に存在する

**なぜ発生するか**：同じ名前のタグを作成しようとすると、既存のタグと競合します。リリース管理時に頻発します。

**Before（エラーが起きるコード）**：
```javascript
const octokit = new Octokit({ auth: '<your-token>' });

await octokit.rest.git.createRef({
  owner: '<owner>',
  repo: '<repo>',
  ref: 'refs/tags/v1.0.0',
  sha: 'abc123def456'
});
```

**After（修正後）**：
```javascript
const octokit = new Octokit({ auth: '<your-token>' });

// タグ存在確認
try {
  await octokit.rest.git.getRef({
    owner: '<owner>',
    repo: '<repo>',
    ref: 'tags/v1.0.0'
  });
  console.log('タグは既に存在します');
} catch (error) {
  if (error.status === 404) {
    // 存在しないため作成可能
    await octokit.rest.git.createRef({
      owner: '<owner>',
      repo: '<repo>',
      ref: 'refs/tags/v1.0.1',
      sha: 'abc123def456'
    });
  }
}
```

### 原因4：リポジトリの状態が保護されている

**なぜ発生するか**：[ブランチ](/glossary/ブランチ/)保護ルールやリポジトリロックが有効な場合、変更が拒否されて409が返ります。

**Before（エラーが起きるコード）**：
```bash
# メインブランチが保護されていると失敗
curl -X DELETE https://api.github.com/repos/<owner>/<repo>/git/refs/heads/main \
  -H "Authorization: token <your-token>"
```

**After（修正後）**：
```bash
# 保護されたブランチの確認
curl -H "Authorization: token <your-token>" \
  https://api.github.com/repos/<owner>/<repo>/branches/main

# 保護ルールを一時的に無効化（管理権限が必要）
# またはフィーチャーブランチを使用
curl -X POST https://api.github.com/repos/<owner>/<repo>/git/refs \
  -H "Authorization: token <your-token>" \
  -d '{
    "ref": "refs/heads/hotfix-branch",
    "sha": "abc123def456"
  }'
```

## ツール固有の注意点

**GitHub [API](/glossary/api/)のバージョン差分**：[REST](/glossary/rest/) [API](/glossary/api/) v3では一部の[エンドポイント](/glossary/エンドポイント/)の409動作が異なります。[GraphQL](/glossary/graphql/) [API](/glossary/api/)を使用する場合は`ValidationError`の形式が異なるため、エラーハンドリングを確認してください。

**[トークン](/glossary/トークン/)の権限不足**：409ではなく403が返ることもありますが、特定の[スコープ](/glossary/スコープ/)（`repo`、`public_repo`）がない場合は409と判定されることがあります。[トークン](/glossary/トークン/)生成時に適切な[スコープ](/glossary/スコープ/)を付与してください。

**コンフリクトマージとリベース**：[マージ](/glossary/マージ/)競合がある場合、[マージ](/glossary/マージ/)PRの作成時に409ではなく422が返ることが多いです。409が出た場合は競合ではなく「既に同じ操作が存在する」状態を疑ってください。

**[レート制限](/glossary/レート制限/)との関連**：404誤検知により409として報告されることはまれですが、キャッシュレイヤーを経由している場合は再度状態確認してください。

## それでも解決しない場合

**ログの確認方法**：`curl -v`フラグで詳細なレスポンスヘッダーを確認し、`X-RateLimit-Remaining`や`X-GitHub-Request-Id`をメモしてください。

**[API](/glossary/api/)[レスポンス](/glossary/レスポンス/)の詳細確認**：`errors`配列内の`field`と`message`フィールドを精読すると、具体的な競合原因が判明します。

**公式ドキュメント参照**：
- [GitHub REST API - エラーハンドリング](https://docs.github.com/ja/rest/guides/getting-started-with-the-rest-api)
- [ブランチ保護ルール](https://docs.github.com/ja/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches)

**GitHub Community Forum**：[github/community](https://github.com/github/community)[リポジトリ](/glossary/リポジトリ/)のディスカッションで同様の事例を検索すると、より詳細な解決例が見つかることがあります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*