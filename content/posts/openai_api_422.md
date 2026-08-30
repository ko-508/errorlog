---
title: "OpenAI API の 422 エラー：原因と解決策"
date: 2026-08-03
description: "422 は OpenAI の API エラー一覧に載っておらず、定義があるのはクライアントライブラリの区分としてだけです。実際に 422 を返しているのは OpenAI 互換サーバーであることが多く、応答本文の形も違います。まず接続先と本文の形を確認するのが切り分けの起点です。"
tags: ["OpenAI API"]
images: ["og/posts/openai_api_422.png"]
errorCode: "422"
lastmod: 2026-08-03
service: "OpenAI API"
error_type: "422"
components: ["Client Library", "Compatible Endpoints"]
related_services: ["Python SDK", "Azure OpenAI Service"]
trend_incident: false
---

## 冒頭まとめ

OpenAI [API](/glossary/api/) の 422 には、他の[コード](/glossary/コード/)と違う特殊な事情があります。**公式の [API](/glossary/api/) [エラー](/glossary/エラー/)一覧に、422 の項目がありません**。401、403、404、429、500、503 には説明がありますが、422 は載っていません。

定義があるのは、公式の[ソフトウェア](/glossary/ソフトウェア/)開発キット側です。[ライブラリ](/glossary/ライブラリ/)の[エラー](/glossary/エラー/)区分の表に `UnprocessableEntityError` があり、説明は「形式は正しいにもかかわらず要求を処理できなかった」、対処は「もう一度試すこと」となっています。状態[コード](/glossary/コード/)の対応表でも 422 はこの区分に割り当てられています。

つまり **422 は、[API](/glossary/api/) 側の[エラー](/glossary/エラー/)としてではなく、[クライアント](/glossary/クライアント/)側の受け取り方として定義されている**わけです。

これが実務で意味を持ちます。開発キットは、接続先が OpenAI 本体かどうかに関係なく、422 を受け取れば同じ例外を投げます。そして OpenAI 互換をうたう[サーバー](/glossary/サーバー/)の多くは、入力の検証に失敗したとき 422 を返します。

**したがって、422 を見たときに最初に疑うべきは、自分の要求内容ではなく接続先です**。応答本文の形を見れば、どちらが返したかはすぐに分かります。

## エラーの概要

OpenAI 本体の[エラー](/glossary/エラー/)応答は、常にこの構造です。

```json
{
  "error": {
    "message": "...",
    "type": "invalid_request_error",
    "param": "messages",
    "code": "..."
  }
}
```

一方、422 を返す互換[サーバー](/glossary/サーバー/)の多くは、次の構造を返します。

```json
{
  "detail": [
    {
      "type": "string_type",
      "loc": ["body", "input", "str"],
      "msg": "Input should be a valid string",
      "input": [[2149, 87515, 1764, 374]],
      "url": "https://errors.pydantic.dev/2.5/v/string_type"
    }
  ]
}
```

**`error` [オブジェクト](/glossary/オブジェクト/)ではなく `detail` 配列**です。項目の名前もまったく違います。これは、多くの互換[サーバー](/glossary/サーバー/)が特定の[フレームワーク](/glossary/フレームワーク/)の上に作られており、その検証機構がこの形式で[エラー](/glossary/エラー/)を返すためです。末尾に検証[ライブラリ](/glossary/ライブラリ/)の説明への [URL](/glossary/url/) が入る点も特徴的です。

紛らわしいのは、**どちらの場合も開発キットの例外名は同じ**になることです。`UnprocessableEntityError` という名前を見て「OpenAI が返した」と判断してはいけません。

## まず最初に：接続先と本文の形を確認する

第一に、応答本文が `error` か `detail` かを見ます。`detail` 配列であれば、OpenAI 本体ではありません。

第二に、接続先の基点 [URL](/glossary/url/) を確認します。設定[ファイル](/glossary/ファイル/)や[環境変数](/glossary/環境変数/)で別の[サーバー](/glossary/サーバー/)を指していないか。

第三に、`detail` があれば、その中の `loc` を読みます。**どの項目が問題かが経路の形で示されます**。

第四に、本体に対して 422 が返っている場合は、公式の[ライブラリ](/glossary/ライブラリ/)の説明どおり、まず再試行します。

## よくある原因と解決手順

### 原因1：接続先が OpenAI 本体ではない

最も多い形です。開発キットは接続先を差し替えられるため、同じ[コード](/glossary/コード/)のまま別の[サーバー](/glossary/サーバー/)を呼んでいることがあります。

該当しやすいのは、推論の提供元を切り替えた場合、手元で動かす推論[サーバー](/glossary/サーバー/)を使っている場合、そして中継の仕組みを挟んでいる場合です。

```bash
# 接続先を確認する
python3 -c "
from openai import OpenAI
print(OpenAI().base_url)
"

# 環境変数で差し替えられていないか
env | grep -iE 'OPENAI_BASE_URL|OPENAI_API_BASE'
```

出力が `https://api.openai.com/v1` でなければ、相手は OpenAI 本体ではありません。**その[サーバー](/glossary/サーバー/)の仕様に合わせる必要があり、OpenAI の文書を読んでも答えは出ません**。

### 原因2：detail 配列を読んでいない

互換[サーバー](/glossary/サーバー/)由来だと分かったら、`detail` の中身が原因を示しています。読むべき項目は3つです。

`loc` は問題のある位置を配列で示します。`["body", "input", "str"]` であれば、要求本文の `input` という項目が文字列であるべきだった、という意味です。`msg` は理由、`type` は検証の種別です。

```bash
# detail の中身だけを取り出す
curl -sS <接続先>/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model":"...","input":"test"}' \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
for x in d.get('detail', []):
    print(' -> '.join(map(str, x.get('loc', []))), '|', x.get('msg'))
"
```

**OpenAI 本体の `param` に相当するのが `loc`** だと考えれば、読み方は同じです。位置が分かれば、直す場所も決まります。

### 原因3：「互換」は形式が同じであって仕様が同じではない

見落とされやすい点です。互換をうたう[サーバー](/glossary/サーバー/)は、要求の形式を合わせていますが、受け付ける値の範囲まで一致しているとは限りません。

代表的なのが埋め込みの入力です。OpenAI 本体は文字列のほかに[トークン](/glossary/トークン/)の配列も受け付けますが、互換[サーバー](/glossary/サーバー/)が文字列しか受け付けない場合、[トークン](/glossary/トークン/)の配列を渡した時点で検証に失敗します。

**Before（本体向けの実装をそのまま向ける）：**

```python
client = OpenAI(base_url="http://localhost:5001/v1", api_key="dummy")
client.embeddings.create(model="...", input=[[2149, 87515, 1764]])  # トークン配列
```

**After（相手が受け付ける形に合わせる）：**

```python
client.embeddings.create(model="...", input="埋め込みたい文字列")
```

上位の枠組みを使っている場合、[トークン](/glossary/トークン/)の配列を送るかどうかは設定で変えられることがあります。**要求を組み立てているのが自分ではなく枠組みの側**である点に注意してください。

### 原因4：OpenAI 本体から 422 が返った場合

まれですが、この場合の対処は公式に示されています。[ライブラリ](/glossary/ライブラリ/)の[エラー](/glossary/エラー/)区分の説明は「形式は正しいのに処理できなかった」であり、対処は**もう一度試すこと**です。

400 とは扱いが違います。400 は内容を直さなければ何度送っても同じですが、422 の説明には再試行が明記されています。開発キットの自動再試行の対象には含まれていないため、必要なら自分で1回試すことになります。

続く場合は、要求の識別子を控えて問い合わせてください。

### 原因5：例外名で発生源を判断している

対処ではなく、切り分けの問題です。`UnprocessableEntityError` は開発キットが状態[コード](/glossary/コード/)から機械的に決めた名前であり、**誰が返したかの情報を含みません**。

同様に、`openai` という名前が付いた例外が出たからといって、OpenAI と[通信](/glossary/通信/)しているとは限りません。多くの道具が、互換[エンドポイント](/glossary/エンドポイント/)に対して同じ開発キットを使っています。

判断材料は例外名ではなく、応答本文の形と接続先の [URL](/glossary/url/) です。

## 補足：似ているが別のもの

OpenAI 本体で入力の検証に失敗した場合は 400 です。`param` に問題の項目、`code` に種別が入ります（[OpenAI API の 400 の記事](/posts/openai_api_400/)）。**本体で内容の問題なら 400、422 ではない**、と押さえておくと切り分けが速くなります。

経路そのものが存在しない場合は 404 です。互換[サーバー](/glossary/サーバー/)では、対応していない[エンドポイント](/glossary/エンドポイント/)を呼ぶとこちらになります（[OpenAI API の 404 の記事](/posts/openai_api_404/)）。

[認証](/glossary/認証/)の失敗は 401 です。互換[サーバー](/glossary/サーバー/)では鍵の検証をしていないことも多く、適当な値でも通る場合があります（[OpenAI API の 401 の記事](/posts/openai_api_401/)）。

Azure 経由の場合も、[エラー](/glossary/エラー/)の形式や検証の仕組みが別系統です。本記事の内容がそのまま当てはまるとは限りません。

## 切り分けの順序

1. 応答本文が `error` か `detail` かを見る。`detail` なら OpenAI 本体ではない。
2. 接続先の基点 [URL](/glossary/url/) を確認する。差し替えられていないか。
3. 互換[サーバー](/glossary/サーバー/)なら、`loc` を読んで問題の項目を特定する。
4. その[サーバー](/glossary/サーバー/)が受け付ける値の範囲を確認する。形式が同じでも仕様は違う。
5. 要求を組み立てているのが自分か枠組みかを確認する。
6. 本体から返っている場合は、まず1回再試行する。
7. 例外名で発生源を判断しない。名前は状態[コード](/glossary/コード/)から機械的に決まる。
8. 内容の問題で本体から返るのは 400。422 なら前提を疑う。

## 確認コマンド集

```bash
# 1. 接続先を確認する（最重要）
python3 -c "
from openai import OpenAI
c = OpenAI()
print('base_url:', c.base_url)
"

# 2. 環境変数で差し替えられていないかを確認する
env | grep -iE 'OPENAI_BASE_URL|OPENAI_API_BASE|OPENAI_API_TYPE'

# 3. 応答本文の形を確認する（error か detail か）
curl -sS <接続先>/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{"model":"<モデル>","messages":[{"role":"user","content":"hi"}]}' | head -c 300

# 4. detail の中身を読みやすく取り出す
curl -sS <接続先>/v1/embeddings \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{"model":"<モデル>","input":"test"}' \
  | python3 -c "
import json,sys
d = json.load(sys.stdin)
if 'detail' in d:
    for x in d['detail']:
        print('loc:', ' -> '.join(map(str, x.get('loc', []))))
        print('msg:', x.get('msg'), '| type:', x.get('type'))
else:
    print('error オブジェクト形式:', d.get('error'))
"

# 5. 例外の中身をそのまま確認する
python3 -c "
from openai import OpenAI
import openai
try:
    OpenAI().embeddings.create(model='text-embedding-3-small', input='test')
except openai.APIStatusError as e:
    print(type(e).__name__, e.status_code)
    print(e.body)
"
```

## Editor's Note

例外の名前が、発生源を誤解させることがあります。それを示す記録があります（[Openai API - OpenAIEmbeddings: UnprocessableEntityError](https://github.com/oobabooga/text-generation-webui/discussions/4876)）。

2023年12月、ある利用者が埋め込みの取得で `UnprocessableEntityError` に遭遇しました。例外の名前には `openai` が付いています。しかし、貼られている内容を読むと事情が違いました。

まず接続先です。要求先は `http://localhost:5001/v1/embeddings`、つまり**手元で動かしている推論[サーバー](/glossary/サーバー/)**でした。次に応答本文です。`error` [オブジェクト](/glossary/オブジェクト/)ではなく `detail` 配列で、各要素に `type`、`loc`、`msg`、そして検証[ライブラリ](/glossary/ライブラリ/)の説明ページへの [URL](/glossary/url/) が入っています。

内容も具体的でした。`loc` は要求本文の `input` を指し、`msg` は文字列であるべきだと述べています。そして `input` の値として記録されているのは、数値の配列——[トークン](/glossary/トークン/)に変換済みの入力でした。上位の枠組みが OpenAI 本体向けに[トークン](/glossary/トークン/)の配列を送っていたのに対し、手元の[サーバー](/glossary/サーバー/)は文字列しか受け付けなかったわけです。

ここに、この[エラー](/glossary/エラー/)の構造が凝縮されています。**例外の名前は開発キットが付けたもの、[エラー](/glossary/エラー/)の中身は相手の[サーバー](/glossary/サーバー/)が作ったもの**。この2つの出どころが違うことを知らないと、OpenAI の文書を延々と読むことになります。

422 を受け取ったら、まず接続先を確認してください。`error` か `detail` か。その1点で、読むべき文書がどこにあるかが決まります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*