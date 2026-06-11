---
title: "CaddyとDockerで502 Bad Gatewayエラーが発生する原因と解決策"
date: 2026-06-11
lastmod: 2026-06-11
draft: false
description: "CaddyとDockerを組み合わせた環境で発生する502 Bad Gatewayエラーについて、その原因と具体的な解決策を解説します。バックエンドサービスの起動遅延、Caddyfileの設定ミス、Dockerネットワークの問題など、実用的なデバッグ方法と修正コードを提供します。"
tags: ["Dev.to - DevOps"]
---

## エラーの概要

HTTP 502 Bad Gatewayエラーは、Caddyがリクエストをプロキシしようとしたバックエンドサーバーから無効なレスポンスを受け取った場合に発生します。CaddyとDockerを組み合わせた環境では、バックエンドサービスがまだ起動していない、Caddyfileの設定が間違っている、またはDockerネットワーク内でサービスが到達不能であるといった状況で頻繁に発生します。

## 実際のエラーメッセージ例

Caddyのログやブラウザのコンソールには、以下のようなエラーが出力されることがあります。

**Caddyログの例:**

```
{"level":"error","ts":1678886400.000000,"logger":"http.log.error","msg":"x509: certificate signed by unknown authority","request":{"remote_ip":"172.18.0.1","remote_port":"54321","proto":"HTTP/2.0","method":"GET","host":"api.example.com","uri":"/health","headers":{"User-Agent":["curl/7.81.0"],"Accept":["*/*"]}},"duration":0.000000,"status":502,"err_id":"<your-error-id>","err_trace":"reverseproxy.statusError (502 from upstream)"}
```

**ブラウザのコンソール出力例:**

```
Failed to load resource: the server responded with a status of 502 (Bad Gateway)
```

## よくある原因と解決手順

### 原因1：バックエンドサービスがまだ起動していない

Caddyがリクエストをプロキシしようとした時点で、対象のバックエンドサービス（APIサーバーなど）がまだ完全に起動していない、または準備ができていない場合に発生します。特にDocker Composeで複数のサービスを起動する際に、Caddyがバックエンドよりも早く起動してしまうとこの問題が起こりやすいです。

**Before（エラーが起きるコード）：**

```yaml
# docker-compose.yml (Caddyがバックエンドの起動を待たない設定)
services:
  caddy:
    image: caddy:latest
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
  api:
    image: my-backend-image
    expose:
      - "3000"
    # healthcheckが設定されていない、またはdepends_onが不十分
```

**After（修正後）：**

```yaml
# docker-compose.yml (Caddyがバックエンドのヘルスチェックを待つ設定)
services:
  caddy:
    image: caddy:latest
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      api:
        condition: service_healthy # APIサービスがhealthyになるまでCaddyの起動を待つ
  api:
    image: my-backend-image
    expose:
      - "3000"
    healthcheck: # APIサービスのヘルスチェックを定義
      test: ["CMD", "curl", "-f", "http://localhost:3000/health"] # 例: /healthエンドポイントをチェック
      interval: 30s
      timeout: 10s
      retries: 5
```

### 原因2：Caddyfileの`reverse_proxy`設定が間違っている

`reverse_proxy`ディレクティブで指定されたバックエンドのアドレスやポートが間違っている場合に発生します。Docker環境では、サービス名がホスト名として機能するため、IPアドレスではなくサービス名を指定するのが一般的です。

**Before（エラーが起きるコード）：**

```caddyfile
# Caddyfile (存在しないホスト名や間違ったポートを指定)
api.example.com {
    reverse_proxy localhost:3000 # Caddyコンテナ内からlocalhost:3000にアクセスしようとしている
}
```

**After（修正後）：**

```caddyfile
# Caddyfile (Dockerサービス名を指定)
api.example.com {
    reverse_proxy api:3000 # Docker Composeのサービス名 'api' とポート '3000' を指定
}
```

### 原因3：Dockerネットワーク内でサービスが到達不能

Caddyコンテナとバックエンドサービスコンテナが異なるDockerネットワークに属している、またはネットワーク設定が不適切で、Caddyがバックエンドサービスの名前解決や接続ができない場合に発生します。

**Before（エラーが起きるコード）：**

```yaml
# docker-compose.yml (異なるネットワークにサービスが分かれている、またはネットワークが未定義)
services:
  caddy:
    image: caddy:latest
    networks:
      - public_network
  api:
    image: my-backend-image
    expose:
      - "3000"
    networks:
      - private_network # Caddyとは異なるネットワーク
networks:
  public_network:
  private_network:
```

**After（修正後）：**

```yaml
# docker-compose.yml (CaddyとAPIサービスが同じネットワークに属する)
services:
  caddy:
    image: caddy:latest
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
    networks:
      - my_app_network # 同じネットワークを指定
  api:
    image: my-backend-image
    expose:
      - "3000"
    networks:
      - my_app_network # 同じネットワークを指定
networks:
  my_app_network: # 共通のネットワークを定義
```

## ツール固有の注意点

Caddyは自動HTTPS機能を備えていますが、これが502エラーに間接的に影響することもあります。例えば、Caddyが証明書を取得しようとしている最中にリクエストが来ると、一時的にプロキシが不安定になる可能性もゼロではありません。しかし、ほとんどの場合、502エラーはバックエンドの到達性や応答の問題に起因します。

Docker環境では、`depends_on`と`healthcheck`の組み合わせが非常に重要です。`depends_on`だけでは、依存するコンテナが起動したことしか保証せず、サービスがリクエストを受け付けられる状態になったことは保証しません。`healthcheck`を適切に設定し、`condition: service_healthy`を使用することで、より堅牢な起動シーケンスを構築できます。

また、Caddyの`reverse_proxy`ディレクティブは、デフォルトでWebSocketのアップグレードをサポートしています。もしWebSocket関連で502エラーが発生する場合は、Caddyfileの設定ではなく、バックエンドのWebSocketサーバーの実装を確認する必要があります。

## それでも解決しない場合

1.  **Caddyのログを詳細に確認する:**
    `docker logs <caddy-container-name>` コマンドでCaddyコンテナのログを確認します。`{"level":"error"}` の行に注目し、`err_trace` や `msg` フィールドから具体的なエラー原因の手がかりを探します。Caddyのログレベルを上げることで、より詳細な情報を得ることも可能です。

2.  **バックエンドサービスのログを確認する:**
    `docker logs <backend-container-name>` でバックエンドサービスのログを確認し、サービス自体が正常に起動しているか、エラーを吐いていないかを確認します。

3.  **Caddyコンテナ内からバックエンドへの接続をテストする:**
    `docker exec -it <caddy-container-name> sh` でCaddyコンテナに入り、`curl` コマンドなどを使ってバックエンドサービスに直接アクセスを試みます。
    例: `curl http://api:3000/health`
    これにより、Caddyからバックエンドへの名前解決やネットワーク接続に問題がないかを確認できます。

4.  **公式ドキュメントを参照する:**
    *   Caddy公式ドキュメント: [https://caddyserver.com/docs/](https://caddyserver.com/docs/)
    *   Docker Compose公式ドキュメント: [https://docs.docker.com/compose/](https://docs.docker.com/compose/)
    特に`reverse_proxy`ディレクティブやDocker Composeの`depends_on`、`healthcheck`に関するセクションを再確認してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*