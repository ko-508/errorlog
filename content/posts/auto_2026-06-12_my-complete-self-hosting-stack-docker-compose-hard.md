---
title: "Docker Composeでセルフホスティング環境を構築する際の一般的なエラーと解決策"
date: 2026-06-12
lastmod: 2026-06-12
draft: false
description: "Docker Composeでセルフホスティング環境を構築する際に遭遇しやすいエラーの原因と解決策を、具体的なコード例を交えて解説します。Caddy、Uptime Kuma、Matomoなどのサービスを安全かつ効率的に運用するためのヒントを提供します。"
tags: ["Dev.to - Docker"]
trend_incident: true
---

## エラーの概要

Docker Composeで複数のサービスをセルフホスティングする際、設定ミスや環境の不整合により様々なエラーが発生します。特に、サービス間の依存関係、ポートの競合、ボリュームのマウント、環境変数の設定、そしてリバースプロキシの設定は、一般的なエラーの原因となります。これらのエラーは、コンテナが起動しない、サービスにアクセスできない、またはデータが永続化されないといった形で現れます。

## 実際のエラーメッセージ例

Docker Composeでサービスが起動しない場合、以下のようなエラーメッセージが出力されることがあります。

```
ERROR: for <service_name>  Cannot start service <service_name>: driver failed programming external connectivity: Error starting userland proxy: listen tcp 0.0.0.0:80: bind: address already in use
```

```json
{
  "level": "error",
  "ts": 1678886400.000000,
  "caller": "caddyfile/adapter.go:104",
  "msg": "adapting config using caddyfile: parsing caddyfile: Caddyfile:2: unrecognized global option: email",
  "error": "adapting config using caddyfile: parsing caddyfile: Caddyfile:2: unrecognized global option: email"
}
```

## よくある原因と解決手順

### 原因1：ポートの競合

Dockerコンテナがホストのポートを占有しようとした際に、そのポートがすでに別のプロセスによって使用されている場合に発生します。特に、Webサーバーでよく使われる80番や443番ポートは競合しやすいです。

**Before（エラーが起きるコード）：**

```yaml
# docker-compose.yml
version: "3.8"
services:
  caddy:
    image: caddy:2-alpine
    container_name: caddy
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    # ...
  another_web_app:
    image: some_web_app:latest
    container_name: another_web_app
    restart: unless-stopped
    ports:
      - "80:80" # Caddyとポートが競合
    # ...
```

**After（修正後）：**

```yaml
# docker-compose.yml
version: "3.8"
services:
  caddy:
    image: caddy:2-alpine
    container_name: caddy
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    # ...
  another_web_app:
    image: some_web_app:latest
    container_name: another_web_app
    restart: unless-stopped
    # Caddyがリバースプロキシとして機能するため、内部ポートのみ公開
    # 外部からはCaddy経由でアクセス
    # ports:
    #   - "80:80" # この行は削除またはコメントアウト
    # ...
```

**解決手順:**
1. `netstat -tulnp | grep :80` や `lsof -i :80` などのコマンドで、どのプロセスがポートを使用しているか確認します。
2. 競合しているプロセスを停止するか、Docker Composeファイル内でポートマッピングを変更して、別のホストポートを使用するようにします。
3. リバースプロキシ（Caddyなど）を使用している場合は、複数のWebサービスが直接ホストポートを公開するのではなく、リバースプロキシの内部ネットワーク経由で通信するように設定します。

### 原因2：ボリュームのマウント失敗または権限不足

コンテナがホストのディレクトリやDockerボリュームにアクセスできない場合に発生します。これは、パスの誤り、ボリュームの未作成、またはホスト側のディレクトリに対する権限不足が原因となることが多いです。

**Before（エラーが起きるコード）：**

```yaml
# docker-compose.yml
version: "3.8"
services:
  matomo:
    image: matomo:latest
    container_name: matomo
    restart: unless-stopped
    volumes:
      - ./matomo:/var/www/html # ホストの相対パスが間違っている、または権限がない
    # ...
volumes:
  matomo: # 名前付きボリュームが定義されているが、上記ではバインドマウントを使用している
```

**After（修正後）：**

```yaml
# docker-compose.yml
version: "3.8"
services:
  matomo:
    image: matomo:latest
    container_name: matomo
    restart: unless-stopped
    volumes:
      - matomo:/var/www/html # 名前付きボリュームを使用
    # ...
volumes:
  matomo: # 名前付きボリュームを正しく定義
```

**解決手順:**
1. **名前付きボリュームを使用する:** 永続化が必要なデータには、Dockerの名前付きボリュームを使用することを強く推奨します。これにより、ホストのファイルシステム構造に依存せず、権限の問題も軽減されます。
2. **バインドマウントの場合:** ホストのパスが正しいか確認し、Dockerコンテナがそのパスにアクセスするための適切な権限（読み書き）を持っているか確認します。必要に応じて `chmod` や `chown` コマンドで権限を調整します。
3. `docker volume ls` でボリュームが正しく作成されているか確認します。

### 原因3：Caddyfileの構文エラー

Caddyfileの記述ミスは、Caddyが起動しない、または期待通りにリバースプロキシとして機能しない原因となります。特に、グローバルオプションの配置や、ドメインとリバースプロキシ設定の対応関係に注意が必要です。

**Before（エラーが起きるコード）：**

```caddyfile
# Caddyfile
grafana.yourdomain.de {
  reverse_proxy grafana:3000
}
{
  email admin@yourdomain.de # グローバルオプションが誤った位置にある
}
uptime.yourdomain.de {
  reverse_proxy uptime-kuma:3001
}
```

**After（修正後）：**

```caddyfile
# Caddyfile
{
  email admin@yourdomain.de # グローバルオプションはファイルの先頭に記述する
}

grafana.yourdomain.de {
  reverse_proxy grafana:3000
}
uptime.yourdomain.de {
  reverse_proxy uptime-kuma:3001
}
```

**解決手順:**
1. Caddyfileの構文は厳密です。公式ドキュメントを参照し、特にグローバルオプションの配置、サイトブロックの開始と終了、ディレクティブの記述方法を確認します。
2. Caddyのログ (`docker logs caddy`) を確認し、具体的なエラーメッセージから問題箇所を特定します。
3. Caddyfileを修正したら、`docker compose restart caddy` または `docker compose up -d caddy` でCaddyコンテナを再起動し、設定を適用します。

## ツール固有の注意点

*   **Caddy:** Caddyは自動HTTPSを非常に簡単に設定できますが、`email`などのグローバルオプションはCaddyfileの先頭に `{ ... }` ブロックで記述する必要があります。また、`reverse_proxy`ディレクティブで指定するサービス名は、Docker Composeのサービス名と一致させる必要があります。
*   **Docker Compose Profiles:** `profiles`機能は、特定のサービス群のみを起動する際に非常に便利です。しかし、`docker compose --profile <profile_name> up -d` のように、起動したいプロファイルをすべて明示的に指定する必要があります。指定を忘れると、意図したサービスが起動しません。
*   **環境変数:** `vaultwarden`などのサービスでは、`ADMIN_TOKEN`や`SMTP_HOST`のような環境変数を`.env`ファイルやDocker Composeファイル内で設定する必要があります。これらの変数が正しく設定されていないと、サービスが正常に動作しない、またはセキュリティ上の問題が発生する可能性があります。

## それでも解決しない場合

1.  **Dockerコンテナのログを確認する:**
    `docker logs <container_name>` コマンドで、エラーが発生しているコンテナのログを詳細に確認します。起動時のエラーや内部的な問題が記録されていることが多いです。
2.  **Docker Composeの再構築:**
    `docker compose down --volumes` で関連するコンテナとボリュームを削除し、`docker compose up -d --build` でクリーンな状態から再構築を試みます。これにより、古いキャッシュや不整合な状態が解消されることがあります。
3.  **ホストのファイアウォール設定を確認する:**
    `ufw status` や `iptables -L` コマンドで、ホストのファイアウォールがDockerコンテナへのアクセスをブロックしていないか確認します。特に、Caddyが使用する80番、443番ポートは許可されている必要があります。
4.  **公式ドキュメントを参照する:**
    各サービスの公式ドキュメントやDockerの公式ドキュメントは、最新の情報や詳細なトラブルシューティングガイドを提供しています。特に、使用しているイメージのバージョンに合わせた設定を確認することが重要です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*