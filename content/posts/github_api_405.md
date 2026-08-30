---
title: "GitHub API の 405 エラー：原因と解決策"
date: 2026-07-26
description: "GitHub API の 405 Method Not Allowed は、HTTP メソッドの間違いではありません。公式 API 定義で 405 を返すと定義された操作は全1,209操作のうち3つだけで、実務で当たるのはプルリクエストのマージです。意味は「今はマージできない」で、原因は応答の message の文言で確定します。Base branch was modified だけが一時的で再試行が正解、他は状態を直すまで結果は変わりません。"
tags: ["GitHub API"]
errorCode: "405"
lastmod: 2026-07-26
service: "GitHub API"
error_type: "405"
components: ["REST API"]
related_services: ["GitHub REST API", "GitHub CLI", "GitHub Actions"]
trend_incident: false
---

## 冒頭まとめ

[GitHub](/glossary/github/) [API](/glossary/api/) の 405 Method Not Allowed は、名前から受ける印象と中身が食い違う[コード](/glossary/コード/)です。[HTTP](/glossary/http/) の[メソッド](/glossary/メソッド/)を間違えたという意味ではありません。[GitHub](/glossary/github/) 公式の [API](/glossary/api/) 定義（OpenAPI）で数えると、405 を応答として定義している操作は全1,209操作のうち3つしかなく、そのうち実務で当たるのは事実上1つ、プルリクエストの[マージ](/glossary/マージ/)（`PUT /repos/{owner}/{repo}/pulls/{pull_number}/merge`）です。この 405 に付けられた定義文は「[マージ](/glossary/マージ/)を実行できない場合」であり、意味は「[メソッド](/glossary/メソッド/)が違う」ではなく「今は[マージ](/glossary/マージ/)できない」です。

応答本文には、422 のような errors 配列がありません。公式定義でも message と documentation_url の2つだけです。つまり調査は、message の文言を読むことに尽きます。実際に記録されている文言は5系統に整理できます。[マージ](/glossary/マージ/)できる状態にない（Pull Request is not mergeable）、base [ブランチ](/glossary/ブランチ/)が動いた（Base branch was modified. Review and try the merge again.）、必須ステータスチェックが未完了、必要なレビューが足りない、その[ブランチ](/glossary/ブランチ/)へ push する[権限](/glossary/権限/)がない、の5つです。

[リトライ](/glossary/リトライ/)してよいかどうかも系統で分かれます。Base branch was modified だけが一時的な状態で、待って再試行するのが正しい対処です。残りは、状態を直さない限り何度送っても同じ結果になります。

境界を先に1つ引いておきます。[マージ](/glossary/マージ/)要求に sha を渡して head が一致しなかった場合は、405 ではなく 409（Head branch was modified. Review and try the merge again.）です。Base と Head の違いしかない文言で、[ステータスコード](/glossary/ステータスコード/)も対処も異なります。

## エラーの概要

公式 [API](/glossary/api/) 定義における[マージ](/glossary/マージ/)操作の 405 は、message と documentation_url を持つだけの単純な[スキーマ](/glossary/スキーマ/)で、例として示されている値は Pull Request is not mergeable です。実際の応答は次の形になります（[マージ](/glossary/マージ/)を[自動化](/glossary/自動化/)するボットが記録に残したもので、status は[クライアント](/glossary/クライアント/)側が付けた項目です）。

```json
{
  "message": "Base branch was modified. Review and try the merge again.",
  "documentation_url": "https://docs.github.com/rest/pulls/pulls#merge-a-pull-request",
  "status": "405"
}
```

もう1つ、先に否定しておくべき筋があります。「[メソッド](/glossary/メソッド/)を直せば解決する 405」は、[GitHub](/glossary/github/) [API](/glossary/api/) ではまず成り立ちません。2026年7月26日に未認証で実測したところ、GET だけを受け付ける[パス](/glossary/パス/)（`/users/octocat`）に DELETE・PUT・PATCH を送った場合、返るのは 405 ではなく 404 Not Found でした。[GitHub](/glossary/github/) [API](/glossary/api/) は、対応していない[メソッド](/glossary/メソッド/)の組み合わせを「そのような資源はない」として扱います。したがって、405 を見たときにまず確認すべきは、[メソッド](/glossary/メソッド/)名ではなく、それが[マージ](/glossary/マージ/)要求への応答かどうかです。

## まず最初に：message の文言で5系統に振り分ける

第一に、405 を返した要求が[マージ](/glossary/マージ/)（`PUT …/pulls/{n}/merge`）かどうかを確認します。[マージ](/glossary/マージ/)以外の操作で 405 が返っているなら、後述の補足を参照してください。

第二に、message を読みます。Pull Request is not mergeable なら原因1、Base branch was modified なら原因2、Required status check または required status checks have not succeeded を含むなら原因3、approving review is required を含むなら原因4、not authorized to push を含むなら原因5です。

第三に、系統が決まったら[リトライ](/glossary/リトライ/)の可否が決まります。原因2だけが待てば解消し、原因1・3・4・5は状態を変えない限り解消しません。この判断を先に済ませてから手を動かすと、無駄な再送を避けられます。

## よくある原因と解決手順

### 原因1：マージできる状態になっていない（Pull Request is not mergeable）

[マージ](/glossary/マージ/)可否そのものが立っていない状態です。代表は2つあります。

1つ目は、[マージ](/glossary/マージ/)可否がまだ計算されていない場合です。公式リファレンスのとおり、プルリクエストの mergeable は true・false・null の3値を取り、null は「[GitHub](/glossary/github/) が背景の処理で計算を始めたところ」を意味します。時間を置いて取得し直せば null 以外になります。作成直後に即[マージ](/glossary/マージ/)する[自動化](/glossary/自動化/)で起きやすく、人が[ブラウザ](/glossary/ブラウザ/)で見たときに「[マージ](/glossary/マージ/)できます」の表示が一拍遅れて緑になるのと同じ現象です。

2つ目は、下書き（draft）のプルリクエストです。公式文書に、下書きのプルリクエストは[マージ](/glossary/マージ/)できないと明記されています。取得したプルリクエストの draft が true なら、[マージ](/glossary/マージ/)の前に下書きを解除する必要があります。

**Before（作成直後にそのまま[マージ](/glossary/マージ/)して 405 になる）：**

```bash
pr=$(curl -s -X POST https://api.github.com/repos/<owner>/<repo>/pulls \
  -H "Authorization: Bearer <your-github-token>" \
  -d '{"title": "release", "head": "release", "base": "main"}' | \
  python3 -c "import json,sys; print(json.load(sys.stdin)['number'])")

curl -s -X PUT https://api.github.com/repos/<owner>/<repo>/pulls/$pr/merge \
  -H "Authorization: Bearer <your-github-token>"
# → mergeable がまだ null のため 405 になることがある
```

**After（mergeable が確定してから[マージ](/glossary/マージ/)する）：**

```bash
for i in $(seq 1 10); do
  m=$(curl -s -H "Authorization: Bearer <your-github-token>" \
    https://api.github.com/repos/<owner>/<repo>/pulls/$pr | \
    python3 -c "import json,sys; d=json.load(sys.stdin); print(d['mergeable'], d['draft'])")
  case "$m" in
    "None"*) sleep 3 ;;                    # 計算中。待って取り直す
    "True False") break ;;                 # マージ可能かつ下書きでない
    *) echo "マージ不可: $m"; exit 1 ;;    # 競合あり、または下書き
  esac
done

curl -s -X PUT https://api.github.com/repos/<owner>/<repo>/pulls/$pr/merge \
  -H "Authorization: Bearer <your-github-token>"
```

なお、より細かい状態を表す mergeable_state（clean、dirty、blocked など）も応答に含まれますが、公式 [API](/glossary/api/) 定義では単なる文字列として置かれているだけで、とりうる値の一覧は定義されていません。この値に依存した分岐は、将来の変更で静かに壊れる可能性があります。判定は mergeable と draft を軸に置くのが安全です。

### 原因2：base ブランチが動いた（Base branch was modified. Review and try the merge again.）

同じ base [ブランチ](/glossary/ブランチ/)に対して複数の[マージ](/glossary/マージ/)がほぼ同時に走ったときに出ます。先に別の[マージ](/glossary/マージ/)が通って base が進むと、後続の[マージ](/glossary/マージ/)要求がこの 405 を受けます。文言は 409 の「Head branch was modified」とよく似ていますが、こちらは base 側の話で、405 で返ります。

この系統は一時的です。5系統の中で唯一、[リトライ](/glossary/リトライ/)が正しい対処になります。

**Before（405 をすべて致命的な失敗として扱う）：**

```bash
curl -sf -X PUT https://api.github.com/repos/<owner>/<repo>/pulls/<number>/merge \
  -H "Authorization: Bearer <your-github-token>" \
  -d '{"merge_method": "squash"}' || exit 1
# → base が動いただけの一時的な失敗でも、処理全体が止まる
```

**After（この文言のときだけ待って再試行する）：**

```bash
for i in $(seq 1 5); do
  status=$(curl -s -o /tmp/merge.json -w "%{http_code}" -X PUT \
    https://api.github.com/repos/<owner>/<repo>/pulls/<number>/merge \
    -H "Authorization: Bearer <your-github-token>" \
    -d '{"merge_method": "squash"}')

  [ "$status" = "200" ] && { echo "マージ完了"; exit 0; }

  if [ "$status" = "405" ] && grep -q "Base branch was modified" /tmp/merge.json; then
    sleep $((i * 5))          # base が落ち着くのを待って再試行
    continue
  fi

  cat /tmp/merge.json; exit 1  # それ以外の 405 は再試行しても変わらない
done
```

### 原因3：必須ステータスチェックが未完了

[ブランチ](/glossary/ブランチ/)保護で必須にしたチェックが、まだ結果を報告していない状態です。この場合の文言として記録されているのは `Required status check "foo" is expected.` と `N of N required status checks have not succeeded: N expected.` の2つです。チェックがすべて成功したように見えても、報告が遅れて届くチェックが1つでもあれば、この 405 になります。

対処は2段階です。まず、必須チェックの名前を事前に取得して、その全部が最新の[コミット](/glossary/コミット/)に対して結果を出したことを確認してから[マージ](/glossary/マージ/)します。必須チェックの一覧は保護設定の取得で分かります。

```bash
curl -s -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/repos/<owner>/<repo>/branches/<branch>/protection/required_status_checks
```

次に、チェックの成否は最新の[コミット](/glossary/コミット/) SHA に対して見ます。公式のトラブルシューティング文書に、必須チェックは最新の[コミット](/glossary/コミット/) SHA で成功している必要があり、それより前の[コミット](/glossary/コミット/)での成功は条件を満たさないと明記されています。プルリクエストに追加の[コミット](/glossary/コミット/)を積んだ直後に[マージ](/glossary/マージ/)すると、この条件で引っかかります。

### 原因4：必要なレビューが足りない（At least 1 approving review is required by reviewers with write access）

[ブランチ](/glossary/ブランチ/)保護でレビュー必須を設定している場合、承認が足りない状態での[マージ](/glossary/マージ/)要求はこの 405 になります。自分が[リポジトリ](/glossary/リポジトリ/)の所有者であっても、保護規則の対象に管理者を含めていれば同じです。

必要な承認数は保護設定から取得できます。

```bash
curl -s -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/repos/<owner>/<repo>/branches/<branch>/protection/required_pull_request_reviews
```

[自動化](/glossary/自動化/)から呼ぶ場合、承認は [API](/glossary/api/) では代替できません。設計としては、承認が揃うまで[マージ](/glossary/マージ/)を試みない（レビュー完了の [Webhook](/glossary/webhook/) を待つ）か、承認が揃っていない状態を異常ではなく「まだその時ではない」として扱う分岐にします。

### 原因5：そのブランチに push する権限がない（You're not authorized to push to this branch.）

[ブランチ](/glossary/ブランチ/)保護の push 制限（特定の利用者・チーム・アプリだけに push を許可する設定）に引っかかった状態です。[権限](/glossary/権限/)の問題は通常 403 か 404 で現れますが、[マージ](/glossary/マージ/)時のこの制限は 405 として返った記録があります。[権限](/glossary/権限/)不足を [403 の記事](/posts/github_api_403/)だけで探すと見つからないのは、このためです。

対処は、[マージ](/glossary/マージ/)を実行する主体（個人の[トークン](/glossary/トークン/)か、[GitHub](/glossary/github/) App の[インストール](/glossary/インストール/)[トークン](/glossary/トークン/)か）を保護設定の許可対象に加えるか、[マージ](/glossary/マージ/)を許可された主体から実行する形に変えることです。

## 補足：405ではない類似エラー

[マージ](/glossary/マージ/)要求に sha を渡し、head がその値と一致しなかった場合は 409 で、message は Head branch was modified. Review and try the merge again. です。405 の Base branch was modified と1語しか違いませんが、意味は逆向きです。405 は「取り込む先が動いた」ので待って再試行、409 は「取り込む中身が動いた」のでレビュー済みの内容と実際の内容がずれていないかの確認が先です（[GitHub API の 409 の記事](/posts/github_api_409/)）。

[リクエスト](/glossary/リクエスト/)の本文が [JSON](/glossary/json/) として壊れている場合は 400、[パラメータ](/glossary/パラメータ/)の検証に落ちた場合は 422 です（[GitHub API の 400 の記事](/posts/github_api_400/)、[422 の記事](/posts/github_api_422/)）。[リポジトリ](/glossary/リポジトリ/)や対象そのものが見えない・[権限](/glossary/権限/)がない場合は 404、[GitHub](/glossary/github/) App や細かい[権限](/glossary/権限/)の[トークン](/glossary/トークン/)での[権限](/glossary/権限/)不足は 403 です（[404 の記事](/posts/github_api_404/)、[403 の記事](/posts/github_api_403/)）。

gh [コマンド](/glossary/コマンド/)を使っている場合は、[HTTP](/glossary/http/) の 405 が出ないことがあります。`gh pr merge` は [GraphQL](/glossary/graphql/) の mergePullRequest を呼ぶため、同じ原因でも `GraphQL: Base branch was modified. Review and try the merge again.` のように、[HTTP](/glossary/http/) の[ステータスコード](/glossary/ステータスコード/)を伴わない形で表示されます。文言が同じであれば、本記事の原因2と同じ扱いで構いません。

最後に、公式 [API](/glossary/api/) 定義で 405 を定義している残り2つは、[リポジトリ](/glossary/リポジトリ/)のプルリクエスト作成上限（pull request creation cap）の取得と更新の[エンドポイント](/glossary/エンドポイント/)です。ただし定義には Method Not Allowed とあるだけで、どの条件でそうなるかは記載されていません。[マージ](/glossary/マージ/)以外で 405 に当たった場合は、この2つに該当するかをまず確認してください。

## 切り分けの順序

1. 405 を返した要求が `PUT …/pulls/{n}/merge` かを確認する。違うなら、[メソッド](/glossary/メソッド/)の誤りではなく、上記の作成上限系か、[GitHub](/glossary/github/) 以外の経路（手前の[プロキシ](/glossary/プロキシ/)など）を疑う。
2. message を読む。文言で原因1〜5に振り分ける。errors 配列は無いので、文言以外の手がかりは無いと考えてよい。
3. Base branch was modified のときだけ、待って再試行する。他の文言での再送は結果が変わらない。
4. Pull Request is not mergeable のときは、プルリクエストを取得して mergeable と draft を見る。mergeable が null なら計算中なので待つ。false なら競合、draft が true なら下書き。
5. チェック・レビュー・push [権限](/glossary/権限/)の文言なら、対象[ブランチ](/glossary/ブランチ/)の保護設定を取得して、満たしていない条件を特定する。
6. [自動化](/glossary/自動化/)に組み込む場合は、405 を一律の失敗にせず、文言で「待つ」と「止める」に分ける。

## 確認コマンド集

```bash
# 1. マージ要求の状態コードと message だけを取り出す
curl -s -o /tmp/merge.json -w "status: %{http_code}\n" -X PUT \
  https://api.github.com/repos/<owner>/<repo>/pulls/<number>/merge \
  -H "Authorization: Bearer <your-github-token>" \
  -d '{"merge_method": "merge"}'
python3 -c "import json; print(json.load(open('/tmp/merge.json')).get('message'))"

# 2. マージ前に、可否・下書き・状態を1行で確認する
curl -s -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/repos/<owner>/<repo>/pulls/<number> | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print('mergeable:', d['mergeable'], '/ draft:', d['draft'], '/ state:', d.get('mergeable_state'))"

# 3. 必須ステータスチェックの名前を事前に取得する
curl -s -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/repos/<owner>/<repo>/branches/<branch>/protection/required_status_checks

# 4. 最新コミットに対するチェックの結果を確認する（3 の名前と突き合わせる）
sha=$(curl -s -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/repos/<owner>/<repo>/pulls/<number> | \
  python3 -c "import json,sys; print(json.load(sys.stdin)['head']['sha'])")
curl -s -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/repos/<owner>/<repo>/commits/$sha/check-runs | \
  python3 -c "import json,sys; [print(c['name'], c['status'], c['conclusion']) for c in json.load(sys.stdin)['check_runs']]"
```

## Editor's Note

原因2の実例として、Kargo（継続的デリバリの[ツール](/glossary/ツール/)）の課題記録があります（[git-merge-pr: 'Base branch was modified' 405 should be retryable when wait=true](https://github.com/akuity/kargo/issues/5761)）。2026年2月18日に登録された報告で、同じ[リポジトリ](/glossary/リポジトリ/)に対して2つの処理が並行して昇格したとき、先のプルリクエストは通り、後のものが 405 Base branch was modified で失敗する、という状況が記録されています。

この記録が示唆に富むのは、開発者側の返答です。「[マージ](/glossary/マージ/)を実行する前に[マージ](/glossary/マージ/)可否の確認をしているはずなのに、その確認を通過して、なお実際の[マージ](/glossary/マージ/)で405になるのはなぜか分からない」と書かれています。これは、確認してから[マージ](/glossary/マージ/)するという素直な作り方では、この405を無くせないということです。確認と[マージ](/glossary/マージ/)の間に他の[マージ](/glossary/マージ/)が割り込む余地は必ず残るためです。つまり原因2への対処は、確認の精度を上げることではなく、この文言に対する[リトライ](/glossary/リトライ/)を最初から設計に入れることです。

もう1つ、原因3については、2021年3月30日に [GitHub](/glossary/github/) のコミュニティに投稿された質問があります（[How to deal with late required status checks?](https://github.com/orgs/community/discussions/24695)）。[マージ](/glossary/マージ/)を代行するボットの作者が、必須チェックの報告が遅れて届くために405を受ける問題を挙げ、文言の文字列一致で判定するのは将来変更されうるので不安だとして、安定した識別子を応答に付けてほしいと要望しています。同年10月に投稿者自身が、必須チェックの名前は保護設定の取得で事前に分かる、と結論を書き残しています。本記事の原因3の対処が「文言で判定する」ではなく「事前に必須チェック名を取得する」である理由は、ここにあります。

405 の応答は、[GitHub](/glossary/github/) が返す[エラー](/glossary/エラー/)の中では情報が少ない部類です。errors 配列も、機械が読める識別子もありません。だからこそ、文言で5系統に分け、[リトライ](/glossary/リトライ/)してよい1つとそうでない4つを見分けるところまでを、あらかじめ決めておく価値があります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*