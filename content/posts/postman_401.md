---
title: "Postman の 401 エラー：原因と解決策"
date: 2026-06-16
description: "テスト対象のAPIへの認証に失敗した。Postman 401 エラーの原因と解決策を解説します。"
tags: ["Postman"]
errorCode: "401"
service: "Postman"
error_type: "401"
components: []
related_services: ["OAuth 2.0", "JWT"]
---

## エラーの概要

Postmanで401[エラー](/glossary/エラー/)が返される場合、[テスト](/glossary/テスト/)対象の[API](/glossary/api/)が、[リクエスト](/glossary/リクエスト/)の認証情報を検証した際に失敗したことを意味します。[API](/glossary/api/)[サーバー](/glossary/サーバー/)側は「[認証](/glossary/認証/)されていない[リクエスト](/glossary/リクエスト/)」と判定し、その[レスポンス](/glossary/レスポンス/)として401 Unauthorizedを返しています。これはPostmanの設定不備や[トークン](/glossary/トークン/)期限切れなど、クライアント側の原因がほとんどです。

## 実際のエラーメッセージ例

Postmanのレスポンスペイン（Response）に以下のようなメッセージが表示されます：

```json
{
  "error": "Unauthorized",
  "message": "Invalid or expired token",
  "status": 401
}
```

または、より詳細な[レスポンス](/glossary/レスポンス/)例：

```json
{
  "code": 401,
  "message": "Authentication failed: Missing or invalid API key"
}
```

Postmanの[コンソール](/glossary/コンソール/)には次のような[ログ](/glossary/ログ/)が出力されます：

```
Request URL: https://api.example.com/v1/data
Request Method: GET
Status Code: 401 Unauthorized
Response Time: 150ms
```

## よくある原因と解決手順

### 原因1：AuthorizationタブでAPIキーやトークンが正しく設定されていない

Postmanの[リクエスト](/glossary/リクエスト/)設定画面でAuthorizationタブを開いても、[認証](/glossary/認証/)タイプが「No Auth」のままであったり、[トークン](/glossary/トークン/)値が空白のまま送信されたりすることで401が発生します。あるいは、[認証](/glossary/認証/)タイプは選択されていても、実際の[API](/glossary/api/)キーや[トークン](/glossary/トークン/)値が正しく入力されていない場合も該当します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```
Authorization Type: No Auth
Headers:
  (認証ヘッダーなし)
```

**After（修正後）：**

```
Authorization Type: Bearer Token
Token: <your-api-token>

もしくは、Authorizationタブで「API Key」を選択：
Key: Authorization
Value: Bearer <your-api-token>
Add to: Header
```

解決手順は以下の通りです：

1. Postmanのリクエストタブを開き、「Authorization」タブをクリック
2. 「Type」ドロップダウンで適切な[認証](/glossary/認証/)タイプを選択（Bearer Token、[API](/glossary/api/) Key、Basic Auth など）
3. [API](/glossary/api/)ドキュメントに従い、正確な[トークン](/glossary/トークン/)またはキーを入力
4. 「Send」ボタンで[リクエスト](/glossary/リクエスト/)を再送信

### 原因2：トークンの有効期限が切れている

[OAuth](/glossary/oauth/) 2.0や[JWT](/glossary/jwt/)等の認証方式では、発行された[トークン](/glossary/トークン/)に有効期限が設定されていることがほとんどです。数時間から数日の期限が切れた[トークン](/glossary/トークン/)をPostmanで送信すると、[API](/glossary/api/)[サーバー](/glossary/サーバー/)はそれを無効と判定し401を返します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```javascript
// Pre-request Scriptで古いトークンをそのまま使用
var token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...";
pm.request.headers.add({
  key: "Authorization",
  value: "Bearer " + token
});
```

**After（修正後）：**

```javascript
// Pre-request Scriptでトークン取得時刻を記録し、期限切れなら再取得
var storedToken = pm.environment.get("api_token");
var tokenTimestamp = pm.environment.get("token_timestamp");
var currentTime = new Date().getTime();
var tokenExpiresIn = 3600000; // 1時間（ミリ秒）

if (!storedToken || (currentTime - tokenTimestamp) > tokenExpiresIn) {
  // トークンが存在しないか期限切れなら新規取得
  var clientId = pm.environment.get("client_id");
  var clientSecret = pm.environment.get("client_secret");
  
  var request = {
    url: "https://api.example.com/oauth/token",
    method: "POST",
    body: {
      mode: "urlencoded",
      urlencoded: [
        { key: "client_id", value: clientId },
        { key: "client_secret", value: clientSecret },
        { key: "grant_type", value: "client_credentials" }
      ]
    }
  };
  
  pm.sendRequest(request, function(err, response) {
    if (!err) {
      var jsonData = response.json();
      pm.environment.set("api_token", jsonData.access_token);
      pm.environment.set("token_timestamp", new Date().getTime());
    }
  });
}
```

解決手順：

1. [API](/glossary/api/)プロバイダーの[認証](/glossary/認証/)[エンドポイント](/glossary/エンドポイント/)（例：`/oauth/token`）にアクセスし、新しい[トークン](/glossary/トークン/)を取得
2. 取得した[トークン](/glossary/トークン/)をPostmanの[環境変数](/glossary/環境変数/)に保存
3. Pre-request Scriptを使用して、[リクエスト](/glossary/リクエスト/)送信前に自動的に[トークン](/glossary/トークン/)期限をチェック
4. 期限切れの場合は自動更新するロジックを組み込む

### 原因3：環境変数に認証情報がセットされていない

Postmanでは、[API](/glossary/api/)キーや[トークン](/glossary/トークン/)を[環境変数](/glossary/環境変数/)として管理することが推奨されています。しかし、[環境変数](/glossary/環境変数/)が正しくセットされていなかったり、参照する環境が異なったりすると、リクエストヘッダーに`{{variable_name}}`という文字列がそのまま送信され、[API](/glossary/api/)[サーバー](/glossary/サーバー/)は無効な[トークン](/glossary/トークン/)と判定して401を返します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```
Authorization Type: Bearer Token
Token: {{api_token}}

環境変数が未設定、または別の環境が選択されている状態でSend
```

**After（修正後）：**

```
1. Postmanの「Environments」パネルから環境を新規作成または既存環境を編集
2. 変数名：api_token
   初期値：（空欄）
   現在値：<your-actual-token-value>
   を入力して保存

3. リクエスト画面の右上「Environment」ドロップダウンで該当環境を選択

4. Authorization Type: Bearer Token
   Token: {{api_token}}
   と設定してSend
```

解決手順：

1. Postman左側の「Environments」をクリック
2. 使用している環境を選択（なければ「Create」で新規作成）
3. 認証情報を格納する[変数](/glossary/変数/)を追加（例：`api_token`、`api_key`）
4. 「Current Value」に実際の[トークン](/glossary/トークン/)値を入力して保存
5. [リクエスト](/glossary/リクエスト/)画面右上の環境セレクタで、今セットした環境が選択されているか確認
6. [リクエスト](/glossary/リクエスト/)のAuthorizationタブで、プレースホルダー構文 `{{variable_name}}` を使用

## Postman固有の注意点

Postmanの[環境変数](/glossary/環境変数/)はローカル（Current Value）とグローバル（Initial Value）の2段階で管理されます。[セキュリティ](/glossary/セキュリティ/)上の理由から、[API](/glossary/api/)キーや[トークン](/glossary/トークン/)などの機密情報は「Initial Value」には記入せず、「Current Value」のみに設定することが重要です。これにより、チームとコレクションを共有する際に機密情報が意図せず流出するのを防げます。

またPostman Workspaceをチーム間で共有している場合、各自の[環境変数](/glossary/環境変数/)を「Private」に設定することで、ローカル端末に限定して認証情報を管理できます。設定方法は環境編集画面で、[環境変数](/glossary/環境変数/)の右側にある目のアイコンをクリックして「Private」を選択してください。

さらに、Pre-request Scriptを使用する場合、スクリプト内で`pm.sendRequest()`を呼び出すと、同期的に別の[HTTP](/glossary/http/)[リクエスト](/glossary/リクエスト/)（[トークン](/glossary/トークン/)取得など）を実行できます。ただし、この[メソッド](/glossary/メソッド/)は非同期で動作するため、続く実[メソッド](/glossary/メソッド/)は十分なコールバック処理を含めて記述する必要があります。コールバック内で`pm.environment.set()`を使い、取得した[トークン](/glossary/トークン/)を[環境変数](/glossary/環境変数/)に保存してから、メインリクエストに参照させるパターンが一般的です。

## それでも解決しない場合

以下の確認手順を実施してください：

**ネットワークトラフィックを確認**
Postmanの[コンソール](/glossary/コンソール/)を開き（左下の「Console」ボタン）、送信されたリクエストヘッダーと、[API](/glossary/api/)[サーバー](/glossary/サーバー/)から返されたレスポンスヘッダーを確認します。特に`Authorization`[ヘッダー](/glossary/ヘッダー/)が正しく送信されているか、[レスポンス](/glossary/レスポンス/)に`WWW-Authenticate`[ヘッダー](/glossary/ヘッダー/)が含まれているかをチェック。

**[API](/glossary/api/)ドキュメントを再確認**
認証方式（Bearer Token、[API](/glossary/api/) Key、Basic Auth等）、[トークン](/glossary/トークン/)の取得方法、[トークン](/glossary/トークン/)に必要な[スコープ](/glossary/スコープ/)やパーミッション、ホスト名や[エンドポイント](/glossary/エンドポイント/)のURL形式が正確か、公式ドキュメントで改めて確認します。

**[テスト](/glossary/テスト/)用[API](/glossary/api/)キーを使用**
本番環境の[API](/glossary/api/)キーではなく、[テスト](/glossary/テスト/)用・開発用の[API](/glossary/api/)キーが別途提供されている場合、それを使用して401が解消するか試してください。本番キーに[権限](/glossary/権限/)がない可能性も考慮します。

**Postmanを再起動**
[環境変数](/glossary/環境変数/)の反映遅延や[キャッシュ](/glossary/キャッシュ/)の問題を排除するため、Postmanアプリケーション全体を再起動し、再度[リクエスト](/glossary/リクエスト/)を送信してみてください。

**サポートページを参照**
Postmanの公式サポートサイト（https://learning.postman.com/docs/sending-requests/authorization/）に、各認証タイプの詳細な設定ガイドが記載されています。また、APIプロバイダーの公式ドキュメントで、401エラーが発生する具体的なシナリオと対処法が説明されている場合も多くあります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*