---
title: "Docker の 429 エラー：原因と解決策"
date: 2026-01-01
description: "Docker の 429 Too Many Requests の大半は Docker Hub の pull 回数制限です。公式の現行制限は、匿名が6時間あたり100回で IPv4 アドレス（または IPv6 の /64）単位、認証済み Personal が200回でアカウント単位、有料プランは無制限です。鍵は匿名の枠が IP 単位で共有される点で、認証・ミラー・pull 削減の3方向で解決します。"
tags: ["Docker"]
errorCode: "429"
lastmod: 2026-07-15
service: "Docker"
error_type: "429"
components: ["Registry"]
related_services: ["Docker Hub", "Kubernetes", "GitHub Actions"]
trend_incident: false
---

## 冒頭まとめ

Docker の 429 Too Many Requests は、そのほとんどが Docker Hub の pull 回数制限です。公式文書に明記された現行の制限は、匿名（未認証）が6時間あたり100回、認証済みの Docker Personal が6時間あたり200回、Pro・Team・Business の有料プランはフェアユースの範囲で無制限です。ここで最も重要なのは回数の数字ではなく、数える単位です。匿名の枠は IPv4 アドレス（または IPv6 の /64 サブネット）単位で数えられるため、同じ NAT の下にいる社内の全マシン、CI の全ジョブ、Kubernetes クラスタの全ノードが1つの枠を共有します。自分はほとんど pull していないのに突然429になる場合、枠を使い切ったのは同じ IP を共有する誰かです。認証すると枠がアカウント単位に変わるため、対処の第一歩は回数を増やすことではなく、帰属を IP からアカウントに切り替えることです。

数えられ方も公式に定義されています。ローカルの確認だけで済む version check は消費に数えられず、通常のイメージの pull はマニフェスト1つで1回、マルチアーキテクチャのイメージは取得したアーキテクチャごとに1回と数えます。対処は3方向に整理できます。認証してアカウント単位の枠にする（原因1）、ミラーやキャッシュで pull の回数自体を減らす（原因2）、そして帰属や別種の制限を確認する（原因3）です。

## エラーの概要

制限を超えた状態でマニフェストを要求すると、Docker Hub は 429 と次の本文を返します。この文言は公式文書に掲載されているものです。

```text
You have reached your pull rate limit. You may increase the limit by authenticating and upgrading: https://www.docker.com/increase-rate-limits
```

CLI や Docker Engine のログでは toomanyrequests: を先頭に付けた形で現れます。Kubernetes 経由では、kubelet のイベント（ErrImagePull / ImagePullBackOff の理由）に同じ文言が記録されます。

現在の残量は、公式文書の手順でヘッダーから確認できます。この確認用リポジトリへの HEAD リクエストは枠を消費しません（GET は実際の pull と同様に消費します）。

```bash
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:ratelimitpreview/test:pull" | jq -r .token)
curl --head -H "Authorization: Bearer $TOKEN" https://registry-1.docker.io/v2/ratelimitpreview/test/manifests/latest
```

```text
ratelimit-limit: 100;w=21600
ratelimit-remaining: 20;w=21600
docker-ratelimit-source: 192.0.2.1
```

この例は「6時間（21600秒）あたり100回の枠のうち残り20回、枠の帰属は IP アドレス 192.0.2.1」という読み方をします。認証済みトークンで同じ確認をすると、docker-ratelimit-source が自分のアカウント帰属に変わったことを確かめられます。ratelimit 系のヘッダーが返らない場合は、有料プランや提携（公認イメージの提供元など）により無制限が適用されている状態で、その pull は制限に数えられません。

## まず最初に：3点を確認する

第一に、上記の手順で残量と docker-ratelimit-source を確認します。source が IP アドレスなら匿名の枠、アカウントならその認証の枠を使っています。第二に、その IP を誰と共有しているかを考えます。オフィスの NAT、CI ランナー、クラスタのノード群は、全員で匿名の1枠です。第三に、429を返しているのが本当に Docker Hub かを確認します。docker.io 以外のレジストリやミラーも429を返すことがあり、その場合の制限値と対処は各サービスの文書に従います。

## よくある原因と解決手順

### 原因1：匿名の pull で IP 単位の枠を共有している

CI・Kubernetes・社内ネットワークからの pull が認証なしで行われている構成が、429の最も多い形です。対処は認証で、枠が IP 単位からアカウント単位に変わることが本質です。パスワードではなくアクセストークン（PAT）を発行して使います。

**Before（匿名の pull。同じ IP の全員で6時間100回を分け合う）：**

```yaml
# GitHub Actions の例：ログインなしでビルド（ベースイメージの pull は匿名）
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t myapp .
```

**After（認証してアカウント単位の枠にする。公式文書が案内する方法）：**

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Login to Docker Hub
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}
      - run: docker build -t myapp .
```

手元のマシンでは docker login、Kubernetes では imagePullSecrets による認証を設定します（公式文書が Kubernetes の手順ページを案内しています）。Swarm では docker service create の --with-registry-auth が必要です。なお、公式文書には注意書きがあり、サードパーティのプラットフォーム経由では多数の利用者が同じ IP を共有するため、認証していても IP 単位の不正利用対策の制限（abuse rate limit。pull 回数制限とは別枠）に当たることがあります。

### 原因2：pull の回数自体が多すぎる

認証しても、クラスタの規模やジョブ数によっては枠や帯域を圧迫します。構造的な対処は、同じイメージの pull を1回にまとめることです。Docker はレジストリミラー（pull-through cache）を公式にサポートしており、デーモンの設定で全ノードの pull をミラー経由にできます。ミラーが一度取得したイメージはミラーから配られるため、Docker Hub への pull はキャッシュが切れたときの1回だけになります。

**Before（全ノード・全ジョブがそれぞれ Docker Hub から pull する）：**

```json
// /etc/docker/daemon.json（既定：ミラーなし）
{}
```

**After（自前のミラーを立て、全ノードの pull をそこ経由にする）：**

```json
// /etc/docker/daemon.json
{
  "registry-mirrors": ["https://mirror.internal.example.com"]
}
```

```bash
# ミラー本体は registry イメージのプロキシモードで動かせる
# （タグと詳細な構成は公式のミラー文書 docs.docker.com の最新版を参照）
docker run -d -p 443:5000 --name registry-mirror \
  -e REGISTRY_PROXY_REMOTEURL=https://registry-1.docker.io \
  registry:2
sudo systemctl restart docker
```

あわせて、pull を発生させない工夫も効きます。version check は消費に数えられないため、ローカルやミラーにイメージが残っていれば消費は起きません。CI ではランナーのイメージキャッシュを維持する、頻用するベースイメージは自組織のレジストリに複製してそこから参照する、という形で Docker Hub への依存回数そのものを減らせます。マルチアーキテクチャのイメージは取得アーキテクチャごとに1回と数えられる点も、多アーキ構成のクラスタで消費が想定より速い理由になります。

### 原因3：想定した枠が効いていない（帰属と別種の制限）

有料プランや認証を設定したのに429が出る場合、pull が意図したアカウントに帰属していない可能性があります。確認の起点は docker-ratelimit-source です。IP アドレスが表示されるなら、その経路の pull は匿名のままです（デーモン・CI・クラスタの一部だけ認証が漏れている構成が典型です）。また、公式文書のとおり、pull の帰属には規則があり、非公開リポジトリの pull はリポジトリの名前空間の所有者に帰属します。組織で契約しているのに個人アカウントで pull している、あるいはその逆で、意図しない側の枠を消費していることもあります。ヘッダーがまったく返らないなら無制限が効いており、pull 回数制限が原因の429ではないため、別種の制限（abuse rate limit）や Docker Hub 以外の429を疑います。

## 補足：このコードではない類似エラー

pull access denied は認証・権限系のエラーで、対象の存在と権限を区別しない設計です。回数制限とは無関係で、調査はログイン状態とリポジトリ名に向けます（[docker_404 の記事](/posts/docker_404/)の補足を参照）。Cannot connect to the Docker daemon はデーモン不達で、Docker Hub に到達する前の問題です（[docker_500 の記事](/posts/docker_500/)の補足を参照）。received unexpected HTTP status: 500 はレジストリ側の内部エラー、504 はレジストリ経路のゲートウェイの時間切れで、いずれも回数とは別の系統です（[docker_500 の記事](/posts/docker_500/)、[docker_504 の記事](/posts/docker_504/)）。また、GitHub API など他サービスの429は制限の仕組みも待ち方の指示も異なります（[GitHub API の 429 の記事](/posts/github_api_429/)、[AWS の 429 の記事](/posts/aws_429/)）。

## 切り分けの順序

1. エラー文言を確認する。toomanyrequests と pull rate limit を含むなら Docker Hub の回数制限で、この記事の調査を進める。別の文言なら補足の各記事へ。
2. 公式手順のヘッダー確認で、残量と枠の帰属（docker-ratelimit-source）を見る。
3. 帰属が IP なら、認証の導入と、その IP を共有する pull 元の洗い出しを行う（原因1）。
4. 認証済みでも消費が速いなら、ミラー・キャッシュ・複製で pull 回数を構造的に減らす（原因2）。
5. 有料・認証済みのはずなら、認証漏れの経路と帰属の規則、別種の制限を確認する（原因3）。
6. 枠の回復を待つ間に急ぐ場合は、対象イメージを認証済みの別経路で取得してノードに配る。

## 確認コマンド集

```bash
# 1. 残量と帰属の確認（HEAD は枠を消費しない。公式手順）
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:ratelimitpreview/test:pull" | jq -r .token)
curl --head -H "Authorization: Bearer $TOKEN" \
  https://registry-1.docker.io/v2/ratelimitpreview/test/manifests/latest 2>&1 | grep -i ratelimit

# 2. 認証済みの枠の確認（username と PAT を指定）
TOKEN=$(curl -s --user 'username:accesstoken' "https://auth.docker.io/token?service=registry.docker.io&scope=repository:ratelimitpreview/test:pull" | jq -r .token)
curl --head -H "Authorization: Bearer $TOKEN" \
  https://registry-1.docker.io/v2/ratelimitpreview/test/manifests/latest 2>&1 | grep -i ratelimit

# 3. デーモンのログイン状態とミラー設定の確認
cat ~/.docker/config.json | jq '.auths | keys'
docker info 2>/dev/null | grep -A2 "Registry Mirrors"

# 4. Kubernetes：429 を起こしている Pod のイベント確認
kubectl describe pod <pod-name> | grep -A3 "Events:"
```

## Editor's Note

原因1の実例として、Docker の公式フォーラムに2025年8月の報告があります（[You have reached your unauthenticated pull rate limit](https://forums.docker.com/t/you-have-reached-your-unauthenticated-pull-rate-limit-https-www-docker-com-increase-rate-limit/149370)）。Kubernetes のデプロイ中に、kubelet の busybox の pull が突然 toomanyrequests: You have reached your unauthenticated pull rate limit で失敗し、ErrImagePull になった、という記録で、報告者は「これまで一度も当たったことがないのに」と書いています。この「突然」の正体が、匿名の枠は IPv4 アドレス（または IPv6 の /64）単位で共有されるという現行仕様です。クラスタの全ノード、あるいは同じ出口 IP を使う他の利用者の pull がすべて合算されるため、自分の操作量と429の発生は必ずしも連動しません。執筆時点から約1年前の事例ですが、匿名100回・IP 単位という枠組みは現行の公式文書と同一で、kubelet の匿名 pull が共有枠を踏み抜くという構図は今日の未認証クラスタでそのまま再現します。

Docker Hub の429は、回数の問題である前に帰属の問題です。ratelimit ヘッダーで「誰の枠を使っているか」を確かめれば、認証で直るのか、構造を変えるべきなのかが最初に分かります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*