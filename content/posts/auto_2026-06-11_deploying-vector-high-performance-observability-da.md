---
title: "VectorのDocker Composeデプロイで発生するHTTPエラーのトラブルシューティング"
date: 2026-06-11
lastmod: 2026-06-11
draft: false
description: "VectorをDocker Composeでデプロイする際に遭遇しやすいHTTPエラーの原因と解決策を解説します。Traefikとの連携、設定ファイルの誤り、ネットワーク問題など、具体的なエラーメッセージと修正コード例を交えて詳しく説明します。"
tags: ["Dev.to - Docker"]
trend_incident: true
---

## エラーの概要

VectorをDocker Composeでデプロイし、Traefikをリバースプロキシとして利用する構成では、HTTPリクエストがVectorコンテナに到達しない、または不正なリクエストとして処理されることで様々なHTTPエラーが発生します。これらは主にTraefikの設定ミス、Vectorの設定ミス、またはネットワーク関連の問題に起因し、外部からのデータ取り込み（ingest）やAPIアクセスが機能しない状況を引き起こします。

## 実際のエラーメッセージ例

TraefikやVectorのログ、または`curl`コマンドの出力で以下のようなエラーメッセージを確認することがあります。

**Traefikログの例:**

```
traefik    | time="2024-01-01T12:34:56Z" level=error msg="Error while calling the ACME server for the challenge: tls: no certificates configured" providerName=letsencrypt rule="Host(`vector.example.com`)" routerName=vector-api
traefik    | time="2024-01-01T12:34:57Z" level=warning msg="No entrypoints defined for router vector-api, skipping" routerName=vector-api
```

**`curl`コマンドの出力例:**

```
curl: (7) Failed to connect to vector.example.com port 443 after 75 ms: Connection refused
```

```json
{
  "error": "404 page not found"
}
```

## よくある原因と解決手順

### 原因1：Traefikのルーティング設定ミス

TraefikがVectorコンテナへのトラフィックを正しくルーティングできていない場合、外部からのリクエストがVectorに到達せず、404 Not FoundやConnection Refusedなどのエラーが発生します。特に`Host`ルールや`PathPrefix`、`service`の指定が誤っているとこの問題が起こります。

**Before（エラーが起きるコード）：**

```yaml
# docker-compose.yamlの一部
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.vector-api.rule=Host(`${DOMAIN}`) && (PathPrefix(`/playground`) || PathPrefix(`/graphql`) || PathPrefix(`/health`))"
      - "traefik.http.routers.vector-api.entrypoints=websecure"
      - "traefik.http.routers.vector-api.tls.certresolver=letsencrypt"
      - "traefik.http.routers.vector-api.service=vector-api"
      - "traefik.http.services.vector-api.loadbalancer.server.port=8686"
      # ingestエンドポイントのPathPrefixが誤っている例
      - "traefik.http.routers.vector-ingest.rule=Host(`${DOMAIN}`) && PathPrefix(`/ingest/`)" # 末尾にスラッシュがある
      - "traefik.http.routers.vector-ingest.entrypoints=websecure"
      - "traefik.http.routers.vector-ingest.tls.certresolver=letsencrypt"
      - "traefik.http.routers.vector-ingest.service=vector-ingest"
      - "traefik.http.services.vector-ingest.loadbalancer.server.port=8080"
      - "traefik.http.middlewares.strip-ingest.stripprefix.prefixes=/ingest"
      - "traefik.http.routers.vector-ingest.middlewares=strip-ingest"
```

**After（修正後）：**

```yaml
# docker-compose.yamlの一部
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.vector-api.rule=Host(`${DOMAIN}`) && (PathPrefix(`/playground`) || PathPrefix(`/graphql`) || PathPrefix(`/health`))"
      - "traefik.http.routers.vector-api.entrypoints=websecure"
      - "traefik.http.routers.vector-api.tls.certresolver=letsencrypt"
      - "traefik.http.routers.vector-api.service=vector-api"
      - "traefik.http.services.vector-api.loadbalancer.server.port=8686"
      # PathPrefixから不要なスラッシュを削除
      - "traefik.http.routers.vector-ingest.rule=Host(`${DOMAIN}`) && PathPrefix(`/ingest`)"
      - "traefik.http.routers.vector-ingest.entrypoints=websecure"
      - "traefik.http.routers.vector-ingest.tls.certresolver=letsencrypt"
      - "traefik.http.routers.vector-ingest.service=vector-ingest"
      - "traefik.http.services.vector-ingest.loadbalancer.server.port=8080"
      - "traefik.http.middlewares.strip-ingest.stripprefix.prefixes=/ingest"
      - "traefik.http.routers.vector-ingest.middlewares=strip-ingest"
```
**説明:**
Traefikの`PathPrefix`ルールは厳密にパスをマッチさせます。`PathPrefix(`/ingest/`)`と指定した場合、`/ingest`というパスにはマッチしません。また、`stripprefix`ミドルウェアを使用している場合、TraefikがVectorに転送する前に`/ingest`を削除するため、Vectorの`http_server`ソースはルートパス（`/`）でリッスンしている必要があります。`PathPrefix`と`stripprefix`の組み合わせが正しく機能しているか確認してください。

### 原因2：VectorのHTTPソース設定ミス

Vectorの`http_server`ソースが正しく設定されていない場合、Traefikから転送されたリクエストをVectorが処理できません。特に`address`や`decoding.codec`が環境と一致しないとエラーになります。

**Before（エラーが起きるコード）：**

```yaml
# config/vector.yamlの一部
sources:
  http_input:
    type: "http_server"
    # 外部からアクセスできないアドレスを指定している例
    address: "127.0.0.1:8080"
    decoding:
      codec: "json"
```

**After（修正後）：**

```yaml
# config/vector.yamlの一部
sources:
  http_input:
    type: "http_server"
    # すべてのインターフェースでリッスンするよう修正
    address: "0.0.0.0:8080"
    decoding:
      codec: "json"
```
**説明:**
Dockerコンテナ内で動作するVectorが外部からのリクエストを受け付けるには、`address`を`0.0.0.0`に設定してすべてのネットワークインターフェースからの接続を許可する必要があります。`127.0.0.1`はコンテナ内部のループバックアドレスであり、Traefikコンテナからの接続は受け付けられません。

### 原因3：HTTPS証明書の問題

TraefikがLet's EncryptでHTTPS証明書を取得できない場合、`curl`コマンドで`Connection refused`や証明書エラーが発生します。これは`LETSENCRYPT_EMAIL`の誤り、DNS設定の誤り、またはファイアウォールによるポート80/443のブロックが原因で起こります。

**Before（エラーが起きるコード）：**

```ini
# .envファイル
DOMAIN=vector.example.com
LETSENCRYPT_EMAIL=invalid-email # 無効なメールアドレス
```

**After（修正後）：**

```ini
# .envファイル
DOMAIN=vector.example.com
LETSENCRYPT_EMAIL=admin@example.com # 有効なメールアドレス
```
**説明:**
Let's Encryptは証明書の発行プロセスで指定されたメールアドレスを使用します。無効なメールアドレスを指定すると、証明書の発行に失敗し、HTTPS接続が確立できません。また、`DOMAIN`に指定したドメインが、デプロイしているサーバーのIPアドレスを指すようにDNSレコード（Aレコード）が正しく設定されていることを確認してください。さらに、サーバーのファイアウォールでポート80（HTTPチャレンジ用）と443（HTTPS）が開放されている必要があります。

## ツール固有の注意点

*   **Traefikの動的設定:** TraefikはDockerラベルを使って動的にルーティング設定を読み込みます。`docker-compose.yaml`の`labels`セクションに誤りがあると、TraefikはVectorサービスを認識できません。`docker compose logs traefik`で起動時のログを確認し、エラーや警告がないかチェックしてください。
*   **Vectorのボリュームマウント:** Vectorの設定ファイル`vector.yaml`はコンテナ内の`/etc/vector/vector.yaml`にマウントされます。このパスが誤っていたり、ファイルが存在しなかったりすると、Vectorはデフォルト設定で起動するか、起動に失敗します。`./config/vector.yaml:/etc/vector/vector.yaml:ro`のように、読み取り専用（`:ro`）でマウントすることで、意図しない変更を防ぎます。
*   **ポートの公開とTraefikのサービスポート:** Vectorコンテナの`expose`セクションは、Dockerネットワーク内でポートを公開しますが、ホストのポートを公開する`ports`とは異なります。TraefikはDockerネットワーク内でVectorに接続するため、`expose`で十分です。Traefikの`loadbalancer.server.port`は、Vectorコンテナがリッスンしている内部ポート（例: 8080や8686）と一致させる必要があります。

## それでも解決しない場合

1.  **Traefikのログを確認する:**
    `docker compose logs traefik`を実行し、`level=error`や`level=warning`のメッセージがないか確認します。特にACME（Let's Encrypt）関連のエラーや、ルーターが認識されていない旨の警告は重要です。
2.  **Vectorのログを確認する:**
    `docker compose logs vector`を実行し、Vectorが正常に起動しているか、`http_server`ソースがエラーなく初期化されているかを確認します。
3.  **コンテナ内部から疎通確認を行う:**
    `docker exec -it <traefik-container-name> sh`でTraefikコンテナに入り、`curl http://vector:8080/`のようにVectorコンテナの内部IPアドレスとポートに対して直接リクエストを送信し、TraefikからVectorへの疎通を確認します。
4.  **公式ドキュメントを参照する:**
    *   Vector公式ドキュメント: [https://vector.dev/docs/](https://vector.dev/docs/)
    *   Traefik公式ドキュメント: [https://doc.traefik.io/traefik/](https://doc.traefik.io/traefik/)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*