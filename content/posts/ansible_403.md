---
title: "Ansible の 403 エラー：原因と解決策"
date: 2026-06-11
description: "ターゲットシステムへのアクセスが拒否された"
tags: ["Ansible"]
errorCode: "403"
service: "Ansible"
error_type: "403"
components: []
related_services: []
trend_incident: true
---
## エラーの概要

Ansibleで403[エラー](/glossary/エラー/)が発生する場合、ターゲットシステムへの[アクセス権限](/glossary/アクセス権限/)が不足していることを意味します。この[エラー](/glossary/エラー/)はSSH接続後、実行対象のタスクやファイル操作時に権限不足を検出した際に表示されます。Ansibleが接続した[ユーザーアカウント](/glossary/ユーザーアカウント/)に必要な[権限](/glossary/権限/)がないため、[コマンド](/glossary/コマンド/)実行やファイル読み書きが拒否される状況です。

## 実際のエラーメッセージ例

```json
{
  "msg": "Aborting, target uses selinux without python selinux bindings",
  "invocation": {
    "module": "file",
    "args": {}
  }
}
```

```bash
fatal: [target_host]: FAILED! => {
    "changed": false,
    "module_stderr": "sudo: command not found",
    "module_stdout": "",
    "msg": "MODULE FAILURE\nSee stdout/messages above for details.",
    "rc": 1
}
```

```bash
FAILED! => {
    "msg": "Permission denied",
    "details": "Could not write to /etc/hosts: Permission denied"
}
```

## よくある原因と解決手順

### 原因1：SSHユーザーにsudo権限が付与されていない

Ansibleで接続した[ユーザーアカウント](/glossary/ユーザーアカウント/)に対して、sudo実行権限そのものが付与されていないケースです。`become: true`を指定してroot[権限](/glossary/権限/)での実行を試みても、sudo[権限](/glossary/権限/)がなければタスクは失敗します。

**修正前（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
- name: Install packages
  hosts: target_servers
  tasks:
    - name: Install Apache
      apt:
        name: apache2
        state: present
      become: true
```

この場合、接続ユーザー（例：ubuntu）がsudo[権限](/glossary/権限/)を持たないと403[エラー](/glossary/エラー/)が発生します。

**修正後：**

```yaml
- name: Install packages
  hosts: target_servers
  tasks:
    - name: Install Apache
      apt:
        name: apache2
        state: present
      become: true
      become_user: root
```

対応するターゲットホスト側の設定：

**修正前（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# /etc/sudoers に ubuntu ユーザーのエントリがない
```

**修正後：**

```bash
# /etc/sudoers または /etc/sudoers.d/ansible
ubuntu ALL=(ALL) NOPASSWD:ALL

# またはより限定的な権限設定
ubuntu ALL=(ALL) NOPASSWD:/bin/apt-get, /bin/systemctl
```

### 原因2：ターゲットホストのsudoersに実行するコマンドが許可されていない

sudoersファイルで特定の[コマンド](/glossary/コマンド/)のみを許可している場合、Ansibleが実行しようとする[コマンド](/glossary/コマンド/)が許可リストに含まれていないと403[エラー](/glossary/エラー/)が発生します。

**修正前（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
- name: Run system command
  hosts: target_servers
  tasks:
    - name: Restart networking
      shell: systemctl restart networking
      become: true
```

対応するターゲットホスト側の制限的な設定：

```bash
# /etc/sudoers.d/ansible - systemctl の特定コマンドのみ許可
ansible ALL=(ALL) NOPASSWD:/bin/systemctl start apache2, /bin/systemctl stop apache2
```

上記の場合、`systemctl restart networking`は許可リストに含まれないため403[エラー](/glossary/エラー/)が発生します。

**修正後：**

```yaml
- name: Run system command
  hosts: target_servers
  tasks:
    - name: Restart networking
      systemd:
        name: networking
        state: restarted
      become: true
```

対応するターゲットホスト側の修正：

```bash
# /etc/sudoers.d/ansible - 必要なコマンドをすべて許可
ansible ALL=(ALL) NOPASSWD:/bin/systemctl restart networking, /bin/systemctl start *, /bin/systemctl stop *, /bin/systemctl restart *
```

### 原因3：ファイルシステムのパーミッションが操作を拒否している

ターゲットホスト上のファイルやディレクトリに対して、接続ユーザーが読み取り・書き込み[権限](/glossary/権限/)を持たないケースです。sudo[権限](/glossary/権限/)があっても、特定のファイル操作が明示的に拒否されることがあります。

**修正前（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
- name: Write configuration file
  hosts: target_servers
  tasks:
    - name: Create app config
      file:
        path: /opt/myapp/config.conf
        state: touch
        mode: '0644'
      become: true
```

ターゲットホスト上で、`/opt/myapp`ディレクトリのパーミッションが不適切：

```bash
# /opt/myapp のパーミッションが 700（オーナーのみアクセス可能）
drwx------ root root /opt/myapp
```

**修正後：**

```yaml
- name: Write configuration file
  hosts: target_servers
  tasks:
    - name: Ensure app directory exists with proper permissions
      file:
        path: /opt/myapp
        state: directory
        mode: '0755'
        owner: root
        group: root
      become: true

    - name: Create app config
      file:
        path: /opt/myapp/config.conf
        state: touch
        mode: '0644'
        owner: root
        group: root
      become: true
```

ターゲットホスト側の修正：

```bash
# ディレクトリパーミッションを適切に設定
chmod 755 /opt/myapp
```

## ツール固有の注意点

Ansibleの403[エラー](/glossary/エラー/)は権限不足を示していますが、実際の原因特定にはいくつかのポイントがあります。

**ターゲットホストでの事前確認**

接続予定のユーザーで以下を実行し、実際のsudo[権限](/glossary/権限/)を確認してください。

```bash
sudo -l
```

この[コマンド](/glossary/コマンド/)の出力から、そのユーザーが実行可能な[コマンド](/glossary/コマンド/)が明記されます。`(ALL) NOPASSWD:ALL`と表示されれば、すべての[コマンド](/glossary/コマンド/)が許可されている状態です。

**Ansibleプレイブックでのbecome設定**

`become`と`become_user`の組み合わせは以下のパターンがあります。

```yaml
# パターン1：sudo で root に昇格（デフォルト）
become: true

# パターン2：特定ユーザーに昇格
become: true
become_user: apache

# パターン3：sudo 以外の昇格方法を指定
become: true
become_method: su
become_user: root

# パターン4：昇格時にパスワード入力が必要
become: true
vars:
  ansible_become_pass: <password>
```

**SELinux環境での注意**

SELinuxが有効な環境では、ファイルアクセス[権限](/glossary/権限/)が追加で制限されます。403[エラー](/glossary/エラー/)が表示される場合、SELinuxコンテキストの確認も必要です。

```bash
getenforce  # SELinuxの有効状態を確認
ls -Z /path/to/file  # ファイルのSELinuxコンテキストを確認
```

## それでも解決しない場合

**詳細な[ログ](/glossary/ログ/)出力での[デバッグ](/glossary/デバッグ/)**

Ansibleをより詳細なログレベルで実行します。

```bash
ansible-playbook playbook.yml -vvv
```

`-vvv`フラグで3段階の詳細出力が有効になり、接続プロセスやモジュール実行の詳細が表示されます。

**ターゲットホストのsyslogを確認**

[権限](/glossary/権限/)[エラー](/glossary/エラー/)の詳細はターゲットホストのsyslogに記録されていることがあります。

```bash
# SSH接続ユーザーで実行
sudo tail -f /var/log/auth.log  # Debian/Ubuntu の場合
sudo tail -f /var/log/secure   # RHEL/CentOS の場合
```

`sudo: <user> : command not allowed`のようなメッセージが表示されていれば、sudoersの設定を再確認してください。

**ターゲットホストでの[コマンド](/glossary/コマンド/)実行[テスト](/glossary/テスト/)**

ローカルでプレイブックの各タスクを手動で実行してみることで、権限問題を特定しやすくなります。

```bash
# Ansibleが接続するユーザーで直接実行
ssh ansible_user@target_host "sudo systemctl restart apache2"
```

**公式ドキュメントとサポート**

Ansibleの権限昇格について、公式ドキュメント（https://docs.ansible.com/ansible/latest/privilege_escalation.html）には詳細な設定方法が記載されています。また、特定の環境やツール（Docker、Kubernetes、クラウドプロバイダー）でのbecome設定パターンも参照できます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*