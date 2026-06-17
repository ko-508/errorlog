---
title: "GitLab の 409 エラー：原因と解決策"
date: 2026-06-13
description: "リソースの状態が競合している。GitLab 409 エラーの原因と解決策を解説します。"
tags: ["GitLab"]
errorCode: "409"
service: "GitLab"
error_type: "409"
components: ["API", "MergeRequest", "Branch", "Tag", "Group", "Project"]
related_services: ["Git", "CI/CD"]
top_queries:
- '409エラー'
---
## エラーの概要

[HTTP](/glossary/http/) 409 Conflict [エラー](/glossary/エラー/)は、GitLab 上でリソースの状態が競合している場合に発生します。既に存在する[ブランチ](/glossary/ブランチ/)やタグ名での作成、MergeRequest のソースとターゲットブランチの重複、あるいは同名のグループ・プロジェクトの存在などが典型的な原因です。この[エラー](/glossary/エラー/)が発生すると、意図した操作がブロックされ、リソースの作成や更新が完了しません。

## 実際のエラーメッセージ例

GitLab [API](/glossary/api/) の 409 [エラー](/glossary/エラー/)は、以下のような[レスポンス](/glossary/レスポンス/)で返されます。

```json
{
  "message": "409 Conflict"
}
```

[REST](/glossary/rest/) [API](/glossary/api/) でより詳細な情報が返される場合もあります。

```json
{
  "message": {
    "base": ["Branch already exists"]
  }
}
```

また、GitLab UI で[ブランチ](/glossary/ブランチ/)作成時に失敗する場合は、以下のような通知メッセージが表示されます。

```
Error: A branch with name 'main' already exists
```

## よくある原因と解決手順

### 原因 1：既に存在するブランチ名またはタグ名で作成しようとしている

[ブランチ](/glossary/ブランチ/)やタグの作成時に、既に同名のリソースが存在する場合、409 [エラー](/glossary/エラー/)が発生します。これは [Git](/glossary/git/) の基本的な制約で、同じ名前空間内で重複する[ブランチ](/glossary/ブランチ/)やタグを持つことはできません。[API](/glossary/api/) 経由での[ブランチ](/glossary/ブランチ/)作成や、[CI/CD](/glossary/ci-cd/) パイプライン内での自動[ブランチ](/glossary/ブランチ/)生成時に特に注意が必要です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# 既に 'develop' ブランチが存在する場合、同じ名前で再度作成しようとする
curl --request POST https://gitlab.example.com/api/v4/projects/<project-id>/repository/branches \
  --header "PRIVATE-TOKEN: <your-token>" \
  --data "branch=develop&ref=main"
```

**After（修正後）：**

```bash
# 事前にブランチの存在を確認してから作成する
RESPONSE=$(curl --request GET https://gitlab.example.com/api/v4/projects/<project-id>/repository/branches/develop \
  --header "PRIVATE-TOKEN: <your-token>" \
  --write-out "\n%{http_code}")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)

# ブランチが存在しない場合（404）のみ作成
if [ "$HTTP_CODE" = "404" ]; then
  curl --request POST https://gitlab.example.com/api/v4/projects/<project-id>/repository/branches \
    --header "PRIVATE-TOKEN: <your-token>" \
    --data "branch=develop&ref=main"
else
  echo "Branch already exists"
fi
```

### 原因 2：MergeRequest のソースブランチとターゲットブランチが同じになっている

MergeRequest を作成する際、ソースブランチとターゲットブランチが同じ場合に 409 [エラー](/glossary/エラー/)が発生します。これは論理的に無意味な操作（自分自身への[マージ](/glossary/マージ/)）であるため、GitLab はこれを防止しています。複雑なパイプライン設定や自動化スクリプト内で、[ブランチ](/glossary/ブランチ/)[変数](/glossary/変数/)の設定ミスにより起こることがあります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# ソースブランチとターゲットブランチが同じ 'main' になっている
curl --request POST https://gitlab.example.com/api/v4/projects/<project-id>/merge_requests \
  --header "PRIVATE-TOKEN: <your-token>" \
  --data "source_branch=main&target_branch=main&title=Test MR"
```

**After（修正後）：**

```bash
# ソースブランチとターゲットブランチが異なることを確認してから作成
SOURCE_BRANCH="feature/new-feature"
TARGET_BRANCH="develop"

if [ "$SOURCE_BRANCH" != "$TARGET_BRANCH" ]; then
  curl --request POST https://gitlab.example.com/api/v4/projects/<project-id>/merge_requests \
    --header "PRIVATE-TOKEN: <your-token>" \
    --data "source_branch=$SOURCE_BRANCH&target_branch=$TARGET_BRANCH&title=Add new feature"
fi
```

### 原因 3：同名のグループやプロジェクトがすでに存在する

グループまたはプロジェクトを作成する際、同じ名前空間内に既に同名のリソースが存在する場合に 409 [エラー](/glossary/エラー/)が発生します。GitLab では、同じグループ内のプロジェクト名やサブグループ名はユニークである必要があります。特にテナント分離や自動プロビジョニング環境では、[冪等性](/glossary/冪等性/)（何度実行しても結果が同じ性質）を考慮した設計が重要です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# 既に存在するプロジェクト 'my-project' を再度作成しようとする
curl --request POST https://gitlab.example.com/api/v4/projects \
  --header "PRIVATE-TOKEN: <your-token>" \
  --data "name=my-project&namespace_id=<group-id>"
```

**After（修正後）：**

```bash
# 事前にプロジェクトの存在を確認してから作成
PROJECT_NAME="my-project"
GROUP_ID="<group-id>"

# プロジェクトが既に存在するか確認
EXISTING_PROJECT=$(curl --request GET https://gitlab.example.com/api/v4/projects \
  --header "PRIVATE-TOKEN: <your-token>" \
  --data "search=$PROJECT_NAME" | grep -c "\"path\":\"$PROJECT_NAME\"")

if [ "$EXISTING_PROJECT" -eq 0 ]; then
  curl --request POST https://gitlab.example.com/api/v4/projects \
    --header "PRIVATE-TOKEN: <your-token>" \
    --data "name=$PROJECT_NAME&namespace_id=$GROUP_ID"
else
  echo "Project $PROJECT_NAME already exists"
fi
```

## ツール固有の注意点

GitLab の 409 [エラー](/glossary/エラー/)は、[REST](/glossary/rest/) [API](/glossary/api/) と [GraphQL](/glossary/graphql/) [API](/glossary/api/) の両方で発生する可能性があります。[GraphQL](/glossary/graphql/) を使用している場合、[エラーメッセージ](/glossary/エラーメッセージ/)の形式が異なることに注意してください。また、GitLab の自動[マージ](/glossary/マージ/)機能（Auto-Merge）を使用している場合、パイプライン実行中にソースブランチが削除されると競合状態が発生し、409 [エラー](/glossary/エラー/)に繋がることがあります。

さらに、GitLab [インスタンス](/glossary/インスタンス/)（環境）が複数の[サーバー](/glossary/サーバー/)で構成されている場合、レプリケーション遅延により一時的に 409 [エラー](/glossary/エラー/)が発生することがあります。特に直後の操作では、短時間の待機を挟むことが推奨されます。GitLab [CI/CD](/glossary/ci-cd/) パイプラインで[ブランチ](/glossary/ブランチ/)やタグを自動生成する場合は、適切な[バックオフ](/glossary/バックオフ/)戦略（待機時間を段階的に増やして再試行する手法）を実装することが重要です。

[CI/CD](/glossary/ci-cd/) 設定内で[ブランチ](/glossary/ブランチ/)作成を行う場合、以下の点を確認してください。

```yaml
# 冪等性を持たせたパイプライン例
create_release_branch:
  script:
    - BRANCH_NAME="release/${CI_COMMIT_SHORT_SHA}"
    - |
      if ! git ls-remote --heads origin $BRANCH_NAME | grep -q $BRANCH_NAME; then
        git checkout -b $BRANCH_NAME
        git push origin $BRANCH_NAME
      fi
```

## それでも解決しない場合

まず、GitLab [インスタンス](/glossary/インスタンス/)の[ログ](/glossary/ログ/)を確認してください。プロジェクト[管理者権限](/glossary/管理者権限/)がある場合、管理者パネルの「[ログ](/glossary/ログ/)」セクションで詳細な[エラー](/glossary/エラー/)情報を確認できます。[API](/glossary/api/) レベルでは、[デバッグ](/glossary/デバッグ/)用の[ヘッダー](/glossary/ヘッダー/)を追加して詳細な[レスポンス](/glossary/レスポンス/)を取得してください。

```bash
# 詳細なエラー応答を確認する
curl -v --request POST https://gitlab.example.com/api/v4/projects/<project-id>/repository/branches \
  --header "PRIVATE-TOKEN: <your-token>" \
  --header "X-Request-ID: debug-$(date +%s)" \
  --data "branch=develop&ref=main"
```

GitLab [サーバー](/glossary/サーバー/)のシステムログ（通常は `/var/log/gitlab/` 配下）も確認の対象です。特に `gitlab-rails/production.log` と `gitlab-rails/api_json.log` には詳細な情報が記録されています。問題が継続する場合は、GitLab の公式ドキュメント（https://docs.gitlab.com/ee/api/）を参照するか、GitLab サポートに問い合わせることをお勧めします。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*