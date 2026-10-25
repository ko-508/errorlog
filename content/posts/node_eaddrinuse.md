---
title: "Node.jsのEADDRINUSE対処法"
date: 2026-10-20
slug: node_eaddrinuse
draft: false
description: "listen EADDRINUSE はサーバーの待ち受け先が使用中のエラーです。WindowsのnetstatやLinuxのssで対象ポートとPIDを確認し、既存サーバーを止めるか起動ポートを変更します。:::3000の意味も説明します。"
tags: ["Node.js"]
images: ["og/posts/node_eaddrinuse.png"]
errorCode: "EADDRINUSE"
service: "Node.js"
error_type: "EADDRINUSE"
components: ["net", "http", "libuv"]
related_services: ["Docker"]
trend_incident: false
---

## 冒頭まとめ

Node.jsの[サーバー](/glossary/サーバー/)を起動したとき、次の[エラー](/glossary/エラー/)が出ることがあります。

```text
Error: listen EADDRINUSE: address already in use :::3000
```

これは、指定した待ち受け先が既に使われていて、[サーバー](/glossary/サーバー/)を起動できなかったことを表します。[Node.jsの公式文書](https://nodejs.org/api/net.html#serverlisten)も、別の[サーバー](/glossary/サーバー/)が同じ待ち受け先を使用している場合の[エラー](/glossary/エラー/)として説明しています。

まず、その[ポート](/glossary/ポート/)を使う[プログラム](/glossary/プログラム/)を確認します。不要な開発[サーバー](/glossary/サーバー/)なら停止し、必要なものなら今回起動する[サーバー](/glossary/サーバー/)の[ポート](/glossary/ポート/)を変えます。[パッケージ](/glossary/パッケージ/)の入れ直しを始める前に、待ち受け先を確認してください。

## :::3000はアドレスとポートをつないだ表示

`:::3000` は、IPv6のアドレス `::` と、区切りの `:`、[ポート番号](/glossary/ポート番号/) `3000` をつないだ表示です。コロンの書き間違いではありません。

[公式のlistenの説明](https://nodejs.org/api/net.html#serverlistenport-host-backlog-callback)では、ホストを省略すると、IPv6が利用可能なら `::`、そうでなければIPv4の `0.0.0.0` で待ち受けます。どちらも、特定の1つのアドレスだけに限定しない指定です。

`::` での待ち受けがIPv4側も受け付ける[環境](/glossary/環境/)もあります。[エラー](/glossary/エラー/)がIPv6の表示だからといって、IPv4の待ち受けを確認対象から外さないでください。

また、同じNode.jsの[プログラム](/glossary/プログラム/)内で別々の[サーバー](/glossary/サーバー/)を作り、同じ待ち受け先を使った場合も重なります。必ずしも別のアプリが原因とは限りません。

## Windowsではローカルの待ち受けとPIDを見る

[コマンドプロンプト](/glossary/コマンドプロンプト/)で、現在の接続と待ち受けを表示します。

```bat
netstat -a -n -o
```

[Microsoftのnetstatの説明](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/netstat)によると、`-a` は待ち受けを含めて表示し、`-n` はアドレスと[ポート](/glossary/ポート/)を数値で表示し、`-o` はPIDを表示します。PIDは、実行中の[プログラム](/glossary/プログラム/)を識別する番号です。

3000番で[エラー](/glossary/エラー/)が出たなら、TCPの行のローカルアドレスが `:3000` で終わり、状態が `LISTENING` になっている行を探します。外部アドレス側に3000番がある行とは区別してください。

PIDが分かったら、[プログラム](/glossary/プログラム/)名を確認します。次の12345は例なので、確認したPIDに置き換えます。

```bat
tasklist /fi "PID eq 12345"
```

[tasklistの公式説明](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/tasklist)には、PIDによる絞り込みが用意されています。ただし、名前が `node.exe` と分かっても、どの[プロジェクト](/glossary/プロジェクト/)かまでは特定できません。起動した[ターミナル](/glossary/ターミナル/)や、タスクマネージャーの詳細も照合してから停止します。

## Linuxでは対象ポートを指定して確認する

[Linux](/glossary/linux/)では、次の[コマンド](/glossary/コマンド/)で待ち受け中のTCPの3000番を確認できます。

```bash
ss -ltnp 'sport = :3000'
```

[ssの説明書き](https://man7.org/linux/man-pages/man8/ss.8.html)では、`-l` は待ち受け、`-t` はTCP、`-n` は数値表示、`-p` は使用する[プロセス](/glossary/プロセス/)の表示です。`sport` の条件でローカル側の[ポート](/glossary/ポート/)を絞ります。

[プロセス](/glossary/プロセス/)情報を確認できない場合は、必要な[権限](/glossary/権限/)で実行してください。表示されたPIDや[プログラム](/glossary/プログラム/)名を、停止する対象の確認に使います。

まずは起動した[ターミナル](/glossary/ターミナル/)に戻り、Ctrl+Cで終了させます。自動で起動し直す仕組みを使っている場合は、その管理元で停止してください。子の[プロセス](/glossary/プロセス/)だけを止めても、再起動される可能性があります。

## 既存サーバーを止めるかポートを変える

前に起動した開発[サーバー](/glossary/サーバー/)が不要なら、停止した後でもう一度[ポート](/glossary/ポート/)を確認し、今回の[サーバー](/glossary/サーバー/)を起動します。

Windowsで起動元から止められない場合は、対象を確認したうえでPIDを指定します。

```bat
taskkill /pid 12345
```

[taskkillの説明](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/taskkill)では、`/f` は強制終了です。通常の停止で終わらず、強制終了してよい対象だと確認できた場合に限り追加します。

```bat
taskkill /pid 12345 /f
```

既存[サーバー](/glossary/サーバー/)も必要なら、今回の[ポート](/glossary/ポート/)を変えます。自分で書いた[HTTP](/glossary/http/)[サーバー](/glossary/サーバー/)なら、次のように指定できます。3001番も空いているとは限らないため、使用状況は確認してください。

```js
// server.cjs
const http = require('node:http');

const server = http.createServer((req, res) => {
  res.end('ok');
});

server.listen(3001, '127.0.0.1', () => {
  console.log('http://127.0.0.1:3001');
});
```

この例は自分のPCからの接続に限定しています。開発[ツール](/glossary/ツール/)を使っている場合は、その[ツール](/glossary/ツール/)の[ポート](/glossary/ポート/)[設定](/glossary/設定/)を変更します。`PORT` [環境変数](/glossary/環境変数/)や `--port` が有効かどうかは[ツール](/glossary/ツール/)によって異なるため、共通の指定として扱わないでください。

## エラー処理を追加してもポートは空かない

[サーバー](/glossary/サーバー/)の待ち受け失敗は `error` [イベント](/glossary/イベント/)で[通知](/glossary/通知/)されます。[イベントの公式文書](https://nodejs.org/api/events.html#error-events)によると、受け取る[処理](/glossary/処理/)が無いと[エラー](/glossary/エラー/)が投げられ、Node.jsの[プロセス](/glossary/プロセス/)が終了します。

次の例では、失敗を表示して終了[コード](/glossary/コード/)を[設定](/glossary/設定/)します。使用中の[ポート](/glossary/ポート/)を解放したり、[サーバー](/glossary/サーバー/)を起動し直したりする[処理](/glossary/処理/)ではありません。

```js
// server.cjs
const http = require('node:http');
const server = http.createServer((req, res) => res.end('ok'));

server.on('error', (error) => {
  console.error(error.code, error.message);
  process.exitCode = 1;
});

server.listen(3000);
```

[テスト](/glossary/テスト/)など、固定[ポート](/glossary/ポート/)が不要な用途では、[ポート](/glossary/ポート/)0を指定して[OS](/glossary/os/)に空き[ポート](/glossary/ポート/)を選ばせる方法もあります。割り当て結果は待ち受け開始後に読み取ります。

```js
// automatic-port.cjs
const http = require('node:http');
const server = http.createServer((req, res) => res.end('ok'));

server.listen(0, '127.0.0.1', () => {
  console.log(`http://127.0.0.1:${server.address().port}`);
});
```

固定[URL](/glossary/url/)を前提にした[ブラウザ](/glossary/ブラウザ/)や他のサービスは、割り当てられた[ポート](/glossary/ポート/)に合わせる必要があります。

[Linux](/glossary/linux/)のNode.js 24.19.0で、最初に[OS](/glossary/os/)が選んだ[ポート](/glossary/ポート/)に別の[サーバー](/glossary/サーバー/)を起動すると、`listen EADDRINUSE: address already in use :::34029` が出ることを確認しました。番号は実行時の値です。[エラー](/glossary/エラー/)を受け取らない子[プロセス](/glossary/プロセス/)は終了[コード](/glossary/コード/)1となり、既存[サーバー](/glossary/サーバー/)を閉じた後は同じ[ポート](/glossary/ポート/)で起動できました。Windowsの確認・停止[コマンド](/glossary/コマンド/)は公式資料との照合のみで、実機では未検証です。

## Dockerのポート競合や接続失敗との違い

[Dockerのport is already allocated](/posts/docker_port_is_already_allocated/)は、[Docker](/glossary/docker/)側の[ポート](/glossary/ポート/)公開で出る[エラー](/glossary/エラー/)です。Node.jsの[ログ](/glossary/ログ/)に本件が出ている場合と、[Docker](/glossary/docker/)が[コンテナ](/glossary/コンテナ/)を起動する段階で停止している場合を分けて確認します。

[connection refused](/posts/postgresql_connection_refused/)は接続する側で出る[エラー](/glossary/エラー/)です。本件は待ち受ける側が起動できなかったことを示します。

`EADDRINUSE` の確認では、[エラー](/glossary/エラー/)内の[ポート番号](/glossary/ポート番号/)と実行環境を揃えてください。[コンテナ](/glossary/コンテナ/)や別の[OS](/glossary/os/)[環境](/glossary/環境/)の中で起動している場合は、[エラー](/glossary/エラー/)を出した環境内の待ち受けも確認対象です。

## 解決手順のまとめ

[エラー](/glossary/エラー/)に出た[ポート](/glossary/ポート/)の待ち受けとPIDを確認し、不要な開発[サーバー](/glossary/サーバー/)なら起動元から止めます。止める前に対象を特定し、既存[サーバー](/glossary/サーバー/)も必要なら今回の[ポート](/glossary/ポート/)を変更します。

`:::3000` のコロンを直したり、[エラー](/glossary/エラー/)表示だけを抑えたりしても、待ち受けの重なりは解消しません。停止や[設定変更](/glossary/設定変更/)の後に再起動し、実際に接続できるところまで確認してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の[仕様](/glossary/仕様/)は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
