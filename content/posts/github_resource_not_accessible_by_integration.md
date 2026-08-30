---
title: "GitHub Actions権限エラー：原因と解決策"
date: 2026-08-05T00:00:00+09:00
description: "Resource not accessible by integration は、GitHub ActionsのGITHUB_TOKENにAPI操作の権限がないときに返る403です。まず失敗した操作と必要なpermissionsを対応させます。フォークやDependabotでは書き込み権限を追加できない場合があります。"
tags: ["GitHub"]
images: ["og/posts/github_resource_not_accessible_by_integration.png"]
errorCode: "Resource not accessible by integration"
lastmod: 2026-08-05T00:00:00+09:00
service: "GitHub"
error_type: "ResourceNotAccessibleByIntegration"
components: ["GITHUB_TOKEN", "Workflow permissions", "GitHub REST API"]
related_services: ["GitHub Actions", "Dependabot", "GitHub App"]
trend_incident: false
---

## 冒頭まとめ

[GitHub](/glossary/github/) Actionsで次の[エラー](/glossary/エラー/)が出た場合、[API](/glossary/api/)が壊れているのではなく、[リクエスト](/glossary/リクエスト/)に使った[トークン](/glossary/トークン/)がその操作を許可されていません。

```text
RequestError [HttpError]: Resource not accessible by integration
status: 403
```

同じ[リポジトリ](/glossary/リポジトリ/)で、`push` や組織内部からの実行が起点なら、解決は失敗した操作に対応する [`permissions`](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#permissions) を[ワークフロー](/glossary/ワークフロー/)へ追加することです。

たとえば、[コード](/glossary/コード/)を読み、IssueとPull Requestへ書き込むジョブなら次のようにします。

```yaml
permissions:
  contents: read
  issues: write
  pull-requests: write
```

必要な[権限](/glossary/権限/)は操作ごとに違います。

```text
リポジトリをcheckoutする         → contents: read
コミット、タグ、Releaseを書く    → contents: write
Issueへ書く                      → issues: write
Pull Requestへ書く               → pull-requests: write
Check Runを作る                  → checks: write
commit statusを書く              → statuses: write
コードスキャン結果を送る         → security-events: write
パッケージを公開する             → packages: write
OIDCトークンを発行する            → id-token: write
```

ただし、`permissions` を書けば必ず直るわけではありません。次の実行では、[ワークフロー](/glossary/ワークフロー/)側から書き込み[権限](/glossary/権限/)へ引き上げられないことがあります。

```text
外部フォークからのpull_request
Dependabotが作成したPull Request
呼び出し元が権限を与えていない再利用ワークフロー
GITHUB_TOKENの対象外である別リポジトリや組織資源への操作
```

特に、外部フォークの失敗を直すために `pull_request_target` へ置き換え、Pull Request側の[コード](/glossary/コード/)をcheckoutして実行するのは危険です。書き込み可能な[トークン](/glossary/トークン/)やシークレットを、信頼できない[コード](/glossary/コード/)から利用できる状態にしないでください。

この[エラー](/glossary/エラー/)は、次の3点を順に確認すると切り分けられます。

```text
何をしようとしたか   → 対応するpermission名とread/write
どこを操作したか     → 現在のリポジトリか、別のリポジトリ・組織か
何が実行を起こしたか → push、内部PR、外部フォーク、Dependabotか
```

## エラーの概要

[GitHub](/glossary/github/) Actionsは各ジョブの開始時に、そのジョブ専用の `GITHUB_TOKEN` を作ります。[GitHub公式の説明](https://docs.github.com/en/actions/concepts/security/github_token)では、この[トークン](/glossary/トークン/)は[ワークフロー](/glossary/ワークフロー/)を含む[リポジトリ](/glossary/リポジトリ/)へ[インストール](/glossary/インストール/)された[GitHub](/glossary/github/) Appのインストールアクセストークンで、ジョブが終わると失効します。

つまり、[エラー](/glossary/エラー/)中の `integration` は、通常は操作に使った[GitHub](/glossary/github/) App、[GitHub](/glossary/github/) Actionsでは `GITHUB_TOKEN` の発行元を指します。[リポジトリ](/glossary/リポジトリ/)やIssueが存在しないという意味ではありません。

[トークン](/glossary/トークン/)は次のどちらでも参照できます。

```yaml
env:
  GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

```yaml
env:
  GH_TOKEN: ${{ github.token }}
```

[アクション](/glossary/アクション/)によっては、入力として明示していなくても `github.token` を利用できます。そのため、外部[アクション](/glossary/アクション/)を使う場合も、[ワークフロー](/glossary/ワークフロー/)の `permissions` は必要最小限にします。

[権限](/glossary/権限/)は[ワークフロー](/glossary/ワークフロー/)全体またはジョブごとに指定できます。

```yaml
permissions:
  contents: read

jobs:
  comment:
    permissions:
      contents: read
      pull-requests: write
```

ジョブ側の指定は、そのジョブで実行する[アクション](/glossary/アクション/)と[コマンド](/glossary/コマンド/)へ適用されます。[ワークフロー](/glossary/ワークフロー/)上部で書き込みを許可していても、ジョブ側で狭めれば、そのジョブは狭めた[権限](/glossary/権限/)で動きます。

また、`permissions` に1つでも項目を書くと、列挙しなかった項目は `none` になります。

```yaml
permissions:
  issues: write
```

この指定では `issues` だけが書き込み可能で、`contents` を含むほかの[権限](/glossary/権限/)は `none` です。後続の `actions/checkout` や[リポジトリ](/glossary/リポジトリ/)内容の参照も必要なら、明示して残します。

```yaml
permissions:
  contents: read
  issues: write
```

`read-all` と `write-all` も指定できますが、恒久的な解決では操作に必要な項目だけを列挙します。`write` は同じ項目の `read` も含みます。

## まず最初に：失敗した操作・実行起点・対象を確認する

第一に、[ログ](/glossary/ログ/)中で最初に403を返した操作を確認します。後続の「処理に失敗した」という行ではなく、[API](/glossary/api/)の[メソッド](/glossary/メソッド/)、[URL](/glossary/url/)、`documentation_url`、実行した `gh` [コマンド](/glossary/コマンド/)、使用した[アクション](/glossary/アクション/)の処理を見ます。

```text
POST /repos/OWNER/REPO/issues/123/comments
PATCH /repos/OWNER/REPO/pulls/123
POST /repos/OWNER/REPO/check-runs
POST /repos/OWNER/REPO/code-scanning/sarifs
```

[GitHub](/glossary/github/) [REST](/glossary/rest/) [API](/glossary/api/)の各[エンドポイント](/glossary/エンドポイント/)には、必要な[権限](/glossary/権限/)が記載されています。[REST APIのトラブルシューティング](https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api#resource-not-accessible)によれば、応答の `X-Accepted-GitHub-Permissions` [ヘッダー](/glossary/ヘッダー/)でも受け付ける[権限](/glossary/権限/)を確認できます。

```text
X-Accepted-GitHub-Permissions: pull_requests=write, contents=read
```

複数の組み合わせを受け付ける[エンドポイント](/glossary/エンドポイント/)では、候補がセミコロンで区切られることがあります。[エラー](/glossary/エラー/)文だけから `contents: write` と決め打ちせず、失敗した[エンドポイント](/glossary/エンドポイント/)の資料または応答[ヘッダー](/glossary/ヘッダー/)を基準にします。

第二に、実行の起点を確認します。ジョブログへ秘密を出さずに確認できる値は次のとおりです。

```yaml
- name: Show workflow context
  run: |
    echo "event=$GITHUB_EVENT_NAME"
    echo "actor=$GITHUB_ACTOR"
    echo "repository=$GITHUB_REPOSITORY"
```

`pull_request` なら、Pull Requestが同じ[リポジトリ](/glossary/リポジトリ/)内の[ブランチ](/glossary/ブランチ/)から来たのか、外部フォークから来たのかを確認します。`github.actor` が `dependabot[bot]` なら、通常の利用者によるPull Requestとは権限条件が異なります。

第三に、[API](/glossary/api/)が操作しようとしている対象を確認します。`GITHUB_TOKEN` の[権限](/glossary/権限/)は、[ワークフロー](/glossary/ワークフロー/)を含む現在の[リポジトリ](/glossary/リポジトリ/)に限定されています。`github.repository` と[API](/glossary/api/)の `OWNER/REPO` が違う場合、現在の[ワークフロー](/glossary/ワークフロー/)へ[権限](/glossary/権限/)を追加するだけでは解決しません。

最後に、[ワークフロー](/glossary/ワークフロー/)上部、失敗したジョブ、再利用[ワークフロー](/glossary/ワークフロー/)の呼び出し元にある `permissions` をすべて確認します。

```bash
rg -n 'permissions:|workflow_call|pull_request_target|pull_request:' .github/workflows
```

## よくある原因と解決手順

### 原因1：同じリポジトリへの書き込み権限が不足している

最も直接的な原因です。たとえば、Pull Requestへコメントする処理なのに、[トークン](/glossary/トークン/)が読み取り専用なら403になります。

**Before（読み取りだけ）：**

```yaml
permissions:
  contents: read
```

**After（Pull Requestへの書き込みを追加）：**

```yaml
permissions:
  contents: read
  pull-requests: write
```

Issueコメント[API](/glossary/api/)はPull Requestの会話にも使われるため、利用する[エンドポイント](/glossary/エンドポイント/)によっては `issues: write` が必要です。Pull Requestを操作するから常に `pull-requests: write` と推測せず、その[エンドポイント](/glossary/エンドポイント/)の「Fine-grained access tokens」欄を確認します。

代表的な対応は次のとおりです。

| 操作 | 主に確認する[権限](/glossary/権限/) |
|---|---|
| checkout、[コミット](/glossary/コミット/)や[ファイル](/glossary/ファイル/)の参照 | `contents: read` |
| push、[タグ](/glossary/タグ/)、Releaseの作成 | `contents: write` |
| Issueの作成・更新・コメント | `issues: write` |
| Pull Requestの作成・更新 | `pull-requests: write` |
| Check Runの作成・更新 | `checks: write` |
| commit statusの作成 | `statuses: write` |
| [GitHub](/glossary/github/) Packagesへの公開 | `packages: write` |
| コードスキャン結果の[アップロード](/glossary/アップロード/) | `security-events: write` |
| OIDC[トークン](/glossary/トークン/)の要求 | `id-token: write` |

`id-token: write` は、[クラウド](/glossary/クラウド/)向けのOIDC[トークン](/glossary/トークン/)を要求できる[権限](/glossary/権限/)です。[リポジトリ](/glossary/リポジトリ/)の内容、Issue、Pull Requestへの書き込み[権限](/glossary/権限/)にはなりません。

### 原因2：permissionsの一部だけを書き、必要なread権限までnoneにした

次の変更は `issues: write` を追加する一方、列挙していない `contents` を `none` にします。

```yaml
permissions:
  issues: write
```

コメント処理の前にcheckoutや[設定ファイル](/glossary/設定ファイル/)の読み取りを行うなら、必要なread[権限](/glossary/権限/)も残します。

```yaml
permissions:
  contents: read
  issues: write
```

`write-all` を付けると表面上は直ることがありますが、どの外部[アクション](/glossary/アクション/)や[スクリプト](/glossary/スクリプト/)にも不要な書き込み[権限](/glossary/権限/)が渡ります。切り分け中に広い[権限](/glossary/権限/)を試した場合も、最終的には[ログ](/glossary/ログ/)と[API](/glossary/api/)資料を基に必要な項目へ戻します。

### 原因3：ジョブ側または再利用ワークフローの呼び出し元で権限を狭めている

[ワークフロー](/glossary/ワークフロー/)上部の指定だけを見ても、実際のジョブ[権限](/glossary/権限/)は確定しません。

```yaml
permissions:
  contents: read
  pull-requests: write

jobs:
  comment:
    permissions:
      contents: read
```

この `comment` ジョブでは、`pull-requests: write` がありません。ジョブ側にも必要な[権限](/glossary/権限/)を指定します。

```yaml
jobs:
  comment:
    permissions:
      contents: read
      pull-requests: write
```

再利用[ワークフロー](/glossary/ワークフロー/)でも、呼び出された側が[権限](/glossary/権限/)を引き上げることはできません。[再利用ワークフローの公式資料](https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations#supported-keywords-for-jobs-that-call-a-reusable-workflow)では、呼び出しの連鎖で[権限](/glossary/権限/)を維持または引き下げることはできても、引き上げられないと説明されています。

呼び出し元のジョブで必要な[権限](/glossary/権限/)を与えます。

```yaml
jobs:
  call-comment-workflow:
    permissions:
      contents: read
      pull-requests: write
    uses: OWNER/REPOSITORY/.github/workflows/comment.yml@main
```

### 原因4：リポジトリまたは組織の既定値が読み取り専用になっている

[リポジトリ](/glossary/リポジトリ/)の `Settings` → `Actions` → `General` → `Workflow permissions` では、`GITHUB_TOKEN` の既定権限を設定できます。[GitHub公式の設定手順](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository#configuring-the-default-github_token-permissions)によれば、組織やEnterpriseの設定を継承していると、[リポジトリ](/glossary/リポジトリ/)側で広い既定値を選べない場合があります。

既定値が読み取り専用でも、信頼された通常実行なら、[ワークフロー](/glossary/ワークフロー/)へ必要な[権限](/glossary/権限/)を明示して解決できます。

```yaml
permissions:
  contents: read
  issues: write
```

一方、[GitHub](/glossary/github/) ActionsからPull Requestの作成や承認を行う処理は、同じ画面にある `Allow GitHub Actions to create and approve pull requests` という別設定の影響も受けます。`pull-requests: write` だけで直らない場合は、この設定と、組織・Enterprise側で変更を制限されていないかを確認します。

### 原因5：外部フォークからのpull_requestで書き込みを要求している

公開[リポジトリ](/glossary/リポジトリ/)の外部フォークから実行される `pull_request` では、`GITHUB_TOKEN` は読み取り専用です。[ワークフロー](/glossary/ワークフロー/)に `write` を書いても、フォーク側の[コード](/glossary/コード/)を起点に書き込み[権限](/glossary/権限/)へ引き上げることはできません。

```yaml
on:
  pull_request:

permissions:
  contents: read
  pull-requests: write  # 外部フォークではwriteへ引き上がらない
```

解決は処理を二つに分けることです。

```text
Pull Request側のコードをcheckoutしてテストする
  → pull_requestのまま、読み取り専用で実行する

ラベル、コメントなど基準リポジトリ側の情報だけを更新する
  → 信頼できるワークフローで別途実行する
```

`pull_request_target` は基準[リポジトリ](/glossary/リポジトリ/)のコンテキストで動くため、ラベル付けやコメントなど、Pull Request側の[コード](/glossary/コード/)を実行しない管理処理に使えます。

```yaml
on:
  pull_request_target:
    types: [opened, reopened, synchronize]

permissions:
  contents: read
  pull-requests: write
```

ただし、ここへ次の処理を追加してはいけません。

```text
Pull Requestのheadをcheckoutする
Pull Request側が変更できるスクリプトを実行する
Pull Request側が変更できる設定を読み、任意コマンドとして実行する
```

[GitHubの安全な `pull_request_target` の資料](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target)でも、信頼できないPull Requestの[コード](/glossary/コード/)を特権付き[環境](/glossary/環境/)で実行しないよう警告されています。[テスト](/glossary/テスト/)に書き込み[権限](/glossary/権限/)が不要なら、`pull_request` のままにします。

### 原因6：DependabotのPull Requestで通常の書き込み処理を動かしている

Dependabotが作成したPull Requestは、[GitHub](/glossary/github/) Actionsでは外部フォークからのPull Requestと同様に扱われます。[トークン](/glossary/トークン/)は読み取り専用で、Actionsのシークレットも通常は利用できません。

```yaml
if: github.actor != 'dependabot[bot]'
```

単に書き込み処理を除外できるなら、上のようにDependabot実行ではそのジョブを動かさない方法があります。必要な処理なら、信頼された後続[ワークフロー](/glossary/ワークフロー/)へ分離します。

コードスキャン結果の[送信](/glossary/送信/)には、公式に個別の扱いがあります。[Dependabotでのコードスキャン403の資料](https://docs.github.com/en/code-security/reference/code-scanning/troubleshoot-analysis-errors/resource-not-accessible)は、Dependabot[ブランチ](/glossary/ブランチ/)への `push` を起点に[アップロード](/glossary/アップロード/)せず、`pull_request` [イベント](/glossary/イベント/)から解析結果を[アップロード](/glossary/アップロード/)する構成を案内しています。これはコードスキャン[API](/glossary/api/)の例外を利用する対処であり、一般のIssueやPull Request書き込みを許可する方法ではありません。

### 原因7：別のリポジトリまたは組織の資源を操作している

`GITHUB_TOKEN` は、[ワークフロー](/glossary/ワークフロー/)が置かれた現在の[リポジトリ](/glossary/リポジトリ/)に限定されます。

```text
実行元: OWNER/app
操作先: OWNER/infrastructure
```

この場合、`OWNER/app` 側で `contents: write` を与えても、`OWNER/infrastructure` への書き込み[権限](/glossary/権限/)にはなりません。

[GitHub AppをActionsで使う公式手順](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/making-authenticated-api-requests-with-a-github-app-in-a-github-actions-workflow)に沿って、対象[リポジトリ](/glossary/リポジトリ/)へ[インストール](/glossary/インストール/)した[GitHub](/glossary/github/) Appの[トークン](/glossary/トークン/)を発行します。

```yaml
permissions:
  contents: read

steps:
  - name: Generate GitHub App token
    id: app-token
    uses: actions/create-github-app-token@v3
    with:
      client-id: ${{ vars.APP_CLIENT_ID }}
      private-key: ${{ secrets.APP_PRIVATE_KEY }}
      owner: TARGET_OWNER
      repositories: TARGET_REPOSITORY
      permission-contents: read

  - name: Call API in target repository
    env:
      GH_TOKEN: ${{ steps.app-token.outputs.token }}
    run: gh api repos/TARGET_OWNER/TARGET_REPOSITORY
```

[GitHub](/glossary/github/) Appには対象操作に必要な[権限](/glossary/権限/)を設定し、対象の[アカウント](/glossary/アカウント/)と[リポジトリ](/glossary/リポジトリ/)へ[インストール](/glossary/インストール/)します。個人の[権限](/glossary/権限/)と寿命に依存するPATより、継続的な[自動化](/glossary/自動化/)には[GitHub](/glossary/github/) Appを優先します。

### 原因8：GITHUB_TOKENでは利用できない権限または設定が必要

[API](/glossary/api/)資料で必要な[権限](/glossary/権限/)を確認しても、`GITHUB_TOKEN` の [`permissions` で選べる項目](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#permissions)に対応するものがない場合があります。また、前述のPull Request作成・承認のように、[リポジトリ](/glossary/リポジトリ/)設定で別途許可が必要な操作もあります。

この場合は `write-all` を追加しても解決しません。

```text
必要な設定が無効
  → リポジトリ、組織、EnterpriseのActions設定を確認する

GITHUB_TOKENが対象権限を持てない
  → 必要最小限の権限を持つGitHub Appトークンを使う
```

[GitHub](/glossary/github/)公式も、`GITHUB_TOKEN` で利用できない[権限](/glossary/権限/)が必要なら、[GitHub](/glossary/github/) AppのインストールアクセストークンまたはPATを使うよう案内しています。

## 補足：似ているが別のもの

### 401 Bad credentials

[トークン](/glossary/トークン/)がない、失効している、形式が違う場合は、通常は認証自体の失敗です。

```text
401 Bad credentials
```

`Resource not accessible by integration` は、[認証](/glossary/認証/)された主体は分かっていても、その操作の許可がない403です。

### 404 Not Found

対象が存在しない場合だけでなく、非公開資源の存在を見せないため、権限不足を404として返す[API](/glossary/api/)もあります。404なら[URL](/glossary/url/)、所有者名、[リポジトリ](/glossary/リポジトリ/)名、対象番号に加え、[トークン](/glossary/トークン/)が対象[リポジトリ](/glossary/リポジトリ/)へアクセスできるかを確認します。

### API rate limit exceededの403

同じ403でも、[レート制限](/glossary/レート制限/)なら[エラー](/glossary/エラー/)本文と応答[ヘッダー](/glossary/ヘッダー/)が違います。

```text
x-ratelimit-remaining: 0
```

[権限](/glossary/権限/)を追加しても[レート制限](/glossary/レート制限/)は直りません。`X-Accepted-GitHub-Permissions` と `x-ratelimit-remaining` を分けて確認します。

### GITHUB_TOKENで行った操作から次のワークフローが起動しない

`GITHUB_TOKEN` を使った操作は、無限再帰を防ぐため、原則として新しい[ワークフロー](/glossary/ワークフロー/)実行を起こしません。これは[API](/glossary/api/)が403を返す権限不足とは別です。`workflow_dispatch` と `repository_dispatch` は例外です。また、Pull Requestの作成・更新による `opened`、`synchronize`、`reopened` も、承認待ちの状態で実行を作る場合があります。書き込み自体は成功するのに後続[ワークフロー](/glossary/ワークフロー/)だけが始まらない場合は、現在の[イベント](/glossary/イベント/)発生規則を確認します。

### ブランチ保護またはルールセットによる拒否

`contents: write` があっても、[ブランチ](/glossary/ブランチ/)保護、ルールセット、必須レビューなどが書き込みを拒否することがあります。その場合は、[ログ](/glossary/ログ/)に表示される保護規則の文言を基準にします。`Resource not accessible by integration` と同じ対処にまとめません。

## 切り分けの順序

1. [ログ](/glossary/ログ/)で最初に403になった[API](/glossary/api/)、`gh` [コマンド](/glossary/コマンド/)、[アクション](/glossary/アクション/)の処理を特定する。
2. [API](/glossary/api/)資料または `X-Accepted-GitHub-Permissions` で必要な[権限](/glossary/権限/)を確認する。
3. `GITHUB_EVENT_NAME`、`GITHUB_ACTOR`、`GITHUB_REPOSITORY` を確認する。
4. 操作先が現在の[リポジトリ](/glossary/リポジトリ/)か、別[リポジトリ](/glossary/リポジトリ/)・組織かを確認する。
5. [ワークフロー](/glossary/ワークフロー/)上部と失敗したジョブの `permissions` を確認する。
6. `permissions` に列挙しなかった必要なread[権限](/glossary/権限/)が `none` になっていないか確認する。
7. 再利用[ワークフロー](/glossary/ワークフロー/)なら、呼び出し元ジョブが必要な[権限](/glossary/権限/)を渡しているか確認する。
8. 外部フォークまたはDependabotなら、書き込み[権限](/glossary/権限/)を追加できるという前提を外す。
9. 別[リポジトリ](/glossary/リポジトリ/)または対象外の[権限](/glossary/権限/)なら、対象へ[インストール](/glossary/インストール/)した[GitHub](/glossary/github/) Appを使う。
10. `pull_request_target` を使う場合は、Pull Request側の[コード](/glossary/コード/)を実行しない構成か確認する。

## 確認コマンド集

[ワークフロー](/glossary/ワークフロー/)とジョブに書かれた[権限](/glossary/権限/)を探します。

```bash
rg -n 'permissions:|workflow_call|pull_request_target|pull_request:' .github/workflows
```

Actions上で実行起点と対象[リポジトリ](/glossary/リポジトリ/)を確認します。

```yaml
- name: Show non-secret context
  run: |
    echo "event=$GITHUB_EVENT_NAME"
    echo "actor=$GITHUB_ACTOR"
    echo "repository=$GITHUB_REPOSITORY"
```

`gh` が現在の[リポジトリ](/glossary/リポジトリ/)を読めるか確認します。

```bash
gh api "repos/$GITHUB_REPOSITORY"
```

応答[ヘッダー](/glossary/ヘッダー/)を含めて確認します。

```bash
gh api --include "repos/$GITHUB_REPOSITORY"
```

ただし、GETが成功しても書き込み[権限](/glossary/権限/)があるとは限りません。403になった実際の[エンドポイント](/glossary/エンドポイント/)の資料と応答を確認します。確認のためだけにIssueやコメントを作成するなど、状態を変更する[API](/glossary/api/)を実行しないでください。

[ワークフロー](/glossary/ワークフロー/)で `gh` を使う場合は、[トークン](/glossary/トークン/)を[環境変数](/glossary/環境変数/)へ渡します。

```yaml
- name: Read repository
  env:
    GH_TOKEN: ${{ github.token }}
  run: gh api "repos/$GITHUB_REPOSITORY"
```

[トークン](/glossary/トークン/)本体は[ログ](/glossary/ログ/)へ出しません。

```bash
# 実行しない
echo "$GH_TOKEN"
```

## Editor's Note

この[エラー](/glossary/エラー/)を「`permissions: write-all` を足せば直る」と覚えると、外部フォークで誤診します。

[GitHub CLIのIssue #10464](https://github.com/cli/cli/issues/10464)では、Pull Requestへコメントする[ワークフロー](/glossary/ワークフロー/)が、個人フォークでは動くのに、上流の公開組織[リポジトリ](/glossary/リポジトリ/)では `403 Resource not accessible by integration` になりました。原因は、外部フォークからの `pull_request` に書き込み可能な `GITHUB_TOKEN` が渡らないことでした。`permissions` の不足という同じ文言でも、[YAML](/glossary/yaml/)で引き上げられる不足ではありません。

その事例では `pull_request_target` へ変更した後も、変更した[ワークフロー](/glossary/ワークフロー/)自体が上流の既定[ブランチ](/glossary/ブランチ/)へ入るまでは期待どおり起動しませんでした。`pull_request_target` は基準[リポジトリ](/glossary/リポジトリ/)側の[ワークフロー](/glossary/ワークフロー/)を使うためです。そして、起動できたことと安全であることは別です。Pull Request側のheadをcheckoutして実行すれば、書き込み[権限](/glossary/権限/)やシークレットを攻撃者の[コード](/glossary/コード/)へ渡し得ます。

一方、[CodeQLのIssue #8843](https://github.com/github/codeql/issues/8843)では、読み取り専用の既定権限へ変えた後にコードスキャン結果の[アップロード](/glossary/アップロード/)が403となり、[ワークフロー](/glossary/ワークフロー/)へ `actions: read`、`contents: read`、`security-events: write` を明示することで解決しています。こちらは操作と[権限](/glossary/権限/)が1対1で対応する通常の不足です。

また、[GitHub](/glossary/github/)は[2021年4月に `permissions` キーを追加](https://github.blog/changelog/2021-04-20-github-actions-control-permissions-for-github_token/)し、列挙しなかった[権限](/glossary/権限/)を `none` とする仕組みを導入しました。さらに[2023年2月には、新しく作成される組織や個人アカウントのリポジトリで、`GITHUB_TOKEN` の既定値を読み取り専用へ変更](https://github.blog/changelog/2023-02-02-github-actions-updating-the-default-github_token-permissions-to-read-only/)しました。古い[リポジトリ](/glossary/リポジトリ/)では動くのに新しい[リポジトリ](/glossary/リポジトリ/)では403になる差は、この既定値から生じることがあります。

要点は、[エラー](/glossary/エラー/)文ではなく[権限](/glossary/権限/)の境界を見ることです。

```text
同一リポジトリ・信頼された実行で項目が不足
  → 必要なpermissionsを追加する

フォーク・Dependabot・再利用ワークフローの上限
  → 実行設計または呼び出し元を直す

別リポジトリ・組織資源・対象外の権限
  → 必要最小限のGitHub Appトークンを使う
```

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
