---
title: "npm の ENOTEMPTY エラー：原因と解決策"
date: 2026-08-08
description: "npm は ENOTEMPTY を内部で一度握りつぶして退避先を消してから移動をやり直すため、画面に出た時点で2回目の失敗が起きており、退避先を消せないか消した直後に作り直されているかのどちらかに絞れます。"
tags: ["npm"]
images: ["og/posts/npm_enotempty.png"]
errorCode: "ENOTEMPTY"
error_name: "ENOTEMPTY: directory not empty, rename"
error_aliases:
  - "npm error code ENOTEMPTY"
  - "npm ERR! code ENOTEMPTY"
  - "directory not empty, rename"
  - "npm error syscall rename"
lastmod: 2026-08-08
service: "npm"
error_type: "ENOTEMPTY"
components: ["npm CLI", "Arborist"]
related_services: ["Node.js", "Docker"]
error_cases:
  - id: "watcher-recreates-dest"
    situation: "開発サーバーやファイル監視ツールを起動したまま npm install を実行すると失敗する"
    messages:
      - "npm error code ENOTEMPTY"
      - "npm error syscall rename"
      - "npm error dest <path>/node_modules/.<package>-<hash>"
    cause: "監視ツールや開発サーバーが node_modules へ書き込み続けている可能性がある"
    check: "dest 行のディレクトリ名を控え、監視ツールを止めてから同じコマンドを実行し、結果が変わるかを見る"
    fix: "node_modules を触るプロセスをすべて止めてから導入をやり直す"
  - id: "concurrent-npm-process"
    situation: "CI で複数のジョブが同じ作業ディレクトリを共有している、または実行中に別の npm が走っている"
    messages:
      - "npm error code ENOTEMPTY"
      - "npm error syscall rename"
      - "npm error path <path>/node_modules/<package>"
    cause: "同じ node_modules に対して npm が同時に複数走っている可能性がある"
    check: "ps で npm または node のプロセスを数え、同じ作業ディレクトリを指すものが複数あるかを確認する"
    fix: "同じディレクトリへの導入を直列にし、ジョブごとに作業ディレクトリを分ける"
  - id: "retired-dirs-left-behind"
    situation: "前回の npm install を中断した、あるいは容量不足や通信断で終わったあとに実行すると失敗する"
    messages:
      - "npm error code ENOTEMPTY"
      - "npm error dest <path>/node_modules/.<package>-<hash>"
      - "ENOTEMPTY: directory not empty, rename '<path>/node_modules/<package>' -> '<path>/node_modules/.<package>-<hash>'"
    cause: "前回の中断で退避用のディレクトリが残っている可能性がある"
    check: "node_modules 直下を ls -a で表示し、dest 行と同じ名前のドットで始まるディレクトリが残っているかを確認する"
    fix: "残っている退避用のディレクトリを取り除いてから導入をやり直す"
  - id: "mounted-volume-limitation"
    situation: "コンテナや共有マウント上に置いた node_modules でだけ失敗し、コンテナ内部のパスでは成功する"
    messages:
      - "npm error code ENOTEMPTY"
      - "npm error syscall rename"
    cause: "割り当てたファイルシステムでディレクトリの移動が期待どおりに働いていない可能性がある"
    check: "node_modules の場所が割り当ての対象に含まれるかを確認し、対象外のパスへ置いて同じコマンドを試す"
    fix: "node_modules を割り当ての対象から外し、コンテナ内部のパスへ置く"
  - id: "antivirus-file-lock"
    situation: "Windows でのみ失敗し、同じ手順が他の環境では成功する"
    messages:
      - "npm error code ENOTEMPTY"
      - "npm error syscall rename"
    cause: "ウイルス対策ソフトや編集ソフトが node_modules の中身を掴んでいる可能性がある"
    check: "作業ディレクトリを監視対象から外し、編集ソフトを閉じてから同じコマンドを実行して結果を比べる"
    fix: "作業ディレクトリを常時監視の対象から外すか、導入中だけ監視を止める"
trend_incident: false
---

## 結論

`npm error code ENOTEMPTY` は、移動しようとした先が空でない[ディレクトリ](/glossary/ディレクトリ/)だったという意味です。npm はこの[コード](/glossary/コード/)に専用の説明を持っておらず、既定の扱いになるため、画面に出るのは [OS](/glossary/os/) が返した1文だけです。

ここで押さえるべき点があります。npm は導入の過程で、置き換える対象を一度別名へ退避します。この移動が `ENOTEMPTY` で失敗した場合、実装は例外を握りつぶし、退避先を中身ごと[削除](/glossary/削除/)してから移動をやり直します。つまり、単に古い退避先が残っていただけなら表には出ません。

したがって画面に出た時点で、それは2回目の失敗です。退避先を[削除](/glossary/削除/)できなかったか、[削除](/glossary/削除/)した直後に誰かが作り直したかのどちらかに絞れます。前者は[ファイル](/glossary/ファイル/)システムの制約、後者は同時に動いている別のプロセスです。

読む場所は `path` と `dest` の2行です。`path` が退避される元、`dest` が退避先で、後者はドットで始まる名前になります。この名前は元の経路から機械的に決まるため、実行のたびに変わりません。

## エラーが発生する処理段階

`ENOTEMPTY` は取得の段階では出ません。依存の解決も取得も終わり、実際に `node_modules` を書き換える段階で起きます。

第一段階は差分の計算です。npm は今ある木と目標の木を比べ、変更するものと[削除](/glossary/削除/)するものを列挙します。

第二段階が退避です。変更または[削除](/glossary/削除/)の対象になった浅い階層のものを、別名へ移動します。ここが `ENOTEMPTY` の主な発生場所です。退避しておく理由は、途中で失敗したときに元へ戻せるようにするためです。

第三段階が展開で、新しい内容を書き込みます。第四段階で退避したものを片付けます。

失敗が第二段階で起きると、npm は元へ戻す処理を試みます。このとき戻す方向の移動でも同じ[コード](/glossary/コード/)が出ることがあります。`path` と `dest` の関係が逆になっていれば、戻す側で失敗しています。

## 最初に確認すること

まず、診断用の行を抜き出します。

```bash
npm install 2>&1 | grep -E "npm error (code|syscall|path|dest|errno)"
```

出力はこの形になります。

```text
npm error code ENOTEMPTY
npm error syscall rename
npm error path /app/node_modules/lodash
npm error dest /app/node_modules/.lodash-Ab3dEf9x
```

`dest` の名前に注目してください。ドットに続けて元の名前があり、その後ろに8文字の英数字が付きます。実装では、元の経路をもとに固定の手順で短い文字列を作り、`.<元の名前>-<その文字列>` という名前にします。経路が同じであれば同じ名前になるため、何度実行しても変わりません。

次に、その退避先が実際に残っているかを見ます。

```bash
ls -a node_modules | grep "^\."
```

`dest` と同じ名前が出てくれば、前回の中断が残っています。出てこないのに失敗する場合は、[削除](/glossary/削除/)した直後に作り直されています。

同時に動いているものも確認してください。

```bash
ps -ef | grep -E "npm|node" | grep -v grep
```

## 原因別の確認方法と解決策

### 原因1：監視ツールや開発サーバーが動いたままになっている {#watcher-recreates-dest}

最も見落とされる形です。開発[サーバー](/glossary/サーバー/)や[ファイル](/glossary/ファイル/)監視[ツール](/glossary/ツール/)が `node_modules` を読み書きし続けていると、npm が退避先を消した直後に作り直されます。

npm は一度目の失敗を自動で処理するため、たまたま残っていただけなら表に出ません。表に出たということは、消した直後に何かが動いています。

確認方法は、止めてから比べることです。

```bash
npm install
```

監視[ツール](/glossary/ツール/)を止めた状態で同じ[コマンド](/glossary/コマンド/)を実行し、結果が変わるかを見ます。変われば確定です。

対処は、`node_modules` を触るものをすべて止めてから導入することです。ビルド監視、[テスト](/glossary/テスト/)の継続実行、統合開発環境の自動処理などが該当します。導入が終わってから起動し直してください。

### 原因2：npm が同時に複数走っている {#concurrent-npm-process}

継続的インテグレーションで複数のジョブが同じ作業[ディレクトリ](/glossary/ディレクトリ/)を共有している場合や、統合開発環境が裏で導入を始めている場合です。

確認方法はプロセスの照会です。

```bash
ps -ef | grep npm | grep -v grep
```

同じ作業[ディレクトリ](/glossary/ディレクトリ/)を指すものが2つ以上あれば確定です。継続的インテグレーションでは、[ログ](/glossary/ログ/)の時刻を突き合わせて、複数のジョブが重なっていないかを確認してください。

対処は直列化と分離です。同じ[ディレクトリ](/glossary/ディレクトリ/)への導入が重ならないようにし、可能であればジョブごとに作業[ディレクトリ](/glossary/ディレクトリ/)を分けます。

```yaml
concurrency:
  group: install-${{ github.ref }}
  cancel-in-progress: false
```

[キャッシュ](/glossary/キャッシュ/)の[復元](/glossary/復元/)と導入が同時に走る構成でも起きます。順序を明示してください。

### 原因3：前回の中断で退避用のディレクトリが残っている {#retired-dirs-left-behind}

導入を途中で止めた、[容量](/glossary/容量/)が足りずに終わった、[通信](/glossary/通信/)が切れた、といった経緯のあとに起きます。

通常はこの状態でも npm が自動で処理します。それでも失敗する場合は、残っている退避先を消せていません。中身が読み取り専用になっている、所有者が違う、といった事情が重なっています。

確認方法は一覧です。

```bash
ls -la node_modules | grep "^d.*\s\."
```

`dest` 行と同じ名前が出れば確定です。対処は取り除いてからの再実行になります。

```bash
ls -d node_modules/.*-????????
```

対象を目で確認してから消してください。`node_modules` の中には `.bin` や `.package-lock.json` のように、ドットで始まる正規のものもあります。まとめて消さないでください。

```bash
rm -rf node_modules
npm install
```

判断に迷う場合は `node_modules` ごと作り直すほうが安全です。記録[ファイル](/glossary/ファイル/)は残してください。

### 原因4：割り当てたファイルシステムの制約 {#mounted-volume-limitation}

[コンテナ](/glossary/コンテナ/)の割り当てや、[ネットワーク](/glossary/ネットワーク/)越しの共有[ファイル](/glossary/ファイル/)システムに `node_modules` を置いている場合です。[ディレクトリ](/glossary/ディレクトリ/)の移動が期待どおりに働かず、[削除](/glossary/削除/)も即座には反映されません。

確認方法は場所を変えて比べることです。割り当ての対象外にある経路へ置いて、同じ[コマンド](/glossary/コマンド/)を実行します。そこで成功すれば、割り当て側の問題です。

対処は、`node_modules` を割り当ての対象から外すことです。手元の[ディレクトリ](/glossary/ディレクトリ/)全体を割り当てている場合、その内側だけを別扱いにできます。

```yaml
services:
  app:
    volumes:
      - .:/app
      - /app/node_modules
```

この書き方は、`/app/node_modules` を[コンテナ](/glossary/コンテナ/)の内部に置き、手元の内容で覆わないようにするものです。導入は[コンテナ](/glossary/コンテナ/)の中で行ってください。

### 原因5：Windows で他のソフトがファイルを掴んでいる {#antivirus-file-lock}

Windows でのみ起きる場合です。[ウイルス](/glossary/ウイルス/)対策ソフトが導入直後の[ファイル](/glossary/ファイル/)を検査していると、その間は移動も[削除](/glossary/削除/)もできません。編集ソフトが開いている場合も同様です。

npm は移動が[権限](/glossary/権限/)の問題で失敗したときに、複製へ切り替える経路を持っています。ただし空でない[ディレクトリ](/glossary/ディレクトリ/)の移動については、退避先を消してからやり直す動きになるため、掴まれ続けていると解消しません。

確認方法は、条件を外して比べることです。作業[ディレクトリ](/glossary/ディレクトリ/)を監視の対象から外し、編集ソフトを閉じてから同じ[コマンド](/glossary/コマンド/)を実行します。

対処は、作業[ディレクトリ](/glossary/ディレクトリ/)を常時監視の対象から外すことです。組織の方針で変更できない場合は、導入の間だけ止められるかを管理者に確認してください。監視を無効にしたままにする対処は勧められません。

## 近いエラーとの境界

`EEXIST` は、移動先が既に存在する場合です。npm の実装では `ENOTEMPTY` と同じ分岐で扱われ、退避先を消してからやり直します。表に出た場合の調べ方も同じになります。

`EPERM` は操作そのものが許されていない場合です。npm はこの[コード](/glossary/コード/)のときに移動をあきらめ、中身を1つずつ複製する経路へ切り替えます。Windows で使用中の[ファイル](/glossary/ファイル/)に対して出ることが多く、`ENOTEMPTY` とは扱いが分かれます。

`EACCES` は[権限](/glossary/権限/)による拒否です。対象は存在しますが読み書きできません。npm は操作が [OS](/glossary/os/) に拒まれたと説明します。

`ENOENT` は対象が見つからない場合です。npm の実装は、移動の途中でこの[コード](/glossary/コード/)が出たときには親[ディレクトリ](/glossary/ディレクトリ/)を作ってからやり直します。

`ENOSPC` は[容量](/glossary/容量/)の不足です。容量不足で導入が途中で止まると、次の実行では原因3の形になります。前後関係で入れ替わる点に注意してください。

## 内部動作または公式仕様

導入の実処理は Arborist が担当します。木を書き換える際、変更または[削除](/glossary/削除/)の対象になった浅い階層のものを先に退避します。

退避先の名前は固定の手順で決まります。元の経路をもとに短い要約を作り、記号を取り除いて先頭8文字を取り、`.<元の名前>-<その8文字>` という名前を組み立てます。要約の材料は経路そのものなので、同じ場所に対しては常に同じ名前になります。作業[ディレクトリ](/glossary/ディレクトリ/)を変えれば名前も変わります。

移動そのものは、まず名前の変更を試み、それが装置をまたぐ場合や[権限](/glossary/権限/)の問題で失敗した場合にだけ、中身を1つずつ複製する経路へ切り替えます。この切り替えは `ENOTEMPTY` では起きません。

`ENOTEMPTY` と `EEXIST` は別に扱われます。実装は移動の失敗を受け取ると、この2つの場合に限り、移動先を中身ごと[削除](/glossary/削除/)してから移動をやり直します。ここで再度失敗すると、その例外は処理されずに上へ伝わります。画面に出るのはこの2回目の失敗です。

この設計から、表に出た `ENOTEMPTY` の意味が絞られます。[削除](/glossary/削除/)が効いていないか、[削除](/glossary/削除/)と再移動の間に移動先が作り直されているかのどちらかです。単に古い退避先が残っているだけであれば、1回目の処理で解消します。

なお npm 側にこの[コード](/glossary/コード/)の説明文はありません。実装の[コード](/glossary/コード/)ごとの分岐に該当がなく、既定の扱いになります。表示されるのは [OS](/glossary/os/) が返した1文と、診断用の項目だけです。

## バージョン差・注意点

出力の接頭辞が変わりました。現在の npm は `npm error` で始まり、古い版は `npm ERR!` でした。`ENOTEMPTY` については専用の分岐が無く既定の扱いのままなので、説明文の違いは接頭辞だけです。

対処として `npm cache clean --force` を挙げる記事が見られますが、`ENOTEMPTY` は取得の段階ではなく `node_modules` の書き換えの段階で起きます。[キャッシュ](/glossary/キャッシュ/)を消しても移動先の状態は変わりません。

`rm -rf node_modules && npm install` は原因3に対しては有効です。ただし原因1と原因2では、作り直している側を止めない限り再発します。まず何が動いているかを確認してください。

退避用の[ディレクトリ](/glossary/ディレクトリ/)を手作業で消す場合は、対象を必ず目で確認してください。`node_modules` の直下には `.bin` や `.package-lock.json` のように、ドットで始まる正規のものが存在します。ドットで始まるものを一括で消すと、導入済みの状態が壊れます。

管理者[権限](/glossary/権限/)を付けて実行する対処も見られますが、`ENOTEMPTY` の多くは[権限](/glossary/権限/)の問題ではありません。付けて通った場合、`node_modules` の所有者が変わり、次回以降も同じ[権限](/glossary/権限/)が必要になります。

## Editor's Note

npm がこの[コード](/glossary/コード/)を内部で一度処理している点は、調査の前提を変えます。実装を確認すると、移動の失敗を受け取る箇所で `EEXIST` と `ENOTEMPTY` だけが特別扱いされ、移動先を中身ごと[削除](/glossary/削除/)してから移動をやり直す作りになっています。

当時の状態としては、この扱いが入る前は、前回の中断で残った退避用の[ディレクトリ](/glossary/ディレクトリ/)がそのまま失敗の原因になっていました。そのため古い解説の多くは「残骸を消せば直る」という対処で完結しています。実際、その時期にはそれで解決していました。

現在も適用できるかという点では、対処としては有効ですが、説明としては不足しています。残骸が残っているだけの状態は、現在の npm が自分で解消します。それでも表に出たということは、[削除](/glossary/削除/)が効いていないか、[削除](/glossary/削除/)の直後に作り直されているかのどちらかです。残骸を消すだけでは、次の実行でも同じ場所で止まります。

読み替えの規則は次のとおりです。古い記事の対処である `rm -rf` は今も試す価値がありますが、それで解消しない場合を「よくある例外」ではなく「本来の姿」として扱ってください。`node_modules` を触っているものが他にあるか、という問いが本筋になります。

## 参考資料

- [npm install](https://docs.npmjs.com/cli/latest/commands/npm-install)
- [npm folders](https://docs.npmjs.com/cli/latest/configuring-npm/folders)
- [導入処理の実装（reify.js）](https://github.com/npm/cli/blob/latest/workspaces/arborist/lib/arborist/reify.js)
- [退避先の命名（retire-path.js）](https://github.com/npm/cli/blob/latest/workspaces/arborist/lib/retire-path.js)
- [移動処理の実装（move-file.js）](https://github.com/npm/fs/blob/main/lib/move-file.js)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*