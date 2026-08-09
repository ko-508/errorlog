---
title: "Docker の port is already allocated：原因と解決策"
date: 2026-08-03
description: "port is already allocated は OS が拒否した結果ではなく、Docker が自分の割り当て台帳を見て断った結果です。だから誰も待ち受けていなくても出ます。OS が拒否した場合は address already in use という別の文言になるため、どちらが断ったかは文言で見分けられます。"
tags: ["Docker"]
images: ["og/posts/docker_port_is_already_allocated.png"]
errorCode: "port is already allocated"
lastmod: 2026-08-03
service: "Docker"
error_type: "port is already allocated"
components: ["Engine", "Networking"]
related_services: ["Docker Compose", "Docker Desktop"]
trend_incident: false
---

## 冒頭まとめ

`port is already allocated` を見たとき、多くの人は「その[ポート](/glossary/ポート/)で何かが待ち受けている」と考えます。しかし実装を読むと、**この文言を出しているのは [Docker](/glossary/docker/) 自身の割り当て台帳**です。

[Docker](/glossary/docker/) は公開[ポート](/glossary/ポート/)を管理する専用の仕組みを持っており、アドレスと[プロトコル](/glossary/プロトコル/)ごとの対応表を内部に保持しています。要求された[ポート](/glossary/ポート/)をこの台帳と照合し、既に登録されていれば「Bind for アドレス:[ポート](/glossary/ポート/) failed: port is already allocated」という文言の[エラー](/glossary/エラー/)を返します。**この時点で、実際に接続を試みてはいません**。

したがって、`ss` や `lsof` で調べて誰も待ち受けていなくても、この[エラー](/glossary/エラー/)は出ます。台帳と実態がずれている状態です。

一方、基本[ソフトウェア](/glossary/ソフトウェア/)の側が拒否した場合、文言は変わります。

```text
Ports are not available: exposing port TCP 0.0.0.0:3000 -> 0.0.0.0:0:
  listen tcp 0.0.0.0:3000: bind: address already in use
```

**`port is already allocated` は [Docker](/glossary/docker/) の台帳、`address already in use` は基本[ソフトウェア](/glossary/ソフトウェア/)**。この2つを見分けることが、切り分けの出発点になります。

## エラーの概要

台帳が断った場合の典型です。

```text
docker: Error response from daemon:
  driver failed programming external connectivity on endpoint my-app
  (a1b2c3...): Bind for 0.0.0.0:8080 failed: port is already allocated.
```

前半の「外部接続の設定に失敗した」は経緯の説明で、読むべきは末尾です。`Bind for` に続くアドレスと[ポート](/glossary/ポート/)が、台帳で衝突した相手を示します。

アドレス部分にも意味があります。`0.0.0.0:8080` は全アドレスでの公開、`127.0.0.1:8080` は特定アドレスのみです。**公開先のアドレスが違えば、同じ[ポート](/glossary/ポート/)番号でも衝突しません**。`-p 127.0.0.1:8080:80` のようにアドレスを絞れば回避できる場合があります。

基本[ソフトウェア](/glossary/ソフトウェア/)が断った場合は、前掲のとおり `bind: address already in use` で終わります。こちらは実際に待ち受けを試みて失敗しているため、**必ず何かがその[ポート](/glossary/ポート/)を掴んでいます**。

## まず最初に：誰が掴んでいるかを3段階で確認する

第一に、[コンテナ](/glossary/コンテナ/)を対象に絞って確認します。公開[ポート](/glossary/ポート/)で絞り込む指定があるため、1行で答えが出ることがあります。

```bash
docker ps -a --filter publish=8080
```

**停止中の[コンテナ](/glossary/コンテナ/)も含めるため `-a` を付けます**。実行中だけを見て「誰もいない」と判断するのが典型的な見落としです。

第二に、[コンテナ](/glossary/コンテナ/)以外を確認します。

```bash
sudo ss -ltnp | grep :8080
```

第三に、文言を読み分けます。ここまでで誰も見つからず、しかも文言が `port is already allocated` であれば、台帳だけが残っている状態です。

## よくある原因と解決手順

### 原因1：停止中のコンテナが公開ポートを抱えている

最も多い形です。`docker ps` は実行中しか表示しないため、停止中の[コンテナ](/glossary/コンテナ/)が原因だと気付けません。

再起動方針が設定されている場合はさらに厄介です。停止したつもりでも、[Docker](/glossary/docker/) の起動時に復帰して公開[ポート](/glossary/ポート/)を取り直します。

**Before（実行中だけを見て判断する）：**

```bash
docker ps | grep 8080     # 何も出ない → 別の原因を探し始める
```

**After（停止中も含めて絞り込む）：**

```bash
docker ps -a --filter publish=8080
docker rm -f <コンテナ名>          # 不要なら削除する
```

構成をまとめて扱う道具を使っている場合、別の作業[ディレクトリ](/glossary/ディレクトリ/)の構成が残っていることもあります。その場合は、その構成の場所で一式を停止するのが確実です。

```bash
docker compose down --remove-orphans
```

### 原因2：Docker 以外のプロセスが待ち受けている

文言が `address already in use` の場合はこちらです。基本[ソフトウェア](/glossary/ソフトウェア/)が拒否しているため、必ず持ち主がいます。

```bash
sudo ss -ltnp | grep :8080
sudo lsof -i :8080
```

持ち主が判明したら、止めるか、公開する[ポート](/glossary/ポート/)を変えます。[コンテナ](/glossary/コンテナ/)の中の待ち受け[ポート](/glossary/ポート/)を変える必要はありません。**変えるのはホスト側だけ**です。

```bash
docker run -p 8081:8080 myapp      # ホスト側だけ 8081 に変える
```

### 原因3：台帳だけが残っている

誰も待ち受けていないのに `port is already allocated` が出る場合です。前述のとおり、[Docker](/glossary/docker/) は台帳を見て判断するため、実態とずれれば矛盾した結果になります。

見分け方があります。[ポート](/glossary/ポート/)の持ち主を調べたとき、**持ち主として [Docker](/glossary/docker/) の常駐プロセス自身や中継用のプロセスが出てくる**場合、[コンテナ](/glossary/コンテナ/)は既に無いのに掴んだままになっています。

```bash
sudo lsof -i :8080 | grep -E "dockerd|docker-proxy"
```

対処は常駐プロセスの再起動です。これで台帳が作り直されます。

```bash
sudo systemctl restart docker
```

**ただし、稼働中の[コンテナ](/glossary/コンテナ/)にも影響します**。再起動方針によっては復帰しますが、無停止が必要な[環境](/glossary/環境/)では影響範囲を確認してから実施してください。この形が繰り返し起きるなら、[コンテナ](/glossary/コンテナ/)の停止と削除の手順に問題がないかを見直すほうが根本的です。

### 原因4：Windows で予約されたポート範囲に当たっている

Windows では、独特の形で現れます。**[ポート](/glossary/ポート/)によって成否がばらつく**のが特徴です。ある番号は必ず失敗し、別の番号は通り、一度失敗した番号はその後も失敗し続ける、という挙動になります。

原因は、[ネットワーク](/glossary/ネットワーク/)変換の仕組みが大量の[ポート](/glossary/ポート/)範囲を予約していることです。実装を見ると、[Docker](/glossary/docker/) の台帳が読み取る予約情報は基本[ソフトウェア](/glossary/ソフトウェア/)ごとに実装が分かれており、Linux ではカーネルの設定[ファイル](/glossary/ファイル/)を読みますが、Windows では何も返さない実装になっています。つまり、Windows 側の予約は [Docker](/glossary/docker/) の台帳には反映されず、実際に待ち受けを試みる段階で失敗します。

```text
# 予約されている範囲を確認する（Windows）
netsh interface ipv4 show excludedportrange protocol=tcp
```

一覧に自分が使いたい番号が含まれていれば、これが原因です。対処は、予約範囲外の[ポート](/glossary/ポート/)を使うか、予約を整理して再起動することです。

### 原因5：expose と ports を混同している

設計の誤解による形です。**公開の指定（`ports` や `-p`）だけがホストの[ポート](/glossary/ポート/)を占有します**。`expose` は、その[コンテナ](/glossary/コンテナ/)が内部で待ち受けている[ポート](/glossary/ポート/)を記述するだけで、ホスト側には何も割り当てません。

したがって、この[エラー](/glossary/エラー/)を避けるために `expose` へ書き換えても意味がありません。逆に、`expose` しか書いていない[コンテナ](/glossary/コンテナ/)がこの[エラー](/glossary/エラー/)の原因になることもありません。

同じ[ネットワーク](/glossary/ネットワーク/)に属する[コンテナ](/glossary/コンテナ/)同士は、公開しなくても互いに[通信](/glossary/通信/)できます。ホストから直接触る必要が無いなら、そもそも公開しないという選択肢もあります。

## 補足：似ているが別のもの

`bind: address already in use` は基本[ソフトウェア](/glossary/ソフトウェア/)が返した拒否です。前述のとおり、必ず実際の持ち主がいます。台帳の不整合ではないため、常駐プロセスを再起動しても解決しません。

常駐プロセスに接続できない場合は別の[エラー](/glossary/エラー/)です（[Docker の Cannot connect to the Docker daemon の記事](/posts/docker_cannot_connect_daemon/)）。

[イメージ](/glossary/イメージ/)が起動できない場合や[容量](/glossary/容量/)が尽きた場合も、それぞれ別系統です（[Docker の exec format error の記事](/posts/docker_exec_format_error/)、[no space left on device の記事](/posts/docker_no_space_left_on_device/)）。

なお、1024 未満の[ポート](/glossary/ポート/)を公開しようとして[権限](/glossary/権限/)で弾かれる場合は、文言に[権限](/glossary/権限/)に関する記述が入ります。番号の衝突とは別の問題です。

## 切り分けの順序

1. 文言の末尾を読む。`port is already allocated` なら台帳、`address already in use` なら基本[ソフトウェア](/glossary/ソフトウェア/)。
2. `Bind for` のアドレスを読む。全アドレスか特定アドレスかで衝突の条件が変わる。
3. 停止中も含めて[コンテナ](/glossary/コンテナ/)を絞り込む。`-a` を忘れない。
4. [コンテナ](/glossary/コンテナ/)以外の待ち受けを確認する。
5. 誰も見つからないなら、台帳の不整合を疑う。持ち主が [Docker](/glossary/docker/) 自身なら確定。
6. 常駐プロセスの再起動は影響範囲を確認してから。
7. Windows で番号によって成否がばらつくなら、予約範囲を確認する。
8. `expose` への書き換えは解決策にならない。占有するのは公開の指定だけ。

## 確認コマンド集

```bash
# 1. 公開ポートでコンテナを絞り込む（停止中も含める）
docker ps -a --filter publish=8080

# 2. コンテナ以外の待ち受けを確認する
sudo ss -ltnp | grep :8080
sudo lsof -i :8080

# 3. 持ち主が Docker 自身かどうかを判定する（台帳の不整合の見分け）
sudo lsof -i :8080 | grep -E "dockerd|docker-proxy"

# 4. 現在の公開ポートを一覧する
docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

# 5. 構成をまとめて片付ける（孤児も含めて）
docker compose down --remove-orphans

# 6. 常駐プロセスを再起動して台帳を作り直す（影響範囲に注意）
sudo systemctl restart docker

# 7. Windows で予約されている範囲を確認する
netsh interface ipv4 show excludedportrange protocol=tcp

# 8. ホスト側のポートを Docker に選ばせる（衝突の回避）
docker run -P myapp
docker port <コンテナ名>
```

## Editor's Note

「誰も使っていないのに使用中だと言われる」——この[エラー](/glossary/エラー/)で最も混乱するのがこの状況です。それを証拠付きで記録した報告があります（[Bind for ip:port failed: port is already allocated](https://github.com/moby/moby/issues/36591)）。

2018年3月の報告で、内容が徹底しています。報告者は問題の[ポート](/glossary/ポート/)について調べ、待ち受けているプロセスを特定しました。**それは [Docker](/glossary/docker/) の常駐プロセスそのものでした**。プロセス番号、[ファイル](/glossary/ファイル/)記述子の番号、その記述子が指すソケット、カーネル側の記録まで辿り、同じソケットであることを確認しています。[コンテナ](/glossary/コンテナ/)は既に存在しないのに、掴んだままだったわけです。

そして報告にはこう書かれています。**現時点での唯一の回避策は常駐プロセスの再起動だが、それは停止時間を意味するので避けたい**。

同種の報告はもっと前からあります（[Cannot start containers: port is already allocated](https://github.com/moby/moby/issues/20486)）。2016年、[コンテナ](/glossary/コンテナ/)を起動しようとして同じ[エラー](/glossary/エラー/)が出た報告で、報告者は明確に書いています。ホスト上でその[ポート](/glossary/ポート/)を待ち受けているものは何も無い、そして別の[コンテナ](/glossary/コンテナ/)を同じ[ポート](/glossary/ポート/)で起動すると成功する、と。

**待ち受けの有無と、台帳の状態は別物です**。この2つがずれ得ることを知っていれば、「誰もいないのに」と悩む時間は要りません。文言が `port is already allocated` であれば、判断しているのは台帳です。まず[コンテナ](/glossary/コンテナ/)を停止中まで含めて探し、それでも見つからなければ、台帳が実態を追い越していないかを疑ってください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*