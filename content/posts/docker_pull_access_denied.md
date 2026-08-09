---
title: "Docker pull拒否エラー：原因と解決策"
date: 2026-08-05T00:00:00+09:00
description: "pull access denied は、権限不足だけを示すエラーではありません。存在しないリポジトリと、存在するが見られない非公開リポジトリが同じ案内へまとめられるためです。まずDockerが補完した完全なイメージ名を確定し、存在、認証、pull権限、タグの順で確認します。"
tags: ["Docker"]
images: ["og/posts/docker_pull_access_denied.png"]
errorCode: "pull access denied"
error_name: "pull access denied"
error_aliases:
  - "pull access denied for"
  - "repository does not exist"
  - "may require 'docker login'"
  - "may require authorization"
  - "denied: requested access to the resource is denied"
lastmod: 2026-08-05T00:00:00+09:00
service: "Docker"
error_type: "PullAccessDenied"
components: ["Docker CLI", "Docker Registry", "Docker Hub"]
related_services: ["BuildKit", "Docker Compose", "OCI Distribution"]
error_cases:
  - id: "docker-hub-library-namespace"
    label: "namespace"
    situation: "イメージ名を名前空間なしの短い名前で指定した場合に発生する"
    cause: "名前空間を省略し、Docker Hubのlibraryを見ている"
    messages:
      - "pull access denied for <image>"
      - "repository does not exist"
    check: "失敗ログに出た短いイメージ名が docker.io/library/<image>:latest に補完されていないか確認する"
    fix: "所有者の名前空間を含めた完全なイメージ名を指定する"
  - id: "repository-not-found"
    label: "repository"
    situation: "公開元の参照名と、ログに出たRegistry・所有者・リポジトリ名が一致しない"
    cause: "リポジトリ名、所有者名、Registryが違う"
    messages:
      - "repository does not exist"
      - "pull access denied for OWNER/IMAGE"
    check: "公開元のREADME、Composeファイル、CI変数、Registry画面で完全な参照名を照合する"
    fix: "正しいRegistry、所有者、リポジトリ名、タグへ直す"
  - id: "authentication"
    label: "authentication"
    situation: "private repositoryを未ログイン状態でpullした場合に発生する"
    cause: "非公開リポジトリへ未認証でアクセスしている"
    messages:
      - "may require 'docker login'"
      - "denied: requested access to the resource is denied"
    check: "対象イメージ名のRegistryとdocker loginのログイン先が一致しているか確認する"
    fix: "対象Registryへログインし、pull権限を持つ主体で取得する"
  - id: "pull-permission"
    label: "permission"
    situation: "docker loginでLogin Succeededと表示された後もpullが拒否される"
    cause: "ログインには成功したが、pull権限がない"
    messages:
      - "Login Succeeded"
      - "denied: requested access to the resource is denied"
    check: "ログインした利用者、team、role、トークンの許可範囲を確認する"
    fix: "Registry管理者または所有者側でreadまたはpull権限を付与する"
  - id: "missing-latest-tag"
    label: "tag"
    situation: "タグを省略したpullでmanifest unknownが表示される"
    cause: "タグを省略し、存在しないlatestを要求している"
    messages:
      - "manifest for OWNER/IMAGE:TAG not found"
      - "manifest unknown"
    check: "タグ省略によりlatestを要求していないか、公開済みタグが存在するか確認する"
    fix: "公開済みのタグまたはdigestを明示する"
  - id: "ci-auth-config"
    label: "ci"
    situation: "ローカルではpullできるがCIでは失敗する"
    cause: "CIだけ別の認証設定を使っている"
    messages:
      - "pull access denied for"
      - "may require 'docker login'"
    check: "pullするjob、実行ユーザー、DOCKER_CONFIG、builderの実行場所を確認する"
    fix: "pullする処理と同じjob、同じDocker設定でログインする"
  - id: "copy-from-stage-name"
    label: "dockerfile"
    situation: "DockerfileのCOPY --fromを使ったbuildで、stage名が外部イメージとして取得される"
    cause: "Dockerfileのstage名を間違え、外部イメージとしてpullしている"
    messages:
      - "pull access denied for build"
      - "repository does not exist or may require authorization"
    check: "COPY --from の値が定義済みstage名と一致しているか確認する"
    fix: "COPY --from を正しいstage名へ直す"
  - id: "buildkit-local-image"
    label: "buildkit"
    situation: "docker image inspectでは見つかる基礎イメージが、buildx buildではpullされる"
    cause: "ローカルだけにあるイメージを、別のbuilderがpullしようとしている"
    messages:
      - "pull access denied for <local-image>"
      - "repository does not exist or may require authorization"
    check: "docker image inspect、docker buildx ls、docker buildx inspectで保存先とbuilderを確認する"
    fix: "同じimage storeを使うbuilderを選ぶか、基礎イメージを共有Registryへpushする"
  - id: "compose-image-build"
    label: "compose"
    situation: "Docker Composeでimageだけを指定し、ローカルにイメージがない場合に発生する"
    cause: "Composeのimageとbuildの関係が想定と違う"
    messages:
      - "pull access denied for"
      - "repository does not exist or may require 'docker login'"
    check: "docker compose configでimageとbuildの展開後設定を確認する"
    fix: "ローカルビルドするサービスにはbuildを設定し、pullしたいimage名は完全な参照へ直す"
trend_incident: false
---

## 冒頭まとめ

`docker pull`、`docker run`、`docker compose up`、`docker build` で次の[エラー](/glossary/エラー/)が出た場合、[ログイン](/glossary/ログイン/)不足だけが原因とは限りません。

```text
Error response from daemon: pull access denied for OWNER/IMAGE,
repository does not exist or may require 'docker login':
denied: requested access to the resource is denied
```

この文は、考えられる原因をそのまま2つ並べています。

```text
repository does not exist
  → 指定したリポジトリが存在しない

may require 'docker login'
  → 非公開リポジトリで、認証またはpull権限が足りない
```

重要なのは、**`access denied` と表示されても、[リポジトリ](/glossary/リポジトリ/)が存在するとは限らない**ことです。反対に、`repository does not exist` と表示されても、削除済みとは限りません。非公開[リポジトリ](/glossary/リポジトリ/)は、[権限](/glossary/権限/)を持たない利用者からは存在を確認できない場合があります。

ただし、Registryの仕様が404と403を同じものとして定義しているわけではありません。[CNCF DistributionのRegistry HTTP API V2仕様](https://distribution.github.io/distribution/spec/api/)は、次のように区別しています。

| 状態 | [HTTP](/glossary/http/) | Registryのエラーコード |
|---|---:|---|
| [認証](/glossary/認証/)が必要 | 401 | `UNAUTHORIZED` |
| 操作を許可されていない | 403 | `DENIED` |
| [リポジトリ](/glossary/リポジトリ/)名が存在しない | 404 | `NAME_UNKNOWN` |
| [リポジトリ](/glossary/リポジトリ/)はあるが[タグ](/glossary/タグ/)やdigestがない | 404 | `MANIFEST_UNKNOWN` |

混同が起きるのは、その手前に認証処理があるためです。Registryは最初に401と `WWW-Authenticate` を返し、[クライアント](/glossary/クライアント/)は指定された[認証](/glossary/認証/)サービスへ、対象[リポジトリ](/glossary/リポジトリ/)の `pull` [権限](/glossary/権限/)を含む[トークン](/glossary/トークン/)を要求します。[権限](/glossary/権限/)のない主体には、要求した[権限](/glossary/権限/)を含まない[トークン](/glossary/トークン/)が返ることがあります。その後のRegistry要求は拒否され、[Docker](/glossary/docker/) [CLI](/glossary/cli/)は不存在と権限不足の両方を含む案内へまとめます。

したがって、最初に `docker login` を繰り返すのではなく、[Docker](/glossary/docker/)がどの名前へアクセスしたかを確定します。

```text
docker pull nginx
  → docker.io/library/nginx:latest

docker pull example/app
  → docker.io/example/app:latest

docker pull registry.example.com/team/app:1.2
  → registry.example.com/team/app:1.2
```

[Docker公式のイメージ名の説明](https://docs.docker.com/get-started/docker-concepts/building-images/build-tag-and-publish-an-image/)でも、`nginx` は `docker.io/library/nginx:latest` と同じ意味です。ホスト名、名前空間、[リポジトリ](/glossary/リポジトリ/)名、[タグ](/glossary/タグ/)のどれかが想定と違えば、正しい[アカウント](/glossary/アカウント/)で[ログイン](/glossary/ログイン/)しても直りません。

切り分けの中心は次の順序です。

```text
1. 実際に解決された完全なイメージ名を確認する
2. そのホストと名前空間にリポジトリが存在するか確認する
3. 非公開なら、そのRegistryへログインする
4. ログインした主体にpull権限があるか確認する
5. リポジトリへ入れた後で、指定したタグが存在するか確認する
```

## エラーの概要

[Docker](/glossary/docker/)で[イメージ](/glossary/イメージ/)を取得するとき、[Docker](/glossary/docker/) [CLI](/glossary/cli/)は直接[ファイル](/glossary/ファイル/)を探すのではありません。選択中の[Docker](/glossary/docker/) EngineまたはBuildKitが、[イメージ](/glossary/イメージ/)名からRegistryを決め、[認証](/glossary/認証/)を行い、manifestとlayerを順に取得します。

```text
Docker CLI
  ↓ pull要求
Docker EngineまたはBuildKit
  ↓ manifest要求
Registry
  ↓ 401と認証先・必要scope
認証サービス
  ↓ 許可された範囲のBearer token
Registry
  ↓ manifestとlayer、または拒否
```

[Registryのトークン認証仕様](https://distribution.github.io/distribution/spec/auth/token/)では、[クライアント](/glossary/クライアント/)が求めた操作と、その主体へ実際に許可された操作の共通部分を[トークン](/glossary/トークン/)へ入れます。たとえば `pull,push` を求めても、pullだけ許可されていればpullだけが入り、何も許可されていなければ空になります。[認証](/glossary/認証/)サービスは、この不足自体を[トークン](/glossary/トークン/)発行時の[エラー](/glossary/エラー/)にする必要はありません。

この仕組みでは、次の2つが利用者側で同じ拒否に見え得ます。

```text
その名前のリポジトリが存在しない
  → pullを許可する対象がない

非公開リポジトリは存在するが、その主体に権限がない
  → pullを許可できない
```

[Docker](/glossary/docker/) Hubでは、[非公開リポジトリは検索結果に表示されず、権限を与えられた利用者だけがアクセスできます](https://docs.docker.com/docker-hub/repos/manage/access/#repository-visibility)。そのため、[権限](/glossary/権限/)を持たない状態で画面検索とpullの両方に失敗しても、不存在とは確定できません。

一方、公開[リポジトリ](/glossary/リポジトリ/)へ到達できていて、[タグ](/glossary/タグ/)だけがない場合は、通常は次の系統になります。

```text
manifest for OWNER/IMAGE:TAG not found: manifest unknown
```

`pull access denied` は[リポジトリ](/glossary/リポジトリ/)へ入る境界、`manifest unknown` はその[リポジトリ](/glossary/リポジトリ/)内の[タグ](/glossary/タグ/)やdigestを探す境界です。ただし、非公開[リポジトリ](/glossary/リポジトリ/)では先に[認証](/glossary/認証/)で止まるため、存在しない[タグ](/glossary/タグ/)を指定していても、[権限](/glossary/権限/)を直すまでは `manifest unknown` に進めないことがあります。

## まず最初に：完全なイメージ名を確定する

第一に、失敗[ログ](/glossary/ログ/)に出た名前をそのまま読みます。

```text
pull access denied for my-app
```

この場合、[Docker](/glossary/docker/) Hub上の公式[イメージ](/glossary/イメージ/)用名前空間へ補完されます。

```text
docker.io/library/my-app:latest
```

自分の[Docker](/glossary/docker/) Hub[アカウント](/glossary/アカウント/) `example` にある `my-app` を取得したいなら、正しい指定は次です。

```bash
docker pull example/my-app:latest
```

第二に、ホスト名を確認します。

```text
example/my-app
  → Docker Hub

ghcr.io/example/my-app
  → GitHub Container Registry

registry.example.com/example/my-app
  → 指定したRegistry
```

[Docker](/glossary/docker/) Hubへ[ログイン](/glossary/ログイン/)しても、`ghcr.io` や自社Registryの[権限](/glossary/権限/)は得られません。[ログイン](/glossary/ログイン/)先は、[イメージ](/glossary/イメージ/)名の先頭にあるRegistryと一致させます。

第三に、[タグ](/glossary/タグ/)を確認します。[タグ](/glossary/タグ/)を省略すると `latest` が使われます。

```bash
docker pull example/my-app
# example/my-app:latest を要求する
```

公開済みの[タグ](/glossary/タグ/)が `v1.4.2` だけなら、`latest` は自動生成されません。存在する[タグ](/glossary/タグ/)を明示します。

```bash
docker pull example/my-app:v1.4.2
```

第四に、ComposeやDockerfileが実際に使う値を確認します。

```bash
docker compose config
docker build --progress=plain .
```

Composeの環境変数展開後に、`image:` が空、古い名前、別Registryになっていないかを見ます。ビルドでは、どの `FROM` または `COPY --from` の解決で止まったかを確認します。

## よくある原因と解決手順

### 原因1：名前空間を省略し、Docker Hubのlibraryを見ている {#docker-hub-library-namespace}

自分の[リポジトリ](/glossary/リポジトリ/)を短い名前だけで指定すると、[Docker](/glossary/docker/) Hub上の自分の[アカウント](/glossary/アカウント/)名は補完されません。

**Before（`docker.io/library/my-app:latest` を探す）：**

```bash
docker pull my-app
```

**After（所有者の名前空間を含める）：**

```bash
docker pull example/my-app:latest
```

DockerfileとComposeでも同じです。

```dockerfile
FROM example/my-app:latest
```

```yaml
services:
  app:
    image: example/my-app:latest
```

`docker login` は名前を修正する処理ではありません。`library/my-app` が存在しないなら、[Docker](/glossary/docker/) Hubへ[ログイン](/glossary/ログイン/)しても要求先は変わりません。

### 原因2：リポジトリ名、所有者名、Registryが違う {#repository-not-found}

次の違いはすべて別の取得先です。

```text
example/my-app
examples/my-app
example/myapp
registry.example.com/example/my-app
```

公開元のREADME、Compose[ファイル](/glossary/ファイル/)、CI[変数](/glossary/変数/)、Registry画面で、完全な参照名を照合します。特に組織移管、[リポジトリ](/glossary/リポジトリ/)削除、製品名変更の後は、古い参照が残ることがあります。

[Docker](/glossary/docker/) Hubの[リポジトリ](/glossary/リポジトリ/)名は作成後に変更できません。[Docker Hubの作成資料](https://docs.docker.com/docker-hub/repos/create/)にも、既存[リポジトリ](/glossary/リポジトリ/)はrenameできないと記載されています。名称を変えた運用では、通常は新しい[リポジトリ](/glossary/リポジトリ/)を作り、[イメージ](/glossary/イメージ/)を新しい参照へ公開します。古い名前が自動転送されるとは考えないでください。

### 原因3：非公開リポジトリへ未認証でアクセスしている {#authentication}

対象が非公開なら、まずそのRegistryへ[認証](/glossary/認証/)します。

[Docker](/glossary/docker/) Hubの場合は次のとおりです。

```bash
docker login
docker pull example/private-app:1.2
```

自社Registryの場合は、ホスト名と必要なら[ポート](/glossary/ポート/)を指定します。

```bash
docker login registry.example.com
docker pull registry.example.com/team/private-app:1.2
```

```bash
docker login registry.example.com:5000
docker pull registry.example.com:5000/team/private-app:1.2
```

[`docker login` の公式資料](https://docs.docker.com/reference/cli/docker/login/)では、[ログイン](/glossary/ログイン/)先に[URL](/glossary/url/)のpathを付けず、ホスト名と必要な[ポート](/glossary/ポート/)だけを指定します。

```bash
# 誤り
docker login registry.example.com/team

# 正しい形
docker login registry.example.com
```

CIでは、秘密を[コマンド](/glossary/コマンド/)[引数](/glossary/引数/)へ直接書かず、標準入力から渡します。

```bash
printf '%s' "$REGISTRY_TOKEN" |
  docker login registry.example.com \
    --username "$REGISTRY_USER" \
    --password-stdin
```

[トークン](/glossary/トークン/)本体、`~/.docker/config.json`、資格情報保存先の内容を[ログ](/glossary/ログ/)へ出さないでください。

### 原因4：ログインには成功したが、pull権限がない {#pull-permission}

`Login Succeeded` は、資格情報が[認証](/glossary/認証/)サービスに受け入れられたことを示します。任意の非公開[リポジトリ](/glossary/リポジトリ/)をpullできるという意味ではありません。

```text
Login Succeeded
denied: requested access to the resource is denied
```

この場合は、次を確認します。

```text
ログインした利用者が想定したアカウントか
対象が個人の非公開リポジトリならcollaboratorか
組織リポジトリなら、対象teamまたはroleにpull権限があるか
組織用トークンなら、対象リポジトリが許可範囲に含まれるか
```

[パスワード](/glossary/パスワード/)を何度作り直しても、対象[リポジトリ](/glossary/リポジトリ/)の許可は増えません。Registry管理者または[リポジトリ](/glossary/リポジトリ/)所有者側で、正しい主体へreadまたはpull[権限](/glossary/権限/)を付けます。

### 原因5：タグを省略し、存在しないlatestを要求している {#missing-latest-tag}

[タグ](/glossary/タグ/)を省略したときに使われる `latest` は、最新時刻の[イメージ](/glossary/イメージ/)を自動で探す機能ではありません。`latest` という名前の[タグ](/glossary/タグ/)です。

**Before（存在しない `latest` を要求）：**

```bash
docker pull example/my-app
```

**After（公開済みの[タグ](/glossary/タグ/)を明示）：**

```bash
docker pull example/my-app:1.4.2
```

[リポジトリ](/glossary/リポジトリ/)への参照権限がある状態なら、[タグ](/glossary/タグ/)不足は通常、次のように `manifest unknown` で判別できます。

```text
manifest for example/my-app:latest not found: manifest unknown
```

非公開[リポジトリ](/glossary/リポジトリ/)で[権限](/glossary/権限/)も[タグ](/glossary/タグ/)も不足している場合は、[権限](/glossary/権限/)の検査が先です。`pull access denied` を直した後に `manifest unknown` が現れることがあります。これは原因が変わったのではなく、次の検査段階まで進んだ結果です。

### 原因6：CIだけ別の認証設定を使っている {#ci-auth-config}

手元で `docker login` しても、その資格情報は自動でCIへ渡りません。[Docker](/glossary/docker/)は通常、実行した利用者の設定または資格情報保存先を使います。Linuxでは `$HOME/.docker/config.json`、Windowsでは `%USERPROFILE%/.docker/config.json` が標準の設定場所です。

CIでは、pullする処理と同じjob、同じ実行利用者、同じ[Docker](/glossary/docker/)設定で[ログイン](/glossary/ログイン/)します。

```bash
export DOCKER_CONFIG="$RUNNER_TEMP/docker-config"
mkdir -p "$DOCKER_CONFIG"

printf '%s' "$REGISTRY_TOKEN" |
  docker login registry.example.com \
    --username "$REGISTRY_USER" \
    --password-stdin

docker pull registry.example.com/team/app:1.2
```

`sudo docker pull` と通常の `docker login` を組み合わせると、資格情報を読む利用者が分かれる場合があります。権限回避のためだけに `sudo` を追加せず、[ログイン](/glossary/ログイン/)とpullを同じ実行環境へそろえます。

### 原因7：Dockerfileのstage名を間違え、外部イメージとしてpullしている {#copy-from-stage-name}

`COPY --from` の値は、以前のbuild stage、名前付きcontext、または外部[イメージ](/glossary/イメージ/)を指せます。[Dockerfileの公式仕様](https://docs.docker.com/reference/dockerfile#copy---from)にあるとおり、stage名として見つからなければ、[イメージ](/glossary/イメージ/)参照として解決される構成があります。

**Before（定義は `builder`、参照は `build`）：**

```dockerfile
FROM golang:1.25 AS builder
WORKDIR /src
COPY . .
RUN go build -o /out/app ./cmd/app

FROM scratch
COPY --from=build /out/app /app
```

[ログ](/glossary/ログ/)では、存在しない `build` という外部[イメージ](/glossary/イメージ/)を取得しようとして、次のように見えることがあります。

```text
pull access denied for build, repository does not exist or may require authorization
```

stage名を一致させます。

```dockerfile
FROM scratch
COPY --from=builder /out/app /app
```

この場合、Registryへの[ログイン](/glossary/ログイン/)は不要です。誤って外部[イメージ](/glossary/イメージ/)扱いされた文字列を直します。

### 原因8：ローカルだけにあるイメージを、別のbuilderがpullしようとしている {#buildkit-local-image}

Dockerfileに次の指定があるとします。

```dockerfile
FROM my-local-base:latest
```

通常の[イメージ](/glossary/イメージ/)保存先に `my-local-base:latest` があっても、選択中のBuildKit builderが別の保存領域を使っていれば、Registryへ取得しに行くことがあります。

```bash
docker image inspect my-local-base:latest
docker buildx ls
docker buildx inspect
```

ローカルの[Docker](/glossary/docker/) Engineと同じ保存先を使う必要があるなら、`docker` driverのbuilderを選びます。

```bash
docker buildx use default
docker buildx inspect
docker buildx build .
```

[`docker` driverの公式資料](https://docs.docker.com/build/builders/drivers/docker/)では、[Docker](/glossary/docker/) Engine内蔵のBuildKitを使い、作成結果をローカルのimage storeへ自動で読み込むと説明されています。一方、`docker-container`、`kubernetes`、`remote` driverは別のBuildKitを使います。builderの実行場所が別なら、基礎[イメージ](/glossary/イメージ/)を共有Registryへpushし、完全な参照名で取得できるようにします。

`--load` は、buildの**結果**をローカルのimage storeへ読み込む指定です。別のbuilderへ既存の基礎[イメージ](/glossary/イメージ/)を渡す指定ではないため、入力側の `pull access denied` を直す目的では使いません。

### 原因9：Composeのimageとbuildの関係が想定と違う {#compose-image-build}

Composeに `image:` だけがあれば、ローカルに見つからない場合はRegistryから取得します。

```yaml
services:
  app:
    image: example/app:latest
```

ローカルのDockerfileから作る意図なら、`build:` を設定します。

```yaml
services:
  app:
    build:
      context: .
    image: example/app:local
```

[環境変数](/glossary/環境変数/)を使っている場合は、展開後の値を確認します。

```yaml
services:
  app:
    image: ${REGISTRY}/${NAMESPACE}/app:${IMAGE_TAG}
```

```bash
docker compose config
```

空の[変数](/glossary/変数/)、余分な `/`、誤ったRegistry、意図しない `latest` がないかを見ます。

## 補足：似ているが別のもの

### manifest unknown

```text
manifest unknown
manifest for OWNER/IMAGE:TAG not found
```

[リポジトリ](/glossary/リポジトリ/)への参照には進めたものの、指定した[タグ](/glossary/タグ/)またはdigestに対応するmanifestがない状態です。[リポジトリ](/glossary/リポジトリ/)名ではなく、[タグ](/glossary/タグ/)、digest、公開処理を確認します。

### no matching manifest for linux/arm64

```text
no matching manifest for linux/arm64/v8 in the manifest list entries
```

[タグ](/glossary/タグ/)は存在しますが、現在の[OS](/glossary/os/)・CPUに対応するmanifestがありません。`--platform`、公開済みの対応環境、multi-platform buildを確認します。[認証](/glossary/認証/)の問題ではありません。

### too many requests

[Docker](/glossary/docker/) Hubのpull回数制限は、`pull access denied` ではなく429と制限用の文言で返されます。[Docker Hub公式のpull制限資料](https://docs.docker.com/docker-hub/usage/pulls/#view-pull-rate-and-limit)にも、上限到達時はmanifest要求へ429を返すと記載されています。[ログイン](/glossary/ログイン/)や契約によって上限条件は変わりますが、[リポジトリ](/glossary/リポジトリ/)名の修正とは別の問題です。

### x509、connection refused、timeout

```text
x509: certificate signed by unknown authority
connect: connection refused
i/o timeout
```

これらは、Registryへの[TLS](/glossary/tls/)検証、接続、通信時間切れです。Registryから `DENIED` や `NAME_UNKNOWN` を受け取る前の失敗なので、権限追加ではなく[証明書](/glossary/証明書/)、ホスト名、port、proxy、firewallを確認します。

### requested access to the resource is deniedがpushで出る

`docker push` では、pullではなくpush[権限](/glossary/権限/)が必要です。正しい[リポジトリ](/glossary/リポジトリ/)へ[ログイン](/glossary/ログイン/)できていても、read-onlyの主体はpushできません。また、[タグ](/glossary/タグ/)付けした参照の名前空間が自分の所有先かを確認します。

```bash
docker image tag app:local example/app:1.0
docker push example/app:1.0
```

## 切り分けの順序

1. [エラー](/glossary/エラー/)を出した処理がpull、run、Compose、Dockerfileのどれかを確認する。
2. [ログ](/glossary/ログ/)に出た[イメージ](/glossary/イメージ/)名を、Registry、名前空間、[リポジトリ](/glossary/リポジトリ/)、[タグ](/glossary/タグ/)へ分ける。
3. 省略されたRegistryが `docker.io`、名前空間が `library`、[タグ](/glossary/タグ/)が `latest` になっていないか確認する。
4. 公開元の資料またはRegistry画面で、完全な参照名が正しいか確認する。
5. 非公開なら、[イメージ](/glossary/イメージ/)名と同じRegistryへ[ログイン](/glossary/ログイン/)する。
6. [ログイン](/glossary/ログイン/)した主体が想定した[アカウント](/glossary/アカウント/)か、対象へのpull[権限](/glossary/権限/)があるか確認する。
7. [権限](/glossary/権限/)を通過した後、[タグ](/glossary/タグ/)またはdigestが存在するか確認する。
8. Dockerfileなら、`FROM` と `COPY --from` のstage名を確認する。
9. Composeなら、`docker compose config` で環境変数展開後の `image:` と `build:` を確認する。
10. CIやBuildKitだけで失敗するなら、資格情報の保存先とbuilderの実行場所を確認する。

## 確認コマンド集

直接pullし、対象名と最終[エラー](/glossary/エラー/)を確認します。

```bash
docker pull OWNER/IMAGE:TAG
```

ローカルにある[イメージ](/glossary/イメージ/)名とdigestを確認します。

```bash
docker image ls --digests
docker image inspect OWNER/IMAGE:TAG
```

manifestを取得できるか確認します。

```bash
docker manifest inspect OWNER/IMAGE:TAG
```

Composeの展開後設定を確認します。

```bash
docker compose config
docker compose config --images
```

Dockerfileの取得位置を詳しく表示します。

```bash
docker build --progress=plain .
```

BuildKit builderを確認します。

```bash
docker buildx ls
docker buildx inspect
```

現在の[Docker](/glossary/docker/)設定場所を確認します。

```bash
printf 'DOCKER_CONFIG=%s\n' "${DOCKER_CONFIG:-$HOME/.docker}"
```

自社Registryへ安全な形で[ログイン](/glossary/ログイン/)します。

```bash
printf '%s' "$REGISTRY_TOKEN" |
  docker login registry.example.com \
    --username "$REGISTRY_USER" \
    --password-stdin
```

資格情報や[トークン](/glossary/トークン/)の本文は表示しません。

## Editor's Note

`pull access denied` の文言が不存在と権限不足を同時に挙げる理由は、Mobyの実装履歴に残っています。

2018年8月の変更（[Include original error when translating distribution errors](https://github.com/moby/moby/commit/99fc4ca2bd5071d55cfbf4f63a1465c5aa0f146a)）には、2つの比較例があります。

```text
存在するbusyboxに、存在しないタグを指定
  → manifest for busybox:... not found

存在しないnosuchimageを指定
  → pull access denied for nosuchimage,
     repository does not exist or may require 'docker login'
```

同じ変更の[コード](/glossary/コード/)では、Registryから `DENIED` を受け取ったときに複合案内を作り、`MANIFEST_UNKNOWN` なら `manifest ... not found`、`NAME_UNKNOWN` なら `repository ... not found` と分けています。つまり、[Docker](/glossary/docker/) [CLI](/glossary/cli/)がすべての404を[権限](/glossary/権限/)[エラー](/glossary/エラー/)へ変換する実装ではありません。

それでも存在しない `nosuchimage` が `DENIED` になったのは、[クライアント](/glossary/クライアント/)から見たRegistryの応答が権限拒否だったためです。[認証](/glossary/認証/)の境界で存在を確認できなければ、[クライアント](/glossary/クライアント/)は「本当にない」と「あるが見られない」を確定できません。その不確定さが、`repository does not exist or may require 'docker login'` という二者択一の文になっています。

この構造は、ビルド機能が増えた後には別の混乱も生みました。2025年のMobyの課題（[Buildkit only wants to download images and refuse to use local images](https://github.com/moby/moby/issues/49542)）では、ローカルにある基礎[イメージ](/glossary/イメージ/)を使う意図でも、`docker-container` driverのBuildKitがRegistryから解決しようとして、`pull access denied` になった例が報告されています。

また、2018年の[Docker](/glossary/docker/) [CLI](/glossary/cli/)の課題（[Unable to use COPY --from, docker build trying to pull image](https://github.com/docker/cli/issues/1559)）では、`COPY --from` の値が外部[イメージ](/glossary/イメージ/)として解釈され、同じ文言が出ています。これらは、対象[リポジトリ](/glossary/リポジトリ/)の[権限](/glossary/権限/)を直す問題ではありません。Registryへ取りに行くはずのない名前が、[イメージ](/glossary/イメージ/)参照として解決されたことが原因です。

だから、この[エラー](/glossary/エラー/)を見たときの最初の問いは「[ログイン](/glossary/ログイン/)したか」ではありません。**[Docker](/glossary/docker/)は、どの文字列を、どのRegistryの、どの[リポジトリ](/glossary/リポジトリ/)として取得しようとしたのか**です。完全な参照名が正しいと確認できてから、存在と[権限](/glossary/権限/)を分けます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
