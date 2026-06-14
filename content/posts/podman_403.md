---
title: "Podman の 403 エラー：原因と解決策"
date: 2026-05-29
description: "認証は成功したが、そのリソースへのアクセス権限がない。プライベートリポジトリへの読み取り・書き込み権限がないなど、Podman 403 エラーの原因と解決策を解説。"
tags: ["Podman"]
errorCode: "403"
service: "Podman"
error_type: "403"
components: []
related_services: ["Docker", "Docker Hub", "Quay.io", "SELinux"]
lastmod: 2026-06-14
---

## エラーの概要

Podman で 403 エラーが発生した場合、認証には成功していますがリソースへのアクセス権限がない状態です。プライベートレジストリへのアクセスやシステムのセキュリティポリシーが原因となることがほとんどです。Podman は Docker と互換性のあるコンテナランタイムですが、権限管理の厳密さから、Docker では許可されるアクセスが Podman では制限されることもあります。

## 実際のエラーメッセージ例

```json
{
  "error": "unauthorized: access denied",
  "status": 403,
  "message": "insufficient_scope"
}
```

```
Error: error pulling image "quay.io/myorg/myimage:latest": 
Error: error unmarshaling JSON: 
error decoding response body: json: line 1: 
invalid character '<' looking for beginning of value
```

```bash
WARN[0001] Failed to pull image "registry.example.com/app:v1.0": 
Error response from daemon: 403 Forbidden
```

## よくある原因と解決手順

### 原因1：プライベートレジストリの認証トークン期限切れ

Podman にログイン後、時間が経過して認証トークンが期限切れになると 403 が発生します。特に CI/CD パイプラインで古い認証情報を使用している場合に顕著です。

**Before（エラーが起きるコード）：**

```bash
# 1ヶ月前にログインした認証情報を使用したまま
podman pull quay.io/myorg/myimage:latest
# 403 Forbidden が返される
```

**After（修正後）：**

```bash
# 認証情報を再ログインで更新
podman login quay.io
# ユーザー名とパスワード（またはトークン）を入力
podman pull quay.io/myorg/myimage:latest
```

### 原因2：ユーザーのリポジトリアクセス権限がない

レジストリ上で対象リポジトリへの読み取り・書き込み権限を持たないユーザーでログインしている場合、403 が返されます。サービスアカウントやロボットアカウントの権限設定不足もここに含まれます。

**Before（エラーが起きるコード）：**

```bash
# 権限のないアカウントでログイン
podman login -u <limited-user> registry.example.com
# パスワード入力
podman push registry.example.com/restricted-repo/image:v1.0
# 403 Forbidden
```

**After（修正後）：**

```bash
# リポジトリへのアクセス権を持つアカウントでログイン
podman login -u <authorized-user> registry.example.com
# パスワード入力
podman push registry.example.com/restricted-repo/image:v1.0
```

### 原因3：Podman の rootless モード での SELinux/AppArmor ポリシー違反

Podman をルートレスモードで実行している場合、SELinux または AppArmor のセキュリティポリシーがネットワークアクセスやボリュームマウントを制限し、実質的に 403 に相当するエラーを発生させることがあります。

**Before（エラーが起きるコード）：**

```bash
# ルートレスモードで実行（SELinux が有効な環境）
podman run -v /data:/data:Z myimage:latest
# Permission denied に続き 403 相当のエラー
```

**After（修正後）：**

```bash
# SELinux ポリシーを確認し、必要に応じて調整
getenforce
# ルートレスモードで明示的に権限を付与
podman run -v /data:/data:Z --userns=keep-id myimage:latest
```

### 原因4：プライベートレジストリの HTTPS 証明書信頼設定

自己署名証明書を使用するプライベートレジストリに対して、Podman が証明書を信頼していない場合、403 ではなく「certificate verification failed」として表現されることもありますが、実質的なアクセス拒否です。

**Before（エラーが起きるコード）：**

```bash
podman pull registry.internal.company.com/app:latest
# error pulling image: x509: certificate signed by unknown authority
```

**After（修正後）：**

```bash
# CA 証明書を Podman の信頼ストアに追加
sudo cp ca-cert.crt /etc/pki/ca-trust/source/anchors/
sudo update-ca-trust

# または /etc/containers/registries.conf でスキップ（本番環境では非推奨）
sudo tee -a /etc/containers/registries.conf <<EOF
[[registry]]
location = "registry.internal.company.com"
insecure = true
EOF

podman pull registry.internal.company.com/app:latest
```

### 原因5：レジストリ側の IP アドレス制限

レジストリがクライアント IP をホワイトリスト制限している場合、認証済みでも特定の IP からのアクセスは 403 になります。VPN を経由していない環境や、CI/CD ランナーのグローバル IP が異なる場合に発生します。

**Before（エラーが起きるコード）：**

```bash
# ローカル環境では成功、CI/CD パイプラインでは 403
podman pull registry.example.com/secure-image:v1.0
# Error: 403 Forbidden （CI/CD ランナーから）
```

**After（修正後）：**

```bash
# レジストリの管理画面で CI/CD ランナーの IP をホワイトリストに追加
# または VPN 経由でアクセスする

# VPN 接続確認
ip addr show
# 信頼された IP レンジからの pull
podman pull registry.example.com/secure-image:v1.0
```

## Podman 固有の注意点

### ルートレス vs ルートモードでの権限差

Podman はルートレスモードでの実行が推奨されていますが、このモード では UID/GID マッピングが有効になり、コンテナ内で見える所有者が異なります。マウントしたボリュームへのアクセスで 403 が発生する場合、ユーザー名前空間の設定を確認してください。

```bash
# ルートレスモードの確認
podman info | grep rootless
# true が返されればルートレスモード

# UID マッピングの確認
cat /etc/subuid
# <username>:100000:65536 という記入があるか確認
```

### `$HOME/.config/containers/auth.json` の権限設定

Podman は ホームディレクトリ下の `auth.json` に認証情報を保存します。このファイルのパーミッションが不正（過度に開放されている）または読み取り不可の場合、認証情報が使用されず 403 になることがあります。

```bash
# auth.json のパーミッション確認（600 が正常）
ls -la ~/.config/containers/auth.json
# -rw------- が理想的

# パーミッション修正
chmod 600 ~/.config/containers/auth.json
```

### Podman Compose での認証コンテキスト

Podman Compose で複数のサービスを起動する場合、各サービスが異なるレジストリにアクセスするシナリオでは、`docker-compose.yml` に明示的に認証情報を渡す必要があります。

**Before（エラーが起きるコード）：**

```yaml
version: '3'
services:
  app:
    image: private-registry.com/myapp:latest
    # 認証情報が指定されていない
```

**After（修正後）：**

```yaml
version: '3'
services:
  app:
    image: private-registry.com/myapp:latest
    # ホストの認証情報を使用
    # または .env ファイルから読み込む
    build:
      context: .
      dockerfile: Dockerfile
```

実行時に `.env` ファイルで認証情報を管理：

```bash
# .env
REGISTRY_USERNAME=<your-username>
REGISTRY_PASSWORD=<your-password>

# Podman Compose 実行前にログイン
podman login -u $REGISTRY_USERNAME private-registry.com
```

## それでも解決しない場合

### ログの確認位置

Podman のデバッグログを有効にして詳細な エラー情報を取得してください。

```bash
# デバッグモードで Podman を実行
podman --log-level=debug pull <image>

# ジャーナルログで daemon ログを確認（rootless の場合）
journalctl --user-unit podman -n 100
```

### 公式ドキュメント参照

- [Podman Authentication Configuration](https://github.com/containers/image/blob/main/docs/containers-auth.json.5.md)
- [Podman rootless mode](https://docs.podman.io/en/latest/markdown/podman.1.html#rootless-mode)
- [Container Registry Authorization](https://docs.podman.io/en/latest/markdown/podman-login.1.html)

### コミュニティリソース

- [GitHub Issues - containers/podman](https://github.com/containers/podman/issues)
- [Red Hat Podman サポートドキュメント](https://access.redhat.com/documentation/ja-jp/red_hat_enterprise_linux/8/html/building_running_and_managing_containers/index)

レジストリの管理者に対して、アカウント権限の確認、IP ホワイトリストの追加、トークンの再発行を依頼することも有効です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*