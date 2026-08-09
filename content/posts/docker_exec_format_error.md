---
title: "Docker の exec format error：原因と解決策"
date: 2026-08-03
description: "exec format error は Linux の execve が返す ENOEXEC の文言で、意味は「形式が認識できない」です。原因は2系統に分かれ、CPU アーキテクチャの不一致と、実行しようとした対象が実行可能な形式でない場合です。似た文言の no such file or directory とは別の系統なので、まず文言を正確に読み分けます。"
tags: ["Docker"]
errorCode: "exec format error"
lastmod: 2026-08-03
service: "Docker"
error_type: "exec format error"
components: ["Engine", "Image"]
related_services: ["Docker Buildx", "Kubernetes"]
trend_incident: false
---

## 冒頭まとめ

`exec format error` は [Docker](/glossary/docker/) が作った文言ではありません。Linux が[プログラム](/glossary/プログラム/)を起動する際に返す `ENOEXEC` という結果を、そのまま表示したものです。

公式のマニュアルには、この結果の意味が1文で書かれています。実行可能[ファイル](/glossary/ファイル/)が**認識できる形式でない**、**アーキテクチャが違う**、あるいは実行できない何らかの形式上の問題がある、という3つが並記されています。

したがって原因は2系統に分かれます。1つ目は **CPU アーキテクチャの不一致**です。[Docker](/glossary/docker/) の公式文書は理由まで説明しています。[コンテナ](/glossary/コンテナ/)はホストのカーネルを共有するため、中で動く[コード](/glossary/コード/)はホストのアーキテクチャと互換でなければならない。だから `linux/amd64` の[コンテナ](/glossary/コンテナ/)を arm64 のホストで（エミュレーションなしに）動かすことはできない、と明記されています。

2つ目は、**実行しようとした対象がそもそも実行可能な形式でない**場合です。先頭行に実行系の指定が無いスクリプトを直接起動しようとした場合が典型です。

そして重要な境界があります。**`no such file or directory` は別の系統**です。マニュアルでは、指定した[ファイル](/glossary/ファイル/)や、スクリプトの実行系、あるいは必要な共有ライブラリが見つからない場合の結果として区別されています。[ファイル](/glossary/ファイル/)は確かにあるのに「無い」と言われる現象は、こちらの系統です。

## エラーの概要

実行時に出る文言は、実行系の階層をそのまま反映した形になります。

```text
docker: Error response from daemon: failed to create task for container:
  failed to create shim task: OCI runtime create failed: runc create failed:
  unable to start container process: exec /entrypoint.sh: exec format error
```

長く見えますが、読むべきは末尾だけです。`unable to start container process:` までは実行系が付け加えた前置きで、実装でもこの文言でくるむ処理が確認できます。その後ろの `exec <対象>: exec format error` が本体です。

古い版では、次の形で表示されることもあります。意味は同じです。

```text
standard_init_linux.go:228: exec user process caused: exec format error
```

まず確認すべきは、**どの対象で失敗したか**です。上の例では `/entrypoint.sh`。この[ファイル](/glossary/ファイル/)が、実行可能な形式として認識されなかった、という意味になります。

## まず最初に：イメージとホストのアーキテクチャを突き合わせる

第一に、[イメージ](/glossary/イメージ/)がどのアーキテクチャ向けかを確認します。

```bash
docker image inspect <イメージ> --format '{{.Os}}/{{.Architecture}}'
```

第二に、ホストのアーキテクチャを確認します。`x86_64` なら amd64、`aarch64` なら arm64 です。

```bash
uname -m
```

第三に、この2つが食い違っていれば、原因は1系統目です。一致しているのに失敗するなら、2系統目を疑います。

第四に、文言が `exec format error` か `no such file or directory` かを読み分けます。後者なら調べる先が変わります。

## よくある原因と解決手順

### 原因1：ビルドしたアーキテクチャと動かす環境が違う

最も多い形です。手元の機械と配備先の CPU が違う場合に起こります。Apple Silicon の機械で作った[イメージ](/glossary/イメージ/)を x86-64 の[サーバー](/glossary/サーバー/)へ持っていく、あるいはその逆です。

`docker build` は、指定が無ければ**実行している機械のアーキテクチャ向け**に作ります。手元では問題なく動くため、配備して初めて発覚します。

**Before（手元のアーキテクチャのまま作る）：**

```bash
docker build -t myapp:latest .
docker push myapp:latest
# → arm64 の機械で作られ、amd64 のサーバーで exec format error
```

**After（対象のアーキテクチャを指定して作る）：**

```bash
# 単一のアーキテクチャ向けに作る
docker build --platform linux/amd64 -t myapp:latest .

# 複数に対応した1つのイメージとして作る（推奨）
docker buildx build --platform linux/amd64,linux/arm64 -t myapp:latest --push .
```

公式文書によれば、複数アーキテクチャに対応した[イメージ](/glossary/イメージ/)は一覧表のような構造を持ち、[レジストリ](/glossary/レジストリ/)から取得する際にホストのアーキテクチャに合う版が自動的に選ばれます。**作る側で対応しておけば、使う側は何も意識しなくて済みます**。

なお `docker run` にも同じ指定があります。ただし、これは取得する版を選ぶだけで、対応する版が[イメージ](/glossary/イメージ/)に含まれていなければ解決しません。

### 原因2：エミュレーションが有効になっていない

アーキテクチャが違っても、エミュレーションがあれば動きます。公式文書によれば、[Docker](/glossary/docker/) Desktop はこの仕組みを既定で備えています。

問題になるのは、[Docker](/glossary/docker/) Desktop を使わない[環境](/glossary/環境/)です。この場合、エミュレータをホストに導入し、実行形式として登録する必要があります。公式が示している前提は、カーネルが 4.8 以降であること、対応する[ソフトウェア](/glossary/ソフトウェア/)が 2.1.7 以降であること、そしてエミュレータが静的に組まれ、専用の指定付きで登録されていることです。

```bash
# エミュレータを導入して実行形式を登録する
docker run --privileged --rm tonistiigi/binfmt --install all

# 登録を確認する（公式は F の有無を見るよう案内している）
cat /proc/sys/fs/binfmt_misc/qemu-aarch64
```

なお、エミュレーションは遅いという注意も公式に書かれています。作るだけなら許容できても、本番で常用する選択肢ではありません。

### 原因3：イメージの中で複数アーキテクチャが混在している

見落とされやすい形です。作る際の基盤[イメージ](/glossary/イメージ/)は正しいのに、その中へ別のアーキテクチャ向けの実行[ファイル](/glossary/ファイル/)を取り込んでしまった場合に起こります。

上流の公式文書にも、[コンテナ](/glossary/コンテナ/)が複数アーキテクチャの実行[ファイル](/glossary/ファイル/)を混在させている場合にこの[エラー](/glossary/エラー/)に遭遇し得る、と明記されています。

原因になりやすいのは、作る際に外部から実行[ファイル](/glossary/ファイル/)を取得している箇所です。取得先の [URL](/glossary/url/) にアーキテクチャが埋め込まれていると、対象を切り替えても取得先が変わりません。

```dockerfile
# 対象のアーキテクチャを受け取り、取得先に反映する
ARG TARGETARCH
RUN curl -L "https://example.com/tool-linux-${TARGETARCH}.tar.gz" | tar xz
```

公式文書で説明されているとおり、作る側の[環境](/glossary/環境/)と対象の[環境](/glossary/環境/)を示す値は、作る過程で自動的に利用できます。埋め込みを避け、これらの値を使ってください。

### 原因4：スクリプトに実行系の指定が無い

アーキテクチャは合っているのに失敗する場合、こちらを疑います。マニュアルの記述どおり、認識できる形式でなければ同じ結果になります。先頭行に `#!` で始まる指定が無いスクリプトは、実行可能な形式として認識されません。

```bash
# 先頭行を確認する
head -1 entrypoint.sh
```

**Before（指定が無い）：**

```bash
echo "starting"
exec "$@"
```

**After（先頭行に実行系を指定する）：**

```bash
#!/bin/sh
echo "starting"
exec "$@"
```

指定を足せない事情がある場合は、明示的に実行系へ渡す形にすれば回避できます。

```dockerfile
ENTRYPOINT ["/bin/sh", "/entrypoint.sh"]
```

### 原因5：no such file or directory と混同している

対処ではなく読み分けの問題です。マニュアルでは、[ファイル](/glossary/ファイル/)や実行系、必要な共有ライブラリが見つからない場合は別の結果として区別されています。

したがって、[ファイル](/glossary/ファイル/)は確実に存在するのに「無い」と言われる場合、疑うべきは実行系の側です。先頭行で指定した実行系が[イメージ](/glossary/イメージ/)に含まれていない場合や、動的に結びつけるライブラリが足りない場合が該当します。軽量な基盤[イメージ](/glossary/イメージ/)で `#!/bin/bash` を指定している場合が典型です。

**同じ「起動できない」でも、形式の問題か、見つからない問題かで調べる先が正反対**になります。文言を最後まで読んでください。

## 補足：似ているが別のもの

[イメージ](/glossary/イメージ/)そのものが取得できない場合は、起動以前の段階です（[Docker の 404 の記事](/posts/docker_404/)）。名前の書式が不正な場合は、[レジストリ](/glossary/レジストリ/)へ問い合わせる前に手元で弾かれます（[Docker の invalid reference format の記事](/posts/docker_invalid_reference_format/)）。

[Kubernetes](/glossary/kubernetes/) 上で同じことが起きた場合、[コンテナ](/glossary/コンテナ/)は起動に失敗して再起動を繰り返す状態になります（[Kubernetes の CrashLoopBackOff の記事](/posts/kubernetes_crashloopbackoff/)）。文言自体は[ログ](/glossary/ログ/)や出来事の欄に同じ形で現れます。

[権限](/glossary/権限/)が足りずに実行できない場合は、また別の文言になります。実行の許可が無いのか、形式が認識できないのかは区別されます。

## 切り分けの順序

1. 文言の末尾を読む。`exec format error` か `no such file or directory` かで系統が分かれる。
2. どの対象で失敗したかを確認する。文言の中に入っている。
3. [イメージ](/glossary/イメージ/)とホストのアーキテクチャを突き合わせる。食い違えば原因は1つ目。
4. 食い違っていれば、対象のアーキテクチャを指定して作り直す。実行時の指定だけでは解決しない。
5. エミュレーションに頼るなら、登録されているかを確認する。[Docker](/glossary/docker/) Desktop 以外では既定で有効ではない。
6. アーキテクチャが一致しているなら、[イメージ](/glossary/イメージ/)内の混在を疑う。取得先にアーキテクチャを埋め込んでいないか。
7. 対象がスクリプトなら、先頭行の指定を確認する。
8. `no such file or directory` なら、実行系や共有ライブラリの不足を疑う。

## 確認コマンド集

```bash
# 1. イメージのアーキテクチャを確認する
docker image inspect <イメージ> --format '{{.Os}}/{{.Architecture}}'

# 2. ホストのアーキテクチャを確認する
uname -m

# 3. レジストリ上のイメージが対応しているアーキテクチャを一覧する
docker manifest inspect <イメージ> \
  | grep -E '"architecture"|"os"'

# 4. 対象のアーキテクチャを指定して作る
docker build --platform linux/amd64 -t <イメージ> .

# 5. 複数アーキテクチャに対応した1つのイメージとして作る
docker buildx build --platform linux/amd64,linux/arm64 -t <イメージ> --push .

# 6. エミュレータの登録状況を確認する
ls /proc/sys/fs/binfmt_misc/ | grep qemu
cat /proc/sys/fs/binfmt_misc/qemu-aarch64 2>/dev/null | head -3

# 7. イメージの中の実行ファイルの形式を調べる
docker run --rm --entrypoint sh <イメージ> -c 'head -c 20 /entrypoint.sh | od -c | head -2'

# 8. スクリプトの先頭行と改行コードを確認する
head -1 entrypoint.sh | cat -A | head -1
```

## Editor's Note

この[エラー](/glossary/エラー/)の厄介さは、**手元では絶対に再現しない**点にあります。

その典型を記録した報告があります（[video-streaming image built on macbook M1 caused exec format error](https://github.com/bootstrapping-microservices/chapter-7/issues/8)）。2022年12月、Apple Silicon の機械で作った[イメージ](/glossary/イメージ/)を配備したところ、`standard_init_linux.go:228: exec user process caused: exec format error` で起動しなかった、という内容です。

手元では動きます。当然で、作った機械と同じアーキテクチャだからです。問題が現れるのは、別のアーキテクチャの[環境](/glossary/環境/)へ持っていったときだけ。**開発機で確認しても意味が無い**という性質が、この[エラー](/glossary/エラー/)を配備直前まで隠します。

報告の中で共有されている対処は、作成の手順を複数アーキテクチャ対応の形に変え、`--platform linux/arm64,linux/amd64` を指定して作るというものでした。片方に決め打ちするのではなく、両方に対応させています。手元でも配備先でも動く状態にすれば、同じ問題は二度と起きません。

なお、開発機のアーキテクチャは選べません。しかし、作る[イメージ](/glossary/イメージ/)のアーキテクチャは選べます。**この2つを混同しないこと**が、この[エラー](/glossary/エラー/)への根本的な対処です。

そして、もう1つ覚えておく価値があるのは文言の読み分けです。`exec format error` は形式の問題、`no such file or directory` は不在の問題。マニュアルで別々の結果として定義されている以上、対処も別々になります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*