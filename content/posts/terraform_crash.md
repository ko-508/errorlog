---
title: "Terraform の crash エラー：原因と解決策"
date: 2026-07-28
description: "Terraform の crash は、本体が落ちた場合とプロバイダのプラグインが落ちた場合で、出力される文言も報告先も異なります。落ちたプラグインを巻き込んだ他の処理は Plugin did not respond や Request cancelled として大量に並びますが、原因はその下にあるスタックトレース1つです。crash.log を探す定番の手順は、1.1 以降のバージョンでは通用しません。"
tags: ["Terraform"]
errorCode: "crash"
lastmod: 2026-07-28
service: "Terraform"
error_type: "crash"
components: ["CLI", "Provider Plugin"]
related_services: ["Terraform Provider", "HCP Terraform"]
trend_incident: false
---

## 冒頭まとめ

Terraform の crash は、設定の誤りではなく[ソフトウェア](/glossary/ソフトウェア/)側の不具合を示します。ただし「Terraform が落ちた」と一口に言っても、中身は2種類あります。Terraform 本体が落ちた場合と、プロバイダのプラグインが落ちた場合です。文言も、確認する場所も、報告する相手も違います。ソースを読むと、この2つには別々の出力文が定義されています。本体が落ちた場合は `TERRAFORM CRASH` という帯で囲まれた文が出て、報告先は Terraform 本体です。プラグインが落ちた場合は `Stack trace from the <プラグイン名> plugin:` に続けてスタックトレースが出て、末尾に `Error: The <プラグイン名> plugin crashed!` が付き、報告先はそのプラグインの保守者です。

実務で頻度が高いのは後者です。そして厄介なのは、プラグインが落ちると、そのプラグインを使っていた他の処理が巻き添えで失敗し、`Plugin did not respond` や `Request cancelled` という[エラー](/glossary/エラー/)が大量に並ぶことです。これらは結果であって原因ではありません。原因は、その下に1つだけ出ているスタックトレースです。

もう1つ、先に否定しておくべき手順があります。「crash.log を確認する」という案内が今も広く出回っていますが、この[ファイル](/glossary/ファイル/)は現在作られません。ソースを比べると、1.0 までは[ファイル](/glossary/ファイル/)を書き出したうえで、その場所と、機密情報が含まれうるという警告まで表示していました。1.1 以降、その処理も文言も消えています。公式の該当ページにも現在は記述がありません。つまり、スタックトレースは標準[エラー](/glossary/エラー/)出力に流れるだけで、取り逃がすと消えます。最初にやるべきは、出力の保全です。

## エラーの概要

出力は3つの形に分かれます。以下は実際に報告された内容をもとにした形です。

プラグインが落ちた場合。巻き添えの[エラー](/glossary/エラー/)が並び、その後にスタックトレースと締めの1文が出ます。

```text
Error: Request cancelled
The plugin6.(*GRPCProvider).UpgradeResourceState request was cancelled.

Error: Plugin did not respond
The plugin encountered an error, and failed to respond to the
plugin6.(*GRPCProvider).ReadResource call. The plugin logs may contain
more details.

Stack trace from the terraform-provider-example_v1.2.3 plugin:

panic: runtime error: invalid memory address or nil pointer dereference
[signal SIGSEGV: segmentation violation code=0x1 addr=0x0 pc=0xe19f58]
...

Error: The terraform-provider-example_v1.2.3 plugin crashed!
```

本体が落ちた場合。帯で囲まれた文が出て、その後に `panic:` とスタックトレースが続きます。

```text
!!!!!!!!!!!!!!!!!!!!!!!!!!! TERRAFORM CRASH !!!!!!!!!!!!!!!!!!!!!!!!!!!!

Terraform crashed! This is always indicative of a bug within Terraform.
Please report the crash with Terraform[1] so that we can fix this.
...
!!!!!!!!!!!!!!!!!!!!!!!!!!! TERRAFORM CRASH !!!!!!!!!!!!!!!!!!!!!!!!!!!!

panic: ...
```

この場合、Terraform は終了[コード](/glossary/コード/) 11 で終わります。ソースの注釈によれば、`plan` の詳細な終了[コード](/glossary/コード/)と衝突しないようにした値で、たまたま SIGSEGV と同じ番号でもあります。[自動化](/glossary/自動化/)の中で終了[コード](/glossary/コード/)を見て分岐している場合、11 は本体が落ちた合図として扱えます。

3つ目は、落ちてはいるがスタックトレースが出ない場合です。プラグインとの[通信](/glossary/通信/)が途絶えたとき、Terraform は[通信](/glossary/通信/)の状態に応じて4種類の[エラー](/glossary/エラー/)を出し分けます。ソースでは、応答が返らない場合は `Plugin did not respond`、要求が取り消された場合は `Request cancelled`、その呼び出しに対応していない場合は `Unsupported plugin method`、それ以外は `Plugin error` と定義されています。1つ目の分岐にはソース上に注釈があり、多くはクラッシュの結果だと書かれています。ただし、スタックトレースが1つも出ていないなら、プラグインは異常終了はしたがパニックはしていない、という読み方になります。代表は[メモリ](/glossary/メモリ/)不足による強制終了です。

## まず最初に：スタックトレースの有無と、その1行目を見る

第一に、出力全体からスタックトレースを探します。`Stack trace from the` で始まる行があればプラグインが落ちています。`TERRAFORM CRASH` の帯があれば本体です。どちらも無く `Plugin did not respond` だけが並んでいるなら、パニックを伴わない異常終了です。

第二に、スタックトレースの1行目を読みます。`panic: runtime error: invalid memory address or nil pointer dereference` であれば、値が無い状態を参照した不具合です。`index out of range` であれば範囲外の参照、`interface conversion` であれば型の取り違えです。この1行が、報告時に最も重要な情報になります。

第三に、スタックトレースの中でプラグインの[ファイル](/glossary/ファイル/)名と[行番号](/glossary/行番号/)が出ている箇所を探します。どの資源の処理で落ちたかがここで分かります。該当する資源を設定から一時的に外せば、原因が確定するとともに、当座の回避策にもなります。

`Plugin did not respond` の行を1つずつ追いかけるのは、遠回りになります。落ちたプラグインを共有していた処理はすべて失敗するため、この[エラー](/glossary/エラー/)は資源の数だけ並びます。読むべきはスタックトレースの側です。

## よくある原因と解決手順

### 原因1：プロバイダのプラグインが落ちた

最も頻度の高い形です。特定の資源の読み取りや更新で、プラグイン側が値の無い状態を扱いきれずに落ちます。プラグインの[バージョン](/glossary/バージョン/)を上げた直後に出始めた場合は、その[バージョン](/glossary/バージョン/)の不具合である可能性が高くなります。

**Before（版を固定せず、落ちた原因が追えない）：**

```hcl
terraform {
  required_providers {
    example = {
      source = "example/example"
    }
  }
}
```

**After（版を固定し、落ちない版まで戻す）：**

```hcl
terraform {
  required_providers {
    example = {
      source  = "example/example"
      version = "1.1.9"
    }
  }
}
```

固定したら `terraform init -upgrade` で入れ替えます。落ちる版と落ちない版が分かれば、それ自体が報告に必要な情報になります。報告先は Terraform 本体ではなく、そのプラグインの保守元です。出力の末尾の文にも、プラグインの保守者に報告してほしいと書かれています。

なお、画面に出るプラグインのスタックトレースは全文ではありません。ソースでは、パニックの始まりを検知してから記録する行数の上限が100行に設定されています。画面が埋まるのを避けるための制限です。全文が必要な場合は、次の項の方法で[ログ](/glossary/ログ/)を採ります。

### 原因2：出力を取り逃がしている

現在の Terraform は crash.log を作りません。したがって、画面を閉じたり、[自動化](/glossary/自動化/)の実行結果を破棄したりすると、原因を示す唯一の情報が消えます。

**Before（画面に流すだけ）：**

```bash
terraform apply
```

**After（標準[エラー](/glossary/エラー/)出力も含めて[保存](/glossary/保存/)する）：**

```bash
terraform apply -no-color 2>&1 | tee terraform-apply.log
```

さらに詳しい情報が要る場合は、[環境変数](/glossary/環境変数/)で[ログ](/glossary/ログ/)を有効にします。公式文書のとおり、`TF_LOG` に `TRACE`・`DEBUG`・`INFO`・`WARN`・`ERROR` のいずれかを設定すると詳細な[ログ](/glossary/ログ/)が標準[エラー](/glossary/エラー/)出力に出ます。`TF_LOG_CORE` と `TF_LOG_PROVIDER` で本体側とプラグイン側を分けて指定でき、`TF_LOG_PATH` で[ファイル](/glossary/ファイル/)に追記できます。ただし `TF_LOG_PATH` だけでは何も出ません。`TF_LOG` が設定されていることが条件だと公式文書に明記されています。

```bash
export TF_LOG=TRACE
export TF_LOG_PATH=./terraform-trace.log
terraform apply
```

プラグイン側だけを詳しく採るなら次のようにします。本体側の[ログ](/glossary/ログ/)量を抑えられます。

```bash
export TF_LOG_CORE=ERROR
export TF_LOG_PROVIDER=TRACE
export TF_LOG_PATH=./provider-trace.log
```

### 原因3：メモリ不足などによる異常終了

`Plugin did not respond` は出るがスタックトレースが1つも出ない場合、プラグインの処理が途中で消えた可能性があります。資源の数が多い構成や、大きな状態[ファイル](/glossary/ファイル/)を扱う実行で起きやすい形です。

確認は、実行環境の[メモリ](/glossary/メモリ/)の使われ方と、システム側の記録です。

```bash
# Linux で強制終了の記録を確認する
dmesg -T | grep -i "killed process"
journalctl -k | grep -i "out of memory"
```

該当する記録があれば、原因は[ソフトウェア](/glossary/ソフトウェア/)の不具合ではなく資源の不足です。同時に動かす数を減らすと収まることがあります。

```bash
terraform apply -parallelism=5
```

根本的には、1つの状態[ファイル](/glossary/ファイル/)で扱う範囲を分割するほうが安定します。

### 原因4：Terraform 本体が落ちた

`TERRAFORM CRASH` の帯が出た場合です。頻度は高くありませんが、設定の書き方が引き金になっている場合があり、その場合は最小の再現手順を作れます。

手順は、対象を絞りながら落ちる範囲を狭めることです。

```bash
terraform plan -target=module.example
```

落ちる対象が特定できたら、その部分だけを別の[ディレクトリ](/glossary/ディレクトリ/)に切り出し、最小の設定で再現するかを確かめます。再現できれば、その設定と[バージョン](/glossary/バージョン/)、スタックトレースを添えて Terraform 本体へ報告できます。出力にも報告先の場所が書かれています。

また、本体を新しい[バージョン](/glossary/バージョン/)に上げると直っている場合があります。落ちた[バージョン](/glossary/バージョン/)は `terraform version` で確認し、変更履歴でその不具合が修正済みかを調べてから上げてください。

## 補足：crash に見えて crash ではないもの

`Request cancelled` は、要求が取り消されたことを示します。他の処理が落ちたことで実行全体が畳まれた際に、巻き添えとして大量に出ます。単独で出ている場合は、利用者による中断や時間切れも考えられます。

`Unsupported plugin method` は、プラグインがその呼び出しに対応していないことを示します。プラグインと本体の[バージョン](/glossary/バージョン/)の組み合わせが合っていない場合に現れます。落ちたわけではないので、スタックトレースは出ません。

`Plugin error` は、上記のどれにも当てはまらない応答が返った場合です。文面に呼び出し名と元の[エラー](/glossary/エラー/)が入るので、そこを読みます。

いずれもスタックトレースを伴いません。逆に言えば、スタックトレースが無い[エラー](/glossary/エラー/)を crash として報告しても、受け取った側は原因を追えません。報告の前に、スタックトレースが出ているかを必ず確かめてください。

状態[ファイル](/glossary/ファイル/)の鍵が絡む失敗は、これらとは別系統です（[Terraform の state lock の記事](/posts/terraform_state_lock/)）。プロバイダから返る [HTTP](/glossary/http/) の[エラー](/glossary/エラー/)は、そもそも crash ではありません（[Terraform の 500 の記事](/posts/terraform_500/)、[429 の記事](/posts/terraform_429/)）。

## 切り分けの順序

1. 出力を[保存](/glossary/保存/)する。crash.log は作られないため、消したら終わりだと考える。
2. `Stack trace from the` を探す。あればプラグインが落ちている。プラグイン名と版がその行に出ている。
3. `TERRAFORM CRASH` の帯を探す。あれば本体が落ちている。終了[コード](/glossary/コード/)は 11 になる。
4. どちらも無く `Plugin did not respond` だけが並ぶなら、パニックを伴わない異常終了を疑い、[メモリ](/glossary/メモリ/)不足の記録を確認する。
5. スタックトレースの1行目と、プラグインの[ファイル](/glossary/ファイル/)名・[行番号](/glossary/行番号/)を読む。落ちた資源を特定する。
6. その資源を外して実行し、落ちなくなることを確かめる。当座の回避と原因の確定を同時に行う。
7. プラグインの版を、落ちない版まで戻して固定する。落ちる版と落ちない版の両方が、報告に必要な情報になる。
8. 報告先を間違えない。プラグインが落ちたならその保守元、本体が落ちたなら Terraform 本体。

## 確認コマンド集

```bash
# 1. 出力を丸ごと保存しながら実行する
terraform apply -no-color 2>&1 | tee terraform-apply.log

# 2. 保存した出力から、原因の行だけを抜き出す
grep -n "Stack trace from the\|TERRAFORM CRASH\|^panic:" terraform-apply.log

# 3. 詳細なログをファイルに採る（TF_LOG が無いと TF_LOG_PATH は働かない）
TF_LOG=TRACE TF_LOG_PATH=./terraform-trace.log terraform plan

# 4. プラグイン側だけを詳しく採る
TF_LOG_CORE=ERROR TF_LOG_PROVIDER=TRACE TF_LOG_PATH=./provider.log terraform plan

# 5. 本体とプラグインの版を確認する
terraform version

# 6. 終了コードを確認する（11 なら本体のパニック）
terraform plan; echo "exit: $?"

# 7. メモリ不足による強制終了の記録を確認する（Linux）
dmesg -T | grep -i "killed process"
```

## Editor's Note

出力の読み方を1件で示す実例として、GitLab のプロバイダに残る不具合報告があります（[Terraform Gitlab provider 17.2 and 17.3 panic: runtime error: invalid memory address or nil pointer dereference](https://gitlab.com/gitlab-org/terraform-provider-gitlab/-/issues/6350)）。Terraform 1.9.5、プロバイダ 17.2 の[環境](/glossary/環境/)で、以前の版では通っていた設定が落ちるようになった、という報告です。

貼られている出力がそのまま教材になっています。まず `Request cancelled` が4つ、`Plugin did not respond` が2つ並びます。これだけを見ると6つの問題が起きたように見えますが、その下に出ているスタックトレースは1つだけで、個人アクセストークンを扱う資源の処理で値の無い状態を参照して落ちたことが、[ファイル](/glossary/ファイル/)名と[行番号](/glossary/行番号/)まで含めて記録されています。最後に `Error: The terraform-provider-gitlab_v17.2.0 plugin crashed!` が付き、報告先がプラグイン側であることも明示されています。並んだ[エラー](/glossary/エラー/)の数と、原因の数は一致しません。

もう1つ、報告者の一言も見過ごせません。詳細な[ログ](/glossary/ログ/)は37,013行あり、公開できる状態にするには時間がかかるので、必要と言われるまで待つ、と書かれています。1.0 までの crash.log は、[ファイル](/glossary/ファイル/)を作ったうえで、機密情報が含まれうるので共有前に[削除](/glossary/削除/)するようにという警告を表示していました。[ファイル](/glossary/ファイル/)を作る仕組みは無くなりましたが、[ログ](/glossary/ログ/)に機密情報が混じる性質は変わっていません。出力を[保存](/glossary/保存/)する運用にするなら、共有する前に中身を確認する手順も一緒に決めておく価値があります。

crash は、利用者側で直せる[エラー](/glossary/エラー/)ではありません。それでも、どちらが落ちたのかを見分け、原因を1つに絞り、報告先を間違えないところまでは、出力を読むだけでできます。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*