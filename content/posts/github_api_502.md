---
title: "GitHub API の 502 エラー：原因と解決策"
date: 2026-01-01
description: "GitHub API の 502 Bad Gateway は、GitHub 側が時間内に応答を作れなかったことを示します。原因は GitHub 側の一時的な障害か、処理が重すぎる時間切れ（特に GraphQL の大きなクエリ）の2系統です。認証やレート制限の問題では502は返りません。稼働状況の確認とクエリの分割で解決します。"
tags: ["GitHub API"]
errorCode: "502"
lastmod: 2026-07-11
service: "GitHub API"
error_type: "502"
components: []
related_services: []
trend_incident: true
top_queries:
- 'github 502'
- 'github 502 bad gateway'
- 'github api 502'
---

## 冒頭まとめ

GitHub [API](/glossary/api/) の 502 Bad Gateway は、[リクエスト](/glossary/リクエスト/)の綴りや[認証](/glossary/認証/)の問題ではなく、GitHub 側が時間内に応答を作れなかったことを示すコードです。原因は2系統に整理できます。第一に、GitHub 側の一時的な障害やインシデントです。この場合、手元でできることは稼働状況の確認と、時間をおいた再試行しかありません。第二に、[リクエスト](/glossary/リクエスト/)の処理が重すぎて時間切れになるケースで、特に [GraphQL](/glossary/graphql/) [API](/glossary/api/) で複雑な[クエリ](/glossary/クエリ/)や大量のデータを一度に要求したときに頻発します。こちらは、取得件数を減らす・[クエリ](/glossary/クエリ/)を分割するという自衛策が有効です。

逆に、[トークン](/glossary/トークン/)の不備は 401、[レート制限](/glossary/レート制限/)の超過は 403 または 429、リソースの不存在や権限不足は 404 として返るのが GitHub の仕様であり、これらが502の原因になることはありません。502の調査は、稼働状況と「操作の重さ」の2点から始めます。

## エラーの概要

502 Bad Gateway は、GitHub の内部で応答の生成に失敗した、または間に合わなかったことを示します。[GraphQL](/glossary/graphql/) [API](/glossary/api/) の場合、実際の報告例に共通する特徴的な応答本文があります。

```json
{
  "data": "null",
  "errors": [
    {
      "message": "Something went wrong while executing your query. This may be the result of a timeout, or it could be a GitHub bug. Please include `XXXX:XXXX:XXXXXXX:XXXXXXX:XXXXXXXX` when reporting this issue."
    }
  ]
}
```

message 内のバッククォートで囲まれた文字列は、その[リクエスト](/glossary/リクエスト/)を特定するための参照 [ID](/glossary/id/) です。GitHub サポートやコミュニティへ報告する際に必要になるため、502が続く場合は控えておきます。文言にあるとおり、この応答は時間切れ（timeout）の可能性を GitHub 自身が示しています。なお、ブラウザの GitHub 上で同種の問題が起きた場合は「We couldn't respond to your request in time.」という表示になり、これも「時間内に応答できなかった」という同じ状態を指します。

## まず最初に：稼働状況と操作の重さを確認する

502を受け取ったら、コードを変更する前に次の3点を確認します。

第一に、GitHub の稼働状況ページ（https://www.githubstatus.com）を確認します。API のインシデントやメンテナンスが進行中なら、原因は自分の[リクエスト](/glossary/リクエスト/)ではありません（原因1）。

第二に、失敗した操作の重さを確認します。大きな[リポジトリ](/glossary/リポジトリ/)への複雑な [GraphQL](/glossary/graphql/) [クエリ](/glossary/クエリ/)、一度に大量のデータを要求する取得、巨大な本文を伴う作成・更新ではないか。同じ操作を小さくして（取得件数を減らして、本文を短くして）試すと通る場合、時間切れが原因です（原因2）。

第三に、応答本文の参照 [ID](/glossary/id/) を控えます。障害でも時間切れでもなさそうな502が続くときの、報告と調査の起点になります。

## よくある原因と解決手順

### 原因1：GitHub 側の一時的な障害・インシデント

GitHub 側の[インフラ](/glossary/インフラ/)に問題が起きている間は、正しい[リクエスト](/glossary/リクエスト/)でも502が返ります。稼働状況ページに該当のインシデントが掲載されていれば、手元での対処はなく、復旧を待って再試行します。掲載が遅れることもあるため、掲載がないことは障害でないことの証明にはなりません。散発的な502が短時間に集中する場合も、まずこの系統を疑います。

再試行の際は操作の種類に注意が必要です。データを読み取るだけの[リクエスト](/glossary/リクエスト/)は、何度実行しても同じなので安心して再試行できます。一方、作成・更新・削除の操作で502を受け取った場合、手元に応答が届かなかっただけで、処理自体は GitHub 側で完了している可能性を排除できません。再試行の前に、対象（Issue やコメントなど）が実際に作られていないかを確認し、二重実行を避けてください。

### 原因2：処理が重すぎて時間内に応答を作れない

GitHub が処理に時間をかけすぎた[リクエスト](/glossary/リクエスト/)は、時間切れとして502になります。実際の報告が集中しているのは [GraphQL](/glossary/graphql/) [API](/glossary/api/) です。GitHub 公式コミュニティでは、大きな[リポジトリ](/glossary/リポジトリ/)の pull request 一覧を大量のフィールド付きで辿る[クエリ](/glossary/クエリ/)が断続的に502になる報告に対し、GitHub 側から、対象[リポジトリ](/glossary/リポジトリ/)が大きいため[クエリ](/glossary/クエリ/)が時間切れになることがある、1回の[クエリ](/glossary/クエリ/)で要求するリソースを減らし、より多くの回数に分けるべきだという回答が示されています。

対処は要求の分割と縮小です。

**Before（一度に大量のデータを要求して時間切れになりやすい[クエリ](/glossary/クエリ/)）：**

```graphql
query {
  repository(owner: "<owner>", name: "<repo>") {
    pullRequests(first: 100) {
      nodes {
        number
        title
        commits(first: 100) { totalCount }
        files(first: 100) { nodes { path } }
        comments(first: 100) { nodes { body } }
      }
    }
  }
}
```

**After（取得件数を絞り、ページングで複数回に分ける）：**

```graphql
query ($cursor: String) {
  repository(owner: "<owner>", name: "<repo>") {
    pullRequests(first: 20, after: $cursor) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        title
      }
    }
  }
}
```

要点は3つです。first の値を小さくする、1つの[クエリ](/glossary/クエリ/)で同時に辿るネストした一覧（commits と files と comments を全部など）を減らす、続きは pageInfo のカーソルを使って別の[リクエスト](/glossary/リクエスト/)で取る、です。作成・更新（mutation）でも、巨大な本文を1回で送ると同じ時間切れが起きるため、入力を分割します。時間切れは対象データの量や混雑に左右されるため、同じ[リクエスト](/glossary/リクエスト/)が通ったり失敗したりと安定しないのもこの原因の特徴です。失敗が再現しないからといって解決したとは限らず、要求量を減らすことが根本の対処になります。

## 補足：502ではない類似コード

502の原因として語られがちですが、GitHub の公式仕様では別のコードが割り当てられている問題があります。[トークン](/glossary/トークン/)の誤り・失効は 401 Unauthorized（Bad credentials）です（[401 の記事](/posts/github_api_401/)）。[レート制限](/glossary/レート制限/)の超過は 403 または 429 で、x-ratelimit-remaining [ヘッダー](/glossary/ヘッダー/)が 0 になり、retry-after や x-ratelimit-reset [ヘッダー](/glossary/ヘッダー/)に従って待つのが公式の指示です（[403 の記事](/posts/github_api_403/)、[429 の記事](/posts/github_api_429/)）。リソースが存在しない、または[権限](/glossary/権限/)がない場合は 404 です（[404 の記事](/posts/github_api_404/)）。受け取ったコードがこれらであれば、502の調査ではなく、それぞれの原因の調査に切り替えてください。

## 切り分けの順序

1. 応答のコードを確認する。401・403・429・404なら、それぞれの記事の調査に切り替える。
2. 稼働状況ページを確認する。インシデント中なら復旧を待って再試行する（原因1）。書き込み系の再試行は、二重実行の確認を先に行う。
3. 操作の重さを確認する。取得件数や本文を小さくして通るなら時間切れであり、分割・縮小で恒久対処する（原因2）。
4. どちらにも該当せず502が続く場合は、応答本文の参照 [ID](/glossary/id/) を控え、GitHub のコミュニティまたはサポートに報告する。

## 確認コマンド集

```bash
# 1. 応答のコードとヘッダーを確認
curl -i -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/repos/<owner>/<repo>

# 2. レート制限の状態を確認（このエンドポイントは利用枠を消費しない）
curl -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/rate_limit

# 3. GraphQL クエリを最小構成で送り、通るかを確認
curl -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/graphql \
  -d '{"query":"query { viewer { login } }"}'

# 4. 失敗した応答から参照 ID とメッセージを取り出す（jq 使用時）
curl -s -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/graphql -d @query.json | jq '.errors[].message'
```

## Editor's Note

原因2の実例として、GitHub 公式コミュニティの議論があります（[Something went wrong while executing your query](https://github.com/orgs/community/discussions/24631)）。アプリの[リリース](/glossary/リリース/)作業を自動化するワークフローの中で、[マージ](/glossary/マージ/)された全 pull request のコミットハッシュ一覧を本文に含む議論スレッドを [GraphQL](/glossary/graphql/) の mutation で作成しようとしたところ、時間切れを示す例の502応答が返り続けたという報告です。他の参加者からは、複雑で大量のデータを扱う[クエリ](/glossary/クエリ/)で同じ問題を経験しており、量を減らしてページングで分割するのが対処だという助言が寄せられ、報告者自身も最終的に、本文が大きすぎて時間内に応答できなかったのが原因であり、[リクエスト](/glossary/リクエスト/)を分割する必要があると結論づけています。なお報告者は制限時間を10秒と述べていますが、これは報告者側の観測に基づく値であり、公式文書に明記された数値ではない点に注意してください。

502は「GitHub が応答を作れなかった」という結果だけを伝えるコードです。自分の[リクエスト](/glossary/リクエスト/)の綴りを疑う前に、稼働状況と要求の重さという2つの観点で切り分けることが確実な近道です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*