---
title: "Bitbucket の 403 エラー：原因と解決策"
date: 2026-06-15
description: "リポジトリまたはリソースへのアクセス権限がない"
tags: ["Bitbucket"]
errorCode: "403"
service: "Bitbucket"
error_type: "403"
components: []
related_services: ["Git", "REST API", "VPN", "Workspace"]
---
## エラーの概要

Bitbucket の 403 [エラー](/glossary/エラー/)は、[認証](/glossary/認証/)されたユーザーが[リポジトリ](/glossary/リポジトリ/)またはリソースへの[アクセス権限](/glossary/アクセス権限/)を持っていないことを示します。つまり、ユーザーが存在し、Bitbucket に正常に[ログイン](/glossary/ログイン/)できているものの、特定の[リポジトリ](/glossary/リポジトリ/)への操作権限が不足している状態です。この[エラー](/glossary/エラー/)は [Git](/glossary/git/) push、pull、または[リポジトリ](/glossary/リポジトリ/)設定変更時に頻繁に発生します。

## 実際のエラーメッセージ例

**[Git](/glossary/git/) [コマンド](/glossary/コマンド/)実行時:**

```
remote: PERMISSION_DENIED: User <user@example.com> has insufficient permissions to access <workspace>/<repository>
fatal: unable to access 'https://bitbucket.org/<workspace>/<repository>.git/': The requested URL returned error: 403
```

**[REST](/glossary/rest/) [API](/glossary/api/) 呼び出し時:**

```json
{
  "type": "error",
  "error": {
    "message": "You do not have permission to access this resource",
    "detail": "User does not have write access to this repository"
  },
  "status": 403
}
```

## よくある原因と解決手順

### 原因1：リポジトリへの必要な権限が付与されていない

[リポジトリ](/glossary/リポジトリ/)へのアクセスレベルが読み取り専用（Read）に制限されている場合、push や設定変更などの書き込み操作は拒否されます。特にチームメンバーとして新たに追加されたユーザーや、[権限](/glossary/権限/)が削除されたユーザーで発生しやすいです。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
git push origin feature-branch
# remote: PERMISSION_DENIED: You do not have write access
# fatal: unable to access '...': The requested URL returned error: 403
```

**After（修正後）：**

```bash
# 1. Bitbucket Web UI でリポジトリを開く
# 2. リポジトリ設定（Repository settings）を開き、
#    「リポジトリのアクセス権（Repository permissions）」
#    または「アクセス管理（Access management）」から権限を調整
# 3. 該当ユーザーのロールを "Write" または "Admin" に変更
# 4. その後、再度 push を実行
git push origin feature-branch
# 正常に push が完了
```

Workspace 管理者は、対象[リポジトリ](/glossary/リポジトリ/)のアクセス管理セクションにアクセスし、ユーザーの[ロール](/glossary/ロール/)（Read、Write、Admin）を確認・変更できます。Read では pull のみ可能で、write [権限](/glossary/権限/)を付与することで push が可能になります。

### 原因2：IP ホワイトリストの設定でアクセスがブロックされている

組織が IP ホワイトリストを有効にしている場合、許可された[ネットワーク](/glossary/ネットワーク/)範囲外からのアクセスは 403 [エラー](/glossary/エラー/)で拒否されます。VPN 接続の切り替えや、リモートワーク環境への移行時に発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# 自宅のネットワーク（192.168.1.100）から push を試みる
git push origin main
# remote: PERMISSION_DENIED: IP address not whitelisted
# fatal: unable to access '...': The requested URL returned error: 403
```

**After（修正後）：**

```bash
# 1. Workspace 管理者が Settings → IP Whitelisting に移動
# 2. 現在の IP アドレスを確認: https://www.whatismyipaddress.com/
# 3. ホワイトリストに IP アドレス範囲（例: 203.0.113.0/24）を追加
# 4. 保存後、再度 push を実行
git push origin main
# 正常に push が完了
```

IP ホワイトリストは Workspace レベルで設定されており、Workspace 管理者のみが変更可能です。詳細は Workspace Settings → IP Whitelisting で確認できます。

### 原因3：チーム Project 管理者のみが実行できる操作を試みている

[リポジトリ](/glossary/リポジトリ/)の削除、保護[ブランチ](/glossary/ブランチ/)の設定変更、[デプロイ](/glossary/デプロイ/)キーの管理など、特定の操作は Admin [ロール](/glossary/ロール/)を持つユーザーのみが実行可能です。Write [権限](/glossary/権限/)ユーザーが管理機能にアクセスしようとすると 403 [エラー](/glossary/エラー/)が発生します。

**Before（[エラー](/glossary/エラー/)が起きるコード）：**

```bash
# リポジトリ設定を変更しようとする（Admin 権限が必要）
curl -X PUT https://api.bitbucket.org/2.0/repositories/<workspace>/<repository> \
  -H "Authorization: Bearer <your-access-token>" \
  -H "Content-Type: application/json" \
  -d '{"is_private": false}'

# Response: 403 Forbidden
# "You do not have permission to modify repository settings"
```

**After（修正後）：**

```bash
# 方法1: Workspace 管理者にロール昇格を依頼
# リポジトリのアクセス管理からロールを "Admin" に変更

# 方法2: Workspace 管理者が代理実行
curl -X PUT https://api.bitbucket.org/2.0/repositories/<workspace>/<repository> \
  -H "Authorization: Bearer <your-admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"is_private": false}'

# Response: 200 OK - 正常に設定が更新される
```

[リポジトリ](/glossary/リポジトリ/)の Admin [ロール](/glossary/ロール/)付与は Workspace 管理者によってのみ実行されます。必要な操作が Admin [権限](/glossary/権限/)を必要とする場合は、Workspace 管理者に依頼する必要があります。

## ツール固有の注意点

**Workspace と Repository の[ロール](/glossary/ロール/)区別：** Bitbucket では Workspace レベルと Repository レベルで異なる[ロール](/glossary/ロール/)設定を持ちます。Workspace 管理者でも、特定[リポジトリ](/glossary/リポジトリ/)に対して Read [ロール](/glossary/ロール/)のみが付与されている場合は、その[リポジトリ](/glossary/リポジトリ/)に対する write 操作は 403 [エラー](/glossary/エラー/)で拒否されます。

**[API](/glossary/api/) アクセストークンの[権限](/glossary/権限/)：** [REST](/glossary/rest/) [API](/glossary/api/) を使用する場合、Personal Access Token または App Password が持つ[スコープ](/glossary/スコープ/)[権限](/glossary/権限/)も確認が必要です。[トークン](/glossary/トークン/)生成時に `repository:write` [スコープ](/glossary/スコープ/)を付与していない場合、[API](/glossary/api/) 経由での push や[コミット](/glossary/コミット/)作成は 403 で失敗します。

**デプロイキーと SSH アクセス：** SSH キーが[リポジトリ](/glossary/リポジトリ/)固有のデプロイキーとして登録されている場合、そのキーの[権限](/glossary/権限/)レベル（Read-only または Write）も考慮されます。[CI/CD](/glossary/ci-cd/) パイプラインから push が 403 で失敗する場合は、デプロイキーの[権限](/glossary/権限/)を確認してください。

## それでも解決しない場合

1. **権限状態を再確認する：** Bitbucket Web UI のリポジトリアクセス管理ページを開き、ブラウザの[キャッシュ](/glossary/キャッシュ/)をクリアして再度アクセスしてください。権限変更が反映されるまで数分かかる場合があります。

2. **[キャッシュ](/glossary/キャッシュ/)された認証情報をリセットする：** [Git](/glossary/git/) の認証情報マネージャーが古いアクセストークンを[キャッシュ](/glossary/キャッシュ/)していないか確認します。

   ```[bash](/glossary/bash/)
   # Windows（Credential Manager）
   git credential-manager erase https://bitbucket.org
   
   # macOS（Keychain）
   security delete-internet-password -s bitbucket.org
   
   # Linux（[キャッシュ](/glossary/キャッシュ/)をクリア）
   git credential reject https://bitbucket.org
   ```

3. **[API](/glossary/api/) [レスポンス](/glossary/レスポンス/)詳細を確認する：** curl で Bitbucket [API](/glossary/api/) を直接呼び出し、より詳細な[エラーメッセージ](/glossary/エラーメッセージ/)を確認します。

   ```[bash](/glossary/bash/)
   curl -v -u <your-username>:<your-password> \
     https://api.bitbucket.org/2.0/repositories/<workspace>/<repository>
   ```

4. **Workspace 管理者に監査[ログ](/glossary/ログ/)を確認させる：** Workspace Settings → Audit log で、ユーザーの権限変更履歴が正確に記録されているか確認できます。

5. **公式サポートに問い合わせる：** 上記の手順でも解決しない場合は、[Bitbucket Cloud サポート](https://support.atlassian.com/bitbucket-cloud/)に問い合わせてください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*