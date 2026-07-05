---
draft: true
title: "Ansible の 404 エラー：原因と解決策"
date: 2026-06-11
description: "ターゲットホストのリソースまたはエンドポイントが見つからない"
tags: ["Ansible"]
errorCode: "404"
service: "Ansible"
error_type: "404"
components: []
related_services: []
trend_incident: true
---
## エラーの概要

Ansible の 404 [エラー](/glossary/エラー/)は、ターゲットホストで参照しようとしたリソースや[エンドポイント](/glossary/エンドポイント/)、あるいはホスト自体が見つからないことを示します。この[エラー](/glossary/エラー/)はファイル操作、[API](/glossary/api/) 呼び出し、ホスト接続など複数の場面で発生し、単純な[パス](/glossary/パス/)の誤記から始まり、ホスト間の接続性の問題まで様々な原因を持つことがあります。

## 実際のエラーメッセージ例

典型的な Ansible の 404 [エラーメッセージ](/glossary/エラーメッセージ/)：

```
fatal: [<target-host>]: FAILED! => {"changed": false, "msg": "Failed to get information about file/directory <path>: No such file or directory", "path": "<path>"}
```

[HTTP](/glossary/http/) モジュール（uri, get_url）経由の[エラー](/glossary/エラー/)例：

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

ターゲットホスト上にファイルやディレクトリが存在しない場合、Ansible はそのリソースを操作できません。特に `copy` モジュールで `src` パラメーターに指定したファイル、あるいは `stat` や `find` モジュールで検索対象の[パス](/glossary/パス/)が間違っていると発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
- name: Copy configuration file
  copy:
    src: /etc/myapp/config.yml
    dest: /opt/myapp/
    mode: '0644'
  remote_user: root
```

このタスクを実行した際、ターゲットホスト上に `/etc/myapp/config.yml` が存在しないと 404 [エラー](/glossary/エラー/)が発生します。

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

ファイルの存在確認を先に行い、存在する場合のみコピーを実行するようにします。または、ターゲットホスト上で実際に[パス](/glossary/パス/)を確認し、正しい絶対[パス](/glossary/パス/)を指定してください。

### 原因2：外部API のURL が間違っているか変更された

`uri` モジュールや `get_url` モジュールで外部 [API](/glossary/api/) に接続する際、[エンドポイント](/glossary/エンドポイント/)の [URL](/glossary/url/) が誤っているか、[API](/glossary/api/) 側で廃止されている可能性があります。特に [API](/glossary/api/) の[バージョン](/glossary/バージョン/)が変更された場合は旧[エンドポイント](/glossary/エンドポイント/)が削除されることがあります。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
- name: Get API data from old endpoint
  uri:
    url: https://api.example.com/v1/old-endpoint
    method: GET
    status_code: 200
  register: api_response
```

[API](/glossary/api/) が v2 に更新され、`v1/old-endpoint` が廃止されていると 404 を返します。

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

[API](/glossary/api/) ドキュメントを確認し、現在の[エンドポイント](/glossary/エンドポイント/) [URL](/glossary/url/) を使用します。必要に応じて[ヘッダー](/glossary/ヘッダー/)や認証情報も併せて確認してください。

### 原因3：インベントリに登録したホストに接続できない

インベントリに記載したホストの IP アドレスやホスト名が誤っている、あるいは[ネットワーク](/glossary/ネットワーク/)接続が不可能な場合、Ansible はターゲットホストへアクセスできず 404 相当の[エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

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

まず `ansible <ホスト名> -m ping` [コマンド](/glossary/コマンド/)を実行してホストへの接続を確認します。接続できない場合は、ホスト名、IP アドレス、[ネットワーク](/glossary/ネットワーク/)設定を見直してください。

## ツール固有の注意点

### copy モジュールの src パラメーター

Ansible の `copy` モジュールにおいて `src` パラメーターで指定する[パス](/glossary/パス/)は、**Ansible コントローラーマシン**上の[パス](/glossary/パス/)であって、ターゲットホスト上の[パス](/glossary/パス/)ではありません。コントローラーマシン側で実際にファイルが存在するか確認が必要です。

### リモートホスト上でのファイル操作

逆に `file` モジュールや `stat` モジュールで操作対象を指定する場合は、ターゲットホスト上での絶対[パス](/glossary/パス/)を指定します。`shell` モジュールで `find` [コマンド](/glossary/コマンド/)を実行して、事前にターゲットホスト上でファイルの場所を確認するのも有効です。

### HTTP ステータスコードの明示的な指定

`uri` モジュールを使用する際は、想定される [HTTP](/glossary/http/) [ステータスコード](/glossary/ステータスコード/)を `status_code` パラメーターで明示的に指定してください。404 が予期された[レスポンス](/glossary/レスポンス/)の場合は、`status_code: [200, 404]` のように複数の値を許容することで、Ansible が[エラー](/glossary/エラー/)と判定しなくなります。

## それでも解決しない場合

### デバッグコマンドでの確認

以下の[コマンド](/glossary/コマンド/)を実行してターゲットホストの情報を確認します。

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

実行時に[環境変数](/glossary/環境変数/)でログレベルを上げて実行します。

```bash
export ANSIBLE_DEBUG=true
export ANSIBLE_LOG_PATH=/tmp/ansible.log
ansible-playbook playbook.yml
```

出力された[ログファイル](/glossary/ログファイル/) `/tmp/ansible.log` を確認することで、より詳細な[エラーメッセージ](/glossary/エラーメッセージ/)が得られます。

### 公式リソースへの参照

Ansible 公式ドキュメント（https://docs.ansible.com/）の該当モジュールセクションを確認してください。特に `uri` モジュール、`copy` モジュール、`stat` モジュールのドキュメントには、各パラメーターの詳細とよくある落とし穴が記載されています。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*