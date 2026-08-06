---
title: "Docker の failed to solve エラー：原因と解決策"
date: 2026-08-06
description: "failed to solve は原因名ではありません。ビルドサーバーが返したエラーを BuildKit のクライアントが包むときに足す語で、先頭の ERROR は buildx が付けたものです。コロンより後ろが実際に失敗した部品の言い分なので、書き手を確定させてから調べる場所を決めます。"
tags: ["Docker"]
images: ["og/posts/docker_failed_to_solve.png"]
errorCode: "failed to solve"
lastmod: 2026-08-06
service: "Docker"
error_type: "failed to solve"
components: ["BuildKit", "Docker Buildx"]
related_services: ["Docker Compose", "containerd", "Docker Registry"]
trend_incident: false
---

## 冒頭まとめ

`ERROR: failed to solve:` を原因名として検索しているなら、探す場所がずれています。この一行は1つの部品が出した文言ではなく、3か所が順に書き足した結果です。

先頭の `ERROR:` を付けるのは buildx の入口部分です（[cmd/buildx/main.go](https://github.com/docker/buildx/blob/master/cmd/buildx/main.go)）。続く `failed to solve` は、BuildKit の[クライアント](/glossary/クライアント/)がビルド[サーバー](/glossary/サーバー/)から受け取った[エラー](/glossary/エラー/)を包む語です（[client/solve.go](https://github.com/moby/buildkit/blob/master/client/solve.go)）。コロンより後ろが、失敗した部品の言い分です。

**読むのはコロンの直後です。** `process "..."` なら実行を担う部分、`failed to resolve source metadata for` なら[イメージ](/glossary/イメージ/)参照の解決、`failed to compute cache key` なら solver、`failed to prepare` なら[キャッシュ](/glossary/キャッシュ/)管理が書き手です。`failed commit on ref` に至っては BuildKit ですらなく、同梱の containerd が出しています。

もう1つの読みどころが `------ Dockerfile:3 ------` の囲みです。[エラー](/glossary/エラー/)に Dockerfile 上の位置情報が付いているときだけ出ます（[solver/errdefs/source.go](https://github.com/moby/buildkit/blob/master/solver/errdefs/source.go)）。囲みの有無で、疑う対象が Dockerfile の中身か外側かに分かれます。

## エラーの概要

BuildKit のビルドは、Dockerfile を内部表現へ変換する段、[イメージ](/glossary/イメージ/)参照を解決する段、[コマンド](/glossary/コマンド/)を実行する段、書き出す段の順に進みます。`failed to solve` は全体を包む外枠で、どの段で止まっても先頭は同じです。区別できるのは後ろだけです。

**型1：ステップ見出しと Dockerfile の囲みを伴う**

```text
> [2/2] RUN apk add --no-cache bash:
...
exited with error 127
2 errors
------
 Dockerfile:3
--------------------
   1 |     FROM alpine:3.23
   2 |
   3 | >>> RUN apk add --no-cache bash
   4 |
--------------------
ERROR: failed to build: failed to solve: process "/dev/.buildkit_qemu_emulator /bin/sh -c apk add --no-cache bash" did not complete successfully: exit code: 2
```

`> [2/2]` がステップ番号、`>>>` の行が失敗した命令、区切りの手前の `exited with error 127` が[コマンド](/glossary/コマンド/)自身の出力です。末尾の `exit code: 2` は結果であり、理由ではありません。

**型2：[イメージ](/glossary/イメージ/)参照の解決で止まっている**

```text
error: failed to solve: <レジストリ>:5000/<イメージ>:22.04: failed to resolve source metadata for ...: failed to do request: Head "https://.../v2/.../manifests/22.04": http: server gave HTTP response to HTTPS client
```

命令は1つも実行されていません。読むのは最後尾の[通信](/glossary/通信/)理由で、この例では HTTPS で問い合わせた先が HTTP で応答しています。

**型3：ステップ番号も[コマンド](/glossary/コマンド/)出力も伴わない**

```text
ERROR: failed to solve: source can't be a git ref for COPY
```

```text
ERROR: failed to solve: failed to prepare 6boxvrjdjur378egamsa297vp as lnddt61dq57lwjio5fkmhme9e: invalid argument
```

行番号が出ないのは、位置情報が付いていないからです。ここで Dockerfile を疑い続けても当たりません。

## まず最初に：文言の書き手を確定させる

第一に `--progress=plain` を付けて取り直します。既定値は `auto` で、指定できるのは `auto`・`none`・`plain`・`quiet`・`rawjson`・`tty` です（[commands/build.go](https://github.com/docker/buildx/blob/master/commands/build.go)）。`auto` のままだと出力が畳まれ、理由を示す行が画面から消えます。

落とし穴が1つあります。`BUILDKIT_PROGRESS` [環境変数](/glossary/環境変数/)は `--progress` が `auto` のときにしか読まれません（[util/progress/printer.go](https://github.com/docker/buildx/blob/master/util/progress/printer.go)）。明示的に別の値を渡していると、[環境変数](/glossary/環境変数/)の指定は無視されます。

第二に、コロンの直後の語で書き手を決めます。第三に、上方向へ `> [N/M] <命令>:` の見出しと `------ Dockerfile:<行> ------` の囲みを探します。

第四に `docker buildx ls` を実行します。ドライバーには `docker`・`docker-container`・`kubernetes`・`remote` があり、既定以外では BuildKit が別の[コンテナ](/glossary/コンテナ/)や別の機械で動きます。到達性・空き容量・[認証](/glossary/認証/)情報は、そちら側で判定されます。手元で `docker pull` が通るのに組み立てだけ落ちるのは、ここから生まれます。

## よくある原因と解決手順

### 原因1：RUN の中のコマンドが非ゼロで終了している

`process "<コマンド>" did not complete successfully: exit code: <数値>` の形です。引用符の中身は Dockerfile の記述そのものではなく、実際に起動された[引数](/glossary/引数/)の並びです（[solver/llbsolver/ops/exec.go](https://github.com/moby/buildkit/blob/master/solver/llbsolver/ops/exec.go)）。`/bin/sh -c` が先頭に見えるのはこのためです。末尾の `exit code: N` は終了状態を表す別の型が整形しています（[frontend/gateway/pb/exit.go](https://github.com/moby/buildkit/blob/master/frontend/gateway/pb/exit.go)）。

この型は外枠を何度読んでも情報が増えません。[コマンド](/glossary/コマンド/)自身の出力は、必ず `------` の区切りより手前にあります。arm64 の機械で amd64 向けに組み立てて `RUN apk add --no-cache bash` が落ちた[報告](https://github.com/moby/buildkit/issues/6400)では、手前の `exited with error 127` が理由で、外枠は `exit code: 2` を伝えているだけでした。apt の[報告](https://github.com/docker/build-push-action/issues/933)も同じです。

```bash
# 失敗ステップの1つ前の段階まででいったん止める
docker buildx build --target <失敗の1つ前のステージ名> -t <検証用タグ> .

# そのイメージに入り、同じコマンドを手で流して終了コードを見る
docker run --rm -it <検証用タグ> sh
```

[キャッシュ](/glossary/キャッシュ/)が効いて出力が省略される場合に限り `--no-cache` を併用します。時間が伸びるので、まず `--progress=plain` だけで読めないかを確かめてください。

### 原因2：FROM のイメージ解決で止まっている

`failed to resolve source metadata for <参照>` の形です。この語を足すのは参照解決の部分で、[レジストリ](/glossary/レジストリ/)への問い合わせが成立しなかったことを表します（[imageresolver.go](https://github.com/moby/buildkit/blob/master/client/llb/sourceresolver/imageresolver.go)）。命令の中身とは無関係に、実行前に止まります。

判断材料は最後尾です。`http: server gave HTTP response to HTTPS client` なら[通信](/glossary/通信/)方式の不一致、`pull access denied` なら[認証](/glossary/認証/)、`dial tcp` や `lookup` なら到達性です。自前の HTTP [レジストリ](/glossary/レジストリ/)を参照した[報告](https://github.com/moby/buildkit/issues/6177)では、この不一致がそのまま末尾に出ています。

```bash
# 同じ参照を、組み立てとは別経路で確認する
docker manifest inspect <レジストリ>/<イメージ>:<タグ>
```

手元で通っても、ビルダーが別の場所で動いていれば問い合わせ元も別です。[認証](/glossary/認証/)情報を登録した場所と実行場所が一致しているかを先に見ます。理由が[認証](/glossary/認証/)なら [Docker の pull access denied の記事](/posts/docker_pull_access_denied/)、[タグ](/glossary/タグ/)が見つからないなら [Docker の manifest unknown の記事](/posts/docker_manifest_unknown/)、応答が返らないなら [Docker の context deadline exceeded の記事](/posts/docker_context_deadline_exceeded/)が対象になります。

### 原因3：COPY の対象が context の起点から見つからない

`failed to compute cache key: failed to calculate checksum of ref <ID>: "<パス>": not found` の形です。外側は solver が[キャッシュ](/glossary/キャッシュ/)計算の失敗を包んだ語で（[solver/edge.go](https://github.com/moby/buildkit/blob/master/solver/edge.go)）、内側は照合処理が出しています（[contenthash.go](https://github.com/moby/buildkit/blob/master/solver/llbsolver/ops/opsutils/contenthash.go)）。

誤読されやすいのは `ref` の後ろの長い文字列です。これは[パス](/glossary/パス/)ではなく内部の識別子で、解読しても手がかりになりません。見るのは引用符で囲まれたほうです。

そして `not found` は、[ファイル](/glossary/ファイル/)が存在しないという意味とは限りません。**context の起点から見て見つからない、という意味です。** Docker Desktop を 4.26 から 4.27.1 へ上げた後、それまで通っていた COPY が同じ文言で止まった[報告](https://github.com/docker/compose/issues/11452)があります。消したのではなく、起点の扱いが変わった例です。

```bash
# context の起点から見て、対象が実在するか
ls -l <contextの起点>/<COPYのソースに書いたパス>

# .dockerignore が読まれたか、context が何バイト転送されたかを見る
docker buildx build --progress=plain . 2>&1 | grep -E "load .dockerignore|transferring context"
```

Compose 経由なら、起点は Dockerfile の置き場所ではなく `context` に書いた場所です。

### 原因4：Dockerfile の記述を frontend が解釈できない

Dockerfile を内部表現へ変換する段で止まる場合です。表示はステップ番号も[コマンド](/glossary/コマンド/)出力も伴わない一行になります。

**Before（エラーが起きるコード）：**

```dockerfile
# 末尾が .git の指定は git 参照として扱われる経路がある
COPY ./.git X
```

**After（修正後）：**

```dockerfile
# 末尾が .git にならない書き方へ変更する
COPY ./.git/ X/
```

buildx v0.13.1 での[報告](https://github.com/moby/buildkit/issues/4777)では、それまで通っていた `COPY ./.git /build-dir/.git` が `source can't be a git ref for COPY` で止まっています。この文言は変換処理が直接書いたもので（[convert_copy.go](https://github.com/moby/buildkit/blob/master/frontend/dockerfile/dockerfile2llb/convert_copy.go)）、[ファイル](/glossary/ファイル/)の有無を確かめる前の段階です。見つからないと言われるのではなく、指定の解釈そのものを拒まれています。原因3との違いはここです。

### 原因5：snapshot の準備や書き出しで止まっている

`failed to prepare <ID> as <ID>: invalid argument` の形です。2つの識別子は、元になる保存単位の ID と新しく作る保存単位の ID です（[cache/manager.go](https://github.com/moby/buildkit/blob/master/cache/manager.go)）。`invalid argument` は下層が返した理由です。命令名が出ないのは、書き手が Dockerfile を扱っていないからです。

書き出し側では `failed commit on ref "sha256:..."` も出ます。これは BuildKit ではなく、同梱の containerd が出しています（[core/content/helpers.go](https://github.com/containerd/containerd/blob/main/core/content/helpers.go)）。[キャッシュ](/glossary/キャッシュ/)を[レジストリ](/glossary/レジストリ/)へ書き出して失敗した[報告](https://github.com/moby/buildkit/issues/5487)では、PUT 要求が 404 で返ったことまで末尾に出ています。

```bash
# どのビルダーのどのドライバーで動いているか
docker buildx ls

# docker-container ドライバーの状態が入るボリューム
docker volume ls | grep buildx_buildkit
```

docker-container ドライバーでは、状態が `buildx_buildkit_<ノード名>_state` という名前のボリュームに入ります（[driver/docker-container/driver.go](https://github.com/docker/buildx/blob/master/driver/docker-container/driver.go)）。調べる対象はここです。空き容量が理由なら [Docker の no space left on device の記事](/posts/docker_no_space_left_on_device/)へ移ります。状態を残して作り直すなら `--keep-state` を検討してください（[buildx_rm.md](https://github.com/docker/buildx/blob/master/docs/reference/buildx_rm.md)）。

## 補足：似ているが別のもの

`failed to solve with frontend dockerfile.v0: failed to build LLB: ...` という入れ子を見かけますが、これは古い[バージョン](/glossary/バージョン/)の文言です。v0.6.4 では frontend 名を含めて包む書き方でした（[forwarder/frontend.go](https://github.com/moby/buildkit/blob/v0.6.4/frontend/gateway/forwarder/frontend.go)）。現在の実装にこの語はありません。2019年の[報告](https://github.com/moby/buildkit/issues/1062)のような古い記録は、[バージョン](/glossary/バージョン/)差に注意してください。

`process "..."` の中に `exec format error` が出ているなら、[Docker の exec format error の記事](/posts/docker_exec_format_error/)へ移ります。[イメージ](/glossary/イメージ/)名の文法で弾かれる `invalid reference format` は、[レジストリ](/glossary/レジストリ/)へ問い合わせる前に手元で止まる別系統で、[Docker の invalid reference format の記事](/posts/docker_invalid_reference_format/)が扱います。

組み立てが通ったのに[イメージ](/glossary/イメージ/)が見当たらない状態は、失敗ではありません。既定以外のドライバーで作った結果を手元の一覧へ入れるには `--load` が必要です（[buildx_build.md](https://github.com/docker/buildx/blob/master/docs/reference/buildx_build.md)）。

組み立て後の実行で起きる事象や、Docker の[デーモン](/glossary/デーモン/)へ接続できない状態は範囲外です。後者は [Docker の Cannot connect to the Docker daemon の記事](/posts/docker_cannot_connect_daemon/)が扱います。

## 切り分けの順序

1. `--progress=plain` を付けて取り直す。
2. コロンより後ろの語を読み、どの部品が答えているかを確定させる。
3. 上方向へ `> [N/M] <命令>:` の見出しと `------ Dockerfile:<行> ------` の囲みを探す。
4. `docker buildx ls` でビルダーとドライバーを確認し、判定が行われている場所を確定させる。
5. 実行段なら、区切りの手前にある[コマンド](/glossary/コマンド/)自身の出力を読む。終了コードは結果であって理由ではない。
6. 解決段なら、最後尾で[認証](/glossary/認証/)・[通信](/glossary/通信/)方式・到達性に分け、`docker manifest inspect` で確かめる。
7. `not found` を含むなら、`<contextの起点>/<相対パス>` の形で照合し、`transferring context` の行と突き合わせる。
8. 準備・書き出し段なら、ビルダー側の容量と[権限](/glossary/権限/)を確認する。削除は共有範囲を確かめたうえで最後に行う。

## 確認コマンド集

```bash
# 1. 畳まれていない出力を取得する（切り分けの起点）
docker buildx build --progress=plain -t <イメージ名>:<タグ> .

# 2. 使用中のビルダー、ドライバー、対応プラットフォームを確認する
docker buildx ls

# 3. 動いている buildx の版を確認する
docker buildx version

# 4. FROM の参照を、組み立てとは別経路で確認する
docker manifest inspect <レジストリ>/<イメージ>:<タグ>

# 5. .dockerignore の読み込みと context の転送量を見る
docker buildx build --progress=plain . 2>&1 | grep -E "load .dockerignore|transferring context"

# 6. COPY のソースが context の起点から実在するか確かめる
ls -l <contextの起点>/<COPYのソースに書いたパス>

# 7. docker-container ドライバーの状態ボリュームを一覧する
docker volume ls | grep buildx_buildkit

# 8. 失敗ステップの手前で止め、その状態で同じコマンドを再現する
docker buildx build --target <失敗の1つ前のステージ名> -t <検証用タグ> .
docker run --rm -it <検証用タグ> sh
```

## Editor's Note

この[エラー](/glossary/エラー/)で最も多い遠回りは、**Dockerfile を疑い続けること**です。文言に Dockerfile の名前が出ていないのに、書き換えては試す。この形に入ると時間が溶けます。

その典型が記録されています（[Docker buildkit fails to build .net project](https://github.com/docker/buildx/issues/2021)）。2023年8月、`dotnet publish` を2行以上書くと落ち、1行なら通る、という報告です。出た文言は `failed to prepare 6boxvrjdjur378egamsa297vp as lnddt61dq57lwjio5fkmhme9e: invalid argument` で、報告者自身が分かりにくい[エラー](/glossary/エラー/)だと書いています。当然でした。この文言を書いた部分は Dockerfile を扱っておらず、保存単位の識別子しか持っていません。報告者は、BuildKit を使わない経路なら同じ Dockerfile が通ることも確かめています。

対照的な記録もあります（[Alpine image build fails on arm64 when targeting amd64](https://github.com/moby/buildkit/issues/6400)）。2025年12月、`RUN apk add --no-cache bash` が落ちた例では `Dockerfile:3` の囲みが出ています。ここは Dockerfile を見るのが正解です。

2つの違いは失敗の重さではなく、**[エラー](/glossary/エラー/)に位置情報が付いていたかどうか**です。囲みが出れば、その行に結び付いている。出なければ結び付いていない。判定は出力を見れば済みます。

`failed to solve` に当たったら、畳まずに取り直す。コロンの後ろで書き手を決める。手を動かすのは、そのあとです。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*