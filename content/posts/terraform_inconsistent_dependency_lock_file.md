---
title: "Terraformロックファイル：原因と解決策"
date: 2026-08-05T00:00:00+09:00
description: "Inconsistent dependency lock file は、設定が要求するプロバイダーと、.terraform.lock.hcl に記録された選択が一致しないエラーです。版の不一致は init -upgrade、実行環境ごとの検査値不足は providers lock -platform と分けて直します。"
tags: ["Terraform"]
images: ["og/posts/terraform_inconsistent_dependency_lock_file.png"]
errorCode: "Inconsistent dependency lock file"
lastmod: 2026-08-05T00:00:00+09:00
service: "Terraform"
error_type: "Inconsistent dependency lock file"
components: ["Terraform CLI", "Dependency Lock File", "Provider"]
related_services: ["Terraform Registry", "CI/CD", "HCP Terraform"]
trend_incident: false
---

## 冒頭まとめ

`Inconsistent dependency lock file` は、現在のTerraform設定が必要とするプロバイダーと、`.terraform.lock.hcl` に記録された選択が一致しないときに出ます。

```text
Error: Inconsistent dependency lock file

The following dependency selections recorded in the lock file are
inconsistent with the current configuration:
  - provider registry.terraform.io/hashicorp/aws:
    locked version selection 5.100.0 doesn't match the updated
    version constraints "~> 6.0"

To update the locked dependency selections to match a changed
configuration, run:
  terraform init -upgrade
```

この場合は、`required_providers` や子モジュールの変更に対して、ロックファイルが古いままです。設定変更を行った作業環境で次を実行し、差分を確認して `.terraform.lock.hcl` も一緒に版管理へ入れます。

```bash
terraform init -upgrade
git diff -- .terraform.lock.hcl
```

ただし、CIで発生するロックファイル関連の失敗が、すべて `init -upgrade` で直るわけではありません。[開発環境](/glossary/開発環境/)とCIの[OS](/glossary/os/)やCPUが違い、対象環境の検査値がロックファイルにない場合は、次のような別の[エラー](/glossary/エラー/)になります。

```text
Error: Failed to install provider

the current package for registry.terraform.io/hashicorp/aws 6.8.0
doesn't match any of the checksums previously recorded in the
dependency lock file
```

この場合は、選択する版ではなく、配布物を検査するための値が不足しています。CIが `linux_amd64`、開発機がApple SiliconのmacOSなら、両方を明示してロックファイルを更新します。

```bash
terraform providers lock \
  -platform=darwin_arm64 \
  -platform=linux_amd64
```

[Terraform公式のロックファイル資料](https://developer.hashicorp.com/terraform/language/files/dependency-lock)によれば、`.terraform.lock.hcl` は構成全体で共有し、版管理へ含める[ファイル](/glossary/ファイル/)です。対して `.terraform` [ディレクトリ](/glossary/ディレクトリ/)は、作業環境ごとの初期化結果やプロバイダー、子モジュールなどを置く場所であり、版管理へ含めません。

解決の軸は次の2つです。

```text
選択された版が設定条件と合わない
  → terraform init -upgrade

選択済みの版についてCI環境の検査値がない
  → terraform providers lock -platform=<OS_CPU>
```

`.terraform.lock.hcl` を消せば通ることはあります。しかし、それは固定していた版と検査値を捨てて選び直す操作です。原因を確認せず[削除](/glossary/削除/)するのではなく、設定変更と実行環境のどちらが不一致なのかを先に確定します。

## エラーの概要

Terraformの設定には、利用できるプロバイダーの版の範囲を書きます。

```hcl
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
```

一方、`.terraform.lock.hcl` には、実際に選択した版と、配布物を確認するための検査値が記録されます。

```hcl
provider "registry.terraform.io/hashicorp/aws" {
  version     = "6.8.0"
  constraints = "~> 6.0"
  hashes = [
    "h1:...",
    "zh:...",
  ]
}
```

[公式資料](https://developer.hashicorp.com/terraform/language/files/dependency-lock#dependency-installation-behavior)では、設定中の版の条件は「利用できる範囲」、ロックファイルの `version` は「前回選んだ具体的な版」という役割で説明されています。通常の `terraform init` は、ロックファイルに選択済みの版があれば、新しい版が公開されていてもその版を再利用します。

`terraform init -upgrade` を付けると、既存の選択をいったん無視し、設定された条件を満たす新しい版を改めて探します。したがって、これは単なる再初期化ではありません。条件内に新しい版があれば、プロバイダーや子モジュールが更新されます。

ロックファイルが現在の設定と一致しない場合、主に次の2種類の文が出ます。

```text
required by this configuration but no version is selected
```

現在の設定には必要なプロバイダーがあるのに、ロックファイルに選択がありません。新しいプロバイダーまたは、それを必要とする子モジュールを追加した後に、更新済みのロックファイルを登録していない場合が代表です。

```text
locked version selection 5.100.0 doesn't match the updated
version constraints "~> 6.0"
```

ロックファイルが選んでいる版を、現在の版の条件が許可していません。`required_providers` または子モジュールの条件が変わったのに、古いロックファイルが残っています。

なお、ロックファイルが現在追跡するのはプロバイダーだけです。遠隔の場所から取得する子モジュールの選択版は記録しません。ただし、子モジュールが要求するプロバイダー条件は全体の選択に影響するため、モジュール更新をきっかけにこの[エラー](/glossary/エラー/)が発生することがあります。

## まず最初に：エラー本文を4種類に分ける

第一に、`no version is selected` かを確認します。

```text
provider registry.terraform.io/hashicorp/random:
required by this configuration but no version is selected
```

この場合、現在の設定が必要とするプロバイダーにロックファイルの項目がありません。CIで `plan` の前に `init` を実行しているか、開発側で更新した `.terraform.lock.hcl` を登録したかを確認します。

第二に、`doesn't match the updated version constraints` かを確認します。

```text
locked version selection 5.100.0 doesn't match the updated
version constraints "~> 6.0"
```

この場合は版の選択が古いため、設定変更を行った側で `terraform init -upgrade` を実行します。CIだけで毎回 `-upgrade` するのではなく、生成されたロックファイルを差分として確認し、設定変更と同じ変更へ含めます。

第三に、`doesn't match any of the checksums` かを確認します。

```text
the current package ... doesn't match any of the checksums
previously recorded in the dependency lock file
```

これは見出しが `Failed to install provider` になることが多く、`Inconsistent dependency lock file` とは別の検査です。版は一致していても、現在の[OS](/glossary/os/)とCPU向けの配布物を確認できません。対象環境を列挙した `terraform providers lock -platform` を使います。

最後に、[保存](/glossary/保存/)したplan[ファイル](/glossary/ファイル/)を適用しているかを確認します。

```text
The given plan file was created with a different set of external
dependency selections than the current configuration.
```

この場合は、古いplanを新しい設定やロックファイルで適用しようとしています。`init -upgrade` で古いplanを直すことはできません。更新後の同じ設定と依存関係でplanを作り直します。

## よくある原因と解決手順

### 原因1：required_providersを変更したが、ロックファイルを更新していない

代表的な原因です。

**Before（ロックファイルは5系、設定だけ6系へ変更）：**

```hcl
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
```

```hcl
provider "registry.terraform.io/hashicorp/aws" {
  version     = "5.100.0"
  constraints = "~> 5.0"
}
```

設定された `~> 6.0` は、選択済みの `5.100.0` を許可しません。設定変更を行った作業環境で次を実行します。

```bash
terraform init -upgrade
terraform providers
git diff -- .terraform.lock.hcl
```

更新後は、選択された版が意図した範囲にあるかを確認します。

**After（設定と選択済みの版が一致）：**

```hcl
provider "registry.terraform.io/hashicorp/aws" {
  version     = "6.8.0"
  constraints = "~> 6.0"
  hashes = [
    "h1:...",
    "zh:...",
  ]
}
```

`-upgrade` は、変更した1つだけでなく、条件を満たす範囲でほかのプロバイダーや取得済みモジュールも更新し得ます。[`terraform init` の公式資料](https://developer.hashicorp.com/terraform/cli/commands/init#plugin-installation)にも、既存の選択を無視し、設定条件を満たす新しい版を選ぶと記載されています。差分を見ずに更新結果を登録しないでください。

### 原因2：新しいプロバイダーまたは子モジュールを追加した

新しいプロバイダーを追加すると、現在の設定には必要でも、古いロックファイルには選択がありません。

```text
provider registry.terraform.io/hashicorp/random:
required by this configuration but no version is selected
```

新規の構成でロックファイル自体がない場合や、新しい項目を追加するだけなら、通常の `terraform init` が初期選択を作成します。

```bash
terraform init
git diff -- .terraform.lock.hcl
```

既存のプロバイダー条件も変更しており、現在の選択では条件を満たせない場合は `-upgrade` が必要です。

```bash
terraform init -upgrade
git diff -- .terraform.lock.hcl
```

直接プロバイダーを追加していなくても、子モジュールの追加や更新によって新しい要求が入ることがあります。どの階層が何を要求しているかは、次で確認します。

```bash
terraform providers
```

[`terraform providers` の公式資料](https://developer.hashicorp.com/terraform/cli/commands/providers)では、この[コマンド](/glossary/コマンド/)は現在の作業[ディレクトリ](/glossary/ディレクトリ/)にある構成を調べ、各プロバイダー要求がどこで検出されたかを示すものと説明されています。

### 原因3：ロックファイルの更新を登録していない

手元では `terraform init -upgrade` が成功しても、`.terraform.lock.hcl` を登録しなければCIには古い選択が届きます。

```bash
git status --short
git diff -- .terraform.lock.hcl
git check-ignore -v .terraform.lock.hcl
```

`.gitignore` がロックファイルを除外している場合は[修正](/glossary/修正/)します。[Terraformの公式スタイルガイド](https://developer.hashicorp.com/terraform/language/style#gitignore)は、`.terraform.lock.hcl` を常に登録し、`.terraform` [ディレクトリ](/glossary/ディレクトリ/)、状態[ファイル](/glossary/ファイル/)、[保存](/glossary/保存/)したplan[ファイル](/glossary/ファイル/)は登録しないよう示しています。

```gitignore
# 登録しない
.terraform/
*.tfstate
*.tfstate.*
*.tfplan

# .terraform.lock.hcl は除外しない
```

CIで自動生成したロックファイルを、その実行の間だけ使う構成にすると、実行ごとに選択が変わる余地が残ります。ロックファイルは開発時に更新し、確認を経て登録し、CIでは変更が必要なら失敗させる方が不意の更新を見つけやすくなります。

```bash
terraform init -input=false -lockfile=readonly
```

`-lockfile=readonly` はロックファイルの変更を抑止し、記録済みの検査値を使って確認します。`-upgrade` とは同時に使えません。CIを更新場所ではなく検証場所にする場合に向いています。

### 原因4：開発環境とCIでOSまたはCPUが違う

典型例は、Apple SiliconのmacOSで作成したロックファイルを、Linux AMD64のCIで使う場合です。

```text
開発機  darwin_arm64
CI      linux_amd64
```

公式の書式は `OS_ARCH` です。代表例は次のとおりです。

```text
linux_amd64     Linux、AMD64またはx86_64
linux_arm64     Linux、ARM64
darwin_amd64    macOS、Intel
darwin_arm64    macOS、Apple Silicon
windows_amd64   Windows、AMD64またはx86_64
```

実際に使う[環境](/glossary/環境/)をすべて指定します。

```bash
terraform providers lock \
  -platform=linux_amd64 \
  -platform=linux_arm64 \
  -platform=darwin_amd64 \
  -platform=darwin_arm64 \
  -platform=windows_amd64
```

WindowsのPowerShellや[コマンドプロンプト](/glossary/コマンドプロンプト/)では、1行で実行できます。

```powershell
terraform providers lock -platform=windows_amd64 -platform=darwin_arm64 -platform=linux_amd64
```

[`terraform providers lock` の公式資料](https://developer.hashicorp.com/terraform/cli/commands/providers/lock#specifying-target-platforms)によれば、この操作は指定した[環境](/glossary/環境/)でプロバイダーが利用できることを確認し、必要な検査値を `.terraform.lock.hcl` へ[保存](/glossary/保存/)します。

ここで重要なのは、**`providers lock` は既存の選択版を新しい版へ上げる[コマンド](/glossary/コマンド/)ではない**ことです。既存の項目があれば、その項目の `version` を使って対象環境の検査値を追加します。版を選び直すのは `terraform init -upgrade` です。

### 原因5：共有キャッシュやミラーから作った検査値が1環境分しかない

通常、公開元の登録場所から署名付きの検査値を取得できれば、Terraformは複数環境の公式配布物を検査できる情報をロックファイルへ記録します。

一方、ファイルシステム上のミラー、[ネットワーク](/glossary/ネットワーク/)上のミラー、または共有プラグインキャッシュだけから初回導入すると、現在の[環境](/glossary/環境/)で使った配布物の検査値しか記録できない場合があります。[公式資料](https://developer.hashicorp.com/terraform/language/files/dependency-lock#checksum-verification)も、代替の導入方法では他環境の検査値を確認できず、別環境で利用できないロックファイルになる可能性を説明しています。

公開元の登録場所へ接続できる[環境](/glossary/環境/)で、対象環境を列挙します。

```bash
terraform providers lock \
  -platform=darwin_arm64 \
  -platform=linux_amd64
```

組織内だけで配布するプロバイダーをミラーから取得する場合は、使用しているミラーを明示します。

```bash
terraform providers lock \
  -fs-mirror=/opt/terraform/providers \
  -platform=linux_amd64 \
  tf.example.com/example/internal
```

```bash
terraform providers lock \
  -net-mirror=https://terraform.example.com/providers/ \
  -platform=linux_amd64 \
  tf.example.com/example/internal
```

公式資料は、公開元だけが配布者の署名で保護された公式の検査値を提供できると注意しています。ミラーを指定した場合は、そのミラーが返す配布物の検査値になります。出力に表示される署名者を確認してから、ロックファイルを登録します。

共有[キャッシュ](/glossary/キャッシュ/)を使う場合も、検査を無効にする設定を安易に追加しないでください。[CLI設定の公式資料](https://developer.hashicorp.com/terraform/cli/config/config-file#allowing-the-provider-plugin-cache-to-break-the-dependency-lock-file)は、`plugin_cache_may_break_dependency_lock_file` を例外的な設定とし、異なる[OS](/glossary/os/)やCPUでは使えない不完全な項目を作る可能性を警告しています。

### 原因6：モノレポで別ディレクトリのロックファイルを更新した

`.terraform.lock.hcl` は、[リポジトリ](/glossary/リポジトリ/)全体に1つとは限りません。Terraformは、ルートモジュールの `.tf` [ファイル](/glossary/ファイル/)がある現在の作業[ディレクトリ](/glossary/ディレクトリ/)にロックファイルを作成します。

```text
repository/
├── envs/
│   ├── dev/
│   │   ├── main.tf
│   │   └── .terraform.lock.hcl
│   └── prod/
│       ├── main.tf
│       └── .terraform.lock.hcl
└── modules/
    └── network/
```

`envs/prod` のCIが失敗しているのに、[リポジトリ](/glossary/リポジトリ/)の直下や `envs/dev` で更新しても直りません。CIと同じルートモジュールを指定します。

```bash
terraform -chdir=envs/prod init -upgrade
terraform -chdir=envs/prod providers lock \
  -platform=darwin_arm64 \
  -platform=linux_amd64
git diff -- envs/prod/.terraform.lock.hcl
```

[公式のロックファイル資料](https://developer.hashicorp.com/terraform/language/files/dependency-lock#lock-file-location)は、ロックファイルが構成全体に属し、ルートモジュールの作業[ディレクトリ](/glossary/ディレクトリ/)に置かれると説明しています。CIの `working-directory`、`terraform -chdir`、更新対象の[ファイル](/glossary/ファイル/)を同じ場所にそろえます。

### 原因7：古い.terraformディレクトリをCIで再利用している

`.terraform.lock.hcl` と `.terraform` は別物です。

```text
.terraform.lock.hcl  選択したプロバイダー版と検査値。版管理する。
.terraform/          作業環境ごとの初期化結果。版管理しない。
```

CIで `.terraform` 全体を、[OS](/glossary/os/)、CPU、Terraformの版、ロックファイルが異なる処理の間で共有すると、古いプロバイダーや子モジュールが混ざります。[ダウンロード](/glossary/ダウンロード/)を減らす場合は、作業[ディレクトリ](/glossary/ディレクトリ/)全体を使い回すのではなく、[公式の共有プラグインキャッシュ](https://developer.hashicorp.com/terraform/cli/config/config-file#provider-plugin-cache)を使い、[キャッシュ](/glossary/キャッシュ/)の[キー](/glossary/キー/)へ少なくとも[OS](/glossary/os/)、CPU、Terraformの版、`.terraform.lock.hcl` の内容を含めます。

初期化時には、どの版をどこから使ったかが表示されます。

```bash
terraform version
terraform init -input=false -lockfile=readonly
```

CI上の一時的な作業場所なら、古い `.terraform` を引き継がない新しい作業場所で再実行し、再現するかを確認します。ローカル[環境](/glossary/環境/)では `.terraform` に現在の作業領域名なども記録されるため、削除後に使う作業領域と接続先を改めて確認します。

### 原因8：plan作成後に設定またはロックファイルが変わった

CIで `plan` と `apply` を別の段階に分ける場合、[保存](/glossary/保存/)したplanには作成時点の設定と依存関係の情報が入ります。plan作成後に `.terraform.lock.hcl` を更新し、古いplanを適用すると不一致になります。

```text
Error: Inconsistent dependency lock file

The given plan file was created with a different set of external
dependency selections than the current configuration.
A saved plan can be applied only to the same configuration it was
created from.

Create a new plan from the updated configuration.
```

この場合は古いplanを捨て、更新後の同じ変更内容から作り直します。

```bash
terraform init -input=false -lockfile=readonly
terraform plan -input=false -out=tfplan
terraform apply tfplan
```

[Terraformを自動実行する公式資料](https://developer.hashicorp.com/terraform/tutorials/automation/automate-terraform)では、planとapplyで同じ[OS](/glossary/os/)とCPUを使い、同一のプロバイダーを利用できるようにする必要があると説明されています。planだけを別の変更内容へ持ち越さず、同じ登録内容から作った成果物として扱います。

## 補足：似ているが別のもの

`Error acquiring the state lock` は、状態[ファイル](/glossary/ファイル/)への同時書き込みを防ぐためのロックです。`.terraform.lock.hcl` が扱うプロバイダー依存関係とは別です。`terraform force-unlock` や `-lock=false` では、`Inconsistent dependency lock file` は直りません。

`Failed to query available provider packages` と `no available releases match the given constraints` は、ルートと子モジュールから集めた版の条件に共通部分がない状態です。ロックファイルを更新しても、条件を満たす版が存在しなければ解決しません。`terraform providers` で要求元を確認し、矛盾する条件を直します。

`does not have a package available for your current platform` は、対象のプロバイダー版が現在の[OS](/glossary/os/)またはCPU向けに配布されていない状態です。`providers lock -platform` は、存在しない配布物を作りません。対応版へ更新するか、対応している実行環境を使います。

`doesn't match any of the checksums previously recorded` は、選択済みの版に対する配布物の検査[エラー](/glossary/エラー/)です。実行環境の検査値不足なら `providers lock -platform` で直せますが、配布物が改変されている可能性もあります。検査を無効にせず、取得元、ミラー、[キャッシュ](/glossary/キャッシュ/)、署名者を確認します。

`Module not installed` は、子モジュールが `.terraform/modules` に取得されていない状態です。`terraform init` で取得します。現在の依存ロックファイルが固定するのはプロバイダーであり、遠隔の子モジュールの選択版ではありません。

## CI向けの再発防止

ロックファイルを更新する処理と、CIで検証する処理を分けます。

開発側では、設定変更後に版と対象環境を確定します。

```bash
terraform init -upgrade

terraform providers lock \
  -platform=darwin_arm64 \
  -platform=linux_amd64

terraform providers
git diff -- .terraform.lock.hcl
```

意図した版、版の条件、検査値、[コマンド](/glossary/コマンド/)出力の署名者を確認し、設定とロックファイルを同じ変更へ含めます。

CIでは、登録済みの選択を変更しない形で[初期化](/glossary/初期化/)します。

```bash
terraform init -input=false -lockfile=readonly
terraform validate
terraform plan -input=false -out=tfplan
```

`plan` と `apply` を別の段階にする場合は、次を同じにします。

```text
登録内容
Terraformの版
OSとCPU
ルートモジュールの場所
初期化設定と取得元
保存したplanファイル
```

CIで `terraform init -upgrade` を毎回実行すると、設定条件内で公開された新しい版が自動的に選ばれ、ロックファイルの差分が[保存](/glossary/保存/)されないまま処理が進む可能性があります。依存関係の更新を行う専用処理でない限り、CIは `-lockfile=readonly` で不一致を検出する側に置きます。

## 切り分けの順序

1. [エラー](/glossary/エラー/)見出しと本文を[保存](/glossary/保存/)し、`no version is selected`、版の条件不一致、検査値不一致、plan不一致のどれかを確定する。
2. CIが実行しているルートモジュールの場所と、対象の `.terraform.lock.hcl` を確認する。
3. `terraform version` でTerraformの版、[OS](/glossary/os/)、CPUを確認する。
4. `terraform providers` で、ルートと子モジュールが要求するプロバイダーと版の条件を確認する。
5. 設定条件と選択済みの版が合わない場合は、開発側で `terraform init -upgrade` を実行する。
6. CI[環境](/glossary/環境/)の検査値がない場合は、全実行環境を指定して `terraform providers lock -platform` を実行する。
7. `.terraform.lock.hcl` の差分と署名者を確認し、設定変更と一緒に版管理へ入れる。
8. CIでは `terraform init -lockfile=readonly` を使い、未登録の変更を検出する。
9. [保存](/glossary/保存/)したplanが古い場合は、更新後の同じ設定と依存関係から作り直す。
10. `.terraform.lock.hcl` の[削除](/glossary/削除/)や検査の無効化は、原因を隠すための手段として使わない。

## 確認コマンド集

```bash
# 1. Terraformの版、OS、CPU、導入済みプロバイダーを確認する
terraform version

# 2. ルートと子モジュールが要求するプロバイダーを確認する
terraform providers

# 3. ロックファイルの選択を確認する
sed -n '1,240p' .terraform.lock.hcl

# 4. ロックファイルが登録対象か確認する
git status --short -- .terraform.lock.hcl
git check-ignore -v .terraform.lock.hcl

# 5. 設定変更に合わせて版を選び直す
terraform init -upgrade

# 6. 開発機とCIの対象環境をロックファイルへ追加する
terraform providers lock \
  -platform=darwin_arm64 \
  -platform=linux_amd64

# 7. 更新差分を確認する
git diff -- .terraform.lock.hcl

# 8. CIと同じくロックファイルを変更せず初期化する
terraform init -input=false -lockfile=readonly

# 9. モノレポの特定環境を更新する
terraform -chdir=envs/prod init -upgrade
terraform -chdir=envs/prod providers lock -platform=linux_amd64

# 10. 保存したplanを更新後の依存関係から作り直す
terraform plan -input=false -out=tfplan
terraform show tfplan
```

Windowsで `sed` がない場合は、PowerShellでロックファイルを表示できます。

```powershell
Get-Content .terraform.lock.hcl
```

## Editor's Note

Terraformの依存ロックファイルは、[公式資料](https://developer.hashicorp.com/terraform/language/files/dependency-lock)によれば0.14から導入された仕組みです。設定に書いた版の範囲とは別に、実際に選んだプロバイダー版と配布物の検査値を[保存](/glossary/保存/)し、別の人やCIでも同じ選択を再現する役割を持ちます。

その役割が、異なる実行環境と共有[キャッシュ](/glossary/キャッシュ/)の組み合わせで表面化した記録が、2021年11月の[Lock Files, Plugin Cache and using several architectures fails terraform init](https://github.com/hashicorp/terraform/issues/29958)です。

報告環境では、Linux AMD64で共有プラグインキャッシュを使って作ったロックファイルに、その[環境](/glossary/環境/)で計算した `h1:` の検査値だけが入りました。別のmacOS[環境](/glossary/環境/)で同じプロバイダー版を使おうとすると、配布物が既存の検査値と一致せず、[初期化](/glossary/初期化/)に失敗しました。

議論で示された対処は、チームが使う[環境](/glossary/環境/)を最初からすべて `terraform providers lock -platform=...` へ渡すことでした。2022年7月に課題が閉じられた際、Terraform 1.2.6へ入る変更として、`providers lock` が既存の検査値に阻まれず対象環境の検査値を追加できるようになったこと、`terraform init` が不完全なロックファイルに警告を出すこと、検査値不一致時に資料への案内を出すことが説明されています。

同じ議論の末尾では、`terraform providers lock` は既存の項目があればその `version` を使い、版自体は更新しないことも確認されています。版を更新するには、引き続き `terraform init -upgrade` が必要です。

ここに2つの[コマンド](/glossary/コマンド/)の境界があります。

```text
terraform init -upgrade
  設定された条件から、使う版を選び直す。

terraform providers lock -platform=...
  選択済みの版について、各実行環境の検査値をそろえる。
```

CIでロックファイルが刺さるのは、ロック機能が無関係な処理を妨げているからではありません。設定、選択済みの版、取得した配布物、実行環境のどれかが、開発時とCIで同じではないことを止めて知らせています。

`.terraform.lock.hcl` を消すと、その不一致を見えなくして、新しい選択を作り直せます。しかし、何が変わったかを確認する機会も同時に消えます。設定変更なら `init -upgrade`、環境差なら `providers lock -platform`。原因を分け、差分を版管理へ残すことが、この[エラー](/glossary/エラー/)の解決です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
