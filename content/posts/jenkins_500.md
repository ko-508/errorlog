---
draft: true
title: "Jenkins の 500 エラー：原因と解決策"
date: 2026-06-19
description: "Jenkinsサーバーで予期しない内部エラーが発生した"
tags: ["Jenkins"]
errorCode: "500"
service: "Jenkins"
error_type: "500"
components: []
related_services: ["Java", "Groovy", "OutOfMemoryError"]
---

## エラーの概要

Jenkinsの500[エラー](/glossary/エラー/)は、Jenkins[サーバー](/glossary/サーバー/)で予期しない内部[エラー](/glossary/エラー/)が発生したことを示します。この際、[リクエスト](/glossary/リクエスト/)の処理中に[サーバー](/glossary/サーバー/)側で制御不能な例外やリソース枯渇が生じており、正常な[レスポンス](/glossary/レスポンス/)を返すことができない状態です。Webブラウザでジョブを実行したり、設定を変更したり、[API](/glossary/api/)[エンドポイント](/glossary/エンドポイント/)にアクセスしたりする際に発生することが多くあります。

## 実際のエラーメッセージ例

**Jenkinsの画面表示：**

```html
HTTP Status 500 – Internal Server Error
java.lang.OutOfMemoryError: Java heap space
	at hudson.model.Queue.schedule(Queue.java:1234)
	at hudson.model.AbstractProject.scheduleBuild2(AbstractProject.java:567)
```

**ブラウザの[コンソール](/glossary/コンソール/)出力（[API](/glossary/api/)[リクエスト](/glossary/リクエスト/)時）：**

```json
{
  "status": 500,
  "message": "Internal Server Error",
  "error": "java.lang.NullPointerException at jenkins.plugins.shiningpanda.interpreters.Interpreters.getDefaultInterpreter(Interpreters.java:123)"
}
```

## よくある原因と解決手順

### 原因1：プラグインのクラッシュまたは競合

Jenkinsのプラグインが正常に動作せず、クラッシュするか他のプラグインと競合している場合、500[エラー](/glossary/エラー/)が発生します。特に新しくインストールされたプラグインやバージョンアップ直後に多く見られます。

Jenkinsの[ログファイル](/glossary/ログファイル/)を確認してから、問題のあるプラグインを特定し無効化します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# Jenkinsを起動すると無効なプラグインによってエラーが発生
sudo systemctl start jenkins
# ブラウザでアクセスすると500エラーが返される
curl -s http://localhost:8080/jenkins/ | grep "500"
```

**After（修正後）：**

```bash
# ログから問題のプラグインを特定
sudo tail -100 /var/log/jenkins/jenkins.log | grep -i "error\|exception"

# 問題のプラグインディレクトリをリネーム（無効化）
sudo mv /var/lib/jenkins/plugins/problematic-plugin.jpi /var/lib/jenkins/plugins/problematic-plugin.jpi.disabled

# Jenkinsを再起動
sudo systemctl restart jenkins

# 動作確認
curl -I http://localhost:8080/jenkins/
# HTTP/1.1 200 OK が返される
```

### 原因2：OutOfMemoryErrorによるメモリ枯渇

Jenkinsが管理するビルドジョブやプラグインが大量の[メモリ](/glossary/メモリ/)を消費し、Java のヒープメモリが枯渇してOutOfMemoryErrorが発生します。大規模なプロジェクトや並行ビルド数が多い環境で顕著です。

Jenkinsの起動設定を修正して、ヒープメモリの上限を増やします。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# Jenkinsの起動オプションが不十分
cat /etc/default/jenkins | grep JAVA_ARGS
# 出力: JAVA_ARGS="-Xmx512m"  ← 512MBは不十分

# ビルド実行時にメモリ不足エラーが発生
curl -X POST http://localhost:8080/jenkins/job/<your-job-name>/build
# HTTP/1.1 500 Internal Server Error
```

**After（修正後）：**

```bash
# Jenkinsの設定ファイルを編集
sudo vi /etc/default/jenkins

# JAVA_ARGSを修正（512MB → 4GB）
# 修正前: JAVA_ARGS="-Xmx512m"
# 修正後: JAVA_ARGS="-Xmx4g -XX:+UseG1GC"

# 設定を適用するため再起動
sudo systemctl restart jenkins

# メモリ設定を確認
ps aux | grep jenkins | grep Xmx
# java ... -Xmx4g ... が表示される
```

### 原因3：ビルドスクリプトまたはGroovyコード内の未処理例外

Jenkinsのジョブで実行するシェルスクリプトやGroovy Script が未処理の例外をスロー、あるいは予期しない終了状態を返す場合、500[エラー](/glossary/エラー/)が発生することがあります。特にスクリプトの実行中に[ファイル](/glossary/ファイル/)が見つからない、[権限](/glossary/権限/)がない、外部[コマンド](/glossary/コマンド/)が存在しないなどの状況です。

スクリプトの[例外処理](/glossary/例外処理/)を強化し、[エラーハンドリング](/glossary/エラーハンドリング/)を明示的に記述します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```groovy
// Jenkinsのジョブで実行されるGroovyスクリプト
pipeline {
    stages {
        stage('Build') {
            steps {
                script {
                    def configFile = readFile('config/missing-file.json')
                    def parsedConfig = readJSON text: configFile
                    // ファイルが存在しなければ例外がスロー → 500エラー
                    echo "Config loaded: ${parsedConfig}"
                }
            }
        }
    }
}
```

**After（修正後）：**

```groovy
// エラーハンドリングを追加したGroovyスクリプト
pipeline {
    stages {
        stage('Build') {
            steps {
                script {
                    try {
                        if (fileExists('config/missing-file.json')) {
                            def configFile = readFile('config/missing-file.json')
                            def parsedConfig = readJSON text: configFile
                            echo "Config loaded: ${parsedConfig}"
                        } else {
                            echo "Warning: config file not found, using defaults"
                            // デフォルト設定で継続
                        }
                    } catch (Exception e) {
                        echo "Error loading config: ${e.message}"
                        currentBuild.result = 'UNSTABLE'
                    }
                }
            }
        }
    }
}
```

## ツール固有の注意点

**Jenkinsのプラグイン管理画面での確認方法：**

Manage Jenkins → System Configuration → Manage Plugins から、インストール済みのプラグイン一覧を確認できます。[エラー](/glossary/エラー/)発生前後でインストール・更新したプラグインを特定し、その右側のチェックボックスを外して無効化できます。ただしこの操作中も500[エラー](/glossary/エラー/)が出ることがあるため、前述のファイルシステム操作での対応が確実です。

**Jenkinsの[設定ファイル](/glossary/設定ファイル/)直接編集：**

Jenkinsを停止してから、`/var/lib/jenkins/jenkins.xml` や `/var/lib/jenkins/config.xml` を直接編集することもできます。ただし[XML](/glossary/xml/)構文[エラー](/glossary/エラー/)があると起動すらできなくなるため、編集前に[バックアップ](/glossary/バックアップ/)を取得することが重要です。

```bash
# 設定ファイルのバックアップ
sudo cp /var/lib/jenkins/config.xml /var/lib/jenkins/config.xml.backup

# Jenkinsを停止
sudo systemctl stop jenkins

# 設定を編集（エディタで修正）
sudo vi /var/lib/jenkins/config.xml

# Jenkinsを起動
sudo systemctl start jenkins
```

**Jenkinsの[バージョン](/glossary/バージョン/)と[互換性](/glossary/互換性/)：**

古い[バージョン](/glossary/バージョン/)のJenkinsで新しいプラグインをインストールすると[バージョン](/glossary/バージョン/)競合が発生し、500[エラー](/glossary/エラー/)になります。`Manage Plugins` で各プラグインが「[互換性](/glossary/互換性/)のある[バージョン](/glossary/バージョン/)」になっているか確認してください。

## それでも解決しない場合

**[ログファイル](/glossary/ログファイル/)の詳細確認：**

```bash
# Jenkinsのメインログを確認（最後の100行）
sudo tail -100 /var/log/jenkins/jenkins.log

# スタックトレース全体を見る
sudo grep -A 50 "Exception\|Error" /var/log/jenkins/jenkins.log

# ジョブの個別ログを確認
sudo cat /var/lib/jenkins/jobs/<your-job-name>/builds/lastBuild/log
```

**Jenkinsの再起動と[初期化](/glossary/初期化/)：**

```bash
# キャッシュをクリアして再起動
sudo systemctl stop jenkins
sudo rm -rf /var/lib/jenkins/cache/*
sudo systemctl start jenkins

# 起動状況を監視
sudo journalctl -u jenkins -f
```

**Java[バージョン](/glossary/バージョン/)の確認：**

プラグインがサポートしていないJava[バージョン](/glossary/バージョン/)が使用されている場合も500[エラー](/glossary/エラー/)になります。

```bash
java -version
# Jenkins 2.426以降はJava 11以上が必須
```

公式ドキュメント（https://www.jenkins.io/doc/book/system-administration/troubleshooting/）にて、より詳細なトラブルシューティングが提供されています。プラグイン固有の問題であれば、プラグインのGitHubページやJiraで既知の不具合がないか確認してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*