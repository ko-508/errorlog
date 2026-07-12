---
title: "Docker の 500 エラー：原因と解決策"
date: 2026-01-01
description: "Docker の 500 Internal Server Error は、どこが500を返したかで対処が変わります。Docker Desktop のエンジン未起動、レジストリ側の障害、デーモン自身の内部エラーの3系統を、エラーメッセージの文言から切り分けて解決します。デーモンが停止しているだけなら500ではなく接続エラーになります。"
tags: ["Docker"]
errorCode: "500"
lastmod: 2026-07-02
service: "Docker"
error_type: "500"
components: []
related_services: []
trend_incident: true
top_queries:
- 'docker 500 internal server error'
- 'docker desktop 500 internal server error'
---

## 冒頭まとめ

[Docker](/glossary/docker/) で 500 Internal Server Error が出たときは、どこが500を返したかを最初に見極めます。原因はほぼ次の3系統のいずれかです。第一に、Windows の [Docker](/glossary/docker/) Desktop でエンジンが起動していない状態です。この場合「request returned Internal Server Error for [API](/glossary/api/) route and version ...」という形式のメッセージになります。第二に、docker pull や docker push の相手である[レジストリ](/glossary/レジストリ/)（[イメージ](/glossary/イメージ/)の配布[サーバー](/glossary/サーバー/)）側の障害です。この場合「received unexpected [HTTP](/glossary/http/) status: 500 Internal Server Error」という形式になります。第三に、[Docker](/glossary/docker/) [デーモン](/glossary/デーモン/)自身の内部[エラー](/glossary/エラー/)で、この場合はメッセージに具体的な原因（ディスク不足など）が含まれるのが普通です。

なお、[デーモン](/glossary/デーモン/)が停止しているだけなら500にはなりません。その場合は「Cannot connect to the [Docker](/glossary/docker/) daemon ... Is the docker daemon running?」という接続[エラー](/glossary/エラー/)になります。500は「相手まで届いたうえで、相手が内部[エラー](/glossary/エラー/)を返した」ことを示すコードです。

## エラーの概要

[Docker](/glossary/docker/) の[コマンド](/glossary/コマンド/)（docker ps、docker run など）は、裏側で [Docker](/glossary/docker/) [デーモン](/glossary/デーモン/)の [API](/glossary/api/) に [HTTP](/glossary/http/) [リクエスト](/glossary/リクエスト/)を送って動いています。500 Internal Server Error は、その応答として[サーバー](/glossary/サーバー/)側（[デーモン](/glossary/デーモン/)、その手前の中継役、または[レジストリ](/glossary/レジストリ/)）が「内部で[エラー](/glossary/エラー/)が起きた」と返してきたことを意味します。

このため、500が出たという事実は「相手まで[リクエスト](/glossary/リクエスト/)が届いた」ことの証拠でもあります。[デーモン](/glossary/デーモン/)のプロセスが停止している、ソケットファイルにアクセスできない、といった場合は [HTTP](/glossary/http/) の応答自体を受け取れないので、500ではなく Cannot connect to the [Docker](/glossary/docker/) daemon という別の[エラー](/glossary/エラー/)になります。500の調査で[デーモン](/glossary/デーモン/)の死活だけを疑うと原因を取り違えるので、まず[エラーメッセージ](/glossary/エラーメッセージ/)の文言全体を読みます。

## まず最初に：エラーメッセージの全体を読む

500[エラー](/glossary/エラー/)の文言は、発生源ごとに形式が決まっています。手元のメッセージと突き合わせてください。

「request returned Internal Server Error for [API](/glossary/api/) route and version http:////./pipe/docker_engine/...」という形式で、経路に docker_engine という文字が見えるなら、Windows の [Docker](/glossary/docker/) Desktop の経路で発生しています（原因1）。

「received unexpected [HTTP](/glossary/http/) status: 500 Internal Server Error」という形式なら、500を返したのは docker pull や docker push の通信相手である[レジストリ](/glossary/レジストリ/)です（原因2）。

「Error response from daemon: 」に続けて具体的な内容（no space left on device など）が書かれているなら、[デーモン](/glossary/デーモン/)自身が処理中の[エラー](/glossary/エラー/)をそのまま報告しています。対処はその文言に従います（原因3）。

「Cannot connect to the [Docker](/glossary/docker/) daemon」や「permission denied」なら、それは500の問題ではありません（後述の補足を参照）。

## よくある原因と解決手順

### 原因1：Docker Desktop のエンジンが起動していない（Windows）

Windows の [Docker](/glossary/docker/) Desktop 環境では、エンジンが起動していない、または起動の途中で止まっている状態で docker [コマンド](/glossary/コマンド/)を実行すると、次のような500[エラー](/glossary/エラー/)が出ることが、公式[リポジトリ](/glossary/リポジトリ/)の多数の報告で確認されています。

```
$ docker ps
request returned Internal Server Error for API route and version
http:////./pipe/docker_engine/v1.24/containers/json, check if the server
supports the requested API version
```

対処の第一歩は、[Docker](/glossary/docker/) Desktop の画面でエンジンの状態を確認することです。画面の左下などに Engine running と表示されるまで待ちます。[Docker](/glossary/docker/) Desktop 自体を終了して起動し直すのが基本の対処です。それでもエンジンが起動しない場合は、[Docker](/glossary/docker/) Desktop のメニューにある Troubleshoot（診断機能）から[ログ](/glossary/ログ/)や診断情報を確認できます。公式ドキュメントによると、[Docker](/glossary/docker/) Desktop の[デーモン](/glossary/デーモン/)関連の[ログ](/glossary/ログ/)は、仮想マシン内の各サービスの出力をまとめた init.log というファイルに記録されます。

なお、この状態は [Docker](/glossary/docker/) 側の[バージョン](/glossary/バージョン/)更新の直後に発生したという報告が複数あります。エンジンが起動しない状態が続く場合は、公式[リポジトリ](/glossary/リポジトリ/)（docker/for-win）で同じ[バージョン](/glossary/バージョン/)の報告がないかを確認してください。

### 原因2：レジストリが500を返している

docker pull、docker push、docker login の相手は[レジストリ](/glossary/レジストリ/)です。[レジストリ](/glossary/レジストリ/)側で障害が起きていると、手元の環境に問題がなくても次のような500[エラー](/glossary/エラー/)になります。

```
$ docker pull hello-world
Error response from daemon: received unexpected HTTP status: 500 Internal Server Error
```

[Docker](/glossary/docker/) Hub（既定の[レジストリ](/glossary/レジストリ/)）からの取得でこれが出た場合、まず公式の稼働状況ページ https://www.dockerstatus.com/ を確認します。実際に2025年2月には、[Docker](/glossary/docker/) Hub 側の障害により、どの[イメージ](/glossary/イメージ/)の取得もこの500[エラー](/glossary/エラー/)で失敗する事象が発生し、稼働状況ページに障害として掲載されました。障害中は手元でできることはなく、復旧を待って再実行するのが対処です。

会社内などで運用している私設の[レジストリ](/glossary/レジストリ/)が相手の場合は、その[レジストリ](/glossary/レジストリ/)側の[ログ](/glossary/ログ/)を確認します。500を返しているのは[レジストリ](/glossary/レジストリ/)なので、原因の記録も[レジストリ](/glossary/レジストリ/)側に残ります。

### 原因3：デーモン自身の内部エラー

[Docker](/glossary/docker/) [デーモン](/glossary/デーモン/)は、処理中に分類できない内部[エラー](/glossary/エラー/)が起きた場合に500を返す実装になっています（[Docker](/glossary/docker/) のソースコードで確認できます）。この場合、[エラーメッセージ](/glossary/エラーメッセージ/)には「Error response from daemon: 」に続けて、起きたことの具体的な文言が含まれるのが普通です。対処はこの文言が示す内容に従います。代表例として、[イメージ](/glossary/イメージ/)などの保存先のディスクが満杯になると no space left on device という文言が含まれます。この場合の対処は次のとおりです。

```bash
# 保存先パーティションの空きを確認（既定の保存先は /var/lib/docker）
df -h /var/lib/docker

# Docker が使っている容量の内訳を確認
docker system df

# 使われていないコンテナ・イメージ・ネットワークを削除
# （-a を付けると、どのコンテナからも使われていないイメージも削除される）
docker system prune -a
```

削除は元に戻せないため、docker system df で内訳を確認してから実行してください。

メッセージの文言だけで原因が分からない場合は、[デーモン](/glossary/デーモン/)の[ログ](/glossary/ログ/)を確認します。公式ドキュメントによると、systemd を使う Linux では次の[コマンド](/glossary/コマンド/)で確認できます。

```bash
sudo journalctl -u docker.service -n 100 --no-pager
```

さらに詳しい記録が必要な場合は、[設定ファイル](/glossary/設定ファイル/) /etc/docker/daemon.json に "debug": true を追加し、[デーモン](/glossary/デーモン/)に設定を読み直させると、動作の詳細が[ログ](/glossary/ログ/)に出力されるようになります（公式ドキュメント記載の手順）。

## 補足：500ではない類似エラー

500の調査だと思っていたものが、実は別の問題であることがよくあります。「Cannot connect to the [Docker](/glossary/docker/) daemon at ... Is the docker daemon running?」は、[デーモン](/glossary/デーモン/)に到達できない状態です。Linux であれば sudo systemctl status docker で[デーモン](/glossary/デーモン/)の稼働を確認し、停止していれば sudo systemctl start docker で起動します。起動に失敗する場合は journalctl -u docker.service で失敗の理由を確認します。「permission denied」がソケット（/var/run/docker.sock）絡みで出る場合は、実行ユーザーの[権限](/glossary/権限/)の問題です。これらはいずれも[デーモン](/glossary/デーモン/)が500を返したのではなく、そもそも応答を受け取れていない状態なので、調査の対象が異なります。

## 切り分けの順序

1. [エラーメッセージ](/glossary/エラーメッセージ/)の全体を読み、形式で発生源を特定する。docker_engine を含む [API](/glossary/api/) route 形式なら原因1、received unexpected [HTTP](/glossary/http/) status なら原因2、Error response from daemon: に具体的な文言が続くなら原因3、Cannot connect なら500以外の問題。
2. 原因1なら [Docker](/glossary/docker/) Desktop のエンジン状態を確認し、再起動する。
3. 原因2なら、[Docker](/glossary/docker/) Hub が相手であれば稼働状況ページを確認し、私設[レジストリ](/glossary/レジストリ/)であればそちらの[ログ](/glossary/ログ/)を見る。
4. 原因3なら、文言の指す内容（ディスク不足など）に対処し、不明なら[デーモン](/glossary/デーモン/)の[ログ](/glossary/ログ/)を確認する。

## 確認コマンド集

```bash
# 1. デーモンに到達できるか、基本情報が取れるかを確認
docker version
docker info

# 2. デーモンの稼働状態を確認（Linux）
sudo systemctl status docker

# 3. デーモンのログを確認（Linux、systemd 環境）
sudo journalctl -u docker.service -n 100 --no-pager

# 4. ディスクの空きと Docker の使用量を確認
df -h /var/lib/docker
docker system df

# 5. 使われていないデータを削除（内訳確認のうえで）
docker system prune -a
```

## Editor's Note

原因2の実例として、[Docker](/glossary/docker/) Hub 側の障害の報告があります（[docker/hub-feedback #2439](https://github.com/docker/hub-feedback/issues/2439)、2025年2月）。報告者の環境では docker pull hello-world という最も基本的な取得すら「received unexpected [HTTP](/glossary/http/) status: 500 Internal Server Error」で失敗しており、複数の国の別々の接続元から試しても同じ結果でした。報告の経過では、当初は公式の稼働状況ページに障害が掲載されておらず、その後に掲載されて対応が進んだことが記録されています。手元の環境を疑う前に稼働状況ページを見る、掲載がなくても障害の可能性は残る、という2点がわかる実例です。

500というコード自体は「内部で[エラー](/glossary/エラー/)が起きた」以上のことを教えてくれません。[Docker](/glossary/docker/) では、メッセージの文言の形式が発生源を示してくれるので、コードの数字ではなく文言の全体から調査を始めることが確実な近道です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*