---
title: "Docker の 404 エラー：原因と解決策"
date: 2026-01-01
description: "Docker の 404 エラーは、どこで見つからなかったかで3系統に分かれます。手元のデーモンの資源（No such container / No such image）、レジストリのタグ（manifest for ... not found）、そしてリポジトリ自体（pull access denied。存在しないのか権限がないのかは意図的に区別されません）。エラー文言から切り分けて解決します。"
tags: ["Docker"]
errorCode: "404"
lastmod: 2026-07-11
service: "Docker"
error_type: "404"
components: ["Registry", "Hub"]
related_services: ["Docker Compose"]
trend_incident: true
---

## 冒頭まとめ

Docker の 404 は「指定したものが見つからない」ことを示しますが、探した場所によって原因も対処も変わります。系統は3つです。第一に、手元のデーモンが管理する資源が見つからない場合で、No such container: や No such image: という文言になります。第二に、レジストリ（Docker Hub などのイメージ保管先）にリポジトリはあるがタグが見つからない場合で、manifest for ... not found という文言になります。第三に、リポジトリ自体にたどり着けない場合で、pull access denied for ..., repository does not exist or may require 'docker login' という文言になります。この3つ目の文言が「存在しない」と「権限がない」を並記しているのは意図的な設計で、Docker Hub は非公開リポジトリの存在を外部に確認させないため、両者を区別しないエラーを返します。

つまり Docker の404の調査は、エラー文言を読んで「手元」「タグ」「リポジトリ（または権限）」のどれかを確定するところから始まります。

## エラーの概要

docker コマンドのエラーで Error response from daemon: と付くものは、Docker デーモンまで指示が届いたうえで、デーモンが処理を拒否したことを示します。デーモンは、コンテナやイメージなどの資源が見つからない場合、API 上は 404 として応答し、CLI には No such container: <名前> のような文言で表示されます（この対応は Docker のソースコードで確認できます）。一方、docker pull や docker push でレジストリとやり取りする場合の404は、レジストリ側の応答に由来します。レジストリの標準仕様では、リポジトリ名が不明な場合のエラーコードは NAME_UNKNOWN（repository name not known to registry）で、これも HTTP 404 に対応付けられています。

どの場合も、エラーコードの数字より文言のほうが多くを語ります。以下、文言ごとに切り分けます。

## まず最初に：エラー文言で3つに分岐する

No such container: <名前> や No such image: <名前> なら、手元のデーモンの中に該当する資源がありません（原因1）。

manifest for <イメージ>:<タグ> not found: manifest unknown なら、リポジトリまでは到達しており、指定したタグが存在しません（原因2）。

pull access denied for <名前>, repository does not exist or may require 'docker login' なら、リポジトリが存在しないか、権限（ログイン）が足りないかのどちらかです（原因3）。

## よくある原因と解決手順

### 原因1：手元のデーモンにその名前の資源がない

docker exec、docker logs、docker rm などで指定した名前のコンテナが存在しない場合の404です。単純な綴りの誤りのほか、見落とされやすいのが Docker Compose の自動命名です。Compose が起動したコンテナには、プロジェクト名とサービス名から組み立てられた名前が付くため、compose ファイルに書いたサービス名をそのまま指定しても一致しないことがあります。

**Before（サービス名をそのまま指定して404）：**

```bash
docker exec -it web bash
# Error response from daemon: No such container: web
```

**After（実際のコンテナ名を確認して指定）：**

```bash
# 停止中も含めて実際の名前を確認
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"

# Compose 管理下なら、サービス名と実コンテナの対応を確認
docker compose ps

# 確認した実際の名前で実行（Compose 経由なら exec はサービス名で可）
docker compose exec web bash
```

docker ps -a で名前自体は合っているのに404になる場合は、コンテナが削除済みです（docker ps は既定で稼働中しか表示しないため、-a での確認が確実です）。No such image: の場合も同様に、docker images で手元のイメージ一覧と名前・タグを突き合わせます。

### 原因2：レジストリに指定したタグが存在しない

リポジトリは実在するがタグが違う場合、レジストリは manifest unknown を返し、CLI には次のように表示されます。

```bash
docker pull ubuntu:24.10.5
# Error response from daemon: manifest for ubuntu:24.10.5 not found:
# manifest unknown: manifest unknown
```

原因はタグの綴りの誤り、提供されていないタグの指定、そして「タグ省略時の latest」です。タグを省略すると latest が補われますが、すべてのリポジトリが latest タグを提供しているわけではないため、リポジトリ名が正しくてもこの404になることがあります。対処は実在するタグの確認です。Docker Hub であればイメージのページの Tags 一覧で確認できます。Dockerfile や compose ファイルにタグを書く場合は、確認した実在のタグを明示します。

### 原因3：リポジトリが存在しない、または権限がない

```bash
docker pull myteam/internal-tool
# Error response from daemon: pull access denied for myteam/internal-tool,
# repository does not exist or may require 'docker login':
# denied: requested access to the resource is denied
```

この文言のとおり、Docker Hub は「リポジトリが存在しない」場合と「非公開リポジトリに権限がない」場合を区別せずに応答します。確認の順序は次のとおりです。

第一に、名前空間の欠落です。ユーザー名（または組織名）を省いた名前は、公式イメージの領域（docker.io/library/）として解釈されます。エラー文言や push 時の出力に library/ が含まれていたら、これが原因です。自分のイメージは <ユーザー名>/<イメージ名> の完全な形で指定します。

第二に、認証です。対象が非公開リポジトリなら、docker login で対象レジストリにログインしてから再実行します。ログイン済みでも失敗する場合は、そのアカウントにリポジトリへのアクセス権があるかを確認します。

第三に、綴りです。上記2つに該当しなければ、リポジトリ名そのものの誤りを疑い、レジストリのウェブ画面で実在を確認します。

なお、名前に大文字が含まれている場合は、この404系のエラーにはなりません。リポジトリ名は小文字と定められており、レジストリへ問い合わせる前に invalid reference format: repository name must be lowercase として拒否されます。この文言が出たら、404の調査ではなく名前の修正です。

## 補足：404に見えて別の問題

push や pull の相手が実はレジストリではない（ポート番号の誤りなどで通常のウェブサーバーに接続している）場合、相手の返す HTML の404を JSON として解析できない旨のエラー（error parsing HTTP 404 response body: invalid character '<' ...）になります。この場合の調査対象は名前ではなく接続先です。また、レジストリに到達できない場合（DNS 解決の失敗や接続タイムアウト）は404ではなく接続系のエラー文言になります。404は「相手まで届いたうえで、見つからなかった」ことの証拠なので、経路の問題とは切り分けて考えられます。

## 切り分けの順序

1. エラー文言を読む。No such 系なら手元（原因1）、manifest 系ならタグ（原因2）、pull access denied 系ならリポジトリまたは権限（原因3）。
2. 原因1なら docker ps -a と docker images で実在の名前を確認する。Compose 管理下なら docker compose ps で対応を確認する。
3. 原因2ならレジストリのタグ一覧で実在するタグを確認し、明示する。
4. 原因3なら、名前空間（library/ と解釈されていないか）、docker login、綴りの順に確認する。

## 確認コマンド集

```bash
# 1. 停止中も含めた実際のコンテナ名を確認
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"

# 2. 手元のイメージの名前とタグを確認
docker images

# 3. Compose のサービス名と実コンテナの対応を確認
docker compose ps

# 4. レジストリへの認証状態を作り直す
docker login

# 5. 完全な名前（レジストリ/名前空間/イメージ:タグ）で取得を再試行
docker pull docker.io/<ユーザー名>/<イメージ名>:<タグ>
```

## Editor's Note

原因3の名前空間の欠落を示す実例として、Docker 公式フォーラムの長期スレッドがあります（[Docker push - Error - requested access to the resource is denied](https://forums.docker.com/t/docker-push-error-requested-access-to-the-resource-is-denied/64468)、2018年開始）。docker login は成功しているのに push が denied: requested access to the resource is denied で失敗するという報告で、出力に The push refers to a repository [docker.io/library/プロジェクト名] とあることから、ユーザー名を省いた名前が公式イメージの領域（library/）への操作として解釈されていたことが分かります。回答は、<ユーザー名>/<イメージ名> の形でタグを付け直して push するというもので、その後も2024年に至るまで同種の報告と同じ解決が繰り返し書き込まれています。この記事は pull の404を中心に扱いましたが、名前空間の欠落という原因は push でも pull でも同じ形で現れる、ということを示す実例です。

Docker の404は、文言が「どこで見つからなかったか」を最初に教えてくれます。名前を打ち直す前に、手元・タグ・リポジトリのどの話なのかを文言で確定することが確実な近道です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*