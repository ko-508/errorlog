---
draft: true
title: "Jenkins の 503 エラー：原因と解決策"
date: 2026-06-19
description: "Jenkinsサービスが利用できない状態にある"
tags: ["Jenkins"]
errorCode: "503"
service: "Jenkins"
error_type: "503"
components: ["Pipeline", "Job", "Plugin", "Credentials"]
related_services: ["systemd", "curl", "nc"]
---

## エラーの概要

Jenkins の 503 [エラー](/glossary/エラー/)は「Service Unavailable」を意味し、Jenkins[サーバー](/glossary/サーバー/)が一時的に[リクエスト](/glossary/リクエスト/)を処理できない状態です。この[エラー](/glossary/エラー/)が発生すると、ブラウザ上でジョブのトリガーや[ダッシュボード](/glossary/ダッシュボード/)へのアクセスが失敗します。原因としてはJenkinsプロセスの停止、[メモリ](/glossary/メモリ/)枯渇、セーフリスタートモード中の状態などが考えられます。

## 実際のエラーメッセージ例

ブラウザでJenkinsにアクセスした際に表示される[エラー](/glossary/エラー/)：

```
HTTP/1.1 503 Service Unavailable
Content-Type: text/html; charset=utf-8

<html>
  <head>
    <title>Error 503 Service Unavailable</title>
  </head>
  <body>
    <h1>HTTP ERROR 503 Service Unavailable</h1>
  </body>
</html>
```

Jenkinsの[ログ](/glossary/ログ/)に出力される典型的なメッセージ：

```
2024-01-15 10:23:45.123 [main] ERROR jenkins.util.SystemProperties - Failed to initialize Jenkins
2024-01-15 10:23:45.456 [main] WARN hudson.lifecycle.Lifecycle - Jenkins is in safe restart mode, refusing new builds
```

## よくある原因と解決手順

### 原因1：Jenkinsのサービスが停止またはクラッシュしている

Jenkinsプロセスが意図しないタイミングで終了していたり、起動に失敗している場合、[サーバー](/glossary/サーバー/)に接続できずに503[エラー](/glossary/エラー/)が返されます。これはOOMKill（[メモリ](/glossary/メモリ/)不足による強制終了）や予期したシャットダウンで発生することが多いです。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# Jenkinsサービスの状態確認もなしに、ジョブをトリガーしようとする
curl -X POST http://localhost:8080/job/<your-job-name>/build
```

**After（修正後）：**

```bash
# まずJenkinsサービスの状態を確認する
sudo systemctl status jenkins

# サービスが停止していた場合、再起動する
sudo systemctl restart jenkins

# 再起動完了を待ってからジョブをトリガーする
sleep 10
curl -X POST http://localhost:8080/job/<your-job-name>/build
```

サービスが起動していることを確認してから、以下の[コマンド](/glossary/コマンド/)でJenkinsが完全に起動するまで待つとよいでしょう。

```bash
# Jenkinsが起動完了するまで待機（ポート接続確認）
timeout 60 bash -c 'until nc -z localhost 8080; do sleep 1; done' && echo "Jenkins is up"
```

### 原因2：Jenkinsのメモリ不足や過負荷でリクエストを処理できない

複数の大規模ビルドが並行実行されたり、プラグイン数が増加したり、古いビルドログが蓄積したりすると、Jenkinsプロセスが[メモリ](/glossary/メモリ/)枯渇に陥ります。この場合、新規[リクエスト](/glossary/リクエスト/)は受け付けられず503[エラー](/glossary/エラー/)が返されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# Jenkinsの起動時のメモリ設定が不足している例
# JENKINS_JAVA_OPTS の設定が不十分
export JENKINS_JAVA_OPTS="-Xms256m -Xmx512m"
java -jar jenkins.war
```

**After（修正後）：**

```bash
# Jenkinsのメモリ設定を増やす
# systemdを使用している場合の例
# /etc/systemd/system/jenkins.service または /etc/systemd/system/jenkins.service.d/override.conf に記述
export JENKINS_JAVA_OPTS="-Xms1g -Xmx2g -XX:+UseG1GC -XX:MaxGCPauseMillis=200"
sudo systemctl daemon-reload
sudo systemctl restart jenkins
```

[メモリ](/glossary/メモリ/)使用状況を[リアルタイム](/glossary/リアルタイム/)で監視する場合は、以下の[コマンド](/glossary/コマンド/)で確認します。

```bash
# Jenkinsプロセスのメモリ使用量を確認
ps aux | grep jenkins | grep -v grep

# より詳細なメモリ統計を取得
top -p $(pgrep -f "jenkins.war")
```

また、Jenkinsの管理画面の「Manage Jenkins」→「System Information」でヒープメモリの状態を確認することも重要です。ヒープ使用率が90%以上の場合は即座に[メモリ](/glossary/メモリ/)増設が必要です。

### 原因3：セーフリスタートモードが有効になっている

Jenkinsの更新やプラグインのインストール後、セーフリスタートモードに入ることがあります。このモード中は新規ビルドのトリガーが拒否され、既存のジョブも完全には動作しない状態になります。ユーザーが誤ってセーフリスタートを実行したり、手動でファイルを編集してこのモードに突入することもあります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# セーフリスタートモードを無視してビルドをトリガーする
curl -X POST http://localhost:8080/job/<your-job-name>/build \
  -H "Authorization: Bearer <your-api-token>"
# レスポンス: 503 Service Unavailable
```

**After（修正後）：**

```bash
# 1. Jenkinsの管理画面でセーフリスタートモードを確認
# ブラウザで http://localhost:8080/manage にアクセス
# または API で確認する場合：
curl http://localhost:8080/api/json | grep -i safe

# 2. セーフリスタートモードが有効な場合、通常リスタートを実行
# Jenkinsの管理画面で「Restart Jenkins」ボタンをクリック
# または以下のコマンドで実行
curl -X POST http://localhost:8080/exit \
  -H "Authorization: Bearer <your-api-token>"

# 3. Jenkinsが再起動完了するまで待機
sleep 30

# 4. ビルドをトリガー（セーフリスタート完了後）
curl -X POST http://localhost:8080/job/<your-job-name>/build \
  -H "Authorization: Bearer <your-api-token>"
```

セーフリスタートファイルを手動で削除する方法もあります（強制的な解除）。

```bash
# Jenkinsを停止してからセーフリスタートファイルを削除
sudo systemctl stop jenkins
sudo rm -f /var/lib/jenkins/safeRestart.txt
sudo systemctl start jenkins
```

## ツール固有の注意点

Jenkins 環境ではプラグインの[バージョン](/glossary/バージョン/)競合やスクリプトコンソールの実行でも[メモリ](/glossary/メモリ/)枯渇が発生することがあります。「Manage Jenkins」→「Plugin Manager」で不要または古いプラグインを定期的に削除することをお勧めします。

また、Jenkinsの `jenkins.log` と `jenkins.err` [ログファイル](/glossary/ログファイル/)は `/var/log/jenkins/` または JENKINS_HOME 配下に保存されます。503[エラー](/glossary/エラー/)の詳細な原因を調査する際は、これらの[ログ](/glossary/ログ/)を最初に確認してください。特に「OutOfMemoryError」「Address already in use」というメッセージが出ていないかを検索するとよいでしょう。

[Docker](/glossary/docker/) を使用している場合、Jenkins[コンテナ](/glossary/コンテナ/)のリソース上限（CPU・[メモリ](/glossary/メモリ/)）が低く設定されていないか確認してください。`docker inspect <container-id>` で `Memory`、`MemorySwap` の値を確認し、必要に応じて `docker update --memory <新しいサイズ> <container-id>` で増加させます。

## それでも解決しない場合

以下の手順でさらに詳細に診断を進めてください。

**1. Jenkinsの[ログ](/glossary/ログ/)を確認する**

```bash
# Jenkinsのログディレクトリを確認
sudo tail -f /var/log/jenkins/jenkins.log

# または JENKINS_HOME 内のログを確認
sudo tail -f /var/lib/jenkins/jenkins.log
```

**2. Jenkinsプロセスが起動していることを確認する**

```bash
# Javaプロセスが存在するか確認
ps aux | grep java | grep jenkins

# ポート 8080 でリッスンしているか確認
sudo netstat -tlnp | grep 8080
# または
sudo ss -tlnp | grep 8080
```

**3. Jenkinsの起動[ログ](/glossary/ログ/)を確認する**

```bash
# systemd経由での起動ログを確認
sudo journalctl -u jenkins -n 50 --no-pager

# または syslog を確認
sudo grep jenkins /var/log/syslog | tail -20
```

**4. JENKINS_HOME の[権限](/glossary/権限/)を確認する**

```bash
# Jenkinsの JENKINS_HOME ディレクトリ（通常は /var/lib/jenkins）の権限確認
ls -ld /var/lib/jenkins
sudo chown -R jenkins:jenkins /var/lib/jenkins
sudo chmod -R 755 /var/lib/jenkins
```

**5. Jenkinsの[設定ファイル](/glossary/設定ファイル/)を確認する**

```bash
# Jenkins サービスファイルの設定を確認
cat /etc/systemd/system/jenkins.service
# または
cat /etc/default/jenkins
```

これらの診断を実施してもなお503[エラー](/glossary/エラー/)が解決しない場合は、Jenkins の公式ドキュメント（https://www.jenkins.io/doc/）や GitHub Issues（https://github.com/jenkinsci/jenkins/issues）で同様の事例がないか検索することをお勧めします。その際、Jenkins の[バージョン](/glossary/バージョン/)、JDK [バージョン](/glossary/バージョン/)、インストール済みプラグイン一覧、[メモリ](/glossary/メモリ/)設定を記録して報告すると、より正確な原因特定が可能になります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*