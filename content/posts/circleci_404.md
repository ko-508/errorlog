---
title: "CircleCI の 404 エラー：原因と解決策"
date: 2026-06-20
description: "パイプラインまたはプロジェクトが見つからない"
tags: ["CircleCI"]
errorCode: "404"
service: "CircleCI"
error_type: "404"
components: []
related_services: ["GitHub", "Bitbucket"]
---

## エラーの概要

CircleCI の 404 [エラー](/glossary/エラー/)は、指定されたプロジェクト・パイプライン・ワークフローが見つからないことを示します。[API](/glossary/api/)呼び出しやWebUI での操作時に、存在しないリソースへアクセスしようとした場合に発生する最も一般的な[エラー](/glossary/エラー/)です。この[エラー](/glossary/エラー/)はしばしばプロジェクトスラッグの誤記、パイプライン[ID](/glossary/id/)の指定ミス、あるいはVCS（GitHub・Bitbucket）との認可情報の失効に起因します。

## 実際のエラーメッセージ例

CircleCI [API](/glossary/api/) v2 からの典型的な 404 [レスポンス](/glossary/レスポンス/)：

```json
{
  "message": "Project not found",
  "type": "project_not_found"
}
```

パイプラインが見つからない場合：

```json
{
  "message": "Pipeline not found",
  "type": "pipeline_not_found"
}
```

## よくある原因と解決手順

### 原因1：プロジェクトスラッグの形式が誤っている

CircleCI [API](/glossary/api/) では、プロジェクトを識別するために `vcs-type/org-name/repo-name` 形式のスラッグを使用します。このスラッグが正確でない場合、プロジェクトが見つからずに 404 [エラー](/glossary/エラー/)が返されます。特に、組織名や[リポジトリ](/glossary/リポジトリ/)名にハイフンやアンダースコアが含まれる場合や、VCS タイプの指定を間違えた場合に多く発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
curl -X GET "https://circleci.com/api/v2/project/github/MyOrg/my-repo/pipeline" \
  -H "Circle-Token: <your-circleci-api-token>"
```

この例では、スラッグに大文字が含まれており、CircleCI は大文字小文字を区別するため 404 が返ります。

**After（修正後）：**

```bash
curl -X GET "https://circleci.com/api/v2/project/github/myorg/my-repo/pipeline" \
  -H "Circle-Token: <your-circleci-api-token>"
```

WebUI で確認したプロジェクト URL（例：`https://app.circleci.com/pipelines/github/myorg/my-repo`）から正確なスラッグを抽出して使用します。

### 原因2：パイプラインID またはワークフローID が存在しない

パイプラインやワークフローを直接指定する際に、存在しない[ID](/glossary/id/) を使用すると 404 [エラー](/glossary/エラー/)が発生します。これは [ID](/glossary/id/) の入力ミス、削除済みパイプラインへのアクセス、あるいは別のプロジェクトのパイプライン[ID](/glossary/id/) を誤って使用した場合に起こります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
curl -X GET "https://circleci.com/api/v2/pipeline/abc123def456/config" \
  -H "Circle-Token: <your-circleci-api-token>"
```

ここで指定したパイプライン[ID](/glossary/id/) が実際には存在しない、または削除済みです。

**After（修正後）：**

```bash
# 先にプロジェクトのパイプラインリストを取得して、正しいIDを確認
curl -X GET "https://circleci.com/api/v2/project/github/myorg/my-repo/pipeline" \
  -H "Circle-Token: <your-circleci-api-token>" | jq '.items[] | .id'

# その後、確認したIDでパイプライン詳細を取得
curl -X GET "https://circleci.com/api/v2/pipeline/correct-pipeline-id-12345/config" \
  -H "Circle-Token: <your-circleci-api-token>"
```

パイプラインが実際に存在するか、先にリスト取得 [API](/glossary/api/) で確認してから詳細情報にアクセスします。

### 原因3：GitHub / Bitbucket との認可情報が失効またはリセット

CircleCI とGitHub・Bitbucket の連携が切れると、そのプロジェクトにアクセスできず 404 [エラー](/glossary/エラー/)が返されることがあります。これは、VCS 側で[認可](/glossary/認可/)を取り消した、CircleCI の[認証](/glossary/認証/)[トークン](/glossary/トークン/)が失効した、あるいはユーザーの[アカウント](/glossary/アカウント/)[権限](/glossary/権限/)が変更された場合に発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# VCS連携が切れているプロジェクトへのアクセス試行
curl -X GET "https://circleci.com/api/v2/project/github/myorg/my-repo" \
  -H "Circle-Token: <your-circleci-api-token>"
```

この[リクエスト](/glossary/リクエスト/)が 401（Unauthorized）や 404 を返す場合、VCS 連携の問題が疑われます。

**After（修正後）：**

```bash
# CircleCI WebUI でプロジェクト設定ページに移動し、
# "Project Settings" > "VCS" または "Integrations" から
# GitHub/Bitbucket との再認証を実行

# CLIの場合、CircleCI personal token を更新
# https://app.circleci.com/settings/user/tokens にアクセスして
# 新しいトークンを生成し、ローカル環境に設定
export CIRCLECI_TOKEN=<your-new-circleci-api-token>

# その後、プロジェクトアクセスを再試行
curl -X GET "https://circleci.com/api/v2/project/github/myorg/my-repo" \
  -H "Circle-Token: $CIRCLECI_TOKEN"
```

WebUI から [OAuth](/glossary/oauth/) 再認証を実行するか、[API](/glossary/api/) [トークン](/glossary/トークン/)を再生成して設定し直します。

## ツール固有の注意点

**プロジェクトスラッグのURL エンコード：**
[API](/glossary/api/) 呼び出しでスラッグを URL パスの一部として使用する場合、特殊文字が含まれていればURL エンコードが必要です。例えば、組織名が `my-org` であれば、そのまま使用できますが、スペースやその他の記号が含まれる場合は適切にエンコードしてください。

```bash
# スラッグに特殊文字がある場合の例
ENCODED_SLUG=$(python3 -c "import urllib.parse; print(urllib.parse.quote('github/my-org/my repo', safe='/'))")
curl -X GET "https://circleci.com/api/v2/project/$ENCODED_SLUG" \
  -H "Circle-Token: <your-circleci-api-token>"
```

**パイプラインフィルタリング：**
複数のパイプラインが存在する場合、`?filter=` [パラメータ](/glossary/パラメータ/)を使用してフィルタリングできます。これにより、特定の条件に一致するパイプラインのみを取得し、[ID](/glossary/id/) の確認が容易になります。

```bash
curl -X GET "https://circleci.com/api/v2/project/github/myorg/my-repo/pipeline?filter=completed" \
  -H "Circle-Token: <your-circleci-api-token>"
```

## それでも解決しない場合

**1. 認可情報と[権限](/glossary/権限/)の確認**

CircleCI WebUI に[ログイン](/glossary/ログイン/)して、以下の確認を行ってください：
- 対象プロジェクトへの[アクセス権限](/glossary/アクセス権限/)があるか（プロジェクト一覧に表示されているか）
- VCS 連携状態が「Connected」になっているか（Project Settings > VCS）

**2. [API](/glossary/api/) [トークン](/glossary/トークン/)の[スコープ](/glossary/スコープ/)確認**

使用している [API](/glossary/api/) [トークン](/glossary/トークン/)の[スコープ](/glossary/スコープ/)が十分か確認します。Personal Token の場合、`view:project` と `read:project` の[スコープ](/glossary/スコープ/)が必要です。

```bash
# 現在のトークンの情報を確認
curl -X GET "https://circleci.com/api/v2/me" \
  -H "Circle-Token: <your-circleci-api-token>"
```

**3. [ネットワーク](/glossary/ネットワーク/)と[ログ](/glossary/ログ/)の確認**

CircleCI のステータスページ（`https://status.circleci.com`）でサービス障害がないか確認し、AWS CloudWatch [ログ](/glossary/ログ/)（ジョブログ）に[エラー](/glossary/エラー/)詳細がないか確認してください。

**4. 公式ドキュメントと [API](/glossary/api/) リファレンス**

CircleCI [API](/glossary/api/) v2 の公式ドキュメント（`https://circleci.com/docs/api/v2/`）で、対象[エンドポイント](/glossary/エンドポイント/)の仕様を再確認し、[パラメータ](/glossary/パラメータ/)の形式や[スコープ](/glossary/スコープ/)の要件を確認してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*