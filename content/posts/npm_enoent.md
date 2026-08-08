---
title: "npm の ENOENT エラー：原因と解決策"
date: 2026-08-08
description: "ENOENT は何かが見つからないとしか言っていないため、npm が併記する syscall と path と file と dest の4項目で対象を特定してから、どの原因に当たるかを判断します。"
tags: ["npm"]
images: ["og/posts/npm_enoent.png"]
errorCode: "ENOENT"
error_name: "ENOENT: no such file or directory"
error_aliases:
  - "npm error code ENOENT"
  - "npm ERR! code ENOENT"
  - "no such file or directory"
  - "enoent This is related to npm not being able to find a file"
lastmod: 2026-08-08
service: "npm"
error_type: "ENOENT"
components: ["npm CLI", "Node.js"]
related_services: ["Git", "Docker"]
error_cases:
  - id: "package-json-missing"
    situation: "npm install や npm run を実行したが、そのディレクトリがプロジェクトの直下ではない"
    messages:
      - "npm error syscall open"
      - "npm error path <path>/package.json"
      - "ENOENT: no such file or directory, open '<path>/package.json'"
    cause: "カレントディレクトリに package.json が無い可能性がある"
    check: "path 行に出ているディレクトリと、pwd の出力を見比べる。package.json のある場所と一致しているかを確認する"
    fix: "package.json のあるディレクトリへ移動してから実行し直す"
  - id: "container-workdir-mismatch"
    situation: "手元では成功するが、Docker や Docker Compose から起動したときだけ失敗する"
    messages:
      - "npm error syscall open"
      - "npm error path /app/package.json"
      - "ENOENT: no such file or directory, open '/app/package.json'"
    cause: "作業ディレクトリが実行時に別の内容で覆われ、構築時に置いた package.json が見えなくなっている可能性がある"
    check: "同じコンテナの中で ls を実行し、package.json が実在するかを確認する。実在しなければ、その経路に割り当てている設定を確認する"
    fix: "作業ディレクトリを覆っている設定を外すか、割り当て元に package.json が含まれる状態にする"
  - id: "git-not-installed"
    situation: "レジストリからの取得は通るが、git の場所を指定した依存だけで失敗する"
    messages:
      - "npm error syscall spawn git"
      - "npm error path git"
      - "ENOENT: no such file or directory, spawn git"
    cause: "git の実行ファイルが検索パス上に無い可能性がある"
    check: "path 行が package.json ではなく git になっていることを確認し、git --version が実行できるかを試す"
    fix: "実行環境に git を導入するか、検索パスに含める"
  - id: "node-modules-incomplete"
    situation: "前回の導入を途中で中断した、あるいは容量不足で終わったあとに実行すると失敗する"
    messages:
      - "npm error syscall open"
      - "npm error path <path>/node_modules/<package>/package.json"
      - "ENOENT: no such file or directory, open '<path>/node_modules/<package>/package.json'"
    cause: "導入が途中で終わり、node_modules の中身が不完全なまま残っている可能性がある"
    check: "path 行に出ているディレクトリを直接開き、package.json が実在するかを確認する"
    fix: "node_modules を作り直す。記録ファイルはそのまま残し、まず再導入だけを試す"
  - id: "file-dependency-path-missing"
    situation: "package.json に file: 指定やワークスペースの参照があり、複製した直後や経路を変更した直後に失敗する"
    messages:
      - "npm error syscall open"
      - "npm error path <path>/package.json"
      - "ENOENT: no such file or directory, open '<path>/package.json'"
    cause: "file: 指定やワークスペースが参照している場所が存在しない可能性がある"
    check: "path 行のディレクトリが、自分の package.json に書いた file: の参照先や workspaces の対象と一致するかを確認する"
    fix: "参照先の経路を実在するものへ直すか、参照先のディレクトリを用意する"
trend_incident: false
---

## 結論

`npm error code ENOENT` は、何かが見つからなかったという意味です。npm が加える説明も2文しかありません。「npm がファイルを見つけられないことに関係している」と述べ、`file` の値がある場合だけ「そのファイルが存在するか確認してください」と続きます。

したがって、原因を絞る材料は説明文ではなく、npm が併記する診断用の項目にあります。実装では `code`、`syscall`、`file`、`path`、`dest`、`errno` の6つのうち、値が入っているものだけを並べて出力します。このうち `syscall` が何をしようとして失敗したか、`path` がどこで失敗したかを示します。

読み方は単純です。`syscall` が `open` で `path` が `package.json` で終わっていれば、そのディレクトリにプロジェクトの定義が無いという意味になります。`syscall` が `spawn git` であれば、ファイルではなく外部コマンドが見つかっていません。`path` が `node_modules` の下を指していれば、導入済みのはずの中身が欠けています。

この2項目を見ないまま `npm install` を繰り返しても状況は変わりません。まず対象を特定してください。

## エラーが発生する処理段階

npm の処理は段階に分かれており、`ENOENT` はどの段階でも起こります。ただし失敗した対象を見れば段階は特定できます。

第一段階はプロジェクトの読み取りです。npm はカレントディレクトリから `package.json` を探します。ここで見つからなければ、依存の解決にも取得にも進みません。

第二段階は依存の解決です。レジストリからの取得だけであれば外部コマンドは不要ですが、git の場所を指定した依存が含まれる場合、npm は `git` を起動します。この起動に失敗すると `syscall` が `spawn git` になります。

第三段階は取得と展開で、`node_modules` の下に書き込みます。前回の実行が途中で終わっていると、この段階の読み取りで欠けた対象に当たります。

第四段階は導入後のスクリプト実行です。ここで外部コマンドが見つからない場合も、同じ形の失敗になります。

段階が違えば `path` の指す場所も変わります。逆に言えば、`path` を見れば段階が分かります。

## 最初に確認すること

まず、出力の診断用の行だけを抜き出します。

```bash
npm install 2>&1 | grep -E "npm error (code|syscall|path|file|dest|errno)"
```

出力はこの形になります。

```text
npm error code ENOENT
npm error syscall open
npm error path /home/user/package.json
npm error errno -2
npm error enoent ENOENT: no such file or directory, open '/home/user/package.json'
npm error enoent This is related to npm not being able to find a file.
```

`syscall` と `path` の2行で、以降の見方が決まります。`path` が `package.json` で終わるなら原因1から原因2、`spawn` を含むなら原因3、`node_modules` を含むなら原因4です。

次に、`path` の指す場所を直接確認します。

```bash
ls -la "$(dirname "<path 行に出た経路>")"
```

存在しないのか、存在するが読めないのかで分かれます。読めない場合は `ENOENT` ではなく `EACCES` になるため、`ENOENT` が出ている時点で対象は存在していません。

## 原因別の確認方法と解決策

### 原因1：カレントディレクトリに package.json が無い {#package-json-missing}

最も多い形です。`syscall` が `open`、`path` が `package.json` で終わっています。

確認方法は経路の突き合わせです。`path` 行に出ているディレクトリと、いま自分がいる場所を見比べます。

```bash
pwd
ls -la package.json
```

`path` 行が `/home/user/package.json` のように、プロジェクトより上の階層を指していれば確定です。npm はカレントディレクトリを起点に探すため、1つ上の階層で実行しただけでもこの形になります。

対処は移動してから実行し直すことです。

```bash
cd /path/to/project
npm install
```

`npm init` で新しく作る方法もありますが、既存のプロジェクトで実行すると意図しない定義ファイルができます。まず場所を確認してください。

### 原因2：コンテナの中で作業ディレクトリが覆われている {#container-workdir-mismatch}

手元では成功するのに、コンテナから起動したときだけ失敗する場合です。表示される内容は原因1と同じなので、状況で区別します。

構築の段階で `package.json` を置いたのに、実行時にその経路へ別の内容を割り当てていると、置いたはずのファイルが見えなくなります。

確認方法は、実行時のコンテナの中を直接見ることです。

```bash
docker compose exec app sh -c 'pwd; ls -la'
```

`package.json` が無ければ確定です。対処は、その経路への割り当てを外すか、割り当て元に定義ファイルが含まれる状態にすることです。

```yaml
services:
  app:
    volumes:
      - .:/app
      - /app/node_modules
```

割り当て元が空のディレクトリになっていないかを、先に確認してください。

### 原因3：git の実行ファイルが見つからない {#git-not-installed}

`syscall` が `spawn git`、`path` が `git` になっている場合です。ファイルではなく外部コマンドが見つかっていません。

npm は依存の指定に git の場所が含まれる場合、`git` を起動して取得します。起動に失敗すると、npm が外部コマンドを起動する仕組みがそのまま失敗として返します。

確認方法は2つです。`path` 行が `package.json` ではなく `git` になっていることを確かめ、そのうえで実行できるかを試します。

```bash
git --version
```

見つからなければ確定です。対処は実行環境に git を導入するか、検索パスに含めることです。軽量なコンテナ画像では git が入っていないことが多く、この形になりやすくなります。

```dockerfile
RUN apk add --no-cache git
```

依存の指定を確認し、git の場所を指しているものがあるかも見ておいてください。

```bash
grep -n "git+" package.json
```

### 原因4：node_modules の中身が欠けている {#node-modules-incomplete}

`path` が `node_modules` の下を指している場合です。前回の実行が途中で終わった、容量が足りずに止まった、といった経緯で中身が不完全なまま残っています。

確認方法は、`path` 行のディレクトリを直接開くことです。

```bash
ls -la "<path 行に出た node_modules 配下の経路>"
```

ディレクトリごと無い場合と、ディレクトリはあるが `package.json` だけ無い場合があります。どちらも同じ対処になります。

対処は作り直しです。記録ファイルは残したまま、まず再導入だけを試してください。

```bash
rm -rf node_modules
npm install
```

これで解消しない場合に限り、記録ファイルの再生成を検討します。記録を消すと他の依存も新しい版へ動く可能性があるため、共同で開発している場合は差分を確認してから共有してください。

### 原因5：file 指定やワークスペースの参照先が存在しない {#file-dependency-path-missing}

`path` が `package.json` で終わっているのに、自分のプロジェクトの直下ではない場所を指している場合です。複製した直後や、ディレクトリの構成を変えた直後に起きます。

npm は `file:` で指定された依存やワークスペースの対象について、その場所の定義ファイルを読みに行きます。参照先が無ければ、そこで失敗します。

確認方法は、`path` 行の経路と自分の指定を突き合わせることです。

```bash
grep -n "\"file:" package.json
```

```bash
node -e "console.log(require('./package.json').workspaces || [])"
```

出力に含まれる経路と `path` 行が一致すれば確定です。対処は、指定を実在する経路へ直すか、参照先のディレクトリを用意することです。複数のリポジトリに分かれている構成では、参照先を先に取得しておく必要があります。

## 近いエラーとの境界

`EACCES` は対象が存在するのに読み書きできない場合です。npm は操作が OS に拒まれたと説明します。`ENOENT` が出ている時点で対象は存在していないため、所有者や権限を調べても解決しません。

`ENOSPC` は容量の不足です。npm は容量を空けて再実行するよう案内します。ただし容量不足で導入が途中で止まると、次の実行では原因4の形で `ENOENT` が出ます。前後関係で入れ替わる点に注意してください。

`EROFS` は読み取り専用のファイルシステムです。npm は記号リンクに対応していないファイルシステムでよく起きると説明します。

`EEXIST` は逆に、対象が既に存在する場合です。npm は既存のファイルを消して再実行するよう案内します。

外部コマンドが起動はしたが失敗した場合は `ENOENT` になりません。終了コードがそのまま `code` に入るため、`npm error code 1` のような表示になります。`spawn` を含む `ENOENT` は、起動そのものができなかった場合だけです。

## 内部動作または公式仕様

npm のエラー表示は、コードごとの分岐で本文を組み立て、そこへ診断用の項目を添える構成になっています。

診断用の項目は `code`、`syscall`、`file`、`path`、`dest`、`errno` の6つで固定です。実装はこの並びから値が入っているものだけを取り出して出力します。したがって、表示される行数はエラーごとに変わります。`file` が出ていれば、npm はその値を使って「そのファイルが存在するか確認してください」という一文を追加します。出ていなければ、説明は1文だけになります。

`ENOENT` の分岐そのものは、npm 6 の時代から変わっていません。実装を比べると、説明文も条件も同じです。つまり古い記事に載っている説明文は現在も同じで、違うのは接頭辞だけです。

`errno` の値も手がかりになります。`-2` は対象が存在しないことを表す番号で、`ENOENT` と対応します。この番号だけが違う場合は、別のコードが返っています。

`syscall` の値は npm が決めているのではなく、Node.js が失敗した呼び出しの名前をそのまま入れています。`open` はファイルを開こうとした、`spawn git` は `git` を起動しようとした、という意味です。npm 側で加工されないため、対象の特定に最も確実に使えます。

## バージョン差・注意点

出力の接頭辞が変わりました。現在の npm は `npm error` で始まります。実装では、見出しと段階名と表題を組み合わせて接頭辞を作る仕組みになっており、失敗時の段階名が `error` です。古い版は `npm ERR!` で始まっていました。

検索したときに `npm ERR! code ENOENT` と書かれた記事が出てきても、内容が古いとは限りません。前述のとおり `ENOENT` の分岐は npm 6 から変わっていないため、説明文の部分は現在も一致します。判断すべきは、対処として書かれている内容が現在の npm に当てはまるかどうかです。

`npm cache clean --force` を最初の対処として勧める記事が多くありますが、`ENOENT` の大半は取得の前の段階、つまり定義ファイルが見つからない段階で起きています。キャッシュを消しても `path` の指す対象は現れません。`path` 行がキャッシュの下を指している場合に限って検討してください。

`rm -rf node_modules package-lock.json` をまとめて実行する手順も広く共有されています。原因4では有効ですが、記録ファイルまで消すと依存の版が動きます。まず `node_modules` だけを作り直し、それで解消しなければ次を検討する、という順序が安全です。

## Editor's Note

`ENOENT` の説明文が長く変わっていないことは、記事を読むときの判断材料になります。実装を版ごとに比べると、npm 6 系の `lib/utils/error-message.js` にある `ENOENT` の分岐と、現在の同名ファイルにある分岐は、条件も文面も同じです。どちらも「npm がファイルを見つけられないことに関係している」と述べ、`file` の値があるときだけ確認を促す一文を足します。

当時の状態としては、npm 6 が広く使われていた時期に書かれた解説が数多く残っています。それらは `npm ERR!` で始まる出力を前提にしています。npm 6 の保守は既に終わっていますが、この分岐に限れば内容は変わっていません。

現在も適用できるかという点では、説明文の読み方は適用できます。変わったのは接頭辞だけです。ただし対処の部分は別で、キャッシュの消去や記録ファイルの再生成を最初に勧める手順は、当時から現在まで一貫して優先順位が高すぎます。`syscall` と `path` を読む手順が先にあれば、そのほとんどは不要になります。

古い記事を参照する場合は、説明文の解釈だけを取り、対処の順序は本記事の切り分けに置き換えてください。

## 参考資料

- [npm config（cache、prefix、global）](https://docs.npmjs.com/cli/latest/using-npm/config)
- [npm folders](https://docs.npmjs.com/cli/latest/configuring-npm/folders)
- [package.json（workspaces）](https://docs.npmjs.com/cli/latest/configuring-npm/package-json#workspaces)
- [エラー文言の生成（error-message.js）](https://github.com/npm/cli/blob/latest/lib/utils/error-message.js)
- [外部コマンドの起動（promise-spawn）](https://github.com/npm/promise-spawn/blob/main/lib/index.js)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*