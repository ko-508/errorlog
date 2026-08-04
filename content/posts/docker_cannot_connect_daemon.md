---
title: "Docker daemon に接続できない：原因と解決策"
date: 2026-08-05T00:00:00+09:00
description: "Cannot connect と permission denied は同じ接続経路で起きますが、原因は別です。前者は接続先から応答を得られず、後者はソケットへ到達する権限がない状態です。sudoやchmodで隠す前に、接続先・稼働状態・ソケット権限の順で切り分けます。"
tags: ["Docker"]
images: ["og/posts/docker_cannot_connect_daemon.png"]
errorCode: "Cannot connect to the Docker daemon"
lastmod: 2026-08-05T00:00:00+09:00
service: "Docker"
error_type: "CannotConnectDaemon"
components: ["Docker CLI", "dockerd", "Unix socket"]
related_services: ["Docker Desktop", "systemd", "Rootless mode"]
trend_incident: false
---

## 冒頭まとめ

`Cannot connect to the Docker daemon` は、[Docker](/glossary/docker/)の操作役である `docker` コマンドが、実行役の `dockerd` と通信できなかったという意味です。

最初に押さえるべきは、**このエラーだけでは daemon が停止しているとは限らない**ことです。[Docker公式のトラブルシューティング](https://docs.docker.com/engine/daemon/troubleshoot/)にも、daemon が動いていない場合だけでなく、クライアントが別の接続先を向いていて、その接続先へ到達できない場合があると書かれています。

一方、次の `permission denied` は一段具体的です。

```text
permission denied while trying to connect to the Docker daemon socket at
unix:///var/run/docker.sock: dial unix /var/run/docker.sock:
connect: permission denied
```

これは、**daemon の停止を確認する前に、利用者がソケットへ接続する権限を疑うべき文言**です。Linuxでは通常、`/var/run/docker.sock` を通してDocker APIを呼びます。ソケットが `root:docker` の所有で、現在の利用者が有効な `docker` グループに入っていなければ、接続の時点で拒否されます。

2つは同じ接続失敗の系統ですが、同じ原因ではありません。読むべき部分は末尾です。

```text
connect: permission denied  → ソケットへの権限を確認する
connect: no such file ...   → 接続先またはdaemonの起動を確認する
connection refused          → 接続先に受け手がいるかを確認する
```

つまり、**`Is the docker daemon running?` という問いをそのまま答えにしない**ことが重要です。まずクライアントがどこへ接続しようとしているかを確定し、次にその接続先でdaemonが動いているか、最後に現在の利用者が接続できるかを見ます。

## エラーの概要

[Docker](/glossary/docker/) Engine は、`docker` というクライアント、`dockerd` という常駐処理、両者を結ぶAPIから成ります。`docker ps` や `docker compose up` を実行すると、クライアントが選択中の接続先へAPI要求を送ります。

daemonから応答を受け取れない場合は、次の形になります。

```text
Cannot connect to the Docker daemon at unix:///var/run/docker.sock.
Is the docker daemon running?
```

権限で拒否された場合は、より長い形になります。

```text
permission denied while trying to connect to the Docker daemon socket at
unix:///var/run/docker.sock: Get
"http://%2Fvar%2Frun%2Fdocker.sock/v1.51/containers/json":
dial unix /var/run/docker.sock: connect: permission denied
```

途中の `http://%2Fvar%2Frun%2Fdocker.sock/...` は、外部のWebサイトへ接続しているという意味ではありません。Docker CLIがUnixソケット上でHTTP形式のAPIを使うため、その内部表現がエラーに出ています。原因を示すのは末尾の `dial unix ... permission denied` です。

このエラーは、[イメージ](/glossary/イメージ/)の取得や[コンテナ](/glossary/コンテナ/)の作成より前に起きます。したがって、Dockerfile、Composeファイル、対象コンテナの設定を直しても解決しません。

## まず最初に：接続先・稼働状態・権限を分ける

第一に、クライアントの接続先を確認します。

```bash
docker context show
docker context ls
env | grep -E '^DOCKER_(HOST|CONTEXT)='
```

第二に、その接続先に合った方法でdaemonの稼働状態を確認します。通常のLinux版Docker Engineなら `systemctl`、Rootless modeなら `systemctl --user`、Docker Desktopならアプリ本体の状態を見ます。

第三に、Linuxの `/var/run/docker.sock` へ接続している場合だけ、ソケットの所有者と現在のグループを確認します。

```bash
stat -c '%A %U %G %n' /var/run/docker.sock
id -nG
```

第四に、`sudo docker info` で結果が変わるかを診断に使います。通常時と `sudo` 時がどちらも同じ `/var/run/docker.sock` を向き、通常時だけ `permission denied` になるなら、daemonの停止ではなく利用者側の権限に絞れます。接続先が違う場合は比較になりません。また、`sudo` を恒久策として使い続けると、後述する `~/.docker` の所有権問題を作ることがあります。

## よくある原因と解決手順

### 原因1：Docker daemonが起動していない

通常のLinux版Docker Engineでは、まずサービスの状態を確認します。

```bash
sudo systemctl is-active docker
sudo systemctl status docker --no-pager -l
```

`inactive` なら起動します。

```bash
sudo systemctl start docker
```

起動時に自動で立ち上げる場合は次のとおりです。[Docker公式](https://docs.docker.com/engine/install/linux-postinstall/#configure-docker-to-start-on-boot-with-systemd)では、Dockerとcontainerdの両サービスを有効にする手順が示されています。

```bash
sudo systemctl enable docker.service
sudo systemctl enable containerd.service
```

`failed` なら、再起動を繰り返す前にログを読みます。

```bash
sudo journalctl -u docker.service -n 100 --no-pager
```

代表例は `/etc/docker/daemon.json` の誤りです。とくに `hosts` を設定ファイルと起動引数の両方で指定すると、競合してdaemonが起動できない場合があります。この場合、接続エラーは結果であり、原因はdaemonのログに出ています。

### 原因2：`docker` グループが現在の接続に反映されていない

Linux版Docker Engineをroot権限で動かす標準的な構成では、daemonが `docker` グループから使えるUnixソケットを作ります。[公式の導入後手順](https://docs.docker.com/engine/install/linux-postinstall/#manage-docker-as-a-non-root-user)は、利用者をそのグループへ追加し、ログインし直すよう案内しています。

**Before（グループ一覧に `docker` がない）：**

```bash
id -nG
# user sudo ...
```

**After（グループを追加して、現在の接続へ反映する）：**

```bash
getent group docker >/dev/null || sudo groupadd docker
sudo usermod -aG docker "$USER"
newgrp docker
```

`usermod` が成功しても、すでに開いている端末の所属グループは自動では変わりません。いったんログアウトして入り直すか、`newgrp docker` で新しいシェルを開きます。仮想マシンでは再起動が必要な場合があることも公式文書に記載されています。

反映後に確認します。

```bash
id -nG
docker run --rm hello-world
```

ここには重要な注意があります。**`docker` グループは、一般利用者向けの弱い権限ではありません**。公式文書は、このグループがroot相当の権限を与えると警告しています。共有サーバーで、信頼できない利用者を安易に追加しないでください。

### 原因3：ソケットの所有者・グループが想定と違う

利用者が `docker` グループに入っているのに拒否される場合は、実際のソケットを見ます。

```bash
ls -l /var/run/docker.sock
stat -c 'mode=%A owner=%U group=%G path=%n' /var/run/docker.sock
namei -l /var/run/docker.sock
```

通常の構成では `docker` グループに読み書きが許可されます。ただし、手動でdaemonを起動した場合、別のサービス定義を使った場合、Docker DesktopやRootless modeと混在した場合は、接続先や所有グループが変わります。

ここで次の修正は避けます。

```bash
sudo chmod 666 /var/run/docker.sock
```

これは全利用者にDocker APIの操作を許可します。Dockerはホストの任意の場所を[コンテナ](/glossary/コンテナ/)へマウントできるため、[公式のセキュリティ文書](https://docs.docker.com/engine/security/#docker-daemon-attack-surface)はdaemonを操作できる利用者を信頼済みに限定するよう求めています。また、ソケットはdaemonの再起動時に作り直されるため、手作業の変更は恒久的な設定にもなりません。

所有者を直接書き換える前に、Dockerの起動方法と接続先を直してください。

### 原因4：`DOCKER_HOST` またはcontextが別のdaemonを向いている

daemonが動いているのに `Cannot connect` になる場合は、クライアントが別のソケットや遠隔ホストを見ている可能性があります。

```bash
docker context show
docker context ls
docker context inspect "$(docker context show)" \
  --format '{{ .Endpoints.docker.Host }}'
env | grep -E '^DOCKER_(HOST|CONTEXT)='
```

[Docker CLIの公式資料](https://docs.docker.com/reference/cli/docker/#environment-variables)では、`DOCKER_HOST` がdaemonの接続先を指定し、`DOCKER_CONTEXT` はその `DOCKER_HOST` と保存済みの既定contextを上書きすると説明されています。つまり `docker context use default` を実行しても、環境変数が残っていれば期待した接続先にならない場合があります。

誤って設定されていた場合は、現在のシェルから外します。

```bash
unset DOCKER_HOST DOCKER_CONTEXT
docker context use default
docker info
```

ただし、Rootless modeやDocker Desktopでは `default` が正解とは限りません。先に、使いたいdaemonが通常版、Rootless版、Desktop版のどれかを決めてください。

### 原因5：Rootless modeなのに通常版のソケットを見ている

Rootless modeでは、daemon自体も一般利用者として動きます。既定のソケットは `/run/user/<UID>/docker.sock` です。`/var/run/docker.sock` の権限を直す話ではありません。

[公式のRootless mode資料](https://docs.docker.com/engine/security/rootless/tips/#client)では、Docker Engine 23.0以降、設定道具が `rootless` contextを自動作成して選択します。まず状態とcontextを確認します。

```bash
systemctl --user is-active docker
docker context ls
docker context use rootless
docker info
```

一部の道具がcontextを読まず、`DOCKER_HOST` を必要とする場合は次の形です。

```bash
export DOCKER_HOST="unix://$XDG_RUNTIME_DIR/docker.sock"
```

通常版とRootless版を同時に置くと、動いているdaemonとCLIが見ているdaemonを取り違えやすくなります。`sudo docker ps` と `docker ps` で別の一覧が出る場合は、権限差ではなく別daemonへ接続している可能性があります。

### 原因6：Docker Desktopが停止している、またはcontextがずれている

macOSとWindowsでは、`dockerd` を `systemctl` で起動するのではなく、Docker Desktopを起動します。Linux版Docker Desktopも、ホストへ直接入れたDocker Engineとは別の環境です。

Linux版Docker Desktopは `desktop-linux` contextを作り、起動中はCLIの接続先として選びます。停止時には以前のcontextへ戻すため、ホスト側のDocker Engineと両方を入れている環境ではまずcontextを確認します。

```bash
docker context ls
docker context use desktop-linux
docker info
```

Linux版Docker Desktop本体は次でも起動できます。

```bash
systemctl --user start docker-desktop
```

さらに、Linux版Docker Desktopは `/var/run/docker.sock` ではなく、利用者ごとの `~/.docker/desktop/docker.sock` を使います。Docker CLIはcontextを通して自動で扱いますが、SDKなど、ソケットを直接見る道具には[公式FAQ](https://docs.docker.com/desktop/troubleshoot-and-support/faqs/linuxfaqs/)の説明どおり接続先の指定が必要です。

```bash
export DOCKER_HOST="unix://$HOME/.docker/desktop/docker.sock"
```

### 原因7：`sudo` の使用で `~/.docker` がroot所有になった

これはdaemonソケットの `permission denied` とは別です。次の警告なら、クライアント設定の所有権を直します。

```text
WARNING: Error loading config file: /home/user/.docker/config.json -
stat /home/user/.docker/config.json: permission denied
```

公式手順は次のとおりです。

```bash
sudo chown "$USER":"$USER" "$HOME/.docker" -R
sudo chmod g+rwx "$HOME/.docker" -R
```

`/var/run/docker.sock` と `~/.docker/config.json` は場所も役割も違います。前者はdaemonとの通信口、後者はクライアントの設定です。エラーに出たパスを見て分けてください。

## 補足：似ているが別のもの

`error during connect` の後に証明書の検証エラーが出る場合は、TCP接続とTLS証明書の問題です。daemon停止やUnixソケットのグループ設定ではありません。遠隔接続をHTTPで公開する場合、Docker公式はTLSとクライアント証明書で保護するよう案内しています。

`Cannot connect` の前後に `context deadline exceeded` が出る場合は、接続先が無応答または到達不能になっている可能性があります。ローカルのソケット権限だけでなく、遠隔ホスト、SSH、ネットワークを確認します。

`docker: command not found` はクライアント自体がない状態です。daemonへの接続はまだ試されていません。

`permission denied` が[コンテナ](/glossary/コンテナ/)内のファイル、マウント先、`entrypoint.sh` などを指している場合も、本記事のエラーとは別です。`Docker daemon socket at ...` または `dial unix ...` が含まれているかで判断してください。

## 切り分けの順序

1. エラー末尾を読む。`permission denied`、`no such file`、`connection refused` を分ける。
2. `docker context ls` と `DOCKER_HOST`、`DOCKER_CONTEXT` で実際の接続先を確定する。
3. 通常版、Rootless版、Desktop版のどのdaemonを使うのか決める。
4. 接続先に合った方法でdaemonの稼働状態を確認する。
5. `/var/run/docker.sock` への `permission denied` なら、ソケットの所有グループと `id -nG` を比べる。
6. グループを追加した直後なら、ログインし直すか `newgrp docker` で現在の接続へ反映する。
7. `sudo docker info` は原因を絞る診断にだけ使う。常用して設定ファイルの所有権問題を増やさない。
8. `chmod 666` でソケットを全利用者へ開放しない。起動方法、context、正しいグループ設定を直す。

## 確認コマンド集

```bash
# 1. Docker CLIが向いているcontextと接続先を確認する
docker context show
docker context ls
docker context inspect "$(docker context show)" --format '{{ .Endpoints.docker.Host }}'

# 2. 接続先を上書きする環境変数を確認する
env | grep -E '^DOCKER_(HOST|CONTEXT|TLS|CERT_PATH)='

# 3. 通常版Docker Engineの稼働状態を確認する
sudo systemctl is-active docker
sudo systemctl status docker --no-pager -l

# 4. daemonの直近ログを確認する
sudo journalctl -u docker.service -n 100 --no-pager

# 5. Unixソケットの所有者・グループ・権限を確認する
stat -c 'mode=%A owner=%U group=%G path=%n' /var/run/docker.sock

# 6. 現在のシェルに反映済みのグループを確認する
id
id -nG

# 7. 通常利用者とrootで結果が変わるか確認する
docker info
sudo docker info

# 8. Rootless版の状態を確認する
systemctl --user is-active docker
docker context inspect rootless --format '{{ .Endpoints.docker.Host }}'

# 9. Linux版Docker Desktopの状態を確認する
systemctl --user is-active docker-desktop
docker context inspect desktop-linux --format '{{ .Endpoints.docker.Host }}'

# 10. APIの応答まで確認する
docker version
docker info
```

## Editor's Note

このエラーの難しさは、**Docker CLIとdaemonが別の処理であること、さらに接続先が1つとは限らないことを、短い文言がほとんど説明していない**点にあります。

2014年4月、Mobyの課題に `dial unix /var/run/docker.sock: permission denied` という報告が登録されています（[dial unix /var/run/docker.sock: permission denied](https://github.com/moby/moby/issues/5314)）。報告者は、ソケットが `docker` グループに属することを確認し、自分をそのグループへ追加しても拒否された、と書いています。

この記録だけから最終原因は確定できません。ただし、現在も重要な落とし穴がそのまま現れています。**グループの登録情報と、すでに開いている端末に反映済みのグループは同じとは限りません**。そのため現在の公式手順にも、追加後にログインし直すか `newgrp docker` を実行する工程が残っています。

2024年10月には、同じ `permission denied while trying to connect ... /var/run/docker.sock` を見た利用者が、Docker Desktopを追加で入れる必要があるのかと尋ねる課題を登録しています（[Permission denied](https://github.com/docker/for-linux/issues/1502)）。少なくともDocker CLIは実行できており、拒否された場所は`docker load`する[イメージ](/glossary/イメージ/)ではありません。CLIから `/var/run/docker.sock` へ接続する段階です。

10年を隔てた2つの報告は、同じ読み違いを示します。利用者は `docker` という1つの道具を実行しているように見えますが、内部では**クライアント、接続先、権限、daemon**が分かれています。`permission denied` は「Dockerが壊れた」ではなく、その境界でOSに拒否されたという記録です。

さらに、一般形の `Cannot connect ... Is the docker daemon running?` は、接続先の指定ミスまでdaemon停止のように見せます。2025年2月のDocker CLIの課題では、`DOCKER_HOST=/invalid.sock` という不正な値が `tcp://localhost:2375/invalid.sock` と表示され、混乱を招くと指摘されました（[`DOCKER_HOST` without `unix://` prefix prints a confusing error](https://github.com/docker/cli/issues/5846)）。

だから、この文言を見て最初からdaemonを再インストールしないでください。**表示された接続先と末尾のOSエラーを先に読む**。停止、接続先のずれ、権限不足は、そこで初めて分かれます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
