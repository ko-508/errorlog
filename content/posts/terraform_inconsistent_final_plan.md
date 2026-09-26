---
title: "final plan不整合の原因と対処法"
date: 2026-09-26
draft: false
description: "TerraformのProvider produced inconsistent final planは、apply中に確定した値を反映した結果、providerが当初のplanと両立しない計画を返したときに発生します。確認すべき属性、providerの更新・切り戻し、stateの扱いを解説します。"
tags: ["Terraform"]
images: ["og/posts/terraform_inconsistent_final_plan.png"]
errorCode: "Provider produced inconsistent final plan"
urgency: "high"
service: "Terraform"
error_type: "inconsistent_final_plan"
components: ["Terraform Core", "Provider", "State"]
related_services: []
trend_incident: false
---

## 冒頭まとめ

`terraform plan`は成功したのに、`terraform apply`の途中で次のエラーが出ることがあります。

```text
Error: Provider produced inconsistent final plan

When expanding the plan for aws_example.main to include new values
learned so far during apply, provider "registry.terraform.io/hashicorp/aws"
produced an invalid new value for .id: was known, but now unknown.

This is a bug in the provider, which should be reported in the provider's
own issue tracker.
```

このエラーは、apply中に新しく確定した値を使って計画を更新したところ、providerが最初のplanと両立しない結果を返したことを示します。エラー本文にもあるとおり、基本的にはprovider側の不整合として扱います。

ただし、エラーに表示されたリソースが不具合の発生元とは限りません。そのリソースが参照している上流リソースの値がapply中に変わり、下流で不整合として検出される場合があります。

失敗後は同じapplyをすぐに繰り返さず、次の順番で確認してください。

```bash
terraform version
terraform providers
terraform plan
```

applyの途中まで変更が反映されている可能性があります。取り直したplanを確認したうえで、providerの既知の不具合、直前のバージョン変更、外部からのインフラ変更を調べます。

## Provider produced inconsistent final planとは

Terraformのplanには、作成時にAPIから発行されるIDやIPアドレスなど、applyするまで確定しない値が含まれることがあります。planでは、このような値が`(known after apply)`と表示されます。

applyが進んで値が確定すると、Terraformはその値を参照する後続リソースの計画を具体化します。この処理でproviderが最初の計画と矛盾する値や操作を返すと、安全にapplyを続行できないため処理が停止します。

HashiCorpのprovider向け資料では、次のように下流リソースでエラーが表面化する例が示されています。

```text
When expanding the plan for null_resource.downstream to include new values
learned so far during apply, provider "null" produced an invalid new value for
.triggers["from_other"]: was cty.StringVal("a"), but now cty.StringVal("b").
```

この例では、`null_resource.downstream`へ渡された上流の値がplan時の`a`からapply時の`b`へ変わっています。Terraformは計画にない変更を黙って受け入れず、providerの不整合として停止します。詳しい説明は[Terraform 0.12 Compatibility for Providers](https://developer.hashicorp.com/terraform/plugin/sdkv2/guides/terraform-0.12-compatibility)で確認できます。

## エラー本文の読み分け方

見出しだけでなく、`produced an invalid new value for`または`changed the planned action`に続く部分を確認します。

| 表示 | 意味 |
|---|---|
| `was absent, but now present` | planになかった値がapply時に現れた |
| `was present, but now absent` | planにあった値がapply時に消えた |
| `was known, but now unknown` | 確定していた値が未確定へ戻った |
| `was <値A>, but now <値B>` | plan時とapply時で具体的な値が変わった |
| `changed the planned action from ... to ...` | 更新、作成、削除、再作成などの操作が変わった |

たとえば、`was known, but now unknown`ならproviderが確定済みとしていた属性を、apply中の再計算で未確定へ戻しています。`changed the planned action from Update to DeleteThenCreate`なら、当初は更新予定だったリソースを再作成へ変更しています。

エラー本文にはproviderの完全なアドレスも表示されます。

```text
provider "registry.terraform.io/hashicorp/aws"
```

まず、このprovider名、問題になった属性、リソースアドレスを記録します。そのうえでproviderの課題管理ページを検索してください。実際にAWS providerでも、apply中に操作が`Update`から`DeleteThenCreate`へ変わり、複数の属性が`known`から`unknown`へ戻った報告があります。

なお、見出しが次のように`Terraform produced`で始まる場合は別です。

```text
Error: Terraform produced inconsistent final plan
```

こちらはproviderではなくTerraform Coreが計画を矛盾させたと判断したエラーです。報告先もproviderのリポジトリではなく、[hashicorp/terraform](https://github.com/hashicorp/terraform/issues)になります。主語を読み飛ばさないでください。

## 原因1：providerの不具合やバージョン変更

最初に疑うのは、エラー本文に表示されたproviderです。providerがComputed属性の変化を正しく予測できない場合や、apply中の再計算で属性の有無、値、操作を変えた場合に発生します。

使用中のproviderと依存関係を確認します。

```bash
terraform version
terraform providers
```

選択されている正確なバージョンは`.terraform.lock.hcl`でも確認できます。

```bash
git diff -- .terraform.lock.hcl
```

providerの更新直後から発生した場合は、そのバージョンのリリースノートとissueを確認します。修正版が公開されていれば、version constraintsの範囲を確認してから更新します。

```bash
terraform init -upgrade
terraform plan
```

`terraform init -upgrade`は、制約を満たす新しいproviderを選び直してロックファイルを更新します。すべての環境で同じ更新結果になるよう、変更された`.terraform.lock.hcl`をレビューし、意図した内容だけをバージョン管理へ含めてください。依存関係の選択方法は[Dependency Lock File](https://developer.hashicorp.com/terraform/language/files/dependency-lock)で説明されています。

新しいproviderで問題が発生し、以前のバージョンでは再現しないことを確認できた場合は、version constraintsを以前の正常な版へ戻し、`terraform init`で選択し直す方法もあります。ロックファイルを手作業で書き換えるのではなく、設定した制約に基づいてTerraformに更新させます。

## 原因2：上流リソースの値がapply中に変わった

エラーに表示されたリソースは、不整合を検出した場所であり、値を変えた場所とは限りません。

たとえば、リソースAのIPアドレスをリソースBの引数や`null_resource`の`triggers`へ渡している場合、Aの値がapply中に変わるとBの最終計画も変化します。このとき、Aを扱うproviderが変化を正しく計画できなかった問題が、Bのエラーとして表示されることがあります。

対象リソースが参照している式を確認してください。

```hcl
resource "null_resource" "configure" {
  triggers = {
    server_ip = example_server.main.public_ip
  }
}
```

この設定だけを見て、`null_resource`が原因だと決めつけることはできません。`example_server.main.public_ip`がplan時にどのように表現され、apply中にどう変わったか、上流のproviderも含めて調べます。

`depends_on`を追加しても、値の不整合そのものは修正できません。実行順序が原因ではなく、plan時の予測とapply時の値が両立していないためです。参照を外して定数へ置き換える方法も、必要な依存関係を失う可能性があります。providerの修正版や、そのリソースに固有の回避策を優先してください。

## stateと再実行を確認する

applyがエラーで終了しても、それ以前に処理されたリソースまで元に戻るとは限りません。まず通常のplanを取り直し、現在のstateと実際のインフラをTerraformに再確認させます。

```bash
terraform plan
```

ここで新しい差分が出たら、エラー前のplanと比較します。CIで保存済みplanを使っている場合は、失敗したplanファイルをそのまま再利用せず、新しいplanを作成してレビューしてください。

手動操作や別の自動化によってインフラが変更され、意図した外部変更をstateへ取り込みたい場合は、最初にrefresh-onlyのplanを確認します。

```bash
terraform plan -refresh-only
```

表示されたstateの変更が正しい場合に限り、適用します。

```bash
terraform apply -refresh-only
```

refresh-onlyは実際のインフラを変更せず、Terraformのstateを外部の状態へ合わせるモードです。providerの計画不整合を自動的に修復するコマンドではありません。認証情報やprovider設定を間違えた状態で適用すると、存在するリソースがstateから消えるような変更を記録する危険があります。HashiCorpも、適用前に変更内容を確認する方法を推奨しています。詳しくは[refreshコマンドの公式文書](https://developer.hashicorp.com/terraform/cli/commands/refresh)を参照してください。

### issueを確認・報告するときの情報

エラー本文が`Provider produced`なら、まず該当providerのissueを検索します。同じリソース名と属性名、providerのバージョンを組み合わせると、既知の不具合や回避策を見つけやすくなります。

報告時には、少なくとも次の情報を揃えます。

- Terraform Coreのバージョン
- providerの名前とバージョン
- エラー全文と問題になった属性
- 最小化したTerraform設定
- 最初のplanで予定されていた操作
- 再現手順と、直前に変更したproviderや設定

認証情報、アカウントID、IPアドレス、リソース名などが含まれる場合は、公開前に伏せてください。デバッグログには機密情報が含まれる可能性があるため、そのままissueへ貼り付けないでください。

同じエラーでも、providerやリソースごとに原因は異なります。別providerのissueにある回避策を、そのまま現在の構成へ適用しないようにします。

## 似たエラーとの違い

`Provider produced invalid plan`は、providerが最初のplan作成時に無効な計画を返した場合のエラーです。今回の`inconsistent final plan`は、apply中に未確定値が確定し、計画を更新した段階で矛盾が見つかっています。

`Provider produced inconsistent result after apply`は、リソースを実際に変更した後、providerが報告した最終状態と計画が一致しない場合に出ます。どちらもproviderの不具合として扱われますが、検出される段階が異なります。

`Terraform produced inconsistent final plan`は、Terraform Core側の問題です。エラーの主語が`Provider`か`Terraform`かで、調査対象と報告先が変わります。

`Inconsistent dependency lock file`は、保存済みplanと現在の`.terraform.lock.hcl`でproviderの選択が一致しない場合などに出る別のエラーです。今回のようにapply中の値や操作が変化したことを示すものではありません。

## 解決手順のまとめ

`Provider produced inconsistent final plan`が出たら、エラー本文からprovider名、リソースアドレス、属性名、値または操作の変化を確認します。`Terraform produced`の場合はTerraform Core側の問題なので、主語も必ず確認してください。

次に、`terraform providers`と`.terraform.lock.hcl`でproviderのバージョンを特定し、該当providerのissueとリリースノートを調べます。更新直後なら正常だった版への切り戻し、修正版があるなら検証後の更新を検討します。

エラーに表示されたリソースだけでなく、そのリソースが参照している上流の値も確認してください。下流リソースで不整合が検出されても、原因は上流のproviderにある場合があります。

失敗後は通常のplanを取り直し、一部だけ適用されていないかを確認します。refresh-onlyは外部変更をstateへ受け入れる場合だけ、planを確認してから使用してください。providerの不具合を直す一般的な再試行手段ではありません。

免責事項：本記事の内容は一般的なTerraform環境を前提としています。providerの更新・切り戻しやstateの変更を行う前に、plan、バックアップ、ロックファイルの差分、実際のインフラへの影響を確認してください。
