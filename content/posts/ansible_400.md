---
title: "Ansible の 400 エラー：原因と解決策"
date: "2026-06-10"
description: "AnsibleがターゲットAPIまたはモジュールに送るリクエストの形式が正しくない。Ansible 400 エラーの原因と解決策を解説します。"
tags: ["Ansible"]
errorCode: "400"
lastmod: "2026-06-10"
service: "Ansible"
error_type: "400"
components: []
related_services: []
---

## エラーの概要

Ansible 400[エラー](/glossary/エラー/)は、ターゲットノードの[API](/glossary/api/)またはモジュールに送られる[リクエスト](/glossary/リクエスト/)の形式が正しくないことを示しています。主にPlaybookのタスク定義における[パラメータ](/glossary/パラメータ/)指定の誤り、[YAML](/glossary/yaml/)ファイルの構文[エラー](/glossary/エラー/)、またはモジュールバージョンとの互換性不一致が原因です。この[エラー](/glossary/エラー/)が発生すると、該当タスクが実行されず、Playbook全体の処理が中断される可能性があります。

## 実際のエラーメッセージ例

```json
{
  "msg": "failed to parse: msg: 'error' Failed validating 'type' in schema['properties']['state']: 'invalid' is not one of ['present', 'absent']",
  "failed": true,
  "_ansible_no_log": false
}
```

```bash
fatal: [target_host]: FAILED! => {
  "msg": "Unsupported parameters for module: <module_name> Unsupported parameters:\n<parameter_name>\n"
}
```

## よくある原因と解決手順

### 原因1：Playbookのパラメータ指定が誤っている

モジュールに存在しない[パラメータ](/glossary/パラメータ/)を指定したり、[パラメータ](/glossary/パラメータ/)の値が許容範囲外だったりすると、400[エラー](/glossary/エラー/)が発生します。特にモジュール固有の[パラメータ](/glossary/パラメータ/)名やその値の形式（文字列、リスト、辞書など）を誤るケースが多いです。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
- name: Create user
  ansible.builtin.user:
    name: testuser
    state: created
    shell: /bin/bash
```

**After（修正後）：**

```yaml
- name: Create user
  ansible.builtin.user:
    name: testuser
    state: present
    shell: /bin/bash
```

上記の例では、`state`[パラメータ](/glossary/パラメータ/)に許容されていない値`created`を指定していました。正しい値は`present`または`absent`です。

### 原因2：YAMLファイルのインデント構造が正しくない

Playbookはインデント（スペース）を厳密に要求する[YAML](/glossary/yaml/)形式です。タブ文字の混在やスペース数の誤りがあると、[パラメータ](/glossary/パラメータ/)の解析に失敗し400[エラー](/glossary/エラー/)が発生します。特にネストされた[パラメータ](/glossary/パラメータ/)で問題が起きやすいです。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
- name: Install package
  ansible.builtin.apt:
    name: nginx
     update_cache: yes
    state: present
```

**After（修正後）：**

```yaml
- name: Install package
  ansible.builtin.apt:
    name: nginx
    update_cache: yes
    state: present
```

`update_cache`のインデントが誤っており、[パラメータ](/glossary/パラメータ/)として正しく認識されていません。各[パラメータ](/glossary/パラメータ/)は同じインデントレベルで記述する必要があります。

### 原因3：モジュールのバージョンとパラメータの互換性がない

Ansibleのバージョンアップによってモジュールの[パラメータ](/glossary/パラメータ/)が追加・変更・削除されることがあります。古いPlaybookを新しいAnsibleで実行したり、その逆をしたりすると、存在しない[パラメータ](/glossary/パラメータ/)の指定となり400[エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```yaml
- name: Manage firewall rule
  ansible.builtin.firewalld:
    service: http
    permanent: true
    offline: yes
    state: enabled
```

**After（修正後）：**

```yaml
- name: Manage firewall rule
  ansible.builtin.firewalld:
    service: http
    permanent: true
    state: enabled
```

`offline`[パラメータ](/glossary/パラメータ/)が古いバージョンのモジュール仕様であり、新しいAnsibleでは削除された可能性があります。最新のモジュール仕様に合わせて[パラメータ](/glossary/パラメータ/)を修正しました。

## ツール固有の注意点

Ansibleの400[エラー](/glossary/エラー/)は複合的な要因が絡むため、段階的な確認が重要です。まず構文レベルでの[エラー](/glossary/エラー/)を検出し、次に意味レベルでの[パラメータ](/glossary/パラメータ/)検証を行います。

`ansible-playbook --syntax-check`[コマンド](/glossary/コマンド/)は基本的な[YAML](/glossary/yaml/)構文[エラー](/glossary/エラー/)を検出しますが、[パラメータ](/glossary/パラメータ/)の有効性までは検証しません。そのため、構文チェックをパスしても400[エラー](/glossary/エラー/)が実行時に発生することがあります。

また、`ansible-doc`[コマンド](/glossary/コマンド/)でモジュールのドキュメントを参照する際は、現在のAnsibleバージョンに対応するドキュメントが表示される点に注意してください。異なるバージョン間で[パラメータ](/glossary/パラメータ/)が変わっている場合は、対象ノードのAnsibleバージョンと合わせる必要があります。

リモートノードとコントロールノード（Playbook実行マシン）のAnsibleバージョンが異なる場合、モジュールの互換性問題が発生しやすいです。特に`ansible.builtin`以外のコレクションモジュール（`community.*`や`ansible.windows`など）を使用する場合は、インストール済みコレクションのバージョンもPlaybookの[パラメータ](/glossary/パラメータ/)指定に影響します。

## それでも解決しない場合

**1. 構文チェックを実行する：**

```bash
ansible-playbook site.yml --syntax-check
```

この[コマンド](/glossary/コマンド/)で[YAML](/glossary/yaml/)の基本的な構文[エラー](/glossary/エラー/)を検出できます。

**2. モジュールドキュメントを確認する：**

```bash
ansible-doc ansible.builtin.user
```

モジュール名を指定して、対応する[パラメータ](/glossary/パラメータ/)一覧と説明を表示します。

**3. Ansibleバージョンを確認する：**

```bash
ansible --version
pip show ansible
```

現在インストール済みのAnsibleバージョンと、インストール済みコレクションを確認します。

**4. ターゲットノードで詳細な[エラー](/glossary/エラー/)情報を得る：**

```bash
ansible-playbook site.yml -vvv
```

`-vvv`オプションで最大レベルの詳細出力を表示し、[エラーメッセージ](/glossary/エラーメッセージ/)から具体的な問題箇所を特定します。

**5. 公式リソースを参照する：**

Ansibleの公式ドキュメント（https://docs.ansible.com/）でモジュール仕様を確認し、お使いのAnsibleバージョンに対応したパラメータを確認してください。特にモジュールの`DEPRECATED`セクションを確認し、非推奨になったパラメータがないか確認します。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
