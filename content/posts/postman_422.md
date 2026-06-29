---
draft: true
title: "Postman の 422 エラー：原因と解決策"
date: 2026-06-29
description: "Postmanにおける422エラー（Unprocessable Entity）は、リクエストの構文は正しいが、送信された。"
tags: ["Postman"]
errorCode: "422"
urgency: "medium"
service: "Postman"
error_type: "422"
components: []
related_services: ["GitHub API", "FastAPI"]
---

## エラーの概要

Postmanで422（Unprocessable Entity）[エラー](/glossary/エラー/)が発生すると、[HTTP](/glossary/http/)[リクエスト](/glossary/リクエスト/)の構文は正しく到達していますが、[サーバー](/glossary/サーバー/)が[リクエストボディ](/glossary/リクエストボディ/)の内容を処理できない状態を示しています。これは[リクエスト](/glossary/リクエスト/)のデータ形式、Content-Typeの不一致、[バリデーション](/glossary/バリデーション/)失敗など、意味論的な問題が原因です。

## 実際のエラーメッセージ例

GitHubの[API](/glossary/api/)検索[エンドポイント](/glossary/エンドポイント/)で報告された[エラー](/glossary/エラー/)：

```json
{
  "message": "Validation Failed",
  "errors": [
    {
      "message": "The listed users and repositories cannot be searched either because the resources do not exist or you do not have permission to view them.",
      "resource": "Search",
      "field": "q",
      "code": "invalid"
    }
  ],
  "documentation_url": "https://docs.github.com/v3/search/",
  "status": "422"
}
```

FastAPI[サーバー](/glossary/サーバー/)からの報告：

```json
{
  "detail": [
    {
      "loc": ["body"],
      "msg": "value is not a valid dict",
      "type": "type_error.dict"
    }
  ]
}
```

**[エラーメッセージ](/glossary/エラーメッセージ/)の読み方：**

- `"status": "422"` → [HTTP](/glossary/http/) [ステータスコード](/glossary/ステータスコード/)：[サーバー](/glossary/サーバー/)が[リクエスト](/glossary/リクエスト/)を理解したが、含まれるデータに検証[エラー](/glossary/エラー/)がある
- `"message": "Validation Failed"` → [リクエストボディ](/glossary/リクエストボディ/)のデータが [API](/glossary/api/) の要件を満たしていないことを示す
- `"errors"` 配列 → 複数の検証[エラー](/glossary/エラー/)が存在する場合、各[エラー](/glossary/エラー/)の詳細情報（フィールド名、エラーコード、説明）を含む
- `"loc": ["body"]` → FastAPI形式：[エラー](/glossary/エラー/)の位置がボディ部分にあることを指示する
- `"msg": "value is not a valid dict"` → 期待されたデータ型（辞書/[オブジェクト](/glossary/オブジェクト/)）が送信されていない

## よくある原因と解決手順

### 原因1：Content-Typeヘッダーがリクエストボディの形式と一致していない

Postmanで `application/x-www-form-urlencoded` または `multipart/form-data` を指定しているのに、実際には[JSON](/glossary/json/)形式でボディを送信している場合、[サーバー](/glossary/サーバー/)は入力データを正しくパースできず、422[エラー](/glossary/エラー/)を返します。また逆に、[JSON](/glossary/json/)を期待している[エンドポイント](/glossary/エンドポイント/)に対してフォーム形式を送信する場合も同様です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
# Postman の Body タブで Form データを選択
Content-Type: multipart/form-data

# 中身は JSON 文字列を直接入力
{
  "username": "john_doe",
  "email": "john@example.com"
}
```

**After（修正後）：**

```yaml
# Postman の Body タブで raw を選択し、JSON を指定
Content-Type: application/json

# JSON 形式で送信
{
  "username": "john_doe",
  "email": "john@example.com"
}
```

✅ 修正後の確認：

```bash
# Postman の Headers タブで Content-Type が正しく設定されていることを確認
# Send ボタンをクリックしレスポンスが 200 または 201 であれば成功です
```

Postmanのレスポンスパネルで、`status: 200` または `status: 201` と表示されていれば修正は完了です。

### 原因2：コレクション実行時のファイル添付で、対象ファイルがワーキングディレクトリに存在しない

Postmanのコレクションランナーで[テスト](/glossary/テスト/)を実行する際、`form-data` でファイル添付（File型）を指定しても、ファイルが Postman の実行ワーキングディレクトリに配置されていないと、422[エラー](/glossary/エラー/)が発生します。UI上での単発[リクエスト](/glossary/リクエスト/)実行では成功しても、Collection Run では失敗するケースが典型的です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
# Postman Body タブ (form-data)
# Key: "document" | Value Type: File
# Value: /home/user/documents/my-file.pdf  ← 相対パスで指定
```

**After（修正後）：**

```yaml
# Postman Body タブ (form-data)
# Key: "document" | Value Type: File
# Value: ./uploads/my-file.pdf  ← プロジェクトルートからの相対パス

# または、ワーキングディレクトリを Postman 設定で明示的に指定
```

✅ 修正後の確認：

```bash
# ファイルをプロジェクトの同じディレクトリに配置
ls -la ./uploads/my-file.pdf

# Postman でコレクションを実行
# Postman → Collection Runner → Run
# レスポンスが 200 または 201 であれば成功です
```

ファイルパスが正しく解決され、コレクションランナーの[レスポンス](/glossary/レスポンス/)結果に `status: 200` が表示されていれば修正は完了です。

### 原因3：リクエストボディのデータがサーバーの期待する型と一致していない

FastAPIなどのフレームワークでは、[エンドポイント](/glossary/エンドポイント/)が `body` [パラメータ](/glossary/パラメータ/)を期待しているのに、Postmanからクエリパラメータとして送信したり、ネストされた[オブジェクト](/glossary/オブジェクト/)構造が異なったりすると、422[エラー](/glossary/エラー/)が発生します。特にPythonバリデーションライブラリ（Pydantic）は型チェックが厳密なため、数値を文字列で送信するなどの型ミスマッチも原因になります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
// Postman の Params タブにデータを入れている場合
// URL: http://localhost:8000/users
// Key: "user_id" | Value: "123"
// Key: "name" | Value: "Alice"

// FastAPI エンドポイントが期待しているボディ
// @app.post("/users")
// async def create_user(user: UserSchema):
//   return user

// ここで FastAPI は Body に {"user_id": 123, "name": "Alice"} の
// JSON オブジェクトを期待しており、クエリパラメータを受け取る仕様になっていない
```

**After（修正後）：**

```javascript
// Postman の Body タブで raw → JSON を選択
// Headers に "Content-Type: application/json" が自動設定される

// URL: http://localhost:8000/users
// Body タブでJSONペイロードを直接入力
{
  "user_id": 123,
  "name": "Alice"
}

// または、FastAPI 側でクエリパラメータを受け取る仕様に変更
// @app.post("/users")
// async def create_user(user_id: int = Query(...), name: str = Query(...)):
//   return {"user_id": user_id, "name": name}
```

✅ 修正後の確認：

```bash
# Postman の Body タブで JSON データが正しく整形されていることを確認
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"user_id": 123, "name": "Alice"}'

# レスポンスが 200 または 201 で、期待されたデータが返されていれば成功です
```

レスポンスボディに作成されたユーザー情報が含まれ、ステータスが `200` または `201` であれば修正は完了です。

## 解決策の早見表

| 解決策 | 実装難易度 | 再起動要否 | 対応[OS](/glossary/os/) |
|--------|-----------|-----------|-------|
| Content-Typeとボディ形式の一致を確認 | 低 | 不要 | 全[OS](/glossary/os/) |
| ファイル添付のパスをワーキングディレクトリに修正 | 中 | 不要 | 全[OS](/glossary/os/) |
| [リクエストボディ](/glossary/リクエストボディ/)を[パラメータ](/glossary/パラメータ/)から移動 | 中 | 不要 | 全[OS](/glossary/os/) |

## ツール固有の注意点

### Postmanの Body タブの設定による違い

Postmanの Body タブには複数の送信方法があり、選択した方法によって自動的に Content-Type が設定されます。

- **form-data** → `multipart/form-data`（ファイルアップロード向け）
- **x-www-form-urlencoded** → `application/x-www-form-urlencoded`（フォーム送信向け）
- **raw** → [JSON](/glossary/json/)/[XML](/glossary/xml/)/テキストなど手動で指定する形式

多くの[API](/glossary/api/)（[REST](/glossary/rest/) [API](/glossary/api/)、[GraphQL](/glossary/graphql/)含む）は [JSON](/glossary/json/) ボディを期待しているため、特に指定がない限り `raw` → `JSON` の組み合わせを使用してください。

### GitHub APIでの422エラーの頻出パターン

GitHubのSearch [API](/glossary/api/)で422が返される場合、クエリパラメータ `q` の値が不正であることが多いです。特に以下のケースで発生します：

- 検索語が長すぎる（最大256文字）
- [スコープ](/glossary/スコープ/)が無効（例：`q=user:nonexistent+repo:nonexistent`）
- 特殊文字がURL エンコードされていない

Postmanの Params タブで `q` を設定する場合、値に空白やコロンが含まれていれば自動的にURL エンコードされます。ただし、複雑な[クエリ](/glossary/クエリ/)を手動で入力する場合は、事前に値の妥当性をGitHubの検索構文ドキュメントで確認することを推奨します。

### FastAPIの Pydantic バリデーション

FastAPIで422が頻発する場合、Postmanから送信されるデータが Pydantic [モデル](/glossary/モデル/)の定義と一致しているか確認してください。以下の点をチェックします：

- すべての必須フィールドが含まれているか
- 各フィールドのデータ型が一致しているか（文字列 vs 数値など）
- ネストされた[オブジェクト](/glossary/オブジェクト/)の構造が期待通りか

Postmanの[レスポンス](/glossary/レスポンス/)に `"loc": ["body", "フィールド名"]` と表示されていれば、そのフィールドの型またはバリデーションルール違反が原因です。

## それでも解決しない場合

### ログとデバッグ情報の確認

Postmanの[コンソール](/glossary/コンソール/)（Console）パネルを開き、[リクエスト](/glossary/リクエスト/)と[レスポンス](/glossary/レスポンス/)の詳細を確認してください。以下の情報を記録します。

```bash
# Postman Console の表示内容
# - Request Headers（実際に送信されたヘッダー）
# - Request Body（実際に送信されたボディ）
# - Response Headers
# - Response Body（エラー詳細）
```

### サーバー側のログ確認

FastAPI、Flask、Django など、[API](/glossary/api/) [サーバー](/glossary/サーバー/)の[ログ](/glossary/ログ/)を確認してください。422[エラー](/glossary/エラー/)時にサーバーログに詳細なバリデーションエラーが出力されている場合があります。

```bash
# FastAPI の場合（ターミナル出力）
# INFO:     127.0.0.1:12345 - "POST /users HTTP/1.1" 422 ...
# 詳細なエラーメッセージがターミナルに出力される

# Python で実行している場合
# python -u main.py  # アンバッファリング出力で即座にログを確認
```

### 公式ドキュメント参照

送信先[API](/glossary/api/)の公式ドキュメントを確認し、該当[エンドポイント](/glossary/エンドポイント/)の[リクエスト](/glossary/リクエスト/)仕様を再度チェックしてください。特に以下の項目を確認します。

- 必須[ヘッダー](/glossary/ヘッダー/)（Authorization、[API](/glossary/api/)-Keyなど）
- 必須フィールドと省略可能フィールド
- サポートされるデータ型とフォーマット
- [ペイロード](/glossary/ペイロード/)例

## 代替ツールの検討

この[エラー](/glossary/エラー/)が頻発して開発に支障が出る場合は、以下のツールへの移行を検討できます。

- **Insomnia** → Postmanよりシンプルなインターフェースで、[JSON](/glossary/json/)/フォーム送信の切り替えが直感的です。環境変数管理やコレクション実行も備え、同等の機能を提供しながら[CLI](/glossary/cli/)ツール(`insomnia-inso`)による自動[テスト](/glossary/テスト/)が容易です。

- **Bruno** → ローカルファーストで、[リクエスト](/glossary/リクエスト/)定義を[Git](/glossary/git/)管理可能なテキスト形式で保存できます。チームでの共有や[バージョン管理](/glossary/バージョン管理/)が効率的で、特にコレクション内でのファイル参照が安定しています。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*