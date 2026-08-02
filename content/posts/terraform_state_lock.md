---
title: "Terraform の state lock エラー：原因と解決策"
date: 2026-07-28
description: "Terraform の Error acquiring the state lock は、状態ファイルが壊れたという意味ではなく、他の実行が鍵を持っている、あるいは持ったまま終われなかったことを示します。出力の Lock Info にある7項目、特に Created と Who が原因をほぼ確定させます。既定では再試行が一度も行われないため、待つのか鍵を外すのかを先に決めることが解決の分かれ目です。"
tags: ["Terraform"]
errorCode: "state lock"
lastmod: 2026-07-28
service: "Terraform"
error_type: "state lock"
components: ["State", "Backend"]
related_services: ["Amazon S3", "Amazon DynamoDB", "HCP Terraform"]
trend_incident: false
---

## 冒頭まとめ

Terraform の `Error acquiring the state lock` は、状態[ファイル](/glossary/ファイル/)が壊れたという意味ではありません。状態[ファイル](/glossary/ファイル/)を同時に書き換えられないよう Terraform が取る鍵を、今回は取れなかったという通知です。原因は突き詰めると2つしかありません。他の実行が本当に鍵を持っているか、鍵を持ったまま終われなかった実行の跡が残っているかです。

判別の材料は、[エラー](/glossary/エラー/)出力に必ず付く Lock Info の7項目です。[ID](/glossary/id/)・Path・Operation・Who・[バージョン](/glossary/バージョン/)・Created・Info が並び、Terraform のソースでもこの並びの雛形として定義されています。このうち Created（鍵を取った時刻、協定世界時）と Who（利用者名@ホスト名）を読めば、待つべきか外すべきかはほぼ決まります。

先に押さえておきたい性質が1つあります。Terraform は既定では鍵の取得を再試行しません。`-lock-timeout` の既定値は 0 で、ソースでは指定された時間をそのまま期限として文脈を作るため、0 の場合は最初の1回で失敗が確定します。逆に `-lock-timeout=5m` のように指定すると、1秒から始めて倍々に伸ばし、最大16秒間隔で、指定時間まで再試行を続けます。「待てば通ったはずの[エラー](/glossary/エラー/)」を即座の失敗として受け取っていることが、実際には少なくありません。

境界も引いておきます。`-lock=false` は解決ではなく回避です。Terraform 自身の[エラー](/glossary/エラー/)本文にも、ほとんどの[コマンド](/glossary/コマンド/)で無効化できるが推奨しないと書かれています。また `Error releasing the state lock` は逆向きの[エラー](/glossary/エラー/)で、鍵を外す側の失敗です。

## エラーの概要

実際の出力は次の形です。冒頭の見出しと、定型の説明文、そして Lock Info が続きます。

```text
Error: Error acquiring the state lock

Error message: operation error S3: PutObject, https response error
StatusCode: 412, api error PreconditionFailed: At least one of the
pre-conditions you specified did not hold

Lock Info:
  ID:        3f6a1c9e-1f2b-4a55-9d1c-0a7e2b9c4d51
  Path:      my-tfstate-bucket/prod/terraform.tfstate.tflock
  Operation: OperationTypeApply
  Who:       deploy@runner-07
  Version:   1.11.4
  Created:   2026-07-28 02:14:22.5 +0000 UTC
  Info:
```

Lock Info の7項目は、Terraform のソースに文字列の雛形として定義されています。[ID](/glossary/id/) は鍵の識別子で、後述の解除[コマンド](/glossary/コマンド/)に渡す値です。Path は鍵の置き場所で、どの[バックエンド](/glossary/バックエンド/)のどの状態[ファイル](/glossary/ファイル/)かが分かります。Operation は実行しようとした操作（`OperationTypeApply` など）、Who は利用者名とホスト名を `@` でつないだもの、[バージョン](/glossary/バージョン/)は鍵を取った側の Terraform の[バージョン](/glossary/バージョン/)、Created は鍵を取った時刻で協定世界時、Info は呼び出し側が付ける補足で、空のことが多い項目です。

説明文の側は固定の文面で、内容は次の3点です。状態[ファイル](/glossary/ファイル/)が複数の利用者から同時に書かれるのを防ぐために鍵を取っていること、上に出ている問題を解消してからやり直してほしいこと、ほとんどの[コマンド](/glossary/コマンド/)では `-lock=false` で無効化できるが推奨されないこと。つまり、原因の手がかりは説明文ではなく `Error message:` の行と Lock Info にあります。

なお、鍵の取得に400ミリ秒を超える時間がかかると、Terraform は待機中である旨を画面に出します。この閾値もソースに定数として定義されています。しばらく止まって見えるのは異常ではありません。

## まず最初に：Created と Who を読む

第一に、Created を現在時刻と比べます。協定世界時なので、日本時間なら9時間を足して考えます。数秒から数分前であれば、別の実行が今まさに動いている可能性が高い状態です。数時間以上前であれば、実行が終わっているのに鍵だけが残っている可能性が高くなります。

第二に、Who を見ます。自分以外の利用者名や、CI の実行環境のホスト名であれば、その実行の生死を先に確認します。自分と同じであれば、直前に自分が止めた実行の跡である可能性が高い状態です。

第三に、Path を見ます。ここに出ている鍵の置き場所が、いま自分が操作しているつもりの[ワークスペース](/glossary/ワークスペース/)と一致しているかを確かめます。ここがずれていると、この後の解除[コマンド](/glossary/コマンド/)が空振りします。

この3項目を読まずに解除[コマンド](/glossary/コマンド/)へ進むのが、最も避けたい進め方です。動いている実行の鍵を外すと、2つのプロセスが同時に状態[ファイル](/glossary/ファイル/)を書く事態になり、鍵が防ごうとしていた壊れ方そのものを招きます。

## よくある原因と解決手順

### 原因1：別の実行が本当に動いている

複数人が同時に実行した、あるいは2つの自動実行が同時に起動した場合です。この場合、鍵は正しく働いています。外すのではなく待つのが正解です。

問題は、既定では待ってくれないことです。前述のとおり `-lock-timeout` の既定値は 0 で、この値がそのまま期限として使われるため、期限は最初から切れた状態になります。結果として、鍵が取れなければ再試行なしで失敗します。

**Before（既定のまま実行して即座に失敗する）：**

```bash
terraform apply
# → Error acquiring the state lock（1回試して終わり）
```

**After（待ち時間を指定して再試行させる）：**

```bash
terraform apply -lock-timeout=10m
```

指定すると、Terraform は1秒待って再試行し、間隔を倍にしながら最大16秒まで伸ばし、指定した時間に達するまで繰り返します。この間隔の伸ばし方もソースに定義されています。自動実行の仕組みでは、実行時間の見込みより長めの値を付けておくと、単なる順番待ちが失敗として扱われなくなります。

### 原因2：実行が異常終了して鍵が残った

Ctrl-C を続けて押した、[自動化](/glossary/自動化/)の実行が時間切れで打ち切られた、実行環境が落ちた、接続が切れた。いずれの場合も、鍵を取ったあと外す処理まで到達できず、鍵だけが残ります。

対処は解除[コマンド](/glossary/コマンド/)です。[引数](/glossary/引数/)は Lock Info の [ID](/glossary/id/) を1つだけ渡します。

**Before（原因を確かめず、待たずに外す）：**

```bash
terraform force-unlock -force 3f6a1c9e-1f2b-4a55-9d1c-0a7e2b9c4d51
```

**After（実行主体の生死を確かめてから外す）：**

```bash
# 1. Who と Created を確認し、その実行が終わっていることを確かめる
# 2. 対象のワークスペースが合っていることを確かめる
terraform workspace show

# 3. 解除する（確認を求められるので yes と入力する）
terraform force-unlock 3f6a1c9e-1f2b-4a55-9d1c-0a7e2b9c4d51
```

確認の問いには `yes` だけが受け付けられます。`-force` を付けると確認を省略できますが、これは人の判断を挟まない指定なので、内容を確かめたうえで使う[コマンド](/glossary/コマンド/)です。

### 原因3：ワークスペースの取り違え

解除[コマンド](/glossary/コマンド/)は、現在選択されている[ワークスペース](/glossary/ワークスペース/)の状態に対して働きます。ソースでも、[バックエンド](/glossary/バックエンド/)を読み込んだあとに現在の[ワークスペース](/glossary/ワークスペース/)を取得し、その状態管理に対して解除を要求する流れになっています。

したがって、Lock Info の Path が示す場所と、`terraform workspace show` の結果が食い違っていると、正しい [ID](/glossary/id/) を渡しても解除されません。[ID](/glossary/id/) が合っているのに解除できないときは、[コマンド](/glossary/コマンド/)を疑う前に[ワークスペース](/glossary/ワークスペース/)を疑ってください。

### 原因4：ローカルの状態ファイルで起きた

[バックエンド](/glossary/バックエンド/)を設定していない場合、鍵は同じ場所に置かれる `.terraform.tfstate.lock.info` という[ファイル](/glossary/ファイル/)で管理されます。名前の付け方はソースで、状態[ファイル](/glossary/ファイル/)名の前に点を付け、後ろに `.lock.info` を足す規則として定義されています。

この場合、解除[コマンド](/glossary/コマンド/)は使えません。ソースには、ローカルの状態は別のプロセスからは解除できないという趣旨の[エラー](/glossary/エラー/)が定義されています。Terraform の[コマンド](/glossary/コマンド/)の説明文にも同じことが書かれています。実行が終わっていることを確かめたうえで、残った[ファイル](/glossary/ファイル/)を削除します。

```bash
ls -la .terraform.tfstate.lock.info
rm .terraform.tfstate.lock.info
```

### 原因5：S3 の鍵ファイルが残った、または二重に取っている

S3 の[バックエンド](/glossary/バックエンド/)には2つの方式があります。新しい方式は `use_lockfile = true` で、状態[ファイル](/glossary/ファイル/)の隣に `.tflock` を付けた[ファイル](/glossary/ファイル/)を作ります。ソースでは、この[ファイル](/glossary/ファイル/)を「存在しない場合のみ作る」という条件付きの書き込みで作成しています。すでにある場合、S3 は 412 PreconditionFailed を返し、それがそのまま `Error message:` の行に出ます。冒頭に挙げた出力例がこの形です。

古い方式は `dynamodb_table` で、[データベース](/glossary/データベース/)側に鍵の記録を置きます。この[引数](/glossary/引数/)は現在のソースで非推奨の印が付いており、指定すると `use_lockfile` を使うようにという警告が出ます。公式の変更履歴では、1.10 で S3 単体での鍵の仕組みが導入され、1.11 で正式版となり、[データベース](/glossary/データベース/)側の[引数](/glossary/引数/)が非推奨になったと記録されています。

注意が要るのは移行期です。1.10 の変更履歴には、両方を設定した場合は両方から鍵を取ると書かれています。つまり、片方だけ鍵が残る状態がありえます。解除[コマンド](/glossary/コマンド/)で解消しない場合は、残っている側を直接確認します。

```bash
# 新しい方式：状態ファイルの隣の .tflock を確認する
aws s3 ls s3://<バケット名>/<状態ファイルのキー>.tflock

# 古い方式：データベース側の記録を確認する
aws dynamodb get-item --table-name <テーブル名> \
  --key '{"LockID": {"S": "<バケット名>/<状態ファイルのキー>"}}'
```

削除は最後の手段です。中身に Who と Created が入っているので、必ず読んでから消してください。

## 補足：似ているが別のもの

`-lock=false` は鍵を取らずに実行する指定です。鍵が残って動かせないときの緊急回避としては働きますが、同時実行に対する保護を外すことと同義です。Terraform 自身の[エラー](/glossary/エラー/)本文が推奨しないと明記しているとおり、常用する指定ではありません。

そもそも鍵を取らない構成もあります。S3 の[バックエンド](/glossary/バックエンド/)で `use_lockfile` も `dynamodb_table` も設定していない場合がこれにあたります。この構成では state lock の[エラー](/glossary/エラー/)は出ませんが、それは安全だからではなく、保護されていないからです。

`Error releasing the state lock` は解放側の失敗です。ソースの文面では、解放できたかどうか分からない状態になりうること、その場合は解除[コマンド](/glossary/コマンド/)を呼ぶこと、ただし他に鍵を持っている者がいないと確信できる場合に限ることが述べられています。取得側の[エラー](/glossary/エラー/)と混同しないでください。

[HTTP](/glossary/http/) の[バックエンド](/glossary/バックエンド/)を使っている場合、鍵の衝突は [HTTP](/glossary/http/) の状態[コード](/glossary/コード/)として現れます。ソースでは 409 Conflict と 423 Locked の両方を鍵の衝突として扱っています。409 が出ている場合の切り分けは[Terraform の 409 の記事](/posts/terraform_409/)も参照してください。[権限](/glossary/権限/)不足で鍵の[ファイル](/glossary/ファイル/)を作れない場合は、鍵の衝突ではなく[権限](/glossary/権限/)の[エラー](/glossary/エラー/)として現れます（[Terraform の 403 の記事](/posts/terraform_403/)）。

## 切り分けの順序

1. Lock Info の Created を現在時刻と比べる。数分以内なら実行中の可能性が高く、待つ判断に寄せる。
2. Who を見て、その実行主体が生きているかを確認する。[自動化](/glossary/自動化/)なら実行履歴、手元なら自分の直前の操作を確かめる。
3. 実行中だと判断したら `-lock-timeout` を付けて待つ。既定では再試行が行われないため、指定しない限り待ってはくれない。
4. 残った鍵だと判断したら、Path と `terraform workspace show` が一致することを確かめてから、Lock Info の [ID](/glossary/id/) で解除する。
5. ローカルの状態[ファイル](/glossary/ファイル/)なら、解除[コマンド](/glossary/コマンド/)は使えない。`.terraform.tfstate.lock.info` を削除する。
6. 解除[コマンド](/glossary/コマンド/)が効かない場合は、[バックエンド](/glossary/バックエンド/)側に鍵の実体が残っていないかを直接確認する。S3 なら `.tflock`、古い方式なら[データベース](/glossary/データベース/)の記録。
7. `-lock=false` は最後まで使わない。使う場合も、同時実行がないと確信できるときに限る。

## 確認コマンド集

```bash
# 1. 現在のワークスペースとバックエンドの設定を確認する
terraform workspace show
terraform workspace list

# 2. 待ち時間を指定して実行する（順番待ちを失敗にしない）
terraform apply -lock-timeout=10m

# 3. 鍵を解除する（ID は Lock Info の ID をそのまま渡す）
terraform force-unlock <LOCK_ID>

# 4. ローカルの鍵ファイルの有無と中身を確認する
cat .terraform.tfstate.lock.info

# 5. S3 の鍵ファイルの有無と中身を確認する
aws s3 ls s3://<バケット名>/<状態ファイルのキー>.tflock
aws s3 cp s3://<バケット名>/<状態ファイルのキー>.tflock - | python3 -m json.tool

# 6. 詳細なログを出して、鍵の取得の様子を追う
TF_LOG=TRACE terraform plan 2>&1 | grep -i "state lock"
```

## Editor's Note

新しい方式に移った先で起きた出来事として、Terraform 本体に残る要望の記録があります（[Provide a cost-effective way to use_lockfile with versioning enabled s3 bucket](https://github.com/hashicorp/terraform/issues/36445)）。2025年2月、Terraform 1.10.5 を使う投稿者が、版管理を有効にした S3 の[バケット](/glossary/バケット/)で `use_lockfile` を使うと、実行のたびに作られては消される鍵[ファイル](/glossary/ファイル/)の履歴がすべて残ってしまう、と報告しています。差分を毎日確認する運用では、履歴が際限なく積み上がります。

興味深いのは回避策の議論です。S3 の自動削除の規則は接頭辞では絞れても接尾辞では絞れないため、`.tflock` だけを狙って消すことができません。そこで議論に加わった別の利用者が、鍵[ファイル](/glossary/ファイル/)がおよそ200[バイト](/glossary/バイト/)、資源を含まない状態[ファイル](/glossary/ファイル/)もおよそ200[バイト](/glossary/バイト/)、資源を1つ含む状態[ファイル](/glossary/ファイル/)がおよそ600[バイト](/glossary/バイト/)という実測を示し、大きさで絞る方法を提案したうえで、これは実装の細部に依存していて脆いと自ら断っています。

この記録が示すのは、鍵の仕組みを変えると、[エラー](/glossary/エラー/)の出方だけでなく運用の形も変わるということです。[データベース](/glossary/データベース/)を別に用意しなくてよくなった代わりに、[バケット](/glossary/バケット/)の中に短命な[ファイル](/glossary/ファイル/)が繰り返し作られる構造になりました。`use_lockfile` へ移行する際は、鍵が正しく働くかだけでなく、版管理や自動削除の設定も一緒に見ておく価値があります。

state lock の[エラー](/glossary/エラー/)は、止められたこと自体が保護が働いた証拠です。急いでいるときほど外したくなりますが、読むべき情報は最初から出力に揃っています。Created と Who を読む。それだけで、待つのか外すのかは決まります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*