---
title: "DockerコンテナがExited (1)で終了する原因と解決策（特にRaspberry Piで）"
date: 2026-06-12
lastmod: 2026-06-12
draft: false
description: "DockerコンテナがExited (1)で終了する一般的な原因と、特にRaspberry Pi環境での解決策を詳しく解説します。互換性のないアーキテクチャ、コマンドの構文エラー、依存関係の不足など、具体的なコード例を交えて説明します。"
tags: ["Dev.to - Docker"]
trend_incident: true
---

## エラーの概要

`docker run` コマンド実行後にコンテナが `Exited (1)` で終了する場合、これはコンテナ内のメインプロセスが一般的なエラーで終了したことを示します。特にRaspberry PiのようなARMベースのデバイスでは、互換性のないアーキテクチャのイメージを使用していることが主な原因として挙げられます。

## 実際のエラーメッセージ例

`docker ps -a` コマンドで確認できるステータスは以下のようになります。

```
CONTAINER ID   IMAGE     COMMAND                  CREATED          STATUS                      PORTS     NAMES
<container-id> myimage   "python app.py"          5 minutes ago    Exited (1) 4 minutes ago              <container-name>
```

また、`docker logs <container-id>` で詳細を確認すると、以下のようなメッセージが出力されることがあります。

```
standard_init_linux.go:211: exec user process caused: no such file or directory
```

## よくある原因と解決手順

### 原因1：イメージのアーキテクチャがRaspberry Piと互換性がない

Raspberry PiはARMアーキテクチャ（arm32v7またはarm64v8）を使用しますが、多くのDockerイメージはx86_64（amd64）アーキテクチャ向けにビルドされています。互換性のないイメージを実行しようとすると、`Exited (1)` エラーが発生します。

**Before（エラーが起きるコード）：**

```bash
# amd64向けにビルドされたイメージをRaspberry Piで実行しようとしている
docker run -d -t myimage:latest
```

**After（修正後）：**

```bash
# 1. イメージのアーキテクチャを確認する
docker inspect myimage:latest --format '{{.Architecture}}'

# 2. ARM互換のイメージを使用する（例: arm32v7/ubuntu）
# または、マルチアーキテクチャ対応のイメージでプラットフォームを指定する
docker run --platform linux/arm/v7 -d -t myimage:latest

# 3. 自分でRaspberry Pi上でイメージをビルドする
# Dockerfileがあるディレクトリで実行
# docker build -t myimage:latest .
```

### 原因2：`docker run` コマンドの構文エラー

特に `--net=host` のように、オプションと値の間にスペースが入ってしまうと、Dockerはそれを誤って解釈し、エラーとなることがあります。

**Before（エラーが起きるコード）：**

```bash
# --net と host の間にスペースが入っている
docker run --net = host -d -t myimage
```

**After（修正後）：**

```bash
# --net と host の間にスペースを入れない
docker run --net host -d -t myimage
```

### 原因3：コンテナ内のアプリケーションが依存関係や権限の問題で起動できない

コンテナ内のアプリケーションが、必要なライブラリやバイナリを見つけられない、または適切な権限がないために起動に失敗することがあります。特にRaspberry Pi OS Liteのような最小限のシステムでは、特定の依存関係が不足している場合があります。

**Before（エラーが起きるコード）：**

```bash
# 依存関係が不足している、または特定のデバイスへのアクセス権限がない状態で実行
docker run -it --rm myimage
```

**After（修正後）：**

```bash
# 1. まずはフォアグラウンドで実行し、エラーメッセージを確認する
docker run -it --rm myimage

# 2. 必要に応じて、特権モードで実行してみる（デバッグ目的）
# これにより、多くの権限問題が一時的に解消されるか確認できる
docker run --privileged -it --rm myimage

# 3. Dockerfileを修正し、必要な依存関係をインストールする
# 例: apt-get install -y libgl1
```

## ツール固有の注意点

Raspberry PiでDockerを使用する場合、特に以下の点に注意が必要です。

*   **QEMUによるエミュレーション**: ARMアーキテクチャ上でx86_64イメージを動かすことは、QEMUなどのエミュレーションツールを使えば可能ですが、パフォーマンスは大幅に低下します。開発やテスト目的以外では推奨されません。
    ```bash
    # QEMUをセットアップし、マルチアーキテクチャ対応を有効にする
    docker run --rm --privileged multiarch/qemu-user-static --reset -p yes
    # その後、--platformを指定してイメージを実行
    docker run --platform linux/arm/v7 -it --rm myimage
    ```
*   **`--net host` の挙動**: Raspberry Pi OS（または特権のないコンテナ）で `systemd-resolved` や `dnsmasq` が使用されている場合、`--net host` が正しく機能しないことがあります。この場合、`--net host` オプションを外して試すか、別のネットワークモードを検討してください。
*   **リソースの制約**: Raspberry PiはPCと比較してCPUやメモリのリソースが限られています。特にメモリを大量に消費するアプリケーションや、多くのコンテナを同時に実行する場合、パフォーマンスの問題やOOM (Out Of Memory) エラーが発生しやすくなります。

## それでも解決しない場合

*   **コンテナのログを確認する**: `docker logs <container-id>` コマンドで、コンテナが終了する直前のログを確認します。ここに具体的なエラーメッセージが出力されていることが多いです。
*   **フォアグラウンドで実行する**: `docker run -it --rm <image-name>` のように `-d` オプションを外し、インタラクティブモードで実行することで、コンテナが終了するまでの標準出力や標準エラー出力をリアルタイムで確認できます。
*   **`strace` を使用してデバッグする**: コンテナ内で `strace` を実行することで、プロセスがどのシステムコールで失敗しているかを詳細に追跡できます。
    ```dockerfile
    # Dockerfileでstraceをインストールする例
    FROM myimage
    RUN apt-get update && apt-get install -y strace
    ```
    ```bash
    # straceを使って実行する
    docker run -it --rm myimage-debug strace -f /bin/sh -c "exec -a 0 <your-command>"
    ```
*   **最小限のARMイメージでテストする**: `arm32v7/alpine:latest` のような最小限のARM互換イメージが正常に動作するかを確認します。これが動作すれば、問題はホスト環境ではなく、あなたの `myimage` にある可能性が高いです。
    ```bash
    docker run -it --rm arm32v7/alpine:latest echo "Hello from Alpine on ARM!"
    ```
*   **公式ドキュメントを参照する**: Dockerの公式ドキュメントや、使用しているベースイメージのドキュメントを確認し、既知の問題や推奨される設定がないか調べます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*