---
title: "OpenAI API の 400 エラー：原因と解決策"
date: 2026-08-03
description: "OpenAI API の 400 は、応答の param にどのパラメータが問題かが入り、code にその種類が入ります。使えないパラメータ、使えない値、上限超過で対処が変わります。なお、モデル名の誤りは 400 ではなく 404 です。まず param と code を読むのが最短の道です。"
tags: ["OpenAI API"]
images: ["og/posts/openai_api_400.png"]
errorCode: "400"
lastmod: 2026-08-03
service: "OpenAI API"
error_type: "400"
components: ["Chat Completions", "Request Validation"]
related_services: ["Python SDK", "Azure OpenAI Service"]
trend_incident: false
top_queries:
- 'チャットgpt リクエストに問題があります 400'
---

## 冒頭まとめ

OpenAI [API](/glossary/api/) の 400 Bad Request は、送った要求の内容が受け付けられなかったことを示します。公式の説明では、要求の形式が壊れているか、必須の[パラメータ](/glossary/パラメータ/)が欠けている場合とされ、**[エラー](/glossary/エラー/)文言がどこが問題かを教えてくれるはず**だと書かれています。

実際、応答には機械が読める形で場所と種類が入ります。`param` に**問題のある[パラメータ](/glossary/パラメータ/)の名前**、`code` に**種類の識別子**です。この2つを読めば、直す場所と直し方がほぼ決まります。

よく見る `code` は3つです。`unsupported_parameter` は、その[パラメータ](/glossary/パラメータ/)自体がその[モデル](/glossary/モデル/)では使えない、という意味です。`unsupported_value` は、[パラメータ](/glossary/パラメータ/)は使えるが**その値が**使えない、という意味です。`context_length_exceeded` は、入力と出力の合計が上限を超えた場合です。

もう1つ、境界として押さえておくべき点があります。**[モデル](/glossary/モデル/)名の誤りは 400 ではありません**。存在しない[モデル](/glossary/モデル/)や[権限](/glossary/権限/)の無い[モデル](/glossary/モデル/)を指定した場合、返るのは 404 で、`code` は `model_not_found` です。400 の原因として[モデル](/glossary/モデル/)名を探し始めると遠回りになります。

## エラーの概要

最も多く見る形は、使えない[パラメータ](/glossary/パラメータ/)を送った場合です。

```json
{
  "error": {
    "message": "Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead.",
    "type": "invalid_request_error",
    "param": "max_tokens",
    "code": "unsupported_parameter"
  }
}
```

`param` に `max_tokens` と名指しされ、`message` には代わりに使うべき名前まで書かれています。**推測の余地がありません**。

値だけが問題の場合は、`code` が変わります。

```json
{
  "error": {
    "message": "Unsupported value: 'temperature' does not support 0.7 with this model. Only the default (1) value is supported.",
    "type": "invalid_request_error",
    "param": "temperature",
    "code": "unsupported_value"
  }
}
```

上限超過の場合は、内訳まで示されます。

```json
{
  "error": {
    "message": "This model's maximum context length is 4097 tokens. However, you requested 4927 tokens (3927 in the messages, 1000 in the completion). Please reduce the length of the messages or completion.",
    "type": "invalid_request_error",
    "param": "messages",
    "code": "context_length_exceeded"
  }
}
```

[プログラム](/glossary/プログラム/)から呼んでいる場合、公式の[ソフトウェア](/glossary/ソフトウェア/)開発キットでは `BadRequestError` として現れます。以前は別の名前でしたが、対応する状態[コード](/glossary/コード/)は同じ 400 です。

## まず最初に：param と code を読む

第一に、`param` を読みます。問題のある[パラメータ](/glossary/パラメータ/)がそのまま入っています。

第二に、`code` を読みます。`unsupported_parameter` なら[パラメータ](/glossary/パラメータ/)を外すか置き換える、`unsupported_value` なら値だけを直す、`context_length_exceeded` なら量を減らす、と対処が分かれます。

第三に、`message` を最後まで読みます。置き換え先の名前や、許される値、[トークン](/glossary/トークン/)の内訳など、必要な情報が書かれていることが多くあります。

第四に、`code` が `model_not_found` であれば、それは 400 ではなく 404 です。調べる対象が変わります。

## よくある原因と解決手順

### 原因1：そのモデルで使えないパラメータを送っている

現在最も多い形です。推論系の[モデル](/glossary/モデル/)では、従来の `max_tokens` が使えず `max_completion_tokens` を使います。公式の資料でも `max_tokens` は非推奨とされ、これらの[モデル](/glossary/モデル/)とは[互換性](/glossary/互換性/)が無いと明記されています。

**Before（従来のまま呼ぶ）：**

```python
client.chat.completions.create(
    model="o3-mini",
    messages=[{"role": "user", "content": "hi"}],
    max_tokens=500,          # → unsupported_parameter
)
```

**After（[モデル](/glossary/モデル/)に応じて名前を変える）：**

```python
client.chat.completions.create(
    model="o3-mini",
    messages=[{"role": "user", "content": "hi"}],
    max_completion_tokens=500,
)
```

複数の[モデル](/glossary/モデル/)を切り替えて使う場合、送る[パラメータ](/glossary/パラメータ/)自体を[モデル](/glossary/モデル/)ごとに変える必要があります。**同じ呼び出し[コード](/glossary/コード/)を使い回す設計だと、[モデル](/glossary/モデル/)を増やした瞬間に破綻します**。

この形は周辺の道具でも大量に起きています。道具の設定画面で[パラメータ](/glossary/パラメータ/)を空にしても、道具側が既定値を送り続けて[エラー](/glossary/エラー/)が消えない、という報告もあります。自分で外したつもりでも、**実際に送られているかどうかは別問題**です。

### 原因2：パラメータは使えるが、値が使えない

`code` が `unsupported_value` の場合です。名前は受け付けられるので、[パラメータ](/glossary/パラメータ/)を消す必要はありません。

推論系の[モデル](/glossary/モデル/)で `temperature` に既定値以外を指定した場合が代表例です。文言に「既定の1のみ対応」と明記されるため、対処はその値に合わせるか、指定自体をやめることです。

```python
# 値を既定に合わせる、または指定しない
client.chat.completions.create(model="o3-mini", messages=[...])
```

この2つの区別は実務で効きます。`unsupported_parameter` は**送ってはいけない**、`unsupported_value` は**送ってよいが値が違う**。前者に対して値だけ変えても直りません。

### 原因3：入力と出力の合計が上限を超えている

`code` が `context_length_exceeded` の場合です。ここで見落とされやすいのは、**上限に数えられるのは入力だけではない**という点です。

前掲の文言を読むと、要求した合計と、その内訳（messages 側と completion 側）が示されています。つまり、**出力の上限として指定した値も合計に含まれます**。入力が短いのに超過する場合、原因は出力側の指定であることがあります。

対処は3つです。入力を短くする、出力の上限指定を小さくする、あるいは文脈の広い[モデル](/glossary/モデル/)へ切り替える。会話履歴を積み上げる作りでは、履歴の打ち切りを実装しないと**使うほど確実に到達します**。

```python
# 履歴を直近だけに絞る（例：直近10件）
messages = [system_message] + history[-10:]
```

### 原因4：構造そのものが不正

`param` が `messages` で、文言が構造に触れている場合です。必須の項目が欠けている、役割の指定が不正、内容が空、といった形が該当します。

公式にも、[API](/glossary/api/) リファレンスで対象の[メソッド](/glossary/メソッド/)を確認し、[パラメータ](/glossary/パラメータ/)の名前・型・値・形式が仕様と一致しているかを見直すよう案内されています。あわせて、データの符号化や形式、大きさが適切かを確認するよう書かれています。

送っている内容そのものを確認するのが確実です。手元で組み立てた辞書を印字するのではなく、実際に送られる本文を見てください。

### 原因5：モデル名の誤りを 400 として探している

対処ではなく、探し方の問題です。冒頭で述べたとおり、存在しない[モデル](/glossary/モデル/)や[権限](/glossary/権限/)の無い[モデル](/glossary/モデル/)の指定は **404** で返ります。`code` は `model_not_found`、文言は対象が存在しないか[権限](/glossary/権限/)が無い、という趣旨になります。

400 が返っているなら、[モデル](/glossary/モデル/)名は少なくとも解決できています。**[モデル](/glossary/モデル/)名の綴りを何度も見直すのは、この場合まったくの遠回り**です。逆に 404 が返っているなら、[パラメータ](/glossary/パラメータ/)をいくら調整しても通りません。

## 補足：似ているが別のもの

内容の形式は正しいのに処理できない場合は 422 です。公式の説明では、形式が正しいにもかかわらず処理できなかった状態とされ、**もう一度試すよう**案内されています。400 とは違い、再試行が対処になり得る点が特徴です。

[認証](/glossary/認証/)の失敗は 401 です。キーの誤りだけでなく、組織や[プロジェクト](/glossary/プロジェクト/)の不一致、[権限](/glossary/権限/)、IP の許可リストも含まれます（[OpenAI API の 401 の記事](/posts/openai_api_401/)）。

上限や請求に関する[エラー](/glossary/エラー/)は 429 です。[トークン](/glossary/トークン/)の話が出てくるため 400 の上限超過と混同されやすいのですが、`context_length_exceeded` は1回の要求の大きさ、429 は一定時間あたりの量や残高の問題です。

Azure 経由で同じ[モデル](/glossary/モデル/)を使う場合も、[パラメータ](/glossary/パラメータ/)の仕様は同じ系統の[エラー](/glossary/エラー/)を返します。ただし配備名や[バージョン](/glossary/バージョン/)の指定が加わるため、確認すべき項目が増えます（[Azure の 400 の記事](/posts/azure_400/)）。

## 切り分けの順序

1. `param` を読む。問題の[パラメータ](/glossary/パラメータ/)がそこに名指しされている。
2. `code` を読む。`unsupported_parameter` は外す、`unsupported_value` は値を直す。
3. `message` を最後まで読む。置き換え先の名前や許される値が書かれている。
4. `code` が `model_not_found` なら 404。400 として調べない。
5. 上限超過なら、内訳を見る。出力側の指定が原因のこともある。
6. 道具を経由しているなら、実際に送られている本文を確認する。外したつもりでも送られていることがある。
7. [モデル](/glossary/モデル/)を切り替えて使うなら、[パラメータ](/glossary/パラメータ/)の組み立ても[モデル](/glossary/モデル/)ごとに分ける。
8. 形式が正しいのに通らないなら、422 の可能性を確認する。こちらは再試行が対処になり得る。

## 確認コマンド集

```bash
# 1. param と code だけを取り出す（最重要）
curl -sS https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d @request.json \
  | python3 -c "import json,sys; e=json.load(sys.stdin).get('error',{}); print('param:', e.get('param'), '| code:', e.get('code')); print(e.get('message'))"

# 2. 実際に送られる本文を確認する（道具を疑う場合）
python3 -c "
import json
body = {'model':'o3-mini','messages':[{'role':'user','content':'hi'}],'max_tokens':500}
print(json.dumps(body, ensure_ascii=False, indent=2))
"

# 3. 開発キットの例外から中身を取り出す
python3 -c "
from openai import OpenAI
import openai
try:
    OpenAI().chat.completions.create(model='o3-mini',
        messages=[{'role':'user','content':'hi'}], max_tokens=10)
except openai.BadRequestError as e:
    print(e.status_code, e.body)
"

# 4. モデル名が有効かを先に確かめる（404 との切り分け）
curl -sS -o /dev/null -w "%{http_code}\n" https://api.openai.com/v1/models/o3-mini \
  -H "Authorization: Bearer $OPENAI_API_KEY"

# 5. 利用できるモデルの一覧を取得する
curl -sS https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  | python3 -c "import json,sys; [print(m['id']) for m in json.load(sys.stdin)['data']]" | sort | head -20
```

## Editor's Note

`param` が示すのは「仕様上おかしい[パラメータ](/glossary/パラメータ/)」ではありません。**実際に送られた[パラメータ](/glossary/パラメータ/)**です。この違いが効く場面があります。

家庭向け自動化基盤の統合機能で報告された不具合が、それを示しています（[OpenAI Conversation o1/o3 models fail with 'max_tokens' is not supported with this model](https://github.com/home-assistant/core/issues/137039)）。2025年1月、推論系の[モデル](/glossary/モデル/)を選ぶと `max_tokens` が使えない旨の 400 で失敗する、という内容です。

注目すべきは続きです。報告者は設定画面で該当の項目を空にしてみたものの、**それは既定値の150を設定したことになるだけで、[エラー](/glossary/エラー/)は消えなかった**と書いています。利用者から見れば「外した」のに、[送信](/glossary/送信/)される要求には値が入り続けていたわけです。

`param` に `max_tokens` と出ている以上、それは送られています。**画面上の見え方ではなく、応答が事実を示している**。この読み方ができれば、設定を疑うのではなく、送信部分を疑う段階へ一足飛びに進めます。

同じ[エラー](/glossary/エラー/)は、公式の開発キットの[リポジトリ](/glossary/リポジトリ/)にも「ライブラリの不具合」として報告されています（[openai.BadRequestError: Error code: 400](https://github.com/openai/openai-python/issues/2046)）。実際にはライブラリの問題ではなく、[モデル](/glossary/モデル/)側の仕様変更に呼び出し側が追随していない状態でした。**400 は、送った側と受け取る側の食い違いを指しています**。どちらが古いのかを見極めるのが、この[エラー](/glossary/エラー/)の本質です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*