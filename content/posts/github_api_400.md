---
title: "GitHub API の 400 エラー：原因と解決策"
date: 2026-01-01
description: "GitHub APIの400エラーは「Bad Request」を意味し、クライアント側の送信内容に問題があることを示します。リクエストの形式が不正だったり、必須パラメータが不足していたり、パラメータ値が無効だったりするときに発生します。"
tags: ["GitHub API"]
errorCode: "400"
lastmod: 2026-05-31
---

## エラーの概要

GitHub [API](/glossary/api/)の400[エラー](/glossary/エラー/)は「Bad Request」を意味し、クライアント側の送信内容に問題があることを示します。[リクエスト](/glossary/リクエスト/)の形式が不正だったり、必須[パラメータ](/glossary/パラメータ/)が不足していたり、[パラメータ](/glossary/パラメータ/)値が無効だったりするときに発生します。この[エラー](/glossary/エラー/)が発生した場合、[サーバー](/glossary/サーバー/)側に問題があるのではなく、[API](/glossary/api/)への呼び出し方を見直す必要があります。

## 実際のエラーメッセージ例

GitHub [API](/glossary/api/)が返す実際の400[エラーレスポンス](/glossary/エラーレスポンス/)は以下のようなものです。

```json
{
  "message": "Problems parsing JSON",
  "documentation_url": "https://docs.github.com/rest"
}
```

あるいはバリデーションエラーの場合：

```json
{
  "message": "Validation Failed",
  "errors": [
    {
      "message": "Required field \"title\" is missing",
      "field": "title",
      "code": "missing_field"
    }
  ],
  "documentation_url": "https://docs.github.com/rest/reference/issues#create-an-issue"
}
```

## よくある原因と解決手順

### 原因1：JSONの形式が不正である

**なぜ発生するか**
[リクエストボディ](/glossary/リクエストボディ/)を[JSON](/glossary/json/)形式で送信する際に、ダブルクォートの閉じ忘れやカンマの不足など、[JSON](/glossary/json/)形式として正しくない構文を送ってしまった場合に発生します。

**Before（[エラー](/glossary/エラー/)が起きる例）**
```bash
curl -X POST https://api.github.com/repos/<owner>/<repo>/issues \
  -H "Authorization: token <your-token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "New issue" "body": "This is a test"}'
```

上記の例では、`"New issue"`と`"body"`の間にカンマがありません。

**After（修正後）**
```bash
curl -X POST https://api.github.com/repos/<owner>/<repo>/issues \
  -H "Authorization: token <your-token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "New issue", "body": "This is a test"}'
```

### 原因2：必須パラメータが不足している

**なぜ発生するか**
[API](/glossary/api/)[エンドポイント](/glossary/エンドポイント/)が要求する必須[パラメータ](/glossary/パラメータ/)を[リクエスト](/glossary/リクエスト/)に含めていない場合に発生します。例えば、IssueやPull Requestの作成時に`title`が必須なのに省略した場合などです。

**Before（[エラー](/glossary/エラー/)が起きる例）**
```javascript
const octokit = require('@octokit/rest')({
  auth: '<your-token>'
});

await octokit.rest.issues.create({
  owner: '<owner>',
  repo: '<repo>',
  // title フィールドが省略されている
  body: 'Issue description'
});
```

**After（修正後）**
```javascript
const octokit = require('@octokit/rest')({
  auth: '<your-token>'
});

await octokit.rest.issues.create({
  owner: '<owner>',
  repo: '<repo>',
  title: 'Issue Title',  // 必須フィールドを追加
  body: 'Issue description'
});
```

### 原因3：パラメータ値が無効な形式である

**なぜ発生するか**
[パラメータ](/glossary/パラメータ/)値の型や値そのものが、[API](/glossary/api/)が期待する形式と異なっている場合に発生します。例えば、数値として解釈されるべき値に文字列を渡した場合や、指定可能な値（enum）の範囲外の値を渡した場合などです。

**Before（[エラー](/glossary/エラー/)が起きる例）**
```bash
curl -X GET "https://api.github.com/repos/<owner>/<repo>/issues?state=opened" \
  -H "Authorization: token <your-token>"
```

`state`[パラメータ](/glossary/パラメータ/)の値は「open」「closed」「all」のいずれかであるべきなのに、「opened」という無効な値を指定しています。

**After（修正後）**
```bash
curl -X GET "https://api.github.com/repos/<owner>/<repo>/issues?state=open" \
  -H "Authorization: token <your-token>"
```

### 原因4：Content-Typeヘッダーが不正である

**なぜ発生するか**
[リクエストボディ](/glossary/リクエストボディ/)を送信する際に、`Content-Type`[ヘッダー](/glossary/ヘッダー/)を指定していなかったり、間違った値を指定していたりすると、[サーバー](/glossary/サーバー/)が正しくボディをパースできず[エラー](/glossary/エラー/)になります。

**Before（[エラー](/glossary/エラー/)が起きる例）**
```bash
curl -X POST https://api.github.com/repos/<owner>/<repo>/issues \
  -H "Authorization: token <your-token>" \
  -d '{"title": "New issue", "body": "Test"}'
```

Content-Type[ヘッダー](/glossary/ヘッダー/)を指定していません。

**After（修正後）**
```bash
curl -X POST https://api.github.com/repos/<owner>/<repo>/issues \
  -H "Authorization: token <your-token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "New issue", "body": "Test"}'
```

## GitHub API固有の注意点

GitHub [API](/glossary/api/)には複数のバージョンが存在し、[エンドポイント](/glossary/エンドポイント/)の仕様がバージョンによって異なります。`Accept`[ヘッダー](/glossary/ヘッダー/)で[API](/glossary/api/) バージョンを指定する場合、不正なバージョン番号を指定すると400[エラー](/glossary/エラー/)が返されます。

公式ドキュメントでは常に最新の[REST](/glossary/rest/) [API](/glossary/api/)仕様が提供されているため、使用している[API](/glossary/api/) バージョンと実装コードが一致しているかを確認してください。特に[GraphQL](/glossary/graphql/) [API](/glossary/api/)と[REST](/glossary/rest/) [API](/glossary/api/)を混同しないことが重要です。

また、[レート制限](/glossary/レート制限/)（Rate Limiting）による429[エラー](/glossary/エラー/)と異なり、400[エラー](/glossary/エラー/)は[リクエスト](/glossary/リクエスト/)形式自体の問題のため、リトライアは効果がありません。むしろ[リクエスト](/glossary/リクエスト/)形式を修正することに注力すべきです。

特定の[エンドポイント](/glossary/エンドポイント/)（例：Pull Request レビューコメントの作成）では、[パラメータ](/glossary/パラメータ/)の組み合わせに対して厳密なバリデーションが行われるため、公式ドキュメントの[パラメータ](/glossary/パラメータ/)説明を隅々まで読むことが不可欠です。

## それでも解決しない場合

まずは、[リクエスト](/glossary/リクエスト/)の内容をPythonの`json`モジュールやオンラインの[JSON](/glossary/json/)検証ツール（JSONlint等）を使って、形式が正しいかを検証してください。

```bash
echo '{"title": "Test", "body": "Body"}' | python3 -m json.tool
```

次に、GitHub [API](/glossary/api/)の公式ドキュメント内の「[REST](/glossary/rest/) [API](/glossary/api/) reference」から、使用している[エンドポイント](/glossary/エンドポイント/)のページを開き、必須[パラメータ](/glossary/パラメータ/)と各[パラメータ](/glossary/パラメータ/)の型・制約を改めて確認してください。

それでも解決しない場合は、GitHub's Community Forum（discussions.github.com）またはGitHub Support に問い合わせることをお勧めします。[リクエスト](/glossary/リクエスト/)の実例を示すことで、より具体的なアドバイスが得られます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*