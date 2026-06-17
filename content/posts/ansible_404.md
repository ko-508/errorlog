---
title: "Ansible の 404 エラー：原因と解決策"
date: 2026-06-11
description: "ターゲットホストのリソースまたはエンドポイントが見つからない。Ansible 404 エラーの原因と解決策を解説します。"
tags: ["Ansible"]
errorCode: "404"
service: "Ansible"
error_type: "404"
components: []
related_services: []
trend_incident: true
---
## エラーの概要

Ansible の 404 エラーは、ターゲットホストで参照しようとしたリソースやエンドポイント、あるいはホスト自体が見つからないことを示します。このエラーはファイル操作、API 呼び出し、ホスト接続など複数の場面で発生し、単純なパスの誤記から始まり、ホスト間の接続性の問題まで様々な原因を持つことがあります。

## 実際のエラーメッセージ例

典型的な Ansible の 404 エラーメッセージ：

```
fatal: [<target-host>]: FAILED! => {"changed": false, "msg": "Failed to get information about file/directory <path>: No such file or directory", "path": "<path>"}
```

HTTP モジュール（uri, get_url）経由のエラー例：

```json
{
  "status": 404,
  "msg": "HTTP Error 404: Not Found",
  "url": "https://api.example.com/v1/endpoint",
  "failed": true
}
```

## よくある原因と解決手順

### 原因1：タスク内で参照するファイルまたはディレクトリが存在しない

ターゲットホスト上にファイルやディレクトリが存在しない場合、Ansible はそのリソースを操作できません。特に `copy` モジュールで `src` パラメーターに指定したファイル、あるいは `stat` や `find` モジュールで検索対象のパスが間違っていると発生します。

**Before（エラーが起きるコード）：**

```yaml
- name: Copy configuration file
  copy:
    src: /etc/myapp/config.yml
    dest: /opt/myapp/
    mode: '0644'
  remote_user: root
```

このタスクを実行した際、ターゲットホスト上に `/etc/myapp/config.yml` が存在しないと 404 エラーが発生します。

**After（修正後）：**

```yaml
- name: Check if config file exists
  stat:
    path: /etc/myapp/config.yml
  register: config_file
  
- name: Copy configuration file
  copy:
    src: /etc/myapp/config.yml
    dest: /opt/myapp/
    mode: '0644'
  when: config_file.stat.exists
  remote_user: root
```

ファイルの存在確認を先に行い、存在する場合のみコピーを実行するようにします。または、ターゲットホスト上で実際にパスを確認し、正しい絶対パスを指定してください。

### 原因2：外部API のURL が間違っているか変更された

`uri` モジュールや `get_url` モジュールで外部 API に接続する際、エンドポイントの URL が誤っているか、API 側で廃止されている可能性があります。特に API のバージョンが変更された場合は旧エンドポイントが削除されることがあります。

**Before（エラーが起きるコード）：**

```yaml
- name: Get API data from old endpoint
  uri:
    url: https://api.example.com/v1/old-endpoint
    method: GET
    status_code: 200
  register: api_response
```

API が v2 に更新され、`v1/old-endpoint` が廃止されていると 404 を返します。

**After（修正後）：**

```yaml
- name: Get API data from updated endpoint
  uri:
    url: https://api.example.com/v2/new-endpoint
    method: GET
    status_code: 200
    headers:
      Authorization: "Bearer {{ api_token }}"
  register: api_response
  failed_when: api_response.status not in [200, 404]
```

API ドキュメントを確認し、現在のエンドポイント URL を使用します。必要に応じてヘッダーや認証情報も併せて確認してください。

### 原因3：インベントリに登録したホストに接続できない

インベントリに記載したホストの IP アドレスやホスト名が誤っている、あるいはネットワーク接続が不可能な場合、Ansible はターゲットホストへアクセスできず 404 相当のエラーが発生します。

**Before（エラーが起きるコード）：**

```yaml
# inventory.ini
[webservers]
web01 ansible_host=192.168.1.999
web02 ansible_host=invalid.hostname
```

無効な IP アドレスやホスト名が指定されており、Ansible が接続できません。

**After（修正後）：**

```yaml
# inventory.ini
[webservers]
web01 ansible_host=192.168.1.100
web02 ansible_host=webserver02.example.com

# 接続確認用のプレイブック
---
- name: Verify host connectivity
  hosts: webservers
  gather_facts: no
  tasks:
    - name: Ping target hosts
      ping:
      register: ping_result
    
    - debug:
        msg: "{{ inventory_hostname }} is reachable"
      when: ping_result is succeeded
```

まず `ansible <ホスト名> -m ping` コマンドを実行してホストへの接続を確認します。接続できない場合は、ホスト名、IP アドレス、ネットワーク設定を見直してください。

## ツール固有の注意点

### copy モジュールの src パラメーター

Ansible の `copy` モジュールにおいて `src` パラメーターで指定するパスは、**Ansible コントローラーマシン**上のパスであって、ターゲットホスト上のパスではありません。コントローラーマシン側で実際にファイルが存在するか確認が必要です。

### リモートホスト上でのファイル操作

逆に `file` モジュールや `stat` モジュールで操作対象を指定する場合は、ターゲットホスト上での絶対パスを指定します。`shell` モジュールで `find` コマンドを実行して、事前にターゲットホスト上でファイルの場所を確認するのも有効です。

### HTTP ステータスコードの明示的な指定

`uri` モジュールを使用する際は、想定される HTTP ステータスコードを `status_code` パラメーターで明示的に指定してください。404 が予期されたレスポンスの場合は、`status_code: [200, 404]` のように複数の値を許容することで、Ansible がエラーと判定しなくなります。

## それでも解決しない場合

### デバッグコマンドでの確認

以下のコマンドを実行してターゲットホストの情報を確認します。

```bash
# 対象ホストへの接続確認
ansible <target-host> -m ping

# インベントリ内容の確認
ansible-inventory --list

# 詳細デバッグ情報を含めて実行
ansible-playbook -vvv playbook.yml

# ターゲットホスト上でのファイル確認
ansible <target-host> -m shell -a "ls -la <path>"
```

### Ansible ログの出力

実行時に環境変数でログレベルを上げて実行します。

```bash
export ANSIBLE_DEBUG=true
export ANSIBLE_LOG_PATH=/tmp/ansible.log
ansible-playbook playbook.yml
```

出力されたログファイル `/tmp/ansible.log` を確認することで、より詳細なエラーメッセージが得られます。

### 公式リソースへの参照

Ansible 公式ドキュメント（https://docs.ansible.com/）の該当モジュールセクションを確認してください。特に `uri` モジュール、`copy` モジュール、`stat` モジュールのドキュメントには、各パラメーターの詳細とよくある落とし穴が記載されています。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*