---
draft: true
title: "Ansible の 500 エラー：原因と解決策"
date: 2026-06-11
description: "ターゲットサーバーの内部エラーが発生した"
tags: ["Ansible"]
errorCode: "500"
service: "Ansible"
error_type: "500"
components: []
related_services: []
trend_incident: true
---
## エラーの概要

Ansibleの500[エラー](/glossary/エラー/)は、ターゲットサーバー上で実行された[コマンド](/glossary/コマンド/)やモジュールが内部[エラー](/glossary/エラー/)で終了したことを示します。この[エラー](/glossary/エラー/)が発生するとPlaybookの実行が中断され、該当タスク以降の処理が実行されなくなります。Playbook内のshellやcommandタスク、またはPythonモジュールの実行中にターゲットホスト側で予期しない障害が発生した場合に出現します。

## 実際のエラーメッセージ例

```json
{
  "msg": "non-zero return code",
  "rc": 500,
  "stderr": "command not found",
  "stdout": "",
  "changed": false
}
```

```bash
FAILED - RETRYING: Install package (1 of 3): FAILED! => {
  "changed": false,
  "cmd": "apt-get install nginx",
  "msg": "non-zero return code",
  "rc": 500,
  "stderr": "E: Could not open lock file /var/lib/apt/lists/lock - open (13: Permission denied)",
  "stdout": ""
}
```

## よくある原因と解決手順

### 原因1：ターゲットホスト上で実行コマンドが見つからない、または権限がない

実行しようとした[コマンド](/glossary/コマンド/)がターゲットホストに存在しない、あるいは実行ユーザーに実行権限がない場合、[コマンド](/glossary/コマンド/)はゼロ以外の終了コード（通常は127や126）を返し、500[エラー](/glossary/エラー/)となります。パッケージ管理ツール（apt、yum等）へのアクセス権限不足も同様です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
- name: Install nginx
  shell: apt-get install nginx -y
  become: no
```

**After（修正後）：**

```yaml
- name: Install nginx
  apt:
    name: nginx
    state: present
  become: yes
  become_user: root
```

### 原因2：shellまたはcommandタスクがゼロ以外の終了コードを返した

shellやcommandモジュールで実行された[コマンド](/glossary/コマンド/)が失敗した（終了コード0以外）場合、Ansibleはデフォルトでそれを失敗と判定します。[コマンド](/glossary/コマンド/)自体の失敗ロジックとAnsibleの失敗判定が一致していない場合、意図しない500[エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
- name: Check if service is running
  shell: systemctl status nginx
  register: service_status
```

**After（修正後）：**

```yaml
- name: Check if service is running
  shell: systemctl status nginx
  register: service_status
  ignore_errors: yes
  
- name: Display service status
  debug:
    msg: "Service status: {{ service_status.rc }}"
```

### 原因3：ターゲットホスト上でPythonモジュール実行時にエラーが発生した

Ansibleが使用するPythonモジュール（apt_repository、yum等）の実行時に、ターゲットホスト側のPython環境の問題や依存パッケージの欠落が原因で500[エラー](/glossary/エラー/)が発生することがあります。特にカスタムモジュールやサードパーティモジュールで顕著です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
- name: Add repository
  apt_repository:
    repo: ppa:nginx/stable
    state: present
```

**After（修正後）：**

```yaml
- name: Install required packages
  apt:
    name:
      - software-properties-common
      - python3-distutils
    state: present
  when: ansible_os_family == "Debian"

- name: Add repository
  apt_repository:
    repo: ppa:nginx/stable
    state: present
```

### 原因4：変数展開時のエラーや環境変数の不正

Playbook内で存在しない[変数](/glossary/変数/)を参照したり、[シェル](/glossary/シェル/)の[環境変数](/glossary/環境変数/)が正しく設定されていない場合、実行時に[エラー](/glossary/エラー/)が発生し500コードで返されます。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
- name: Copy configuration file
  shell: cp {{ config_path }}/nginx.conf /etc/nginx/
```

**After（修正後）：**

```yaml
- name: Copy configuration file
  shell: cp {{ config_path }}/nginx.conf /etc/nginx/
  vars:
    config_path: /opt/config
  environment:
    PATH: "{{ ansible_env.PATH }}"
```

## ツール固有の注意点

Ansibleの500[エラー](/glossary/エラー/)は返却元がターゲットホスト側であるため、コントローラーノード（Ansibleを実行するマシン）ではなくターゲットホスト側の[ログ](/glossary/ログ/)を確認する必要があります。Playbookに`become: yes`を指定している場合、sudo経由で実行されるため、そのプロセスが権限不足で失敗していないか確認してください。また、Windowsターゲットを使用している場合、PowerShellモジュールの終了コード解釈がUnixとは異なるため、`failed_when`を明示的に指定することが重要です。

```yaml
- name: Windows command execution
  win_shell: Get-Service nginx
  failed_when: 
    - win_shell.rc != 0
    - "'Access denied'" not in win_shell.stderr
```

## それでも解決しない場合

まず、Playbookを実行する際に`-vvv`フラグで詳細な[デバッグ](/glossary/デバッグ/)出力を有効にしてください。

```bash
ansible-playbook playbook.yml -vvv
```

この出力にはターゲットホストで実行された[コマンド](/glossary/コマンド/)、その標準出力、標準[エラー](/glossary/エラー/)が含まれます。ターゲットホストに直接SSHで[ログイン](/glossary/ログイン/)して、同じ[コマンド](/glossary/コマンド/)を手動で実行し、[エラー](/glossary/エラー/)が再現するか確認してください。特に権限関連の[エラー](/glossary/エラー/)の場合、`sudo -l`で実行可能な[コマンド](/glossary/コマンド/)を確認できます。

```bash
ssh <target-host>
sudo -l
# 実行したいコマンドを直接実行してエラーを確認
sudo apt-get install nginx -y
```

ターゲットホストのシステムログを確認してください。

```bash
# Linux（systemd使用）
sudo journalctl -xe

# 旧式Linuxまたは汎用ログ
tail -100 /var/log/syslog
tail -100 /var/log/messages
```

Ansibleの公式ドキュメント（https://docs.ansible.com/ansible/latest/user_guide/intro_inventory.html）でインベントリ設定を見直し、ターゲットホストの接続情報（ホスト名、ポート、ユーザー、秘密鍵等）が正確か確認してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*