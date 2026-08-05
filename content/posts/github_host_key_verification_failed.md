---
title: "GitHub の Host key verification failed：原因と解決策"
date: 2026-08-03
description: "この文言を出しているのは GitHub ではなく SSH クライアントで、意味は相手が本人だと確認できなかったということです。記録に無い場合と、記録と違う場合の2系統に分かれます。GitHub は鍵の指紋を公開しているため、突き合わせれば正当な交換か異常かを自分で判断できます。"
tags: ["GitHub"]
images: ["og/posts/github_host_key_verification_failed.png"]
errorCode: "Host key verification failed"
lastmod: 2026-08-03
service: "GitHub"
error_type: "Host key verification failed"
components: ["SSH", "Git"]
related_services: ["GitHub Actions", "OpenSSH"]
trend_incident: false
---

## 冒頭まとめ

`Host key verification failed.` を出しているのは GitHub ではありません。**手元の SSH [クライアント](/glossary/クライアント/)**です。意味は「接続先が名乗っている身元を、こちらでは確認できなかった」ということです。

[認証](/glossary/認証/)の失敗ではない点に注意してください。鍵が正しいかを問う以前の段階で、**相手が本物の github.com かどうか**を確かめています。

実装を読むと、この段階には2つの分岐があります。1つは**記録に無い場合**です。相手の鍵を初めて見たとき、対話できる環境なら「この接続先の真正性を確認できません」と表示して確認を求めます。**対話できない環境では、確認のしようがないので失敗します**。自動処理や[コンテナ](/glossary/コンテナ/)の中でこの[エラー](/glossary/エラー/)が出るのは、ほぼこの形です。

もう1つは**記録と違う場合**です。この場合は大きな警告が出ます。実装では「接続先の識別情報が変わった」という囲み枠に加えて、記録の何行目が該当するかまで表示されます。

そして重要なのは、**この警告は「攻撃かもしれない」と「正当な鍵の交換かもしれない」の両方を意味する**ことです。どちらかを判断するのは利用者の側です。判断材料はあります。GitHub は接続先の鍵の指紋を文書として公開し、[API](/glossary/api/) からも配信しています。**突き合わせれば、自分で判断できます**。

## エラーの概要

記録に無い場合、対話できる環境ではこう表示されます。

```text
The authenticity of host 'github.com (140.82.x.x)' can't be established.
ED25519 key fingerprint is SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU.
Are you sure you want to continue connecting (yes/no/[fingerprint])?
```

対話できない環境では確認が省略され、そのまま次の文言で終わります。

```text
Host key verification failed.
fatal: Could not read from remote repository.
```

記録と違う場合は、囲み枠付きの警告になります。

```text
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@    WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!     @
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
...
Add correct host key in /home/user/.ssh/known_hosts to get rid of this message.
Offending RSA key in /home/user/.ssh/known_hosts:12
Host key verification failed.
```

**`Offending` の行に、記録[ファイル](/glossary/ファイル/)の何行目が該当するかが書かれています**。この番号があれば、消すべき行が特定できます。

なお、後半の「読み取れませんでした」は Git 側の文言です。**原因は常に前半にあります**。

## まず最初に：どちらの系統かを判別する

第一に、囲み枠の警告があるかを見ます。**あれば記録との不一致、無ければ記録に無い**、という判別ができます。

第二に、記録に無い形であれば、対話できない環境かどうかを確認します。自動処理や[コンテナ](/glossary/コンテナ/)なら、それが原因です。

第三に、不一致の形であれば、**実際の指紋を公開値と突き合わせます**。ここが判断の分かれ目です。

第四に、`Offending` の行番号を控えます。対処の際に使います。

## よくある原因と解決手順

### 原因1：記録に無く、確認もできない（自動処理・コンテナ）

最も多い形です。手元では通るのに、自動処理の中では失敗します。**手元には過去に確認した記録が残っているから**です。

**Before（記録の用意を省く）：**

```bash
git clone git@github.com:org/repo.git   # → Host key verification failed.
```

**After（公開されている鍵を、指紋を確認したうえで登録する）：**

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
ssh-keyscan -t ed25519 github.com > /tmp/gh.pub

# 取得した鍵の指紋を確認する（公開値と一致するか）
ssh-keygen -lf /tmp/gh.pub
# → SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU が公開値

cat /tmp/gh.pub >> ~/.ssh/known_hosts
chmod 600 ~/.ssh/known_hosts
```

ここで**指紋の確認を省かない**ことが要点です。取得結果をそのまま追記する手順は広く出回っていますが、それでは「初めて会った相手を無条件に信用する」ことになり、この仕組みの意味が失われます。

GitHub が公開している指紋は次のとおりです。

```text
SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU  (Ed25519)
SHA256:p2QAMXNIC1TJYWeIOttrVc98/R1BUFWu3/LiyKgUfQM  (ECDSA)
SHA256:uNiVztksCsDhcc0u9e8BujQXVUpKZIDTMczCvj3tD2s  (RSA)
```

### 原因2：記録と実際の鍵が違う

囲み枠の警告が出る形です。**まず落ち着いて、指紋を突き合わせてください**。

```bash
ssh-keyscan -t rsa,ecdsa,ed25519 github.com 2>/dev/null | ssh-keygen -lf -
```

公開値と一致すれば、相手は本物です。記録のほうが古いので、該当行を消して入れ直します。

```bash
ssh-keygen -R github.com          # 該当のエントリを削除する
ssh -T git@github.com             # 再確認のうえ登録する
```

一致しなければ、**そこで止めてください**。経路上に別の相手がいる可能性があります。回線、中継の設定、名前解決を確認するまで接続を続けないのが原則です。

実際に、GitHub が鍵を交換したことがあります。後述しますが、そのときは世界中で同じ警告が出ました。**警告そのものは正しく、しかも危険ではなかった**という事例です。判断材料を持っているかどうかで、対応の速さがまったく変わります。

### 原因3：同じ名前で別の接続先を指している

設定によって、`github.com` という名前が別の場所へ向いている場合です。社内の中継[サーバー](/glossary/サーバー/)を経由する構成や、別名を定義している場合に起こります。

```bash
# 実際に使われる設定を展開して確認する
ssh -G github.com | grep -iE "^hostname|^port|^user|^proxycommand|^userknownhostsfile"
```

`hostname` が想定と違えば、記録と食い違って当然です。設定[ファイル](/glossary/ファイル/)の別名定義を確認してください。

### 原因4：記録ファイルを読み書きできない

記録[ファイル](/glossary/ファイル/)が存在しない、権限が無い、あるいは想定と違う場所を見ている場合です。[コンテナ](/glossary/コンテナ/)の中や、実行利用者が切り替わる環境で起こります。

```bash
# どのファイルを見ているかを確認する
ssh -G github.com | grep -i userknownhostsfile
# 実行時の利用者と home の位置を確認する
id; echo "$HOME"; ls -ld ~/.ssh ~/.ssh/known_hosts
```

`HOME` が設定されていない環境では、記録の場所そのものが定まりません。**利用者を切り替えて実行する構成では、切り替え後の利用者の記録が使われます**。

### 原因5：検証を無効にして「解決」してしまう

広く出回っている回避策があります。厳格な確認を切る指定や、記録[ファイル](/glossary/ファイル/)を捨てる指定です。

```bash
# 推奨しない
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null git@github.com
```

この[エラー](/glossary/エラー/)は確かに消えます。しかし、**消えるのは[エラー](/glossary/エラー/)だけでなく、相手が本物かを確かめる仕組みそのもの**です。原因1で述べたとおり、自動処理では「公開値と照合したうえで鍵を固定する」のが正しい対処です。手間はほとんど変わりません。

なお、SSH ではなく HTTPS で接続する構成に変えるという選択肢もあります。その場合、接続先の確認は証明書の仕組みが担うため、この[エラー](/glossary/エラー/)自体が発生しません。自動処理でトークンを使うなら、こちらのほうが管理は簡単です。

## 補足：似ているが別のもの

鍵は登録されているのに拒否される場合は、[認証](/glossary/認証/)の失敗です。文言は「公開鍵での接続を拒否された」という趣旨になります（[GitHub の Permission denied (publickey) の記事](/posts/github_permission_denied_publickey/)）。**接続先の身元確認と、自分の身元証明は別の段階**です。

前者に失敗すると、後者には進みません。したがって、この[エラー](/glossary/エラー/)が出ているときに自分の鍵を作り直しても意味がありません。

自動実行の仕組みで既定の取得方法を使っている場合、通信は HTTPS で行われるため、この[エラー](/glossary/エラー/)は出ません。出るのは、部分的な取り込みや配備の手順で SSH のアドレスを使っている場合です。

## 切り分けの順序

1. 囲み枠の警告があるかを見る。あれば不一致、無ければ記録に無い。
2. 記録に無い形なら、対話できない環境かを確認する。自動処理では必ず失敗する。
3. 不一致の形なら、実際の指紋を公開値と突き合わせる。ここで判断する。
4. 一致すれば該当行を消して入れ直す。一致しなければ接続を止める。
5. `Offending` の行番号を使う。消すべき行が特定できる。
6. 接続先が想定どおりかを設定の展開で確認する。
7. 記録[ファイル](/glossary/ファイル/)の場所と権限、実行利用者を確認する。
8. 検証を切る回避策は使わない。公開値との照合で固定する。

## 確認コマンド集

```bash
# 1. 接続を試して、どちらの系統かを見る
ssh -T git@github.com

# 2. 実際の指紋を取得して公開値と突き合わせる
ssh-keyscan -t rsa,ecdsa,ed25519 github.com 2>/dev/null | ssh-keygen -lf -

# 3. 記録に入っている内容を確認する
ssh-keygen -F github.com

# 4. 記録から該当のエントリを削除する
ssh-keygen -R github.com

# 5. 実際に使われる設定を展開して確認する
ssh -G github.com | grep -iE "^hostname|^port|^proxycommand|^userknownhostsfile|^stricthostkeychecking"

# 6. 記録ファイルの場所と権限、実行利用者を確認する
id; echo "$HOME"; ls -ld ~/.ssh ~/.ssh/known_hosts

# 7. 詳しい経過を出して、どの段階で止まったかを見る
ssh -vT git@github.com 2>&1 | grep -iE "known_hosts|host key|fingerprint"

# 8. 公開されている鍵を API から取得する（自動処理での固定に使う）
curl -sS https://api.github.com/meta \
  | python3 -c "import json,sys; d=json.load(sys.stdin); [print('github.com', k) for k in d.get('ssh_keys', [])]"
```

## Editor's Note

囲み枠の警告を見たとき、多くの人は「攻撃かもしれない」と「またこれか」の間で揺れます。**実際に、世界中で一斉にこの警告が出た日があります**。

2023年3月24日、GitHub は RSA の接続先鍵を交換しました（[We updated our RSA SSH host key](https://github.blog/news-insights/company-news/we-updated-our-rsa-ssh-host-key/)）。公表された理由は明確です。GitHub.com の RSA の秘密鍵が、公開の[リポジトリ](/glossary/リポジトリ/)内に短時間さらされていたことを発見したため、封じ込めのうえ交換した、というものでした。

同時に、範囲も明示されています。交換されたのは RSA のみで、ECDSA と Ed25519 を使っている利用者には変更も対応も不要。そして、**この件は GitHub の設備や利用者情報が侵害された結果ではない**とも書かれています。

この日、RSA を使っていた利用者の画面には、あの囲み枠が出ました。文言のとおり「接続先の識別情報が変わった」のであり、警告としては完全に正しい。しかし危険ではなかった。**両者を区別する手段は、公開されている指紋との照合しかありません**。

ここに、この仕組みの本質があります。SSH は「以前と同じ相手か」しか判断できません。相手が本物かどうかを決めるのは、外部の情報源と突き合わせる利用者の側です。GitHub が指紋を文書で公開し、[API](/glossary/api/) でも配信しているのは、そのためです。

だからこそ、確認を省いて記録に追記する手順や、検証そのものを切る回避策は、この設計を無効化します。**自動処理でも、公開値と照合して鍵を固定する**。手順としてはほんの数行の違いですが、意味はまったく違います。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*