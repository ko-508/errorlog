---
draft: true
title: "OpenAI API の 404 エラー：原因と解決策"
date: 2026-05-24
description: "OpenAI APIで404エラーが発生する場合、リクエストで指定されたリソース（モデル、アシスタント、ファイルなど）がサーバー上に存在しないことを示しています。"
tags: ["OpenAI API"]
errorCode: "404"
lastmod: 2026-05-31
service: "OpenAI API"
error_type: "404"
components: []
related_services: ["ChatCompletion", "Assistants API", "Models"]
---

## エラーの概要

OpenAI [API](/glossary/api/)で404[エラー](/glossary/エラー/)が発生する場合、[リクエスト](/glossary/リクエスト/)で指定されたリソース（[モデル](/glossary/モデル/)、アシスタント、ファイルなど）が[サーバー](/glossary/サーバー/)上に存在しないことを示しています。この[エラー](/glossary/エラー/)は、存在しない[モデル](/glossary/モデル/)名の指定、削除済みのアシスタント[ID](/glossary/id/)の使用、間違った[エンドポイント](/glossary/エンドポイント/)へのアクセスなど、様々な原因で発生します。OpenAI [API](/glossary/api/)の仕様変更に伴い、廃止された[モデル](/glossary/モデル/)の使用も404の一般的な原因です。

## 実際のエラーメッセージ例

```json
{
  "error": {
    "message": "The model 'gpt-3.5-turbo-0301' does not exist. You can view a list of available models at https://platform.openai.com/docs/models.",
    "type": "invalid_request_error",
    "param": "model",
    "code": "model_not_found"
  }
}
```

```json
{
  "error": {
    "message": "Could not locate assistant with id 'asst_xxxxxxxxxxxxx'",
    "type": "invalid_request_error",
    "param": "assistant_id",
    "code": "assistant_not_found"
  }
}
```

## よくある原因と解決手順

### 原因1：廃止または存在しないモデル名の指定

OpenAIは定期的に[モデル](/glossary/モデル/)を更新し、古いスナップショット版（例：`gpt-3.5-turbo-0301`）を廃止しています。廃止された[モデル](/glossary/モデル/)名を指定すると404[エラー](/glossary/エラー/)が返されます。

**Before：**
```python
import openai

response = openai.ChatCompletion.create(
    model="gpt-3.5-turbo-0301",
    messages=[
        {"role": "user", "content": "Hello"}
    ]
)
```

**After：**
```python
import openai
from openai import OpenAI

client = OpenAI()

response = client.chat.completions.create(
    model="gpt-4-turbo",
    messages=[
        {"role": "user", "content": "Hello"}
    ]
)
```

現在のOpenAI [API](/glossary/api/)では、`gpt-4-turbo`、`gpt-4o`、`gpt-4o-mini` など、明確に指定された[モデル](/glossary/モデル/)名を使用してください。利用可能な[モデル](/glossary/モデル/)の一覧は[OpenAI Models ページ](https://platform.openai.com/docs/models)で確認できます。

### 原因2：不正なアシスタントID、スレッドID、またはファイルID

Assistants [API](/glossary/api/)を使用している場合、削除済みのアシスタントやスレッド、ファイルの[ID](/glossary/id/)を参照すると404が発生します。

**Before：**
```python
client = OpenAI()

# 削除されたアシスタントIDを使用
response = client.beta.threads.create(
    assistant_id="asst_oldidthatnoexists"
)
```

**After：**
```python
client = OpenAI()

# 有効なアシスタントIDを確認して使用
assistants = client.beta.assistants.list()
valid_assistant_id = assistants.data[0].id

response = client.beta.threads.create(
    assistant_id=valid_assistant_id
)
```

アシスタントやスレッドを削除した場合、保存された[ID](/glossary/id/)は無効になります。必ず有効な[ID](/glossary/id/)を確認してから使用してください。

### 原因3：誤ったエンドポイントまたはパスの指定

[API](/glossary/api/)キーは正しくても、存在しない[エンドポイント](/glossary/エンドポイント/)に[リクエスト](/glossary/リクエスト/)を送信すると404が返されます。特にカスタム実装やcurl[コマンド](/glossary/コマンド/)で[エンドポイント](/glossary/エンドポイント/)を直接指定する場合に発生しやすいです。

**Before：**
```bash
curl https://api.openai.com/v1/chat/complete \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

**After：**
```bash
curl https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

[エンドポイント](/glossary/エンドポイント/)のパスを正確に確認してください。例えば `/chat/complete` ではなく `/chat/completions` です。

## OpenAI API固有の注意点

OpenAI [API](/glossary/api/)では複数の[API](/glossary/api/)[バージョン](/glossary/バージョン/)と多様なリソースタイプが存在するため、404[エラー](/glossary/エラー/)の原因も多岐にわたります。

**Chat Completions [API](/glossary/api/)：** 最新の[モデル](/glossary/モデル/)名は定期的に更新されます。`gpt-3.5-turbo` は常に最新のスナップショット版を指します。特定の[バージョン](/glossary/バージョン/)が必要な場合は、公式ドキュメントで現在のスナップショット版番号を確認してください。

**Assistants [API](/glossary/api/)：** `v=20240415` などのベータバージョンを指定する場合、古い[バージョン](/glossary/バージョン/)ではリソースが存在しない可能性があります。RequestHeaderで正しい[バージョン](/glossary/バージョン/)を指定してください。

**Organization [ID](/glossary/id/)：** 複数のOrganizationに属している場合、`OpenAI(organization="<your-org-id>")` でOrganizationを明示的に指定しないと、アシスタントやファイルが見つからないことがあります。

```python
client = OpenAI(
    api_key="<your-api-key>",
    organization="<your-org-id>"
)
```

**ファイルとベクトルストア：** Files [API](/glossary/api/)でアップロードしたファイル[ID](/glossary/id/)は、期限切れや削除で無効になります。必ず最新のファイル[ID](/glossary/id/)を確認してから使用してください。

## それでも解決しない場合

**利用可能なリソースを確認する：**
使用しているリソースが実際に存在するか確認してください。

```python
# 利用可能なモデル一覧
models = client.models.list()
for model in models.data:
    print(model.id)

# 作成済みアシスタント一覧
assistants = client.beta.assistants.list()
for assistant in assistants.data:
    print(f"{assistant.id}: {assistant.name}")
```

**[API](/glossary/api/)[バージョン](/glossary/バージョン/)とライブラリバージョンを確認する：**
`openai` パッケージを最新版に更新してください。`pip install --upgrade openai` を実行し、ライブラリが最新であることを確認します。

**公式ドキュメントを参照する：**
[OpenAI API Reference](https://platform.openai.com/docs/api-reference) で、使用している[エンドポイント](/glossary/エンドポイント/)、[パラメータ](/glossary/パラメータ/)、現在の[モデル](/glossary/モデル/)一覧を確認してください。

**OpenAI Community Forumで報告する：**
他に原因が考えられない場合は、詳細な[エラーメッセージ](/glossary/エラーメッセージ/)、使用しているコード、[API](/glossary/api/)キーの権限設定（Billing settings）を確認した上で、[OpenAI Community Discussions](https://community.openai.com/) で質問してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*