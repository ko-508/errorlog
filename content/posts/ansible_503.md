---
title: "Ansible の 503 エラー：原因と解決策"
date: 2026-06-11
description: "ターゲットサービスが一時的に利用できない。Ansible 503 エラーの原因と解決策を解説します。"
tags: ["Ansible"]
errorCode: "503"
service: "Ansible"
error_type: "503"
components: []
related_services: ["nginx"]
trend_incident: true
---
## エラーの概要

Ansible の 503 [エラー](/glossary/エラー/)は、ターゲットホスト上のサービスまたはシステムが一時的に利用できない状態を示します。SSH 接続は確立されているものの、実行対象のサービス（Web [サーバー](/glossary/サーバー/)、[データベース](/glossary/データベース/)、[API](/glossary/api/) 等）が停止中・起動中・リスタート中であるために、タスクの実行に失敗します。特にサービス再起動やローリング更新の際に頻出する[エラー](/glossary/エラー/)です。

## 実際のエラーメッセージ例

```json
{
  "msg": "503 Service Unavailable",
  "status_code": 503,
  "url": "http://target-host:8080/api/health",
  "ansible_facts": {},
  "failed": true
}
```

```bash
FAILED! => {
  "changed": false,
  "msg": "HTTP Error 503: Service Unavailable",
  "elapsed": 0.5,
  "status": 503
}
```

## よくある原因と解決手順

### 原因1：操作対象のサービスが停止またはリスタート中にある

Ansible でサービス再起動・[デプロイ](/glossary/デプロイ/)を行う際、次のタスクがサービス起動完了前に実行されると 503 [エラー](/glossary/エラー/)が発生します。特にローリング更新やブルーグリーンデプロイメント（新旧環境の同時実行）で顕著です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
- name: Restart web service
  service:
    name: nginx
    state: restarted

- name: Check API endpoint
  uri:
    url: "http://{{ inventory_hostname }}:8080/api/status"
    method: GET
    status_code: 200
  register: api_check
```

**After（修正後）：**

```yaml
- name: Restart web service
  service:
    name: nginx
    state: restarted

- name: Wait for service to be ready
  wait_for:
    host: "{{ inventory_hostname }}"
    port: 8080
    state: started
    delay: 2
    timeout: 30

- name: Check API endpoint
  uri:
    url: "http://{{ inventory_hostname }}:8080/api/status"
    method: GET
    status_code: 200
  register: api_check
```

`wait_for` モジュールを挿入することで、サービスが[ポート](/glossary/ポート/) 8080 でリッスン開始するまで次のタスク実行を遅延させます。`delay` は[リトライ](/glossary/リトライ/)開始前の待機秒数、`timeout` は総試行時間の上限です。

### 原因2：ターゲットホストへの SSH 接続がタイムアウトしている

SSH 接続自体が[タイムアウト](/glossary/タイムアウト/)すると、サービス確認ができず 503 [エラー](/glossary/エラー/)と同じく実行が失敗します。[ネットワーク](/glossary/ネットワーク/)遅延が大きい環境や[ファイアウォール](/glossary/ファイアウォール/)設定が厳しい場合に発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```ini
[webservers]
web-server-1 ansible_host=192.168.1.100

[webservers:vars]
ansible_user=deploy
ansible_ssh_key_file=/home/user/.ssh/id_rsa
```

**After（修正後）：**

```ini
[webservers]
web-server-1 ansible_host=192.168.1.100

[webservers:vars]
ansible_user=deploy
ansible_ssh_key_file=/home/user/.ssh/id_rsa
ansible_connection_timeout=60
ansible_ssh_timeout=60
```

インベントリファイルに `ansible_connection_timeout` と `ansible_ssh_timeout` を設定し、デフォルトの 10 秒から 60 秒に延長します。非常に遠い環境や低速[ネットワーク](/glossary/ネットワーク/)では、さらに 120 秒以上に設定することもあります。

### 原因3：ネットワーク障害でターゲットに到達できない

[ネットワーク](/glossary/ネットワーク/)の一時的な分断、[ファイアウォール](/glossary/ファイアウォール/)設定の不備、ルーティング問題により、ターゲットホストに[パケット](/glossary/パケット/)が到達しなくなると 503 [エラー](/glossary/エラー/)が発生します。実際には 503 ではなく接続自体が失敗する場合もありますが、ターゲット側の[ロードバランサー](/glossary/ロードバランサー/)が返す 503 として観測されることがあります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
- name: Run critical task without network validation
  hosts: all
  tasks:
    - name: Update application
      shell: /opt/app/update.sh
```

**After（修正後）：**

```yaml
- name: Run critical task with network validation
  hosts: all
  tasks:
    - name: Verify connectivity
      ping:
      register: ping_result

    - name: Check DNS resolution
      shell: nslookup {{ inventory_hostname }}
      changed_when: false
      run_once: true

    - name: Test SSH port connectivity
      wait_for:
        host: "{{ inventory_hostname }}"
        port: 22
        state: started
        timeout: 10
      delegate_to: localhost

    - name: Update application
      shell: /opt/app/update.sh
      when: ping_result is succeeded
```

`ping` モジュールで基本接続を確認し、[DNS](/glossary/dns/) 解決と[ポート](/glossary/ポート/)到達可能性を事前チェックしてからタスク実行に進みます。条件付き実行（`when`）で失敗時の安全性も確保します。

## ツール固有の注意点

**wait_for モジュールのパラメーター設計**

`wait_for` で[ポート](/glossary/ポート/)のリッスン確認をする際、`state: started` は TCP コネクション試行で判定するため、サービスが [HTTP](/glossary/http/) [レスポンス](/glossary/レスポンス/)を返せるまでの時間は含みません。より堅牢なチェックには、URI モジュールにリトライロジックを組み合わせます：

```yaml
- name: Wait for HTTP endpoint to be healthy
  uri:
    url: "http://{{ inventory_hostname }}:8080/health"
    method: GET
    status_code: 200
  register: health_check
  until: health_check.status == 200
  retries: 30
  delay: 2
```

`retries` と `until` を組み合わせることで、最大 60 秒間、2 秒間隔で [HTTP](/glossary/http/) 200 が返されるまで待機します。

**複数ホストへの並行実行と serial パラメーター**

ローリング更新では `serial` パラメーターで同時実行数を制限し、一部ホストの 503 が全体の失敗に繋がるのを防ぎます：

```yaml
- name: Rolling update
  hosts: webservers
  serial: 2
  tasks:
    - name: Restart service
      service:
        name: nginx
        state: restarted
    
    - name: Wait for health check
      uri:
        url: "http://{{ inventory_hostname }}:8080/health"
        status_code: 200
      until: result is succeeded
      retries: 10
      delay: 3
```

`serial: 2` で、1 つのタスク実行サイクルで最大 2 ホストのみを処理します。

## それでも解決しない場合

**1. 接続確認[コマンド](/glossary/コマンド/)実行**

まず基本的な接続[テスト](/glossary/テスト/)を実施します：

```bash
ansible <ホスト名> -m ping
ansible <ホスト名> -m setup -a "filter=ansible_os_family"
ansible <ホスト名> -c local -m command -a "systemctl status nginx"
```

**2. サービス状態を直接確認**

ターゲットホストへ SSH で直接[ログイン](/glossary/ログイン/)し、サービスの状態を確認します：

```bash
ssh deploy@192.168.1.100
systemctl status nginx
journalctl -u nginx -n 50
netstat -tuln | grep 8080
```

**3. Ansible の詳細[ログ](/glossary/ログ/)を出力**

Ansible 実行時に `-vvv` フラグで詳細[ログ](/glossary/ログ/)を取得し、どの段階で失敗しているかを特定します：

```bash
ansible-playbook playbook.yml -vvv -e "ansible_python_interpreter=/usr/bin/python3"
```

**4. 公式ドキュメント・コミュニティの確認**

- [Ansible 公式ドキュメント：uri モジュール](https://docs.ansible.com/ansible/latest/modules/uri_module.html)
- [wait_for モジュール](https://docs.ansible.com/ansible/latest/modules/wait_for_module.html)
- [インベントリ接続設定](https://docs.ansible.com/ansible/latest/user_guide/intro_inventory.html#managing-dynamic-inventory)

[ファイアウォール](/glossary/ファイアウォール/)・セキュリティグループ設定の確認も同時に実施してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*