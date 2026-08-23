---
title: "Docker の name is already in use：原因と解決策"
date: 2026-08-07
description: "この記事が扱うのは対処法の一覧ではなく、名前がいつ確保されいつ返されるのかという仕組みです。Docker は名前とコンテナ ID の対応を、コンテナ本体とは別の表で持っています。この表から消えるのは削除の完了と改名のときだけで、停止も異常終了も名前を返しません。だから止めたコンテナが名前を握り続けます。"
tags: ["Docker"]
images: ["og/posts/docker_container_name_already_in_use.png"]
errorCode: "container name is already in use"
lastmod: 2026-08-07
service: "Docker"
error_type: "Conflict"
components: ["Docker Daemon", "Compose"]
related_services: ["Docker Compose", "Docker Engine API"]
trend_incident: false
---

## 冒頭まとめ

`The container name "/web" is already in use` を見たとき、動いている[コンテナ](/glossary/コンテナ/)を探しても見つからないことがあります。`docker ps` に何も出ないのに拒まれる、という状況です。

理由は名前の持ち方にあります。[Docker](/glossary/docker/) の[デーモン](/glossary/デーモン/)は、名前と[コンテナ](/glossary/コンテナ/) [ID](/glossary/id/) の対応を、[コンテナ](/glossary/コンテナ/)本体とは別の表で管理しています。実装では `names` という名前の表で、`containers` の表とは分かれています。名前を確保するのは作成の時点で、その予約を消す処理が呼ばれるのは[削除](/glossary/削除/)と改名の2か所だけです。

つまり名前は、動いている[コンテナ](/glossary/コンテナ/)が占有しているのではありません。[コンテナ](/glossary/コンテナ/)が存在する限り予約され続けます。停止しても、異常終了しても、作成に失敗して起動前で止まっていても、名前は返りません。`docker ps` が既定で動いているものだけを表示するため、この食い違いが起きます。

この仕組みが分かると、対処が3つに絞られます。予約している[コンテナ](/glossary/コンテナ/)を消すか、その[コンテナ](/glossary/コンテナ/)の名前を変えるか、こちらの名前を変えるかです。強制的に作り直しても、[デーモン](/glossary/デーモン/)を再起動しても、原則としてこの3つ以外の道はありません。なお同じ[コンテナ](/glossary/コンテナ/)が同じ名前を確保し直す場合は衝突しません。予約の処理は、名前と [ID](/glossary/id/) の組が一致していればそのまま通る作りになっています。

もう1つ押さえるべき点があります。名前の一意性は[デーモン](/glossary/デーモン/)ごとです。[ネットワーク](/glossary/ネットワーク/)を分けても、Compose の[プロジェクト](/glossary/プロジェクト/)を分けても、同じ[デーモン](/glossary/デーモン/)の上なら名前は1つしか使えません。

## エラーの概要

出力は次の形です。

```text
docker: Error response from daemon: Conflict. The container name "/web" is already in use by container
"e7f8c9a2b1d4...". You have to remove (or rename) that container to be able to reuse that name.
```

読む場所は2つあります。1つ目は名前の先頭に付いた `/` です。これは入力の誤りではありません。実装は名前を予約する前に、先頭が `/` でなければ付け足します。だから表示にも `/` が現れます。

2つ目は後半の[コンテナ](/glossary/コンテナ/) [ID](/glossary/id/) です。これが予約している当事者で、調査の出発点になります。名前で探しても見つからない場合があるため、この [ID](/glossary/id/) で直接照会するのが確実です。

この応答は [Docker](/glossary/docker/) Engine [API](/glossary/api/) では 409 として返ります。名前の衝突以外にも 409 になる場面はあるため、状態[コード](/glossary/コード/)だけでは区別できません（[Docker の 409 エラーの記事](/posts/docker_409/)）。

名前に使える文字も実装で決まっています。先頭は英数字で、2文字目以降は英数字と下線・点・ハイフンだけです。これを外れると衝突ではなく、別の[エラー](/glossary/エラー/)として拒まれます。

## まず最初に：名乗っている相手を ID で特定する

推測の前に、出力に書かれた [ID](/glossary/id/) をそのまま照会します。

```bash
docker inspect --format '{{.Name}} {{.State.Status}} {{.Created}}' <出力に出た ID>
```

ここで状態が分かれば、次の一手が決まります。`exited` なら停止済みで、原因1です。`created` なら作成だけされて起動していない状態で、原因2に当たります。`Removal In Progress` と出るなら[削除](/glossary/削除/)の途中で、原因5です。

`docker inspect` が対象なしと返る場合もあります。予約だけが残って本体が消えている状況で、原因5の後半で扱います。

一覧で確かめるなら、必ず `-a` を付けてください。

```bash
docker ps -a --filter "name=^/web$"
```

`docker ps` は既定で動いている[コンテナ](/glossary/コンテナ/)しか出しません。この点を見落とすと、存在しない相手と衝突しているように見えます。

## よくある原因と解決手順

### 原因1：停止済みのコンテナが名前を握っている

最も多い形です。前回の実行で作った[コンテナ](/glossary/コンテナ/)が停止したまま残っており、名前の予約も残っています。

対処は3つあります。もう使わないなら[削除](/glossary/削除/)します。残しておきたいなら改名します。どちらも避けたいなら、こちらの名前を変えます。実装では、名前の予約が消えるのは[削除](/glossary/削除/)の完了時と改名時だけなので、選択肢はこの範囲に収まります。

**Before（同じ名前でそのまま作り直す）：**

```bash
docker run -d --name web nginx
```

**After（予約している側を消してから作る）：**

```bash
docker rm web
docker run -d --name web nginx
```

繰り返し使い捨てるなら、`--rm` を付けて終了時に自動で消えるようにしておくと、この衝突自体が起きにくくなります。ただし `--rm` は終了時の[削除](/glossary/削除/)であり、`docker stop` で止めた場合も[削除](/glossary/削除/)は行われます。手元に残して調べたい[コンテナ](/glossary/コンテナ/)には向きません。

### 原因2：作成だけされて起動していないコンテナが残っている

状態が `created` の場合です。`docker create` を使った場合のほか、`docker run` が起動の段階で失敗したときにも残ります。[ポート](/glossary/ポート/)の衝突やボリュームの指定誤りで起動に失敗しても、[コンテナ](/glossary/コンテナ/)自体は作られているため、名前は確保済みです。

見落としやすいのは、起動に失敗した直後に同じ[コマンド](/glossary/コマンド/)を打ち直す場面です。1回目は起動の失敗、2回目は名前の衝突と、違う[エラー](/glossary/エラー/)が出ます。2回目の文言だけを見て名前を変えると、本来の失敗の原因が残ったままになります。

**Before（文言が変わったので名前だけ変える）：**

```bash
docker run -d --name web2 nginx
```

**After（残骸を消して、最初の失敗の理由を確かめる）：**

```bash
docker rm web
docker run -d --name web nginx
```

### 原因3：Compose のプロジェクト名が意図せず一致している

Compose は既定で[プロジェクト](/glossary/プロジェクト/)名を作業[ディレクトリ](/glossary/ディレクトリ/)の名前から決めます。そのため、別の場所にある同じ名前の[ディレクトリ](/glossary/ディレクトリ/)で作業すると、[コンテナ](/glossary/コンテナ/)名まで一致します。`~/work/app` と `~/tmp/app` は、Compose から見れば同じ[プロジェクト](/glossary/プロジェクト/)です。

対処は[プロジェクト](/glossary/プロジェクト/)名を明示することです。仕様では最上位の `name` 要素で指定でき、指定した値は `COMPOSE_PROJECT_NAME` として参照できます。

**Before（[プロジェクト](/glossary/プロジェクト/)名を[ディレクトリ](/glossary/ディレクトリ/)名任せにする）：**

```yaml
services:
  web:
    image: nginx
```

**After（[プロジェクト](/glossary/プロジェクト/)名を明示して分離する）：**

```yaml
name: myapp-staging

services:
  web:
    image: nginx
```

### 原因4：container_name を明示している

Compose の設定に `container_name` を書くと、その名前がそのまま使われます。[プロジェクト](/glossary/プロジェクト/)名による区切りが効かなくなるため、同じ設定を別の[プロジェクト](/glossary/プロジェクト/)や別の[環境](/glossary/環境/)で動かした瞬間に衝突します。

仕様には制約も明記されています。`container_name` を書いたサービスは1つを超えて増やせず、増やそうとすると[エラー](/glossary/エラー/)になります。使える文字も、[Docker](/glossary/docker/) 本体と同じ制限に従います。

**Before（名前を固定して分離を失う）：**

```yaml
services:
  db:
    image: postgres
    container_name: db
```

**After（既定の命名に任せる）：**

```yaml
services:
  db:
    image: postgres
```

既定に任せると、名前は[プロジェクト](/glossary/プロジェクト/)名とサービス名と連番をハイフンでつないだものになります。`myapp-web-1` のような形です。同じ[ネットワーク](/glossary/ネットワーク/)にいる他の[コンテナ](/glossary/コンテナ/)からは、この名前に加えてサービス名でも届くため、名前を固定する理由はほとんどありません。

なお `container_name` を消したあとも、以前の名前で作られた[コンテナ](/glossary/コンテナ/)は残ります。Compose から見れば管理対象の外になるため、一度は手作業で消す必要があります。

### 原因5：削除が終わっていない、または予約だけが残っている

`docker rm` を実行した直後に作り直すと、まれに衝突します。[削除](/glossary/削除/)は即座には終わらず、その間の状態は `Removal In Progress` と表示されます。実装でも、[削除](/glossary/削除/)の開始時にこの印を立て、二重の削除要求を弾く作りになっています。

対処は待つことです。名前が一覧から消えたことを確かめてから次に進みます。自動処理では、消えるまで短い間隔で確認する手順を挟むのが確実です。

**Before（[削除](/glossary/削除/)の直後に作り直す）：**

```bash
docker rm -f web
docker run -d --name web nginx
```

**After（名前が消えたことを確かめてから作る）：**

```bash
docker rm -f web
until [ -z "$(docker ps -a --filter 'name=^/web$' --format '{{.Names}}')" ]; do sleep 0.2; done
docker run -d --name web nginx
```

まれに、予約だけが残って本体が消えている場合もあります。出力の [ID](/glossary/id/) を `docker inspect` に渡しても対象なしと返る状況です。この場合は[デーモン](/glossary/デーモン/)の再起動で解消したという報告があります。ただし他の[コンテナ](/glossary/コンテナ/)にも影響するため、先に一覧を控えてから行ってください。

## 補足：似ているが別のもの

`port is already allocated` は[ポート](/glossary/ポート/)の衝突で、名前とは無関係です。名前を変えても解消しません（[Docker の port is already allocated の記事](/posts/docker_port_is_already_allocated/)）。

`removal of container ... is already in progress` は、同じ[コンテナ](/glossary/コンテナ/)への削除要求が重なった場合です。こちらも 409 で返りますが、待てば解消します。

`You cannot remove a running container` は、動いている[コンテナ](/glossary/コンテナ/)を止めずに消そうとした場合です。名前ではなく、[削除](/glossary/削除/)の手順の問題になります。

[ネットワーク](/glossary/ネットワーク/)上の別名は、[コンテナ](/glossary/コンテナ/)名とは別の仕組みです。同じ[ネットワーク](/glossary/ネットワーク/)に属していなければ名前で呼び合えませんが、名前の予約自体は[ネットワーク](/glossary/ネットワーク/)に関係なく[デーモン](/glossary/デーモン/)全体で1つです。分けたつもりでも衝突します。

[デーモン](/glossary/デーモン/)が別なら名前は独立します。接続先が意図した[デーモン](/glossary/デーモン/)かどうかを疑う場面もあります（[Docker daemon に接続できない記事](/posts/docker_cannot_connect_daemon/)）。

## 切り分けの順序

1. 出力の後半にある[コンテナ](/glossary/コンテナ/) [ID](/glossary/id/) を控える。名前ではなくこの [ID](/glossary/id/) で追う。
2. その [ID](/glossary/id/) を `docker inspect` に渡し、状態と作成時刻を確認する。
3. 状態が `exited` なら原因1、`created` なら原因2、`Removal In Progress` なら原因5に進む。
4. `docker ps -a` で名前を確かめる。`-a` を付けないと停止済みが見えない。
5. 対象なしと返るなら、予約だけが残っている状況として原因5の後半を見る。
6. Compose を使っているなら、[プロジェクト](/glossary/プロジェクト/)名が意図したものかを確認する。既定は作業[ディレクトリ](/glossary/ディレクトリ/)の名前になる。
7. 設定に `container_name` があるかを確認する。あれば[プロジェクト](/glossary/プロジェクト/)ごとの分離が効かない。
8. 残すか消すかを決める。残すなら改名、消すなら[削除](/glossary/削除/)で、いずれも予約は解放される。

## 確認コマンド集

```bash
# 1. 出力に出た ID から、名前と状態と作成時刻を取り出す（最初に行う）
docker inspect --format '{{.Name}} {{.State.Status}} {{.Created}}' <ID>

# 2. 停止中を含めて、その名前のコンテナを厳密に探す
docker ps -a --filter "name=^/web$" --format '{{.ID}} {{.Names}} {{.Status}}'

# 3. 停止中のコンテナだけを一覧する
docker ps -a --filter "status=exited" --filter "status=created"

# 4. 名前を保ったまま退避する（予約は新しい名前へ移る）
docker rename web web-old

# 5. 予約している側を削除する（動いていれば -f が要る）
docker rm -f web

# 6. 使っていない停止済みコンテナをまとめて消す（消える対象を必ず確認する）
docker container prune --filter "until=24h"

# 7. Compose が使うプロジェクト名を確認する
docker compose config --format json | head -20

# 8. 接続先のデーモンを確認する（別のデーモンを見ている場合がある）
docker context ls
```

## Editor's Note

[削除](/glossary/削除/)した直後なのに名前が使えない、という現象の記録が [moby/moby の Issue #37698](https://github.com/moby/moby/issues/37698) に残っています。2018年8月22日に開かれ、現在も開いたままです。

報告者の[環境](/glossary/環境/)は継続的インテグレーションの基盤でした。`docker run --rm --name foo` で起動する前に、必ず `docker kill foo` と `docker rm foo` を実行しています。それにもかかわらず、`docker rm` の直後の `docker run` が名前の衝突で失敗する。発生率は全体の3%未満で、間欠的だと書かれています。

報告者は最初、`docker ps -a` を失敗時に走らせても、衝突相手として示された [ID](/glossary/id/) が出力に現れないと述べています。競合の窓が狭いのだろう、という見立てです。しかし追跡を続けたところ、失敗直後の一覧に古い[コンテナ](/glossary/コンテナ/)が `Removal In Progress` の状態で残っている場面を捉えました。ここで結論が変わります。競合ではなく、[削除](/glossary/削除/)が完了していないだけだったのです。

回避策として書かれたのは、名前が一覧から消えるまで短い間隔で確認し続ける処理でした。報告者はその過程について、`docker ps` に `-a` を付ける必要があると気付くまで手間取ったと書き添えています。動いている[コンテナ](/glossary/コンテナ/)だけを見ていては、名前を握っている相手が見えません。

この記録が示しているのは、名前の予約が[コンテナ](/glossary/コンテナ/)の見え方と一致しないという点です。実装でも、名前は専用の表に置かれ、その予約が消えるのは[削除](/glossary/削除/)の完了と改名のときだけです。`docker rm` が返ってきたことと、予約が解放されたことは別の出来事です。名前の衝突を追うときは、動いているかどうかではなく、予約がまだ残っているかどうかを見てください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*