---
title: "GitHub API の 504 エラー：原因と解決策"
date: 2026-01-01
description: "GitHub API の 504 Gateway Timeout は、GitHub が時間内に応答を作り終えられず、リクエストを打ち切ったことを示します。公式文書は処理が10秒を超えるリクエストを打ち切ると明記しています。原因は GitHub 側の障害か、リクエストが重すぎるかの2系統で、要求の縮小・分割と間隔を空けた再試行で解決します。認証やレート制限の問題では504は返りません。"
tags: ["GitHub API"]
errorCode: "504"
lastmod: 2026-07-15
service: "GitHub API"
error_type: "504"
components: ["REST API"]
related_services: ["GitHub REST API", "GitHub GraphQL API", "Octokit"]
trend_incident: false
---

## 冒頭まとめ

GitHub [API](/glossary/api/) の 504 Gateway Timeout は、GitHub が制限時間内に応答を作り終えられず、[リクエスト](/glossary/リクエスト/)を処理の途中で打ち切ったことを示すコードです。これは公式に明文化された挙動で、GitHub の公式文書（Troubleshooting the [REST](/glossary/rest/) [API](/glossary/api/)）は、処理が10秒を超える[リクエスト](/glossary/リクエスト/)を打ち切って[タイムアウト](/glossary/タイムアウト/)の応答と Server Error のメッセージを返すこと、そしてこの制限時間は [API](/glossary/api/) の速度と信頼性を守るために予告なく変更されうることを明記しています。原因は2系統に整理できます。第一に、GitHub 側の障害や混雑で、普段は通る[リクエスト](/glossary/リクエスト/)が散発的に時間切れになるケースです。第二に、[リクエスト](/glossary/リクエスト/)自体が重すぎて、平常時でも制限時間に収まらないケースです。

対処もこの公式文書がそのまま示しています。稼働状況を確認すること、要求を簡素化すること（1ページに100件を要求しているなら件数を減らす）、時間をおいて再試行することの3つです。逆に、[トークン](/glossary/トークン/)の不備は 401、[レート制限](/glossary/レート制限/)は 403 または 429、不存在や権限不足は 404 として返るのが GitHub の仕様であり、これらが504の原因になることはありません。また、手元の [HTTP](/glossary/http/) [クライアント](/glossary/クライアント/)に設定した[タイムアウト](/glossary/タイムアウト/)の発火は、GitHub からコードが返る前に手元で接続を打ち切る動きなので、504とは別の事象です。504の調査は、コードが本当に GitHub から返っているかの確認と、「散発か、重さ由来か」の見極めから始めます。

## エラーの概要

GitHub は [API](/glossary/api/) [リクエスト](/glossary/リクエスト/)の処理時間に上限を設けており、超過した[リクエスト](/glossary/リクエスト/)を自らの判断で打ち切ります。打ち切られた[リクエスト](/glossary/リクエスト/)への応答は次のような形になります。

```bash
$ curl -i -H "Authorization: Bearer <your-github-token>" \
  "https://api.github.com/repos/<owner>/<repo>/commits?per_page=100"
HTTP/2 504
...
{
  "message": "Server Error",
  "documentation_url": "https://docs.github.com/rest"
}
```

この Server Error という文言は、公式文書が[タイムアウト](/glossary/タイムアウト/)応答に伴うと明記しているメッセージです。なお、同じ「時間内に応答を作れなかった」状態は、経路や [API](/glossary/api/) の種類によって 502 として現れることもあります。特に [GraphQL](/glossary/graphql/) [API](/glossary/api/) の重い[クエリ](/glossary/クエリ/)の時間切れは、参照 [ID](/glossary/id/) 入りの[エラーメッセージ](/glossary/エラーメッセージ/)を伴う 502 の形の報告が多く、その扱いは [GitHub API の 502 の記事](/posts/github_api_502/)で説明しています。コードが502でも504でも、時間切れである限り、原因の見極め方と対処（縮小・分割・再試行）は共通です。

## まず最初に：3点を確認する

504を受け取ったら、コードを変更する前に次の3点を確認します。

第一に、そのコードが本当に GitHub から返っているかを確認します。手元の[クライアント](/glossary/クライアント/)の[タイムアウト](/glossary/タイムアウト/)（curl の --max-time、requests の timeout= など）が先に発火した場合、[ステータスコード](/glossary/ステータスコード/)は受け取れず、例外や接続打ち切りとして現れます。この場合の調査対象は GitHub ではなく、手元の設定と経路です。

第二に、GitHub の稼働状況ページ（https://www.githubstatus.com）を確認します。公式文書も、時間切れが [API](/glossary/api/) 側の問題によるものかをこのページで確認するよう案内しています。インシデントが進行中なら原因は自分の[リクエスト](/glossary/リクエスト/)ではありません（原因1）。掲載が遅れることもあるため、掲載がないことは障害でないことの証明にはなりません。

第三に、失敗した操作の重さを確認します。1ページあたりの取得件数（per_page）が大きい一覧取得、巨大な[リポジトリ](/glossary/リポジトリ/)の[コミット](/glossary/コミット/)履歴や差分の取得ではないか。同じ操作を小さくして試すと通る場合、重さ由来の時間切れです（原因2）。

## よくある原因と解決手順

### 原因1：GitHub 側の障害・混雑で時間内に処理が終わらない

GitHub 側の[インフラ](/glossary/インフラ/)に問題が起きている間は、普段は数秒で返る[リクエスト](/glossary/リクエスト/)でも制限時間を超え、504が返ります。稼働状況ページに該当のインシデントが掲載されていれば、手元での対処はなく、復旧を待って再試行します。普段は安定している操作の504が短時間に集中する場合も、まずこの系統を疑います。

再試行の設計は [GitHub API の 500 の記事](/posts/github_api_500/)の原因1と同じです。GitHub 公式の Octokit の retry プラグインは、504を含む[サーバー](/glossary/サーバー/)側[エラー](/glossary/エラー/)を再試行の対象とし、400・401・403・404・410・422・451 は再試行しません。自前で書く場合も、指数[バックオフ](/glossary/バックオフ/)と回数上限をつけ、再試行は 5xx に限定します。作成・更新・削除の操作で504を受け取った場合は、応答が届かなかっただけで処理自体は完了している可能性を排除できないため、再試行の前に対象が実際に作られていないかを確認し、二重実行を避けてください。

### 原因2：リクエストが重すぎて制限時間に収まらない

平常時でも特定の操作だけが504になる場合、その[リクエスト](/glossary/リクエスト/)の処理が制限時間に収まっていません。公式文書の指示は要求の簡素化で、例として挙げられているのもまさに「1ページに100件を要求しているなら、件数を減らす」ことです。

**Before（1回の[リクエスト](/glossary/リクエスト/)に最大件数を詰め込み、時間切れになりやすい）：**

```bash
curl -i -H "Authorization: Bearer <your-github-token>" \
  "https://api.github.com/repos/<owner>/<repo>/commits?per_page=100"
# 巨大なリポジトリでは、この1リクエストの処理が制限時間に収まらないことがある
```

**After（1ページの件数を減らし、ページングで回数に分ける）：**

```python
import requests

headers = {"Authorization": "Bearer <your-github-token>"}
url = "https://api.github.com/repos/<owner>/<repo>/commits"
params = {"per_page": 30}  # 1回あたりの要求を小さくする

commits = []
while url:
    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()
    commits.extend(r.json())
    # 続きは Link ヘッダーの next を辿る（2ページ目以降は params 不要）
    url = r.links.get("next", {}).get("url")
    params = None
```

要点は3つです。per_page を小さくする、続きは Link [ヘッダー](/glossary/ヘッダー/)のページングで別の[リクエスト](/glossary/リクエスト/)として取る、取得範囲を絞れる[パラメータ](/glossary/パラメータ/)（期間、[ブランチ](/glossary/ブランチ/)、[パス](/glossary/パス/)など、各[エンドポイント](/glossary/エンドポイント/)のリファレンス参照）で対象自体を減らす、です。時間切れは対象データの量や混雑に左右されるため、同じ[リクエスト](/glossary/リクエスト/)が通ったり失敗したりと安定しないのもこの原因の特徴です。失敗が再現しないからといって解決したとは限らず、要求量を減らすことが根本の対処になります。また、公式文書が制限時間の変更の権利を明記している以上、「現状ぎりぎり通る重さ」に依存した設計は避け、余裕を持って分割しておくのが安全です。

## 補足：504ではない類似エラー

504と混同されやすい事象の正しい行き先です。手元の[クライアント](/glossary/クライアント/)の[タイムアウト](/glossary/タイムアウト/)発火は、コードが返らずに例外や接続打ち切りとして現れるもので、GitHub の504ではありません（調査対象は手元の設定です）。[トークン](/glossary/トークン/)の誤り・失効は 401 です（[401 の記事](/posts/github_api_401/)）。並列や高頻度の大量[リクエスト](/glossary/リクエスト/)が弾かれる場合、GitHub の仕様では 403 または 429 の secondary rate limit として現れ、待ち時間の指示に従うのが公式の対処です（[403 の記事](/posts/github_api_403/)、[429 の記事](/posts/github_api_429/)）。「大量に送ったから504になった」という説明は、混雑による時間切れ（原因1の変種）でない限り仕様に合いません。private リソースへの認証不備は、権限不足を隠すための 404 です（[404 の記事](/posts/github_api_404/)）。GitHub 内部の予期しない[エラー](/glossary/エラー/)で、時間切れとは限らないものは 500 です（[500 の記事](/posts/github_api_500/)）。[GraphQL](/glossary/graphql/) の重い[クエリ](/glossary/クエリ/)の時間切れは 502 の形の報告が多く、分割の考え方は共通です（[502 の記事](/posts/github_api_502/)）。

## 切り分けの順序

1. コードが GitHub から返っているかを確認する。手元の[タイムアウト](/glossary/タイムアウト/)の発火なら、手元の設定と経路の調査に切り替える。
2. コードが 401・403・429・404・500・502 なら、それぞれの記事の調査に切り替える。
3. 稼働状況ページを確認する。インシデント中なら復旧を待って再試行する（原因1）。書き込み系の再試行は、二重実行の確認を先に行う。
4. 操作の重さを確認する。per_page を減らして通るなら重さ由来であり、縮小・分割・範囲指定で恒久対処する（原因2）。
5. どちらにも該当せず504が続く場合は、応答の x-github-request-id を控え、GitHub のコミュニティまたはサポートに報告する。

## 確認コマンド集

```bash
# 1. コードと所要時間を同時に確認（時間切れ付近かどうかの手がかり）
curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" \
  -H "Authorization: Bearer <your-github-token>" \
  "https://api.github.com/repos/<owner>/<repo>/commits?per_page=100"

# 2. 件数を減らした同じリクエストと比較（通れば重さ由来）
curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" \
  -H "Authorization: Bearer <your-github-token>" \
  "https://api.github.com/repos/<owner>/<repo>/commits?per_page=10"

# 3. 失敗した応答の参照 ID を控える（報告用）
curl -sI -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/repos/<owner>/<repo> | grep -i x-github-request-id

# 4. レート制限の状態を確認（このエンドポイントは利用枠を消費しない。
#    504の調査で大量に叩いていないかの確認にも使う）
curl -s -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/rate_limit
```

## Editor's Note

原因1の実例として、GitHub 自身が公開した記録があります（[GitHub availability report: June 2026](https://github.blog/news-insights/company-news/github-availability-report-june-2026/)）。2026年6月8日、06:30 から 08:36 UTC ごろにかけて、未[ログイン](/glossary/ログイン/)のユーザーが pull request・Issue・[リリース](/glossary/リリース/)・差分などの github.com のページにアクセスした際、持続的に [HTTP](/glossary/http/) 504 が返る状態になり、公式レポートによれば対象[エンドポイント](/glossary/エンドポイント/)への未認証[リクエスト](/glossary/リクエスト/)の約17%がゲートウェイタイムアウトになりました。これは api.github.com ではなく github.com のウェブ側の事例ですが、「入口のゲートウェイが、時間内に応答を作れなかった[リクエスト](/glossary/リクエスト/)を504として打ち切る」という機構そのものは、この記事で扱った [API](/glossary/api/) の504と同じです。執筆時点から1か月前の直近の事例であり、正しい[リクエスト](/glossary/リクエスト/)でも504が返る時間帯は現実にあること、そしてその原因と対策が月次の公式レポートで後から公開されることを示しています。手元の[ログ](/glossary/ログ/)で504が特定の日時に集中していた場合、その日付のレポートで裏が取れます。

504は「GitHub が時間切れで打ち切った」という一点だけを伝えるコードです。手元の[タイムアウト](/glossary/タイムアウト/)との区別、稼働状況、そして要求の重さ。この3つを順に確認すれば、コードをいじるべきか、待つべきか、分割すべきかが決まります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*