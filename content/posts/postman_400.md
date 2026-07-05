---
draft: true
title: "Postman の 400 エラー：原因と解決策"
date: 2026-06-16
description: "Postmanから送ったリクエストのパラメータや形式に誤りがある"
tags: ["Postman"]
errorCode: "400"
service: "Postman"
error_type: "400"
components: []
related_services: ["HTTP", "JSON", "API", "URL"]
top_queries:
- 'postman 400 bad request'
---

## エラーの概要

Postmanから送信した[HTTP](/glossary/http/)[リクエスト](/glossary/リクエスト/)の[パラメータ](/glossary/パラメータ/)や形式に誤りがある場合、[サーバー](/glossary/サーバー/)は400（Bad Request）[エラー](/glossary/エラー/)を返します。これはクライアント側の[リクエスト](/glossary/リクエスト/)構成に問題があることを示しており、[JSON](/glossary/json/)ボディの形式破損、Content-Type[ヘッダー](/glossary/ヘッダー/)とボディ内容の不一致、クエリパラメータの不正な文字などが典型的な原因です。Postmanでこの[エラー](/glossary/エラー/)が発生した場合、[リクエスト](/glossary/リクエスト/)内容の詳細確認と修正が必要になります。

## 実際のエラーメッセージ例

Postmanのレスポンスパネルに表示される例：

```json
{
  "status": 400,
  "error": "Bad Request",
  "message": "Invalid request body",
  "details": "JSON parse error: Unexpected character"
}
```

Postman Consoleに出力される[ログ](/glossary/ログ/)の例：

```
POST http://api.example.com/users
→ Request Headers: Content-Type: application/json
→ Request Body: {"name":"John","age":}
← 400 Bad Request
← Response: {"error":"Invalid JSON format"}
```

## よくある原因と解決手順

### 原因1：JSONボディの形式が壊れている、または必須フィールドが欠けている

[JSON](/glossary/json/)の文法[エラー](/glossary/エラー/)が最も一般的な原因です。括弧の閉じ忘れ、カンマの位置[エラー](/glossary/エラー/)、シングルクォートの使用、必須キーの欠落などが該当します。[API](/glossary/api/)[サーバー](/glossary/サーバー/)は[リクエストボディ](/glossary/リクエストボディ/)をパースする際に、形式が正確でないと400[エラー](/glossary/エラー/)で拒否します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```json
{
  "name": "Yamada Taro",
  "email": "yamada@example.com",
  "age": 30,
  "address": "Tokyo"
}
```
↑ 上記は正しい[JSON](/glossary/json/)に見えますが、[API](/glossary/api/)が`phone`フィールドを必須としている場合や、Postmanで以下のようなボディを入力しているケースで[エラー](/glossary/エラー/)が発生します：

```json
{
  "name": "Yamada Taro",
  "email": "yamada@example.com",
  "age": 30,
  "address": "Tokyo",
}
```

**After（修正後）：**

```json
{
  "name": "Yamada Taro",
  "email": "yamada@example.com",
  "age": 30,
  "address": "Tokyo",
  "phone": "09012345678"
}
```

Postmanで修正するには、Bodyタブを開き、以下の手順を実行してください。

1. Body内の「Code beautifier」または「format」ボタンをクリックして[JSON](/glossary/json/)形式を自動整形する
2. 右側に表示される「Error」メッセージを確認する
3. [API](/glossary/api/)ドキュメントで必須フィールドを確認し、すべて揃っているか検証する

### 原因2：Content-Typeヘッダーがボディのデータフォーマットと一致していない

Postmanが送信するContent-Type[ヘッダー](/glossary/ヘッダー/)の値が、実際のボディの形式と異なると[サーバー](/glossary/サーバー/)が400[エラー](/glossary/エラー/)を返します。[JSON](/glossary/json/)形式のボディを送信する場合はapplication/jsonを指定する必要がありますが、誤ってtext/plainやapplication/x-www-form-urlencodedが設定されているケースが多く見られます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

Postmanの[リクエスト](/glossary/リクエスト/)設定：
- Method: POST
- [URL](/glossary/url/): http://api.example.com/data
- Headers: Content-Type: text/plain
- Body (raw):
```json
{
  "product_id": 12345,
  "quantity": 10
}
```

**After（修正後）：**

Postmanの[リクエスト](/glossary/リクエスト/)設定：
- Method: POST
- [URL](/glossary/url/): http://api.example.com/data
- Headers: Content-Type: application/json
- Body (raw):
```json
{
  "product_id": 12345,
  "quantity": 10
}
```

Postmanで修正するには、Headersタブを開き、以下の対応を行ってください。

1. Headersタブで「Content-Type」キーの値を確認する
2. Bodyタブで「raw」を選択している場合、右側のドロップダウンから「[JSON](/glossary/json/)」を選択する
3. ドロップダウン選択でContent-Typeが自動的に application/json に設定されることを確認する
4. または、Headersタブで手動でContent-Type: application/json に修正する

### 原因3：URLのクエリパラメータに不正な文字が含まれている

[URL](/glossary/url/)のクエリパラメータに、スペースや日本語などのエンコードが必要な文字が含まれている場合、[サーバー](/glossary/サーバー/)が400[エラー](/glossary/エラー/)を返すことがあります。特にPostmanで手動で[URL](/glossary/url/)を入力している場合、[URL](/glossary/url/)エンコードが自動的に行われないかもしれません。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```
GET http://api.example.com/search?keyword=東京都&sort=新着順
```

上記の[URL](/glossary/url/)はブラウザでは自動的にエンコードされますが、Postmanで手動入力した場合、日本語や記号がそのまま送信されて400[エラー](/glossary/エラー/)になる可能性があります。

**After（修正後）：**

```
GET http://api.example.com/search?keyword=%E6%9D%B1%E4%BA%AC%E9%83%BD&sort=%E6%96%B0%E7%9D%80%E9%A0%86
```

またはPostmanで以下の方法で安全に設定します：

Postmanの[リクエスト](/glossary/リクエスト/)設定：
- Method: GET
- [URL](/glossary/url/): http://api.example.com/search
- Params（タブ）:
  - Key: keyword, Value: 東京都
  - Key: sort, Value: 新着順

Paramsタブを使用することで、Postmanが自動的に[URL](/glossary/url/)エンコードを行い、正しい形式で[リクエスト](/glossary/リクエスト/)が送信されます。

## ツール固有の注意点

Postmanで400[エラー](/glossary/エラー/)が発生した際、以下のツール固有の確認ポイントがあります。

**Postman Consoleの活用**

View メニュー → Show Postman Console を選択すると、[リクエスト](/glossary/リクエスト/)と[レスポンス](/glossary/レスポンス/)の詳細な[ログ](/glossary/ログ/)が表示されます。ここでは実際に送信された[ヘッダー](/glossary/ヘッダー/)、ボディ、クエリパラメータを確認できます。UIで設定した内容と実際に送信された内容が異なるかどうかを把握できるため、[デバッグ](/glossary/デバッグ/)が格段に容易になります。

**[環境変数](/glossary/環境変数/)とコレクション[変数](/glossary/変数/)の確認**

Postmanで[環境変数](/glossary/環境変数/)やコレクション[変数](/glossary/変数/)を使用している場合、[変数](/glossary/変数/)の値が意図しない形式で解決されていないか確認が必要です。例えば、{{api_key}} という[変数](/glossary/変数/)が空文字列に解決された場合、[ヘッダー](/glossary/ヘッダー/)が不完全になり400[エラー](/glossary/エラー/)が発生する可能性があります。左上の「Environments」セクションで変数値を確認してください。

**Pre-request Scriptでの自動生成値の検証**

Pre-request Scriptで動的にボディや[ヘッダー](/glossary/ヘッダー/)を生成している場合、そのスクリプトが正確な[JSON](/glossary/json/)や[ヘッダー](/glossary/ヘッダー/)値を生成しているか確認してください。JavaScriptの文法[エラー](/glossary/エラー/)があれば、生成される値が不正となり400[エラー](/glossary/エラー/)の原因になります。

## それでも解決しない場合

以下の[デバッグ](/glossary/デバッグ/)手順を実施してください。

**Postman Consoleでの詳細確認**

Postman Consoleを開き、以下の情報を確認します：

```
リクエストURL、メソッド、すべてのヘッダー、ボディの完全な内容、サーバーから返されたレスポンスボディの全文を記録してください。
```

**cURL[コマンド](/glossary/コマンド/)での検証**

Postmanの[リクエスト](/glossary/リクエスト/)右側にある「</> Code」ボタンをクリックし、cURL[コマンド](/glossary/コマンド/)をコピーして[ターミナル](/glossary/ターミナル/)で実行してみてください。もし同じ[エラー](/glossary/エラー/)がcURLでも発生すれば、Postmanではなく[リクエスト](/glossary/リクエスト/)自体が不正です。反対に、cURLでは成功する場合、Postman固有の設定に問題がある可能性があります。

例：

```bash
curl -X POST http://api.example.com/users \
  -H "Content-Type: application/json" \
  -d '{"name":"Yamada","email":"yamada@example.com"}'
```

**[API](/glossary/api/)[サーバー](/glossary/サーバー/)側の[ログ](/glossary/ログ/)を確認**

自社の[API](/glossary/api/)[サーバー](/glossary/サーバー/)である場合、[サーバー](/glossary/サーバー/)側の[エラーログ](/glossary/エラーログ/)を確認してください。404や[タイムアウト](/glossary/タイムアウト/)ではなく400[エラー](/glossary/エラー/)であれば、[サーバー](/glossary/サーバー/)が受け取った[リクエスト](/glossary/リクエスト/)の内容についても詳細な[エラーメッセージ](/glossary/エラーメッセージ/)が記録されているはずです。その情報から原因がより明確になります。

**公式ドキュメントの参照**

連携している[API](/glossary/api/)提供者の公式ドキュメントやリファレンスで、[リクエスト](/glossary/リクエスト/)形式の仕様を確認してください。必須フィールド、データ型、許可される値の範囲などが明記されていることが多く、自身の[リクエスト](/glossary/リクエスト/)との差異を特定できます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*