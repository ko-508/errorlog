---
draft: true
title: "Prometheus の 403 エラー：原因と解決策"
date: 2026-06-21
description: "Prometheus APIへのアクセスが拒否された"
tags: ["Prometheus"]
errorCode: "403"
service: "Prometheus"
error_type: "403"
components: []
related_services: ["Nginx", "Apache", "Envoy", "firewalld", "iptables", "AWS EC2", "systemd"]
conclusion: "Prometheus の 403 エラーは、管理 API が有効化されていないか、ファイアウォール・リバースプロキシでアクセスが制限されていることが原因です。`--web.enable-admin-api` フラグを追加してサービスを再起動し、ネットワーク設定を確認することで解決できます。"
---

## エラーの概要

Prometheus の 403 [エラー](/glossary/エラー/)は、[HTTP](/glossary/http/) Forbidden を意味し、[API](/glossary/api/) [エンドポイント](/glossary/エンドポイント/)へのアクセスが明示的に拒否されたことを示します。Prometheus では主に管理 [API](/glossary/api/)（削除操作やスナップショット生成など）へのアクセス制限に該当します。認証情報の不足や権限不足ではなく、[エンドポイント](/glossary/エンドポイント/)自体が無効化されているか、ネットワークレベルで遮断されている状態です。

## 実際のエラーメッセージ例

**cURL での [API](/glossary/api/) アクセス時：**

```bash
$ curl -X DELETE http://localhost:9090/api/v1/admin/tsdb/delete_series
<html>
<head><title>403 Forbidden</title></head>
<body>
<center><h1>403 Forbidden</h1></center>
<hr><center>nginx</center>
</body>
</html>
```

**Prometheus [ログ](/glossary/ログ/)出力例：**

```
level=warn msg="Received request to admin endpoint without admin API enabled" endpoint=/api/v1/admin/tsdb/delete_series remote_addr=192.168.1.100:52345
```

## よくある原因と解決手順

### 原因 1：管理 API が無効化されている

Prometheus のデフォルト設定では、[セキュリティ](/glossary/セキュリティ/)上の理由から危険な管理 [API](/glossary/api/)（時系列データの削除など）が無効化されています。`--web.enable-admin-api` フラグを明示的に指定しない起動では、管理[エンドポイント](/glossary/エンドポイント/)がすべて 403 で応答します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# 管理APIなしで起動
prometheus --config.file=prometheus.yml \
  --storage.tsdb.path=/var/lib/prometheus
```

**After（修正後）：**

```bash
# 管理APIを有効化して起動
prometheus --config.file=prometheus.yml \
  --storage.tsdb.path=/var/lib/prometheus \
  --web.enable-admin-api
```

systemd でサービス起動している場合は、`/etc/systemd/system/prometheus.service` の `ExecStart` に フラグを追加して再起動します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```ini
[Service]
ExecStart=/usr/local/bin/prometheus --config.file=/etc/prometheus/prometheus.yml
```

**After（修正後）：**

```ini
[Service]
ExecStart=/usr/local/bin/prometheus --config.file=/etc/prometheus/prometheus.yml \
  --web.enable-admin-api
```

設定後、`systemctl daemon-reload && systemctl restart prometheus` でサービスを再起動してください。

### 原因 2：ファイアウォールやセキュリティグループが Prometheus ポートをブロックしている

EC2・[クラウド](/glossary/クラウド/)環境では、セキュリティグループやファイアウォールルールが Prometheus のデフォルトポート（9090）への受信を拒否している場合があります。この場合、ローカル接続でも外部接続でも 403 ではなく[タイムアウト](/glossary/タイムアウト/)が発生する傾向ですが、[プロキシ](/glossary/プロキシ/)を経由した場合は明確な 403 応答となることがあります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# AWS EC2 セキュリティグループ例（Prometheus へのアクセス拒否）
# Inbound Rule: すべてのトラフィック拒否
```

**After（修正後）：**

```bash
# AWS セキュリティグループに受信ルールを追加
# Protocol: TCP
# Port Range: 9090
# Source: <your-client-ip>/32 または <your-vpc-cidr>
```

Linux ホスト上の firewalld を使用している場合：

```bash
# Prometheus ポートを許可
sudo firewall-cmd --permanent --add-port=9090/tcp
sudo firewall-cmd --reload
```

iptables の場合：

```bash
# 特定 IP からのアクセスのみ許可
sudo iptables -A INPUT -p tcp --dport 9090 -s <your-client-ip> -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 9090 -j DROP
```

### 原因 3：リバースプロキシの ACL 設定で管理 API がブロックされている

Prometheus の前段に Nginx・Apache・Envoy などのリバースプロキシを配置している場合、[プロキシ](/glossary/プロキシ/)側の ACL（アクセス制御リスト）で `/api/v1/admin/*` [エンドポイント](/glossary/エンドポイント/)が明示的に拒否されていることがあります。この場合、リバースプロキシ自体から 403 が返却されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```nginx
server {
  listen 80;
  server_name prometheus.example.com;

  location / {
    proxy_pass http://localhost:9090;
  }

  # 管理エンドポイントを拒否
  location ~ ^/api/v1/admin/ {
    return 403;
  }
}
```

**After（修正後）：**

```nginx
server {
  listen 80;
  server_name prometheus.example.com;

  location / {
    proxy_pass http://localhost:9090;
  }

  # 管理エンドポイントは特定の IP からのみ許可
  location ~ ^/api/v1/admin/ {
    allow <your-admin-ip>;
    deny all;
    proxy_pass http://localhost:9090;
  }
}
```

Nginx の設定変更後、`sudo nginx -s reload` で設定を反映させてください。

## ツール固有の注意点

**[Docker](/glossary/docker/) [コンテナ](/glossary/コンテナ/)での Prometheus 運用：**

[Docker](/glossary/docker/) で Prometheus を実行する場合、[コンテナ](/glossary/コンテナ/)起動時に `--web.enable-admin-api` フラグを渡す必要があります。

```bash
# 管理APIを有効化してコンテナ起動
docker run -d \
  --name prometheus \
  -p 9090:9090 \
  -v /path/to/prometheus.yml:/etc/prometheus/prometheus.yml \
  prom/prometheus \
  --config.file=/etc/prometheus/prometheus.yml \
  --web.enable-admin-api
```

**[Kubernetes](/glossary/kubernetes/) での Prometheus [デプロイ](/glossary/デプロイ/)：**

Helm で Prometheus をインストールする場合、`values.yaml` の `serverFiles.args` に フラグを追加してください。

```yaml
prometheus:
  prometheusSpec:
    containers:
      - name: prometheus
        args:
          - --config.file=/etc/prometheus/prometheus.yml
          - --web.enable-admin-api
```

**削除操作の実行例：**

管理 [API](/glossary/api/) 有効化後、時系列データの削除は以下の[コマンド](/glossary/コマンド/)で実行できます。

```bash
# メトリクス削除例
curl -X DELETE 'http://localhost:9090/api/v1/admin/tsdb/delete_series?match[]=metric_name'
```

## それでも解決しない場合

**Prometheus [ログ](/glossary/ログ/)の確認：**

サービス起動時の[ログ](/glossary/ログ/)で `admin API` のメッセージを確認してください。

```bash
# systemd サービス経由で起動している場合
sudo journalctl -u prometheus -f

# ログ出力に以下が含まれるか確認
# "msg=Listening..." "address=0.0.0.0:9090"
```

**[ネットワーク](/glossary/ネットワーク/)接続の確認：**

Prometheus が実際に[ポート](/glossary/ポート/) 9090 でリッスンしているか確認します。

```bash
# ポートがリッスン中か確認
sudo netstat -tlnp | grep 9090
# または
sudo ss -tlnp | grep 9090
```

**リバースプロキシの[ログ](/glossary/ログ/)確認：**

Nginx・Apache など[プロキシ](/glossary/プロキシ/)のアクセスログで実際の[リクエスト](/glossary/リクエスト/)・[レスポンス](/glossary/レスポンス/)を確認します。

```bash
# Nginx アクセスログ確認
sudo tail -f /var/log/nginx/access.log | grep 9090

# Apache アクセスログ確認
sudo tail -f /var/log/apache2/access.log | grep 9090
```

**管理 [API](/glossary/api/) の動作確認：**

フラグ追加後、管理[エンドポイント](/glossary/エンドポイント/)への简单な[リクエスト](/glossary/リクエスト/)で動作確認を行います。

```bash
# ヘルスチェック
curl -v http://localhost:9090/-/healthy

# ツナギエンドポイント（管理API非対象）で動作確認
curl -v http://localhost:9090/api/v1/query?query=up
```

公式ドキュメント：[Prometheus Management API](https://prometheus.io/docs/prometheus/latest/management_api/)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*