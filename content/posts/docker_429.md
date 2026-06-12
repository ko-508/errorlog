---
title: "Docker の 429 エラー：原因と解決策"
date: 2026-01-01
description: "Docker の 429 エラーは、HTTP ステータスコード 429（Too Many Requests）を意味し、短時間に送信されたリクエスト数が上限を超えたことを示します。"
tags: ["Docker"]
errorCode: "429"
lastmod: 2026-05-31
service: "Docker"
error_type: "429"
components: ["Compose", "Registry"]
related_services: ["Docker Hub", "GitHub Actions", "Kubernetes"]
trend_incident: true
---

## エラーの概要

[Docker](/glossary/docker/) の 429 [エラー](/glossary/エラー/)は、[HTTP](/glossary/http/) [ステータスコード](/glossary/ステータスコード/) 429（Too Many Requests）を意味し、短時間に送信された[リクエスト](/glossary/リクエスト/)数が上限を超えたことを示します。[Docker](/glossary/docker/) Hub や[プライベートレジストリ](/glossary/プライベートレジストリ/)に対して過度なアクセスが集中した場合、[レート制限](/glossary/レート制限/)により一時的に[リクエスト](/glossary/リクエスト/)が拒否されます。特に [CI/CD](/glossary/ci-cd/) パイプラインや複数マシンからの並行アクセスで頻繁に発生します。

## 実際のエラーメッセージ例

[Docker](/glossary/docker/) [コマンド](/glossary/コマンド/)実行時のエラーメッセージ：

```
Error response from daemon: manifest unknown: manifest unknown
Error pulling image <your-image>: rate limit exceeded
```

[Docker](/glossary/docker/) Compose でのビルド時：

```json
{
  "error": "too many requests",
  "details": "You have reached your pull rate limit. You may increase the limit by authenticating and upgrading: https://www.docker.com/increase-rate-limits"
}
```

## よくある原因と解決手順

### 原因1：Docker Hub のレート制限に達している

[Docker](/glossary/docker/) Hub の無料プランでは、[認証](/glossary/認証/)なしで6時間に100回の pull に制限されています。[CI/CD](/glossary/ci-cd/) で頻繁に[イメージ](/glossary/イメージ/)をダウンロードする環境では、この上限に達しやすくなります。

**Before（[エラー](/glossary/エラー/)が起きる設定）：**

```bash
docker pull ubuntu:latest
docker pull nginx:latest
docker pull postgres:latest
# ... 100回以上のpullを短時間に実行
```

**After（修正後）：**

```bash
# Docker Hubにログイン（認証ユーザーは200リクエスト/6時間）
docker login -u <your-username> -p <your-password>

# その後、イメージを pull
docker pull ubuntu:latest
```

[ログイン](/glossary/ログイン/)情報を[環境変数](/glossary/環境変数/)で設定する場合：

```bash
echo "$DOCKER_PASSWORD" | docker login -u "$DOCKER_USERNAME" --password-stdin
docker pull <your-image>
```

### 原因2：CI/CD パイプラインで短時間に大量の pull が発生している

複数のジョブが並行して実行され、同じ[レジストリ](/glossary/レジストリ/)に対して同時にアクセスしている場合、[レート制限](/glossary/レート制限/)に引っかかります。

**Before（[エラー](/glossary/エラー/)が起きる設定）：**

```yaml
# .github/workflows/ci.yml
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        version: [1, 2, 3, 4, 5]
    steps:
      - name: Pull image
        run: docker pull <your-image>:v${{ matrix.version }}
```

**After（修正後）：**

```yaml
# .github/workflows/ci.yml
env:
  DOCKER_USERNAME: ${{ secrets.DOCKER_USERNAME }}
  DOCKER_PASSWORD: ${{ secrets.DOCKER_PASSWORD }}

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Login to Docker Hub
        run: |
          echo "$DOCKER_PASSWORD" | docker login -u "$DOCKER_USERNAME" --password-stdin
      - name: Pull image with concurrency control
        run: |
          for version in 1 2 3 4 5; do
            docker pull <your-image>:v$version
            sleep 2  # リクエスト間隔を設ける
          done
```

### 原因3：複数マシンから同時にレジストリにアクセスしている

ローカルネットワークや [Kubernetes](/glossary/kubernetes/) クラスタ内で複数ノードが同時に同じ[イメージ](/glossary/イメージ/)をダウンロードしている場合、集約的なアクセスが[レート制限](/glossary/レート制限/)を超えます。

**Before（[エラー](/glossary/エラー/)が起きる設定）：**

```yaml
# docker-compose.yml
services:
  app1:
    image: <your-registry>/<your-image>:latest
  app2:
    image: <your-registry>/<your-image>:latest
  app3:
    image: <your-registry>/<your-image>:latest

# 3つのコンテナが同時に起動 → 同じイメージを3回 pull
```

**After（修正後）：**

```yaml
# docker-compose.yml
services:
  app1:
    image: <your-registry>/<your-image>:latest
  app2:
    image: <your-registry>/<your-image>:latest
  app3:
    image: <your-registry>/<your-image>:latest

# イメージを事前に pull してキャッシュ
# docker pull <your-registry>/<your-image>:latest
# その後、docker-compose up -d で起動（pull はスキップされる）
```

より確実な解決：

```bash
# 事前にすべてのマシンでイメージをプリロード
docker pull <your-registry>/<your-image>:latest

# Docker Compose では pull ポリシーを制御
docker-compose up -d --pull never
```

## ツール固有の注意点

### Docker レジストリの認証設定

[Docker](/glossary/docker/) Hub 以外の[プライベートレジストリ](/glossary/プライベートレジストリ/)を使用する場合、`~/.docker/config.json` で認証情報を設定することで、[レート制限](/glossary/レート制限/)を回避できる場合があります。

```bash
# プライベートレジストリにログイン
docker login <your-registry.com>
```

[設定ファイル](/glossary/設定ファイル/)は自動生成され、以後のアクセスで[認証](/glossary/認証/)が有効になります。

### Docker Build のキャッシュ戦略

`docker build` 時に複数のベースイメージを使用する場合、イメージキャッシュを活用してレジストリアクセスを削減できます。

```dockerfile
# 複数ステージビルドでベースイメージの pull 回数を削減
FROM ubuntu:22.04 as builder
RUN apt-get update && apt-get install -y build-essential

FROM ubuntu:22.04
COPY --from=builder /usr/bin/gcc /usr/bin/gcc
```

### Kubernetes での image pull policy

[Kubernetes](/glossary/kubernetes/) を使用する場合、`imagePullPolicy` を `IfNotPresent` に設定して、ノード上に[キャッシュ](/glossary/キャッシュ/)された[イメージ](/glossary/イメージ/)を優先的に使用します。

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: example
spec:
  containers:
  - name: app
    image: <your-image>:latest
    imagePullPolicy: IfNotPresent  # ローカルキャッシュを優先
```

## それでも解決しない場合

### デバッグコマンド

現在のレート制限状態を確認：

```bash
# Docker Hub API で残りリクエスト数を確認
curl -i https://hub.docker.com/v2/
# レスポンスヘッダの RateLimit-* を確認
```

ローカルのイメージキャッシュを確認：

```bash
docker images | grep <your-image>
```

### 公式ドキュメント参照

- [Docker Hub Rate Limiting](https://docs.docker.com/docker-hub/rate-limiting/)：[レート制限](/glossary/レート制限/)の詳細仕様
- [Docker Engine API Reference](https://docs.docker.com/engine/api/)：[REST](/glossary/rest/) [API](/glossary/api/) の詳細

### コミュニティリソース

GitHub Issues で同様の問題を検索：

```bash
# Docker 公式リポジトリで issue を検索
# https://github.com/moby/moby/issues?q=429+rate+limit
```

Stackoverflow や [Docker](/glossary/docker/) Community Forums でも、実装例や回避方法が共有されています。[Docker](/glossary/docker/) Pro/Team プランへのアップグレードも検討に値します。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*