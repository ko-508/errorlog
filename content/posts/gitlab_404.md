---
title: "GitLab の 404 エラー：原因と解決策"
date: 2026-06-13
description: "指定したリポジトリ・MR・リソースが見つからない"
tags: ["GitLab"]
errorCode: "404"
service: "GitLab"
error_type: "404"
components: []
related_services: ["curl", "Python requests"]
lastmod: 2026-06-14
top_queries:
- 'gitlab 404'
---

## エラーの概要

GitLabの404[エラー](/glossary/エラー/)は、指定したプロジェクト・マージリクエスト・ファイルなどのリソースが見つからないことを意味します。[API](/glossary/api/)呼び出しやWebUIでのアクセス時に発生し、プロジェクトの存在確認、[アクセス権限](/glossary/アクセス権限/)、リソースパスの誤入力などが主な原因です。プロジェクトが削除された、[URL](/glossary/url/)エンコーディングが正しくない、[トークン](/glossary/トークン/)の[権限](/glossary/権限/)が不足している場合にも表示されます。

## 実際のエラーメッセージ例

**GitLab [API](/glossary/api/)経由での[レスポンス](/glossary/レスポンス/)：**

```json
{
  "message": "404 Not Found"
}
```

**curl[コマンド](/glossary/コマンド/)での出力：**

```bash
$ curl -H "PRIVATE-TOKEN: <your-token>" "https://gitlab.com/api/v4/projects/wrong-namespace%2Fproject-name"
{"message":"404 Not Found"}
```

**WebUIでのブラウザ表示：**

```
404 Not Found

The page you're looking for could not be found.
```

**Python requests ライブラリでの[エラー](/glossary/エラー/)：**

```python
import requests
response = requests.get(
    "https://gitlab.com/api/v4/projects/invalid-path",
    headers={"PRIVATE-TOKEN": "<your-token>"}
)
print(response.status_code)  # 404
```

## よくある原因と解決手順

### 原因1：プロジェクトIDまたはパスの誤入力

GitLab [API](/glossary/api/)のプロジェクト指定時に、数字のプロジェクト[ID](/glossary/id/)、または[URL](/glossary/url/)形式の `namespace/project-name` を使用します。[パス](/glossary/パス/)に特殊文字やスペースが含まれる場合は、[URL](/glossary/url/)エンコーディングが必須です。スラッシュ（`/`）は `%2F` にエンコードする必要があります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# スラッシュがエンコードされていない
curl -H "PRIVATE-TOKEN: <your-token>" \
  "https://gitlab.com/api/v4/projects/my-group/my-project/repository/commits"

# 結果：404 Not Found
```

**After（修正後）：**

```bash
# スラッシュをURLエンコードする（%2F）
curl -H "PRIVATE-TOKEN: <your-token>" \
  "https://gitlab.com/api/v4/projects/my-group%2Fmy-project/repository/commits"

# または数字のプロジェクトIDを使用
curl -H "PRIVATE-TOKEN: <your-token>" \
  "https://gitlab.com/api/v4/projects/12345/repository/commits"
```

### 原因2：トークンの権限不足またはプロジェクトへのアクセス権限がない

プライベートプロジェクトへのアクセスには、適切な[権限](/glossary/権限/)を持つ[トークン](/glossary/トークン/)が必要です。[トークン](/glossary/トークン/)が存在しない、有効期限が切れている、または該当プロジェクトへの[アクセス権限](/glossary/アクセス権限/)がないメンバーが使用している場合、404が返されます。GitLabは[セキュリティ](/glossary/セキュリティ/)の観点から、[権限](/glossary/権限/)がないリソースを404で返すため、403（Forbidden）と区別されません。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
import requests

# 有効期限切れのトークンを使用
headers = {"PRIVATE-TOKEN": "glpat-xxxxxxxxxxxx"}
response = requests.get(
    "https://gitlab.example.com/api/v4/projects/sensitive-project",
    headers=headers
)
# 404 Not Found が返される
print(response.status_code)
```

**After（修正後）：**

```python
import requests
import os

# 環境変数から有効なトークンを取得
token = os.environ.get("GITLAB_TOKEN")
if not token:
    raise ValueError("GITLAB_TOKEN is not set")

headers = {"PRIVATE-TOKEN": token}
response = requests.get(
    "https://gitlab.example.com/api/v4/projects/sensitive-project",
    headers=headers
)

if response.status_code == 404:
    print("プロジェクトが見つからないか、アクセス権限がありません")
elif response.status_code == 200:
    print("成功")
```

### 原因3：プロジェクトが削除された、または名前空間が変更された

プロジェクトが削除された場合、その[URL](/glossary/url/)にアクセスすると404が返されます。また、グループやユーザーの名前空間が変更された場合、古い[パス](/glossary/パス/)でのアクセスも404になります。プロジェクトが転送（移動）された場合、古い[URL](/glossary/url/)から新しい[URL](/glossary/url/)へのリダイレクトが設定されていないと404が表示されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# 旧いプロジェクトパスでアクセス（名前空間が変更済み）
curl -H "PRIVATE-TOKEN: <your-token>" \
  "https://gitlab.com/api/v4/projects/old-team%2Fproject-name"

# 404 Not Found
```

**After（修正後）：**

```bash
# 新しいプロジェクトパスでアクセス
curl -H "PRIVATE-TOKEN: <your-token>" \
  "https://gitlab.com/api/v4/projects/new-team%2Fproject-name"

# または、プロジェクトの詳細情報を確認して実際のパスを確認
curl -H "PRIVATE-TOKEN: <your-token>" \
  "https://gitlab.com/api/v4/projects" | jq '.[] | select(.name=="project-name")'
```

### 原因4：マージリクエストやイシューのIDが存在しない

プロジェクト内の特定マージリクエスト、イシュー、パイプラインなどの[ID](/glossary/id/)が存在しない場合、404が返されます。プロジェクト[ID](/glossary/id/)は正しいがリソース[ID](/glossary/id/)が誤っている、または削除されている状況です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# マージリクエストID 999 が存在しない
curl -H "PRIVATE-TOKEN: <your-token>" \
  "https://gitlab.com/api/v4/projects/12345/merge_requests/999"

# 404 Not Found
```

**After（修正後）：**

```bash
# プロジェクト内のすべてのマージリクエストをリストして確認
curl -H "PRIVATE-TOKEN: <your-token>" \
  "https://gitlab.com/api/v4/projects/12345/merge_requests" | jq '.[] | {id, title}'

# 正しいIDでアクセス
curl -H "PRIVATE-TOKEN: <your-token>" \
  "https://gitlab.com/api/v4/projects/12345/merge_requests/42"
```

### 原因5：ファイルパスが間違っている、またはブランチが削除されている

[リポジトリ](/glossary/リポジトリ/)内のファイルにアクセスする際、ファイルパスや[ブランチ](/glossary/ブランチ/)名が誤っている場合に404が返されます。特定[ブランチ](/glossary/ブランチ/)が削除されている、ファイルが移動された、[パス](/glossary/パス/)の大文字小文字が一致していない場合も対象です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# 削除済みブランチ "feature-old" からファイルを取得
curl -H "PRIVATE-TOKEN: <your-token>" \
  "https://gitlab.com/api/v4/projects/12345/repository/files/src%2Fmain.py?ref=feature-old"

# 404 Not Found
```

**After（修正後）：**

```bash
# 存在するブランチを確認
curl -H "PRIVATE-TOKEN: <your-token>" \
  "https://gitlab.com/api/v4/projects/12345/repository/branches" | jq '.[] | .name'

# 正しいブランチでアクセス
curl -H "PRIVATE-TOKEN: <your-token>" \
  "https://gitlab.com/api/v4/projects/12345/repository/files/src%2Fmain.py?ref=main"
```

## ツール固有の注意点

**GitLab [API](/glossary/api/)固有の問題：**

GitLab [API](/glossary/api/)ではリソース所有者の[権限](/glossary/権限/)がない場合、[セキュリティ](/glossary/セキュリティ/)上の理由から404を返します。つまり、403（Forbidden）ではなく404が表示されるため、「リソースがない」のか「[権限](/glossary/権限/)がない」のか区別が難しくなります。WebUIで同じプロジェクトにアクセスできるか確認することが有効です。

**グループ・サブグループ間での[パス](/glossary/パス/)変更：**

グループやサブグループの構造が変わった場合、[API](/glossary/api/)呼び出しの[パス](/glossary/パス/)も対応する必要があります。`/groups/<id>` と `/groups/<path>` の両形式がサポートされていますが、パスベースでアクセスする場合は完全な階層[パス](/glossary/パス/)が必須です。

**Self-hosted GitLab での[URL](/glossary/url/)確認：**

オンプレミスGitLab環境では、WebUIで確認した[URL](/glossary/url/)と[API](/glossary/api/) [エンドポイント](/glossary/エンドポイント/)のベース[URL](/glossary/url/)が一致しているか確認します。リバースプロキシや[ロードバランサー](/glossary/ロードバランサー/)経由でアクセスしている場合、`gitlab.yml` の `external_url` 設定が正確か検証が必要です。

**Legacy [API](/glossary/api/) vs [GraphQL](/glossary/graphql/)：**

GitLab [REST](/glossary/rest/) [API](/glossary/api/)と[GraphQL](/glossary/graphql/) [API](/glossary/api/)では、リソースの指定方法が異なります。特にマージリクエストやパイプラインではプロジェクト[ID](/glossary/id/)が必須の場合があり、プロジェクトパスだけでは404になることがあります。

## それでも解決しない場合

**確認すべき[ログ](/glossary/ログ/)の場所：**

GitLab[管理者権限](/glossary/管理者権限/)がある場合は、管理画面の「[ログ](/glossary/ログ/)」セクションで詳細なアクセスログを確認します。また、自身のGitLab[インスタンス](/glossary/インスタンス/)へのアクセス履歴は、WebUI右上のプロフィール > 「Last activity」で時系列確認できます。

**デバッグコマンド：**

```bash
# トークンの権限を確認
curl -H "PRIVATE-TOKEN: <your-token>" \
  "https://gitlab.example.com/api/v4/user"

# プロジェクト一覧を取得（アクセス可能なもの）
curl -H "PRIVATE-TOKEN: <your-token>" \
  "https://gitlab.example.com/api/v4/projects?pagination=keyset&per_page=100"

# 特定プロジェクトの詳細情報を確認
curl -H "PRIVATE-TOKEN: <your-token>" \
  "https://gitlab.example.com/api/v4/projects/<project-id>"
```

**公式ドキュメント参照：**

- GitLab [API](/glossary/api/) ドキュメント：`https://docs.gitlab.com/ee/api/`
- プロジェクト[API](/glossary/api/)：`https://docs.gitlab.com/ee/api/projects.html`
- [トークン](/glossary/トークン/)管理：`https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html`

**コミュニティリソース：**

GitLab公式フォーラム（`https://forum.gitlab.com`）やGitHub Issues（GitLab Runnerなどのオープンソースコンポーネントの場合）でも同様の問題が報告されていないか検索してみてください。特に「404」「Not Found」「[API](/glossary/api/)」を組み合わせたキーワード検索が有効です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*