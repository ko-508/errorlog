---
title: "GitHub API の 422 エラー：原因と解決策"
date: 2026-01-01
description: "422 Unprocessable Entity は、HTTPリクエストの形式は正しいものの、送信されたデータが GitHub API の検証ルールに違反している場合に返されるステータスコードです。"
tags: ["GitHub API"]
errorCode: "422"
lastmod: 2026-05-29
---

## エラーの概要

422 Unprocessable Entity は、[HTTP](/glossary/http/)[リクエスト](/glossary/リクエスト/)の形式は正しいものの、送信されたデータが GitHub [API](/glossary/api/) の検証ルールに違反している場合に返される[ステータスコード](/glossary/ステータスコード/)です。GitHub [API](/glossary/api/) では、[リクエストボディ](/glossary/リクエストボディ/)のフィールド値が不正、重複、無効な状態、または不足している時に発生します。このエラーは 400 系の汎用的なクライアントエラーとは異なり、**データの意味的な問題**を指摘します。

## 実際のエラーメッセージ例

GitHub [API](/glossary/api/) が返す 422 [エラーレスポンス](/glossary/エラーレスポンス/)の典型例を以下に示します。

```json
{
  "message": "Validation Failed",
  "errors": [
    {
      "resource": "Issue",
      "field": "title",
      "code": "missing"
    }
  ],
  "documentation_url": "https://docs.github.com/rest/issues/issues?apiVersion=2022-11-28#create-an-issue"
}
```

別の例として、[ブランチ](/glossary/ブランチ/)作成時に既存の[ブランチ](/glossary/ブランチ/)名を指定した場合：

```json
{
  "message": "Validation Failed",
  "errors": [
    {
      "message": "Reference already exists",
      "documentation_url": "https://docs.github.com/rest/git/refs?apiVersion=2022-11-28#create-a-reference",
      "resource": "GitRef",
      "field": "ref",
      "code": "already_exists"
    }
  ]
}
```

## よくある原因と解決手順

### 原因 1: 必須フィールドが不足している

**なぜ発生するか**  
Issue や Pull Request 作成時に、`title` など必須[パラメータ](/glossary/パラメータ/)を省略するとこのエラーが発生します。GitHub [API](/glossary/api/) の各[エンドポイント](/glossary/エンドポイント/)には、[リクエストボディ](/glossary/リクエストボディ/)に含める必須フィールドが定義されており、これらが欠けていると検証に失敗します。

**Before（エラーが起きるコード）**
```bash
curl -X POST https://api.github.com/repos/<owner>/<repo>/issues \
  -H "Authorization: token <your-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "body": "This is the issue description"
  }'
```

**After（修正後）**
```bash
curl -X POST https://api.github.com/repos/<owner>/<repo>/issues \
  -H "Authorization: token <your-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Bug: Login button not responding",
    "body": "This is the issue description"
  }'
```

### 原因 2: 既に存在するリソースを重複作成しようとしている

**なぜ発生するか**  
[ブランチ](/glossary/ブランチ/)やリリース、ラベルなど、[リポジトリ](/glossary/リポジトリ/)内で一意性が求められるリソースを作成する際に、同じ名前のリソースが既に存在する場合に 422 エラーが返されます。

**Before（エラーが起きるコード）**
```bash
curl -X POST https://api.github.com/repos/<owner>/<repo>/git/refs \
  -H "Authorization: token <your-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "ref": "refs/heads/main",
    "sha": "abc1234567890def"
  }'
```

**After（修正後：[ブランチ](/glossary/ブランチ/)が存在するか確認してから作成）**
```bash
# 既存ブランチを確認
curl -s https://api.github.com/repos/<owner>/<repo>/branches \
  -H "Authorization: token <your-token>" | grep '"name"'

# 新しいブランチ名で作成
curl -X POST https://api.github.com/repos/<owner>/<repo>/git/refs \
  -H "Authorization: token <your-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "ref": "refs/heads/feature/new-feature",
    "sha": "abc1234567890def"
  }'
```

### 原因 3: フィールド値の形式が不正または制約に違反している

**なぜ発生するか**  
フィールド値の型が不正（文字列ではなく数値を期待など）、文字数制限を超過している、または許可されない値を指定した場合に検証エラーとなります。例えば、Issue のラベルに存在しないラベルを指定、または状態フィールドに無効な値を指定するケースです。

**Before（エラーが起きるコード）**
```javascript
const axios = require('axios');

axios.post(
  'https://api.github.com/repos/<owner>/<repo>/issues',
  {
    title: 'New Issue',
    labels: ['bug', 'non-existent-label'],  // 存在しないラベルを指定
    assignee: 12345  // 文字列である必要があります
  },
  {
    headers: {
      'Authorization': 'token <your-token>',
      'Content-Type': 'application/json'
    }
  }
).catch(err => console.log(err.response.data));
```

**After（修正後）**
```javascript
const axios = require('axios');

axios.post(
  'https://api.github.com/repos/<owner>/<repo>/issues',
  {
    title: 'New Issue',
    labels: ['bug', 'enhancement'],  // リポジトリに存在するラベルのみを使用
    assignee: 'username'  // 文字列でユーザー名を指定
  },
  {
    headers: {
      'Authorization': 'token <your-token>',
      'Content-Type': 'application/json'
    }
  }
).then(res => console.log(res.status)).catch(err => console.log(err.response.data));
```

## ツール固有の注意点

### GitHub API バージョンと API Preview の影響

GitHub [API](/glossary/api/) には複数のバージョンが存在し、リクエストヘッダの `Accept` ヘッダで指定した [API](/glossary/api/) バージョンによって、同じ[パラメータ](/glossary/パラメータ/)でも検証ルールが異なる場合があります。特に [GraphQL](/glossary/graphql/) [API](/glossary/api/) と [REST](/glossary/rest/) [API](/glossary/api/) の間、または [REST](/glossary/rest/) [API](/glossary/api/) の異なるバージョン間で相違が生じることがあります。

```bash
# 明示的に API バージョンを指定する場合
curl -X POST https://api.github.com/repos/<owner>/<repo>/issues \
  -H "Authorization: token <your-token>" \
  -H "Accept: application/vnd.github.v3+json" \
  -H "Content-Type: application/json" \
  -d '{"title": "Issue Title"}'
```

### Pull Request 関連の検証エラー

Pull Request 作成時の 422 エラーでよくある原因は、ベースブランチとヘッドブランチが同じ、またはマージベースが存在しない場合です。

```bash
# エラーになるケース：同じブランチを指定
curl -X POST https://api.github.com/repos/<owner>/<repo>/pulls \
  -H "Authorization: token <your-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "PR Title",
    "head": "main",
    "base": "main"
  }'

# 正しい例：異なるブランチを指定
curl -X POST https://api.github.com/repos/<owner>/<repo>/pulls \
  -H "Authorization: token <your-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "PR Title",
    "head": "feature/my-feature",
    "base": "main"
  }'
```

### Release・Tag 作成時の制約

Release やタグ作成時は、タグ名が有効な Git 参照形式であることが必須です。また、タグが既に存在する場合、または指定した SHA [コミット](/glossary/コミット/)が存在しない場合も 422 エラーが発生します。

## それでも解決しない場合

### ログ確認とデバッグ方法

GitHub [CLI](/glossary/cli/) を使用している場合、`--verbose` フラグでエラーの詳細情報を確認できます。

```bash
gh api repos/<owner>/<repo>/issues --verbose
```

[REST](/glossary/rest/) [API](/glossary/api/) を直接呼び出す場合、レスポンスボディの `errors` フィールドに詳細な検証エラー情報が含まれているため、必ず確認してください。

```bash
curl -i -X POST https://api.github.com/repos/<owner>/<repo>/issues \
  -H "Authorization: token <your-token>" \
  -H "Content-Type: application/json" \
  -d '{}' 2>&1 | grep -A 20 "errors"
```

### 公式リソースの確認

GitHub [API](/glossary/api/) エラーの詳細は、[GitHub REST API ドキュメント](https://docs.github.com/rest)の該当[エンドポイント](/glossary/エンドポイント/)のページで「Validation」セクションを確認してください。[エラーレスポンス](/glossary/エラーレスポンス/)に含まれる `documentation_url` フィールドから直接該当ドキュメントにアクセスすることもできます。

### コミュニティサポート

[GitHub Community Discussions](https://github.com/orgs/community/discussions) や [GitHub Issue トラッカー](https://github.com/github/docs/issues)で、同じ問題が報告されていないか検索することも有効です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*