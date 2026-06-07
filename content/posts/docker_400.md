---
title: "Docker の 400 エラー：原因と解決策"
date: 2026-01-01
description: "Docker の 400 エラーは、クライアント側のリクエストが不正な形式であることを示すHTTPステータスコードです。Docker デーモンとの通信（コンテナの操作、イメージのプッシュ・プル、API呼び出し）の際に、形式不正なリクエストが"
tags: ["Docker"]
errorCode: "400"
lastmod: 2026-05-31
---
## エラーの概要

[Docker](/glossary/docker/)の400[エラー](/glossary/エラー/)は、クライアント側の[リクエスト](/glossary/リクエスト/)が不正な形式であることを示す[HTTP](/glossary/http/)[ステータスコード](/glossary/ステータスコード/)です。[Docker](/glossary/docker/)[デーモン](/glossary/デーモン/)との[通信](/glossary/通信/)（[コンテナ](/glossary/コンテナ/)の操作、[イメージ](/glossary/イメージ/)のプッシュ・プル、[API](/glossary/api/)呼び出し）の際に、形式不正な[リクエスト](/glossary/リクエスト/)が送信された場合に発生します。多くの場合、Dockerfileの構文エラー、[API](/glossary/api/)[リクエスト](/glossary/リクエスト/)の形式ミス、または[設定ファイル](/glossary/設定ファイル/)の不正な記述が原因です。

## 実際のエラーメッセージ例

```
docker build -t myimage:latest .
Step 1/5 : FROM ubuntu:20.04
Step 2/5 : RUN apt-get update && apt-get install -y curl
Step 3/5 : COPY . /app
Step 4/5 : WORKDIR /app
Step 5/5 : RUN python script.py
Error response from daemon: invalid header field value "oci runtime error"
Error response from daemon: HTTP/400: Bad Request
```

```json
{
  "message": "invalid request: malformed JSON in request body",
  "code": 400,
  "detail": "failed to decode request body"
}
```

## よくある原因と解決手順

### 原因1：Dockerfileのrun コマンドの構文エラー

**なぜ発生するか**
Dockerfileの[コマンド](/glossary/コマンド/)で行末の区切り文字（バックスラッシュ）が正しく使われていないか、シェルコマンドの構文が不正な場合に、[Docker](/glossary/docker/)[デーモン](/glossary/デーモン/)が該当行を解析できず400エラーを返します。

**Before（エラーが起きる状態）**
```dockerfile
FROM ubuntu:20.04
RUN apt-get update && \
    apt-get install -y python3 \
    curl
RUN echo "Installation complete"
```

**After（修正後）**
```dockerfile
FROM ubuntu:20.04
RUN apt-get update && \
    apt-get install -y python3 \
    curl
RUN echo "Installation complete"
```

正しくは、継続する各行の末尾に`\`を記述し、改行を[コマンド](/glossary/コマンド/)の一部として解釈させます。

### 原因2：docker-compose.ymlのYAML形式の不正

**なぜ発生するか**
docker-composeファイルでインデント（空白）が不規則であるか、キー名の引用符が不完全な場合、[YAML](/glossary/yaml/)パーサーが設定を読み込めず、[Docker](/glossary/docker/)[デーモン](/glossary/デーモン/)への[リクエスト](/glossary/リクエスト/)が不正な形式になります。

**Before（エラーが起きる状態）**
```yaml
version: '3.8'
services:
  web:
    image: nginx:latest
    ports:
      - "80:80"
    environment:
      - NGINX_HOST=example.com
      - NGINX_PORT: 80
    volumes:
    - ./html:/usr/share/nginx/html
```

**After（修正後）**
```yaml
version: '3.8'
services:
  web:
    image: nginx:latest
    ports:
      - "80:80"
    environment:
      - NGINX_HOST=example.com
      - NGINX_PORT=80
    volumes:
      - ./html:/usr/share/nginx/html
```

キー`NGINX_PORT`の値は`=`で区切り（`:`ではなく）、`volumes`のインデントを統一します。

### 原因3：Docker APIのJSONリクエスト形式が不正

**なぜ発生するか**
[Docker](/glossary/docker/)Remote[API](/glossary/api/)（[HTTP](/glossary/http/)で[Docker](/glossary/docker/)[デーモン](/glossary/デーモン/)と[通信](/glossary/通信/)する場合）を使用する際、[リクエストボディ](/glossary/リクエストボディ/)の[JSON](/glossary/json/)が不正な形式または必須フィールドが欠けている場合、400エラーが返されます。

**Before（エラーが起きる状態）**
```bash
curl -X POST http://localhost:2375/containers/create \
  -H "Content-Type: application/json" \
  -d '{
    "Image": "ubuntu:20.04",
    "Cmd": ["echo", "hello]
  }'
```

[JSON](/glossary/json/)が不完全です（`"hello]`のクォートが閉じられていません）。

**After（修正後）**
```bash
curl -X POST http://localhost:2375/containers/create \
  -H "Content-Type: application/json" \
  -d '{
    "Image": "ubuntu:20.04",
    "Cmd": ["echo", "hello"],
    "Tty": true
  }'
```

[JSON](/glossary/json/)の構文を正しく閉じ、必須フィールドを完成させます。

### 原因4：docker push時のタグ形式の誤り

**なぜ発生するか**
[Docker](/glossary/docker/)[レジストリ](/glossary/レジストリ/)（[Docker](/glossary/docker/)Hubや[プライベートレジストリ](/glossary/プライベートレジストリ/)）に[イメージ](/glossary/イメージ/)をプッシュする際、タグ形式が不正であるか、認証情報が不足している場合、[レジストリ](/glossary/レジストリ/)が400エラーを返します。

**Before（エラーが起きる状態）**
```bash
docker tag myapp:latest myregistry.com/myapp
docker push myregistry.com/myapp
# Error response from daemon: HTTP/400: Bad Request
```

タグに版が含まれていません。

**After（修正後）**
```bash
docker tag myapp:latest myregistry.com/myapp:latest
docker push myregistry.com/myapp:latest
```

[レジストリ](/glossary/レジストリ/)URL、[リポジトリ](/glossary/リポジトリ/)名、タグを完全な形式で指定します。

## Docker固有の注意点

### docker-composeネットワーク設定でのエラー

docker-composeで複数のサービス間の通信設定が不正な場合、400エラーが発生することがあります。特に`networks`セクションで指定する[ネットワーク](/glossary/ネットワーク/)名やドライバーが不正であると、[コンテナ](/glossary/コンテナ/)起動時に[デーモン](/glossary/デーモン/)が[リクエスト](/glossary/リクエスト/)を拒否します。

```yaml
version: '3.8'
services:
  app:
    image: myapp:latest
    networks:
      - backend
networks:
  backend:
    driver: bridge
```

### Dockerソケット接続時の権限問題

[Docker](/glossary/docker/)[デーモン](/glossary/デーモン/)への接続に使用される`/var/run/docker.sock`への[アクセス権](/glossary/アクセス権/)がない場合、結果として400エラーとして報告されることがあります。ユーザーが`docker`グループに属していることを確認してください。

```bash
sudo usermod -aG docker $USER
newgrp docker
```

### レジストリ認証情報の不完全性

[Docker](/glossary/docker/)Hubや[プライベートレジストリ](/glossary/プライベートレジストリ/)に認証なしでプッシュしようとした場合、[サーバー](/glossary/サーバー/)が400エラーを返すことがあります。事前に`docker login`を実行してください。

```bash
docker login
# ユーザー名とパスワードを入力
docker push myregistry.com/myapp:latest
```

## それでも解決しない場合

### デバッグログの確認

[Docker](/glossary/docker/)[デーモン](/glossary/デーモン/)の詳細[ログ](/glossary/ログ/)を確認することで、エラーの正確な原因が判明することがあります。

```bash
dockerd --debug 2>&1 | grep -i "400\|bad request"
```

または、[Docker](/glossary/docker/)[コマンド](/glossary/コマンド/)に`-D`フラグを追加して詳細情報を表示します。

```bash
docker -D build -t myimage:latest .
```

### Dockerfileのバリデーション

Dockerfileの構文を事前にチェックするには、Hadolintなどのツールを使用してください。

```bash
hadolint Dockerfile
```

### 公式ドキュメントの確認

- [Docker Build reference](https://docs.docker.com/reference/dockerfile/) - Dockerfileの正確な構文
- [Docker Compose specification](https://docs.docker.com/compose/compose-file/) - docker-compose.ymlの仕様
- [Docker Engine API](https://docs.docker.com/engine/api/) - Remote[API](/glossary/api/)の詳細

### コミュニティリソース

[Docker](/glossary/docker/)のGitHub Issuesやstack Overflowで同様のエラーが報告されていないか検索してください。特に`docker-compose`や特定のバージョンでの互換性問題はGitHubのIssuesで詳細が共有されていることが多いです。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*