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

Docker で 500 Internal Server Error が出たときは、どこが500を返したかを最初に見極めます。原因はほぼ次の3系統のいずれかです。第一に、Windows の Docker Desktop でエンジンが起動していない状態です。この場合「request returned Internal Server Error for API route and version ...」という形式のメッセージになります。第二に、docker pull や docker push の相手であるレジストリ（イメージの配布サーバー）側の障害です。この場合「received unexpected HTTP status: 500 Internal Server Error」という形式になります。第三に、Docker デーモン自身の内部エラーで、この場合はメッセージに具体的な原因（ディスク不足など）が含まれるのが普通です。

なお、デーモンが停止しているだけなら500にはなりません。その場合は「Cannot connect to the Docker daemon ... Is the docker daemon running?」という接続エラーになります。500は「相手まで届いたうえで、相手が内部エラーを返した」ことを示すコードです。

## エラーの概要

Docker のコマンド（docker ps、docker run など）は、裏側で Docker デーモンの API に HTTP リクエストを送って動いています。500 Internal Server Error は、その応答としてサーバー側（デーモン、その手前の中継役、またはレジストリ）が「内部でエラーが起きた」と返してきたことを意味します。

このため、500が出たという事実は「相手までリクエストが届いた」ことの証拠でもあります。デーモンのプロセスが停止している、ソケットファイルにアクセスできない、といった場合は HTTP の応答自体を受け取れないので、500ではなく Cannot connect to the Docker daemon という別のエラーになります。500の調査でデーモンの死活だけを疑うと原因を取り違えるので、まずエラーメッセージの文言全体を読みます。

## まず最初に：エラーメッセージの全体を読む

500エラーの文言は、発生源ごとに形式が決まっています。手元のメッセージと突き合わせてください。

「request returned Internal Server Error for API route and version http:////./pipe/docker_engine/...」という形式で、経路に docker_engine という文字が見えるなら、Windows の Docker Desktop の経路で発生しています（原因1）。

「received unexpected HTTP status: 500 Internal Server Error」という形式なら、500を返したのは docker pull や docker push の通信相手であるレジストリです（原因2）。

「Error response from daemon: 」に続けて具体的な内容（no space left on device など）が書かれているなら、デーモン自身が処理中のエラーをそのまま報告しています。対処はその文言に従います（原因3）。

「Cannot connect to the Docker daemon」や「permission denied」なら、それは500の問題ではありません（後述の補足を参照）。

## よくある原因と解決手順

### 原因1：Docker Desktop のエンジンが起動していない（Windows）

Windows の Docker Desktop 環境では、エンジンが起動していない、または起動の途中で止まっている状態で docker コマンドを実行すると、次のような500エラーが出ることが、公式リポジトリの多数の報告で確認されています。

```
$ docker ps
request returned Internal Server Error for API route and version
http:////./pipe/docker_engine/v1.24/containers/json, check if the server
supports the requested API version
```

対処の第一歩は、Docker Desktop の画面でエンジンの状態を確認することです。画面の左下などに Engine running と表示されるまで待ちます。Docker Desktop 自体を終了して起動し直すのが基本の対処です。それでもエンジンが起動しない場合は、Docker Desktop のメニューにある Troubleshoot（診断機能）からログや診断情報を確認できます。公式ドキュメントによると、Docker Desktop のデーモン関連のログは、仮想マシン内の各サービスの出力をまとめた init.log というファイルに記録されます。

なお、この状態は Docker 側のバージョン更新の直後に発生したという報告が複数あります。エンジンが起動しない状態が続く場合は、公式リポジトリ（docker/for-win）で同じバージョンの報告がないかを確認してください。

### 原因2：レジストリが500を返している

docker pull、docker push、docker login の相手はレジストリです。レジストリ側で障害が起きていると、手元の環境に問題がなくても次のような500エラーになります。

```
$ docker pull hello-world
Error response from daemon: received unexpected HTTP status: 500 Internal Server Error
```

Docker Hub（既定のレジストリ）からの取得でこれが出た場合、まず公式の稼働状況ページ https://www.dockerstatus.com/ を確認します。実際に2025年2月には、Docker Hub 側の障害により、どのイメージの取得もこの500エラーで失敗する事象が発生し、稼働状況ページに障害として掲載されました。障害中は手元でできることはなく、復旧を待って再実行するのが対処です。

会社内などで運用している私設のレジストリが相手の場合は、そのレジストリ側のログを確認します。500を返しているのはレジストリなので、原因の記録もレジストリ側に残ります。

### 原因3：デーモン自身の内部エラー

Docker デーモンは、処理中に分類できない内部エラーが起きた場合に500を返す実装になっています（Docker のソースコードで確認できます）。この場合、エラーメッセージには「Error response from daemon: 」に続けて、起きたことの具体的な文言が含まれるのが普通です。対処はこの文言が示す内容に従います。代表例として、イメージなどの保存先のディスクが満杯になると no space left on device という文言が含まれます。この場合の対処は次のとおりです。

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

メッセージの文言だけで原因が分からない場合は、デーモンのログを確認します。公式ドキュメントによると、systemd を使う Linux では次のコマンドで確認できます。

```bash
sudo journalctl -u docker.service -n 100 --no-pager
```

さらに詳しい記録が必要な場合は、設定ファイル /etc/docker/daemon.json に "debug": true を追加し、デーモンに設定を読み直させると、動作の詳細がログに出力されるようになります（公式ドキュメント記載の手順）。

## 補足：500ではない類似エラー

500の調査だと思っていたものが、実は別の問題であることがよくあります。「Cannot connect to the Docker daemon at ... Is the docker daemon running?」は、デーモンに到達できない状態です。Linux であれば sudo systemctl status docker でデーモンの稼働を確認し、停止していれば sudo systemctl start docker で起動します。起動に失敗する場合は journalctl -u docker.service で失敗の理由を確認します。「permission denied」がソケット（/var/run/docker.sock）絡みで出る場合は、実行ユーザーの権限の問題です。これらはいずれもデーモンが500を返したのではなく、そもそも応答を受け取れていない状態なので、調査の対象が異なります。

## 切り分けの順序

1. エラーメッセージの全体を読み、形式で発生源を特定する。docker_engine を含む API route 形式なら原因1、received unexpected HTTP status なら原因2、Error response from daemon: に具体的な文言が続くなら原因3、Cannot connect なら500以外の問題。
2. 原因1なら Docker Desktop のエンジン状態を確認し、再起動する。
3. 原因2なら、Docker Hub が相手であれば稼働状況ページを確認し、私設レジストリであればそちらのログを見る。
4. 原因3なら、文言の指す内容（ディスク不足など）に対処し、不明ならデーモンのログを確認する。

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

原因2の実例として、Docker Hub 側の障害の報告があります（[docker/hub-feedback #2439](https://github.com/docker/hub-feedback/issues/2439)、2025年2月）。報告者の環境では docker pull hello-world という最も基本的な取得すら「received unexpected HTTP status: 500 Internal Server Error」で失敗しており、複数の国の別々の接続元から試しても同じ結果でした。報告の経過では、当初は公式の稼働状況ページに障害が掲載されておらず、その後に掲載されて対応が進んだことが記録されています。手元の環境を疑う前に稼働状況ページを見る、掲載がなくても障害の可能性は残る、という2点がわかる実例です。

500というコード自体は「内部でエラーが起きた」以上のことを教えてくれません。Docker では、メッセージの文言の形式が発生源を示してくれるので、コードの数字ではなく文言の全体から調査を始めることが確実な近道です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*