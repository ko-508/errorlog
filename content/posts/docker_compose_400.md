---
title: "Docker Compose の 400 エラー：原因と解決策"
date: 2026-05-30
description: "Docker Composeの設定またはAPIリクエストに誤りがある。Docker Compose 400 エラーの原因と解決策を解説します。"
tags: ["Docker Compose"]
errorCode: "400"
---
Docker Composeで400エラーが発生する場合、compose.ymlの設定に問題があるか、コマンドのオプション指定が誤っている可能性があります。設定ファイルの検証とコマンドの確認により、ほぼすべてのケースで解決します。

## よくある原因

### compose.ymlのYAML書式エラー

YAML形式の構文ミスが最も多い原因です。インデント（スペース）の不一致、タブ文字の混在、コロンの後の空白忘れなどが該当します。YAMLはインデントに非常に敏感であり、2文字か4文字のスペースで統一する必要があります。タブ文字を使用するとパーサーが正しく解釈できず、400エラーが発生します。

### サービス定義の必須キー不足または型エラー

serviceセクション内で必須キーが欠けている、または値の型が仕様と異なる場合も400エラーになります。例えば、`ports`に文字列を指定すべきところに数値を指定したり、`environment`に配列ではなくオブジェクト形式を使用したりすると、Docker Composeは設定を受け入れません。

### docker composeコマンドのオプション指定誤り

`docker compose up --detach`など、存在しないオプションを指定した場合や、オプションの値の形式が間違っている場合も400エラーが返されます。オプション名のスペル間違いや、廃止されたオプションの使用もこれに該当します。

## 解決手順

### ステップ1：docker compose configで設定を検証する

まず、compose.ymlが正しく解析されているか確認します。以下のコマンドを実行してください。

```bash
docker compose config
```

このコマンドはDocker Composeが解析した設定をそのまま出力します。エラーがあれば、その時点で具体的なエラーメッセージが表示されます。メッセージに行番号が含まれている場合は、その箇所を重点的に確認してください。

### ステップ2：compose.ymlのYAML構文をチェックする

インデント、コロン、引用符などの構文を確認します。以下の点に注意してください。

```yaml
# 正しい例
version: '3.8'
services:
  web:
    image: nginx:latest
    ports:
      - "80:80"
    environment:
      - NGINX_HOST=example.com
      - NGINX_PORT=80

  db:
    image: mysql:8.0
    volumes:
      - db_data:/var/lib/mysql
    ports:
      - "3306:3306"

volumes:
  db_data:
```

```yaml
# 間違った例
version: '3.8'
services:
  web:
    image: nginx:latest
    ports:
    - "80:80"  # インデント不足
    environment:
    NGINX_HOST: example.com  # キーと値の関係が不明確
```

YAMLリンターツール（例：yamllint）をローカルにインストールして検査することも有効です。

```bash
# yamllintのインストール（Pythonが必要）
pip install yamllint

# compose.ymlを検査
yamllint compose.yml
```

### ステップ3：サービス定義の型を確認する

各サービスの主要キーの値の型が正しいか確認します。`ports`と`volumes`は配列形式が必須です。

```yaml
# ポートの正しい指定例
ports:
  - "8080:80"        # 文字列
  - target: 80       # オブジェクト形式
    published: 8080
    protocol: tcp

# ボリュームの正しい指定例
volumes:
  - /host/path:/container/path
  - named_volume:/container/path

# 環境変数の正しい指定例（配列とオブジェクトの両形式で可）
environment:
  - KEY1=value1
  - KEY2=value2

# または

environment:
  KEY1: value1
  KEY2: value2
```

### ステップ4：docker composeコマンドのオプションを確認する

使用しているコマンドが正しいか確認します。

```bash
# ヘルプを表示
docker compose --help

# サブコマンド別のヘルプ（例：up）
docker compose up --help
```

正しいコマンド例を以下に示します。

```bash
# コンテナーをバックグラウンドで起動
docker compose up -d

# 特定のcompose.ymlファイルを指定
docker compose -f ./custom-compose.yml up -d

# サービスをビルドしてから起動
docker compose up --build

# コンテナーを停止・削除
docker compose down

# ログを表示
docker compose logs -f
```

### ステップ5：特定のファイルパスを確認する

複数のcompose.ymlが存在する場合、正しいファイルを指定しているか確認します。

```bash
# デフォルトのcompose.ymlを使用
docker compose up -d

# ファイル名またはパスを明示的に指定
docker compose -f /path/to/compose.yml up -d

# 複数のcomposeファイルをマージ
docker compose -f compose.yml -f compose.override.yml up -d
```

## それでも解決しない場合

`docker compose config --resolve-image-digests`を実行して、詳細な検証情報を確認してください。ネットワーク接続の問題でレジストリー（イメージ保管サーバー）と通信できていない場合も400エラーが返されることがあります。その場合は、Dockerログ（`journalctl -u docker`）を確認し、ネットワーク設定を見直してください。

また、Docker Composeのバージョンが古い場合、新しい設定キーが認識されないため、`docker compose version`で確認し、必要に応じてアップグレードします。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*