---
title: "GitLab の 400 エラー：原因と解決策"
date: 2026-06-12
description: "GitLab APIへのリクエストの形式または内容に誤りがある。GitLab 400 エラーの原因と解決策を解説します。"
tags: ["GitLab"]
errorCode: "400"
trend_incident: true
---
## エラーの概要

GitLab の 400 [エラー](/glossary/エラー/)は、「Bad Request」を意味し、GitLab [API](/glossary/api/) またはウェブインターフェースへの[リクエスト](/glossary/リクエスト/)の形式や内容に誤りがある場合に発生します。これは、[サーバー](/glossary/サーバー/)が[リクエスト](/glossary/リクエスト/)を正しく解析できない、または必須情報が不足していることを示します。[CI/CD](/glossary/ci-cd/) パイプラインの実行時やプロジェクト管理操作の際に頻出する[エラー](/glossary/エラー/)です。

## 実際のエラーメッセージ例

**[API](/glossary/api/) [リクエスト](/glossary/リクエスト/)の場合：**

```json
{
  "message": "400 Bad Request",
  "error": "Invalid JSON body",
  "error_description": "The request body could not be parsed as JSON"
}
```

**[CI/CD](/glossary/ci-cd/) パイプライン実行時：**

```yaml
ERROR: (ci::pipeline:creation) This project does not have CI enabled
400 Bad Request - The request body contains invalid fields
```

## よくある原因と解決手順

### 原因1：JSON リクエストボディの形式エラーまたは必須フィールドの欠落

GitLab [API](/glossary/api/) への POST/PUT [リクエスト](/glossary/リクエスト/)で、[JSON](/glossary/json/) の形式が壊れているか、[API](/glossary/api/) が必須とするフィールドが含まれていません。特に issue 作成や merge request の更新時に頻発します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
curl -X POST "https://gitlab.example.com/api/v4/projects/<project_id>/issues" \
  -H "PRIVATE-TOKEN: <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "New Issue"
    "description": "Missing comma and required labels field"
  }'
```

**After（修正後）：**

```bash
curl -X POST "https://gitlab.example.com/api/v4/projects/<project_id>/issues" \
  -H "PRIVATE-TOKEN: <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "New Issue",
    "description": "Correct JSON format with all required fields",
    "labels": ["bug"]
  }'
```

### 原因2：.gitlab-ci.yml ファイルの YAML 構文エラー

`.gitlab-ci.yml` の [YAML](/glossary/yaml/) 構文が壊れている場合、パイプライン作成時に 400 [エラー](/glossary/エラー/)が返されます。インデント不正、不正なキー名、型の不一致が原因になることが多いです。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
stages:
  - build
  - test

build_job:
  stage: build
  script:
    - echo "Building"
    timeout: 300  # インデントミス
  artifacts:
    paths:
      - build/
    expire_in 30 days  # コロンの欠落

test_job
  stage: test  # コロンの欠落
  script:
    - echo "Testing"
```

**After（修正後）：**

```yaml
stages:
  - build
  - test

build_job:
  stage: build
  script:
    - echo "Building"
  timeout: 300
  artifacts:
    paths:
      - build/
    expire_in: 30 days

test_job:
  stage: test
  script:
    - echo "Testing"
```

### 原因3：API パラメーター値が許可範囲外またはサポートされていない値

GitLab [API](/glossary/api/) の各[エンドポイント](/glossary/エンドポイント/)（接続先）では、パラメーター（設定項目）の値に制約があります。例えば、優先度レベル、ユーザーロール、有効期限の日数などが指定値外の場合に 400 [エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
import requests

url = "https://gitlab.example.com/api/v4/projects/<project_id>/members"
headers = {"PRIVATE-TOKEN": "<token>"}
data = {
    "user_id": 123,
    "access_level": 99,  # 有効なレベルは 10～50
    "expires_at": "2020-01-01"  # 過去の日付
}

response = requests.post(url, json=data, headers=headers)
print(response.json())
```

**After（修正後）：**

```python
import requests
from datetime import datetime, timedelta

url = "https://gitlab.example.com/api/v4/projects/<project_id>/members"
headers = {"PRIVATE-TOKEN": "<token>"}

# 30日先の日付を有効期限として設定
future_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

data = {
    "user_id": 123,
    "access_level": 30,  # Developer レベル（有効値：10-50）
    "expires_at": future_date
}

response = requests.post(url, json=data, headers=headers)
print(response.json())
```

## ツール固有の注意点

**GitLab CI Lint を活用した検証：**

`.gitlab-ci.yml` の構文[エラー](/glossary/エラー/)は、GitLab の公式 CI Lint ツール（`Settings` → `CI/CD` → `CI Lint`）を使用すると、[エラー](/glossary/エラー/)行と理由を詳細に確認できます。ローカルでパイプラインを[テスト](/glossary/テスト/)したい場合は、GitLab Runner に `--debug` フラグを付けて実行すると、詳細な[デバッグ](/glossary/デバッグ/)（問題調査）情報が出力されます。

**[API](/glossary/api/) [レスポンス](/glossary/レスポンス/)（返信）の message フィールドの重要性：**

GitLab [API](/glossary/api/) の 400 [レスポンス](/glossary/レスポンス/)には、`message` フィールドに具体的な[エラー](/glossary/エラー/)内容が含まれています。このメッセージを確認することで、原因を特定する速度が大幅に向上します。例えば「`Expires at date must be after today`」というメッセージから、有効期限の日付が過去に設定されていることが判断できます。

**プロジェクト設定による [CI/CD](/glossary/ci-cd/) 有効化の確認：**

稀に、プロジェクトレベルで [CI/CD](/glossary/ci-cd/) が無効化されていると 400 [エラー](/glossary/エラー/)が返される場合があります。`Settings` → `General` → `Visibility, project features, permissions` で [CI/CD](/glossary/ci-cd/) を有効化しているか確認してください。

## それでも解決しない場合

**1. GitLab システムログの確認：**

[管理者権限](/glossary/管理者権限/)がある場合、`Admin Area` → `Logs` で詳細な[エラーログ](/glossary/エラーログ/)を確認できます。[API](/glossary/api/) [リクエスト](/glossary/リクエスト/)の場合は、`gitlab-rails.log` に 400 [エラー](/glossary/エラー/)の詳細が記録されています。

```bash
# GitLab がインストールされているサーバーで実行
sudo tail -f /var/log/gitlab/gitlab-rails/production.log | grep "400"
```

**2. curl [コマンド](/glossary/コマンド/)で [API](/glossary/api/) [テスト](/glossary/テスト/)：**

以下の[コマンド](/glossary/コマンド/)で[リクエスト](/glossary/リクエスト/)を[テスト](/glossary/テスト/)し、詳細な[エラーレスポンス](/glossary/エラーレスポンス/)を確認できます。

```bash
curl -v -X POST "https://gitlab.example.com/api/v4/projects/<project_id>/issues" \
  -H "PRIVATE-TOKEN: <token>" \
  -H "Content-Type: application/json" \
  -d '{"title":"Test"}'
```

**3. GitLab 公式 [API](/glossary/api/) ドキュメントの参照：**

[GitLab API Documentation](https://docs.gitlab.com/ee/api/) では、各[エンドポイント](/glossary/エンドポイント/)の必須パラメーター、データ型、有効値範囲が明記されています。[エラー](/glossary/エラー/)が続く場合は、該当する[エンドポイント](/glossary/エンドポイント/)のドキュメントを再度確認してください。

**4. GitLab コミュニティフォーラムへの相談：**

問題が解決しない場合、[GitLab Community Forum](https://forum.gitlab.com/) で[エラーレスポンス](/glossary/エラーレスポンス/)、使用している GitLab バージョン、[リクエスト](/glossary/リクエスト/)の詳細を共有して支援を求めることをお勧めします。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*