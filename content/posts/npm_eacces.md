---
title: "npm の EACCES エラー：原因と解決策"
date: 2026-08-07
description: "npm は EACCES の文面を2種類に出し分けており、書き込もうとした場所がキャッシュ配下かどうかで文言が変わるため、どちらが出ているかを読めば直す対象が所有者か権限かに二分できます。"
tags: ["npm"]
images: ["og/posts/npm_eacces.png"]
errorCode: "EACCES"
lastmod: 2026-08-07
service: "npm"
error_type: "EACCES"
components: ["npm CLI", "cacache"]
related_services: ["Node.js", "Docker"]
trend_incident: false
---

## 結論

`npm ERR! code EACCES` は、[OS](/glossary/os/) が書き込みや読み取りを拒んだという意味です。npm 自身の判断ではなく、システムコールが返した値がそのまま[コード](/glossary/コード/)になっています。

重要なのは、npm がこの[エラー](/glossary/エラー/)に対して2種類の文面を用意している点です。実装では、失敗した経路または書き込み先が[キャッシュ](/glossary/キャッシュ/)の置き場から始まっていて、かつ Windows でない場合にだけ、[キャッシュ](/glossary/キャッシュ/)の所有者を直す案内を出します。それ以外は、[OS](/glossary/os/) に拒まれたという汎用の文面になります。

つまり文面を読めば、直す対象が二分できます。[キャッシュ](/glossary/キャッシュ/)の所有者の話なのか、書き込み先そのものの[権限](/glossary/権限/)の話なのか、という分かれ方です。

`sudo` を付けて回避するのは勧められません。多くの場合、それが次回以降の失敗の原因を作ります。root で作られた[ファイル](/glossary/ファイル/)が[キャッシュ](/glossary/キャッシュ/)に残り、通常の利用者では触れなくなるためです。

## エラーが発生する処理段階

npm の処理は大きく3段階に分かれます。どの段階で拒まれたかで、疑う場所が変わります。

第一段階は[キャッシュ](/glossary/キャッシュ/)への読み書きです。取得した[パッケージ](/glossary/パッケージ/)の内容は[キャッシュ](/glossary/キャッシュ/)の置き場に[保存](/glossary/保存/)されます。既定の場所は、POSIX 系が `~/.npm`、Windows が `%LocalAppData%\npm-cache` です。

第二段階は導入先への展開です。通常の導入なら作業[ディレクトリ](/glossary/ディレクトリ/)の `node_modules`、全体向けの導入なら `prefix` の下です。公式の説明によれば、全体向けの導入では[パッケージ](/glossary/パッケージ/)が `{prefix}/lib/node_modules` に置かれ、実行[ファイル](/glossary/ファイル/)が `{prefix}/bin` に、説明書が `{prefix}/share/man` にそれぞれ結び付けられます。

第三段階は導入後の[スクリプト](/glossary/スクリプト/)実行です。ここで失敗する場合、拒まれているのは npm ではなく[スクリプト](/glossary/スクリプト/)が触ろうとした場所です。

`npm ERR! path` と `npm ERR! syscall` の2行が、どの段階かを教えてくれます。

## 最初に確認すること

まず、拒まれた経路と操作を出力から読み取ります。

```text
npm ERR! code EACCES
npm ERR! syscall mkdir
npm ERR! path /usr/local/lib/node_modules/typescript
npm ERR! errno -13
npm ERR! Error: EACCES: permission denied, mkdir '/usr/local/lib/node_modules/typescript'
```

`path` がどこを指しているかで、次に見る場所が決まります。[キャッシュ](/glossary/キャッシュ/)の置き場の下なら原因1、`prefix` の下なら原因2、作業[ディレクトリ](/glossary/ディレクトリ/)の下なら原因3です。

その3つの場所を、実際の値で確認します。

```bash
npm config get cache
npm config get prefix
pwd
```

次に、その場所の所有者と[権限](/glossary/権限/)を見ます。

```bash
ls -ld "$(npm config get cache)" "$(npm config get prefix)/lib/node_modules"
```

所有者が `root` になっていて、自分が root でないなら、そこが原因です。所有者は自分でも[権限](/glossary/権限/)の欄に書き込みが無い場合は、[権限](/glossary/権限/)の側の問題になります。

## 原因別の確認方法と解決策

### 原因1：キャッシュ配下が root 所有になっている

過去に `sudo npm` を実行したことがあると起きます。root で作られた[ファイル](/glossary/ファイル/)が[キャッシュ](/glossary/キャッシュ/)に残り、以後の通常実行が拒まれます。

この場合、npm は専用の文面を出します。実行中の利用者番号を埋め込んだ復旧[コマンド](/glossary/コマンド/)まで示されます。

```text
npm ERR! Your cache folder contains root-owned files, due to a bug in previous versions of npm which has since been addressed.
npm ERR!
npm ERR! To permanently fix this problem, please run:
npm ERR!   sudo chown -R 1000:1000 "/home/user/.npm"
```

確認方法は、root 所有の[ファイル](/glossary/ファイル/)が残っているかどうかです。

```bash
find "$(npm config get cache)" ! -user "$(id -un)" -print -quit
```

1行でも出力されれば該当します。対処は所有者の付け替えです。npm が示した[コマンド](/glossary/コマンド/)をそのまま使えます。

```bash
sudo chown -R "$(id -u):$(id -g)" "$(npm config get cache)"
```

対象が[キャッシュ](/glossary/キャッシュ/)の置き場に限られていることを確認してから実行してください。`npm config get cache` の値が空だったり想定と違ったりする状態で流すと、範囲が広がります。

### 原因2：全体向けの導入先に書き込めない

`npm install -g` で起きる最も多い形です。`prefix` の既定値は、公式の説明によれば node の実行[ファイル](/glossary/ファイル/)が置かれている[ディレクトリ](/glossary/ディレクトリ/)です。多くの[環境](/glossary/環境/)では `/usr/local` になり、通常の利用者には書き込めません。

確認方法は導入先の[権限](/glossary/権限/)です。

```bash
ls -ld "$(npm config get prefix)/lib/node_modules"
```

対処は2通りあります。安全なのは、書き込める場所を `prefix` に指定する方法です。

```bash
mkdir -p "$HOME/.npm-global"
npm config set prefix "$HOME/.npm-global"
```

このあと `$HOME/.npm-global/bin` を実行経路に加えてください。加えないと、導入した[コマンド](/glossary/コマンド/)が見つかりません。

```bash
export PATH="$HOME/.npm-global/bin:$PATH"
```

もう1つは、node 自体を利用者の領域に入れ直す方法です。版を切り替える道具を使えば、node と npm が最初から利用者の所有になるため、この[エラー](/glossary/エラー/)は起きなくなります。

`sudo npm install -g` は避けてください。導入は成功しますが、[キャッシュ](/glossary/キャッシュ/)に root 所有の[ファイル](/glossary/ファイル/)が残り、原因1を作ります。

### 原因3：作業ディレクトリの所有者が実行利用者と違う

[コンテナ](/glossary/コンテナ/)や CI で起きます。ホスト側の[ディレクトリ](/glossary/ディレクトリ/)を[コンテナ](/glossary/コンテナ/)に持ち込むと、番号だけが引き継がれます。ホスト側の所有者番号と[コンテナ](/glossary/コンテナ/)内の実行利用者の番号が違えば、書き込めません。

確認方法は、両側の番号の突き合わせです。

```bash
id -u
ls -ldn node_modules
```

`ls -ldn` は番号のまま表示するので、名前が解決できない[環境](/glossary/環境/)でも比較できます。値が一致していなければ、これが原因です。

対処は、実行する利用者の番号をホスト側に合わせることです。

```yaml
services:
  app:
    image: node:22
    user: "1000:1000"
```

所有者を変える方法もありますが、持ち込み元のホスト側にも影響します。どちらを変えてよいかを確認してから選んでください。

### 原因4：導入後のスクリプトが別の場所へ書こうとしている

`path` が[キャッシュ](/glossary/キャッシュ/)でも `prefix` でも作業[ディレクトリ](/glossary/ディレクトリ/)でもない場合です。[パッケージ](/glossary/パッケージ/)の導入後[スクリプト](/glossary/スクリプト/)が、システムの領域や他の利用者の領域に書こうとしています。

確認方法は、[スクリプト](/glossary/スクリプト/)を止めて切り分けることです。

```bash
npm install --ignore-scripts
```

これで通るなら、失敗しているのは導入そのものではなく[スクリプト](/glossary/スクリプト/)です。対処は、その[パッケージ](/glossary/パッケージ/)が何をしようとしているかを確認したうえで判断することになります。書き込み先を設定で変えられる場合が多くあります。

`--ignore-scripts` を恒久的な設定にすると、正常に必要な[スクリプト](/glossary/スクリプト/)も動かなくなります。切り分けの手段として使ってください。

## 近いエラーとの境界

`EPERM` は、実装上 `EACCES` と同じ分岐で処理されます。文面もほぼ同じで、Windows の場合だけ2行目が変わり、[ファイル](/glossary/ファイル/)が編集用の道具や[ウイルス](/glossary/ウイルス/)対策の常駐によって使用中である可能性に触れます。Windows で出ている場合は、[権限](/glossary/権限/)ではなく[ファイル](/glossary/ファイル/)の使用中を先に疑ってください。

Windows では、[キャッシュ](/glossary/キャッシュ/)配下であっても所有者を直す案内は出ません。実装の条件に Windows の除外が入っているためです。

`EROFS` は書き込み先が読み取り専用の場合、`ENOSPC` は[容量](/glossary/容量/)が足りない場合です。いずれも[権限](/glossary/権限/)とは別で、所有者を変えても解消しません。

`E401` は、[パッケージ](/glossary/パッケージ/)の置き場に対する[認証](/glossary/認証/)の失敗です。[ファイル](/glossary/ファイル/)の[権限](/glossary/権限/)ではなく、通信相手に対する[認証](/glossary/認証/)の話になります。

## 内部動作または公式仕様

npm の文面を組み立てる処理は、`EACCES` と `EPERM` を同じ分岐で扱います。分岐の中で最初に判定するのが、失敗した経路が[キャッシュ](/glossary/キャッシュ/)配下かどうかです。[エラー](/glossary/エラー/)[オブジェクト](/glossary/オブジェクト/)の `path` と `dest` のいずれかが、設定されている[キャッシュ](/glossary/キャッシュ/)の値で始まっているかを見ます。

その条件に加えて、実行中の[環境](/glossary/環境/)が Windows でないことが求められます。両方を満たしたときだけ、[キャッシュ](/glossary/キャッシュ/)に root 所有の[ファイル](/glossary/ファイル/)が残っているという説明と、所有者を直す[コマンド](/glossary/コマンド/)が出ます。[コマンド](/glossary/コマンド/)に入る番号は、実行中の処理から取得した利用者番号と集団番号です。

条件を満たさない場合は汎用の文面になります。[OS](/glossary/os/) に拒まれたという1文と、現在の利用者ではこの[ファイル](/glossary/ファイル/)に触れられない可能性が高いという説明、そして[ファイル](/glossary/ファイル/)とその上位[ディレクトリ](/glossary/ディレクトリ/)の[権限](/glossary/権限/)を確認するか、管理者として実行し直すようにという案内です。

設定の既定値も押さえておきます。[キャッシュ](/glossary/キャッシュ/)の置き場は、公式の説明によれば Windows が `%LocalAppData%\npm-cache`、POSIX 系が `~/.npm` です。`prefix` は、全体向けの動作では node の実行[ファイル](/glossary/ファイル/)が置かれている[ディレクトリ](/glossary/ディレクトリ/)が既定になります。

## バージョン差・注意点

古い手順で見かける `--unsafe-perm` は、現在の npm には存在しません。npm 6 の設定定義には確かに含まれており、Windows か cygwin か、あるいは実行者が root でない場合に真になる作りでした。しかし npm 7.0.0 の設定定義には既に含まれておらず、8 系にも最新版にもありません。`sudo npm install -g --unsafe-perm` という指示を見かけても、現在の npm では設定として認識されません。

[キャッシュ](/glossary/キャッシュ/)の文面にある「以前の版の不具合」という表現にも注意が必要です。不具合そのものは修正済みですが、当時作られた root 所有の[ファイル](/glossary/ファイル/)は自動では消えません。そのため、修正後の npm を使っていても、過去に作られた[ファイル](/glossary/ファイル/)が残っていれば同じ文面が出ます。npm を更新しても解消しないのはこのためです。

`sudo` での回避は、その場は通っても後で効いてきます。root で導入した結果として[キャッシュ](/glossary/キャッシュ/)に root 所有の[ファイル](/glossary/ファイル/)が増え、次に通常の利用者で実行したときに原因1の状態になります。

## Editor's Note

`--unsafe-perm` の廃止は、この[エラー](/glossary/エラー/)の対処法を調べるときに引っかかる点です。npm 7.0.0 は2020年10月12日に公開されており、この版の設定定義には既に `unsafe-perm` が含まれていません。

当時の状態としては、npm 6 系が広く使われており、root で実行したときに[スクリプト](/glossary/スクリプト/)の実行[権限](/glossary/権限/)を落とす挙動があったため、それを無効にする設定として `--unsafe-perm` が使われていました。実装を見ると、Windows か cygwin の場合、利用者番号を扱う機能が使えない場合、あるいは実行者が root でない場合に既定で真になる形でした。裏返せば、root で実行したときだけ既定で偽になり、そこで問題が起きていたわけです。

現在も適用できるかという点では、適用できません。npm 6 は既に保守が終わっており、7 以降の設定定義にこの項目はありません。したがって、いま `--unsafe-perm` を含む手順を見つけた場合、それは npm 6 以前を前提にした情報です。同じ記事に書かれている他の対処も、古い前提のままである可能性を疑ってください。

現在の推奨は、[権限](/glossary/権限/)を緩めるのではなく、書き込める場所を使うことです。`prefix` を利用者の領域に移すか、node 自体を利用者の所有で入れ直すかのどちらかになります。

## 参考資料

- [Resolving EACCES permissions errors when installing packages globally](https://docs.npmjs.com/resolving-eacces-permissions-errors-when-installing-packages-globally)
- [npm config（cache、prefix、global）](https://docs.npmjs.com/cli/latest/using-npm/config)
- [npm フォルダ構成](https://docs.npmjs.com/cli/latest/configuring-npm/folders)
- [エラー文面の生成（error-message.js）](https://github.com/npm/cli/blob/latest/lib/utils/error-message.js)
- [設定定義（definitions.js）](https://github.com/npm/cli/blob/latest/workspaces/config/lib/definitions/definitions.js)
- [npm 7.0.0 の変更履歴](https://github.com/npm/cli/blob/v7.0.0/CHANGELOG.md)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*