---
title: "OpenAI API の 404 エラー：原因と解決策"
date: 2026-08-03
description: "OpenAI API の 404 は3系統に分かれます。モデルが見つからない場合、経路が違う場合、資源の識別子が見つからない場合です。文言には実際に要求されたモデル名や経路がそのまま入るため、自分の指定と突き合わせれば原因が確定します。モデルの文言は「存在しない」と「権限が無い」を区別しません。"
tags: ["OpenAI API"]
images: ["og/posts/openai_api_404.png"]
errorCode: "404"
lastmod: 2026-08-03
service: "OpenAI API"
error_type: "404"
components: ["Chat Completions", "Models"]
related_services: ["Python SDK", "Node SDK"]
trend_incident: false
---

## 冒頭まとめ

OpenAI [API](/glossary/api/) の 404 は、指定した対象が見つからないことを示します。ただし「何が」見つからないかで、3つの系統に分かれます。

1つ目は**モデル**です。`code` は `model_not_found`、文言は指定したモデルが存在しない**か、アクセス権が無い**、という形になります。

2つ目は**経路**です。文言は `Invalid URL (POST /v1/...)` の形で、`code` は付きません。要求を送った先の経路そのものが存在しない場合です。

3つ目は**資源の識別子**です。ファイルやアシスタントなど、識別子で指定する対象が見つからない場合が該当します。

この3つには共通の性質があります。**文言に、実際に要求された内容がそのまま入る**ことです。モデル名なら送られたモデル名、経路なら送られた経路。したがって、自分が指定したつもりの値と突き合わせるだけで、原因の大半は確定します。

そしてもう1つ、押さえるべき点があります。モデルの文言は、**存在しないのか、権限が無いのかを区別しません**。1つの文に両方が併記されています。したがって「モデル名が正しいか」だけを確認しても、原因の半分しか潰せません。

## エラーの概要

モデルが見つからない場合の応答です。

```json
{
  "error": {
    "message": "The model `gpt-4` does not exist or you do not have access to it.",
    "type": "invalid_request_error",
    "param": null,
    "code": "model_not_found"
  }
}
```

`param` は `null` です。**どの[パラメータ](/glossary/パラメータ/)が問題かは示されません**。示されるのはモデル名そのもので、文言の中に埋め込まれています。

経路が違う場合は、形式がまったく変わります。

```text
404 Invalid URL (POST /v1/chat/completions/)
```

括弧の中に、**実際に要求された[メソッド](/glossary/メソッド/)と経路**が入ります。上の例では末尾に余分な区切り文字が付いています。これが原因そのものです。

同じ形で、次のような経路も報告されています。

```text
404 Invalid URL (POST /v1/v1/chat/completions)
404 Invalid URL (POST /v1/chat/completions/chat/completions/)
```

いずれも、基点となる URL と経路の組み立てが二重になった結果です。**文言を読めば、何が起きたかがそのまま見えます**。

## まず最初に：文言に入っている値を自分の指定と突き合わせる

第一に、`code` があるかを見ます。`model_not_found` ならモデルの系統、無ければ経路か資源の系統です。

第二に、文言に括弧付きの経路が入っていれば、それが実際に要求された経路です。自分が設定した基点 URL と、[ソフトウェア](/glossary/ソフトウェア/)開発キットが付ける経路の組み合わせを確認します。

第三に、モデル名が入っていれば、綴りを確認します。ただし綴りが正しくても終わりではありません。

第四に、綴りが正しい場合は**アクセス権の側**を疑います。文言はこの2つを区別しないためです。

## よくある原因と解決手順

### 原因1：モデル名は正しいが、アクセス権が無い

見落とされやすい形です。文言に「存在しない**か**、アクセス権が無い」と併記されている以上、綴りの確認だけでは足りません。

アクセス権が分かれる要因はいくつかあります。組織の利用段階によって使えるモデルが違う場合、プロジェクト単位でモデルが制限されている場合、そして地域の制限がかかっている場合です。

```bash
# いま実際に使えるモデルの一覧を取得する（推測より確実）
curl -sS https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  | python3 -c "import json,sys; [print(m['id']) for m in json.load(sys.stdin)['data']]" | sort

# 特定のモデルだけを確認する
curl -sS -o /dev/null -w "%{http_code}\n" https://api.openai.com/v1/models/gpt-4o \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

一覧に出てこないなら、そのキーからは使えません。**一覧に無いモデルを指定し続けても、綴りをどう直しても通りません**。

複数のプロジェクトを使い分けている場合、キーの属するプロジェクトによって結果が変わります。別のキーで一覧を取ると内容が違う、という形で切り分けられます。

### 原因2：昨日まで動いていたモデルが消えた

[コード](/glossary/コード/)を変えていないのに突然 404 になる場合です。モデルには提供の終了があり、廃止されると同じ文言で「存在しない」と扱われます。

この形では、綴りもアクセス権も問題ではありません。**モデルの側が無くなっています**。対処は後継のモデルへの切り替えです。

固定のモデル名を[コード](/glossary/コード/)へ直接書いていると、この事態に弱くなります。設定として外に出しておけば、切り替えが1か所で済みます。

```python
# モデル名を設定として外に出す
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
client.chat.completions.create(model=MODEL, messages=[...])
```

### 原因3：経路が二重になっている

`Invalid URL` の形で返る場合です。原因のほとんどは、**基点となる URL と経路の組み立てが重複している**ことです。

**Before（基点にも経路にも版を含める）：**

```python
client = OpenAI(base_url="https://api.openai.com/v1/")   # 末尾に区切り文字
# 開発キットが /chat/completions を付けるため、経路が崩れる
```

**After（基点は版まで、末尾の区切り文字は付けない）：**

```python
client = OpenAI(base_url="https://api.openai.com/v1")
```

代替の提供元や中継の仕組みを使っている場合、その基点 URL に既に版が含まれていることがあります。その状態で開発キットに版を足させると、`/v1/v1/...` の形になります。**文言の括弧内を読めば、どちらが余分かが一目で分かります**。

まとめて実行する仕組みで送る場合も同様です。項目として指定する経路に版を含めるかどうかで、同じ問題が起こります。

### 原因4：モデルと経路の組み合わせが合っていない

経路は実在するが、そのモデルがその経路に対応していない場合です。会話形式のモデルを、旧来の補完用の経路へ送った場合が代表例です。

この場合、モデル名も経路も単体では正しいため、どちらを見ても間違いが見つかりません。**組み合わせが問題**です。

対処は、使うモデルに対応した経路を確認することです。会話形式のモデルは会話用の経路、埋め込みは埋め込み用の経路、と対応が決まっています。

### 原因5：資源の識別子が見つからない

ファイル、アシスタント、微調整の実行など、識別子で指定する対象が見つからない場合です。文言には対象の種類と識別子が入ります。

ここで疑うべきは、識別子そのものよりも**どのプロジェクトから見ているか**です。資源はプロジェクトに属するため、別のプロジェクトのキーで参照すれば「無い」と返ります。

```bash
# 資源が現在のキーから見えるかを一覧で確認する
curl -sS https://api.openai.com/v1/files \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  | python3 -c "import json,sys; [print(f['id'], f.get('filename')) for f in json.load(sys.stdin)['data']]"
```

削除済みの対象を参照している場合も同じ結果になります。作成した処理と参照する処理が別々に動いている構成では、順序や有効期限を確認してください。

## 補足：似ているが別のもの

[認証](/glossary/認証/)の失敗は 401 です。キーの誤りだけでなく、組織やプロジェクトの不一致もこちらに含まれます（[OpenAI API の 401 の記事](/posts/openai_api_401/)）。

地域が対応外の場合は 403 で、`type` が `request_forbidden` になります（[OpenAI API の 403 の記事](/posts/openai_api_403/)）。**同じ「使えない」でも、モデルの権限は 404、地域は 403** と分かれます。

送った内容そのものに問題がある場合は 400 です。使えない[パラメータ](/glossary/パラメータ/)や値、上限の超過が該当します（[OpenAI API の 400 の記事](/posts/openai_api_400/)）。

残高や利用量の問題は 429 です。モデルが使えないという症状は似て見えますが、返る[コード](/glossary/コード/)が違います。

なお、他の基盤でも 404 が「無い」と「見せない」を兼ねる設計は共通しています。GCP でも、対象の存在を明かさないために 404 が返ることがあると公式に明記されています（[GCP の 404 の記事](/posts/gcp_404/)）。

## 切り分けの順序

1. `code` を見る。`model_not_found` ならモデル、無ければ経路か資源。
2. 文言の括弧内に経路があれば、それが実際に要求された経路。基点 URL と突き合わせる。
3. モデル名の綴りを確認する。ただし、これだけでは半分。
4. 使えるモデルの一覧を取得する。載っていなければ権限の問題。
5. 昨日まで動いていたなら、モデルの提供終了を疑う。
6. モデルも経路も正しいなら、組み合わせを疑う。
7. 資源の識別子なら、キーの属するプロジェクトを確認する。
8. 地域の制限であれば 403 の側。`type` で見分ける。

## 確認コマンド集

```bash
# 1. エラーの code と文言を取り出す
curl -sS https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hi"}]}' \
  | python3 -c "import json,sys; e=json.load(sys.stdin).get('error',{}); print(e.get('code'), '|', e.get('message'))"

# 2. 実際に要求されている URL を確認する（開発キット経由）
python3 -c "
from openai import OpenAI
c = OpenAI()
print('base_url:', c.base_url)
"

# 3. 使えるモデルの一覧を取得する
curl -sS https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  | python3 -c "import json,sys; [print(m['id']) for m in json.load(sys.stdin)['data']]" | sort

# 4. 特定のモデルが使えるかだけを確認する
curl -sS -o /dev/null -w "%{http_code}\n" https://api.openai.com/v1/models/<モデル名> \
  -H "Authorization: Bearer $OPENAI_API_KEY"

# 5. 経路を明示して最小の要求を送る（開発キットの組み立てを排除する）
curl -sS -o /dev/null -w "%{http_code}\n" https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hi"}]}'

# 6. 資源が現在のキーから見えるかを確認する
curl -sS https://api.openai.com/v1/files \
  -H "Authorization: Bearer $OPENAI_API_KEY" | head -c 500
```

## Editor's Note

`Invalid URL` の形で返る 404 は、**答えが文言の中に書かれている**種類の[エラー](/glossary/エラー/)です。それを示す報告があります（[openai.chat.completions.create throws a 404 Invalid URL error](https://github.com/openai/openai-node/issues/348)）。

2023年10月、公式の[ソフトウェア](/glossary/ソフトウェア/)開発キットを使った[アプリケーション](/glossary/アプリケーション/)で `404 Invalid URL (POST /v1/chat/completions/)` が出続ける、という内容です。報告者は同じ[エンドポイント](/glossary/エンドポイント/)を別の道具から呼ぶと正常に動くことを確認しており、[プログラム](/glossary/プログラム/)側の問題だと絞り込んでいます。

そして、報告の中でこう書いています。**[エラー](/glossary/エラー/)文言に出ている経路には、余分な区切り文字が1つ付いている**。正しい経路との違いは、末尾のその1文字だけでした。URL の組み立て方を差し替えたところ、期待どおりに動くようになっています。

この[エラー](/glossary/エラー/)の構造は、401 の文言に送られたキーが入るのと同じです。**[サーバー](/glossary/サーバー/)は、受け取ったものをそのまま返しています**。したがって、自分の設定を眺めるより、返ってきた文言を読むほうが速い。設定[ファイル](/glossary/ファイル/)には正しく見える値が書いてあり、実際に送られているものが違う、という状況は珍しくありません。

モデルの側の 404 にも似た性質があります。ただしこちらは、文言が「存在しない」と「権限が無い」を区別しません。**綴りを何度見直しても、権限の問題なら永久に直りません**。一覧を取得して、使えるモデルを事実として確認するのが最短です。

404 に当たったら、文言の中の値を読む。それが自分の指定と一致するか。一致するなら、次に疑うのは権限です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*