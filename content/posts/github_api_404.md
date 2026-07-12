---
title: "GitHub API の 404 エラー：原因と解決策"
date: 2026-01-01
description: "GitHub API の 404 Not Found は、リソースが存在しない場合だけでなく、認証や権限の不備でも返されます。GitHub は非公開リポジトリの存在を隠すため、権限の問題に 403 ではなく 404 を使う設計です。URL の誤り・認証の不備・権限不足の3系統を切り分けて解決します。"
tags: ["GitHub API"]
errorCode: "404"
lastmod: 2026-07-10
service: "GitHub API"
error_type: "404"
components: []
related_services: []
trend_incident: true
top_queries:
- 'github 404 原因'
- 'github api 404'
- 'github api not found'
---

## 冒頭まとめ

GitHub [API](/glossary/api/) の 404 Not Found には、二重の意味があります。指定したリソースが本当に存在しない場合と、存在するが[権限](/glossary/権限/)がなくて見せてもらえない場合です。公式ドキュメントに明記されているとおり、GitHub は非公開[リポジトリ](/glossary/リポジトリ/)の存在を外部に確認させないために、[認証](/glossary/認証/)や[権限](/glossary/権限/)の不備に対して 403 Forbidden ではなく 404 を返す設計を採っています。つまり、リソースがあるはずなのに404が出たら、まず疑うべきは [URL](/glossary/url/) ではなく[認証](/glossary/認証/)と[権限](/glossary/権限/)です。

原因は3系統に整理できます。[URL](/glossary/url/) の指定誤り（タイポ・末尾スラッシュ・エンコード漏れ）、[認証](/glossary/認証/)の不備（[トークン](/glossary/トークン/)未指定・期限切れ・失効）、そして[認証](/glossary/認証/)は通っているが[トークン](/glossary/トークン/)の[権限](/glossary/権限/)が足りない場合です。切り分けの起点は、同じ形の[リクエスト](/glossary/リクエスト/)を条件を変えて比べることです。

## エラーの概要

GitHub [API](/glossary/api/) の404の応答本文は次の形です。status の値は数値ではなく文字列である点に注意してください。

```json
{
  "message": "Not Found",
  "documentation_url": "https://docs.github.com/rest/repos/repos#get-a-repository",
  "status": "404"
}
```

documentation_url は、GitHub がその[リクエスト](/glossary/リクエスト/)をどの[エンドポイント](/glossary/エンドポイント/)として解釈したかを示す手がかりです。意図と違う[エンドポイント](/glossary/エンドポイント/)のリファレンスが返ってきている場合は、[URL](/glossary/url/) の形そのものを取り違えています。意図どおりのリファレンスが返っているのに404なら、対象の存在か[権限](/glossary/権限/)の問題です。

[権限](/glossary/権限/)の問題が404として現れるのは GitHub の意図的な設計です。もし権限不足に403を返すと、404との違いから「その[リポジトリ](/glossary/リポジトリ/)は存在する（が見られない）」という情報が漏れてしまいます。これを防ぐため、非公開リソースへの適切に[認証](/glossary/認証/)されていない[リクエスト](/glossary/リクエスト/)には、存在しない場合と同じ404を返します。診断する側から見ると、404は「無い」と「見せてもらえない」を区別してくれないコードだ、と理解しておくことが出発点になります。

## まず最初に：条件を変えて同じリクエストを比べる

404の原因を推測する前に、2つの比較で範囲を絞れます。

第一に、[トークン](/glossary/トークン/)自体の生死を確認します。認証済みユーザー自身の情報を返す[エンドポイント](/glossary/エンドポイント/)を叩きます。

```bash
curl -i -H "Authorization: Bearer <your-github-token>" https://api.github.com/user
```

200 が返れば[トークン](/glossary/トークン/)は有効です。401 Unauthorized（Bad credentials）が返るなら、[トークン](/glossary/トークン/)の値の誤りや失効であり、404とは別の問題として先に解決します。

第二に、確実に存在する公開[リポジトリ](/glossary/リポジトリ/)に対して、調べたいものと同じ形の[リクエスト](/glossary/リクエスト/)を送ります。

```bash
curl -i https://api.github.com/repos/octocat/Hello-World
```

これが通るなら [URL](/glossary/url/) の組み立て方は正しく、問題は対象リソースの側（存在または[権限](/glossary/権限/)）に絞られます。これも404になるなら、[URL](/glossary/url/) の形そのものを疑います（原因1）。

## よくある原因と解決手順

### 原因1：URL の指定誤り

オーナー名・[リポジトリ](/glossary/リポジトリ/)名・ファイルパスの綴りの誤りは、そのまま404になります。[ファイル名](/glossary/ファイル名/)は思い込みが入りやすい箇所です。たとえば microsoft/vscode [リポジトリ](/glossary/リポジトリ/)のライセンスファイルは LICENSE.md ではなく LICENSE.txt であり、[拡張子](/glossary/拡張子/)を誤ると404が返ります。

**Before（[ファイル名](/glossary/ファイル名/)の思い込みで404）：**

```bash
curl -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/repos/microsoft/vscode/contents/LICENSE.md
```

**After（実際の[ファイル名](/glossary/ファイル名/)を確認して指定）：**

```bash
curl -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/repos/microsoft/vscode/contents/LICENSE.txt
```

[ファイル名](/glossary/ファイル名/)の確認には、親[ディレクトリ](/glossary/ディレクトリ/)の一覧取得（/contents/ を[パス](/glossary/パス/)なしで叩く）や、ブラウザでの[リポジトリ](/glossary/リポジトリ/)の目視が確実です。

綴り以外に、公式ドキュメントが名指しで挙げている落とし穴が2つあります。1つは末尾スラッシュで、[エンドポイント](/glossary/エンドポイント/)の末尾に / を付けるだけで404になります。もう1つはパスパラメータの [URL](/glossary/url/) エンコードで、[パラメータ](/glossary/パラメータ/)値にスラッシュなどの特殊文字が含まれる場合、正しくエンコードしないと [URL](/glossary/url/) が別の形として解釈されます。[ブランチ](/glossary/ブランチ/)名にスラッシュが含まれる場合（feature/login など）が典型です。

### 原因2：認証されていない・トークンが失効している

対象が非公開[リポジトリ](/glossary/リポジトリ/)の場合、[認証](/glossary/認証/)[ヘッダー](/glossary/ヘッダー/)なしの[リクエスト](/glossary/リクエスト/)は、[リポジトリ](/glossary/リポジトリ/)が実在しても404になります。前述のとおり、存在を隠すための設計です。期限切れや取り消し済みの[トークン](/glossary/トークン/)を付けた[リクエスト](/glossary/リクエスト/)も、適切に[認証](/glossary/認証/)されていない[リクエスト](/glossary/リクエスト/)として同じ結果になります。

**Before（[認証](/glossary/認証/)なしで非公開[リポジトリ](/glossary/リポジトリ/)にアクセス）：**

```bash
curl -i https://api.github.com/repos/myorg/private-repo
# -> 404 Not Found
```

**After（有効な[トークン](/glossary/トークン/)を付与）：**

```bash
curl -i -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/repos/myorg/private-repo
```

[トークン](/glossary/トークン/)の有効性は前述の /user への[リクエスト](/glossary/リクエスト/)で確認できます。有効なのにまだ404が出る場合は、原因3に進みます。

### 原因3：認証は通っているが、トークンの権限が足りない

最も見落とされやすい原因です。[トークン](/glossary/トークン/)が有効でも、その[トークン](/glossary/トークン/)に対象リソースへの[権限](/glossary/権限/)がなければ、応答は403ではなく404です。公式のトラブルシューティング文書は、存在するはずのリソースで404が出た場合の確認項目を次のように挙げています。

personal access token (classic) を使っている場合は、[エンドポイント](/glossary/エンドポイント/)が要求する scope（非公開[リポジトリ](/glossary/リポジトリ/)なら repo など）を[トークン](/glossary/トークン/)が持っているか、[トークン](/glossary/トークン/)の所有者自身が[エンドポイント](/glossary/エンドポイント/)の要求する役割（組織オーナー限定の[エンドポイント](/glossary/エンドポイント/)など）を持っているか、[トークン](/glossary/トークン/)が対象の非公開[リポジトリ](/glossary/リポジトリ/)にアクセスできるか、失効・期限切れになっていないかを確認します。

fine-grained personal access token や GitHub App の[トークン](/glossary/トークン/)の場合は、[エンドポイント](/glossary/エンドポイント/)が要求する[権限](/glossary/権限/)（permissions）が付与されているかに加えて、その[トークン](/glossary/トークン/)の対象範囲に該当[リポジトリ](/glossary/リポジトリ/)が含まれているかを確認します。[トークン](/glossary/トークン/)作成時に対象[リポジトリ](/glossary/リポジトリ/)を限定していると、[権限](/glossary/権限/)の種類が合っていても対象外の[リポジトリ](/glossary/リポジトリ/)には届きません。

GitHub Actions の GITHUB_TOKEN を使っている場合は、その[トークン](/glossary/トークン/)で操作できるのはワークフローが動いている[リポジトリ](/glossary/リポジトリ/)の資源に限られます。別の[リポジトリ](/glossary/リポジトリ/)や組織の資源を操作するには、personal access token か GitHub App の[トークン](/glossary/トークン/)が必要です。

また、読み取りはできる相手でも、書き込み系の[エンドポイント](/glossary/エンドポイント/)（[リポジトリ](/glossary/リポジトリ/)設定の更新など）はより強い役割を要求します。閲覧できるのに更新だけ404になる場合は、その操作に必要な役割を[エンドポイント](/glossary/エンドポイント/)のリファレンス（応答の documentation_url が指すページ）で確認してください。

## 切り分けの順序

1. /user で[トークン](/glossary/トークン/)の生死を確認する。401なら[トークン](/glossary/トークン/)の値・失効の問題として先に解決する。
2. 公開[リポジトリ](/glossary/リポジトリ/)への同じ形の[リクエスト](/glossary/リクエスト/)で、[URL](/glossary/url/) の組み立てを検証する（原因1）。末尾スラッシュとパスパラメータのエンコードもここで確認する。
3. 対象が非公開かどうかを確認する。非公開なら、[認証](/glossary/認証/)[ヘッダー](/glossary/ヘッダー/)の有無（原因2）と、[トークン](/glossary/トークン/)の scope・[権限](/glossary/権限/)・対象範囲（原因3）を順に確認する。
4. 応答の documentation_url が指すリファレンスで、その[エンドポイント](/glossary/エンドポイント/)が要求する[権限](/glossary/権限/)・役割と、[URL](/glossary/url/) の正しい形を確認する。

## 確認コマンド集

```bash
# 1. トークンの生死と権限の主体を確認（200なら有効、401なら失効・誤り）
curl -i -H "Authorization: Bearer <your-github-token>" https://api.github.com/user

# 2. URL の組み立てを公開リポジトリで検証
curl -i https://api.github.com/repos/octocat/Hello-World

# 3. 対象リクエストをヘッダー付きで実行し、本文の documentation_url を確認
curl -i -H "Authorization: Bearer <your-github-token>" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/<owner>/<repo>"

# 4. ファイル名の確認（ディレクトリ一覧の取得）
curl -H "Authorization: Bearer <your-github-token>" \
  "https://api.github.com/repos/<owner>/<repo>/contents/"
```

## Editor's Note

[権限](/glossary/権限/)の問題が404として現れることの実例として、GitHub 公式コミュニティの議論があります（[REST API GET /repos/{owner}/{repo}/pages 404s](https://github.com/orgs/community/discussions/24604)）。GitHub Pages の情報を返す[エンドポイント](/glossary/エンドポイント/)で404が出続けるという報告に対し、repo scope を持つ[トークン](/glossary/トークン/)で[認証](/glossary/認証/)したら取得できたという検証結果が寄せられています。当時のリファレンスには追加の[権限](/glossary/権限/)が不要と読める記載があり、[認証](/glossary/認証/)すれば通るという事実に報告者たちがなかなか到達できなかった経過が記録されています。また、組織で SSO（シングルサインオン）を使っている環境では、[トークン](/glossary/トークン/)を組織に対して承認することで解決したという報告も含まれています。2024年時点でも同様の報告が続いており、404の正体が[権限](/glossary/権限/)だったという本記事の原因3の典型例です。

GitHub [API](/glossary/api/) の404は、存在と[権限](/glossary/権限/)を意図的に区別しない設計であるぶん、調査する側の手順が重要になります。[URL](/glossary/url/) の綴りを何度も見直す前に、[トークン](/glossary/トークン/)の生死と[権限](/glossary/権限/)を先に確かめることが確実な近道です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*