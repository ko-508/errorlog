---
title: "GitHub API の 409 エラー：原因と解決策"
date: 2026-01-01
description: "GitHub API の 409 Conflict は、リクエストの形は正しいのに、リソースの現在の状態と矛盾していることを示します。公式の API 定義を調べると、実際の409はマージ競合、sha 不一致の競合ガード、空リポジトリなど状態の前提を満たさない操作の3系統です。「Reference already exists」などの検証エラーは409ではなく422で、調査の場所が異なります。"
tags: ["GitHub API"]
errorCode: "409"
lastmod: 2026-07-15
service: "GitHub API"
error_type: "409"
components: ["REST API"]
related_services: ["GitHub REST API", "GitHub Actions", "Octokit"]
trend_incident: false
---

## 冒頭まとめ

GitHub [API](/glossary/api/) の 409 Conflict は、[リクエスト](/glossary/リクエスト/)の綴りや[権限](/glossary/権限/)の問題ではなく、「[リクエスト](/glossary/リクエスト/)の内容が対象の現在の状態と矛盾している」ことを示すコードです。GitHub 公式の [API](/glossary/api/) 定義（OpenAPI）で409が定義されている[エンドポイント](/glossary/エンドポイント/)を調べると、実際の409は3系統に整理できます。第一に、本物の[マージ](/glossary/マージ/)競合です（[ブランチ](/glossary/ブランチ/)の[マージ](/glossary/マージ/) [API](/glossary/api/) や上流[ブランチ](/glossary/ブランチ/)との[同期](/glossary/同期/) [API](/glossary/api/) が、競合時に409を返すと定義されています）。第二に、競合ガードです。対象が「あなたが見た時点」から動いたことを検出して操作を止める仕組みで、pull request の[マージ](/glossary/マージ/) [API](/glossary/api/) に sha を渡した場合の head 不一致や、[ファイル](/glossary/ファイル/)更新（contents）[API](/glossary/api/) の sha 不一致がこれにあたります。第三に、[リポジトリ](/glossary/リポジトリ/)の状態が操作の前提を満たさないケースで、代表は空の[リポジトリ](/glossary/リポジトリ/)に対する [Git](/glossary/git/) 系・[コミット](/glossary/コミット/)系の [API](/glossary/api/) です（公式ガイドに、[リポジトリ](/glossary/リポジトリ/)が空または利用不能のとき [REST](/glossary/rest/) [API](/glossary/api/) は 409 Conflict を返すと明記されています）。

同じくらい重要なのが、409だと思い込みやすいのに409ではない[エラー](/glossary/エラー/)です。「Reference already exists」（[ブランチ](/glossary/ブランチ/)や[タグ](/glossary/タグ/)が既に存在する）、「No commits between ...」（差分のないプルリクエスト作成）、既存[タグ](/glossary/タグ/)への[リリース](/glossary/リリース/)作成は、いずれも 422 Validation Failed です。また、競合状態のプルリクエストを[マージ](/glossary/マージ/)しようとした場合は 405 が定義されています。これらを409として調査すると出口のない回り道になるため、まずコードと系統の確認から始めます。

## エラーの概要

409は「待てば直る」とも「直らない」とも一概に言えないコードで、系統によって正反対の対処になります。競合ガードの409は、最新の状態を取得し直して再実行するのが正しい対処です。[マージ](/glossary/マージ/)競合の409は、再試行しても同じ結果で、競合の解決そのものが必要です。空[リポジトリ](/glossary/リポジトリ/)の409は、[初期化](/glossary/初期化/)するまで何度でも返ります。

実際の応答例として、空の[リポジトリ](/glossary/リポジトリ/)の[コミット](/glossary/コミット/)一覧を取得した場合は次の形になります（公開されている実測記録と一致します）。

```bash
$ curl -i https://api.github.com/repos/<owner>/<empty-repo>/commits
HTTP/2 409
...
{
  "message": "Git Repository is empty.",
  "documentation_url": "https://docs.github.com/rest/commits/commits#list-commits"
}
```

message の文言が、系統を見分ける最初の手がかりです。[Git](/glossary/git/) Repository is empty なら原因3、[マージ](/glossary/マージ/)操作への応答なら原因1か2、[ファイル](/glossary/ファイル/)更新への応答なら原因2です。

## まず最初に：どの操作への409かで3つに分岐する

[ブランチ](/glossary/ブランチ/)の[マージ](/glossary/マージ/)（POST .../merges）や上流との[同期](/glossary/同期/)（POST .../merge-upstream）への409なら、[マージ](/glossary/マージ/)競合です（原因1）。pull request の[マージ](/glossary/マージ/)（PUT .../pulls/{n}/merge）への409は、[リクエスト](/glossary/リクエスト/)に sha を渡している場合に head の移動を検出したガードです（原因2）。[ファイル](/glossary/ファイル/)の作成・更新・削除（PUT / DELETE .../contents/{path}）への409も、並行更新による sha の食い違いというガードです（原因2）。[コミット](/glossary/コミット/)一覧や [Git](/glossary/git/) [データベース](/glossary/データベース/)系（git/refs、git/commits、git/trees など）の取得・作成への409で、message が [Git](/glossary/git/) Repository is empty なら、[リポジトリ](/glossary/リポジトリ/)が空です（原因3）。

## よくある原因と解決手順

### 原因1：本当にマージ競合が起きている

[ブランチ](/glossary/ブランチ/)同士を[マージ](/glossary/マージ/)する [API](/glossary/api/)（POST /repos/{owner}/{repo}/merges）は、公式定義のとおり、[マージ](/glossary/マージ/)競合があるときに409を返します。同じ定義には、すでに[マージ](/glossary/マージ/)済みなら 204、base や head が存在しなければ 404 と、結果ごとの割り当ても明記されています。フォークを上流に追随させる [API](/glossary/api/)（merge-upstream）も、競合で[同期](/glossary/同期/)できない場合は409です。

この系統の409に対して、[API](/glossary/api/) の再試行は意味を持ちません。競合の解決は [API](/glossary/api/) ではできず、作業コピーで行います。

**Before（[同期](/glossary/同期/)スクリプトが409を一時[エラー](/glossary/エラー/)扱いして再試行し続ける）：**

```bash
# 上流の変更を main に取り込む定期ジョブ
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/repos/<owner>/<repo>/merges \
  -d '{"base": "main", "head": "upstream-sync"}'
# → 409 を受けてもリトライを繰り返す（何回やっても 409）
```

**After（409 は「競合の解決が必要」という結果として扱い、解決フローへ回す）：**

```bash
status=$(curl -s -o /tmp/resp.json -w "%{http_code}" -X POST \
  -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/repos/<owner>/<repo>/merges \
  -d '{"base": "main", "head": "upstream-sync"}')

case "$status" in
  201) echo "マージ完了" ;;
  204) echo "すでにマージ済み。何もしない" ;;
  409) echo "競合あり。ローカルで解決して push するか、PR を作成して解決する"
       # 例: git fetch && git checkout main && git merge origin/upstream-sync
       exit 1 ;;
esac
```

### 原因2：対象が「見た時点」から動いた（競合ガード）

pull request の[マージ](/glossary/マージ/) [API](/glossary/api/) に sha [パラメータ](/glossary/パラメータ/)を渡すと、「この head のときだけ[マージ](/glossary/マージ/)してよい」という指定になり、公式定義のとおり、head がその sha と一致しなければ409が返ります。これはレビューが済んだ内容と実際に[マージ](/glossary/マージ/)される内容のすり替えを防ぐガードで、409は「レビュー後に新しい[コミット](/glossary/コミット/)が積まれた」という通知です。対処は、head を確認し直し、必要なら再レビューのうえ最新の sha で再実行することです。

[ファイル](/glossary/ファイル/)の作成・更新・削除（contents [API](/glossary/api/)）の409も同じ構図です。更新には現在の[ファイル](/glossary/ファイル/)の sha を渡す必要があり、取得から[リクエスト](/glossary/リクエスト/)までの間に誰かが同じ[ファイル](/glossary/ファイル/)を更新すると、渡した sha が古くなって409になります。典型は、GitHub Actions の並列ジョブが同じ[ファイル](/glossary/ファイル/)（[バージョン](/glossary/バージョン/)表、集計結果など）を更新する構成です。

**Before（並列ジョブが同じ[ファイル](/glossary/ファイル/)を取得→更新し、先に書いた方以外が409になる）：**

```yaml
jobs:
  update-manifest:
    strategy:
      matrix:
        target: [a, b, c]   # 3ジョブが同時に同じファイルを更新する
    runs-on: ubuntu-latest
    steps:
      - run: |
          sha=$(gh api repos/$REPO/contents/manifest.json --jq .sha)
          gh api -X PUT repos/$REPO/contents/manifest.json \
            -f message="update ${{ matrix.target }}" \
            -f content="$(base64 -w0 new.json)" -f sha="$sha"
```

**After（直列化するか、409 のときだけ sha を取り直して再試行する）：**

```yaml
jobs:
  update-manifest:
    concurrency:
      group: manifest-update   # 同じファイルを触るジョブを直列化する
    runs-on: ubuntu-latest
    steps:
      - run: |
          for i in 1 2 3; do
            sha=$(gh api repos/$REPO/contents/manifest.json --jq .sha)
            if gh api -X PUT repos/$REPO/contents/manifest.json \
              -f message="update" \
              -f content="$(base64 -w0 new.json)" -f sha="$sha"; then
              exit 0
            fi
            echo "409 の可能性。sha を取り直して再試行 ($i)"
            sleep 2
          done
          exit 1
```

ガード系の409の対処は共通で、「最新を取得し直してから、やり直す」です。再試行そのものは正しい対処ですが、古い sha のまま繰り返しても何度でも409になる点だけ注意してください。

### 原因3：リポジトリが空、または操作の前提となる状態にない

GitHub の公式ガイド（[Git](/glossary/git/) [データベース](/glossary/データベース/)の利用ガイド）には、[Git](/glossary/git/) [リポジトリ](/glossary/リポジトリ/)が空か利用不能（unavailable）の場合、[REST](/glossary/rest/) [API](/glossary/api/) は 409 Conflict を返すと明記されています。利用不能とは、典型的には[リポジトリ](/glossary/リポジトリ/)の作成処理が進行中の状態です。[リポジトリ](/glossary/リポジトリ/)作成 [API](/glossary/api/) の直後に[コミット](/glossary/コミット/)一覧・[ブランチ](/glossary/ブランチ/)・[Git](/glossary/git/) [データベース](/glossary/データベース/)系の [API](/glossary/api/) を呼ぶ[自動化](/glossary/自動化/)で、この409に当たります。

公式ガイドは解決策も示しています。空の[リポジトリ](/glossary/リポジトリ/)には、contents [API](/glossary/api/)（PUT /repos/{owner}/{repo}/contents/{path}）で最初の[ファイル](/glossary/ファイル/)を作成すれば[リポジトリ](/glossary/リポジトリ/)が[初期化](/glossary/初期化/)され、以後 [Git](/glossary/git/) 系の [API](/glossary/api/) が使えるようになります。

**Before（作成直後の空[リポジトリ](/glossary/リポジトリ/)に[ブランチ](/glossary/ブランチ/)を作ろうとして409になる）：**

```bash
curl -s -X POST -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/user/repos -d '{"name": "new-repo"}'

curl -i -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/repos/<owner>/new-repo/git/ref/heads/main
# → 409 {"message": "Git Repository is empty."}
```

**After（作成時に[初期化](/glossary/初期化/)するか、contents [API](/glossary/api/) で最初の[コミット](/glossary/コミット/)を作る）：**

```bash
# 方法1：作成時に auto_init を指定し、最初のコミット（README）を作らせる（公式パラメータ）
curl -s -X POST -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/user/repos -d '{"name": "new-repo", "auto_init": true}'

# 方法2：contents API で最初のファイルを作成して初期化する（公式ガイドの方法）
curl -s -X PUT -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/repos/<owner>/new-repo/contents/README.md \
  -d '{"message": "init", "content": "'"$(printf '# new-repo' | base64)"'"}'
```

このほか、状態の前提を満たさない操作の409は各所に定義されています。たとえば GitHub Actions の実行の取り消し [API](/glossary/api/) にも409が定義されており、取り消せる状態にない実行への要求がこれにあたります。共通する読み方は「操作は正しいが、相手が今その操作を受けられる状態ではない」です。

## 補足：409ではない類似エラー

409と思われがちな検証[エラー](/glossary/エラー/)の正しい行き先です。[ブランチ](/glossary/ブランチ/)や[タグ](/glossary/タグ/)の作成で同名の参照が既に存在する場合の Reference already exists、差分のないプルリクエスト作成の No commits between、既存[タグ](/glossary/タグ/)と重複する[リリース](/glossary/リリース/)作成は、いずれも errors 配列を伴う 422 Validation Failed で、409ではありません（422 の読み方は [GitHub API の 400 の記事](/posts/github_api_400/)を参照）。競合などで[マージ](/glossary/マージ/)できない状態のプルリクエストへの[マージ](/glossary/マージ/)要求は、409ではなく 405 と定義されており、[マージ](/glossary/マージ/)可否は事前に pull request の mergeable [属性](/glossary/属性/)で確認できます（公式ガイドは mergeable が計算されるまでポーリングする方法を案内しています）。権限不足や不存在は、private [リポジトリ](/glossary/リポジトリ/)の秘匿のため 404 です（[404 の記事](/posts/github_api_404/)）。並行[リクエスト](/glossary/リクエスト/)の多さそのものが弾かれる場合は secondary rate limit で、403 または 429 です（[403 の記事](/posts/github_api_403/)、[429 の記事](/posts/github_api_429/)）。

## 切り分けの順序

1. コードを確認する。422（Validation Failed）・405・404・403・429 なら、409ではないのでそれぞれの調査に切り替える。
2. どの[エンドポイント](/glossary/エンドポイント/)への409かを確認する。[マージ](/glossary/マージ/)系なら原因1、sha を渡す操作（PR [マージ](/glossary/マージ/)・contents）なら原因2、[Git](/glossary/git/) 系・[コミット](/glossary/コミット/)系なら原因3。
3. message を読む。[Git](/glossary/git/) Repository is empty なら[初期化](/glossary/初期化/)（auto_init または contents [API](/glossary/api/)）で解決する。
4. ガード系（原因2）は、最新の状態（head の sha、[ファイル](/glossary/ファイル/)の sha）を取得し直してから再実行する。並行更新が常態なら直列化する。
5. [マージ](/glossary/マージ/)競合（原因1）は [API](/glossary/api/) の再試行では解決しないため、ローカルまたは PR で競合を解決する。

## 確認コマンド集

```bash
# 1. コードと message を確認する
curl -i -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/repos/<owner>/<repo>/commits 2>&1 | grep -E "^HTTP|message"

# 2. リポジトリが空かどうかの確認（コミット一覧の409自体が空の証拠になる）
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/repos/<owner>/<repo>/commits

# 3. PR の head と マージ可否を確認する（原因2の再実行前）
curl -s -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/repos/<owner>/<repo>/pulls/<number> | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(d['head']['sha'], d['mergeable'])"

# 4. ファイルの現在の sha を取得し直す（contents の409の再実行前）
curl -s -H "Authorization: Bearer <your-github-token>" \
  https://api.github.com/repos/<owner>/<repo>/contents/<path> | \
  python3 -c "import json,sys; print(json.load(sys.stdin)['sha'])"
```

## Editor's Note

原因3の実例として、GitHub 自身の [API](/glossary/api/) 定義[リポジトリ](/glossary/リポジトリ/)に残る記録があります（[Schema Inaccuracy: GET /repos/.../commits can respond with 409 if repository is empty](https://github.com/github/rest-api-description/issues/385)）。2021年、Octokit のメンテナが「[コミット](/glossary/コミット/)一覧 [API](/glossary/api/) の応答定義に409が欠けている」と報告したもので、空[リポジトリ](/glossary/リポジトリ/)への実測の curl 出力（[HTTP](/glossary/http/)/2 409、message は [Git](/glossary/git/) Repository is empty.）がそのまま添えられています。空[リポジトリ](/glossary/リポジトリ/)の409は、GitHub 公式の [API](/glossary/api/) 定義からさえ一時的に漏れていたほど見落とされやすい挙動だった、ということです。本記事の執筆にあたり取得した現行の公式 OpenAPI 定義では、この[エンドポイント](/glossary/エンドポイント/)に409が定義されており、報告は反映済みです。約5年前の記録ですが、空[リポジトリ](/glossary/リポジトリ/)への [Git](/glossary/git/) 系 [API](/glossary/api/) が409を返す挙動と、contents [API](/glossary/api/) で[初期化](/glossary/初期化/)するという回避策は、現行の公式ガイドにそのまま明記されています。

409は「あなたの見ている世界と、GitHub 側の今の状態がずれている」ことを伝えるコードです。ずれの正体が競合なのか、追い越されただけなのか、そもそも前提が欠けているのか。[エンドポイント](/glossary/エンドポイント/)と message でそこを見極めれば、再試行すべきか、解決すべきか、[初期化](/glossary/初期化/)すべきかが決まります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*