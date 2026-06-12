---
title: "Docker Hardened Imagesへの移行ガイド：HTTPエラーを回避し、コンテナセキュリティを強化する"
date: 2026-06-11
lastmod: 2026-06-11
draft: false
description: "Docker Hardened Images (DHI) への移行は、コンテナセキュリティを劇的に向上させますが、従来のDockerfileの前提を覆すため、HTTPエラーや予期せぬ挙動を引き起こす可能性があります。本記事では、DHI移行時に遭遇しやすい問題と、それらを解決するための実践的な手順を解説します。"
tags: ["Dev.to - Docker"]
trend_incident: true
---

## エラーの概要

Docker Hardened Images (DHI) は、最小限のパッケージ構成と非rootユーザーをデフォルトとする、セキュリティ強化されたベースイメージです。従来の汎用ベースイメージ（例: `ubuntu:22.04`）とは異なり、シェルやパッケージマネージャーが含まれていないため、既存のDockerfileやアプリケーションがこれらの前提に依存している場合、ビルド時や実行時にHTTPエラーを含む様々なエラーが発生します。具体的には、`docker exec -it app sh` のようなシェルコマンドが失敗したり、`RUN apt-get install curl` のようなパッケージインストールがビルドエラーになったりします。

## 実際のエラーメッセージ例

DHIへの移行時に遭遇する可能性のある典型的なエラーメッセージは以下の通りです。

**シェルが見つからない場合:**

```
OCI runtime exec failed: exec failed: container_linux.go:380: starting container process caused: exec: "sh": executable file not found in $PATH: unknown
```

**パッケージマネージャーが見つからない場合:**

```
#0 0.320 /bin/sh: 1: apt-get: not found
```

**非rootユーザーによる権限エラー:**

```
Error: listen EACCES: permission denied 0.0.0.0:80
```

## よくある原因と解決手順

### 原因1：シェルやパッケージマネージャーの不在

DHIは、攻撃対象領域を最小化するために、シェル（`sh`, `bash`など）やパッケージマネージャー（`apt-get`, `yum`など）を意図的に含んでいません。これにより、`docker exec` でコンテナ内部に入ってデバッグしたり、`RUN apt-get install` でビルド時に追加パッケージをインストールしたりする従来のDockerfileパターンが機能しなくなります。

**Before（エラーが起きるコード）：**

```dockerfile
# シェルに依存するヘルスチェック
HEALTHCHECK CMD curl -f localhost:8080/health || exit 1

# ビルド時にパッケージをインストール
RUN apt-get update && apt-get install -y curl
```

**After（修正後）：**

```dockerfile
# ヘルスチェックをexec形式に変更し、必要なバイナリをコンテナに含めるか、オーケストレーターのプローブを利用
# 例: アプリケーションが提供するヘルスチェックエンドポイントを直接叩くバイナリをビルドステージで作成し、ランタイムステージにコピー
# または、Kubernetesのliveness/readiness probeを利用し、コンテナ外部からヘルスチェックを行う

# パッケージインストールはマルチステージビルドのdev-variantで行う
FROM <registry>/dhi/python:3.12-dev AS build
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates
# ... 必要なビルドステップ ...

FROM <registry>/dhi/python:3.12
COPY --from=build /usr/bin/curl /usr/bin/curl
COPY --from=build /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
HEALTHCHECK CMD ["curl", "-f", "localhost:8080/health"]
```

### 原因2：非rootユーザーのデフォルト化

DHIはセキュリティ強化のため、デフォルトで非rootユーザー（`nonroot`など）で実行されます。これにより、ポート80へのバインドや、`/` ディレクトリへの書き込みなど、root権限を前提とした操作が権限エラー（`EACCES: permission denied`）を引き起こします。

**Before（エラーが起きるコード）：**

```dockerfile
# rootユーザーで実行されることを前提としたポートバインド
EXPOSE 80
CMD ["node", "server.js"] # server.jsがポート80にバインドしようとする

# rootユーザーでファイルを作成
RUN touch /app/data.txt
```

**After（修正後）：**

```dockerfile
# 非rootユーザーがアクセス可能なポート（例: 8080）を使用
EXPOSE 8080
USER nonroot # DHIでは通常デフォルトだが明示的に指定
CMD ["node", "server.js"] # server.jsはポート8080にバインドするよう修正

# 非rootユーザーが書き込み可能なディレクトリにファイルを配置
RUN mkdir -p /app/data && chown nonroot:nonroot /app/data
USER nonroot
CMD ["sh", "-c", "touch /app/data/data.txt && node server.js"]
```

### 原因3：ENTRYPOINTスクリプトの依存性

従来のDockerfileでは、起動ロジックをシェルスクリプト（例: `entrypoint.sh`）に記述し、`ENTRYPOINT ["/entrypoint.sh"]` のように指定することが一般的でした。しかし、DHIにはシェルが含まれないため、これらのスクリプトは実行できず、エラーとなります。

**Before（エラーが起きるコード）：**

```dockerfile
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
```

**After（修正後）：**

```dockerfile
# 起動ロジックをアプリケーション自体に組み込むか、exec形式で直接実行可能なコマンドを指定
# 例1: アプリケーションが直接起動ロジックを持つ場合
ENTRYPOINT ["python", "/app/src/main.py"]

# 例2: 起動前に環境設定などが必要な場合、マルチステージビルドで静的バイナリをビルドし、ランタイムステージにコピー
# または、一時的な回避策としてbusyboxのような最小限のシェルをコピーする（推奨されないが移行期には有効）
FROM <registry>/dhi/python:3.12-dev AS build
# ... 起動ロジックをGoなどで記述し、静的バイナリとしてビルド ...
COPY --from=build /path/to/my-startup-binary /usr/local/bin/my-startup-binary

FROM <registry>/dhi/python:3.12
COPY --chown=nonroot:nonroot src/ /app/src
COPY --from=build /usr/local/bin/my-startup-binary /usr/local/bin/my-startup-binary
USER nonroot
ENTRYPOINT ["/usr/local/bin/my-startup-binary"]
```

## ツール固有の注意点

Docker Hardened Imagesは、従来のDockerイメージとは異なる設計思想に基づいています。特に以下の点に注意が必要です。

*   **マルチステージビルドの必須化:** DHIはランタイムイメージが極めて軽量であるため、ビルドに必要なコンパイラやパッケージマネージャーは `-dev` バリアントのイメージを使用し、マルチステージビルドで最終的なランタイムイメージにコピーする必要があります。これは最適化ではなく、DHIを利用するための基本的なパターンです。
*   **デバッグ手法の変更:** `docker exec -it <container> sh` は機能しません。デバッグが必要な場合は、`docker debug` コマンド（Docker Desktopなど）やKubernetesのEphemeral Debug Containers（`kubectl debug`）を利用し、外部からデバッグツールをアタッチする方式に切り替える必要があります。これにより、本番イメージにデバッグツールを含めることなく、安全にデバッグが可能です。
*   **タイムゾーンとCA証明書:** 最小限のイメージであるため、`tzdata` や一般的なCA証明書バンドルが含まれていない場合があります。TLS通信やタイムスタンプ処理を行うアプリケーションでは、これらの不足が原因でエラーが発生することがあります。必要に応じて、ビルドステージでこれらのファイルをコピーする必要があります。

## それでも解決しない場合

上記の手順を試しても問題が解決しない場合は、以下の点を確認してください。

*   **詳細なログの確認:**
    *   Dockerデーモンのログ (`journalctl -u docker` または `/var/log/docker.log`)
    *   コンテナの標準出力/標準エラー出力 (`docker logs <container_id>`)
    *   Kubernetes環境であれば、Podのイベント (`kubectl describe pod <pod_name>`) やコンテナログ (`kubectl logs <pod_name> -c <container_name>`)
*   **デバッグコマンドの活用:**
    *   `docker debug <container_name>`: Docker Desktopなどの環境で、実行中のコンテナにデバッグコンテナをアタッチし、シェルやツールを利用できます。
    *   `kubectl debug -it <pod_name> --image=busybox:1.36 --target=<app_container_name>`: Kubernetes 1.25以降で利用可能なEphemeral Debug Containersを使用し、本番コンテナのネームスペースを共有する一時的なデバッグコンテナを起動できます。
*   **公式ドキュメントの参照:**
    *   Docker Hardened Imagesの公式ドキュメント: 最新の仕様や推奨されるプラクティスを確認してください。
    *   使用しているベースイメージ（例: `dhi/python`）の具体的なドキュメント: 各言語やフレームワークに特化したDHIの利用方法が記載されている場合があります。
*   **アプリケーションのコードレビュー:** アプリケーション自体が、ファイルシステムへの書き込みパス、ポートバインド、外部コマンドの実行などにroot権限や特定の環境を前提としていないか、再度確認してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*