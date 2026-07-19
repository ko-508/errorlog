---
title: "GitHub API の 403 エラー：原因と解決策"
date: 2026-01-01
description: "GitHub API の 403 Forbidden が返るのは主に3つの場面です。レート制限の超過、GitHub App・fine-grained トークン・Actions の GITHUB_TOKEN の権限不足（Resource not accessible by integration）、組織の SAML SSO 未承認。classic トークンの権限不足は403ではなく404になります。message の文言から切り分けて解決します。"
tags: ["GitHub API"]
errorCode: "403"
lastmod: 2026-07-11
service: "GitHub API"
error_type: "403"
components: ["Actions"]
related_services: []
trend_incident: true
top_queries:
- 'github api 403'
- 'http 403: resource not accessible by personal access token (https://api.github.com/user/keys?per_page=100)'
- 'resource not accessible by integration'
---

## 冒頭まとめ

GitHub [API](/glossary/api/) の 403 Forbidden は、「[権限](/glossary/権限/)が足りないとき全般」に返るコードではありません。GitHub は、非公開リソースへの権限不足に対しては存在を隠すために 404 を返す設計であり、classic の personal access token の scope 不足も 404 になります。403 が返るのは、主に次の3つの場面です。第一に、[レート制限](/glossary/レート制限/)の超過（403 または 429）。第二に、GitHub App・fine-grained personal access token・Actions の GITHUB_TOKEN の権限不足で、この場合だけ Resource not accessible by integration（または by personal access token）という固有の文言が返ります。第三に、組織が SAML SSO（組織のシングルサインオン）を強制していて、[トークン](/glossary/トークン/)がその組織に対して未承認の場合です。

3つの場面はいずれも応答の message の文言で即座に見分けられます。403 の調査は、設定を触る前に message を読むことから始めます。

## エラーの概要

403 は「[リクエスト](/glossary/リクエスト/)は理解したが、実行を拒否した」ことを示すコードです。GitHub [API](/glossary/api/) では、拒否の理由が message に明示されるため、文言がそのまま調査の入口になります。実際の403応答の例です。

```json
{
  "message": "Resource not accessible by integration",
  "documentation_url": "https://docs.github.com/rest/repos/contents#create-or-update-file-contents"
}
```

見落とされやすいのが 404 との役割分担です。公式のトラブルシューティング文書のとおり、classic [トークン](/glossary/トークン/)の scope 不足や非公開[リポジトリ](/glossary/リポジトリ/)への無権限アクセスは、403 ではなく 404 Not Found として返ります。一方、GitHub App や fine-grained [トークン](/glossary/トークン/)の権限不足は 403 の Resource not accessible 系として返ります。つまり同じ「[権限](/glossary/権限/)が足りない」でも、[トークン](/glossary/トークン/)の種類によって受け取るコードが変わります。403 を受け取ったという事実自体が、原因の範囲をすでに絞り込んでいます。

## まず最初に：message を読んで3つに分岐する

[API](/glossary/api/) rate limit exceeded、または You have exceeded a secondary rate limit という文言なら、[レート制限](/glossary/レート制限/)の超過です（原因1）。応答[ヘッダー](/glossary/ヘッダー/)の x-ratelimit-remaining が 0 になっているはずです。

Resource not accessible by integration、または Resource not accessible by personal access token なら、GitHub App・fine-grained [トークン](/glossary/トークン/)・Actions の GITHUB_TOKEN の権限不足です（原因2）。

Resource protected by organization SAML enforcement なら、組織の SAML SSO に対する[トークン](/glossary/トークン/)の承認が済んでいません（原因3）。

これらのどれでもなく、[権限](/glossary/権限/)の問題を疑っているのに 404 が返っている場合は、classic [トークン](/glossary/トークン/)の scope や非公開リソースへの[アクセス権](/glossary/アクセス権/)の問題です（[404 の記事](/posts/github_api_404/)）。認証自体の失敗（Bad credentials）は 401 です（[401 の記事](/posts/github_api_401/)）。

## よくある原因と解決手順

### 原因1：レート制限の超過

公式ドキュメントのとおり、[レート制限](/glossary/レート制限/)（primary）を超えると 403 または 429 が返り、x-ratelimit-remaining [ヘッダー](/glossary/ヘッダー/)が 0 になります。短時間の集中的なアクセスを抑える別枠の制限（secondary）もあり、こちらは超過した旨のメッセージ（You have exceeded a secondary rate limit）で見分けられます。

対処も公式ドキュメントに明確な指針があります。retry-after [ヘッダー](/glossary/ヘッダー/)があれば、その秒数が経過するまで再試行しない。x-ratelimit-remaining が 0 なら、x-ratelimit-reset [ヘッダー](/glossary/ヘッダー/)が示す時刻（UTC の epoch 秒）まで再試行しない。どちらもなければ最低1分待つ。secondary の超過が続く場合は、待ち時間を指数的に増やしながら再試行し、一定回数で打ち切る、というものです。

現在の状態は、利用枠を消費しない専用[エンドポイント](/glossary/エンドポイント/)で確認できます。

```bash
curl -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/rate_limit
```

自分に適用されている上限そのものは、通常の応答の x-ratelimit-limit [ヘッダー](/glossary/ヘッダー/)にも表示されます。上限の具体的な値は認証方法によって異なり、変更されることもあるため、この実測値と公式の[レート制限](/glossary/レート制限/)ドキュメントで確認してください。未認証の[リクエスト](/glossary/リクエスト/)は認証済みより大幅に低い上限が適用されるため、繰り返し呼び出すプログラムでは[認証](/glossary/認証/)を付けることが第一の対策になります。

### 原因2：GitHub App・fine-grained トークン・GITHUB_TOKEN の権限不足

公式のトラブルシューティング文書に明記されているとおり、Resource not accessible by integration または Resource not accessible by personal access token という403は、GitHub App の[トークン](/glossary/トークン/)または fine-grained personal access token の[権限](/glossary/権限/)（permissions）が、その[エンドポイント](/glossary/エンドポイント/)の要求に足りないことを意味します。

必要な[権限](/glossary/権限/)は推測しなくて済みます。この403応答には X-Accepted-GitHub-Permissions という[ヘッダー](/glossary/ヘッダー/)が付き、その[エンドポイント](/glossary/エンドポイント/)に必要な[権限](/glossary/権限/)の一覧が示されるからです。

```bash
curl -i -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/repos/<owner>/<repo>/contents/<path>

# 応答ヘッダーの例:
# X-Accepted-GitHub-Permissions: contents=read
```

この例なら、[トークン](/glossary/トークン/)に contents の read [権限](/glossary/権限/)が必要という意味です。複数の組み合わせで満たせる場合は、セミコロン区切りで複数の一覧が示されます。[ヘッダー](/glossary/ヘッダー/)で特定した[権限](/glossary/権限/)を、fine-grained [トークン](/glossary/トークン/)なら設定画面の Repository permissions で、GitHub App なら App の権限設定とインストール先で付与します。[権限](/glossary/権限/)の種類だけでなく、[トークン](/glossary/トークン/)の対象範囲に該当[リポジトリ](/glossary/リポジトリ/)が含まれているかも確認してください。

GitHub Actions の中でこの403が出る場合、使われているのは自動発行の GITHUB_TOKEN です。この[トークン](/glossary/トークン/)の[権限](/glossary/権限/)は workflow [ファイル](/glossary/ファイル/)の permissions ブロックで決まり、書き込みが必要な操作（[ファイル](/glossary/ファイル/)の作成、[リリース](/glossary/リリース/)の作成、pull request へのコメントなど）には明示的な付与が必要です。

```yaml
permissions:
  contents: write
  pull-requests: write
```

なお、同じ権限不足でも classic [トークン](/glossary/トークン/)なら404が返るため、「404 ではなく 403 が返っている」こと自体が、App 系・fine-grained 系の[トークン](/glossary/トークン/)を使っているという手がかりになります。

### 原因3：組織の SAML SSO に対する承認が済んでいない

組織が SAML SSO を強制している場合、その組織のリソースにアクセスするには、[トークン](/glossary/トークン/)自体を組織に対して承認しておく必要があります。未承認の[トークン](/glossary/トークン/)でアクセスすると、次の文言の403が返ります。

```json
{
  "message": "Resource protected by organization SAML enforcement. You must grant your Personal Access token access to this organization.",
  "documentation_url": "https://docs.github.com/articles/authenticating-to-a-github-organization-with-saml-single-sign-on/"
}
```

応答[ヘッダー](/glossary/ヘッダー/)には X-GitHub-Sso が付き、承認のための [URL](/glossary/url/) が示される場合もあります。対処は、GitHub の設定画面（Settings > Developer settings > Personal access tokens）で対象[トークン](/glossary/トークン/)の Configure SSO から該当組織を承認することです。応答本文の documentation_url が公式の手順を直接指しているので、そのまま参照できます。組織側で SSO を有効化した直後から、それまで動いていた[トークン](/glossary/トークン/)が一斉にこの403を返し始める、という形で現れるのが典型です。

## 切り分けの順序

1. 応答の message を読む。レート制限系・Resource not accessible 系・SAML enforcement 系のどれかを確定する。どれでもなければ、404（scope・[アクセス権](/glossary/アクセス権/)）や 401（[認証](/glossary/認証/)）の問題として切り替える。
2. レート制限系なら、retry-after と x-ratelimit-reset に従って待つ。恒久対処として、[認証](/glossary/認証/)の付与と呼び出し回数の削減を検討する。
3. Resource not accessible 系なら、X-Accepted-GitHub-Permissions [ヘッダー](/glossary/ヘッダー/)で必要権限を特定し、[トークン](/glossary/トークン/)（fine-grained・App・GITHUB_TOKEN）側に付与する。対象[リポジトリ](/glossary/リポジトリ/)が範囲に含まれているかも確認する。
4. SAML enforcement 系なら、[トークン](/glossary/トークン/)を組織に対して承認する。

## 確認コマンド集

```bash
# 1. 応答の message とヘッダーをまとめて確認
curl -i -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/repos/<owner>/<repo>

# 2. レート制限の状態を確認（このエンドポイントは利用枠を消費しない）
curl -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/rate_limit

# 3. 403応答から必要権限のヘッダーを抽出
curl -si -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/repos/<owner>/<repo>/contents/<path> \
  | grep -i "x-accepted-github-permissions\|x-github-sso\|x-ratelimit"

# 4. トークンの認証自体が生きているかを確認（401なら別問題）
curl -i -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/user
```

## Editor's Note

原因2の実例として、GitHub 公式コミュニティの議論があります（[Resource not accessible by integration on GitHub App](https://github.com/orgs/community/discussions/108369)、2024年）。GitHub App の[トークン](/glossary/トークン/)で、[ファイル](/glossary/ファイル/)の存在確認などの読み取りは通るのに、[リポジトリ](/glossary/リポジトリ/)への workflow [ファイル](/glossary/ファイル/)（.github/workflows/ 配下）の作成だけが Resource not accessible by integration の403で失敗するという報告です。報告者は App に適切な[権限](/glossary/権限/)を与えたつもりでしたが、最終的に、App の権限設定で workflow の[権限](/glossary/権限/)を選択していなかったことが原因だったと自己解決しています。読み取りが通ることと書き込みが通ることは別の[権限](/glossary/権限/)であり、操作ごとに必要な[権限](/glossary/権限/)が異なる、という原因2の要点をそのまま示す記録です。今であれば、応答の X-Accepted-GitHub-Permissions [ヘッダー](/glossary/ヘッダー/)を見ることで、この特定にかかった往復を省略できます。

GitHub の 403 は、文言が原因を名指ししてくれる親切な[エラー](/glossary/エラー/)です。コードの数字だけを見て権限全般を疑い始める前に、message と[ヘッダー](/glossary/ヘッダー/)を読むことが確実な近道です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*