---
title: "Podman の 401 エラー：原因と解決策"
date: 2026-05-28
lastmod: 2026-06-14
description: "Podmanでコンテナイメージをpullやpushしようとすると、401認証エラーが発生することがあります。このエラーはレジストリへの認証に失敗したときに出現し、適切な認証情報がないか有効期限切れの状態を示しています。"
tags: ["Podman"]
errorCode: "401"
service: "Podman"
error_type: "401"
components: []
related_services: ["Docker Hub", "GCR"]
---

## エラーの概要

Podmanでコンテナイメージをpullやpushしようとすると、401認証エラーが発生することがあります。このエラーはレジストリへの認証に失敗したときに出現し、適切な認証情報がないか、あるいは有効期限切れの状態を示しています。Docker互換性を重視するPodmanでも認証メカニズムは同様であり、レジストリごとに異なる認証情報を管理する必要があります。

## 実際のエラーメッセージ例

```
Error: initializing source docker://registry.example.com/myimage:latest: pinging docker registry v2: responding with status 401 Unauthorized
```

```json
{
  "error": "unauthorized",
  "error_description": "authentication required",
  "status": 401
}
```

```
WARN[0000] Failed to authenticate to registry.example.com: 401 Unauthorized
error pulling image "registry.example.com/myimage:latest": unable to pull registry.example.com/myimage:latest: Error response from daemon: unauthorized: authentication required
```

## よくある原因と解決手順

### 原因1: podman loginを実行していない

Podmanでレジストリからイメージを取得するには、事前に認証を完了する必要があります。ログイン処理を行わずにpullコマンドを実行すると、認証情報がないため401エラーが発生します。特に新しい環境構築時や別のレジストリを利用する場合に見落とされやすいです。

**Before（エラーが起きるコード）：**

```bash
podman pull registry.example.com/myimage:latest
# Error: initializing source docker://registry.example.com/myimage:latest: pinging docker registry v2: responding with status 401 Unauthorized
```

**After（修正後）：**

```bash
podman login registry.example.com
# username: <your-username>
# password: <your-password>
podman pull registry.example.com/myimage:latest
```

### 原因2: 認証トークンの有効期限が切れている

レジストリが発行した認証トークンには有効期限があります。特にGitHub Container RegistryやDocker Hubの一時トークンは短期間で失効するため、古い認証情報が `~/.config/containers/auth.json` に残っていると401エラーが起きます。

**Before（エラーが起きるコード）：**

```bash
# 数週間前にログインした古い認証情報で実行
podman pull ghcr.io/myorg/myimage:latest
# Error: responding with status 401 Unauthorized
```

**After（修正後）：**

```bash
# 既存の認証情報をクリア
podman logout ghcr.io

# 新しく再認証
podman login ghcr.io
# username: <your-username>
# password: <your-token>

podman pull ghcr.io/myorg/myimage:latest
```

### 原因3: 認証情報の形式が間違っている

Podmanの `auth.json` ファイルが破損していたり、手動編集で不正な形式になっていたりすると、レジストリが認証情報を正しく解析できず401エラーが発生します。特にBase64エンコーディングが不完全な場合に問題が生じやすいです。

**Before（エラーが起きるコード）：**

```yaml
# ~/.config/containers/auth.json の例（不正な形式）
{
  "auths": {
    "registry.example.com": {
      "auth": "dXNlcm5hbWU6cGFzc3dvcmQ"  # Base64エンコーディングが不完全
    }
  }
}
```

**After（修正後）：**

```bash
# auth.jsonをリセット
rm ~/.config/containers/auth.json

# podman loginで正しい形式で再作成
podman login registry.example.com
# username: <your-username>
# password: <your-password>

# 確認: auth.jsonが正しい構造になっている
test -f ~/.config/containers/auth.json && echo "認証ファイルが作成されました"
```

### 原因4: 使用しているユーザーアカウントが異なっている

Podmanは各ユーザーごとに独立した認証情報を `~/.config/containers/auth.json` に保存します。root権限で実行する場合と通常ユーザーで実行する場合で、異なる認証情報を使うことになり、一方がログイン済みでも他方は未認証状態になる可能性があります。

**Before（エラーが起きるコード）：**

```bash
# 通常ユーザーでログイン
podman login registry.example.com

# root権限で実行（別の認証情報を参照）
sudo podman pull registry.example.com/myimage:latest
# Error: responding with status 401 Unauthorized
```

**After（修正後）：**

```bash
# root権限でログイン
sudo podman login registry.example.com
# username: <your-username>
# password: <your-password>

# その後、root権限で実行
sudo podman pull registry.example.com/myimage:latest
```

## Podman固有の注意点

**auth.json のパーミッション管理**: Podmanの認証情報ファイルは自動的にパーミッション600で作成されますが、手動編集後にパーミッションが広げられていると、セキュリティの問題で認証が拒否される場合があります。編集後は `chmod 600 ~/.config/containers/auth.json` で確認してください。

**マルチアーキテクチャイメージの取得**: Podman 4.0以降では、異なるプラットフォーム向けイメージを取得する際、レジストリが厳格な認証を要求することがあります。プライベートレジストリの場合、必ず適切なユーザーで `podman login` してください。

**Podman Desktopでの認証**: Podman Desktopを使用している場合、GUIの認証管理が有効ですが、コマンドラインから直接 `podman` コマンドを実行する場合は、コマンドラインでも別途 `podman login` が必要です。GUIでのログインだけでは不十分です。

**ホスト間での auth.json の複製**: 複数のホストで同じ認証情報を使う場合、セキュアではない方法（平文でのコピー）は避け、各ホストで独立して `podman login` を実行してください。

## それでも解決しない場合

**デバッグログの確認**: `PODMAN_LOG_LEVEL=debug podman pull <image>` でデバッグログを出力し、認証ヘッダーがどう送信されているかを確認してください。

**レジストリのログ確認**: プライベートレジストリを運用している場合、レジストリサーバー側のログで拒否理由を確認できます。例えばRegistry V2の標準実装では `/var/log/registry/` 配下にアクセスログが記録されます。

**ネットワーク接続の確認**: ファイアウォールやプロキシが認証リクエストをブロックしていないか、`curl -v https://registry.example.com/v2/` でHTTP応答を確認してください。

**公式ドキュメント参照**:
- [Podman ログイン - 公式ドキュメント](https://docs.podman.io/en/latest/markdown/podman-login.1.html)
- [認証設定 - containers-auth.json](https://github.com/containers/image/blob/main/docs/containers-auth.json.5.md)

**コミュニティリソース**:
- [Podman GitHub Issues - 認証関連](https://github.com/containers/podman/issues?q=is%3Aissue+401)
- [Red Hat Forum - Podmanコミュニティ](https://access.redhat.com/discussions/)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*