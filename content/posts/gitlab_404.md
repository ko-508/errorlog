---
title: "GitLab の 404 エラー：原因と解決策"
date: 2026-06-13
description: "指定したリポジトリ・MR・リソースが見つからない。GitLab 404 エラーの原因と解決策を解説します。"
tags: ["GitLab"]
errorCode: "404"
service: "GitLab"
error_type: "404"
components: []
related_services: ["curl", "Python requests"]
---
## エラーの概要

GitLabの404エラーは、指定したプロジェクト・マージリクエスト・ファイルなどのリソースが見つからないことを意味します。API呼び出しやWebUIでのアクセス時に発生し、プロジェクトの存在確認、アクセス権限、リソースパスの誤入力などが主な原因です。

## 実際のエラーメッセージ例

**GitLab API経由でのレスポンス：**

```json
{
  "message": "404 Not Found"
}
```

**curlコマンドでの出力：**

```bash
$ curl -H "PRIVATE-TOKEN: <your-token>" "https://gitlab.com/api/v4/projects/wrong-namespace%2Fproject-name"
{"message":"404 Not Found"}
```

**Python requests ライブラリでのエラー：**

```python
import requests
response = requests.get(
    "https://gitlab.com/api/v4/projects/invalid-path",
    headers={"PRIVATE-TOKEN": "<your-token>"}
)
# response.status_code == 404
# response.json() → {"message": "404 Not Found"}
```

## よくある原因と解決手順

### 原因1：プロジェクトのパスまたはIDの綴りが間違っている

GitLabのプロジェクトはnamespace/project_pathの形式でアクセスされます。URLやAPIパスに誤字があると、サーバーがそのリソースを検索できず404を返します。特に複数の類似プロジェクト名がある環境では、このミスが頻繁に発生します。

**修正前（エラーが起きるコード）：**

```bash
# プロジェクトパスの綴りが間違っている
curl -H "PRIVATE-TOKEN: <your-token>" \
  "https://gitlab.com/api/v4/projects/my-team%2Fmy-projct"
  # ↑ "my-projct" は存在しない（正しくは "my-project"）
```

**修正後：**

```bash
# GitLab WebUIで確認したパスと完全に一致させる
curl -H "PRIVATE-TOKEN: <your-token>" \
  "https://gitlab.com/api/v4/projects/my-team%2Fmy-project"
  # URLエンコード: "/" → "%2F"
```

### 原因2：プライベートプロジェクトに権限のないトークンでアクセスしている

プライベートプロジェクトへのAPIアクセスには、`api`スコープ（APIアクセス権限）を持つPersonal Access Tokenが必要です。スコープがない、または期限切れのトークンを使用した場合、権限がないとみなされ404が返されます。

**修正前（エラーが起きるコード）：**

```python
import requests

# トークンに api スコープがない（read_user のみなど）
token = "<your-token-without-api-scope>"
response = requests.get(
    "https://gitlab.com/api/v4/projects/private-namespace%2Fprivate-project",
    headers={"PRIVATE-TOKEN": token}
)
# → 404 Not Found (権限不足が原因)
```

**修正後：**

```python
import requests

# api スコープを含むトークンを使用
token = "<your-token-with-api-scope>"
response = requests.get(
    "https://gitlab.com/api/v4/projects/private-namespace%2Fprivate-project",
    headers={"PRIVATE-TOKEN": token}
)
# → 200 OK
print(response.json())
```

### 原因3：ブランチ名またはコミットSHAが間違っている

ファイル取得やコミット情報の参照時に、存在しないブランチ名やコミットハッシュを指定すると404になります。特にブランチ名の大文字小文字の区別やコミットSHAの一部指定時に注意が必要です。

**修正前（エラーが起きるコード）：**

```bash
# ブランチ名が間違っている（大文字小文字の不一致）
curl -H "PRIVATE-TOKEN: <your-token>" \
  "https://gitlab.com/api/v4/projects/my-team%2Fmy-project/repository/files/README.md?ref=Main"
  # ↑ ブランチ名は "main" だが "Main" と指定

# またはコミットSHAが不完全な形式
curl -H "PRIVATE-TOKEN: <your-token>" \
  "https://gitlab.com/api/v4/projects/my-team%2Fmy-project/repository/commits/abc123"
  # ↑ 実際のコミットSHAが "abc123def456..." なのに一部のみ指定
```

**修正後：**

```bash
# ブランチ名を正確に指定（GitLab WebUIで確認）
curl -H "PRIVATE-TOKEN: <your-token>" \
  "https://gitlab.com/api/v4/projects/my-team%2Fmy-project/repository/files/README.md?ref=main"

# コミットSHAの完全形式を使用するか、タグを利用
curl -H "PRIVATE-TOKEN: <your-token>" \
  "https://gitlab.com/api/v4/projects/my-team%2Fmy-project/repository/commits/abc123def456789"
  # またはブランチ名やタグで参照
  # ?ref=feature/my-feature
```

## ツール固有の注意点

GitLabでは、プロジェクトIDとパスの両方でリソースにアクセスできます。プロジェクトIDは数値で不変ですが、パス名は変更される可能性があります。プロジェクトが移動またはリネームされた場合、古いパスでのアクセスは404になります。

**例：プロジェクトIDでアクセスする方法**

```bash
# パスの代わりにプロジェクトIDで参照（より確実）
# プロジェクトIDは GitLab WebUI > プロジェクト設定から確認可能
curl -H "PRIVATE-TOKEN: <your-token>" \
  "https://gitlab.com/api/v4/projects/12345/repository/files/README.md"
  # 12345 がプロジェクトID
```

セルフホストGitLabの場合、URLが異なります（例：`https://gitlab.your-company.com`）。API仕様はGitLab.comと同じですが、URLの誤入力がないか確認してください。

マージリクエスト番号やissue番号を参照する際も、プロジェクトパスが正確でない限り404になります。特にCI/CDパイプラインスクリプト内で動的にURLを構築する場合は、変数展開時の誤りに注意してください。

```bash
# GitLab CI 内での例：PROJECT_PATH と MR_IID を利用
curl -H "PRIVATE-TOKEN: $CI_JOB_TOKEN" \
  "https://gitlab.com/api/v4/projects/$CI_PROJECT_ID/merge_requests/$CI_MERGE_REQUEST_IID"
```

## それでも解決しない場合

まずGitLab WebUIで同じURLにアクセスして、そのリソースが実際に存在するかを確認してください。WebUIでアクセス可能であればAPI呼び出しのパスやスコープ、トークンの期限を確認します。

**デバッグ用コマンド：**

```bash
# トークンの情報を確認（スコープ、期限）
curl -H "PRIVATE-TOKEN: <your-token>" \
  "https://gitlab.com/api/v4/user"

# プロジェクト情報を取得（パスとIDを確認）
curl -H "PRIVATE-TOKEN: <your-token>" \
  "https://gitlab.com/api/v4/projects?search=my-project"

# ブランチ一覧を確認
curl -H "PRIVATE-TOKEN: <your-token>" \
  "https://gitlab.com/api/v4/projects/<project-id>/repository/branches"
```

`gitlab.com`の代わりにセルフホストGitLabを使用している場合は、管理者ログで該当リクエストのログを確認することができます（`/var/log/gitlab/nginx/access.log`など、インストール方法に応じて異なります）。

最新のGitLab APIドキュメントは公式サイト（https://docs.gitlab.com/ee/api/）を参照してください。バージョンによってエンドポイントやレスポンス形式が異なることがあります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*