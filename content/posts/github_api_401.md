---
title: "GitHub API の 401 エラー：原因と解決策"
date: 2026-01-01
description: "GitHub API の 401 Unauthorized は認証そのものの失敗です。message が Requires authentication なら認証情報が届いておらず、Bad credentials なら届いた値が正しくありません。ヘッダーの欠落、トークンの誤り・期限切れ・失効、環境変数の古いトークンの優先、という原因を文言から切り分けて解決します。"
tags: ["GitHub API"]
errorCode: "401"
lastmod: 2026-07-11
service: "GitHub API"
error_type: "401"
components: ["Personal Access Token", "Authorization header"]
related_services: []
trend_incident: true
top_queries:
- '401エラー'
- 'gh: bad credentials (http 401)'
- 'github api 401'
---

## 冒頭まとめ

GitHub [API](/glossary/api/) の 401 Unauthorized は、[認証](/glossary/認証/)そのものの失敗です。[権限](/glossary/権限/)の不足ではありません（権限不足は GitHub では 404 または 403 として返ります）。401 の応答の message は2種類しかなく、これが調査の分岐点になります。Requires authentication なら、認証情報がそもそも GitHub に届いていません（原因1）。Bad credentials なら、認証情報は届いたものの、その値が正しくありません（原因2・3）。

Bad credentials の正体は、[トークン](/glossary/トークン/)の誤記や期限切れ・失効のほか、「有効な[トークン](/glossary/トークン/)を設定し直したのに、別の場所（[環境変数](/glossary/環境変数/)など）に残った古い[トークン](/glossary/トークン/)が優先され続けている」という取り違えが定番です。どの文言か、そして実際にどの[トークン](/glossary/トークン/)が送られているかを確かめることから始めます。

## エラーの概要

401 の応答は次の2種類です（いずれも実際の応答をそのまま確認したものです）。

認証情報なしで認証必須の[エンドポイント](/glossary/エンドポイント/)にアクセスした場合：

```json
{
  "message": "Requires authentication",
  "documentation_url": "https://docs.github.com/rest",
  "status": "401"
}
```

認証情報は送ったが、値が正しくない場合：

```json
{
  "message": "Bad credentials",
  "documentation_url": "https://docs.github.com/rest",
  "status": "401"
}
```

[ヘッダー](/glossary/ヘッダー/)の形式について、公式ドキュメントは、ほとんどの場合 Authorization: Bearer と Authorization: token のどちらでも[トークン](/glossary/トークン/)を渡せる（[JSON](/glossary/json/) Web Token を渡す場合のみ Bearer が必須）としています。どちらの形式かが401の原因になることは基本的にありません。また、github.com の [API](/glossary/api/) はユーザー名と[パスワード](/glossary/パスワード/)による[認証](/glossary/認証/)に対応していないため、[パスワード](/glossary/パスワード/)での[認証](/glossary/認証/)を試みる古いコードは動きません。[トークン](/glossary/トークン/)による[認証](/glossary/認証/)が前提です。

## まず最初に：message を読み、最小のリクエストで再現する

まず message の文言で、認証情報が「届いていない」のか「届いたが不正」なのかを確定します。次に、問題を最小の形で再現します。認証済みユーザー自身の情報を返す /user [エンドポイント](/glossary/エンドポイント/)が最適です。

```bash
curl -i -H "Authorization: Bearer <your-github-token>" https://api.github.com/user
```

これが 200 なら、[トークン](/glossary/トークン/)自体は有効です。[アプリケーション](/glossary/アプリケーション/)側で401が出ているなら、[アプリケーション](/glossary/アプリケーション/)が実際に送っている[トークン](/glossary/トークン/)がこれと同じものではない、という取り違え（原因3）に的が絞られます。これが 401 Bad credentials なら、[トークン](/glossary/トークン/)の値そのものの問題です（原因2）。

## よくある原因と解決手順

### 原因1：認証情報がそもそも送られていない（Requires authentication）

Authorization [ヘッダー](/glossary/ヘッダー/)が付いていない[リクエスト](/glossary/リクエスト/)が、認証必須の[エンドポイント](/glossary/エンドポイント/)に届いています。コードで[ヘッダー](/glossary/ヘッダー/)を付け忘れているか、条件分岐によって[ヘッダー](/glossary/ヘッダー/)なしの経路を通っているのが典型です。ライブラリによっては、[トークン](/glossary/トークン/)が未設定のときに Authorization [ヘッダー](/glossary/ヘッダー/)自体を送らない作りになっているため、「設定したつもりの[トークン](/glossary/トークン/)が読み込まれていない」場合もこの文言になります。

**Before（[ヘッダー](/glossary/ヘッダー/)なし）：**

```bash
curl -i https://api.github.com/user
# → 401 Requires authentication
```

**After（[ヘッダー](/glossary/ヘッダー/)を付与）：**

```bash
curl -i -H "Authorization: Bearer <your-github-token>" https://api.github.com/user
# → 200 OK
```

実際に[ヘッダー](/glossary/ヘッダー/)が送られているかは、curl の -v で送信内容を表示して、[リクエスト](/glossary/リクエスト/)に Authorization 行が含まれるかで確認できます。

### 原因2：トークンの値が正しくない（Bad credentials）

[ヘッダー](/glossary/ヘッダー/)は届いていますが、値が有効な[トークン](/glossary/トークン/)ではありません。確認すべきは次の点です。第一に、値の誤り。コピーの取りこぼしや前後の余分な文字が典型です。第二に、空の値。[環境変数](/glossary/環境変数/)が未定義のまま "Authorization: Bearer $TOKEN" のように[ヘッダー](/glossary/ヘッダー/)を組み立てると、値が空の[ヘッダー](/glossary/ヘッダー/)が送られ、実測でもこの場合の応答は Bad credentials になります。「設定したはずなのに Bad credentials」の一定数はこれです。第三に、期限切れと失効です。公式のトラブルシューティング文書も、[トークン](/glossary/トークン/)が期限切れ・取り消し済みでないことを確認項目に挙げています。fine-grained personal access token には有効期限があるため、ある日を境に突然401が始まった場合はまず期限を疑います。[トークン](/glossary/トークン/)の状態は GitHub の設定画面（Settings > Developer settings > Personal access tokens）で確認・再生成できます。

### 原因3：意図したものと違うトークンが使われている（Bad credentials）

[トークン](/glossary/トークン/)を正しく再設定したのに Bad credentials が続く場合、[アプリケーション](/glossary/アプリケーション/)が参照している認証情報が、いま設定したものと別である可能性が高いです。典型例は[環境変数](/glossary/環境変数/)です。GitHub [CLI](/glossary/cli/)（gh）のように、[環境変数](/glossary/環境変数/)（GITHUB_TOKEN や GH_TOKEN）が設定されていると、保存済みの[ログイン](/glossary/ログイン/)情報より[環境変数](/glossary/環境変数/)を優先する道具があります。この場合、gh auth login で何度[ログイン](/glossary/ログイン/)し直しても、[環境変数](/glossary/環境変数/)に残った古い[トークン](/glossary/トークン/)が送られ続け、401が再発します。CI 環境では、Secrets に登録された古い[トークン](/glossary/トークン/)や、別のサービス用に設定したままの[トークン](/glossary/トークン/)[変数](/glossary/変数/)（例として、パッケージ管理ツール用に設定して忘れられた[トークン](/glossary/トークン/)）が同じ症状を起こします。GitHub Enterprise と github.com の取り違え（接続先と違うホスト用の[トークン](/glossary/トークン/)を送っている）も同類です。

対処は、実際に使われている[トークン](/glossary/トークン/)の特定です。

```bash
# トークン系の環境変数が設定されていないかを確認
env | grep -iE "github|gh_" | sed 's/=.*/=（値は非表示）/'

# GitHub CLI の場合、どの認証情報が使われているかを確認
gh auth status
```

[環境変数](/glossary/環境変数/)が優先されている場合は、その[変数](/glossary/変数/)を更新するか削除したうえで、再度最小の[リクエスト](/glossary/リクエスト/)（/user）で確認します。

## 補足：401を繰り返すと一時的に403に変わる

公式ドキュメントによると、短時間に無効な認証情報での[リクエスト](/glossary/リクエスト/)を繰り返すと、GitHub はそのユーザーの[認証](/glossary/認証/)の試みを一時的にすべて拒否し、正しい認証情報を使っても 403 Forbidden が返るようになります。無効な[トークン](/glossary/トークン/)のまま自動[リトライ](/glossary/リトライ/)を回し続けると、正しい[トークン](/glossary/トークン/)に直した後もしばらく締め出される、という二次被害につながります。401 が出たら[リトライ](/glossary/リトライ/)で押し切ろうとせず、先に原因を直してください。

なお、[認証](/glossary/認証/)は通っているのに操作が拒否される場合のコードは401ではありません。classic [トークン](/glossary/トークン/)の scope 不足や非公開リソースへの無権限アクセスは 404（[404 の記事](/posts/github_api_404/)）、GitHub App・fine-grained [トークン](/glossary/トークン/)の権限不足や[レート制限](/glossary/レート制限/)は 403（[403 の記事](/posts/github_api_403/)）です。

## 切り分けの順序

1. message を読む。Requires authentication なら原因1（届いていない）、Bad credentials なら原因2・3（値の問題）。
2. curl の /user で最小再現する。手元の[トークン](/glossary/トークン/)で 200 が返るなら、[アプリケーション](/glossary/アプリケーション/)が送っている[トークン](/glossary/トークン/)との取り違え（原因3）。401 のままなら値・期限の問題（原因2）。
3. 原因3 の場合、[環境変数](/glossary/環境変数/)と設定を洗い出し、実際に使われている認証情報を特定して更新する。
4. 修正後、無効[トークン](/glossary/トークン/)での[リトライ](/glossary/リトライ/)を止めてから再確認する（繰り返しによる一時的な403を避けるため）。

## 確認コマンド集

```bash
# 1. トークンの有効性を最小構成で確認
curl -i -H "Authorization: Bearer <your-github-token>" https://api.github.com/user

# 2. Authorization ヘッダーが実際に送信されているかを確認
curl -v -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/user 2>&1 | grep -i "^> authorization"

# 3. トークン系の環境変数の有無を確認（値は表示しない）
env | grep -iE "github|gh_" | sed 's/=.*/=（値は非表示）/'

# 4. GitHub CLI が使っている認証情報を確認
gh auth status
```

## Editor's Note

原因3の実例として、GitHub [CLI](/glossary/cli/) の公式[リポジトリ](/glossary/リポジトリ/)への報告があります（[401 Error at every turn](https://github.com/cli/cli/issues/10032)、2024年12月）。gh の[コマンド](/glossary/コマンド/)を実行するたびに [HTTP](/glossary/http/) 401: Bad credentials が出て、gh auth login で[ログイン](/glossary/ログイン/)し直しても少し経つとまた再発する、という報告です。報告者の環境では[環境変数](/glossary/環境変数/) GITHUB_TOKEN に値が設定されており、gh は保存済みの[ログイン](/glossary/ログイン/)よりこの[環境変数](/glossary/環境変数/)を優先するため、[環境変数](/glossary/環境変数/)を消す（set GITHUB_TOKEN=）ことでその場をしのぎ、別の作業でまた設定されると再発する、という繰り返しが記録されています。「[ログイン](/glossary/ログイン/)は成功しているのに Bad credentials」という一見矛盾した症状の正体が、別の場所にある古い認証情報だったという典型例です。

401 は、認証情報が「届いていない」のか「届いたが不正」なのかを message が最初に教えてくれる[エラー](/glossary/エラー/)です。[トークン](/glossary/トークン/)を作り直す前に、いま実際に何が送られているのかを確かめることが確実な近道です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*