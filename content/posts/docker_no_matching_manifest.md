---
title: "no matching manifestの対処法"
date: 2026-09-29
draft: false
description: "Dockerのno matching manifest forは、指定したイメージのタグに要求したOS・CPU向けの版がないときに発生します。対応プラットフォームと指定元を照合し、タグや--platformを見直す手順を解説します。"
tags: ["Docker"]
images: ["og/posts/docker_no_matching_manifest.png"]
errorCode: "no matching manifest for"
urgency: "medium"
service: "Docker"
error_type: "platform_mismatch"
components: ["image", "manifest", "buildx"]
related_services: []
trend_incident: false
---

## 冒頭まとめ

`docker pull`や`docker run`、Dockerfileのビルドで次のように止まることがあります。

```text
no matching manifest for linux/amd64 in the manifest list entries
```

この場合、まず**要求しているプラットフォーム**と、**そのイメージのタグに用意されているプラットフォーム**を比べます。例の`linux/amd64`は「Linux用、x86-64 CPU向け」という要求です。イメージの名前だけでなく、タグも含めて確認してください。

```bash
docker buildx imagetools inspect <image>:<tag>
```

表示された`Platform:`の一覧に要求したものがなければ、そのタグのまま同じプラットフォームを指定し直しても解決しません。対応するタグを選ぶか、利用可能な別のプラットフォームを指定します。自分で配布するイメージなら、そのプラットフォーム向けの版をビルドして公開します。[Docker公式の確認コマンド](https://docs.docker.com/reference/cli/docker/buildx/imagetools/inspect/)に一覧の表示例があります。

## no matching manifest forとは

複数の環境に対応したイメージのタグは、各環境向けのイメージを指す一覧（manifest listまたはOCI image index）を持ちます。Dockerは取得するときに、要求されたOS・CPUアーキテクチャに合う項目を選びます。[Dockerのマルチプラットフォームの説明](https://docs.docker.com/build/building/multi-platform/)によると、ARM環境とx86-64環境では同じタグから異なる版が選ばれます。

```text
no matching manifest for linux/amd64 in the manifest list entries
no match for platform in manifest sha256:<digest>: not found
```

上は表示されることのある文言の例です。`linux/amd64`の部分やダイジェストは環境によって変わります。後者は[containerdの実装](https://github.com/containerd/containerd/blob/main/core/images/image.go)にもある文言です。両者とも、対象のタグを参照したうえで、要求するプラットフォームに適合する版を選べなかった場合に調べるエラーです。Dockerやビルドの経路によって表示全体は異なり、二つの文言が連結される場合もあります。

たとえば[公式Goイメージの報告](https://github.com/docker-library/golang/issues/502)では、`golang:1.21.5`を`linux/arm/v6`向けにビルドしようとして`no match for platform in manifest: not found`が出ています。タグがあることと、必要な環境向けの版があることは別です。この報告だけで、現在の同じタグの対応状況までは判断できません。

## タグの対応プラットフォームを確認する

失敗したコマンドのイメージ名とタグをそのまま使い、レジストリ上の一覧を調べます。`FROM`で止まった場合はDockerfileに書かれた基底イメージ、Composeの場合は該当サービスの`image`を確認します。

```bash
docker buildx imagetools inspect registry.example.com/myapp:1.2
```

複数の版を持つ場合、出力の`Manifests:`以下に`Platform: linux/amd64`や`Platform: linux/arm64`などが並びます。出力に要求した版があるかを見ます。タグによっては単一プラットフォームのmanifestを指すため、一覧ではなく単一のmanifestとして表示されます。`unknown/unknown`の項目は証明情報などの付随データの場合もあるので、それだけを見て実行環境の自動検出が失敗したと判断しないでください。[`imagetools inspect`の出力例](https://docs.docker.com/reference/cli/docker/buildx/imagetools/inspect/)で形式を確認できます。

別のタグを候補にするときも、置き換える前にそのタグを同じコマンドで調べます。`latest`という名前だけでは、必要なCPU向けの版が存在する保証にはなりません。

## 要求しているプラットフォームを確認する

エラーに`linux/amd64`などが表示されていれば、まずその値を確認します。ローカルのDockerデーモンが報告するOSとアーキテクチャは次のように調べられます。リモートのDocker contextを使っている場合、表示されるのは接続先のデーモンです。

```bash
docker info --format '{{.OSType}}/{{.Architecture}}'
```

デーモンの値とエラーの値が違うなら、明示的な指定を探します。`docker pull --platform ...`、`docker run --platform ...`、`docker buildx build --platform ...`、Dockerfileの`FROM --platform=...`、Composeの`platform:`などです。ビルドではターゲットの指定と`FROM`の指定の両方を確認してください。

CLIの`DOCKER_DEFAULT_PLATFORM`は、`--platform`を受け取るコマンドの既定値を変えます。シェルに合わせて値を確認します。

```bash
# bash / zsh
printf '%s\n' "$DOCKER_DEFAULT_PLATFORM"
```

```powershell
# PowerShell
$Env:DOCKER_DEFAULT_PLATFORM
```

たとえばARM64環境で`DOCKER_DEFAULT_PLATFORM=linux/amd64`を設定すると、明示的なフラグがないコマンドでもamd64を要求する場合があります。[Docker CLIの環境変数一覧](https://docs.docker.com/reference/cli/docker/)がこの変数の用途を説明しています。不要な固定なら、現在のシェルで`unset DOCKER_DEFAULT_PLATFORM`（bash / zsh）または`Remove-Item Env:DOCKER_DEFAULT_PLATFORM`（PowerShell）を実行し、もう一度試します。永続設定に書いた場合は設定元も直してください。

## タグと--platformを見直す

要求した版が一覧にない場合の対処は、**どの環境で実行する必要があるか**によって変わります。

| 確認結果 | 対処 |
|---|---|
| 必要な`linux/arm64`がタグにない | `linux/arm64`を含む別タグや別イメージを選ぶ |
| ARM64の端末で、タグには`linux/amd64`だけがある | amd64のエミュレーションを使える環境なら`--platform linux/amd64`を検討する |
| `linux/amd64`を強制したが、タグには`linux/arm64`だけがある | 強制した指定を外すか、amd64を含むタグを選ぶ |

ARM64環境でamd64版を利用する必要があり、一覧にamd64が**存在する**場合の例です。

```bash
docker pull --platform linux/amd64 <image>:<tag>
docker run --platform linux/amd64 <image>:<tag>
```

Docker Desktopは他のCPU向けのイメージをエミュレーションで実行・ビルドできますが、[公式資料](https://docs.docker.com/build/building/multi-platform/)はエミュレーションがネイティブ実行より遅くなりうると説明しています。Linux上ではエミュレーターの構成が必要な場合もあります。`--platform`は存在しない版を作る機能ではありません。

Composeで意図的に固定しているなら、該当サービスの`platform: linux/amd64`も同じ条件で見直します。Dockerfileの`FROM --platform=linux/amd64`を常に書く方法は、マルチプラットフォームビルドを妨げます。[Dockerのビルドチェック](https://docs.docker.com/reference/build-checks/from-platform-flag-const-disallowed/)は、固定値を省き、必要なターゲットをビルドコマンドの`--platform`で指定する方法を勧めています。

## 自分のイメージに必要な版を公開する

配布しているイメージの特定タグだけに版が足りない場合は、そのタグの公開手順を見直します。Dockerfileの基底イメージやビルドするバイナリも、両方のターゲットに対応する必要があります。

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t registry.example.com/myapp:1.2 \
  --push .
```

これはビルドした二つの版とその一覧をレジストリへ送る例です。[Docker公式のマルチプラットフォームビルド手順](https://docs.docker.com/build/building/multi-platform/)に沿っています。指定だけで各版のビルドが成功するわけではないため、ビルダーの対応状況、基底イメージ、アプリケーションのアーキテクチャ依存を確認してください。公開後は`docker buildx imagetools inspect registry.example.com/myapp:1.2`で、必要な両方の`Platform:`が表示されるか検証します。

## 似たエラーとの違い

| 文言 | どこを調べるか |
|---|---|
| `no matching manifest for ...` / `no match for platform in manifest` | 指定タグに要求したOS・CPU向けの版があるか。取得またはビルドのイメージ解決時に止まる |
| `manifest unknown` | 名前とタグがレジストリにあるか。要求した参照そのものが見つからない場合がある |
| `exec format error` | イメージ取得後、コンテナ内で起動する実行ファイルの形式と実行環境が合うか |

`exec format error`はイメージの取得に成功していても起こります。たとえばコンテナ内の実行ファイルだけが異なるCPU向けに作られている場合です。`no matching manifest for`を直した後に別のエラーが出たら、表示された段階に合わせて調べ直してください。

## 解決手順のまとめ

エラーに表示された`linux/amd64`などの要求値を控え、失敗した**同じイメージ名・タグ**を`docker buildx imagetools inspect`で調べます。対応する版がなければタグを変更するか、その版を公開します。

一覧に別の版がある場合は、`--platform`、Composeの`platform:`、Dockerfileの`FROM --platform`、`DOCKER_DEFAULT_PLATFORM`を確認します。実行環境が対応するなら、その既存の版を指定できます。指定を変えても一覧にない版を取得することはできません。

免責事項：本記事の内容は一般的なDocker環境を前提としています。実際に選ばれる版はイメージのタグ、Dockerの接続先、ビルド設定によって変わります。本番環境のタグやCPUアーキテクチャを変更する前に、実行結果と性能を検証してください。
