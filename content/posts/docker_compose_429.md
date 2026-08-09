---
title: "Docker Compose の 429 エラー：原因と解決策"
date: 2026-08-03
description: "Docker Compose の 429 は Docker Hub の pull 回数制限ですが、Compose 固有の増幅要因が3つあります。並列度が既定で無制限、latest タグは既定の pull_policy でも毎回取得され、up のたびに全サービス分の要求が飛びます。回数を増やす前に、この3つを潰すのが先です。"
tags: ["Docker Compose"]
errorCode: "429"
lastmod: 2026-08-03
service: "Docker Compose"
error_type: "429"
components: ["Compose"]
related_services: ["Docker Hub", "Docker Engine"]
trend_incident: false
---

## 冒頭まとめ

`docker compose` の実行中に現れる 429 Too Many Requests は、ほぼ例外なく [Docker](/glossary/docker/) Hub の pull 回数制限です。制限そのものの仕組み（匿名は IP 単位、[認証](/glossary/認証/)済みは[アカウント](/glossary/アカウント/)単位）は Compose に固有の話ではありません（[Docker の 429 の記事](/posts/docker_429/)）。

Compose に固有なのは、**同じ作業でも要求の回数と同時実行数が増えやすい**という点です。増幅の要因は3つあります。

1つ目は並列度です。公式のリファレンスによれば、`--parallel` の既定値は `-1`、つまり**無制限**です。15 サービスの構成なら、15 件の取得要求がほぼ同時に飛びます。

2つ目は[タグ](/glossary/タグ/)です。公式文書には、既定の `missing` という方針であっても `latest` [タグ](/glossary/タグ/)だけは常に取得される、と明記されています。実装を読むと、手元に[イメージ](/glossary/イメージ/)があるかを判定する[関数](/glossary/関数/)が、[タグ](/glossary/タグ/)が `latest` のときは「無い」と扱う作りになっています。`image: nginx` のように[タグ](/glossary/タグ/)を省略した記述は `latest` を指すため、**`up` のたびに[レジストリ](/glossary/レジストリ/)へ問い合わせが行きます**。

3つ目は取得方針です。`pull_policy: always` や `docker compose up --pull always` を使っていると、手元にあっても毎回取得します。

さらに、Compose の取得処理には**再試行の仕組みがありません**。制限に当たれば、その場で失敗します。

したがって対処の順序は、上限を増やすことではなく、この3つの増幅要因を減らすことから始まります。

## エラーの概要

`docker compose pull` や `docker compose up` の実行中に、次の形で現れます。

```text
[+] Pulling 3/5
 ✔ redis Pulled
 ✘ web Error toomanyrequests: You have reached your pull rate limit.
     You may increase the limit by authenticating and upgrading: ...
 ✘ api Error toomanyrequests: You have reached your pull rate limit.
Error response from daemon: toomanyrequests: You have reached your pull rate limit.
```

注目すべきは、**複数のサービスが同時に失敗する**点です。単発の `docker pull` なら1件で終わるところが、並列に走っているため、残り枠を一気に使い切ってまとめて弾かれます。

[レジストリ](/glossary/レジストリ/)側の応答そのものは 429 ですが、Compose の表示には状態[コード](/glossary/コード/)の数字が出ないことがあります。`toomanyrequests` の文字列が、429 であることの目印です。

なお、この文言を出しているのは Compose ではありません。取得処理は [Docker](/glossary/docker/) Engine の中で行われ、Compose はそれを依頼して進捗を表示しているだけです。この構造は、あとの対処の方向を決めます。

## まず最初に：Compose 側の3点を確認する

第一に、同時に何件失敗したかを見ます。複数なら並列度が効いています。

第二に、記述している[タグ](/glossary/タグ/)を確認します。省略していれば `latest` であり、毎回取得の対象です。

第三に、`pull_policy` と `--pull` の指定を確認します。`always` になっていないか。

第四に、[認証](/glossary/認証/)状態を確認します。ただしこれは Compose ではなく Engine 側の設定です。`docker login` の有無で決まります。

## よくある原因と解決手順

### 原因1：並列度が無制限のまま

公式リファレンスに、`--parallel` は同時に実行するエンジン呼び出しの上限を指定するもので、既定値は `-1`（無制限）だと明記されています。あわせて、`COMPOSE_PARALLEL_LIMIT` という[環境変数](/glossary/環境変数/)でも同じ指定ができること、[コマンド](/glossary/コマンド/)行で明示した場合は[環境変数](/glossary/環境変数/)が無視されることも書かれています。

**Before（無制限のまま実行する）：**

```bash
docker compose pull
# → 全サービス分の要求がほぼ同時に飛ぶ
```

**After（同時実行数を絞る）：**

```bash
docker compose --parallel 1 pull
# または
export COMPOSE_PARALLEL_LIMIT=2
docker compose pull
```

公式リファレンスにも、`--parallel 1` を付ければ[イメージ](/glossary/イメージ/)を1つずつ取得する、という説明があります。この指定は取得だけでなく構築の同時実行数にも効きます。

並列度を下げても、消費する回数の合計は変わりません。効くのは、残り枠がわずかなときに全滅を避けられる点と、共有 IP の[環境](/glossary/環境/)で瞬間的な集中を作らない点です。

### 原因2：latest タグで毎回取得している

これが最も気付きにくい要因です。公式文書には、`missing` の方針でも `latest` [タグ](/glossary/タグ/)は常に取得される、と例外として明記されています。実装でも、手元の[イメージ](/glossary/イメージ/)と照合する処理が、[タグ](/glossary/タグ/)付きの[イメージ](/glossary/イメージ/)については「手元にあり、かつ[タグ](/glossary/タグ/)が `latest` でない」場合にのみ既存と判定します。

**Before（[タグ](/glossary/タグ/)を省略する）：**

```yaml
services:
  web:
    image: nginx          # latest を指す。毎回取得される
  cache:
    image: redis:latest   # 同上
```

**After（[タグ](/glossary/タグ/)を固定する）：**

```yaml
services:
  web:
    image: nginx:1.27-alpine
  cache:
    image: redis:7.2
```

[タグ](/glossary/タグ/)を固定すると、手元にある限り[レジストリ](/glossary/レジストリ/)への問い合わせが発生しません。回数の削減としては最も効果が大きく、同時に構成の再現性も上がります。

### 原因3：取得方針が毎回取得になっている

`pull_policy: always` を指定している場合、あるいは `docker compose up --pull always` を使っている場合です。`up` の `--pull` の既定値は `policy` で、これは構成[ファイル](/glossary/ファイル/)に書かれた方針に従うという意味です。

更新を取りこぼしたくないという意図で `always` にしている場合、公式文書が用意している中間の選択肢が使えます。

```yaml
services:
  web:
    image: nginx:1.27-alpine
    pull_policy: daily      # 24時間以上経っていれば確認する
  api:
    image: example/api:v2
    pull_policy: every_12h  # 週や日、時間、分の組み合わせで指定できる
```

`daily` は前回の取得から24時間以上、`weekly` は7日以上経過している場合にのみ[レジストリ](/glossary/レジストリ/)を確認します。`every_<期間>` は任意の間隔を指定できます。毎回取得と一切取得しないの二択ではない、という点を押さえてください。

### 原因4：認証していない

匿名の枠は IP 単位で数えられるため、同じ[回線](/glossary/回線/)を使う全員で共有します。[認証](/glossary/認証/)すると[アカウント](/glossary/アカウント/)単位に変わります。

ここで重要なのは、**[認証](/glossary/認証/)は Compose の設定ではない**ことです。取得は Engine が行うため、`docker login` で Engine に資格情報を渡します。構成[ファイル](/glossary/ファイル/)に書く項目はありません。

```bash
docker login
docker compose pull
```

[自動化](/glossary/自動化/)の中で実行する場合は、取得の前に一度 `docker login` を挟みます。Compose の[コマンド](/glossary/コマンド/)を工夫しても、[認証](/glossary/認証/)されていなければ枠は増えません。

### 原因5：どのサービスが原因かを切り分けられていない

多数のサービスがある構成では、どの[イメージ](/glossary/イメージ/)が枠を消費しているのか把握しづらくなります。

`docker compose pull` には、取得できるものだけ取得して失敗を無視する指定があります。切り分けの際に有用です。

```bash
# 失敗を無視して、取得できたものと落ちたものを一覧で見る
docker compose pull --ignore-pull-failures

# 方針を明示して、手元にあるものは取得しない
docker compose pull --policy missing
```

構築対象の[イメージ](/glossary/イメージ/)を除外する指定もあります。ベース[イメージ](/glossary/イメージ/)の取得は構築の側で発生するため、取得と構築のどちらで枠を使っているかを分けて考える必要があります。

## 補足：似ているが別のもの

制限そのものの数え方、枠の単位、ミラーによる回避は [Docker](/glossary/docker/) 全体に共通する話です（[Docker の 429 の記事](/posts/docker_429/)）。本記事は Compose 側で調整できる部分に絞っています。

[認証](/glossary/認証/)情報が無効な場合や、[権限](/glossary/権限/)の無い[レジストリ](/glossary/レジストリ/)を指している場合は 429 ではなく 401 や 403 になります。`toomanyrequests` の文字列が無ければ、回数の問題ではありません。

同じ回数制限でも、[Kubernetes](/glossary/kubernetes/) 経由では Pod の出来事として現れ、調べる場所が変わります（[Kubernetes の 429 の記事](/posts/kubernetes_429/)）。

構成内のサービスが返す 429 は、これらとは無関係です。[コンテナ](/glossary/コンテナ/)の中の[アプリケーション](/glossary/アプリケーション/)が自分で[レート制限](/glossary/レート制限/)を実装している場合、原因はその[アプリケーション](/glossary/アプリケーション/)側にあります。応答が[レジストリ](/glossary/レジストリ/)からなのか、[コンテナ](/glossary/コンテナ/)からなのかを最初に分けてください。

起動後の応答が返らない場合は 500 や 503 の系統です（[Docker Compose の 500 の記事](/posts/docker_compose_500/)、[503 の記事](/posts/docker_compose_503/)）。

## 切り分けの順序

1. `toomanyrequests` の文字列があるかを確認する。無ければ回数の問題ではない。
2. 同時に何件失敗したかを見る。複数なら並列度が効いている。
3. 記述している[タグ](/glossary/タグ/)を確認する。省略や `latest` は毎回取得の対象。
4. `pull_policy` と `--pull` を確認する。`always` なら中間の方針に変える。
5. `docker login` の有無を確認する。Compose 側ではなく Engine 側の設定。
6. `--parallel 1` で同時実行数を絞り、再現するかを見る。
7. `--ignore-pull-failures` でどの[イメージ](/glossary/イメージ/)が落ちているかを一覧化する。
8. 取得と構築のどちらで枠を使っているかを分ける。

## 確認コマンド集

```bash
# 1. 同時実行数を1にして取得する（切り分けと緩和を兼ねる）
docker compose --parallel 1 pull

# 2. 環境変数でも指定できる（コマンド行の指定が優先される）
export COMPOSE_PARALLEL_LIMIT=2

# 3. 失敗するイメージを一覧化する
docker compose pull --ignore-pull-failures

# 4. 構成が実際に参照しているイメージとタグを確認する
docker compose config --images

# 5. latest を指しているサービスを洗い出す
docker compose config --images | grep -E ':latest$|^[^:]+$'

# 6. 手元にあるイメージと突き合わせる
docker image ls --format '{{.Repository}}:{{.Tag}}'

# 7. 認証状態を確認する（Engine 側の設定）
docker login
docker system info | grep -i username

# 8. 残り回数を確認する（Docker Hub の応答ヘッダー）
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:ratelimitpreview/test:pull" | sed -E 's/.*"token":"([^"]+)".*/\1/')
curl -sI -H "Authorization: Bearer $TOKEN" \
  https://registry-1.docker.io/v2/ratelimitpreview/test/manifests/latest | grep -i ratelimit
```

## Editor's Note

Compose で 429 に当たると、Compose 側の不具合を疑いたくなります。実際、そのように報告された記録があります（[Rate limit hit with docker compose](https://github.com/docker/compose/issues/12336)）。2024年11月、Compose での配備時に [Docker](/glossary/docker/) Hub の回数制限に当たるようになった、という内容です。報告者は、同じ[イメージ](/glossary/イメージ/)を単発で取得しても失敗すること、より頻繁に取得している別環境では問題が起きないことを挙げ、Compose との関連を疑っています。

返答は明快でした。関連は無い、取得は Engine の中で行われ、Compose のような[クライアント](/glossary/クライアント/)は Engine に取得を依頼して進捗を報告するだけで、その中身を制御していない、というものです。そのうえで、[自動化](/glossary/自動化/)の中で最初に `docker login` を実行するのが枠を増やす簡単な方法だ、と案内されています。

この説明は正確ですが、そこで話を終えると半分を取りこぼします。**Compose は取得の中身を制御しませんが、「何件の取得を、いくつ同時に依頼するか」は制御します**。並列度の既定が無制限であること、`latest` [タグ](/glossary/タグ/)が毎回の取得対象になること、取得方針が `always` なら手元にあっても取りに行くこと。これらはすべて Compose 側の設定で決まります。

同じ報告の中で参照されている別の相談には、「取得していないのに制限に達した」という趣旨の題名が付いています。心当たりが無いのに枠が減っていく感覚は、`latest` [タグ](/glossary/タグ/)の扱いを知ると腑に落ちます。手元にあるから取りに行かないはずだ、という前提が成り立っていないためです。

429 に当たったら、まず[認証](/glossary/認証/)する。これは正しい第一歩です。そのうえで、構成[ファイル](/glossary/ファイル/)の[タグ](/glossary/タグ/)を見てください。枠を静かに消費していた原因は、たいていそこにあります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*