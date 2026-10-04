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

この場合、まず**要求しているプラットフォーム**と、**その[イメージ](/glossary/イメージ/)の[タグ](/glossary/タグ/)に用意されているプラットフォーム**を比べます。例の`linux/amd64`は「[Linux](/glossary/linux/)用、x86-64 [CPU](/glossary/cpu/)向け」という要求です。[イメージ](/glossary/イメージ/)の名前だけでなく、[タグ](/glossary/タグ/)も含めて確認してください。

```bash
docker buildx imagetools inspect <image>:<tag>
```

表示された`Platform:`の一覧に要求したものがなければ、その[タグ](/glossary/タグ/)のまま同じプラットフォームを指定し直しても解決しません。[対応](/glossary/対応/)する[タグ](/glossary/タグ/)を選ぶか、利用可能な別のプラットフォームを指定します。自分で配布する[イメージ](/glossary/イメージ/)なら、そのプラットフォーム向けの版をビルドして公開します。[Docker公式の確認コマンド](https://docs.docker.com/reference/cli/docker/buildx/imagetools/inspect/)に一覧の表示例があります。

## no matching manifest forとは

複数の[環境](/glossary/環境/)に[対応](/glossary/対応/)した[イメージ](/glossary/イメージ/)の[タグ](/glossary/タグ/)は、各環境向けの[イメージ](/glossary/イメージ/)を指す一覧（manifest listまたはOCI image index）を持ちます。[Docker](/glossary/docker/)は取得するときに、要求された[OS](/glossary/os/)・[CPU](/glossary/cpu/)アーキテクチャに合う項目を選びます。[Dockerのマルチプラットフォームの説明](https://docs.docker.com/build/building/multi-platform/)によると、ARM[環境](/glossary/環境/)とx86-64[環境](/glossary/環境/)では同じ[タグ](/glossary/タグ/)から異なる版が選ばれます。

```text
no matching manifest for linux/amd64 in the manifest list entries
no match for platform in manifest sha256:<digest>: not found
```

上は表示されることのある文言の例です。`linux/amd64`の部分やダイジェストは[環境](/glossary/環境/)によって変わります。後者は[containerdの実装](https://github.com/containerd/containerd/blob/main/core/images/image.go)にもある文言です。両者とも、対象の[タグ](/glossary/タグ/)を参照したうえで、要求するプラットフォームに適合する版を選べなかった場合に調べる[エラー](/glossary/エラー/)です。[Docker](/glossary/docker/)やビルドの経路によって表示全体は異なり、二つの文言が連結される場合もあります。

たとえば[公式Goイメージの報告](https://github.com/docker-library/golang/issues/502)では、`golang:1.21.5`を`linux/arm/v6`向けにビルドしようとして`no match for platform in manifest: not found`が出ています。[タグ](/glossary/タグ/)があることと、必要な環境向けの版があることは別です。この報告だけで、現在の同じ[タグ](/glossary/タグ/)の対応状況までは判断できません。

## タグの対応プラットフォームを確認する

失敗した[コマンド](/glossary/コマンド/)の[イメージ](/glossary/イメージ/)名と[タグ](/glossary/タグ/)をそのまま使い、[レジストリ](/glossary/レジストリ/)上の一覧を調べます。`FROM`で止まった場合はDockerfileに書かれた基底[イメージ](/glossary/イメージ/)、Composeの場合は該当サービスの`image`を確認します。

```bash
docker buildx imagetools inspect registry.example.com/myapp:1.2
```

複数の版を持つ場合、出力の`Manifests:`以下に`Platform: linux/amd64`や`Platform: linux/arm64`などが並びます。出力に要求した版があるかを見ます。[タグ](/glossary/タグ/)によっては単一プラットフォームのmanifestを指すため、一覧ではなく単一のmanifestとして表示されます。`unknown/unknown`の項目は証明情報などの付随データの場合もあるので、それだけを見て実行環境の自動検出が失敗したと判断しないでください。[`imagetools inspect`の出力例](https://docs.docker.com/reference/cli/docker/buildx/imagetools/inspect/)で形式を確認できます。

別の[タグ](/glossary/タグ/)を候補にするときも、置き換える前にその[タグ](/glossary/タグ/)を同じ[コマンド](/glossary/コマンド/)で調べます。`latest`という名前だけでは、必要な[CPU](/glossary/cpu/)向けの版が存在する保証にはなりません。

## 要求しているプラットフォームを確認する

[エラー](/glossary/エラー/)に`linux/amd64`などが表示されていれば、まずその値を確認します。ローカルの[Docker](/glossary/docker/)[デーモン](/glossary/デーモン/)が報告する[OS](/glossary/os/)とアーキテクチャは次のように調べられます。リモートの[Docker](/glossary/docker/) contextを使っている場合、表示されるのは接続先の[デーモン](/glossary/デーモン/)です。

```bash
docker info --format '{{.OSType}}/{{.Architecture}}'
```

[デーモン](/glossary/デーモン/)の値と[エラー](/glossary/エラー/)の値が違うなら、明示的な指定を探します。`docker pull --platform ...`、`docker run --platform ...`、`docker buildx build --platform ...`、Dockerfileの`FROM --platform=...`、Composeの`platform:`などです。ビルドではターゲットの指定と`FROM`の指定の両方を確認してください。

[CLI](/glossary/cli/)の`DOCKER_DEFAULT_PLATFORM`は、`--platform`を受け取る[コマンド](/glossary/コマンド/)の既定値を変えます。[シェル](/glossary/シェル/)に合わせて値を確認します。

```bash
# bash / zsh
printf '%s\n' "$DOCKER_DEFAULT_PLATFORM"
```

```powershell
# PowerShell
$Env:DOCKER_DEFAULT_PLATFORM
```

たとえばARM64[環境](/glossary/環境/)で`DOCKER_DEFAULT_PLATFORM=linux/amd64`を[設定](/glossary/設定/)すると、明示的なフラグがない[コマンド](/glossary/コマンド/)でもamd64を要求する場合があります。[Docker CLIの環境変数一覧](https://docs.docker.com/reference/cli/docker/)がこの[変数](/glossary/変数/)の用途を説明しています。不要な固定なら、現在の[シェル](/glossary/シェル/)で`unset DOCKER_DEFAULT_PLATFORM`（[bash](/glossary/bash/) / zsh）または`Remove-Item Env:DOCKER_DEFAULT_PLATFORM`（PowerShell）を実行し、もう一度試します。永続設定に書いた場合は設定元も直してください。

## タグと--platformを見直す

要求した版が一覧にない場合の対処は、**どの[環境](/glossary/環境/)で実行する必要があるか**によって変わります。

| 確認結果 | 対処 |
|---|---|
| 必要な`linux/arm64`が[タグ](/glossary/タグ/)にない | `linux/arm64`を含む別[タグ](/glossary/タグ/)や別[イメージ](/glossary/イメージ/)を選ぶ |
| ARM64の端末で、[タグ](/glossary/タグ/)には`linux/amd64`だけがある | amd64のエミュレーションを使える[環境](/glossary/環境/)なら`--platform linux/amd64`を検討する |
| `linux/amd64`を強制したが、[タグ](/glossary/タグ/)には`linux/arm64`だけがある | 強制した指定を外すか、amd64を含む[タグ](/glossary/タグ/)を選ぶ |

ARM64[環境](/glossary/環境/)でamd64版を利用する必要があり、一覧にamd64が**存在する**場合の例です。

```bash
docker pull --platform linux/amd64 <image>:<tag>
docker run --platform linux/amd64 <image>:<tag>
```

[Docker](/glossary/docker/) Desktopは他の[CPU](/glossary/cpu/)向けの[イメージ](/glossary/イメージ/)をエミュレーションで実行・ビルドできますが、[公式資料](https://docs.docker.com/build/building/multi-platform/)はエミュレーションがネイティブ実行より遅くなりうると説明しています。[Linux](/glossary/linux/)上ではエミュレーターの構成が必要な場合もあります。`--platform`は存在しない版を作る機能ではありません。

Composeで意図的に固定しているなら、該当サービスの`platform: linux/amd64`も同じ条件で見直します。Dockerfileの`FROM --platform=linux/amd64`を常に書く方法は、マルチプラットフォームビルドを妨げます。[Dockerのビルドチェック](https://docs.docker.com/reference/build-checks/from-platform-flag-const-disallowed/)は、固定値を省き、必要なターゲットをビルドコマンドの`--platform`で指定する方法を勧めています。

## 自分のイメージに必要な版を公開する

配布している[イメージ](/glossary/イメージ/)の特定[タグ](/glossary/タグ/)だけに版が足りない場合は、その[タグ](/glossary/タグ/)の公開手順を見直します。Dockerfileの基底[イメージ](/glossary/イメージ/)やビルドするバイナリも、両方のターゲットに[対応](/glossary/対応/)する必要があります。

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t registry.example.com/myapp:1.2 \
  --push .
```

これはビルドした二つの版とその一覧を[レジストリ](/glossary/レジストリ/)へ送る例です。[Docker公式のマルチプラットフォームビルド手順](https://docs.docker.com/build/building/multi-platform/)に沿っています。指定だけで各版のビルドが成功するわけではないため、ビルダーの対応状況、基底[イメージ](/glossary/イメージ/)、[アプリケーション](/glossary/アプリケーション/)のアーキテクチャ依存を確認してください。公開後は`docker buildx imagetools inspect registry.example.com/myapp:1.2`で、必要な両方の`Platform:`が表示されるか検証します。

## 似たエラーとの違い

| 文言 | どこを調べるか |
|---|---|
| `no matching manifest for ...` / `no match for platform in manifest` | 指定[タグ](/glossary/タグ/)に要求した[OS](/glossary/os/)・[CPU](/glossary/cpu/)向けの版があるか。取得またはビルドの[イメージ](/glossary/イメージ/)解決時に止まる |
| `manifest unknown` | 名前と[タグ](/glossary/タグ/)が[レジストリ](/glossary/レジストリ/)にあるか。要求した参照そのものが見つからない場合がある |
| `exec format error` | [イメージ](/glossary/イメージ/)取得後、[コンテナ](/glossary/コンテナ/)内で起動する実行[ファイル](/glossary/ファイル/)の形式と実行環境が合うか |

`exec format error`は[イメージ](/glossary/イメージ/)の取得に成功していても起こります。たとえば[コンテナ](/glossary/コンテナ/)内の実行[ファイル](/glossary/ファイル/)だけが異なる[CPU](/glossary/cpu/)向けに作られている場合です。`no matching manifest for`を直した後に別の[エラー](/glossary/エラー/)が出たら、表示された段階に合わせて調べ直してください。

## 解決手順のまとめ

[エラー](/glossary/エラー/)に表示された`linux/amd64`などの要求値を控え、失敗した**同じ[イメージ](/glossary/イメージ/)名・[タグ](/glossary/タグ/)**を`docker buildx imagetools inspect`で調べます。[対応](/glossary/対応/)する版がなければ[タグ](/glossary/タグ/)を変更するか、その版を公開します。

一覧に別の版がある場合は、`--platform`、Composeの`platform:`、Dockerfileの`FROM --platform`、`DOCKER_DEFAULT_PLATFORM`を確認します。実行環境が[対応](/glossary/対応/)するなら、その既存の版を指定できます。指定を変えても一覧にない版を取得することはできません。

免責事項：本記事の内容は一般的な[Docker](/glossary/docker/)[環境](/glossary/環境/)を前提としています。実際に選ばれる版は[イメージ](/glossary/イメージ/)の[タグ](/glossary/タグ/)、[Docker](/glossary/docker/)の接続先、ビルド[設定](/glossary/設定/)によって変わります。[本番環境](/glossary/本番環境/)の[タグ](/glossary/タグ/)や[CPU](/glossary/cpu/)アーキテクチャを変更する前に、実行結果と性能を検証してください。
