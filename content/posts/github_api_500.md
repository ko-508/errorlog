---
title: "GitHub API の 500 エラー：原因と解決策"
date: 2026-01-01
description: "GitHub API の 500 Internal Server Error は、GitHub 側の内部で予期しないエラーが起きたことを示します。認証・権限・レート制限の問題では500は返りません。原因は GitHub 側の一時的な障害か、特定のリクエストが毎回踏む不具合かの2系統で、散発か再現かの見極めと x-github-request-id の控えが対処の起点です。"
tags: ["GitHub API"]
errorCode: "500"
lastmod: 2026-07-15
service: "GitHub API"
error_type: "500"
components: ["REST API"]
related_services: ["GitHub REST API", "GitHub GraphQL API", "Octokit"]
trend_incident: false
---

## 冒頭まとめ

GitHub API の 500 Internal Server Error は、リクエストの綴りや認証の問題ではなく、GitHub 側の内部で予期しないエラーが起きたことを示すコードです。クライアント側に起因する問題には別のコードが割り当てられており（トークンの不備は 401、レート制限は 403 または 429、不存在や権限不足は 404、入力の検証エラーは 422）、これらが500として返ることはありません。原因は2系統に整理できます。第一に、GitHub 側の一時的な障害や内部エラーで、散発的に発生し、同じリクエストをやり直すと通ります。大半はこちらです。第二に、特定のリクエストが GitHub 側の不具合を毎回踏んでいるケースで、同じ呼び出しだけが何度でも500になります。

対処もこの2系統で決まります。散発なら、稼働状況の確認と、間隔を空けた再試行です。再現するなら、リクエストを最小化して引き金を特定し、応答に必ず含まれる x-github-request-id を添えて報告します。手元のコードの修正で500が直るのは、この引き金を特定して回避できた場合に限られます。500の調査は「散発か、再現か」の見極めから始めます。

## エラーの概要

GitHub の API は、クライアント側で対処すべき問題を 4xx 系の各コードに割り当てる設計です。500 は、その割り当てのどれにも該当しない「GitHub 内部の予期しない失敗」を意味します。応答から得られる手がかりは多くありませんが、1つだけ確実なものがあります。GitHub API のすべての応答には x-github-request-id ヘッダーが含まれます（実測で確認できます）。

```bash
$ curl -sI https://api.github.com/repos/<owner>/<repo> | grep -i x-github-request-id
x-github-request-id: C005:2D15D8:A1B83BD:2375C5CD:6A57385F
```

この値は、GitHub 側のログでそのリクエストを一意に特定するための参照 ID です。500が続く場合の報告と調査の起点になるため、失敗した応答のこのヘッダーを控えておきます。GraphQL API では、参照 ID がエラーメッセージの本文中に埋め込まれて返ることがあり、その扱いは [GitHub API の 502 の記事](/posts/github_api_502/)で説明したものと同じです。

## まず最初に：散発か再現かを見極める

500を受け取ったら、コードを変更する前に次の3点を確認します。

第一に、GitHub の稼働状況ページ（https://www.githubstatus.com）を確認します。API のインシデントが進行中なら、原因は自分のリクエストではありません（原因1）。掲載が遅れることもあるため、掲載がないことは障害でないことの証明にはなりません。

第二に、同じリクエストを1回だけ再実行します。通れば散発（原因1）、また500なら再現（原因2）の疑いです。ただし作成・更新・削除の操作は、応答が届かなかっただけで処理自体は完了している可能性を排除できないため、再実行の前に対象（Issue やコメントなど）が実際に作られていないかを確認し、二重実行を避けてください。

第三に、失敗した応答の x-github-request-id と発生時刻を控えます。

## よくある原因と解決手順

### 原因1：GitHub 側の一時的な障害・内部エラー

GitHub 側のインフラに問題が起きている間は、正しいリクエストでも500が返ります。稼働状況ページに該当のインシデントが掲載されていれば、手元での対処はなく、復旧を待って再試行します。短時間に散発的な500が集中する場合も、まずこの系統を疑います。

再試行の設計には、GitHub 公式の Octokit の retry プラグインの線引きがそのまま使えます。公式の説明のとおり、このプラグインは500を含むサーバー側エラーを再試行の対象とし（500応答なら最大3回）、400・401・403・404・410・422・451 は再試行しません。つまり GitHub 公式のツールにおいても、500は「待ってやり直す価値があるコード」、上記の 4xx は「やり直しても結果が変わらないコード」という扱いです。自前で再試行を書く場合もこの線引きに従います。

**Before（間隔なしの固定リトライ。障害中の GitHub に負荷をかけ、自分のレート制限も消費する）：**

```python
import requests

def get_with_retry(url, headers):
    while True:  # 無限に即時リトライ
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            return r
```

**After（指数バックオフと回数上限。再試行は読み取り系と500系に限定する）：**

```python
import requests
import time

def get_with_retry(url, headers, max_retries=3):
    for attempt in range(max_retries + 1):
        r = requests.get(url, headers=headers)
        if r.status_code < 500:
            return r  # 4xx は再試行しても結果が変わらないため、そのまま返して原因調査へ
        if attempt < max_retries:
            wait = 2 ** attempt  # 1, 2, 4 秒と間隔を広げる
            print(f"HTTP {r.status_code} (request-id: {r.headers.get('x-github-request-id')}), "
                  f"retrying in {wait}s")
            time.sleep(wait)
    return r
```

作成・更新・削除をこの仕組みに乗せる場合は、再試行の前に対象の存在確認を挟み、二重実行を防ぎます。

### 原因2：特定のリクエストが毎回500になる

稼働状況が正常で、他のリクエストは通るのに、特定の呼び出しだけが何度でも500になる場合は、そのリクエストが GitHub 側の不具合を踏んでいる状態です。不具合そのものは手元で直せませんが、引き金の特定と回避はできます。

やり方は最小化です。失敗するリクエストから、パラメータやフィールドを1つずつ削って通るかを試し、どの要素が500を引き起こすかを絞り込みます。

**Before（失敗する呼び出しをそのまま繰り返す）：**

```bash
curl -i -H "Authorization: Bearer <your-github-token>" \
  "https://api.github.com/repos/<owner>/<repo>/issues?state=all&sort=comments&direction=asc&per_page=100&page=50"
# → 何度実行しても 500
```

**After（要素を削って引き金を特定する）：**

```bash
# パラメータを最小にして通ることを確認
curl -i -H "Authorization: Bearer <your-github-token>" \
  "https://api.github.com/repos/<owner>/<repo>/issues"

# 削ったパラメータを1つずつ戻し、500が再発する要素を特定する
# 特定できたら、その要素を避ける（件数を減らす、並び替えを変える、範囲を分割する）
```

引き金が特定できれば、多くの場合はその要素を避けた形（取得の分割、別のパラメータ、別のエンドポイント）で目的を達成できます。要求が重すぎることが引き金の場合、GitHub は時間切れを 502 として返すことが多く、その場合の分割の考え方は [GitHub API の 502 の記事](/posts/github_api_502/)の原因2と共通です。回避できない場合は、控えておいた x-github-request-id・発生時刻・最小化したリクエストを添えて、GitHub のコミュニティ（https://github.com/orgs/community/discussions）またはサポート（https://support.github.com）に報告します。参照 ID があると、GitHub 側は該当リクエストを内部ログから直接特定できます。

## 補足：500ではない類似コード

500の原因として語られがちですが、GitHub の公式仕様では別のコードが割り当てられている問題があります。トークンの誤り・失効は 401 Unauthorized（Bad credentials）です（[401 の記事](/posts/github_api_401/)）。レート制限の超過は 403 または 429 で、x-ratelimit-remaining ヘッダーが 0 になります（[403 の記事](/posts/github_api_403/)、[429 の記事](/posts/github_api_429/)）。リソースが存在しない、または権限がない場合は、classic トークンのスコープ不足を含めて 404 です（[404 の記事](/posts/github_api_404/)）。リクエスト本文の検証エラーや必須パラメータの不足は 422 です（[400 の記事](/posts/github_api_400/)）。つまり「JSON の形式が悪いから500」「レート制限を超えたから500」という説明は GitHub の仕様に合いません。また、応答の生成が時間内に終わらない場合は 502 や 504 で、特に GraphQL の重いクエリの時間切れは 502 として現れます（[502 の記事](/posts/github_api_502/)）。受け取ったコードがこれらであれば、500の調査ではなく、それぞれの原因の調査に切り替えてください。

## 切り分けの順序

1. 応答のコードを確認する。401・403・429・404・422・502なら、それぞれの記事の調査に切り替える。
2. 稼働状況ページを確認する。インシデント中なら復旧を待って再試行する（原因1）。
3. 同じリクエストを1回だけ再実行し、散発か再現かを見極める。書き込み系は二重実行の確認を先に行う。
4. 散発なら、指数バックオフと回数上限つきの再試行を実装する（原因1）。
5. 再現するなら、リクエストを最小化して引き金を特定し、回避する。回避できなければ x-github-request-id を添えて報告する（原因2）。

## 確認コマンド集

```bash
# 1. 応答のコードと参照 ID を確認
curl -i -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/repos/<owner>/<repo> 2>&1 | grep -iE "^HTTP|x-github-request-id"

# 2. レート制限の状態を確認（このエンドポイントは利用枠を消費しない）
curl -s -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/rate_limit

# 3. 認証なしの最小リクエストで疎通を確認（対象が public の場合）
curl -s -o /dev/null -w "%{http_code}\n" https://api.github.com/repos/<owner>/<repo>

# 4. 失敗するリクエストのパラメータを削って最小化し、引き金を特定する
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer <your-github-token>" \
  "https://api.github.com/repos/<owner>/<repo>/issues"
```

## Editor's Note

原因1の実例として、GitHub 自身が公開した記録があります（[GitHub availability report: March 2026](https://github.blog/news-insights/company-news/github-availability-report-march-2026/)）。2026年3月3日、18:46 から 20:09 UTC にかけて github.com と API を含む広い範囲で可用性が低下し、公式レポートによればピーク時には API リクエストの約43%が失敗しました。原因はユーザー設定のキャッシュ機構への大量の書き込みで、2月上旬に起きたインシデントと同じ根です。レポートには、この機構への killswitch の追加、監視の強化、機構の専用ホストへの分離という再発防止策まで記載されています。執筆時点から4か月前の直近の事例であり、「正しいリクエストでも失敗する時間帯は現実にあり、その間に手元でできるのは待つことと安全な再試行だけ」という原因1の構図をそのまま示しています。GitHub は月次の可用性レポートでインシデントの原因まで公開しているため、手元のログで500が特定の日時に集中していた場合、その日付のレポートで裏が取れることも覚えておくと役に立ちます。

500は応答から得られる手がかりが最も少ないコードですが、やるべきことは「散発か再現か」の見極めと x-github-request-id の控えだけで決まります。手元のリクエストの体裁を疑い始める前に、まず稼働状況と再現性を確認することが確実な近道です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*