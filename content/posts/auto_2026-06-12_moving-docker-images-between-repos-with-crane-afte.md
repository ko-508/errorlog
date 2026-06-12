---
title: "Dockerイメージをリポジトリ間で移動する際の400 Bad Requestエラーと解決策"
date: 2026-06-12
lastmod: 2026-06-12
draft: false
description: "Dockerイメージをリポジトリ間で移動する際に発生する400 Bad Requestエラーの原因と、Go-Containerregistryのcraneツールを使った効果的な解決策を解説します。特にマルチアーキテクチャイメージの扱いや認証の問題に焦点を当てます。"
tags: ["Dev.to - Docker"]
trend_incident: true
---

## エラーの概要

Dockerイメージをあるリポジトリから別のリポジトリへコピーする際、特に`docker buildx imagetools create`コマンドを使用すると、`400 Bad Request`エラーやハングアップが発生することがあります。このエラーは、主にDocker Hubのようなレジストリ間でのクロスリポジトリなBLOBコピーが不安定な場合に発生し、イメージの移動が正常に完了しないことを示します。

## 実際のエラーメッセージ例

`docker buildx imagetools create`コマンドでエラーが発生した場合、以下のような出力が見られることがあります。

```
ERROR: failed to copy: failed to copy blob: unexpected status: 400 Bad Request
```

あるいは、エラーメッセージが出ずにコマンドが応答しなくなる（ハングアップする）こともあります。

## よくある原因と解決手順

### 原因1：`docker buildx imagetools create`の不安定性

`docker buildx imagetools create`は、マルチアーキテクチャイメージのマニフェストをタグ間でコピーするために設計されていますが、Docker Hubのような特定のレジストリ環境において、クロスリポジトリでのBLOBコピーが不安定になることがあります。これにより、`400 Bad Request`エラーが発生したり、コマンドがハングアップしたりします。

**解決策：`crane`ツールを使用する**

`crane`はGoogleのgo-containerregistryプロジェクトの一部であり、レジストリ間で直接イメージをコピーするツールです。イメージをローカルにプルすることなく、サーバーサイドでコピーを実行するため、安定性が高く、特にマルチアーキテクチャイメージの移動に適しています。

**Before（エラーが起きるコード）：**

```bash
# Docker Hubのプライベートリポジトリ間でイメージをコピーしようとする
docker buildx imagetools create \
  <source-repo>/<your-app>:dev \
  <destination-repo>/<your-partner-app>:latest
```

**After（修正後）：**

`crane`はDockerコンテナとして実行できるため、インストール不要で利用できます。

```bash
# craneをDockerコンテナとして実行し、イメージをコピー
docker run --rm gcr.io/go-containerregistry/crane:debug cp \
  <source-repo>/<your-app>:dev \
  <destination-repo>/<your-partner-app>:latest
```

### 原因2：マルチアーキテクチャイメージの構造破壊

従来の`docker pull` → `docker tag` → `docker push`という手順でイメージを移動すると、ローカル環境のアーキテクチャに依存してマルチアーキテクチャイメージのマニフェストが単一アーキテクチャに「フラット化」されてしまうリスクがあります。これにより、コピー先のイメージが意図したすべてのアーキテクチャをサポートしなくなる可能性があります。

**解決策：`crane`でマニフェストを維持する**

`crane cp`コマンドは、イメージインデックスをダイジェストによってコピーするため、マルチアーキテクチャのマニフェストを完全に維持します。

**Before（エラーが起きるコード）：**

```bash
# ローカルにプルしてリタグ・プッシュする（マルチアーキテクチャが失われる可能性）
docker pull <source-repo>/<your-app>:dev
docker tag <source-repo>/<your-app>:dev <destination-repo>/<your-partner-app>:latest
docker push <destination-repo>/<your-partner-app>:latest
```

**After（修正後）：**

```bash
# craneでマルチアーキテクチャマニフェストを維持したままコピー
docker run --rm gcr.io/go-containerregistry/crane:debug cp \
  <source-repo>/<your-app>:dev \
  <destination-repo>/<your-partner-app>:latest
```

### 原因3：認証情報の問題（特にmacOS）

`crane`をDockerコンテナとして実行する場合、ホストの`~/.docker/config.json`ファイルをマウントして認証情報を利用します。しかし、macOSのDocker Desktop環境では、認証情報が`osxkeychain`に保存されており、`~/.docker/config.json`には直接記述されていません。このため、単純にファイルをマウントすると`UNAUTHORIZED`エラーが発生します。

**解決策：一時的な認証情報ファイルを作成してマウントする**

macOSの場合、キーチェーンから認証情報を抽出し、一時的な`config.json`ファイルを生成して`crane`コンテナにマウントする必要があります。Linux環境など、`docker login`が直接`~/.docker/config.json`に認証情報を書き込む場合は、この手順は不要で、直接ファイルをマウントできます。

**Before（エラーが起きるコード）：**

```bash
# macOSで直接config.jsonをマウント（UNAUTHORIZEDエラーが発生する可能性）
docker run --rm -v ~/.docker/config.json:/root/.docker/config.json:ro \
  gcr.io/go-containerregistry/crane:debug cp \
  <source-repo>/<your-app>:dev \
  <destination-repo>/<your-partner-app>:latest
```

**After（修正後）：**

以下のスクリプトは、一時ディレクトリを作成し、macOSキーチェーンから認証情報を取得して`config.json`を生成、`crane`コンテナにマウントします。シェル終了時に一時ファイルは自動的に削除されます。

```bash
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/mkcfg.py" <<'PY'
import json, sys, base64
d = json.load(sys.stdin)
auth = base64.b64encode((d["Username"] + ":" + d["Secret"]).encode()).decode()
json.dump({"auths": {"https://index.docker.io/v1/": {"auth": auth}}}, open(sys.argv[1], "w"))
PY

echo "https://index.docker.io/v1/" | docker-credential-osxkeychain get | python3 "$TMP/mkcfg.py" "$TMP/config.json"

CRANE() {
  docker run --rm -v "$TMP/config.json":/root/.docker/config.json:ro \
             gcr.io/go-containerregistry/crane:debug "$@"
}

# CRANE関数を使ってイメージをコピー
CRANE cp <source-repo>/<your-app>:dev \
         <destination-repo>/<your-partner-app>:latest

# 別のタグも追加する場合
CRANE cp <source-repo>/<your-app>:dev \
         <destination-repo>/<your-partner-app>:dev-$(date +%Y-%m-%d)
```

## ツール固有の注意点

- **`crane`の実行環境**: `crane`はDockerコンテナとして実行できるため、ホストマシンにGoやその他の依存関係をインストールする必要がありません。これはCI/CDパイプラインでの利用において非常に便利です。
- **読み書き権限**: 宛先リポジトリへのプッシュには、適切な読み書き権限を持つ認証情報が必要です。読み取り専用トークンではプッシュできません。
- **イメージの検証**: コピーが成功したことを確認するために、コピー元とコピー先のイメージダイジェストが一致するかを必ず検証してください。`crane digest`コマンドを使用します。

```bash
CRANE digest <source-repo>/<your-app>:dev
CRANE digest <destination-repo>/<your-partner-app>:latest
CRANE digest <destination-repo>/<your-partner-app>:dev-$(date +%Y-%m-%d)
```
これらの出力がすべて一致すれば、正しくイメージがコピーされています。

- **タグの削除**: `crane`にはタグを削除する機能はありません。Docker HubのUIまたはAPIを使用して削除する必要があります。タグ削除には管理者権限を持つトークンが必要です。

## それでも解決しない場合

- **詳細ログの確認**: `crane`はデフォルトで詳細なログを出力しませんが、`docker run`コマンドに`--log-level debug`などのオプションを追加することで、Dockerデーモン側のログを確認できる場合があります。
- **レジストリのステータス確認**: 利用しているDockerレジストリ（例: Docker Hub）のステータスページを確認し、サービス障害が発生していないか確認してください。
- **公式ドキュメントの参照**:
    - `go-containerregistry/crane`のGitHubリポジトリ: [https://github.com/google/go-containerregistry/blob/main/cmd/crane/README.md](https://github.com/google/go-containerregistry/blob/main/cmd/crane/README.md)
    - Docker公式ドキュメント: [https://docs.docker.com/](https://docs.docker.com/)
- **認証情報の再確認**: 使用している認証情報が、コピー元とコピー先の両方のリポジトリに対して適切な権限を持っているか、有効期限が切れていないかなどを再確認してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*