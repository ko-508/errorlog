---
title: "OpenAI API の 422 エラー：原因と解決策"
date: 2026-05-28
description: "リクエストの形式は正しいが、含まれているデータの内容が処理できない。。Fine-tuning用のJSONLファイルの形式や内容がOなど、OpenAI API 422 エラーの原因と解決策を解説。"
tags: ["OpenAI API"]
errorCode: "422"
---

OpenAI APIで422エラーが発生するのは、リクエストの構文は正しいものの、含まれるデータが処理要件を満たしていないときです。特にFine-tuningでよく出現するエラーです。

## よくある原因

**Fine-tuningのJSONLファイル形式が不正**

Fine-tuningに使用するJSONLファイルの各行が、OpenAIが定める正しい形式になっていない場合、422エラーが返されます。例えば、JSON形式で統一されていなかったり、不要なフィールドが含まれていたり、必須フィールドが欠けていたりすると、OpenAI側で処理できないと判断されるためです。

**messagesフォーマットが要件と異なる**

Fine-tuningのデータセットでは、各サンプルが`messages`配列を含む必要があります。その配列内のメッセージオブジェクトが`role`と`content`フィールドを持っていなかったり、`role`の値が不正な値（例：「user_message」など）だったりすると、422エラーが返されます。OpenAIは厳密なスキーマ検証を行うため、わずかな形式のズレでも拒否されるのです。

**データセット件数が最小要件を下回っている**

Fine-tuningには最低限のサンプル数（通常は10件以上、推奨は50件以上）が必要です。これを満たさないデータセットをアップロードしようとすると、422エラーで拒否されます。

**JSONLファイルに無効なJSON行が含まれている**

各行が有効なJSON形式になっていない場合、422エラーが返されます。例えば、シングルクォートの使用、末尾のカンマ、エスケープ漏れなども原因になります。

## 解決手順

**1. JSONLファイルの形式を確認する**

Fine-tuningデータは、1行1個の有効なJSONオブジェクトからなるJSONL形式である必要があります。以下が正しいサンプルです。

```jsonl
{"messages": [{"role": "system", "content": "あなたは優秀なアシスタントです。"}, {"role": "user", "content": "こんにちは"}, {"role": "assistant", "content": "こんにちは。何かお手伝いできることはありますか？"}]}
{"messages": [{"role": "system", "content": "あなたは優秀なアシスタントです。"}, {"role": "user", "content": "天気は？"}, {"role": "assistant", "content": "申し訳ございませんが、リアルタイムの天気情報は提供できません。"}]}
```

ファイルの各行が独立した有効なJSONであることをテキストエディタで目視確認します。

**2. Pythonでファイルの検証を行う**

以下のスクリプトで、JSONL形式とmessagesの構造を自動検証します。

```python
import json

def validate_jsonl(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, start=1):
            try:
                data = json.loads(line)
                # messagesフィールドが存在するか確認
                if 'messages' not in data:
                    print(f"行 {line_num}: 'messages' フィールドが見つかりません")
                    continue
                # messagesは配列か確認
                if not isinstance(data['messages'], list):
                    print(f"行 {line_num}: 'messages' が配列ではありません")
                    continue
                # 各メッセージが role と content を持つか確認
                for msg_num, msg in enumerate(data['messages']):
                    if 'role' not in msg or 'content' not in msg:
                        print(f"行 {line_num}、メッセージ {msg_num}: 'role' または 'content' が見つかりません")
                    if msg.get('role') not in ['system', 'user', 'assistant']:
                        print(f"行 {line_num}、メッセージ {msg_num}: roleが不正です（値：{msg.get('role')}）")
            except json.JSONDecodeError as e:
                print(f"行 {line_num}: JSON形式エラー - {e}")
    print("検証完了")

validate_jsonl('<your-file-path>.jsonl')
```

**3. データセット件数を確認する**

以下のコマンドで行数（サンプル数）を確認します。

```bash
wc -l <your-file-path>.jsonl
```

10件未満の場合は、トレーニングデータを追加してから再度アップロードします。

**4. OpenAI CLIを使用してアップロードする前に検証する**

OpenAIが提供する公式の検証ツールを使う場合、以下のようにします。

```bash
openai tools fine_tunes.prepare_data -f <your-file-path>.jsonl
```

このコマンドを実行すると、形式エラーがあれば詳細に指摘されます。修正内容を確認し、再度実行します。

**5. Fine-tuningジョブをアップロードする**

検証を通過したら、OpenAI APIでFine-tuningジョブを作成します。

```python
import openai

openai.api_key = '<your-api-key>'

with open('<your-file-path>.jsonl', 'rb') as f:
    response = openai.File.create(file=f, purpose='fine-tune')
    file_id = response['id']

job = openai.FineTune.create(training_file=file_id, model='gpt-3.5-turbo')
print(job['id'])
```

## それでも解決しない場合

OpenAIの公式ドキュメント（https://platform.openai.com/docs/guides/fine-tuning）で最新のスキーマ要件を確認してください。APIアップデートにより仕様が変わっている可能性があります。また、OpenAI APIサポートフォーラムでエラーメッセージの全文を含めて質問することで、より具体的な原因を特定できます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*