---
title: "Prometheus の 503 エラー：原因と解決策"
date: 2026-06-22
description: "Prometheusが起動中かスクレイプターゲットが利用できない。"
tags: ["Prometheus"]
errorCode: "503"
service: "Prometheus"
error_type: "503"
components: []
related_services: ["node-exporter"]
conclusion: "Prometheus の 503 エラーは、Prometheus 自体が起動中またはスクレイプターゲットが利用できないことを示します。プロセス状態の確認、ターゲットの疎通確認、ストレージ容量のチェックを順に行うことで解決できます。"
---

## エラーの概要

Prometheus が 503 Service Unavailable [エラー](/glossary/エラー/)を返す場合、[メトリクス](/glossary/メトリクス/)収集システム自体が正常に動作していないか、監視対象となる[エンドポイント](/glossary/エンドポイント/)（スクレイプターゲット）へのアクセスが失敗しています。この[エラー](/glossary/エラー/)は起動直後の初期化中、ターゲットの障害、またはストレージリソース不足の3つの場面で頻繁に発生します。Prometheus の管理画面にアクセスできる場合と、完全に応答がない場合とで対応手順が異なります。

## 実際のエラーメッセージ例

Prometheus の Web UI にアクセスした際の[レスポンス](/glossary/レスポンス/):

```
HTTP/1.1 503 Service Unavailable
Content-Type: text/html; charset=utf-8

<html>
<head><title>503 Service Unavailable</title></head>
<body>
<h1>503 Service Unavailable</h1>
<p>Prometheus is starting up</p>
</body>
</html>
```

スクレイプ失敗時の[ログ](/glossary/ログ/)出力例:

```
level=warn ts=2024-01-15T10:23:45.123Z caller=scrape.go:1234 component=scraper msg="scrape failed" job=<your-job-name> err="context deadline exceeded"
```

## よくある原因と解決手順

### 原因1：Prometheus が起動中またはクラッシュしている

Prometheus の起動直後は、WAL（Write-Ahead Log）の復旧やメモリ初期化処理が行われます。この期間中は外部からの[リクエスト](/glossary/リクエスト/)に対して 503 [エラー](/glossary/エラー/)を返します。同時に、メモリ不足やセグメンテーションフォルトなどの原因でプロセスが停止している場合も 503 が返されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# 状態確認なしに再起動して問題を見落とす
sudo systemctl restart prometheus
```

**After（修正後）：**

```bash
# Prometheus のプロセス状態を確認
sudo systemctl status prometheus

# 詳細なジャーナルログを確認
sudo journalctl -u prometheus -n 50 --no-pager

# プロセスが停止している場合は起動
sudo systemctl start prometheus

# 起動後、起動完了までの時間を確認（通常数秒〜数十秒）
sleep 10 && curl -s http://localhost:9090/-/healthy
```

起動完了の確認は `http://localhost:9090/-/healthy` [エンドポイント](/glossary/エンドポイント/)で行えます。[レスポンス](/glossary/レスポンス/)が 200 OK であれば起動完了です。

### 原因2：スクレイプターゲットが停止またはタイムアウトしている

Prometheus の主要機能は[メトリクス](/glossary/メトリクス/)の収集です。[設定ファイル](/glossary/設定ファイル/)内に定義されたターゲット（監視対象[サーバー](/glossary/サーバー/)の[エンドポイント](/glossary/エンドポイント/)）が停止していたり、ネットワークタイムアウトが発生していたりすると、Prometheus 全体が 503 を返すことがあります。特に、スクレイプタイムアウトが非常に短く設定されている場合は注意が必要です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  scrape_timeout: 1s  # 1秒はネットワーク遅延が大きい環境では短すぎる

scrape_configs:
  - job_name: 'node-exporter'
    static_configs:
      - targets: ['<your-target-host>:9100']
```

**After（修正後）：**

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  scrape_timeout: 10s  # ネットワーク遅延を考慮した値

scrape_configs:
  - job_name: 'node-exporter'
    static_configs:
      - targets: ['<your-target-host>:9100']
    relabel_configs:
      - source_labels: [__address__]
        target_label: instance
```

Prometheus の管理画面で実際のターゲット状態を確認します：

```bash
# Prometheus の Web UI から「Status」→「Targets」にアクセス
# または API で確認
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .job, endpoint: .scrapeUrl, health: .health}'

# 個別ターゲットへの直接疎通確認
curl -v http://<your-target-host>:9100/metrics
```

ターゲットが応答しない場合は、対象[サーバー](/glossary/サーバー/)の[ポート](/glossary/ポート/)番号や[ファイアウォール](/glossary/ファイアウォール/)設定を確認します。

### 原因3：Prometheus のストレージが満杯になっている

Prometheus はメトリクスデータを時系列形式でディスク上に保存します。`--storage.tsdb.path` で指定されたディレクトリ（デフォルトは `./data`）の空き容量がなくなると、新たな[メトリクス](/glossary/メトリクス/)書き込みが失敗し、[クエリ](/glossary/クエリ/)に対して 503 を返すようになります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# ディスク容量を確認しない設定
# retention days を確認しない
```

**After（修正後）：**

```bash
# ストレージの使用状況を確認
df -h /var/lib/prometheus
# 出力例:
# Filesystem      Size  Used Avail Use% Mounted on
# /dev/sda1       100G  98G  1.5G  99% /

# Prometheus のデータディレクトリサイズを確認
du -sh /var/lib/prometheus/data

# 古いデータを削除する場合：prometheus.yml で retention を設定
# または旧ブロックを手動削除
find /var/lib/prometheus/data -type d -name "*.db" -mtime +30 -exec rm -rf {} \;

# 設定ファイルで retention days を明示的に設定
# prometheus.yml の global セクションに以下を追加:
# global:
#   retention: 90d

# 変更後は Prometheus を再起動
sudo systemctl restart prometheus
```

容量が逼迫している場合、即座に古いデータを削除するか、アーカイブストレージへの移行を検討します。

## ツール固有の注意点

Prometheus は [HTTP](/glossary/http/) [ステータスコード](/glossary/ステータスコード/) 503 を複数の状況で返すため、[エラーメッセージ](/glossary/エラーメッセージ/)のテキスト内容で原因を判定することが重要です。

Web UI の「Status」メニューから以下の情報を確認できます：

```
- Targets：各スクレイプターゲットの状態（UP/DOWN）
- Configuration：現在適用されている prometheus.yml の内容
- Flags：起動時の設定フラグと値
- Service Discovery：サービスディスカバリーで検出されたターゲット
```

特に重要なのは Targets ページです。ここで DOWN となっているターゲットを確認し、Last Error メッセージから具体的な原因（接続拒否、[タイムアウト](/glossary/タイムアウト/)、[DNS](/glossary/dns/) 解決失敗など）を特定できます。

[Kubernetes](/glossary/kubernetes/) 環境で Prometheus を運用する場合は、Pod のリソースリクエスト・リミットを確認し、メモリ不足で OOMKill されていないかを確認します：

```bash
# Pod のイベント履歴を確認
kubectl describe pod prometheus-pod -n monitoring

# リソース使用量を確認
kubectl top pod prometheus-pod -n monitoring
```

## それでも解決しない場合

Prometheus のデバッグログを有効化して詳細な情報を収集します：

```bash
# 起動時に --log.level=debug を指定
sudo systemctl stop prometheus
prometheus --config.file=/etc/prometheus/prometheus.yml --log.level=debug

# または systemd サービスファイルで設定
# /etc/systemd/system/prometheus.service
# [Service]
# ExecStart=/usr/local/bin/prometheus --config.file=/etc/prometheus/prometheus.yml --log.level=debug
```

ジャーナルログから詳細な[エラー](/glossary/エラー/)を確認します：

```bash
# リアルタイムでログを監視
sudo journalctl -u prometheus -f

# 最後の500行を表示
sudo journalctl -u prometheus -n 500 --no-pager
```

prometheus.yml の [YAML](/glossary/yaml/) 構文を検証します：

```bash
# curl で Prometheus のサーバーに設定をロードさせる
curl -X POST http://localhost:9090/-/reload

# promtool を使用した構文チェック
promtool check config /etc/prometheus/prometheus.yml
```

[ファイアウォール](/glossary/ファイアウォール/)・セキュリティグループの設定を確認し、Prometheus から各スクレイプターゲットへの[通信](/glossary/通信/)が遮断されていないか確認します：

```bash
# ターゲットへの通信を確認
telnet <your-target-host> 9100
nc -zv <your-target-host> 9100
```

公式ドキュメントの[Troubleshooting](https://prometheus.io/docs/prometheus/latest/troubleshooting/troubleshooting/)セクションと[疎通確認ガイド](https://prometheus.io/docs/prometheus/latest/management_api/)も参照してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
