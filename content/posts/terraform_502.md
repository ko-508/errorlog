---
title: "Terraform の 502 エラー：原因と解決策"
date: 2026-07-29
description: "Terraform の 502 は、中継役がその先から正常な応答を得られなかったことを示します。Terraform 本体のソースは、レジストリ向けの再試行の説明で 502 を名指ししており、設計として再試行で吸収する想定になっています。ところが既定の再試行回数は1回です。文言に出る URL は宛先であって、応答を作った相手ではありません。"
tags: ["Terraform"]
errorCode: "502"
lastmod: 2026-07-29
service: "Terraform"
error_type: "502"
components: ["Registry", "Provider"]
related_services: ["Terraform Registry", "AWS", "HCP Terraform"]
trend_incident: false
---

## 冒頭まとめ

502 Bad Gateway は、要求を取り次いだ中継役が、その先から正常な応答を得られなかったことを示します。同じ 5xx でも、待ちきれずに諦めた場合は 504 です。応答が得られなかったのか、待ち時間が尽きたのかという違いで、疑うべき場所も変わります。

Terraform では、502 の扱いに1つ特徴があります。本体のソースを読むと、[レジストリ](/glossary/レジストリ/)への問い合わせの再試行回数を設定する処理の説明に、「502 のような再試行可能な[エラー](/glossary/エラー/)に対して行う再試行の回数」と書かれています。つまり Terraform は、502 を再試行で吸収すべきものとして名指しで想定しています。

ところが、その既定値は1回です。合計2回で諦める設計になっており、失敗時の文言に「2回試した」と出るのはこのためです。想定しているにもかかわらず、既定では吸収できる幅が非常に狭い、という状態になっています。この回数は[環境変数](/glossary/環境変数/)で増やせます。

もう1つ、読み方の注意点があります。[エラー](/glossary/エラー/)文に現れる URL は、要求の宛先であって、502 を作った相手ではありません。社内の[プロキシ](/glossary/プロキシ/)がその先へ繋げずに 502 を返している場合でも、文言には[レジストリ](/glossary/レジストリ/)の URL が並びます。「[レジストリ](/glossary/レジストリ/)が落ちている」と判断する前に、応答を作ったのが誰かを確かめてください。

## エラーの概要

`terraform init` の段階では、再試行の回数を含む形になります。

```text
Error: Failed to query available provider packages

Could not retrieve the list of available versions for provider example/example:
the request failed after 2 attempts, please try again later:
502 Bad Gateway returned from https://registry.terraform.io/v1/providers/...
```

「2回試した」という数字は、既定の再試行回数が1回であることに対応します。この数字が2以外になっていれば、[環境変数](/glossary/環境変数/)で回数が変更されているということです。

プロバイダの[ファイル](/glossary/ファイル/)を取得する段階でも起きます。この場合、宛先は[レジストリ](/glossary/レジストリ/)ではなく配布元です。

```text
Error: Failed to install provider

Error while installing example/example v1.2.3: unsuccessful request to
https://releases.example.com/terraform-provider-example_1.2.3_linux_amd64.zip:
502 Bad Gateway
```

`terraform plan` や `terraform apply` の途中で出る場合は、プロバイダが[クラウド](/glossary/クラウド/)の窓口を叩いた結果です。この場合、どの資源の処理で起きたかが示されます。応答の本文が各社の[エラー](/glossary/エラー/)形式ではなく、簡素な HTML であれば、作ったのは窓口ではなく手前の中継役です。

## まず最初に：段階と、応答を作った相手を確定する

第一に、`init` の途中か、`plan` や `apply` の途中かを見ます。前者なら[レジストリ](/glossary/レジストリ/)や配布元への経路、後者ならプロバイダから[クラウド](/glossary/クラウド/)への経路です。

第二に、応答の本文を見ます。宛先のサービスが返す[エラー](/glossary/エラー/)には、たいてい機械が読める識別子や追跡番号が含まれます。それが無く、簡素な HTML や短い文字列だけであれば、応答を作ったのは経路上の中継役です。

第三に、Terraform を通さずに同じ宛先へ要求してみます。手元から直接叩いて 200 が返るのに Terraform からは 502 になるなら、両者の経路が違う、つまり[プロキシ](/glossary/プロキシ/)の設定が絡んでいると分かります。

## よくある原因と解決手順

### 原因1：一時的な502で、再試行の回数が足りていない

[レジストリ](/glossary/レジストリ/)側の一時的な混雑や、配布元の一時的な不調で起きる形です。前述のとおり、Terraform はこの状況を想定していますが、既定では1回しか再試行しません。

**Before（既定のまま実行して、2回で諦める）：**

```bash
terraform init
# → the request failed after 2 attempts, please try again later: 502 Bad Gateway
```

**After（再試行の回数を増やす）：**

```bash
export TF_REGISTRY_DISCOVERY_RETRY=5
terraform init
```

1回あたりの待ち時間も[環境変数](/glossary/環境変数/)で変えられます。既定は10秒です。

```bash
export TF_REGISTRY_CLIENT_TIMEOUT=30
```

再試行で通るなら一時的な問題です。何度やっても同じ場所で止まるなら、原因は別にあります。次へ進んでください。

### 原因2：社内の中継役が502を作っている

[プロキシ](/glossary/プロキシ/)を経由する環境で多い形です。[プロキシ](/glossary/プロキシ/)がその先へ繋げないと、利用者には 502 として見えます。文言に並ぶ URL は宛先のままなので、[レジストリ](/glossary/レジストリ/)側の問題に見えてしまいます。

まず、Terraform を通さずに確かめます。

```bash
# プロキシを経由せずに確認する
curl -sS -o /dev/null -w "status:%{http_code}\n" --noproxy '*' \
  https://registry.terraform.io/.well-known/terraform.json

# プロキシを経由して確認する
curl -sS -o /dev/null -w "status:%{http_code}\n" \
  -x "$HTTPS_PROXY" https://registry.terraform.io/.well-known/terraform.json
```

経由しない場合だけ成功するなら、原因は[プロキシ](/glossary/プロキシ/)側です。管理者に、宛先への通信が許可されているかを確認してください。

逆に、[プロキシ](/glossary/プロキシ/)を通すべき環境なのに設定が Terraform に渡っていない、という形もあります。この場合は接続そのものが失敗するので、502 ではなく別の文言になります。渡っているかどうかは[環境変数](/glossary/環境変数/)で確認できます。

```bash
env | grep -i "_proxy"
```

なお、除外の設定に必要な宛先が含まれていないと、内向きの通信まで[プロキシ](/glossary/プロキシ/)へ送られて 502 になることがあります。自前の[レジストリ](/glossary/レジストリ/)を使っている場合は、除外の一覧を確認してください。

### 原因3：プロバイダがクラウドの窓口から受け取っている

`plan` や `apply` の途中で出る形です。調整できるのはプロバイダ側の再試行の設定で、名前と既定値はプロバイダごとに違います。

AWS の場合、実装として 500・502・503・504 が再試行の対象と定義され、既定の試行回数は3回です。AWS のプロバイダはこれを引き上げており、既定で25回になっています。設定で変えられます。

**Before（既定のまま）：**

```hcl
provider "aws" {
  region = "ap-northeast-1"
}
```

**After（再試行の回数を明示する）：**

```hcl
provider "aws" {
  region      = "ap-northeast-1"
  max_retries = 30
}
```

502 は 504 と違い、要求が宛先まで届いていない可能性が高い[エラー](/glossary/エラー/)です。中継役がその先から正常な応答を得られなかった、という意味だからです。したがって、作成の操作で 502 を受けた場合でも、504 ほど二重作成の危険は高くありません。ただし、確実ではありません。中継役が応答の途中で異常を検知した場合など、宛先には届いているという場合もあります。作成の操作であれば、再実行の前に確認する習慣は変えないでください。

### 原因4：自前のレジストリやミラーが応答していない

社内の[レジストリ](/glossary/レジストリ/)や、取得先を差し替える設定を使っている場合です。この構成では、宛先が公開の[レジストリ](/glossary/レジストリ/)ではないため、公開の稼働状況を見ても意味がありません。

まず、どこを見に行っているかを確認します。

```bash
cat ~/.terraformrc 2>/dev/null
cat "$TF_CLI_CONFIG_FILE" 2>/dev/null
```

取得先の差し替えが設定されていれば、その宛先が応答しているかを直接確かめます。

```bash
curl -sS -o /dev/null -w "status:%{http_code}\n" https://<自前のレジストリ>/.well-known/terraform.json
```

一時的に公開の[レジストリ](/glossary/レジストリ/)へ戻して切り分ける場合は、設定[ファイル](/glossary/ファイル/)を退避して再実行します。これで通るなら、原因は自前側です。

## 補足：似ているが別のもの

中継役が待ちきれずに諦めた場合は 504 です。502 は「正常な応答を得られなかった」、504 は「待ち時間が尽きた」という違いです。502 のほうが、宛先まで届いていない可能性が高いと考えられます（[Terraform の 504 の記事](/posts/terraform_504/)）。

要求の頻度が上限を超えた場合は 429 です（[Terraform の 429 の記事](/posts/terraform_429/)）。窓口の内部で処理が失敗した場合は 500 で、こちらは宛先まで届いています（[Terraform の 500 の記事](/posts/terraform_500/)）。[権限](/glossary/権限/)の不足は 403 です（[Terraform の 403 の記事](/posts/terraform_403/)）。

証明書の検証で失敗する場合は、状態コードが返る前に接続が終わるため、502 にはなりません。文言に証明書に関する語が含まれていれば、それは経路の問題であって、宛先の問題ではありません。

実行が途中で止まった場合、次の実行が状態の鍵で止まることがあります（[Terraform の state lock の記事](/posts/terraform_state_lock/)）。

## 切り分けの順序

1. `init` の途中か、`plan` や `apply` の途中かを確定する。
2. 「2回試した」という数字を見る。既定のままなら、まだ再試行の余地がある。
3. 応答の本文を見る。簡素な内容なら、作ったのは中継役。
4. Terraform を通さず、[プロキシ](/glossary/プロキシ/)を経由する場合としない場合の両方で、同じ宛先へ要求してみる。
5. 経由しない場合だけ成功するなら、原因は[プロキシ](/glossary/プロキシ/)側。宛先の許可と除外の設定を確認する。
6. 自前の[レジストリ](/glossary/レジストリ/)や取得先の差し替えを使っていないかを確認する。使っていれば、公開の稼働状況は無関係。
7. プロバイダ経由なら、プロバイダの再試行の設定を確認する。

## 確認コマンド集

```bash
# 1. レジストリへの到達性を、プロキシの有無で比べる
curl -sS -o /dev/null -w "direct: %{http_code}\n" --noproxy '*' \
  https://registry.terraform.io/.well-known/terraform.json
curl -sS -o /dev/null -w "proxy : %{http_code}\n" \
  https://registry.terraform.io/.well-known/terraform.json

# 2. プロキシ関連の環境変数を確認する
env | grep -i "_proxy"

# 3. 再試行の回数と待ち時間を増やして init する
TF_REGISTRY_DISCOVERY_RETRY=5 TF_REGISTRY_CLIENT_TIMEOUT=30 terraform init

# 4. 取得先の差し替え設定を確認する
cat ~/.terraformrc 2>/dev/null; cat "$TF_CLI_CONFIG_FILE" 2>/dev/null

# 5. 詳細なログを採り、502 の出どころと応答本文を見る
TF_LOG=DEBUG TF_LOG_PATH=./tf-debug.log terraform init
grep -n "502\|Bad Gateway\|proxy" tf-debug.log | head -20

# 6. 応答本文をそのまま見る（誰が作った応答かを判断する）
curl -sS -i https://registry.terraform.io/v1/providers/hashicorp/aws/versions | head -20
```

## Editor's Note

本記事で強調した「文言の URL は宛先であって、応答を作った相手ではない」という点は、HashiCorp 自身の窓口記事にも別の形で現れています（[Terraform init: Error while installing provider. Failed to retrieve authentication checksums for provider](https://support.hashicorp.com/hc/en-us/articles/5177241219859-Terraform-init-Error-while-installing-provider-Failed-to-retrieve-authentication-checksums-for-provider)）。

この記事が扱っているのは 502 ではなく証明書の[エラー](/glossary/エラー/)ですが、構図は同じです。通信の中身を検査する[プロキシ](/glossary/プロキシ/)が[レジストリ](/glossary/レジストリ/)への接続に割り込むと、[プロキシ](/glossary/プロキシ/)が用意した証明書が Terraform に提示されます。それを検証できず接続が終わる、という説明が書かれています。表示される[エラー](/glossary/エラー/)文には[レジストリ](/glossary/レジストリ/)の URL が並びますが、実際に応答を作っていたのは経路の途中にいる装置です。対処も、[レジストリ](/glossary/レジストリ/)側ではなく、手元の信頼済み証明書の置き場所を直すことだと案内されています。

502 も同じ位置に立つ[エラー](/glossary/エラー/)です。同じ装置が、その先へ繋げなかったときに返すのが 502、証明書を差し替えたときに起きるのが証明書の[エラー](/glossary/エラー/)、という関係になります。どちらも、文言の URL を読んで宛先を疑うと外します。

Terraform 自身が、再試行の設定の説明で 502 を名指ししているのは示唆的です。この[エラー](/glossary/エラー/)は、待てば消えるものとして扱われています。しかし既定の再試行が1回である以上、その想定が働く幅は狭いままです。[自動化](/glossary/自動化/)の中で `init` を繰り返す構成なら、回数を明示的に増やしておく価値があります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*