---
draft: true
title: "CircleCI の 401 エラー：原因と解決策"
date: 2026-06-20
description: "CircleCIへの認証に失敗した"
tags: ["CircleCI"]
errorCode: "401"
service: "CircleCI"
error_type: "401"
components: []
related_services: ["curl", "CircleCI CLI"]
---

## エラーの概要

CircleCI の 401 [エラー](/glossary/エラー/)は、[API](/glossary/api/) [認証](/glossary/認証/)に失敗したことを示す[ステータスコード](/glossary/ステータスコード/)です。CircleCI に[リクエスト](/glossary/リクエスト/)を送信する際、[API](/glossary/api/)[トークン](/glossary/トークン/)が無効・欠落・期限切れのいずれかの状態にあることが原因で、[リクエスト](/glossary/リクエスト/)が[認可](/glossary/認可/)されません。この[エラー](/glossary/エラー/)は [CI/CD](/glossary/ci-cd/) パイプラインから CircleCI [API](/glossary/api/) を呼び出す場合や、ローカルから [CLI](/glossary/cli/) で操作する際に頻出します。

## 実際のエラーメッセージ例

**CircleCI [CLI](/glossary/cli/) での出力：**

```bash
Error: 401 Unauthorized: Invalid token
Failed to authenticate with CircleCI. Please check your CIRCLE_TOKEN environment variable.
```

**[API](/glossary/api/) [レスポンス](/glossary/レスポンス/)（[JSON](/glossary/json/)）：**

```json
{
  "message": "Unauthorized",
  "errors": [
    {
      "message": "The token is invalid or has expired"
    }
  ]
}
```

## よくある原因と解決手順

### 原因1：APIトークンが無効または削除されている

CircleCI のシステム側で[トークン](/glossary/トークン/)が無効化・削除された、または生成元の[ユーザーアカウント](/glossary/ユーザーアカウント/)が削除された場合、それ以降その[トークン](/glossary/トークン/)はすべての[リクエスト](/glossary/リクエスト/)で 401 を返します。[トークン](/glossary/トークン/)の有効性は CircleCI [ダッシュボード](/glossary/ダッシュボード/)で確認できますが、削除された[トークン](/glossary/トークン/)は履歴にも表示されなくなるため、新たに生成する必要があります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
curl -X GET \
  https://circleci.com/api/v2/me \
  -H "Circle-Token: <your-old-deleted-token>"
```

[レスポンス](/glossary/レスポンス/):
```json
{
  "message": "Unauthorized"
}
```

**After（修正後）：**

```bash
# CircleCI -> User Settings -> Personal API Tokens で新規生成
# 新しいトークンをコピー
NEW_TOKEN="<your-new-personal-api-token>"

curl -X GET \
  https://circleci.com/api/v2/me \
  -H "Circle-Token: ${NEW_TOKEN}"
```

[レスポンス](/glossary/レスポンス/):
```json
{
  "id": "12345678-1234-1234-1234-123456789012",
  "login": "your-username",
  "name": "Your Name"
}
```

### 原因2：CIRCLE_TOKEN 環境変数が設定されていない

CircleCI のジョブ内から [API](/glossary/api/) を呼び出す場合、`CIRCLE_TOKEN` [環境変数](/glossary/環境変数/)が定義されていないと、curl や [API](/glossary/api/) クライアントライブラリが[トークン](/glossary/トークン/)を含めずに[リクエスト](/glossary/リクエスト/)を送信します。結果として 401 [エラー](/glossary/エラー/)が返ります。この[環境変数](/glossary/環境変数/)はプロジェクト設定またはコンテキスト（Context）で明示的に設定する必要があります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
# .circleci/config.yml
version: 2.1

jobs:
  call_api:
    docker:
      - image: cimg/base:stable
    steps:
      - run:
          name: Call CircleCI API
          command: |
            curl -X GET \
              https://circleci.com/api/v2/me
```

実行時の[エラー](/glossary/エラー/)：
```json
{
  "message": "Unauthorized"
}
```

**After（修正後）：**

```yaml
# .circleci/config.yml
version: 2.1

jobs:
  call_api:
    docker:
      - image: cimg/base:stable
    environment:
      CIRCLE_TOKEN: << pipeline.parameters.api_token >>
    steps:
      - run:
          name: Call CircleCI API
          command: |
            curl -X GET \
              https://circleci.com/api/v2/me \
              -H "Circle-Token: ${CIRCLE_TOKEN}"
```

または Project Settings → Environment Variables で `CIRCLE_TOKEN` を直接登録：

```bash
# CircleCI ダッシュボード → Project Settings → Environment Variables
# キー: CIRCLE_TOKEN
# 値: <your-project-api-token>
```

### 原因3：Personal Access Token と Project Token を使い分けていない

CircleCI では 2 種類の[トークン](/glossary/トークン/)が存在します。Personal [API](/glossary/api/) Token はユーザー個人のリソースへのアクセス用で、Project Token はプロジェクト固有の操作（ステータスチェック、トリガーなど）用です。プロジェクトのワークフローからプロジェクト特有の [API](/glossary/api/) を呼び出す場合、Personal Token では権限不足で 401 が返されることがあります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
# .circleci/config.yml
version: 2.1

jobs:
  trigger_workflow:
    docker:
      - image: cimg/base:stable
    steps:
      - run:
          name: Trigger another workflow
          command: |
            PERSONAL_TOKEN="<your-personal-api-token>"
            curl -X POST \
              https://circleci.com/api/v2/project/gh/your-org/your-repo/pipeline \
              -H "Circle-Token: ${PERSONAL_TOKEN}" \
              -H "Content-Type: application/json" \
              -d '{"branch":"main"}'
```

結果：
```json
{
  "message": "Unauthorized"
}
```

**After（修正後）：**

```yaml
# .circleci/config.yml
version: 2.1

jobs:
  trigger_workflow:
    docker:
      - image: cimg/base:stable
    environment:
      CIRCLE_API_TOKEN: << pipeline.parameters.project_token >>
    steps:
      - run:
          name: Trigger another workflow
          command: |
            curl -X POST \
              https://circleci.com/api/v2/project/gh/your-org/your-repo/pipeline \
              -H "Circle-Token: ${CIRCLE_API_TOKEN}" \
              -H "Content-Type: application/json" \
              -d '{"branch":"main"}'
```

Project Token 取得方法：Project Settings → Project [API](/glossary/api/) Tokens から新規生成。

## ツール固有の注意点

**CircleCI [CLI](/glossary/cli/) との連携：**

CircleCI [CLI](/glossary/cli/) を使用している場合、`~/.circleci/cli.yml` に正しい[トークン](/glossary/トークン/)が設定されていることを確認してください。ローカルで[テスト](/glossary/テスト/)する際は、`CIRCLE_TOKEN` [環境変数](/glossary/環境変数/)を[シェル](/glossary/シェル/)環境に直接設定するか、`~/.circlerc` ファイルに保存します。

```bash
# シェル環境に設定
export CIRCLE_TOKEN="<your-personal-api-token>"
circleci config validate .circleci/config.yml
```

**コンテキスト（Context）の活用：**

複数のプロジェクトで同じ[認証](/glossary/認証/)[トークン](/glossary/トークン/)を共有する場合、CircleCI のコンテキスト機能を使用すると管理が容易になります。Organization Settings → Contexts から新規作成し、[環境変数](/glossary/環境変数/)を一元管理します。

```yaml
workflows:
  main:
    jobs:
      - call_api:
          context: circleci-api-context
```

**[レート制限](/glossary/レート制限/)との区別：**

429 Too Many Requests との混同に注意してください。401 は認証失敗であり、429 は[レート制限](/glossary/レート制限/)です。同じく[認可](/glossary/認可/)[エラー](/glossary/エラー/)の 403 Forbidden との違いも重要で、403 は[トークン](/glossary/トークン/)は有効だが[権限](/glossary/権限/)が不足している状況です。

## それでも解決しない場合

**ステップ1：[トークン](/glossary/トークン/)の有効性をダイレクト確認**

以下の[コマンド](/glossary/コマンド/)で[トークン](/glossary/トークン/)が有効か直接[テスト](/glossary/テスト/)します。

```bash
curl -X GET \
  https://circleci.com/api/v2/me \
  -H "Circle-Token: <your-api-token>"
```

200 OK が返れば、[トークン](/glossary/トークン/)自体は有効です。

**ステップ2：ジョブ実行時のシークレット状態を確認**

CircleCI [ダッシュボード](/glossary/ダッシュボード/) → Job Details → Step Output で[環境変数](/glossary/環境変数/)がマスク（隠蔽）されているか確認します。[環境変数](/glossary/環境変数/)が表示されている場合、[トークン](/glossary/トークン/)が正しく設定されています。

**ステップ3：公式 [API](/glossary/api/) リファレンスの確認**

[CircleCI API v2 Reference](https://circleci.com/docs/api/v2/) で、使用している [API](/glossary/api/) [エンドポイント](/glossary/エンドポイント/)が該当トークンタイプで対応しているか確認します。Personal Token では呼べない[エンドポイント](/glossary/エンドポイント/)も存在します。

**ステップ4：CircleCI サポートへの問い合わせ**

[トークン](/glossary/トークン/)生成時刻、ジョブ [ID](/glossary/id/)、[エラー](/glossary/エラー/)が発生した正確な時刻を記録した上で、CircleCI Support（support@circleci.com）に問い合わせます。[サーバー](/glossary/サーバー/)側の[トークン](/glossary/トークン/)失効・[ユーザーアカウント](/glossary/ユーザーアカウント/)問題の可能性があります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*