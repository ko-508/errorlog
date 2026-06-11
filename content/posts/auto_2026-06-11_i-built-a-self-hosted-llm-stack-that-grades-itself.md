---
title: "LiteLLMにおけるHTTP 403エラー：アクセス制御と監査ログの落とし穴を解決する"
date: 2026-06-11
lastmod: 2026-06-11
draft: false
description: "LiteLLMでカスタム認証を実装する際に遭遇しやすいHTTP 403エラーの原因と、それに伴う監査ログの問題を詳細に解説します。ユーザーごとのモデルアクセス制御と、正確な監査記録の残し方を具体的なコード例と共に紹介します。"
tags: ["Dev.to - DevOps"]
---

## エラーの概要

HTTP 403 Forbiddenエラーは、クライアントがリソースへのアクセスを試みたものの、サーバーがそのアクセスを拒否したことを示します。LiteLLMのようなLLMゲートウェイでは、主にユーザー認証や認可の失敗、つまり特定のユーザーがアクセス権限を持たないモデルや機能を利用しようとした場合に発生します。

## 実際のエラーメッセージ例

LiteLLMのカスタム認証パスでアクセスが拒否された場合、以下のようなJSONレスポンスが返されることがあります。

```json
{
  "error": {
    "message": "model_access_denied",
    "type": "access_denied",
    "code": 403
  }
}
```

また、内部ログには以下のようなメッセージが出力される可能性があります。

```
[ERROR] 2023-10-27 10:30:00,123 - litellm.custom_auth - Access denied for key <your-api-key-id> to model <requested-model-name>
```

## よくある原因と解決手順

### 原因1：カスタム認証フックでのアクセスチェックの欠落

LiteLLMには `can_key_call_model` のようなアクセスチェック機能が組み込まれていますが、カスタム認証パスを使用する場合、この機能が自動的に呼び出されないことがあります。結果として、認証されたキーがすべてのモデルにアクセスできてしまい、意図しないモデルへの呼び出しが発生した際に403エラーが適切に返されません。

**Before（エラーが起きるコード）：**

```python
# custom_auth.py (LiteLLMのカスタム認証フックの例)
from litellm import ModelResponse, completion

def custom_auth(key: str, **kwargs):
    # キーの存在チェックのみを行い、モデルアクセス権限のチェックを省略
    if key == "valid-key-alice":
        return {"user_id": "alice", "model_allow_list": ["qwen3-32b"]}
    elif key == "valid-key-bob":
        return {"user_id": "bob", "model_allow_list": ["gemma4-31b"]}
    else:
        raise Exception("Invalid Key")

# このカスタム認証では、リクエストされたモデルがallow_listに含まれているかチェックされない
# 例: aliceがgemma4-31bをリクエストしても、認証は通ってしまう
```

**After（修正後）：**

```python
# custom_auth.py (LiteLLMのカスタム認証フックの例)
from litellm import ModelResponse, completion
from litellm.exceptions import AccessDeniedError
import json

def custom_auth(key: str, **kwargs):
    request_model = None
    if "request_body" in kwargs and kwargs["request_body"]:
        try:
            request_body = json.loads(kwargs["request_body"])
            request_model = request_body.get("model")
        except json.JSONDecodeError:
            pass # リクエストボディがJSONでない場合はスキップ

    if key == "valid-key-alice":
        user_id = "alice"
        model_allow_list = ["qwen3-32b"]
    elif key == "valid-key-bob":
        user_id = "bob"
        model_allow_list = ["gemma4-31b"]
    else:
        raise AccessDeniedError("Invalid Key")

    if request_model and request_model not in model_allow_list:
        # 認証フック内で明示的にモデルアクセスをチェックし、403を発生させる
        raise AccessDeniedError(f"model_access_denied: User {user_id} is not allowed to access {request_model}")

    return {"user_id": user_id, "model_allow_list": model_allow_list}
```
**説明:** カスタム認証フック内で、リクエストボディから要求されたモデル名を抽出し、認証されたキーの `model_allow_list` と照合します。アクセスが許可されていない場合は、`AccessDeniedError` を発生させて403エラーを返します。これにより、意図しないモデルへのアクセスを確実にブロックできます。

### 原因2：アクセス拒否時の監査ログにユーザー情報が記録されない

アクセス拒否が発生した場合、LiteLLMのデフォルトの監査ログでは `user_id='unknown'` と記録されることがあります。これは、カスタム認証フックが例外を発生させた後に監査コールバックが呼び出されるため、その時点でリクエストのメタデータ（ユーザーIDなど）が失われていることが原因です。セキュリティ監査において、誰が不正なアクセスを試みたかを特定できないのは重大な問題です。

**Before（エラーが起きるコード）：**

```python
# custom_auth.py (原因1のBeforeコードと同じく、認証フックで例外を発生させるだけ)
from litellm.exceptions import AccessDeniedError

def custom_auth(key: str, **kwargs):
    # ... (認証ロジック) ...
    if not is_allowed: # アクセス拒否の条件
        raise AccessDeniedError("model_access_denied") # 例外発生後、監査ログはuser_id='unknown'となる
    return {"user_id": "known_user", "model_allow_list": ["allowed_model"]}

# audit_callback.py (LiteLLMの監査コールバックの例)
def audit_callback(kwargs, response_obj, start_time, end_time):
    # kwargs['user_id']が空または'unknown'になる可能性がある
    user_id = kwargs.get("user_id", "unknown")
    print(f"Audit Log: User {user_id} attempted access. Status: Denied.")
```

**After（修正後）：**

```python
# custom_auth.py (LiteLLMのカスタム認証フックの例)
from litellm.exceptions import AccessDeniedError
import json
import logging

logger = logging.getLogger(__name__)

def custom_auth(key: str, **kwargs):
    request_model = None
    if "request_body" in kwargs and kwargs["request_body"]:
        try:
            request_body = json.loads(kwargs["request_body"])
            request_model = request_body.get("model")
        except json.JSONDecodeError:
            pass

    user_id = None
    model_allow_list = []

    if key == "valid-key-alice":
        user_id = "alice"
        model_allow_list = ["qwen3-32b"]
    elif key == "valid-key-bob":
        user_id = "bob"
        model_allow_list = ["gemma4-31b"]
    else:
        # 未知のキーの場合、ログは「unknown」として記録される
        logger.warning(f"Audit: Unidentifiable caller attempted access with key: {key}")
        raise AccessDeniedError("Invalid Key")

    if request_model and request_model not in model_allow_list:
        # アクセス拒否時に、例外を発生させる前に監査ログを記録
        logger.warning(f"Audit: User {user_id} (key: {key}) attempted to access unauthorized model: {request_model}. Denied.")
        # 例外にカスタム属性を追加し、ダウンストリームのコールバックが重複ログを避けるようにする
        exc = AccessDeniedError(f"model_access_denied: User {user_id} is not allowed to access {request_model}")
        setattr(exc, "logged_by_custom_auth", True) # カスタムフラグ
        raise exc

    return {"user_id": user_id, "model_allow_list": model_allow_list}

# audit_callback.py (LiteLLMの監査コールバックの例)
def audit_callback(kwargs, response_obj, start_time, end_time):
    # 例外がカスタム認証で既にログ記録されているかチェック
    if "exception" in kwargs and getattr(kwargs["exception"], "logged_by_custom_auth", False):
        return # 既にログ記録済みなのでスキップ

    user_id = kwargs.get("user_id", "unknown")
    model = kwargs.get("model", "unknown")
    status = "Success" if response_obj else "Failed"
    error_message = kwargs.get("exception", "")

    print(f"Audit Log: User {user_id} requested {model}. Status: {status}. Error: {error_message}")
```
**説明:** `custom_auth` フック内でアクセス拒否を判断した時点で、`user_id` や `key` などの情報が利用可能なうちにログを記録します。その後、`AccessDeniedError` を発生させますが、この例外オブジェクトにカスタム属性（例: `logged_by_custom_auth=True`）を追加します。LiteLLMの監査コールバックでは、このカスタム属性をチェックし、既にログ記録済みのイベントであれば重複して記録しないようにします。これにより、誰が何を試みたのかを正確に追跡できる監査ログが実現します。

### 原因3：GPUメモリ不足によるモデルの同時ロード失敗

LLMゲートウェイで複数の大規模言語モデル（LLM）を運用する場合、特に評価プロセスなどで複数のモデルを同時にロードしようとすると、GPUメモリが不足し、モデルのロードに失敗したり、パフォーマンスが著しく低下したりすることがあります。これは、各モデルが大量のVRAMを消費するため、単一のGPUでは収まりきらない場合に発生します。

**Before（エラーが起きるコード）：**

```python
# 評価スクリプトの擬似コード
def run_evaluation_naive(generator_model, judge_model, questions):
    results = []
    for q in questions:
        # 質問ごとに生成モデルと評価モデルを交互にロード・アンロード
        # または、両方を同時にロードしようとする
        generator_output = generator_model.generate(q) # GPUにgenerator_modelをロード
        score = judge_model.score(generator_output, q) # GPUにjudge_modelをロード (generator_modelと競合)
        results.append(score)
    return results
```

**After（修正後）：**

```python
# 評価スクリプトの擬似コード
import torch

def run_evaluation_optimized(generator_model_instance, judge_model_instance, questions):
    # 1. 全ての質問に対する回答を生成
    generated_answers = []
    print("Loading generator model...")
    # generator_model_instanceをロード (例: Ollama/vLLMのAPIを叩く)
    # keep_alive=0 を設定して、使用後にモデルがアンロードされるようにする
    for q in questions:
        response = generator_model_instance.generate(q, keep_alive=0)
        generated_answers.append(response)
    
    # generator_model_instanceがGPUメモリから解放されることを確認
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    print("Generator model finished and unloaded.")

    # 2. 生成された回答を評価
    scores = []
    print("Loading judge model...")
    # judge_model_instanceをロード
    for i, answer in enumerate(generated_answers):
        score = judge_model_instance.score(answer, questions[i], keep_alive=0)
        scores.append(score)
    
    # judge_model_instanceがGPUメモリから解放されることを確認
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    print("Judge model finished and unloaded.")

    return scores
```
**説明:** 評価プロセスを2つのパスに分割します。まず、すべての質問に対して生成モデルで回答を生成し、そのモデルをGPUメモリからアンロードします（`keep_alive=0`設定など）。次に、評価モデルをロードし、生成されたすべての回答を評価します。これにより、GPUメモリに同時にロードされるモデルは常に1つだけになり、メモリ不足によるエラーやパフォーマンス低下を防ぎます。

## ツール固有の注意点

LiteLLMは、複数のLLMプロバイダーを統合する強力なゲートウェイですが、カスタム認証や監査ログの機能は、その柔軟性ゆえに実装の詳細に注意が必要です。特に、`litellm.exceptions.AccessDeniedError` を適切に利用し、例外発生時のコンテキスト情報を失わないようにすることが重要です。また、OllamaやvLLMのようなオンプレミスLLMランタイムと組み合わせる場合、GPUリソースの管理はLiteLLMの範疇外となるため、モデルのロード・アンロード戦略はアプリケーション側で慎重に設計する必要があります。`keep_alive=0` のような設定は、モデルがアイドル状態になったときにGPUメモリを解放するのに役立ちます。

## それでも解決しない場合

1.  **LiteLLMのログレベルを上げる:**
    LiteLLMのデバッグログを有効にすることで、内部の動作やエラーの詳細を確認できます。
    ```python
    import litellm
    litellm.set_verbose(True)
    ```
2.  **カスタム認証フックのデバッグ:**
    カスタム認証フック内で `print` 文やロガーを多用し、どのパスが実行され、どの変数がどのような値を持っているかを確認します。特に、`kwargs` の内容を詳細に調査してください。
3.  **LiteLLMの公式ドキュメントを参照:**
    LiteLLMのカスタム認証、コールバック、エラーハンドリングに関する最新の公式ドキュメントを確認し、実装が最新のベストプラクティスに沿っているかを確認します。
    *   [LiteLLM Custom Auth](https://docs.litellm.ai/docs/proxy/custom_auth)
    *   [LiteLLM Callbacks](https://docs.litellm.ai/docs/completion/callbacks)
4.  **GPUメモリ使用量の監視:**
    `nvidia-smi` コマンドや `torch.cuda.memory_allocated()` などのツールを使用して、LLMのロード前後のGPUメモリ使用量を監視し、メモリ不足が本当に問題の原因であるかを確認します。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*