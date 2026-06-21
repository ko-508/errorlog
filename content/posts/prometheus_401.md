---
title: "Prometheus の 401 エラー：原因と解決策"
date: 2026-06-21
description: "Prometheusへの認証に失敗した。Prometheus 401 エラーの原因と解決策を解説します。"
tags: ["Prometheus"]
errorCode: "401"
service: "Prometheus"
error_type: "401"
components: []
related_services: ["curl", "Python requests", "HTTPBasicAuth"]
---

## エラーの概要

Prometheus の 401 [エラー](/glossary/エラー/)は、[HTTP](/glossary/http/) [認証](/glossary/認証/)が失敗したことを示します。Prometheus [サーバー](/glossary/サーバー/)が[認証](/glossary/認証/)を要求しているにもかかわらず、クライアント（スクレイパー、エクスポーター、またはリモート [API](/glossary/api/) クライアント）が有効な認証情報を提供していない状態で発生します。この[エラー](/glossary/エラー/)は、ベーシック[認証](/glossary/認証/)、[TLS](/glossary/tls/) クライアント証明書認証、またはリバースプロキシ経由の[認証](/glossary/認証/)など、複数の[認証](/glossary/認証/)メカニズムで発生する可能性があります。

## 実際のエラーメッセージ例

**Prometheus のスクレイプログ：**

```
level=error ts=2024-01-15T10:30:45.123Z caller=scrape.go:1234 component=scraper msg="scrape failed" instance=http://localhost:9090/metrics err="server returned HTTP status 401 Unauthorized"
```

**curl での[レスポンス](/glossary/レスポンス/)：**

```
HTTP/1.1 401 Unauthorized
Content-Type: application/json
WWW-Authenticate: Basic realm="Prometheus"

{"status":"error","errorType":"unauthorized","error":"Unauthorized"}
```

## よくある原因と解決手順

### 原因1：Prometheus のベーシック認証が設定されているが認証情報を送っていない

Prometheus [サーバー](/glossary/サーバー/)が `--web.basic-auth.username` と `--web.basic-auth.password` フラグで起動されているか、リバースプロキシのベーシック認証設定が有効な場合、すべての[リクエスト](/glossary/リクエスト/)に `Authorization: Basic` [ヘッダー](/glossary/ヘッダー/)が必須となります。この[ヘッダー](/glossary/ヘッダー/)なしで[リクエスト](/glossary/リクエスト/)すると 401 [エラー](/glossary/エラー/)が返されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
# prometheus.yml - ベーシック認証が必要なPrometheusへのスクレイプ設定（認証情報なし）
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['http://prometheus-server:9090']
```

**After（修正後）：**

```yaml
# prometheus.yml - ベーシック認証情報を追加
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    basic_auth:
      username: '<your-username>'
      password: '<your-password>'
    static_configs:
      - targets: ['http://prometheus-server:9090']
```

または、Prometheus リモート書き込みクライアントの場合：

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```python
import requests

# ベーシック認証なしでリモート Prometheus にリクエスト
response = requests.post(
    'http://prometheus-server:9090/api/v1/write',
    json={"metric": "test", "value": 42}
)
print(response.status_code)  # 401 が返される
```

**After（修正後）：**

```python
import requests
from requests.auth import HTTPBasicAuth

# ベーシック認証を含める
response = requests.post(
    'http://prometheus-server:9090/api/v1/write',
    json={"metric": "test", "value": 42},
    auth=HTTPBasicAuth('<your-username>', '<your-password>')
)
print(response.status_code)  # 200 が返される
```

### 原因2：TLS クライアント証明書認証が必要なのに証明書を設定していない

Prometheus が相互 [TLS](/glossary/tls/)（mTLS）[認証](/glossary/認証/)で保護されている場合、クライアント側でクライアント証明書と秘密鍵を提示する必要があります。これらの設定がない場合、[TLS](/glossary/tls/) ハンドシェイクが失敗し、[認証](/glossary/認証/)[エラー](/glossary/エラー/)として 401 が返されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
# prometheus.yml - TLS設定なしでmTLS保護されたPrometheusにアクセス
scrape_configs:
  - job_name: 'remote-prometheus'
    scheme: https
    static_configs:
      - targets: ['prometheus-secure:9090']
```

**After（修正後）：**

```yaml
# prometheus.yml - TLSクライアント証明書とキーを設定
scrape_configs:
  - job_name: 'remote-prometheus'
    scheme: https
    tls_config:
      ca_file: /etc/prometheus/certs/ca.crt
      cert_file: /etc/prometheus/certs/client.crt
      key_file: /etc/prometheus/certs/client.key
      insecure_skip_verify: false
    static_configs:
      - targets: ['prometheus-secure:9090']
```

curl での[テスト](/glossary/テスト/)例：

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# TLS認証なしでアクセス
curl -k https://prometheus-secure:9090/api/v1/query
```

**After（修正後）：**

```bash
# クライアント証明書を指定してアクセス
curl --cert /etc/prometheus/certs/client.crt \
     --key /etc/prometheus/certs/client.key \
     --cacert /etc/prometheus/certs/ca.crt \
     https://prometheus-secure:9090/api/v1/query
```

### 原因3：リバースプロキシ（Nginx 等）の認証設定でブロックされている

Prometheus の前段に Nginx や Apache などのリバースプロキシが配置されている場合、[プロキシ](/glossary/プロキシ/)側で[認証](/glossary/認証/)が設定されていることがあります。この場合、[プロキシ](/glossary/プロキシ/)への認証情報が必要であり、同時に Prometheus 自体の認証設定とも整合させなければなりません。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```nginx
# Nginx の設定 - 認証を要求するが、Prometheusへの転送時に認証情報を削除
server {
    listen 80;
    server_name prometheus.example.com;

    location / {
        auth_basic "Prometheus";
        auth_basic_user_file /etc/nginx/.htpasswd;

        proxy_pass http://localhost:9090;
        # 認証情報がPrometheusに転送されない
    }
}
```

**After（修正後）：**

```nginx
# Nginx の設定 - 認証後にPrometheusへ正しく転送
server {
    listen 80;
    server_name prometheus.example.com;

    location / {
        auth_basic "Prometheus";
        auth_basic_user_file /etc/nginx/.htpasswd;

        proxy_pass http://localhost:9090;
        proxy_set_header Authorization $http_authorization;
        proxy_pass_header Authorization;
    }
}
```

または、Prometheus 側で直接ベーシック[認証](/glossary/認証/)を設定する場合：

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# Prometheusを起動（認証なし）
./prometheus --config.file=prometheus.yml
```

**After（修正後）：**

```bash
# Prometheusを起動（ベーシック認証有効）
./prometheus \
  --config.file=prometheus.yml \
  --web.basic-auth.username=<your-username> \
  --web.basic-auth.password=<your-password>
```

## ツール固有の注意点

**Prometheus スクレイパーの[認証](/glossary/認証/)：** `prometheus.yml` 内で定義されたスクレイプ対象も 401 を返す可能性があります。特にエクスポーター（Node Exporter、MySQL Exporter など）がベーシック[認証](/glossary/認証/)で保護されている場合、該当するジョブ設定に `basic_auth` セクションを追加する必要があります。

**Grafana 経由でのアクセス：** Grafana が Prometheus を Datasource として登録している場合、Datasource 設定画面の「Authentication」セクションで認証情報を入力してください。curl で[テスト](/glossary/テスト/)する際と同じ認証方式（ベーシック[認証](/glossary/認証/)、[TLS](/glossary/tls/)、[OAuth](/glossary/oauth/) など）を選択します。

**リモート書き込み・読み取り設定：** `remote_write` や `remote_read` で別の Prometheus [インスタンス](/glossary/インスタンス/)と[通信](/glossary/通信/)する際も、同様に `basic_auth` や `tls_config` を設定する必要があります。

```yaml
remote_write:
  - url: https://remote-prometheus:9090/api/v1/write
    basic_auth:
      username: '<your-username>'
      password: '<your-password>'
    tls_config:
      ca_file: /etc/prometheus/certs/ca.crt
      cert_file: /etc/prometheus/certs/client.crt
      key_file: /etc/prometheus/certs/client.key
```

## それでも解決しない場合

**1. Prometheus の[ログ](/glossary/ログ/)を確認：**

```bash
# ログレベルをdebugに上げて起動
./prometheus --log.level=debug --config.file=prometheus.yml
```

[ログ](/glossary/ログ/)に[認証](/glossary/認証/)[ヘッダー](/glossary/ヘッダー/)や [TLS](/glossary/tls/) ハンドシェイクの[エラー](/glossary/エラー/)が記録されているか確認してください。

**2. curl での[テスト](/glossary/テスト/)：**

```bash
# ベーシック認証付きでテスト
curl -u <your-username>:<your-password> \
     http://prometheus-server:9090/api/v1/query?query=up

# TLS付きでテスト
curl --cert /path/to/client.crt \
     --key /path/to/client.key \
     --cacert /path/to/ca.crt \
     https://prometheus-server:9090/api/v1/query?query=up
```

**3. Prometheus の[設定ファイル](/glossary/設定ファイル/)検証：**

```bash
./prometheus --config.file=prometheus.yml --config.check
```

設定に誤りがないか確認します。

**4. リバースプロキシのアクセスログ確認：**

Nginx の場合、`/var/log/nginx/access.log` や `error.log` で[認証](/glossary/認証/)の成否や転送状況を確認します。

```bash
tail -f /var/log/nginx/error.log | grep authorization
```

**5. 公式ドキュメント：**

- [Prometheus Configuration - Basic Auth](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#basic_auth)
- [Prometheus Configuration - TLS Config](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#tls_config)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*