---
title: "Docker の 422 エラー：原因と解決策"
date: 2026-01-01
description: "Docker で 422 エラーが発生するのは、Docker API またはコンテナレジストリへのリクエストが構文的には正しいものの、含まれるデータが処理要件を満たしていない場合です。"
tags: ["Docker"]
errorCode: "422"
lastmod: 2026-05-31
service: "Docker"
error_type: "422"
components: ["Compose", "Registry", "Daemon"]
related_services: ["Docker API"]
trend_incident: true
---
## エラーの概要

[Docker](/glossary/docker/)で 422 [エラー](/glossary/エラー/)が発生するのは、[Docker](/glossary/docker/) [API](/glossary/api/)またはコンテナレジストリへの[リクエスト](/glossary/リクエスト/)が構文的には正しいものの、含まれるデータが処理要件を満たしていない場合です。[Docker](/glossary/docker/) Daemon、[Docker](/glossary/docker/) Compose、[レジストリ](/glossary/レジストリ/) [API](/glossary/api/)との通信時にこの[エラー](/glossary/エラー/)が返される典型的なシナリオは、不正なイメージタグ指定、設定値の型違反、あるいは [API](/glossary/api/)[スキーマ](/glossary/スキーマ/)の検証失敗です。

## 実際のエラーメッセージ例

```json
{
  "message": "invalid tag format",
  "code": 422
}
```

```bash
$ docker push myregistry.example.com/app:invalid@tag
Error response from daemon: invalid tag format
```

```yaml
# docker-compose.yml でエラーが発生
ERROR: The Compose file is invalid because:
Service 'web' has invalid value for ports: ports must be an integer or string
```

## よくある原因と解決手順

### 1. イメージタグの形式が不正

[Docker](/glossary/docker/)[レジストリ](/glossary/レジストリ/) [API](/glossary/api/)は [RFC](/glossary/rfc/) 6391 に基づいたタグ形式を要求します。許可されない文字（`@`や大文字の混在）が含まれている場合に 422 が返されます。

**Before（[エラー](/glossary/エラー/)が起きる例）：**
```bash
docker tag myimage:latest myregistry.example.com/app:INVALID@latest
docker push myregistry.example.com/app:INVALID@latest
# Error: invalid tag format
```

**After（修正後）：**
```bash
# タグは小文字のみで、「:」で区切る
docker tag myimage:latest myregistry.example.com/app:v1.0.0
docker push myregistry.example.com/app:v1.0.0
```

### 2. docker-compose.yml の設定値の型違反

`ports`、`mem_limit`、`cpu_shares`など、数値型を期待するフィールドに文字列を指定すると[バリデーション](/glossary/バリデーション/)失敗で 422 が返されます。

**Before（[エラー](/glossary/エラー/)が起きる例）：**
```yaml
version: '3.8'
services:
  web:
    image: nginx:latest
    ports:
      - "8080"  # 文字列のままだと型エラー
    mem_limit: "512"  # 文字列だと失敗する場合がある
```

**After（修正後）：**
```yaml
version: '3.8'
services:
  web:
    image: nginx:latest
    ports:
      - "8080:80"  # ホストポート:コンテナポートの形式
    mem_limit: 536870912  # バイト単位の数値、または "512m" 形式の文字列
```

### 3. マニフェスト JSON の構造が不正

[Docker](/glossary/docker/)[イメージ](/glossary/イメージ/)をプッシュする際に、レイヤーのダイジェスト値が不正な形式である場合、[レジストリ](/glossary/レジストリ/)が 422 で拒否します。

**Before（[エラー](/glossary/エラー/)が起きる例）：**
```bash
# イメージをビルド中に破損したマニフェスト参照
docker build -t myapp:broken .
docker push myregistry.example.com/myapp:broken
# Error: invalid manifest: sha256: invalid digest
```

**After（修正後）：**
```bash
# イメージを再度ビルドしてプッシュ
docker build -t myregistry.example.com/myapp:v1.0.0 .
docker push myregistry.example.com/myapp:v1.0.0
# 正規のダイジェスト形式で処理されます
```

### 4. API リクエストのボディスキーマ不整合

[Docker](/glossary/docker/) [API](/glossary/api/)（例：`/containers/create`）に POST [リクエスト](/glossary/リクエスト/)を送る際、必須フィールドが欠落しているか、型が異なると[バリデーション](/glossary/バリデーション/)失敗で 422 が返されます。

**Before（[エラー](/glossary/エラー/)が起きる例）：**
```bash
curl -X POST http://localhost:2375/containers/create \
  -H "Content-Type: application/json" \
  -d '{"Hostname": "test"}'
# 422: ExposedPorts must be a map
```

**After（修正後）：**
```bash
curl -X POST http://localhost:2375/containers/create \
  -H "Content-Type: application/json" \
  -d '{
    "Image": "ubuntu:latest",
    "Hostname": "test",
    "ExposedPorts": {}
  }'
```

## Docker 固有の注意点

### Docker Compose バージョンと設定値の互換性

`docker-compose.yml`で `version: '3.8'`を指定した場合、古い構文（`1.0`時代の短縮[ポート](/glossary/ポート/)指定）は 422 で拒否されます。[バージョン](/glossary/バージョン/)と設定内容の整合性を確認してください。

### レジストリ認証後のプッシュ時エラー

[Docker](/glossary/docker/) Hub や Private Registry に[ログイン](/glossary/ログイン/)後、プッシュ時に 422 が出る場合は、[イメージ](/glossary/イメージ/)名が登録済みプロジェクトのパス構造に一致しているか確認します。

```bash
# 認証は成功したが 422 エラーが出る場合
docker login -u <username> myregistry.example.com

# プッシュ前にタグ形式をチェック
docker image ls | grep myimage
# タグが完全なレジストリパスになっているか確認
```

### BuildKit キャッシュとダイジェスト値

`DOCKER_BUILDKIT=1`を使用している場合、キャッシュレイヤーのダイジェスト不整合で 422 が発生することがあります。この場合は `--no-cache`フラグを使用してビルドを再実行してください。

```bash
DOCKER_BUILDKIT=1 docker build --no-cache -t myapp:v1 .
```

## それでも解決しない場合

### ログ確認とデバッグコマンド

[Docker](/glossary/docker/) Daemon の[ログ](/glossary/ログ/)を確認し、より詳細な[エラー](/glossary/エラー/)情報を取得します。

```bash
# systemd でコンテナを実行している場合
journalctl -u docker -f

# macOS / Windows の Docker Desktop の場合
cat ~/.docker/daemon.json | jq .

# Docker API への直接リクエストをテスト
curl -v --unix-socket /var/run/docker.sock \
  -X GET http://localhost/version
```

### 公式ドキュメント参照

[Docker](/glossary/docker/) Compose 設定リファレンス（https://docs.docker.com/compose/compose-file/）で、各フィールドの型と制約を確認してください。API [スキーマ](/glossary/スキーマ/)検証[エラー](/glossary/エラー/)の場合は「[Docker](/glossary/docker/) Engine [API](/glossary/api/)」ドキュメントの `POST /containers/create`セクションを参照します。

### 環境別の確認ポイント

- **Private Registry 使用時**: [レジストリ](/glossary/レジストリ/)の [API](/glossary/api/)[バージョン](/glossary/バージョン/)を確認し、サポートされているイメージマニフェスト形式を検証します
- **[Kubernetes](/glossary/kubernetes/)経由での[デプロイ](/glossary/デプロイ/)**: `imagePullPolicy`設定とイメージレジストリの [CORS](/glossary/cors/)設定を確認します
- **[CI/CD](/glossary/ci-cd/)パイプライン**: GitHub Actions や GitLab CI のアーティファクトストレージ設定を見直し、イメージダイジェストの計算ロジックを[テスト](/glossary/テスト/)します

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*