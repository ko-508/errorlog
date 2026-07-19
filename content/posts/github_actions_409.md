---
draft: true
title: "GitHub Actions の 409 エラー：原因と解決策"
date: 2026-06-29
description: "HTTPステータスコード409 Conflictは、リクエストがサーバー上のリソースの現在の状態と競合していることを示し。"
tags: ["GitHub Actions"]
errorCode: "409"
urgency: "medium"
service: "GitHub Actions"
error_type: "409"
components: ["Actions"]
related_services: ["Azure App Service", "GitHub API"]
---

## エラーの概要

[HTTP](/glossary/http/) [ステータスコード](/glossary/ステータスコード/) 409 は、[リクエスト](/glossary/リクエスト/)が[サーバー](/glossary/サーバー/)上のリソースの現在の状態と競合していることを示します。GitHub Actions では、別の[デプロイ](/glossary/デプロイ/)が進行中である場合や複数の同時更新が[ファイル](/glossary/ファイル/)のハッシュ値と競合している場合、または[ポリシー](/glossary/ポリシー/)変更が[リポジトリ](/glossary/リポジトリ/)権限設定と競合する場合に発生することが多いです。

## 実際のエラーメッセージ例

```
Failed to deploy web package to App Service. Conflict (CODE: 409).
```

```json
{
  "statusCode": 409,
  "statusMessage": "Conflict",
  "headers": {
    "connection": "close",
    "content-type": "text/plain; charset=utf-8",
    "date": "nnnnnnnn",
    "server": "xxxxx",
    "transfer-encoding": "chunked",
    "scm-deployment-id": "xxxxxxxxxxxxxxxxx"
  },
  "body": "There is a deployment currently in progress. Please try again when it completes."
}
```

```
Error: PUT https://ndia.ghe.com/api/v3/repos/<organization>/<repository>/actions/permissions: 409 []
```

**[エラーメッセージ](/glossary/エラーメッセージ/)の読み方：**

- `409` → [HTTP](/glossary/http/) [ステータスコード](/glossary/ステータスコード/)：[リクエスト](/glossary/リクエスト/)が[サーバー](/glossary/サーバー/)のリソース状態と競合している
- `Conflict` → 理由フレーズ：複数の操作や状態の不整合を示す
- `"There is a deployment currently in progress. Please try again when it completes."` → [エラー](/glossary/エラー/)本体：別の[デプロイ](/glossary/デプロイ/)がまだ実行中であることを明示
- `scm-deployment-id` → デプロイメント [ID](/glossary/id/)：進行中の[デプロイ](/glossary/デプロイ/)を特定するための識別子
- `statusCode: 409` → [JSON](/glossary/json/) 形式のレスポンスボディ：プログラムで処理可能な形式で[エラー](/glossary/エラー/)を通知

## よくある原因と解決手順

### 原因1：別のデプロイが進行中

複数のワークフロー実行が同時に[デプロイ](/glossary/デプロイ/)を試みた場合、同じ[アプリケーション](/glossary/アプリケーション/)に対する競合が発生します。Azure App Service などでは、一度に 1 つのデプロイメントのみを受け付けるため、進行中の[デプロイ](/glossary/デプロイ/)が完了するまで待つ必要があります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
name: Deploy to Azure
on:
  push:
    branches:
      - main
  pull_request:
    branches:
      - main

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Deploy to App Service
        uses: azure/webapps-deploy@v1
        with:
          app-name: <your-app-name>
          publish-profile: ${{ secrets.AZURE_PUBLISH_PROFILE }}
          package: ./build
```

**After（修正後）：**

```yaml
name: Deploy to Azure
on:
  push:
    branches:
      - main

jobs:
  deploy:
    runs-on: ubuntu-latest
    concurrency:
      group: deployment-${{ github.ref }}
      cancel-in-progress: false
    steps:
      - uses: actions/checkout@v3
      - name: Deploy to App Service
        uses: azure/webapps-deploy@v1
        with:
          app-name: <your-app-name>
          publish-profile: ${{ secrets.AZURE_PUBLISH_PROFILE }}
          package: ./build
```

✅ 修正後の確認：

```bash
# Azure ポータルの App Service デプロイブレードで、デプロイが順序立てて実行されていることを確認します。
# GitHub Actions ログに「Waiting for deployment to complete」というメッセージが表示されず、
# 連続したデプロイが成功すれば競合は解決しています。
```

### 原因2：ファイルハッシュ（SHA）の不一致による同時更新競合

GitHub [API](/glossary/api/) で[ファイル](/glossary/ファイル/)を更新する際、[リクエスト](/glossary/リクエスト/)に含まれる SHA（[ファイル](/glossary/ファイル/)の現在のハッシュ値）が[サーバー](/glossary/サーバー/)上の実際の状態と一致しない場合に発生します。特に複数のワークフロー実行が同じ[ファイル](/glossary/ファイル/)を同時に更新しようとすると、最初の更新後に 2 番目の[リクエスト](/glossary/リクエスト/)の SHA が古くなり競合します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
import requests
import base64

GITHUB_TOKEN = "<your-github-token>"
REPO = "organization/repository"
FILE_PATH = "config.yaml"

headers = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

# ファイルを取得
response = requests.get(
    f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}",
    headers=headers
)
file_data = response.json()
current_sha = file_data["sha"]
current_content = base64.b64decode(file_data["content"]).decode()

# 内容を更新
updated_content = current_content.replace("key: old", "key: new")
encoded_content = base64.b64encode(updated_content.encode()).decode()

# 複数のリクエストが同時に実行されるとここで SHA が古くなり 409 が発生
response = requests.put(
    f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}",
    headers=headers,
    json={
        "message": "Update config",
        "content": encoded_content,
        "sha": current_sha
    }
)

if response.status_code == 409:
    print("Conflict: File was updated by another process")
```

**After（修正後）：**

```python
import requests
import base64
import time

GITHUB_TOKEN = "<your-github-token>"
REPO = "organization/repository"
FILE_PATH = "config.yaml"
MAX_RETRIES = 3

headers = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

def update_file_with_retry(repo, file_path, new_content, message):
    for attempt in range(MAX_RETRIES):
        # 更新直前に最新の SHA を取得
        response = requests.get(
            f"https://api.github.com/repos/{repo}/contents/{file_path}",
            headers=headers
        )
        file_data = response.json()
        current_sha = file_data["sha"]

        encoded_content = base64.b64encode(new_content.encode()).decode()

        response = requests.put(
            f"https://api.github.com/repos/{repo}/contents/{file_path}",
            headers=headers,
            json={
                "message": message,
                "content": encoded_content,
                "sha": current_sha
            }
        )

        if response.status_code == 200:
            print(f"File updated successfully")
            return True
        elif response.status_code == 409:
            print(f"Conflict detected. Retrying... (attempt {attempt + 1}/{MAX_RETRIES})")
            time.sleep(10)  # 他のプロセスに時間を与える
        else:
            print(f"Error: {response.status_code}")
            return False

    return False

# 使用例
update_file_with_retry(
    REPO,
    FILE_PATH,
    "key: new_value",
    "Update config with retry logic"
)
```

✅ 修正後の確認：

```bash
# スクリプトを実行して、複数回のコンフリクトが発生しても最終的に成功することを確認します。
python update_file.py
# 出力に「File updated successfully」が表示されれば、リトライロジックが機能しています。
```

### 原因3：Organization/Enterprise レベルのポリシーと権限設定の競合

Organization または Enterprise レベルで GitHub Actions の[ポリシー](/glossary/ポリシー/)が設定されている場合、リポジトリレベルでの権限削除やアクセス設定の変更が禁止されていることがあります。[API](/glossary/api/) 経由で `actions/permissions` [エンドポイント](/glossary/エンドポイント/)にアクセスするとこの競合が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
const { Octokit } = require("@octokit/rest");

const octokit = new Octokit({
  auth: "<your-github-token>"
});

async function updateActionsPermissions() {
  try {
    // Organization のポリシーが有効な場合、リポジトリレベルで権限を変更しようとすると 409 が発生
    const response = await octokit.rest.actions.setRepositoryAccessToSelfHostedRunners({
      owner: "organization",
      repo: "repository",
      access_level: "none"
    });
    console.log("Permissions updated:", response.data);
  } catch (error) {
    if (error.status === 409) {
      console.error("Conflict: Organization policy prevents this change");
    }
  }
}

updateActionsPermissions();
```

**After（修正後）：**

```javascript
const { Octokit } = require("@octokit/rest");

const octokit = new Octokit({
  auth: "<your-github-token>"
});

async function getActionsPermissions() {
  try {
    // まず現在の権限設定を確認
    const response = await octokit.rest.actions.getRepositoryAccessToSelfHostedRunners({
      owner: "organization",
      repo: "repository"
    });
    console.log("Current permissions:", response.data);

    // Organization ポリシーの制限がないか確認
    if (response.data.access_level === "organization") {
      console.log("Organization policy is enforced. Check with org admins.");
      return false;
    }

    return true;
  } catch (error) {
    console.error("Error fetching permissions:", error.message);
    return false;
  }
}

async function updateActionsPermissionsWithCheck() {
  const canUpdate = await getActionsPermissions();

  if (canUpdate) {
    try {
      const response = await octokit.rest.actions.setRepositoryAccessToSelfHostedRunners({
        owner: "organization",
        repo: "repository",
        access_level: "user"
      });
      console.log("Permissions updated successfully:", response.data);
    } catch (error) {
      if (error.status === 409) {
        console.error("Conflict: Retry after resolving organizational constraints");
      }
    }
  }
}

updateActionsPermissionsWithCheck();
```

✅ 修正後の確認：

```bash
# スクリプトを実行して、Organization ポリシーの確認と権限更新が順番に実行されることを確認します。
node update_permissions.js
# 「Current permissions」が表示され、その後「Permissions updated successfully」が出力されれば成功です。
```

### 原因4：マージ競合のある PR を API 経由でマージしようとした場合

GitHub [API](/glossary/api/) でマージリクエストを送信した際に、自動的に解決できない[マージ](/glossary/マージ/)競合が存在すると 409 [エラー](/glossary/エラー/)が返されます。この場合、[API](/glossary/api/) では解決できず、手動での対応が必要です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
const { Octokit } = require("@octokit/rest");

const octokit = new Octokit({
  auth: "<your-github-token>"
});

async function mergePullRequest() {
  try {
    const response = await octokit.rest.pulls.merge({
      owner: "organization",
      repo: "repository",
      pull_number: 42,
      merge_method: "squash"
    });
    console.log("PR merged:", response.data);
  } catch (error) {
    if (error.status === 409) {
      console.error("Cannot merge: Conflicting changes exist");
    }
  }
}

mergePullRequest();
```

**After（修正後）：**

```javascript
const { Octokit } = require("@octokit/rest");

const octokit = new Octokit({
  auth: "<your-github-token>"
});

async function checkAndMergePullRequest() {
  try {
    // まず PR の状態を確認
    const pr = await octokit.rest.pulls.get({
      owner: "organization",
      repo: "repository",
      pull_number: 42
    });

    console.log("PR state:", pr.data.state);
    console.log("Mergeable:", pr.data.mergeable);
    console.log("Mergeable state:", pr.data.mergeable_state);

    // mergeable_state が "dirty" の場合はマージ競合がある
    if (pr.data.mergeable_state === "dirty") {
      console.error("This PR has merge conflicts that cannot be automatically resolved.");
      console.error("Please resolve conflicts manually on GitHub before merging.");
      return false;
    }

    if (!pr.data.mergeable) {
      console.error("PR is not mergeable. Check for conflicts or CI failures.");
      return false;
    }

    // マージ可能な場合のみマージを実行
    const response = await octokit.rest.pulls.merge({
      owner: "organization",
      repo: "repository",
      pull_number: 42,
      merge_method: "squash"
    });
    console.log("PR merged successfully:", response.data);
    return true;

  } catch (error) {
    if (error.status === 409) {
      console.error("Merge conflict detected. Manual intervention required.");
      console.error("Visit https://github.com/organization/repository/pull/42 to resolve");
    } else {
      console.error("Error:", error.message);
    }
    return false;
  }
}

checkAndMergePullRequest();
```

✅ 修正後の確認：

```bash
# スクリプトを実行して、PR の状態が確認され、mergeable_state が checked であれば成功です。
node merge_pr.js
# 出力に「PR merged successfully」が表示されるか、競合がある場合は「mergeable_state: dirty」が表示されます。
```

## 解決策の早見表

| 解決策 | 実装難易度 | 再起動要否 | 対応[OS](/glossary/os/) |
|--------|-----------|-----------|-------|
| 同時[デプロイ](/glossary/デプロイ/)の制御（concurrency） | 低 | 不要 | 全[OS](/glossary/os/) |
| [ファイル](/glossary/ファイル/)更新時の SHA リトライロジック | 中 | 不要 | 全[OS](/glossary/os/) |
| [ポリシー](/glossary/ポリシー/)競合の事前確認 | 中 | 不要 | 全[OS](/glossary/os/) |
| [マージ](/glossary/マージ/)可能性の検証 | 低 | 不要 | 全[OS](/glossary/os/) |

## ツール固有の注意点

**Azure App Service への[デプロイ](/glossary/デプロイ/)時の確認**

`azure/webapps-deploy` アクションを使用して[エラー](/glossary/エラー/) 409 が発生した場合、Azure ポータルのデプロイブレードで詳細を確認する必要があります。Kudu（App Service の高度な管理ツール）で進行中の[デプロイ](/glossary/デプロイ/)を強制停止できます。

```bash
# App Service のスケーリング中や再起動中に競合が発生することもあります
# Azure CLI で現在のデプロイ状態を確認
az webapp deployment list --resource-group <your-resource-group> --name <your-app-name>
```

**GitHub Enterprise での権限設定**

GitHub Enterprise 2.20 以降では、Enterprise Admin が Actions のアクセスポリシーを一元管理しています。リポジトリレベルでの権限変更は Enterprise [ポリシー](/glossary/ポリシー/)に制限されるため、変更前に Enterprise Admin に確認が必要な場合があります。

**複数[ファイル](/glossary/ファイル/)更新時の [Git](/glossary/git/) Tree [API](/glossary/api/)**

複数の[ファイル](/glossary/ファイル/)を同時に更新する場合、個別の PUT [リクエスト](/glossary/リクエスト/)を連続送信するのではなく、[Git](/glossary/git/) Tree [API](/glossary/api/) を使用して一括更新する方法が 409 [エラー](/glossary/エラー/)を回避しやすいです。

```javascript
// 複数ファイルを一度に更新する場合の例
const treeData = [
  {
    path: "config/app.yaml",
    mode: "100644",
    type: "blob",
    content: "updated_content_1"
  },
  {
    path: "config/db.yaml",
    mode: "100644",
    type: "blob",
    content: "updated_content_2"
  }
];

const tree = await octokit.rest.git.createTree({
  owner: "organization",
  repo: "repository",
  tree: treeData,
  base_tree: "main"
});
```

## それでも解決しない場合

[ログ](/glossary/ログ/)の確認と[デバッグ](/glossary/デバッグ/)手順を実施してください。

**GitHub Actions [ログ](/glossary/ログ/)で詳細を確認**

ワークフロー実行ページの `Logs` タブで完全な[エラーメッセージ](/glossary/エラーメッセージ/)を確認します。デバッグモードを有効化することでより詳細な情報が表示されます。

```bash
# ワークフロー内でデバッグモードを有効化（secrets.ACTIONS_STEP_DEBUG を設定）
echo "::debug::Current SHA: ${{ github.sha }}"
```

**Azure App Service の詳細[ログ](/glossary/ログ/)**

```bash
# Kudu サイトでストリーミングログを確認
https://<your-app-name>.scm.azurewebsites.net/api/logstream

# または Azure CLI で直近のデプロイログを表示
az webapp log tail --resource-group <your-resource-group> --name <your-app-name>
```

**GitHub [API](/glossary/api/) の詳細確認**

curl で[リクエスト](/glossary/リクエスト/)を手動実行し、レスポンスヘッダーの `X-RateLimit-*` や `Etag` を確認します。

```bash
curl -v -H "Authorization: token <your-github-token>" \
  https://api.github.com/repos/<organization>/<repository>/actions/permissions
```

**公式ドキュメント参照**

- [GitHub Actions: Workflow syntax](https://docs.github.com/en/actions/using-workflows/workflow-syntax-

> **調査について**　この記事の解決策は、GitHub Issues・Stack Overflow への公開報告（azure/webapps-deploy@v1, GitHub Enterprise 2.20 環境での報告を含む）を Gemini + Google Search で検索・精査し、実効性の高いものを整理したものです。参照元の [URL](/glossary/url/) は Editor's Note に記載しています。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*