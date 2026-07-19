---
title: "GitHub API の 429 エラー：原因と解決策"
date: 2026-01-01
description: "GitHub API の 429 Too Many Requests には2種類あります。時間あたりの総量を超えた primary rate limit（x-ratelimit-remaining が 0）と、短時間の集中・並列に対する secondary rate limit（残量があっても発動）です。同じ超過が 403 で返ることもあります。ヘッダーの指示に従った正しい待ち方と、呼び出しを減らす公式の手法で解決します。"
tags: ["GitHub API"]
errorCode: "429"
lastmod: 2026-07-14
service: "GitHub API"
error_type: "429"
components: []
related_services: ["Personal Access Token", "GraphQL API", "REST API"]
trend_incident: true
---

## 冒頭まとめ

GitHub [API](/glossary/api/) の 429 Too Many Requests は、呼び出しの量が制限を超えたことを示します。重要なのは、制限が2種類あることです。第一に primary rate limit で、時間あたりの総量の上限です。これに達すると応答[ヘッダー](/glossary/ヘッダー/)の x-ratelimit-remaining が 0 になります。第二に secondary rate limit で、短時間の集中（大量の並列[リクエスト](/glossary/リクエスト/)、作成系操作の連打など）に対する保護です。こちらは残量が残っていても発動し、message に secondary rate limit という文言が入ります。なお、公式ドキュメントのとおり、同じ制限超過が 429 ではなく 403 で返ることもあります（対処は同じです）。

429 を受け取ったときにやってはいけないのが、待たずに再試行を繰り返すことです。対処の順序は、まず[ヘッダー](/glossary/ヘッダー/)の指示どおりに待つ、次に[認証](/glossary/認証/)を付けて上限を上げる、最後に呼び出しそのものを減らす（直列化・条件付き[リクエスト](/glossary/リクエスト/)・webhook への転換）、です。いずれも公式の指針が明確に定まっています。

## エラーの概要

2種類の 429 は、応答の message で見分けられます。

primary rate limit の超過（時間あたりの総量を使い切った場合）：

```json
{
  "message": "API rate limit exceeded for user ID <user-id>.",
  "documentation_url": "https://docs.github.com/rest/overview/rate-limits-for-the-rest-api"
}
```

secondary rate limit の超過（短時間の集中に対する保護）：

```json
{
  "message": "You have exceeded a secondary rate limit. Please wait a few minutes before you try again.",
  "documentation_url": "https://docs.github.com/rest/overview/rate-limits-for-the-rest-api"
}
```

あわせて読むべきなのが応答[ヘッダー](/glossary/ヘッダー/)です。x-ratelimit-limit が現在の自分の上限、x-ratelimit-remaining が残量、x-ratelimit-reset が残量の回復時刻（UTC の epoch 秒）、x-ratelimit-resource がどの区分（core、search、graphql など）の制限かを示します。retry-after [ヘッダー](/glossary/ヘッダー/)が付いている場合は、その秒数が最優先の待ち時間です。上限の具体的な数値は認証方法などで異なり、変更されることもあるため、この x-ratelimit-limit の実測値と公式の[レート制限](/glossary/レート制限/)ドキュメントで確認してください。

## まず最初に：ヘッダーで primary か secondary かを確定する

現在の状態は、利用枠を消費しない専用[エンドポイント](/glossary/エンドポイント/)でいつでも確認できます。

```bash
curl -H "Authorization: Bearer <your-github-token>" https://api.github.com/rate_limit
```

429 の応答[ヘッダー](/glossary/ヘッダー/)（または上記の出力）で x-ratelimit-remaining を見ます。0 なら primary の超過で、x-ratelimit-reset の時刻まで待つのが正解です（原因1・2）。残量があるのに 429 が出ているなら secondary で、待ったうえで呼び出しの「集中」を崩す必要があります（原因3）。どちらの場合も、恒久対処として呼び出し量そのものの削減（原因4）を検討します。

## よくある原因と解決手順

### 原因1：認証なし（または低い上限のまま）で呼び出している

公式ドキュメントのとおり、認証済みの[リクエスト](/glossary/リクエスト/)は未認証よりも大幅に高い primary の上限を持ちます。スクリプトや CI から未認証で繰り返し呼び出すと、すぐに上限に達します。しかも未認証の上限は接続元の [IP アドレス](/glossary/ip-アドレス/)単位で数えられるため、共有環境（CI サービスや社内[ネットワーク](/glossary/ネットワーク/)）では自分以外の利用と枠を取り合うことになります。

**Before（未認証で繰り返し呼び出す）：**

```bash
curl https://api.github.com/repos/<owner>/<repo>/issues
```

**After（[トークン](/glossary/トークン/)で[認証](/glossary/認証/)して呼び出す）：**

```bash
curl -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/repos/<owner>/<repo>/issues
```

まず[認証](/glossary/認証/)を付けることが、429 対策の最初の一手です。

### 原因2：待ち方が間違っている

429 を受け取った直後に再試行しても成功しません。公式ドキュメントは待ち方を3段階で定めています。第一に、retry-after [ヘッダー](/glossary/ヘッダー/)があれば、その秒数が経過するまで再試行しない。第二に、x-ratelimit-remaining が 0 なら、x-ratelimit-reset が示す時刻（UTC の epoch 秒）まで再試行しない。第三に、どちらもなければ最低1分待つ。それでも続く場合は待ち時間を指数的に増やし、一定回数で打ち切って[エラー](/glossary/エラー/)にする、というものです。[リセット](/glossary/リセット/)時刻は次のように人間が読める形にできます。

```bash
# 応答ヘッダーの x-ratelimit-reset の値（epoch 秒）を時刻に変換
date -d @<x-ratelimit-resetの値>
```

自動[リトライ](/glossary/リトライ/)を実装している場合は、この指針に沿っているかを確認してください。待たない連打は、状況を改善しないだけでなく、secondary の保護をさらに引き起こす方向に働きます。

### 原因3：短時間の集中・並列・作成の連打（secondary rate limit）

secondary rate limit は総量ではなく「勢い」への制限です。公式ドキュメントが引き金として挙げているのは、同時に送る[リクエスト](/glossary/リクエスト/)が多すぎる（この同時数の枠は [REST](/glossary/rest/) と [GraphQL](/glossary/graphql/) で共有）、単一の[エンドポイント](/glossary/エンドポイント/)に1分間に集中しすぎる、処理の重い[リクエスト](/glossary/リクエスト/)で CPU 時間を使いすぎる、短時間にコンテンツ（Issue、コメントなど）を作りすぎる（ウェブ画面での操作も合算されます）、といった類型です。個々のしきい値は公式に予告なく変更されるとされており、非公開の理由で発動する場合もあると明記されています。数値を当てにせず、挙動を設計で抑えるのが正攻法です。

公式の回避策は明確です。[リクエスト](/glossary/リクエスト/)は並列ではなく直列にする（必要ならキューを実装する）。作成・更新系の[リクエスト](/glossary/リクエスト/)（POST、PATCH、PUT、DELETE）を大量に行う場合は、1件ごとに1秒以上の間隔を空ける。この2つを守るだけで、secondary の大半は避けられます。並列で一括処理しているバッチやワークフローがあれば、そこが最初の見直し対象です。

### 原因4：変わらないデータを取得し続けている

定期的なポーリング（変化の監視のための繰り返し取得）は、内容が変わっていなくても枠を消費します。公式のベストプラクティスは2つの削減策を示しています。

第一に、条件付き[リクエスト](/glossary/リクエスト/)です。多くの[エンドポイント](/glossary/エンドポイント/)は応答に etag [ヘッダー](/glossary/ヘッダー/)（内容の指紋）を返し、last-modified を返すものもあります。次回の取得時に If-None-Match（または If-Modified-Since）[ヘッダー](/glossary/ヘッダー/)で前回の値を送ると、内容が変わっていなければ 304 Not Modified が返ります。公式ドキュメントのとおり、Authorization [ヘッダー](/glossary/ヘッダー/)付きで正しく[認証](/glossary/認証/)された[リクエスト](/glossary/リクエスト/)で 304 が返った場合、その取得は primary の制限を消費しません。

```bash
# 1回目: etag を控える
curl -si -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/repos/<owner>/<repo> | grep -i "^etag"

# 2回目以降: 変更がなければ 304 が返り、制限を消費しない
curl -si -H "Authorization: Bearer <your-github-token>" \
  -H 'If-None-Match: "<控えたetagの値>"' \
  https://api.github.com/repos/<owner>/<repo> | head -1
```

第二に、ポーリング自体をやめて webhook（変更時に GitHub 側から通知が届く仕組み）を購読することです。公式ベストプラクティスの筆頭に挙げられている方法で、変化のたびに知らせが来るため、確認のための取得が不要になります。

## 補足：429ではない類似エラー

同じ[レート制限](/glossary/レート制限/)の超過でも、403 Forbidden として返る場合があります（公式仕様。x-ratelimit-remaining が 0 か、message がレート制限系かで見分けられます。対処はこの記事と同じです。[403 の記事](/posts/github_api_403/)）。一方、Bad credentials の 401 は[トークン](/glossary/トークン/)自体の問題であり、[レート制限](/glossary/レート制限/)とは無関係です（[401 の記事](/posts/github_api_401/)）。

## 切り分けの順序

1. 応答[ヘッダー](/glossary/ヘッダー/)（または /rate_limit）で x-ratelimit-remaining を確認する。0 なら primary、残量があれば secondary。
2. retry-after があればその秒数、primary なら x-ratelimit-reset の時刻まで待つ。どちらもなければ最低1分。自動[リトライ](/glossary/リトライ/)は指数的な待ち時間と打ち切り回数を実装する。
3. 未認証の呼び出しが残っていないかを確認し、[認証](/glossary/認証/)を付ける。
4. 恒久対処として、並列の直列化、作成系操作の1秒以上の間隔、条件付き[リクエスト](/glossary/リクエスト/)（etag）、webhook への転換を、呼び出しの実態に合わせて導入する。

## 確認コマンド集

```bash
# 1. 現在の残量とリセット時刻を確認（このエンドポイントは利用枠を消費しない）
curl -H "Authorization: Bearer <your-github-token>" https://api.github.com/rate_limit

# 2. 429 応答のヘッダーをまとめて確認
curl -si -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/repos/<owner>/<repo> \
  | grep -iE "^(x-ratelimit|retry-after)"

# 3. リセット時刻を人間が読める形に変換
date -d @<x-ratelimit-resetの値>

# 4. 条件付きリクエストの動作確認（変更がなければ 304）
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer <your-github-token>" \
  -H 'If-None-Match: "<控えたetagの値>"' \
  https://api.github.com/repos/<owner>/<repo>
```

## Editor's Note

原因4の効果を数字で示した解説として、GitHub 公式コミュニティの議論があります（[Working with the GitHub API rate limit](https://github.com/orgs/community/discussions/189255)）。50個の[リポジトリ](/glossary/リポジトリ/)の pull request を5分おきに監視する例で、9割の確率で変更がないとすると、1時間600回の取得のうち540回が同じデータの取り直しに消えます。etag による条件付き[リクエスト](/glossary/リクエスト/)に切り替えると、取得の回数自体は600回のままでも、制限を消費するのは変更のあった約60回だけになる、という計算が示されています。あわせて実務上の注意も記録されています。etag はページ単位なので、ページ分割された一覧では1ページ目が 304 でも他のページが未変更とは限らないこと、[GraphQL](/glossary/graphql/) は etag に対応していないため、[GraphQL](/glossary/graphql/) の結果は[クエリ](/glossary/クエリ/)と[変数](/glossary/変数/)を鍵に自前で[キャッシュ](/glossary/キャッシュ/)する必要があること、通知系の[エンドポイント](/glossary/エンドポイント/)では応答の X-Poll-Interval [ヘッダー](/glossary/ヘッダー/)が示す間隔を守るべきことです。「呼び出しを減らす」の具体像として、そのまま設計の参考にできます。

429 は、応答の[ヘッダー](/glossary/ヘッダー/)が「いつまで待てばよいか」を毎回教えてくれる[エラー](/glossary/エラー/)です。感覚で待ち時間を決めたり連打で押し切ろうとしたりせず、[ヘッダー](/glossary/ヘッダー/)の指示に従い、そのうえで呼び出しの総量と勢いを設計で減らすことが確実な近道です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*