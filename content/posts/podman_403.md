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
---
Podman で 403 [エラー](/glossary/エラー/)が発生した場合、[認証](/glossary/認証/)には成功していますがリソースへの[アクセス権限](/glossary/アクセス権限/)がない状態です。プライベートリポジトリへのアクセスやシステムのセキュリティポリシーが原因となることがほとんどです。

## よくある原因

**プライベートリポジトリへの権限不足**

プライベートコンテナレジストリ（Quay.io、[Docker](/glossary/docker/) Hub のプライベートリポジトリ、組織内[レジストリ](/glossary/レジストリ/)など）に対して、[ログイン](/glossary/ログイン/)済みのユーザーが読み取り・書き込み[権限](/glossary/権限/)を持たないために発生します。[認証](/glossary/認証/)[トークン](/glossary/トークン/)や[クレデンシャル](/glossary/クレデンシャル/)（認証情報）は有効ですが、そのユーザー・[サービスアカウント](/glossary/サービスアカウント/)（プログラムが用いるアカウント）が対象[リポジトリ](/glossary/リポジトリ/)へのアクセス許可を受けていないため、403 が返されます。

**コンテナレジストリの組織[ポリシー](/glossary/ポリシー/)制限**

企業内のコンテナレジストリでは、チームごと・プロジェクトごとに[アクセス権限](/glossary/アクセス権限/)を分けていることがあります。あなたのユーザーアカウントがそのチームに属していない、または組織の設定で該当[リポジトリ](/glossary/リポジトリ/)へのアクセスが明示的に禁止されている場合に 403 が発生します。

**SELinux の[ポリシー](/glossary/ポリシー/)がコンテナプロセスをブロック**

Red Hat 系の Linux（RHEL、CentOS、Fedora など）で SELinux が有効な場合、コンテナプロセスがホストのファイルシステムやネットワークリソースへのアクセスを SELinux [ポリシー](/glossary/ポリシー/)で拒否されることがあります。[認証](/glossary/認証/)は Podman で成功していても、SELinux の粒度の細かいアクセス制御により、403 相当の動作となります。

## 解決手順

**ステップ 1：認証情報が正しく保存されているか確認**

まず、Podman に登録されている[ログイン](/glossary/ログイン/)情報を確認します。

```bash
podman login <registry-url>
```

プロンプトでユーザー名と[パスワード](/glossary/パスワード/)（またはアクセストークン）を入力し、[ログイン](/glossary/ログイン/)に成功することを確認してください。[ログイン](/glossary/ログイン/)情報は `~/.config/containers/auth.json` に保存されます。

**ステップ 2：[リポジトリ](/glossary/リポジトリ/)[権限](/glossary/権限/)をコンテナレジストリの管理画面で確認**

[Docker](/glossary/docker/) Hub、Quay.io などの[レジストリ](/glossary/レジストリ/)の Web UI に[ログイン](/glossary/ログイン/)して、対象[リポジトリ](/glossary/リポジトリ/)の権限設定を確認します。

- **[Docker](/glossary/docker/) Hub：** アカウント設定 → Organizations → 対象組織 → Members で、自分の[ロール](/glossary/ロール/)（Owner、Write、Read など）を確認
- **Quay.io：** Settings → Permissions タブで、チームメンバーシップと[権限](/glossary/権限/)レベルを確認
- **組織内[レジストリ](/glossary/レジストリ/)：** 管理者に権限付与を依頼

ここで自分のアカウントが「Read（読み取り）」のみであれば、プッシュはできません。必要に応じてリポジトリオーナーに権限昇格を依頼してください。

**ステップ 3：SELinux が有効な環境での場合、[ポリシー](/glossary/ポリシー/)を一時的に無効化して検証**

SELinux が有効な場合、以下の[コマンド](/glossary/コマンド/)で[コンテナ](/glossary/コンテナ/)の SELinux ラベリングを無効化して実行してみます。

```bash
podman run --security-opt label=disable -it <image-name> /bin/sh
```

この[コマンド](/glossary/コマンド/)で 403 [エラー](/glossary/エラー/)が消える場合、SELinux の[ポリシー](/glossary/ポリシー/)が原因です。本番環境では `label=disable` 全体の無効化ではなく、より限定的な[ポリシー](/glossary/ポリシー/)調整をセキュリティチームに相談してください。

**ステップ 4：プル・プッシュ操作を再実行**

権限確認後、改めて Podman でプル・プッシュを試みます。

```bash
# プル
podman pull <registry-url>/<repository>:<tag>

# プッシュ
podman push <local-image-name> <registry-url>/<repository>:<tag>
```

[レジストリ](/glossary/レジストリ/) URL は `quay.io`、`docker.io`、または企業内[レジストリ](/glossary/レジストリ/)のホスト名などです。

**ステップ 5：ログインキャッシュをクリアして再認証**

既存の認証情報が古い、または破損している可能性があります。

```bash
podman logout <registry-url>
podman login <registry-url>
```

その後、再度プル・プッシュを試します。

## それでも解決しない場合

- **Podman のバージョンを確認：** `podman --version` で古いバージョンを使用していないか確認し、必要に応じてアップデートしてください。
- **[プロキシ](/glossary/プロキシ/)・[ファイアウォール](/glossary/ファイアウォール/)経由のアクセス：** 企業[ネットワーク](/glossary/ネットワーク/)内からのアクセスの場合、[プロキシ](/glossary/プロキシ/)設定が `~/.config/containers/registries.conf` に正しく記述されているか確認してください。
- **コンテナレジストリの管理者に問い合わせ：** [リポジトリ](/glossary/リポジトリ/)の権限設定が正しく機能しているか、[レジストリ](/glossary/レジストリ/)側のアクセスログを確認してもらうことで、より詳細な拒否理由が判明することもあります。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*