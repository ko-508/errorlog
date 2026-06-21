---
title: "Ansible の 401 エラー：原因と解決策"
date: 2026-06-11
description: "ターゲットホストまたは外部サービスへの認証に失敗した。Ansible 401 エラーの原因と解決策を解説します。"
tags: ["Ansible"]
errorCode: "401"
service: "Ansible"
error_type: "401"
components: []
related_services: []
trend_incident: true
---
## エラーの概要

Ansibleで[認証](/glossary/認証/)[エラー](/glossary/エラー/)が発生する場合、ターゲットホストまたは連携している外部サービスへの[認証](/glossary/認証/)に失敗していることを示します。この[エラー](/glossary/エラー/)は主にSSH接続時の認証失敗、sudo権限昇格時の[パスワード](/glossary/パスワード/)不一致、[API](/glossary/api/)[トークン](/glossary/トークン/)または[クレデンシャル](/glossary/クレデンシャル/)（認証情報）の誤りによって発生し、Playbookの実行が途中で停止する重大な状況です。認証情報の管理ミスやキー設定の誤りが原因となることが大部分です。

## 実際のエラーメッセージ例

**SSH認証失敗時：**

```json
{
  "msg": "Failed to connect to the host via ssh: Permission denied (publickey,password).",
  "unreachable": true,
  "_ansible_no_log": false,
  "failed": true
}
```

**become（sudo）[パスワード](/glossary/パスワード/)誤り時：**

```bash
FAILED! => {
    "changed": false,
    "module_stderr": "sudo: 1 incorrect password attempt\nsudo: a password is required to run sudo\n",
    "module_stdout": "",
    "msg": "MODULE FAILURE\nSee stdout/stderr for the details."
}
```

**[API](/glossary/api/)認証失敗時：**

```json
{
  "status_code": 401,
  "msg": "Unauthorized",
  "body": "Invalid API token or credentials"
}
```

## よくある原因と解決手順

### 原因1：SSH秘密鍵が間違っているか、パスフレーズが設定されている

SSHで使用する秘密鍵がターゲットホストの公開鍵と対応していない場合、またはパスフレーズで保護された鍵をAnsibleが処理できない場合に発生します。Ansibleがホストに接続する際に認証情報を提示できず、Permission deniedで弾かれる状況です。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
# inventory.ini
[webservers]
192.168.1.10 ansible_user=ubuntu

# playbook.yml
---
- name: Deploy application
  hosts: webservers
  tasks:
    - name: Copy file
      copy:
        src: /local/file.txt
        dest: /tmp/file.txt
```

```bash
# SSH秘密鍵がホームディレクトリのデフォルト場所にない場合
# または鍵がパスフレーズで保護されている場合、接続失敗
ansible-playbook -i inventory.ini playbook.yml
```

**After（修正後）：**

```yaml
# inventory.ini
[webservers]
192.168.1.10 ansible_user=ubuntu ansible_ssh_private_key_file=~/.ssh/id_rsa

# playbook.yml
---
- name: Deploy application
  hosts: webservers
  tasks:
    - name: Copy file
      copy:
        src: /local/file.txt
        dest: /tmp/file.txt
```

```bash
# 方法1：秘密鍵をSSHエージェントに追加（パスフレーズ入力は1回のみ）
ssh-add ~/.ssh/id_rsa
ansible-playbook -i inventory.ini playbook.yml

# 方法2：ansible.cfgで秘密鍵を明示的に指定
# ansible.cfg
[defaults]
private_key_file = ~/.ssh/id_rsa
```

### 原因2：become（sudo）のパスワードが間違っているか、未設定

ターゲットホストで[管理者権限](/glossary/管理者権限/)が必要なタスク（パッケージインストール、ファイル編集など）を実行する際に、`become: yes`の設定だけではbecome_passwordが未設定のため、sudoの[認証](/glossary/認証/)に失敗します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
# playbook.yml
---
- name: Install packages
  hosts: webservers
  become: yes
  tasks:
    - name: Install nginx
      apt:
        name: nginx
        state: present
```

```bash
# パスワードを指定せずに実行
ansible-playbook -i inventory.ini playbook.yml
# エラー: sudo: a password is required to run sudo
```

**After（修正後）：**

```yaml
# playbook.yml
---
- name: Install packages
  hosts: webservers
  become: yes
  vars_prompt:
    - name: ansible_become_password
      prompt: "Enter sudo password"
      private: yes
  tasks:
    - name: Install nginx
      apt:
        name: nginx
        state: present
```

```bash
# -K オプションで対話的にbecome_passwordを入力
ansible-playbook -i inventory.ini playbook.yml -K

# または ansible.cfg に設定
# [privilege_escalation]
# become_ask_pass = True
```

### 原因3：外部APIにアクセスするモジュールの認証情報が間違っている

`uri`、`ansible.posix.synchronize`、クラウドプロバイダー連携モジュール（aws_s3、azure_vm等）などで使用する[API](/glossary/api/)[トークン](/glossary/トークン/)、アクセスキー、[パスワード](/glossary/パスワード/)が誤っている場合、外部サービスが401 Unauthorizedで応答し、モジュールが失敗します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
# playbook.yml
---
- name: Access API endpoint
  hosts: localhost
  tasks:
    - name: Fetch data from API
      uri:
        url: https://api.example.com/v1/data
        method: GET
        headers:
          Authorization: "Bearer <incorrect-api-token>"
        status_code: 200
      register: api_response
    
    - name: Upload to AWS S3
      amazon.aws.s3:
        bucket: my-bucket
        object: myfile.txt
        src: /tmp/myfile.txt
        mode: put
        aws_access_key: "<your-access-key-id>"
        aws_secret_key: "<your-secret-access-key>"
```

**After（修正後）：**

```yaml
# playbook.yml（機密情報をvaultで保護）
---
- name: Access API endpoint
  hosts: localhost
  vars_files:
    - vault_secrets.yml
  tasks:
    - name: Fetch data from API
      uri:
        url: https://api.example.com/v1/data
        method: GET
        headers:
          Authorization: "Bearer {{ api_token }}"
        status_code: 200
      register: api_response
    
    - name: Upload to AWS S3
      amazon.aws.s3:
        bucket: my-bucket
        object: myfile.txt
        src: /tmp/myfile.txt
        mode: put
        aws_access_key: "{{ aws_access_key_id }}"
        aws_secret_key: "{{ aws_secret_access_key }}"

# vault_secrets.yml（暗号化）
# api_token: "your-valid-api-token"
# aws_access_key_id: "<your-access-key-id>"
# aws_secret_access_key: "<your-secret-access-key>"
```

```bash
# 機密情報をvaultで管理
ansible-vault create vault_secrets.yml
# エディタで正しい認証情報を入力して保存

# Playbookを実行（vaultパスワードをプロンプトで入力）
ansible-playbook playbook.yml --ask-vault-pass

# または vault パスフレーズをファイルで指定
ansible-playbook playbook.yml --vault-password-file ~/.vault_pass
```

## ツール固有の注意点

**SSHエージェント設定の確認：**
パスフレーズ保護された秘密鍵を使用する場合、SSHエージェントが起動していることを確認してください。Linuxで`eval $(ssh-agent -s)`を実行後、`ssh-add`で鍵を登録することで、Ansibleの実行時にパスフレーズ入力が不要になります。

**become_methodの指定：**
デフォルトではsudoが使用されますが、環境によって異なる場合があります。`become_method: su`や`become_method: doas`など、ターゲットホスト環境に応じた設定をinventoryで指定してください。

**複数ホストへの並列実行時：**
`-f`オプションで並列数を制限している場合、複数ホストの[認証](/glossary/認証/)が同時に行われるため、ホスト単位で認証情報が異なるケースでは単一実行で検証してから並列実行に移行することが推奨されます。

**[API](/glossary/api/)[トークン](/glossary/トークン/)の有効期限：**
外部[API](/glossary/api/)の[トークン](/glossary/トークン/)は有効期限切れになることがあります。定期的に新規[トークン](/glossary/トークン/)を取得し、vaultで更新する運用フローを構築してください。

## それでも解決しない場合

**詳細な[ログ](/glossary/ログ/)出力で[デバッグ](/glossary/デバッグ/)：**

```bash
# -vvv オプションで詳細ログを出力
ansible-playbook -i inventory.ini playbook.yml -vvv

# SSH接続の詳細を確認
ssh -vvv -i ~/.ssh/id_rsa ubuntu@192.168.1.10
```

**Ansible[設定ファイル](/glossary/設定ファイル/)で認証設定を確認：**

```bash
# 現在のAnsible設定を表示
ansible-config dump | grep -i ssh
ansible-config dump | grep -i become

# ansible.cfg の例
cat ~/.ansible.ansible.cfg
cat /etc/ansible/ansible.cfg
```

**ターゲットホストの認証関連[ログ](/glossary/ログ/)を確認：**

```bash
# リモートホストのSSH認証ログ確認
ssh ubuntu@192.168.1.10 'tail -50 /var/log/auth.log | grep -i "failed\|accepted"'

# sudo実行ログ確認
ssh ubuntu@192.168.1.10 'sudo journalctl -u sudo -n 20'
```

**公式ドキュメント・サポート参照：**
- Ansible User Guide：https://docs.ansible.com/ansible/latest/user_guide/index.html
- Privilege Escalation：https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_privilege_escalation.html
- Vault：https://docs.ansible.com/ansible/latest/user_guide/vault.html

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*