---
title: "Docker の 504 エラー：原因と解決策"
date: 2026-01-01
description: "Docker の 504 Gateway Timeout で最初に押さえるべき事実は、Docker デーモン自身は504を返さないことです（ソースコードで確認できます）。実際に504が発生するのは、docker pull / push の相手であるレジストリの前段のプロキシ、リモートのデーモンを公開しているプロキシ、コンテナ上のアプリの前段のプロキシの3か所で、received unexpected HTTP status などの文言から切り分けて解決します。"
tags: ["Docker"]
errorCode: "504"
lastmod: 2026-07-15
service: "Docker"
error_type: "504"
components: ["Registry"]
related_services: ["Docker Hub", "Docker Registry", "Nginx"]
trend_incident: false
---

## 冒頭まとめ

[Docker](/glossary/docker/) まわりの 504 Gateway Timeout で最初に確定させるべき事実は、[Docker](/glossary/docker/) [デーモン](/glossary/デーモン/)自身は504を返さない、ということです。[デーモン](/glossary/デーモン/)が[エラー](/glossary/エラー/)を [HTTP](/glossary/http/) のステータスに割り当てる実装（moby のソースコード）には504がそもそも存在せず、時間切れ系の内部[エラー](/glossary/エラー/)（deadline exceeded）ですら500に割り当てられています。したがって、[Docker](/glossary/docker/) の操作で504を見たとき、それを返しているのは必ず[デーモン](/glossary/デーモン/)以外のどこかの「中継役」です。実際に起きる場所は3つに絞れます。第一に、docker pull / push の通信経路にあるゲートウェイ（自前[レジストリ](/glossary/レジストリ/)の前段の Nginx や ingress、[Docker](/glossary/docker/) Hub 側の基盤）です。第二に、リモートの [Docker](/glossary/docker/) [デーモン](/glossary/デーモン/)をリバースプロキシ越しに公開している構成の、その[プロキシ](/glossary/プロキシ/)です。第三に、[コンテナ](/glossary/コンテナ/)で動かしている[アプリケーション](/glossary/アプリケーション/)の前段の[プロキシ](/glossary/プロキシ/)で、これは [Docker](/glossary/docker/) ではなく[プロキシ](/glossary/プロキシ/)とアプリの調査になります。

見分けは文言でつきます。received unexpected [HTTP](/glossary/http/) status: 504 Gateway Time-out や error parsing [HTTP](/glossary/http/) 504 response body なら、pull / push の経路の504です（原因1）。docker [コマンド](/glossary/コマンド/)全般がリモートデーモン相手に504になるなら、[デーモン](/glossary/デーモン/)の前の[プロキシ](/glossary/プロキシ/)です（原因2）。ブラウザや curl で[コンテナ](/glossary/コンテナ/)上のアプリにアクセスして504が返るなら、それは [Docker](/glossary/docker/) の問題ではありません（原因3として境界を示します）。

## エラーの概要

[Docker](/glossary/docker/) [デーモン](/glossary/デーモン/)は、[エラー](/glossary/エラー/)の種類ごとに返す [HTTP](/glossary/http/) ステータスを割り当てます。この割り当てはソースコード（moby の daemon/server/httpstatus/status.go）で確認でき、404・400・409・503・500 などへの割り当てはあっても、504への割り当ては存在しません。つまり Error response from daemon: で始まる[エラー](/glossary/エラー/)の中に504の数字が現れた場合も、その504は[デーモン](/glossary/デーモン/)が作ったものではなく、[デーモン](/glossary/デーモン/)が[レジストリ](/glossary/レジストリ/)などの通信相手から受け取ったものの転記です。

pull / push で504を受け取ったときの文言は、レジストリクライアントの実装（docker/distribution の registry/client/errors.go）で決まっており、2種類あります。

```text
Error response from daemon: received unexpected HTTP status: 504 Gateway Time-out
```

```text
Error response from daemon: error parsing HTTP 504 response body: invalid character '<' looking for beginning of value: "<html>\r\n<head><title>504 Gateway Time-out</title></head>\r\n..."
```

前者は、[レジストリ](/glossary/レジストリ/) [API](/glossary/api/) として想定外のステータスを受け取ったことを示します。後者はさらに手がかりが濃く、応答の本文が[レジストリ](/glossary/レジストリ/)の返す [JSON](/glossary/json/) ではなく HTML だったことを示します。[レジストリ](/glossary/レジストリ/)本体は HTML のエラーページを返さないため、この文言は「応答したのは[レジストリ](/glossary/レジストリ/)ではなく、その手前にいる何か（Nginx や[ロードバランサー](/glossary/ロードバランサー/)）だ」という強い証拠になります。

## まず最初に：どの操作の504かで3つに分岐する

docker pull・docker push・docker build の中の[イメージ](/glossary/イメージ/)取得で失敗し、上記のいずれかの文言が出ているなら、[レジストリ](/glossary/レジストリ/)経路の504です（原因1）。DOCKER_HOST や docker context でリモートの[デーモン](/glossary/デーモン/)に接続していて、pull に限らず操作全般が504になるなら、[デーモン](/glossary/デーモン/)の前に置いた[プロキシ](/glossary/プロキシ/)の504です（原因2）。docker [コマンド](/glossary/コマンド/)は成功していて、[コンテナ](/glossary/コンテナ/)で動くアプリへの [HTTP](/glossary/http/) アクセスが504を返すなら、返しているのは前段の[プロキシ](/glossary/プロキシ/)であり、調査対象は[プロキシ](/glossary/プロキシ/)の時間設定とアプリの応答時間です（原因3）。

## よくある原因と解決手順

### 原因1：レジストリの前段のゲートウェイが pull / push を打ち切っている

自前で運用する[レジストリ](/glossary/レジストリ/)（registry:2、Harbor、GitLab Container Registry など）は、多くの場合 Nginx や ingress の背後に置かれます。[イメージ](/glossary/イメージ/)の層（blob）の転送は1[リクエスト](/glossary/リクエスト/)が長く大きいため、前段の[プロキシ](/glossary/プロキシ/)の読み取り時間や本文サイズの制限が、通常の Web アプリ向けの値のままだと、大きな層の push や、ストレージが遅いときの pull で制限に達し、[プロキシ](/glossary/プロキシ/)が504を返します。[クライアント](/glossary/クライアント/)側では層ごとの再試行（Retrying in ... seconds）を繰り返した末に失敗する形で現れます。

**Before（Web アプリ向けの既定値のまま[レジストリ](/glossary/レジストリ/)を中継している設定）：**

```nginx
server {
    listen 443 ssl;
    server_name registry.example.com;

    location /v2/ {
        proxy_pass http://registry:5000;
        # proxy_read_timeout は既定のまま（大きな層の転送で時間切れになる）
        # client_max_body_size は既定のまま（大きな層の push が弾かれる）
    }
}
```

**After（[レジストリ](/glossary/レジストリ/)の転送に合わせて制限を広げる）：**

```nginx
server {
    listen 443 ssl;
    server_name registry.example.com;

    location /v2/ {
        proxy_pass http://registry:5000;
        client_max_body_size 0;        # 層のサイズ制限を外す
        proxy_read_timeout  900s;      # 層の転送時間に合わせて延長
        proxy_send_timeout  900s;
        proxy_request_buffering off;   # 大きな push をバッファせず流す
    }
}
```

切り分けの決め手は、[レジストリ](/glossary/レジストリ/)本体の[ログ](/glossary/ログ/)と前段の[ログ](/glossary/ログ/)の突き合わせです。[クライアント](/glossary/クライアント/)には504が返っているのに、[レジストリ](/glossary/レジストリ/)本体の[ログ](/glossary/ログ/)には 200 や 202 が並んでいて異常がない場合、打ち切ったのは前段です。逆に[レジストリ](/glossary/レジストリ/)本体の[ログ](/glossary/ログ/)に処理の遅延やストレージ（S3 など）への[エラー](/glossary/エラー/)が残っているなら、根本は[レジストリ](/glossary/レジストリ/)の後ろ側にあり、[プロキシ](/glossary/プロキシ/)の時間延長は対症にすぎません。相手が [Docker](/glossary/docker/) Hub の場合は手元で直せる設定はなく、公式の稼働状況ページ（https://www.dockerstatus.com）を確認し、復旧を待って再試行します。pull も push も層ごとに自動で再試行される設計のため、散発的な504は再実行で通ることがあります。

### 原因2：リモートデーモンの前のプロキシが長い API 呼び出しを打ち切っている

[Docker](/glossary/docker/) [デーモン](/glossary/デーモン/)をリモートから使う構成（DOCKER_HOST=tcp://... や docker context）で、[デーモン](/glossary/デーモン/)の前に[認証](/glossary/認証/)や [TLS](/glossary/tls/) 終端のためのリバースプロキシを置いている場合、その[プロキシ](/glossary/プロキシ/)の時間設定が [Docker](/glossary/docker/) [API](/glossary/api/) と相性の悪い点に注意が必要です。[Docker](/glossary/docker/) [API](/glossary/api/) には、docker pull や docker build のように1[リクエスト](/glossary/リクエスト/)が数分かかる呼び出しと、docker logs -f・docker events・docker attach のように応答が終わらないストリーミングの呼び出しが多く、[プロキシ](/glossary/プロキシ/)の読み取り[タイムアウト](/glossary/タイムアウト/)が応答の途中で発火すると、[クライアント](/glossary/クライアント/)には504が返ります。

**Before（一般的な Web 向け[タイムアウト](/glossary/タイムアウト/)のまま[デーモン](/glossary/デーモン/)を中継している設定）：**

```nginx
location / {
    proxy_pass http://unix:/var/run/docker.sock;
    # 既定の読み取りタイムアウトでは logs -f や大きな pull が途中で切れる
}
```

**After（長い呼び出しとストリーミングを前提にした設定）：**

```nginx
location / {
    proxy_pass http://unix:/var/run/docker.sock;
    proxy_read_timeout 3600s;   # 長時間の呼び出しに合わせる
    proxy_send_timeout 3600s;
    proxy_buffering    off;     # ストリーミング応答をため込まない
    proxy_http_version 1.1;
    proxy_set_header   Upgrade $http_upgrade;      # attach / exec の接続切替
    proxy_set_header   Connection $http_connection;
}
```

なお、[デーモン](/glossary/デーモン/)の [API](/glossary/api/) はホストのほぼ全権に相当します。[プロキシ](/glossary/プロキシ/)経由で公開する場合は、504の調査とあわせて、到達できる範囲と[認証](/glossary/認証/)の設計を必ず確認してください。

### 原因3：コンテナ上のアプリの前段のプロキシが返している（Docker の問題ではない）

docker [コマンド](/glossary/コマンド/)は正常で、[コンテナ](/glossary/コンテナ/)で動かしているアプリへの [HTTP](/glossary/http/) アクセスが504になる場合、その504を作っているのは前段の[プロキシ](/glossary/プロキシ/)（Nginx など）で、原因はアプリの応答が時間内に完成しないことです。[コンテナ](/glossary/コンテナ/)で動いていることは本質ではなく、調査の手順は [Nginx の 504 の記事](/posts/nginx_504/)がそのまま使えます。[プロキシ](/glossary/プロキシ/)の[エラーログ](/glossary/エラーログ/)の upstream timed out の行を起点に、[プロキシ](/glossary/プロキシ/)の時間設定とアプリの処理時間を突き合わせてください。

[Docker](/glossary/docker/) 固有の落とし穴として1つだけ区別しておくと、Compose 構成で上流の[コンテナ](/glossary/コンテナ/)が停止している場合、[プロキシ](/glossary/プロキシ/)から見れば接続の失敗なので、返るのは504ではなく502です。504が出ているなら接続自体はできており、「[コンテナ](/glossary/コンテナ/)に届いていない」のではなく「[コンテナ](/glossary/コンテナ/)の中の処理が遅い」方向を調べるのが近道です（この境界は [Nginx の 502 の記事](/posts/nginx_502/)で扱っています）。

## 補足：このコードではない類似エラー

Cannot connect to the [Docker](/glossary/docker/) daemon は、[デーモン](/glossary/デーモン/)に到達できていない状態で、[HTTP](/glossary/http/) のやり取り自体が成立していません（[docker_500 の記事](/posts/docker_500/)の補足を参照）。context deadline exceeded や Client.Timeout exceeded、net/http: [TLS](/glossary/tls/) handshake timeout を含む[エラー](/glossary/エラー/)は、手元の[クライアント](/glossary/クライアント/)側が時間切れで接続を打ち切ったもので、[サーバー](/glossary/サーバー/)から504が返ったのとは別の事象です。Error response from daemon: の直後に具体的な処理の失敗が書かれた500系は、[デーモン](/glossary/デーモン/)または[レジストリ](/glossary/レジストリ/)の内部[エラー](/glossary/エラー/)です（[docker_500 の記事](/posts/docker_500/)）。[Docker](/glossary/docker/) Hub の利用回数の制限は toomanyrequests の文言を伴う 429 で、時間切れではありません（[docker_429 の記事](/posts/docker_429/)）。pull access denied は[認証](/glossary/認証/)・権限系で、対象の存在と[権限](/glossary/権限/)を区別しない設計の[エラー](/glossary/エラー/)です（[docker_404 の記事](/posts/docker_404/)の補足を参照）。

## 切り分けの順序

1. どの操作で504が出たかを確認する。pull / push なら原因1、リモートデーモン経由の操作全般なら原因2、[コンテナ](/glossary/コンテナ/)上のアプリへのアクセスなら原因3（Nginx の 504 の手順へ）。
2. 文言を読む。error parsing [HTTP](/glossary/http/) 504 response body があれば、応答したのは[レジストリ](/glossary/レジストリ/)本体ではなく前段の[プロキシ](/glossary/プロキシ/)だと確定できる。
3. 原因1は、[レジストリ](/glossary/レジストリ/)本体の[ログ](/glossary/ログ/)と前段の[ログ](/glossary/ログ/)を突き合わせ、打ち切った層を特定する。本体が正常（200/202）なら前段の制限を広げ、本体側に遅延の記録があればストレージや負荷を調べる。
4. [Docker](/glossary/docker/) Hub 相手なら公式の稼働状況を確認し、復旧を待って再試行する。
5. 原因2は、[プロキシ](/glossary/プロキシ/)の読み取り[タイムアウト](/glossary/タイムアウト/)とストリーミング設定を [Docker](/glossary/docker/) [API](/glossary/api/) の長い呼び出しに合わせる。

## 確認コマンド集

```bash
# 1. レジストリ本体に前段を通さず到達できるか（レジストリのホスト上で）
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5000/v2/

# 2. 前段のプロキシ経由での応答を確認（error parsing の切り分け）
curl -i https://registry.example.com/v2/

# 3. 前段プロキシの504と、レジストリ本体のアクセスログを同時刻で突き合わせる
grep " 504 " /var/log/nginx/access.log | tail -5
docker logs registry --since 10m 2>&1 | tail -20

# 4. リモートデーモン構成の切り分け：プロキシを介さない接続と比較する
docker -H unix:///var/run/docker.sock version   # デーモンのホスト上で直接
docker version                                   # 普段の（プロキシ経由の）接続

# 5. デーモン側のログに該当時刻の記録があるかを確認
journalctl -u docker --since "10 minutes ago" | tail -20
```

## Editor's Note

原因1の実例として、Harbor（自前運用の[レジストリ](/glossary/レジストリ/)）の公開 issue に詳細な記録があります（[docker push received unexpected HTTP status: 504 Gateway Timeout](https://github.com/goharbor/harbor/issues/12126)）。[Kubernetes](/glossary/kubernetes/) 上に Helm で Harbor を立て、ingress 経由で公開した環境で、docker push が層のアップロード中に Retrying in 3 seconds の再試行を繰り返した末、received unexpected [HTTP](/glossary/http/) status: 504 Gateway Timeout で失敗した、という2020年の報告です。この記録の価値は、報告者自身が「[レジストリ](/glossary/レジストリ/)の[ログ](/glossary/ログ/)には 200 と 202 ばかりが並んでいて異常が見当たらない」と書き残している点にあります。[レジストリ](/glossary/レジストリ/)本体は正常に応答しており、504を作っていたのはその手前の中継層だった、という本記事の切り分けの決め手がそのまま現れています。約6年前の事例ですが、[レジストリ](/glossary/レジストリ/)を前段の[プロキシ](/glossary/プロキシ/)や ingress の背後に置く構成、層の転送が1[リクエスト](/glossary/リクエスト/)として長く大きいこと、[クライアント](/glossary/クライアント/)が層ごとに自動再試行することは現在も同じで、この構図は今日の自前[レジストリ](/glossary/レジストリ/)でもそのまま再現します。

[Docker](/glossary/docker/) の504は、[デーモン](/glossary/デーモン/)が返せないコードだからこそ、見た瞬間に「間に誰がいるか」を数える[エラー](/glossary/エラー/)です。pull / push の経路か、[デーモン](/glossary/デーモン/)の前か、アプリの前か。中継役を特定すれば、直すべき設定は自然に決まります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*