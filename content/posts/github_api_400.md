---
title: "GitHub API の 400 エラー：原因と解決策"
date: 2026-01-01
description: "GitHub API の 400 Bad Request は、リクエストの形式そのものが壊れている場合に返されます。代表例は JSON 構文の誤り（Problems parsing JSON）です。必須パラメータの不足や値の不正は 400 ではなく 422 が返ります。エラーメッセージの文言から原因を切り分けて解決します。"
tags: ["GitHub API"]
errorCode: "400"
lastmod: 2026-07-10
service: "GitHub API"
error_type: "400"
components: []
related_services: []
trend_incident: true
top_queries:
- 'api400'
---

## 冒頭まとめ

GitHub [API](/glossary/api/) の 400 Bad Request は、[リクエスト](/glossary/リクエスト/)の形式そのものが壊れていて、[サーバー](/glossary/サーバー/)が中身の検証に進めない場合に返されます。公式ドキュメントが 400 として挙げているのは、[リクエスト](/glossary/リクエスト/)本文が [JSON](/glossary/json/) として読めない（Problems parsing [JSON](/glossary/json/)）、本文が [JSON](/glossary/json/) [オブジェクト](/glossary/オブジェクト/)の形になっていない（Body should be a [JSON](/glossary/json/) object）、[API](/glossary/api/) [バージョン](/glossary/バージョン/)指定の[ヘッダー](/glossary/ヘッダー/)に存在しない値を指定した、の3つです。

一方、[JSON](/glossary/json/) としては正しく読めたうえで、必須[パラメータ](/glossary/パラメータ/)が足りない・値が仕様に合わないという場合に返るのは、400 ではなく 422 Unprocessable Entity です。400 の調査で最初にすべきことは、設定や[パラメータ](/glossary/パラメータ/)の見直しではなく、応答の message を読んで 400 と 422 のどちらの問題かを確定することです。400 は形式の問題なので、同じ[リクエスト](/glossary/リクエスト/)を再試行しても結果は変わりません。修正が必要です。

## エラーの概要

GitHub [API](/glossary/api/) の 400 の応答本文は次の形です。

```json
{
  "message": "Problems parsing JSON",
  "documentation_url": "https://docs.github.com/rest"
}
```

公式のトラブルシューティング文書は、400 と 422 の境界を明確に定めています。[リクエスト](/glossary/リクエスト/)本文に不正な [JSON](/glossary/json/) を送ると 400 と Problems parsing [JSON](/glossary/json/) が返ります。[エンドポイント](/glossary/エンドポイント/)が [JSON](/glossary/json/) [オブジェクト](/glossary/オブジェクト/)を期待しているのに本文がその形になっていないと 400 と Body should be a [JSON](/glossary/json/) object が返ります。これに対し、必須[パラメータ](/glossary/パラメータ/)の省略や[パラメータ](/glossary/パラメータ/)の型の誤りは 422 と Invalid request、[リクエスト](/glossary/リクエスト/)を処理できない場合は 422 と Validation Failed です。つまり「[JSON](/glossary/json/) として読めるかどうか」が 400 と 422 のおおまかな境界線です。

## まず最初に：message を読んで境界を確定する

応答の message の文言で、調べるべき場所が決まります。

Problems parsing [JSON](/glossary/json/) なら、本文が [JSON](/glossary/json/) として壊れています（原因1）。Body should be a [JSON](/glossary/json/) object なら、[JSON](/glossary/json/) としては読めるものの、[オブジェクト](/glossary/オブジェクト/)（波かっこで始まる形）になっていません（原因2）。[API](/glossary/api/) [バージョン](/glossary/バージョン/)が未サポートである旨のメッセージなら、[バージョン](/glossary/バージョン/)指定[ヘッダー](/glossary/ヘッダー/)の値の問題です（原因3）。

Validation Failed や Invalid request が返っているなら、それは 400 ではなく 422 の問題です。本文の形式は正しく届いており、中身が[エンドポイント](/glossary/エンドポイント/)の仕様に合っていません。[GitHub API の 422 エラー](/posts/github_api_422/)の記事を参照してください。Bad credentials なら 401 で、[トークン](/glossary/トークン/)の問題です（[GitHub API の 401 エラー](/posts/github_api_401/)）。

## よくある原因と解決手順

### 原因1：リクエスト本文が JSON として壊れている

手書きの [JSON](/glossary/json/) では、カンマの欠落や引用符の閉じ忘れが定番です。

**Before（カンマが欠落していて400になる）：**

```bash
curl -X POST https://api.github.com/repos/<owner>/<repo>/issues \
  -H "Authorization: Bearer <your-github-token>" \
  -d '{"title": "New issue" "body": "This is a test"}'
```

**After（修正後）：**

```bash
curl -X POST https://api.github.com/repos/<owner>/<repo>/issues \
  -H "Authorization: Bearer <your-github-token>" \
  -d '{"title": "New issue", "body": "This is a test"}'
```

見落とされやすいのが、プログラムから呼び出す場合の直列化（[オブジェクト](/glossary/オブジェクト/)を [JSON](/glossary/json/) 文字列に変換する処理）の漏れです。手元のコード上では[オブジェクト](/glossary/オブジェクト/)が正しく見えていても、直列化せずに送信すると、通信路には [JSON](/glossary/json/) でない文字列が流れます。実際の報告例として、JavaScript の fetch で body に[オブジェクト](/glossary/オブジェクト/)をそのまま渡して Problems parsing [JSON](/glossary/json/) になったケースが GitHub 公式コミュニティに記録されています。fetch の body には [JSON](/glossary/json/).stringify() で変換した文字列を渡す必要があります。送信前の検証には、本文を一度ファイルに書き出して確かめる方法が確実です。

```bash
# 本文が JSON として正しいかを検証してから送信する
python3 -m json.tool < body.json && \
curl -X POST https://api.github.com/repos/<owner>/<repo>/issues \
  -H "Authorization: Bearer <your-github-token>" \
  --data @body.json
```

### 原因2：本文が JSON オブジェクトの形になっていない

[JSON](/glossary/json/) としては読めるものの、[エンドポイント](/glossary/エンドポイント/)が期待する[オブジェクト](/glossary/オブジェクト/)（{ } の形）ではなく、文字列や配列を送っているケースです。公式ドキュメントのとおり、この場合は Body should be a [JSON](/glossary/json/) object が返ります。

**Before（[JSON](/glossary/json/) の文字列を送ってしまい400になる）：**

```bash
curl -X POST https://api.github.com/repos/<owner>/<repo>/issues \
  -H "Authorization: Bearer <your-github-token>" \
  -d '"just a string"'
```

**After（[オブジェクト](/glossary/オブジェクト/)の形で送る）：**

```bash
curl -X POST https://api.github.com/repos/<owner>/<repo>/issues \
  -H "Authorization: Bearer <your-github-token>" \
  -d '{"title": "New issue"}'
```

プログラムからの呼び出しでは、二重の直列化が典型的な発生源です。すでに [JSON](/glossary/json/) 文字列に変換済みのデータを、さらに [JSON](/glossary/json/) として送信する仕組み（Python の requests の json= [引数](/glossary/引数/)など）に渡すと、[オブジェクト](/glossary/オブジェクト/)ではなく「[JSON](/glossary/json/) の文字列」が届きます。直列化は1回だけ、送信ライブラリの [JSON](/glossary/json/) 送信機能を使うならライブラリに任せる、と決めておくのが安全です。なおこの種の誤りは、[エンドポイント](/glossary/エンドポイント/)によっては 400 ではなく 422（... is not an object という文言）として報告されることもあります。どちらのコードでも、疑う場所は同じく直列化の回数です。

### 原因3：API バージョン指定の誤り

GitHub [API](/glossary/api/) は、リクエストヘッダー X-GitHub-Api-Version で [API](/glossary/api/) [バージョン](/glossary/バージョン/)を指定します。公式ドキュメントのとおり、存在しない[バージョン](/glossary/バージョン/)を指定すると、400 とともにその[バージョン](/glossary/バージョン/)がサポートされていない旨のメッセージが返ります。

```bash
curl -H "Authorization: Bearer <your-github-token>" \
  -H "X-GitHub-Api-Version: <APIバージョン>" \
  https://api.github.com/repos/<owner>/<repo>
```

指定できる値は公式ドキュメントの [API](/glossary/api/) [バージョン](/glossary/バージョン/)一覧で確認してください。日付の書式の誤記や、思い込みの値をそのまま書くことが原因になります。なお、かつて使われていた Accept [ヘッダー](/glossary/ヘッダー/)による[バージョン](/glossary/バージョン/)指定とは仕組みが異なるため、古い記事のコードを流用する場合は注意が必要です。

## 切り分けの順序

1. 応答の message を読む。Validation Failed / Invalid request なら 422 の問題として切り替える（[422 の記事](/posts/github_api_422/)）。Bad credentials なら 401。
2. Problems parsing [JSON](/glossary/json/) なら、送信している本文そのものを取り出して [JSON](/glossary/json/) 検証にかける（python3 -m json.tool など）。プログラムからの送信なら、直列化の有無を確認する。
3. Body should be a [JSON](/glossary/json/) object なら、本文の先頭が { で始まる[オブジェクト](/glossary/オブジェクト/)かを確認する。直列化を2回していないかを確認する。
4. [バージョン](/glossary/バージョン/)未サポートのメッセージなら、X-GitHub-Api-Version の値を公式の一覧と突き合わせる。

## 確認コマンド集

```bash
# 1. 本文の JSON 検証（送信前に必ず通す）
python3 -m json.tool < body.json

# 2. 検証済みファイルから送信し、応答ヘッダーごと確認
curl -i -X POST https://api.github.com/repos/<owner>/<repo>/issues \
  -H "Authorization: Bearer <your-github-token>" \
  --data @body.json

# 3. 実際に何が送信されているかを確認（リクエスト内容の表示）
curl -v -X POST https://api.github.com/repos/<owner>/<repo>/issues \
  -H "Authorization: Bearer <your-github-token>" \
  --data @body.json 2>&1 | grep -A5 "^>"
```

## Editor's Note

400 と 422 の境界を1つの流れで示す実例として、GitHub 公式コミュニティの議論があります（[github actions repository dispatch "message": "Problems parsing JSON"](https://github.com/orgs/community/discussions/28224)、2022年）。Python からワークフローを起動する [API](/glossary/api/) を呼んだ報告者は、まず 400 と Problems parsing [JSON](/glossary/json/) を受け取ります（本文が [JSON](/glossary/json/) として届いていない状態）。次に json.dumps() で直列化した文字列を requests の json= [引数](/glossary/引数/)に渡したところ、今度は 422 と「... is not an object」が返りました（[JSON](/glossary/json/) としては読めるが、二重直列化により文字列が届いた状態）。最終的な解決は、辞書を json= に直接渡して直列化をライブラリに任せる形でした。エラーコードが 400 から 422 に変わったこと自体が「[JSON](/glossary/json/) として読めるようになった」という前進のサインだった、という点がこの実例の要点です。2022年の議論ですが、400 と 422 のこの境界は現行の公式トラブルシューティング文書の記述と一致しています。

400 の対処は、[パラメータ](/glossary/パラメータ/)の意味を考える前に、送信物が [JSON](/glossary/json/) としてどう届いているかを機械的に検証することから始まります。message の文言が調査の場所を正確に教えてくれるので、コードの数字だけで判断しないことが確実な近道です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*