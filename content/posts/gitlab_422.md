---
title: "GitLab の 422 エラー：原因と解決策"
date: 2026-06-13
description: "データの内容が検証に失敗した。GitLab 422 エラーの原因と解決策を解説します。"
tags: ["GitLab"]
errorCode: "422"
service: "GitLab"
error_type: "422"
components: ["API", "Merge Request", "Issue", "Project", "Group", "Epic", "Board", "Pipeline Schedule"]
related_services: []
top_queries:
- "gitlab 422 error"
---
## エラーの概要

GitLabの422[エラー](/glossary/エラー/)は「Unprocessable Entity」を意味し、[リクエスト](/glossary/リクエスト/)自体は正しく到達したものの、送信されたデータが検証ルールを満たしていないことを示します。プロジェクト作成、マージリクエスト、イシューなどの[API](/glossary/api/)操作で頻繁に発生し、GitLab[サーバー](/glossary/サーバー/)側がデータの内容を受け入れられない状態です。

## 実際のエラーメッセージ例

GitLabの[API](/glossary/api/)経由で発生した422[エラー](/glossary/エラー/)の典型的な[レスポンス](/glossary/レスポンス/)は以下のような[JSON](/glossary/json/)形式です。

```json
{
  "message": "422 Unprocessable Entity",
  "error": "Validation failed",
  "errors": {
    "title": ["can't be blank"],
    "description": ["is invalid"]
  }
}
```

ブラウザのWebUIで遭遇した場合の[エラー](/glossary/エラー/)表示例：

```
422 Unprocessable Entity
Failed to create merge request: Title can't be blank
```

## よくある原因と解決手順

### 原因1：マージリクエストのタイトルが空白になっている

マージリクエスト作成時にtitleフィールドが空文字列または省略されると、GitLabの検証ルールに違反して422[エラー](/glossary/エラー/)が発生します。GitLab [API](/glossary/api/)ではtitleが必須フィールドとして定義されており、どのような値でも良いわけではなく「空でない文字列」という最小限の検証を通す必要があります。

**修正前（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
curl --request POST \
  --header "PRIVATE-TOKEN: <your-token>" \
  "https://<your-gitlab-instance>/api/v4/projects/<project-id>/merge_requests" \
  --data "source_branch=feature-branch&target_branch=main&title="
```

**修正後：**

```bash
curl --request POST \
  --header "PRIVATE-TOKEN: <your-token>" \
  "https://<your-gitlab-instance>/api/v4/projects/<project-id>/merge_requests" \
  --data "source_branch=feature-branch&target_branch=main&title=Add new feature"
```

### 原因2：プロジェクト名がグループのルールに違反している

グループレベルで名前の長さ制限や命名規則が設定されている場合、その規則に適合しないプロジェクト名で作成しようとすると422[エラー](/glossary/エラー/)が返されます。特に大規模な組織では、プロジェクト命名を統一するためにグループ管理者が検証ルールを配置していることがあります。

**修正前（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
curl --request POST \
  --header "PRIVATE-TOKEN: <your-token>" \
  "https://<your-gitlab-instance>/api/v4/projects" \
  --data "name=ThisProjectNameIsWayTooLongAndViolatesGroupNameLengthRestrictions&namespace_id=<group-id>"
```

**修正後：**

```bash
curl --request POST \
  --header "PRIVATE-TOKEN: <your-token>" \
  "https://<your-gitlab-instance>/api/v4/projects" \
  --data "name=my-project&namespace_id=<group-id>"
```

### 原因3：カスタムフィールドまたは属性の値が許容範囲外

GitLabで定義されたカスタムフィールドやEpic、ボード、パイプラインスケジュールなどの属性値が、あらかじめ設定された範囲（例：数値の上限値、選択肢の外の文字列、日付フォーマットの不一致）から外れている場合に422[エラー](/glossary/エラー/)が発生します。

**修正前（[エラー](/glossary/エラー/)が起きるコード）：**

```json
{
  "title": "New Issue",
  "description": "Test issue",
  "weight": 100,
  "labels": "non-existent-label"
}
```

**修正後：**

```json
{
  "title": "New Issue",
  "description": "Test issue",
  "weight": 10,
  "labels": "bug,documentation"
}
```

## ツール固有の注意点

GitLabでは422[エラー](/glossary/エラー/)が返る際、レスポンスボディの`errors`フィールドに検証に失敗したフィールドと理由が詳細に記載されます。[API](/glossary/api/)利用時は必ずこのフィールドを確認して、具体的にどのフィールドが問題かを特定することが重要です。

ブラウザのデベロッパーツール（F12キー）のネットワークタブで、失敗した[リクエスト](/glossary/リクエスト/)の[レスポンス](/glossary/レスポンス/)を確認すれば、[エラー](/glossary/エラー/)詳細を即座に把握できます。また、グループやプロジェクトレベルでカスタム検証ルールが設定されている場合、GitLab管理画面の「グループ設定」→「詳細」または「プロジェクト設定」から確認可能です。

マージリクエストテンプレートが設定されているプロジェクトでは、テンプレートの必須フィールドを満たさないと422[エラー](/glossary/エラー/)が発生することもあります。この場合、プロジェクト設定の「マージリクエスト」セクションでテンプレート内容を確認してください。

## それでも解決しない場合

GitLabの[API](/glossary/api/)[レスポンス](/glossary/レスポンス/)に記載されている`errors`フィールドの内容をそのまま確認することで、検証ルールの具体的な要件を明確にできます。以下の[コマンド](/glossary/コマンド/)で[JSON](/glossary/json/)整形済みの[エラー](/glossary/エラー/)詳細を確認してください。

```bash
curl -i --request POST \
  --header "PRIVATE-TOKEN: <your-token>" \
  "https://<your-gitlab-instance>/api/v4/projects" \
  --data "name=test&namespace_id=<group-id>" | jq '.errors'
```

GitLab[インスタンス](/glossary/インスタンス/)の管理者[ログ](/glossary/ログ/)（通常は `/var/log/gitlab/gitlab-rails/production.log`）を確認することで、[サーバー](/glossary/サーバー/)側での検証処理の詳細が記録されている場合があります。また、カスタムプラグインや検証ルールが導入されている場合は、[Git](/glossary/git/)管理者に確認してください。

公式ドキュメント「[GitLab API - Error responses](https://docs.gitlab.com/ee/api/#error-responses)」に各[HTTP](/glossary/http/)[ステータスコード](/glossary/ステータスコード/)の標準的な意味が記載されており、プロジェクト固有のルール設定については「[Projects API](https://docs.gitlab.com/ee/api/projects.html)」を参照してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*