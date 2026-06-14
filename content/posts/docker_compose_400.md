---
title: "Docker Compose の 400 エラー：原因と解決策"
date: 2026-05-30
lastmod: 2026-06-14
description: "Docker Composeの設定またはAPIリクエストに誤りがある。Docker Compose 400 エラーの原因と解決策を解説します。"
tags: ["Docker Compose"]
errorCode: "400"
service: "Docker Compose"
error_type: "400"
components: ["Compose"]
related_services: ["Docker", "yamllint", "YAML"]
---

## エラーの概要

Docker Composeで400エラーが発生する場合、`compose.yml`（または`docker-compose.yml`）の設定に問題があるか、コマンドのオプション指定が誤っている可能性があります。このエラーはCompose自体が設定ファイルを正しくパースできないことを示しており、設定ファイルの検証とコマンド構文の確認により、ほぼすべてのケースで解決します。

## 実際のエラーメッセージ例

```
ERROR: The Compose file './docker-compose.yml' is invalid because:
service 'web' has unsupported config option: 'cointainer_name'
```

```json
{
  "error": "Invalid service configuration",
  "message": "service 'db' config has unsupported option: 'envrionment'",
  "code": 400
}
```

```
Error response from daemon: Ports must be expressed as "port" (a number) or "port/protocol" (a string).
```

## よくある原因と解決手順

### 原因1：compose.ymlのYAML構文エラー（インデント・タブ混在）

YAML形式の構文ミスが最も多い原因です。インデント（スペース）の不一致、タブ文字の混在、コロンの後の空白忘れなどが該当します。YAMLはインデントに非常に敏感であり、2文字か4文字のスペースで統一する必要があります。タブ文字を使用するとパーサーが正しく解釈できず、400エラーが発生します。

**Before（エラーが起きるコード）：**

```yaml
version: '3.8'
services:
  web:
    image: nginx:latest
	ports:  # タブ文字が混在している
      - "80:80"
  db:
   image: postgres:13  # インデントが統一されていない（スペース数が異なる）
   environment:
    POSTGRES_PASSWORD: secret
```

**After（修正後）：**

```yaml
version: '3.8'
services:
  web:
    image: nginx:latest
    ports:
      - "80:80"
  db:
    image: postgres:13
    environment:
      POSTGRES_PASSWORD: secret
```

### 原因2：サービス定義の必須キー不足または値の型エラー

serviceセクション内で必須キーが欠けている、または値の型が仕様と異なる場合も400エラーになります。例えば、`ports`に文字列を指定すべきところに数値を指定したり、`environment`をリスト形式で記述すべきところにオブジェクト形式で書いたりすると発生します。また、キー名のタイプミス（`cointainer_name`など）も認識されずエラーとなります。

**Before（エラーが起きるコード）：**

```yaml
version: '3.8'
services:
  web:
    image: nginx:latest
    ports: 80 8080  # 正しい形式ではない
    environment: NGINX_HOST=localhost NGINX_PORT=8080  # リスト形式で書くべき
    cointainer_name: my_web  # キー名のタイプミス
```

**After（修正後）：**

```yaml
version: '3.8'
services:
  web:
    image: nginx:latest
    ports:
      - "80:80"
      - "8080:8080"
    environment:
      - NGINX_HOST=localhost
      - NGINX_PORT=8080
    container_name: my_web
```

### 原因3：イメージタグまたはレジストリ形式の誤り

イメージ名の指定形式が不正な場合も400エラーが発生します。プライベートレジストリを使用する場合、`<registry>/<repository>:<tag>`形式を厳密に守る必要があります。また、無効なタグやホスト名を含むと、Composeのバリデーションに引っかかります。

**Before（エラーが起きるコード）：**

```yaml
version: '3.8'
services:
  app:
    image: my-app:latest@sha256=abc123  # 無効な形式
  db:
    image: 192.168.1.1:5000/postgres  # ポート番号がない場合がある
```

**After（修正後）：**

```yaml
version: '3.8'
services:
  app:
    image: my-app:latest
  db:
    image: registry.example.com:5000/postgres:13
```

### 原因4：ネットワークまたはボリューム定義の不備

`networks`または`volumes`トップレベルキーで定義されていないネットワーク・ボリュームを参照すると、400エラーが発生します。サービス内で使用するネットワークやボリュームは、必ずcompose.yml内で事前に定義するか、`external: true`で外部リソースとして明示する必要があります。

**Before（エラーが起きるコード）：**

```yaml
version: '3.8'
services:
  web:
    image: nginx:latest
    volumes:
      - app_data:/var/www/html  # app_data が定義されていない
    networks:
      - backend  # backend が定義されていない
```

**After（修正後）：**

```yaml
version: '3.8'
services:
  web:
    image: nginx:latest
    volumes:
      - app_data:/var/www/html
    networks:
      - backend

volumes:
  app_data:
    driver: local

networks:
  backend:
    driver: bridge
```

## Docker Compose固有の注意点

**compose.yml検証コマンド：** `docker compose config` コマンドを実行することで、ファイルの妥当性を即座に確認できます。このコマンドはファイルをパースして規範化された出力を表示するため、構文エラーを素早く発見できます。

```bash
docker compose -f compose.yml config
```

**バージョン互換性：** `version`キーで指定したCompose仕様のバージョンが、インストール済みのDocker Composeバージョンで対応していない場合も400エラーになります。デフォルトは最新安定版を使用することを推奨します。

**環境変数の展開エラー：** `${VARIABLE_NAME}`形式で環境変数を参照している場合、変数が定義されていないと展開時にエラーになる可能性があります。`.env`ファイルの存在確認と変数定義を必ず確認してください。

```bash
docker compose --env-file .env up
```

**Buildコンテキストパスエラー：** `build`セクションで`context`や`dockerfile`を指定する場合、存在しないパスを記述すると400エラーが発生します。相対パスは`compose.yml`ファイルの位置を基準として解釈されるため注意が必要です。

## それでも解決しない場合

**ログ出力の詳細化：** `--verbose`フラグを付けてコマンドを再実行し、より詳細なエラーメッセージを確認してください。

```bash
docker compose --verbose up 2>&1 | head -50
```

**YAML検証ツール：** [yamllint](https://github.com/adrienverge/yamllint) などのオンラインYAML検証ツールやコマンドラインツールを使用して、ファイルの構文をスタンドアロンで検証することも有効です。

```bash
yamllint compose.yml
```

**公式リファレンス確認：** Docker Composeの公式ドキュメント「[Compose file reference](https://docs.docker.com/compose/compose-file/)」で、使用しているバージョンの仕様を確認してください。キー名や値の型、必須キーが正確に記載されています。

**GitHub Issuesの検索：** 同じエラーメッセージが記録されているか [Docker Compose GitHub リポジトリ](https://github.com/docker/compose/issues) を検索し、既知の問題や回避策がないか確認してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*