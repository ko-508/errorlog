---
title: "ConoHa VPSのDockerでufwが効かない原因と解決策"
date: 2026-08-08
description: "ConoHa VPS の Docker 環境では OS 内の ufw と VPS 外側のセキュリティグループが併用されますが、Docker が -p で公開したポートは通常 ufw の INPUT 規則を迂回するため、どちらを触っているのかを先に確定させないと設定が噛み合いません。"
tags: ["Docker"]
images: ["og/posts/conoha_vps_docker_ufw.png"]
errorCode: ""
lastmod: 2026-08-08
service: "Docker"
error_type: "firewall configuration"
components: ["Docker Engine", "ufw"]
related_services: ["ConoHa VPS", "Ubuntu"]
trend_incident: false
---

> この記事にはアフィリエイト広告が含まれています。

## 冒頭まとめ

ConoHa VPS で [Docker](/glossary/docker/) を動かすとき、[通信](/glossary/通信/)を止めたり通したりする設定は2か所にあります。ひとつは [OS](/glossary/os/) の中にある ufw、もうひとつは VPS の外側にあるセキュリティグループです。

ここで噛み合わなくなる理由が1つあります。[Docker](/glossary/docker/) が `-p` で公開した[ポート](/glossary/ポート/)宛の[通信](/glossary/通信/)は、ufw が使う規則を迂回します。[Docker](/glossary/docker/) の公式ドキュメントは、[Docker](/glossary/docker/) と ufw が互いに相容れない使い方で[ファイアウォール](/glossary/ファイアウォール/)の規則を使うと明記しており、公開された[コンテナ](/glossary/コンテナ/)への[通信](/glossary/通信/)は nat [テーブル](/glossary/テーブル/)で転送されるため、ufw が使う INPUT と OUTPUT のチェーンに到達する前に迂回する、と説明しています（[Packet filtering and firewalls](https://docs.docker.com/engine/network/packet-filtering-firewalls/)）。

この性質から2つのことが言えます。第一に、`ufw allow` だけでは [Docker](/glossary/docker/) の公開[ポート](/glossary/ポート/)を制御できません。第二に、`ufw deny` で拒否しても、[Docker](/glossary/docker/) の公開[ポート](/glossary/ポート/)を塞いだことにはなりません。

したがって、ufw を変更したのに外部から接続できない場合は、ConoHa のセキュリティグループ側を確認する必要があります。逆に、ufw で塞いだつもりの[ポート](/glossary/ポート/)については、ufw の設定を根拠に安全だと判断できません。

## 症状の概要

現れ方は2通りあります。

ひとつは、開けたつもりで繋がらない状態です。`ufw allow 8080` を実行し、`ufw status` の一覧にも出ているのに、外部のブラウザや `curl` から接続できません。

もうひとつは、塞いだつもりで開いている状態です。`ufw deny 8080` を設定しても、`docker run -p 8080:80` で公開した[コンテナ](/glossary/コンテナ/)には[通信](/glossary/通信/)が届きうる、という状態です。

どちらも、ufw の表示と実際の通信経路がずれていることから生じます。ufw の一覧はあくまで ufw が管理している規則を示すもので、[Docker](/glossary/docker/) が別に作る規則は含まれません。

前提として、ConoHa の [Docker](/glossary/docker/) テンプレートの仕様を押さえておきます。公式ドキュメントによれば、[OS](/glossary/os/) は Ubuntu 24.04、[Docker](/glossary/docker/) CE は 29.2.1 で、[OS](/glossary/os/) 内の[ファイアウォール](/glossary/ファイアウォール/)は既定で22番[ポート](/glossary/ポート/)（SSH）のみ許可となっています。また Minimum RAM は 1024 MB と明記されています（[Docker｜ConoHaドキュメントサイト](https://doc.conoha.jp/products/vps-v3/image-v3/image-application-v3/docker-v3/)）。512 MB のプランはこの最小要件を下回ります。

## まず最初に：どちらの層を触っているのかを確定する

推測の前に、2つの層を分けて確認します。

[OS](/glossary/os/) の中の状態は ufw で見ます。

```bash
sudo ufw status verbose
```

ここに出るのは ufw が管理している規則だけです。[Docker](/glossary/docker/) が公開した[ポート](/glossary/ポート/)は、この一覧に現れなくても[通信](/glossary/通信/)が成立しうる、という点を踏まえて読んでください。

外側の状態は ConoHa のコントロールパネルで見ます。ConoHa VPS(Ver.3.0) では、[サーバー](/glossary/サーバー/)ごとに [IP アドレス](/glossary/ip-アドレス/)や[ポート](/glossary/ポート/)、[プロトコル](/glossary/プロトコル/)で[通信](/glossary/通信/)を制御するホワイトリスト形式のセキュリティグループが標準で設定されます。公式ドキュメントは、標準では各テナントごとの default セキュリティグループがアタッチされている[サーバー](/glossary/サーバー/)からのみ[通信](/glossary/通信/)を許可する設定になっていること、外部からの[通信](/glossary/通信/)を許可したい場合は[サーバー](/glossary/サーバー/)の[ネットワーク](/glossary/ネットワーク/)ごとに許可設定が必要であることを述べています（[セキュリティグループ｜ConoHaドキュメントサイト](https://doc.conoha.jp/products/vps-v3/security-v3/security-group-v3/)）。

同じページには、イメージテンプレートによっては [OS](/glossary/os/) 内にもソフトウェアファイアウォールが設定されているため、セキュリティグループとは別に [OS](/glossary/os/) 内の設定もあわせて確認するように、という案内もあります。2か所を分けて見る必要があるのは、この構成によります。

## よくある原因と解決手順

### 原因1：外側の許可設定が入っていない

`ufw allow` を実行したのに外部から接続できない場合です。[OS](/glossary/os/) の中は通す設定になっていても、外側で止まっていれば届きません。

確認方法はコントロールパネル側です。対象[サーバー](/glossary/サーバー/)の[ネットワーク](/glossary/ネットワーク/)に、どのセキュリティグループが割り当てられているかを見ます。公式ドキュメントによれば、ConoHa が用意しているセキュリティグループはルールの設定変更ができず、独自のルールが必要な場合はセキュリティグループを追加して設定する必要があります。用意されているものとしては、SSH 用の IPv4v6-SSH が22番、Web 用の IPv4v6-Web が80番と443番を解放する構成です（[セキュリティグループ](https://doc.conoha.jp/products/vps-v3/security-v3/security-group-v3/)）。

**Before（[OS](/glossary/os/) 内だけを開けて確認を終える）：**

```bash
sudo ufw allow 443
sudo ufw status verbose
```

**After（外側の割り当ても確認する）：**

```text
コントロールパネル → 対象サーバー → ネットワーク情報 → セキュリティグループ
```

80番と443番であれば IPv4v6-Web を割り当てることで対応できます。

### 原因2：80番と443番以外を使おうとしている

8080番や3000番のような任意の[ポート](/glossary/ポート/)を公開したい場合です。ConoHa が用意しているセキュリティグループは用途ごとに解放[ポート](/glossary/ポート/)が決まっており、任意の[ポート](/glossary/ポート/)番号に対応するものはありません。

公式ドキュメントは、独自のセキュリティグループが必要な場合はセキュリティグループを追加してルールを設定する、と明記しています。追加できるルールの項目は、通信方向、イーサタイプ、[プロトコル](/glossary/プロトコル/)、1から65535の[ポート](/glossary/ポート/)、そして [IP アドレス](/glossary/ip-アドレス/)または CIDR 形式の接続元です（[セキュリティグループ](https://doc.conoha.jp/products/vps-v3/security-v3/security-group-v3/)）。

したがって対処は、必要な[ポート](/glossary/ポート/)と接続元を絞った独自グループを作ることです。接続元を CIDR で限定できるので、開発中の管理画面のように公開範囲を狭めたい用途では、全開放ではなく接続元の指定を併用してください。

### 原因3：外部公開が不要なポートを全体へ公開している

`-p 8080:80` の書き方は、ホストのすべてのアドレスで待ち受けます。手元からしか使わない管理画面や[データベース](/glossary/データベース/)でも、この書き方をすると外へ出る構成になります。

[Docker](/glossary/docker/) の公式ドキュメントは、公開フラグに `127.0.0.1` や `::1` を含めると、[Docker](/glossary/docker/) ホストだけがその公開[ポート](/glossary/ポート/)へアクセスできると説明しています（[Port publishing](https://docs.docker.com/engine/network/port-publishing/)）。

**Before（すべての宛先で待ち受ける）：**

```bash
docker run -d -p 8080:80 nginx
```

**After（ホスト自身からのみ届く形にする）：**

```bash
docker run -d -p 127.0.0.1:8080:80 nginx
```

同じページには、28.0.0 より前の版では同じ L2 セグメントにいるホストから、localhost へ公開した[ポート](/glossary/ポート/)に到達できるという注意も書かれています（[moby/moby#45610](https://github.com/moby/moby/issues/45610)）。ConoHa の [Docker](/glossary/docker/) テンプレートに入っている 29.2.1 はこれより新しい版です。

外部から使う予定がないなら、まずこの書き方に変えるのが確実です。外側の設定に依存せず、公開範囲そのものを狭められます。

### 原因4：ホスト側でも制限したいが ufw で書いている

外側の設定に加えて、ホストの中でも[通信](/glossary/通信/)を絞りたい場合です。ufw に書いても [Docker](/glossary/docker/) の公開[ポート](/glossary/ポート/)には適用されません。

[Docker](/glossary/docker/) の公式ドキュメントは、利用者が独自の規則を書く場所として `DOCKER-USER` チェーンを用意しており、ここに置いた規則が `DOCKER-FORWARD` や `DOCKER` の各チェーンより先に処理される、と説明しています。FORWARD チェーンへ追加した規則は [Docker](/glossary/docker/) の規則より後に処理されるため、この目的には `DOCKER-USER` を使うように、とも書かれています（[Docker and iptables](https://docs.docker.com/engine/network/firewall-iptables/)）。

同じページには注意点もあります。`DOCKER-USER` チェーンへ到達した時点で、[パケット](/glossary/パケット/)は既に宛先アドレスの変換を通過しているため、`iptables` の一致条件では[コンテナ](/glossary/コンテナ/)側の内部アドレスと[ポート](/glossary/ポート/)しか照合できません。元の宛先で照合したい場合は `conntrack` の拡張を使う必要があります。

この方法は書き方を誤ると[コンテナ](/glossary/コンテナ/)の通信全体を止めます。まずは原因3の公開範囲の限定と、外側のセキュリティグループでの制限を検討し、それでもホスト側の制御が必要な場合に取り組んでください。

## 補足：似ているが別のもの

ufw の一覧に規則が出ていること自体は誤りではありません。ufw が管理する範囲、たとえば[コンテナ](/glossary/コンテナ/)を経由しないホスト上のプロセスへの[通信](/glossary/通信/)には、そのまま効きます。効かないのは [Docker](/glossary/docker/) が公開した[ポート](/glossary/ポート/)宛の[通信](/glossary/通信/)です。

`docker run` を使わずホスト上で直接起動したプロセスは、この話の対象外です。ufw の設定がそのまま適用されます。

ConoHa の公式ドキュメントに載っている `ufw allow` の手順は、テンプレート全般に共通する [OS](/glossary/os/) 内[ファイアウォール](/glossary/ファイアウォール/)の操作方法として書かれています。[Docker](/glossary/docker/) が公開する[ポート](/glossary/ポート/)に関しては、上記の [Docker](/glossary/docker/) 側の仕様と合わせて読む必要があります。

なお、swap の設定、プライベートネットワークと [Docker](/glossary/docker/) の既定アドレス帯の衝突、IPv6 固有の挙動については、本記事では確認できていないため扱いません。

## 切り分けの順序

1. 対象の[ポート](/glossary/ポート/)が [Docker](/glossary/docker/) の `-p` で公開されたものかどうかを確認する。そうでなければ ufw の話として扱える。
2. `docker ps` で、公開の指定に待ち受けアドレスが含まれているかを見る。`0.0.0.0` から始まっていれば全体へ公開している。
3. `sudo ufw status verbose` を確認する。ここに出るのは ufw が管理する規則だけだと理解したうえで読む。
4. コントロールパネルで、対象[サーバー](/glossary/サーバー/)に割り当てられているセキュリティグループを確認する。
5. 外部から接続できない場合は、まず4のグループに必要な[ポート](/glossary/ポート/)が含まれるかを見る。
6. 80番と443番以外であれば、独自のセキュリティグループを追加する必要がある。
7. 外部公開が不要な[ポート](/glossary/ポート/)については、公開の指定を `127.0.0.1` へ限定する。
8. ホスト側でも制限が必要な場合に限り、`DOCKER-USER` チェーンの利用を検討する。

## 確認コマンド集

```bash
# 1. 公開されているポートと待ち受けアドレスを一覧する（最初に行う）
docker ps --format '{{.Names}}\t{{.Ports}}'

# 2. ホスト上で実際に待ち受けている宛先を確認する
sudo ss -ltnp

# 3. ufw が管理している規則を確認する（Docker の公開ポートは含まれない）
sudo ufw status verbose

# 4. Docker が作った転送用の規則を確認する
sudo iptables -t nat -L DOCKER -n

# 5. 利用者が追加できるチェーンの現在の内容を確認する
sudo iptables -L DOCKER-USER -n --line-numbers

# 6. Docker のバージョンを確認する（公開ポートの挙動が版で変わるため）
docker version --format '{{.Server.Version}}'

# 7. 特定のコンテナの公開設定だけを取り出す
docker inspect <コンテナ名> --format '{{json .NetworkSettings.Ports}}'

# 8. 外部からの到達性を、VPS の外にある別の端末から確認する
curl -sS -o /dev/null -w '%{http_code}\n' http://<VPSのIPアドレス>:8080/
```

## Editor's Note

この記事の内容は、2つの公式ドキュメントを突き合わせると読み取れます。どちらも単体では誤っていませんが、対象としている範囲が違います。

ConoHa 側の [Docker](/glossary/docker/) テンプレート解説は、最終更新が2026年2月25日です。[OS](/glossary/os/) 内の[ファイアウォール](/glossary/ファイアウォール/)設定として `ufw status verbose` での確認と `ufw allow 443` での開放を案内しています。これはテンプレート全般に共通する [OS](/glossary/os/) 内の操作方法の説明であり、[Docker](/glossary/docker/) が公開する[ポート](/glossary/ポート/)に限定した記述ではありません（[Docker｜ConoHaドキュメントサイト](https://doc.conoha.jp/products/vps-v3/image-v3/image-application-v3/docker-v3/)）。

[Docker](/glossary/docker/) 側のドキュメントは、[Docker](/glossary/docker/) と ufw が互いに相容れない使い方で規則を使うこと、公開された[コンテナ](/glossary/コンテナ/)宛の[通信](/glossary/通信/)が nat [テーブル](/glossary/テーブル/)で転送され ufw の INPUT と OUTPUT チェーンに届く前に迂回することを述べています（[Packet filtering and firewalls](https://docs.docker.com/engine/network/packet-filtering-firewalls/)）。

この性質は、以前から繰り返し報告されてきたものです。[Docker](/glossary/docker/) の開発[リポジトリ](/glossary/リポジトリ/)には2014年3月18日に [docker and ufw serious problems](https://github.com/moby/moby/issues/4737) という報告が出ています。報告者は[受信](/glossary/受信/)を既定で拒否する設定にしていたにもかかわらず、[Docker](/glossary/docker/) がホストへ割り当てた[ポート](/glossary/ポート/)へ外部から到達できた、と述べています。この報告は完了として閉じられています。

同じ内容が2021年6月24日に [Docker does not honor ufw rules.](https://github.com/moby/moby/issues/42563) として改めて提起され、こちらは現在も開いたままです。提起者はこれを繰り返し起きる落とし穴だと書き、先の2014年の報告を参照しています。仕様の説明としてだけでなく、長期にわたって同じ行き違いが起きてきた点も踏まえて読んでください。

したがって、ConoHa の手順に従って ufw を設定した状態でも、[Docker](/glossary/docker/) で公開した[ポート](/glossary/ポート/)については `ufw allow` だけでは制御できません。読み替えとしては、ufw の操作は [Docker](/glossary/docker/) を経由しない[通信](/glossary/通信/)に対する設定として扱い、[Docker](/glossary/docker/) の公開[ポート](/glossary/ポート/)については公開の指定とセキュリティグループの側で考える、という分け方になります。

なお、実際にどの[通信](/glossary/通信/)が到達するかは、外側のセキュリティグループ、[OS](/glossary/os/) 内の各種規則、[Docker](/glossary/docker/) が作る規則といった複数の層で決まります。本記事は公式ドキュメントの記述にもとづく整理であり、個別の[環境](/glossary/環境/)での挙動を確認したものではありません。構成を変更する際は、変更前の状態を控えたうえで、限定した範囲から試してください。

<a href="https://px.a8.net/svt/ejp?a8mat=4BA1PB+5QLFOY+50+4Z0M6A" rel="nofollow">ConoHa VPSのDockerテンプレートと料金を公式サイトで確認する（PR）</a>
<img border="0" width="1" height="1" src="https://www17.a8.net/0.gif?a8mat=4BA1PB+5QLFOY+50+4Z0M6A" alt="">

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
