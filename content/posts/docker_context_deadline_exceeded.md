---
title: "Docker の context deadline exceeded エラー：原因と解決策"
date: 2026-07-28
description: "context deadline exceeded は Docker 固有のエラーではなく、Go の標準の時間切れエラーです。したがって、どの締め切りが切れたのかを特定しない限り直りません。決め手は文言の末尾で、括弧が付かない場合、応答ヘッダの前に切れた場合、本体の転送中に切れた場合で、疑うべき場所が変わります。COMPOSE_HTTP_TIMEOUT を上げる助言は Compose v2 では効きません。"
tags: ["Docker"]
errorCode: "context deadline exceeded"
lastmod: 2026-07-28
service: "Docker"
error_type: "context deadline exceeded"
components: ["Daemon", "Registry", "Compose"]
related_services: ["Docker Compose", "Docker Hub", "BuildKit"]
trend_incident: false
---

## 冒頭まとめ

`context deadline exceeded` は、[Docker](/glossary/docker/) が独自に定義した[エラー](/glossary/エラー/)ではありません。[Docker](/glossary/docker/) が書かれている Go 言語の標準の仕組みが返す、時間切れを表す[エラー](/glossary/エラー/)です。Go のソースでは、この文字列を返す値が定義されており、時間切れかどうかを尋ねると真を返すことも明記されています。つまりこの文言が伝えているのは「何かの締め切りに間に合わなかった」という事実だけで、どこの締め切りかは書かれていません。だからこそ、締め切りの持ち主を特定しないまま設定をいじると、直らないまま時間だけが過ぎます。

特定の手がかりは、文言の末尾です。3通りあります。

括弧が何も付かず `context deadline exceeded` だけの場合、切れたのは呼び出し側が設定した締め切りです。末尾に `(Client.Timeout exceeded while awaiting headers)` が付く場合、[クライアント](/glossary/クライアント/)自身の制限時間が、応答の見出し部分が届く前に切れています。末尾が `(Client.Timeout or context cancellation while reading body)` の場合、見出しは届いており、本体の転送の途中で切れています。この2つの接尾辞は、Go の [HTTP](/glossary/http/) の実装の中でそれぞれ別の場所に定義されており、付く条件も違います。前者なら接続・名前解決・[プロキシ](/glossary/プロキシ/)・相手の無応答を、後者なら転送速度と転送量を疑う、という具合に、見るべき場所が変わります。

もう1つ、先に否定しておくべき助言があります。「`COMPOSE_HTTP_TIMEOUT` を大きくする」という案内が今も多く見つかりますが、[Docker](/glossary/docker/) Compose の公式文書には「Compose V2 では効果がない[環境変数](/glossary/環境変数/)」という一覧があり、この[環境変数](/glossary/環境変数/)はそこに挙げられています。設定しても何も変わりません。

境界も引いておきます。`context canceled` は時間切れではなく取り消しで、別の[エラー](/glossary/エラー/)です。Go のソースでも別の値として定義されています。

## エラーの概要

実際に見かける形を並べます。まず[イメージ](/glossary/イメージ/)の取得で出るもの。

```text
Error response from daemon: Get "https://registry-1.docker.io/v2/":
context deadline exceeded (Client.Timeout exceeded while awaiting headers)
```

次にビルドで出るもの。

```text
failed to solve: example:1.0: failed to resolve source metadata:
context deadline exceeded
```

そして転送の途中で切れたもの。進捗が途中まで進んでから止まるのが特徴です。

```text
example 23.80 MiB / 70.32 MiB [=========>--------]  33.85% 19s
context deadline exceeded (Client.Timeout or context cancellation while reading body)
```

3つ目の形は、[ネットワーク](/glossary/ネットワーク/)が切れているのではなく、転送が終わる前に締め切りが来たことを示します。進捗の数字が出ているなら、相手には届いていて、[通信](/glossary/通信/)も成立していた、ということです。

なお Go の定義では、この[エラー](/glossary/エラー/)は時間切れであると同時に「一時的」とも申告します。再実行で通ることがあるのはこのためですが、締め切りの側が短すぎる場合は何度やっても同じところで切れます。[リトライ](/glossary/リトライ/)で解決するかどうかは、進捗の位置が毎回同じかどうかで見当が付きます。

## まず最初に：末尾の括弧を読む

第一に、`context deadline exceeded` の直後を見ます。何も付いていないなら、[Docker](/glossary/docker/) やその周辺の[ソフトウェア](/glossary/ソフトウェア/)が自分で設けた締め切りです。この場合、[ネットワーク](/glossary/ネットワーク/)の設定を触っても意味がないことがあります。

第二に、`while awaiting headers` が付いているなら、相手からの最初の反応が返ってきていません。名前解決、[プロキシ](/glossary/プロキシ/)、経路、相手側の停止を順に確認します。

第三に、`while reading body` が付いているなら、[通信](/glossary/通信/)は成立し、転送が始まっています。疑うのは速度と量です。大きな[イメージ](/glossary/イメージ/)を細い[回線](/glossary/回線/)で取得している場合が典型です。

第四に、進捗表示があれば、切れる位置を2回以上見比べます。毎回ほぼ同じ位置・同じ秒数で切れるなら、締め切りが固定されている証拠です。毎回違う位置なら、回線側の不安定さを疑います。

## よくある原因と解決手順

### 原因1：応答の見出しが返る前に切れている

末尾が `while awaiting headers` の場合です。順に確認します。

まず、名前解決と到達性を [Docker](/glossary/docker/) の外から確かめます。

```bash
nslookup registry-1.docker.io
curl -sI --connect-timeout 10 https://registry-1.docker.io/v2/ | head -3
```

ここで止まるなら、[Docker](/glossary/docker/) ではなく[ネットワーク](/glossary/ネットワーク/)側の問題です。手元では通るのに [Docker](/glossary/docker/) からは通らない場合は、[プロキシ](/glossary/プロキシ/)の設定が [Docker](/glossary/docker/) に渡っていない可能性が高くなります。利用者の[環境変数](/glossary/環境変数/)を設定しても、常駐している側には届きません。

**Before（自分の[環境変数](/glossary/環境変数/)にだけ設定している）：**

```bash
export HTTPS_PROXY=http://proxy.example.com:8080
docker pull example:1.0
# → 常駐側は proxy を知らないままなので変わらない
```

**After（常駐側の設定として渡す）：**

```bash
sudo mkdir -p /etc/systemd/system/docker.service.d
sudo tee /etc/systemd/system/docker.service.d/proxy.conf > /dev/null <<'EOF'
[Service]
Environment="HTTP_PROXY=http://proxy.example.com:8080"
Environment="HTTPS_PROXY=http://proxy.example.com:8080"
Environment="NO_PROXY=localhost,127.0.0.1"
EOF
sudo systemctl daemon-reload
sudo systemctl restart docker
```

設定が効いているかは、次で確認できます。

```bash
docker info | grep -i proxy
```

### 原因2：本体の転送の途中で切れている

末尾が `while reading body` の場合です。[通信](/glossary/通信/)は成立しているので、[プロキシ](/glossary/プロキシ/)や名前解決を触っても直りません。

[Docker](/glossary/docker/) 側で調整できるのは、同時に取得する数と、取得の試行回数です。moby のソースでは、同時取得数の既定が3、取得の試行回数の既定が5と定義されています。細い[回線](/glossary/回線/)では、同時数を減らしたほうが1本あたりの速度が上がり、結果として締め切りに間に合うことがあります。

```json
{
  "max-concurrent-downloads": 1,
  "max-download-attempts": 10
}
```

この内容を `/etc/docker/daemon.json` に置き、常駐している側を再起動します。設定を変えたら、実際に反映されているかを確認してください。

```bash
docker info | grep -i "concurrent"
```

これで直らない場合、締め切りは [Docker](/glossary/docker/) のものではなく、呼び出している側の[ソフトウェア](/glossary/ソフトウェア/)のものです。後述の Editor's Note の例がこれにあたります。

### 原因3：Compose での時間切れ

Compose の実行中に出た場合、`COMPOSE_HTTP_TIMEOUT` を上げるという助言は使えません。公式文書に、Compose V2 では効果がない[環境変数](/glossary/環境変数/)として明記されています。この[環境変数](/glossary/環境変数/)は、Python で書かれていた古い Compose の時代のものです。当時の時間切れの文言は `An HTTP request took too long to complete` で、今の文言とはそもそも別物でした。

**Before（効かない[環境変数](/glossary/環境変数/)を設定する）：**

```bash
export COMPOSE_HTTP_TIMEOUT=300
docker compose up -d
```

**After（同時実行数を絞る）：**

```bash
export COMPOSE_PARALLEL_LIMIT=1
docker compose up -d
```

`COMPOSE_PARALLEL_LIMIT` は、常駐側への同時呼び出しの上限を指定する[環境変数](/glossary/環境変数/)として公式文書に載っています。一度に多くの[コンテナ](/glossary/コンテナ/)を起動しようとして詰まっている場合は、これで収まることがあります。

なお、[環境変数](/glossary/環境変数/)は書き出さないと Compose に渡りません。設定したのに変わらない場合は、`export` を忘れていないかを確認してください。

### 原因4：ビルド中に出た

`failed to solve` に続いて出た場合、時間切れが起きたのはビルドを担当する仕組みの側です。`failed to resolve source metadata` が付いていれば、土台となる[イメージ](/glossary/イメージ/)の情報を[レジストリ](/glossary/レジストリ/)へ問い合わせる段階です。原因1と同じ経路の問題を疑います。

ビルドの途中で、[コンテナ](/glossary/コンテナ/)の中から外部へ出る[通信](/glossary/通信/)が時間切れになる場合は、別の話です。この場合は、ビルドの際に[プロキシ](/glossary/プロキシ/)の設定を渡す必要があります。

```bash
docker build \
  --build-arg HTTP_PROXY="$HTTP_PROXY" \
  --build-arg HTTPS_PROXY="$HTTPS_PROXY" \
  --build-arg NO_PROXY="$NO_PROXY" \
  -t example:1.0 .
```

どちらの段階で切れているかは、出力のどこで止まったかで分かります。土台の取得の段階か、命令の実行の途中かを先に見てください。

## 補足：似ているが別のもの

`context canceled` は取り消しで、時間切れではありません。Go のソースでも別の値として定義されています。利用者による中断や、上位の処理が畳まれたことによる巻き添えで出ます。締め切りを延ばしても意味がありません。

`dial tcp <アドレス>: i/o timeout` は、接続そのものが確立できずに切れた形です。相手のアドレスには到達しようとしているが、応答がない状態を指します。`proxyconnect tcp:` が前に付いていれば、[プロキシ](/glossary/プロキシ/)への接続で止まっています。

[HTTP](/glossary/http/) の状態[コード](/glossary/コード/)として返る時間切れは、また別です。[Docker](/glossary/docker/) の応答に 504 が現れた場合の切り分けは別記事にあります（[Docker の 504 の記事](/posts/docker_504/)）。取得の頻度が多すぎて弾かれている場合は、時間切れではなく制限です（[Docker の 429 の記事](/posts/docker_429/)）。常駐側そのものに繋がらない場合は、時間切れの前に `Cannot connect to the Docker daemon` として現れます（[Docker の 500 の記事](/posts/docker_500/)）。

## 切り分けの順序

1. 文言の末尾を読む。括弧なし、`while awaiting headers`、`while reading body` のどれかを確定させる。
2. 進捗表示があれば、切れる位置を2回以上見比べる。同じ位置なら締め切りが固定、違う位置なら[回線](/glossary/回線/)の不安定さを疑う。
3. `while awaiting headers` なら、[Docker](/glossary/docker/) の外から名前解決と到達性を確かめる。外から通るなら[プロキシ](/glossary/プロキシ/)設定が常駐側に渡っているかを確認する。
4. `while reading body` なら、同時取得数を減らし、試行回数を増やす。それでも同じ位置で切れるなら、締め切りの持ち主は [Docker](/glossary/docker/) ではない。
5. Compose なら、`COMPOSE_HTTP_TIMEOUT` は効かない前提で考える。同時実行数を絞る方向を試す。
6. `failed to solve` が付いていればビルド側。土台の取得か、命令の実行中かを出力の位置で見分ける。
7. `context canceled` は別物として扱う。締め切りの調整では直らない。

## 確認コマンド集

```bash
# 1. Docker の外から到達性と名前解決を確認する
nslookup registry-1.docker.io
curl -sI --connect-timeout 10 https://registry-1.docker.io/v2/ | head -3

# 2. 常駐側に渡っているプロキシ設定を確認する
docker info | grep -i proxy

# 3. 同時取得数と試行回数の現在値を確認する
docker info | grep -i "concurrent"

# 4. 取得の様子を詳しく見る（切れる位置を確かめる）
docker pull --debug example:1.0

# 5. 常駐側の記録を見る（Linux）
journalctl -u docker --since "10 min ago" | tail -40

# 6. コンテナの中から外部への到達性を確かめる
docker run --rm alpine sh -c "nslookup registry-1.docker.io; wget -S -O /dev/null https://registry-1.docker.io/v2/"
```

## Editor's Note

締め切りの持ち主を取り違えると何が起きるかを示す実例として、開発環境を提供する ddev という道具に残る記録があります（[Timeout upgrading docker-compose after upgrading ddev to 1.24.5 on slower networks](https://github.com/ddev/ddev/issues/7298)）。2025年5月、この道具を 1.24.5 に上げたところ、起動のたびに約70メガバイトの[ファイル](/glossary/ファイル/)の取得が途中で止まり、`context deadline exceeded (Client.Timeout or context cancellation while reading body)` で失敗するようになった、という報告です。

読みどころは、参加者が書き残した数字です。ある人は1.62パーセント、18秒で停止。別の人は33.85パーセント、19秒で停止。位置は違うのに、秒数がほぼ揃っています。別の参加者が「20秒の固定値は不自然だ」と書いているとおり、原因は[回線](/glossary/回線/)ではなく、道具の側に新しく入った固定の締め切りでした。実際、この問題は次の版で修正されています。

もし文言の末尾を読まずに対処していたら、名前解決を変える、[プロキシ](/glossary/プロキシ/)を疑う、常駐側を再起動する、といった作業に時間を使ったはずです。しかし `while reading body` は「相手には繋がっていて、転送が始まっている」と告げていました。この一言が、疑うべき場所を[ネットワーク](/glossary/ネットワーク/)から呼び出し側へ移してくれます。

`context deadline exceeded` は、それ自体には何の情報もない[エラー](/glossary/エラー/)です。しかし括弧の中と、切れる位置と秒数を並べれば、締め切りの持ち主はかなり絞り込めます。設定を変える前に、まずそこを読んでください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*