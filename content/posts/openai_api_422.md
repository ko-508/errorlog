---
title: "OpenAI API の 422 エラー：原因と解決策"
date: 2026-05-28
description: "リクエストの形式は正しいが、含まれているデータの内容が処理できない"
tags: ["OpenAI API"]
errorCode: "422"
service: "OpenAI API"
error_type: "422"
components: []
related_services: ["Fine-tuning", "JSONL", "Python", "CLI"]
lastmod: 2026-06-14
---

## エラーの概要

OpenAI [API](/glossary/api/)で422[エラー](/glossary/エラー/)が発生するのは、[リクエスト](/glossary/リクエスト/)の構文は正しいものの、含まれるデータが処理要件を満たしていないときです。特にFine-tuningやチャット補完（Chat Completions）でよく出現する[エラー](/glossary/エラー/)で、OpenAIのバリデーションルールに違反しているため、[サーバー](/glossary/サーバー/)側が処理を拒否した状態を示します。

## 実際のエラーメッセージ例

**Fine-tuningファイルアップロード時の例：**

```json
{
  "error": {
    "message": "Unprocessable entity",
    "type": "invalid_request_error",
    "param": "training_file",
    "code": "invalid_request"
  }
}
```

**Chat Completions [API](/glossary/api/)の例：**

```json
{
  "error": {
    "message": "Invalid value: '/wrong-role/' is not one of 'user', 'assistant', 'system', 'function'",
    "type": "invalid_request_error",
    "param": "messages.0.role",
    "code": "invalid_enum_value"
  }
}
```

## よくある原因と解決手順

**原因1：Fine-tuningのJSONLファイル形式が不正**

Fine-tuningに使用するJSONLファイルの各行が、OpenAIが定める正しい形式になっていない場合に422[エラー](/glossary/エラー/)が返されます。各行が有効な[JSON](/glossary/json/)形式でなかったり、必須フィールド（messages、completion等）が欠けていたり、不要なフィールドが混在していたりすると、OpenAI側で処理できないと判断されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```jsonl
{"messages": [{"role": "user", "content": "Hello"}], "completion": " Hi there"}
{"messages": [{"role": "user", "content": "How are you?"}]}
{"messages": [{"role": "user", "content": "Test"}], "extra_field": "value", "completion": " Good"}
```

**After（修正後）：**

```jsonl
{"messages": [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi there"}]}
{"messages": [{"role": "user", "content": "How are you?"}, {"role": "assistant", "content": "I'm doing well"}]}
{"messages": [{"role": "user", "content": "Test"}, {"role": "assistant", "content": "Good"}]}
```

**原因2：messagesフォーマットにおけるroleの値が不正**

Fine-tuningおよびChat Completions [API](/glossary/api/)では、各メッセージオブジェクトの`role`フィールドが厳密に定義されています。「user_message」「assistant_response」などの独自の値を使用したり、大文字小文字を誤ったりすると422[エラー](/glossary/エラー/)が発生します。許可される値は`user`、`assistant`、`system`、`function`に限定されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
response = client.chat.completions.create(
  model="gpt-4",
  messages=[
    {"role": "User", "content": "こんにちは"},
    {"role": "Assistant_Response", "content": "こんにちは！"}
  ]
)
```

**After（修正後）：**

```python
response = client.chat.completions.create(
  model="gpt-4",
  messages=[
    {"role": "user", "content": "こんにちは"},
    {"role": "assistant", "content": "こんにちは！"}
  ]
)
```

**原因3：Fine-tuningのメッセージ数が要件を満たさない**

Fine-tuningでは、各トレーニング例に含まれるメッセージ数に下限があります。少なくとも1つ以上のユーザーメッセージと1つ以上のアシスタントメッセージが必要です。メッセージが空配列だったり、ユーザーまたはアシスタントのいずれかの[ロール](/glossary/ロール/)のメッセージしかない場合、422[エラー](/glossary/エラー/)が返されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
training_data = [
  {"messages": []},  # 空配列
  {"messages": [{"role": "user", "content": "Hello"}]},  # アシスタントメッセージなし
]

with open("training.jsonl", "w") as f:
  for item in training_data:
    f.write(json.dumps(item) + "\n")
```

**After（修正後）：**

```python
training_data = [
  {"messages": [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi there"}
  ]},
  {"messages": [
    {"role": "user", "content": "How are you?"},
    {"role": "assistant", "content": "I'm doing well"}
  ]},
]

with open("training.jsonl", "w") as f:
  for item in training_data:
    f.write(json.dumps(item) + "\n")
```

**原因4：contentフィールドが空文字列または存在しない**

各メッセージオブジェクトの`content`フィールドが必須です。空文字列、null、または完全に欠落している場合、422[エラー](/glossary/エラー/)が発生します。また、文字列型以外の値（[オブジェクト](/glossary/オブジェクト/)や配列）を渡すことも[エラー](/glossary/エラー/)の原因となります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```json
{"messages": [{"role": "user", "content": ""}, {"role": "assistant", "content": "response"}]}
{"messages": [{"role": "user"}, {"role": "assistant", "content": "response"}]}
{"messages": [{"role": "user", "content": null}]}
```

**After（修正後）：**

```json
{"messages": [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi"}]}
{"messages": [{"role": "user", "content": "Question"}, {"role": "assistant", "content": "Answer"}]}
{"messages": [{"role": "user", "content": "test"}]}
```

## OpenAI API固有の注意点

OpenAI [API](/glossary/api/)の422[エラー](/glossary/エラー/)は、[API](/glossary/api/)[エンドポイント](/glossary/エンドポイント/)や利用する[モデル](/glossary/モデル/)によって、[バリデーション](/glossary/バリデーション/)規則が異なります。

**Fine-tuning [API](/glossary/api/)の場合**、JSONLファイルの検証はファイルアップロード時に実施されます。`files.create()`でファイルをアップロードする際、[ファイルサイズ](/glossary/ファイルサイズ/)が大きい場合は[バリデーション](/glossary/バリデーション/)がサンプリングで実行されるため、アップロード直後に422[エラー](/glossary/エラー/)が出ず、後の`fine_tuning.jobs.create()`実行時に発見されることもあります。

**Chat Completions [API](/glossary/api/)の場合**、[モデル](/glossary/モデル/)の[バージョン](/glossary/バージョン/)によってサポートされる[ロール](/glossary/ロール/)値が異なる可能性があります。例えば、`gpt-3.5-turbo`で`system`[ロール](/glossary/ロール/)を使用する場合、特定の[API](/glossary/api/)[バージョン](/glossary/バージョン/)では非対応の場合があるため、[API](/glossary/api/)ドキュメントで対象[モデル](/glossary/モデル/)のサポート状況を確認してください。

また、関数呼び出し（Function Calling）を使用する場合、`function`[ロール](/glossary/ロール/)のメッセージに対しては`content`フィールドに加えて`tool_calls`または`function_call`フィールドの構造が厳密に定義されています。これらが不正な形式だと422[エラー](/glossary/エラー/)が発生します。

## それでも解決しない場合

**JSONLファイルの妥当性を検証する**

以下の[コマンド](/glossary/コマンド/)でJSONLファイルの各行を検証できます：

```bash
python3 << 'EOF'
import json

with open("training.jsonl", "r") as f:
  for i, line in enumerate(f, 1):
    try:
      json.loads(line)
    except json.JSONDecodeError as e:
      print(f"Line {i}: Invalid JSON - {e}")
EOF
```

**OpenAIの公式Fine-tuningドキュメント**を確認し、現在の[バージョン](/glossary/バージョン/)で要求されるJSONL形式の仕様を確認してください。特に「Preparing your dataset」セクションにサンプルファイルが記載されています。

**GitHub Issues**でOpenAI Pythonライブラリの[リポジトリ](/glossary/リポジトリ/)を検索し、同様の422[エラー](/glossary/エラー/)に関する報告がないか確認してください。既知の問題や回避策が記載されている可能性があります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*