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

GitHub Actionsで次のエラーが出た場合、APIが壊れているのではなく、リクエストに使ったトークンがその操作を許可されていません。

```text
RequestError [HttpError]: Resource not accessible by integration
status: 403
```

同じリポジトリで、`push` や組織内部からの実行が起点なら、解決は失敗した操作に対応する [`permissions`](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#permissions) をワークフローへ追加することです。

たとえば、コードを読み、IssueとPull Requestへ書き込むジョブなら次のようにします。

```yaml
permissions:
  contents: read
  issues: write
  pull-requests: write
```

必要な権限は操作ごとに違います。

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

ただし、`permissions` を書けば必ず直るわけではありません。次の実行では、ワークフロー側から書き込み権限へ引き上げられないことがあります。

```text
外部フォークからのpull_request
Dependabotが作成したPull Request
呼び出し元が権限を与えていない再利用ワークフロー
GITHUB_TOKENの対象外である別リポジトリや組織資源への操作
```

特に、外部フォークの失敗を直すために `pull_request_target` へ置き換え、Pull Request側のコードをcheckoutして実行するのは危険です。書き込み可能なトークンやシークレットを、信頼できないコードから利用できる状態にしないでください。

このエラーは、次の3点を順に確認すると切り分けられます。

```text
何をしようとしたか   → 対応するpermission名とread/write
どこを操作したか     → 現在のリポジトリか、別のリポジトリ・組織か
何が実行を起こしたか → push、内部PR、外部フォーク、Dependabotか
```

## エラーの概要

GitHub Actionsは各ジョブの開始時に、そのジョブ専用の `GITHUB_TOKEN` を作ります。[GitHub公式の説明](https://docs.github.com/en/actions/concepts/security/github_token)では、このトークンはワークフローを含むリポジトリへインストールされたGitHub Appのインストールアクセストークンで、ジョブが終わると失効します。

つまり、エラー中の `integration` は、通常は操作に使ったGitHub App、GitHub Actionsでは `GITHUB_TOKEN` の発行元を指します。リポジトリやIssueが存在しないという意味ではありません。

トークンは次のどちらでも参照できます。

```yaml
env:
  GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

```yaml
env:
  GH_TOKEN: ${{ github.token }}
```

アクションによっては、入力として明示していなくても `github.token` を利用できます。そのため、外部アクションを使う場合も、ワークフローの `permissions` は必要最小限にします。

権限はワークフロー全体またはジョブごとに指定できます。

```yaml
permissions:
  contents: read

jobs:
  comment:
    permissions:
      contents: read
      pull-requests: write
```

ジョブ側の指定は、そのジョブで実行するアクションとコマンドへ適用されます。ワークフロー上部で書き込みを許可していても、ジョブ側で狭めれば、そのジョブは狭めた権限で動きます。

また、`permissions` に1つでも項目を書くと、列挙しなかった項目は `none` になります。

```yaml
permissions:
  issues: write
```

この指定では `issues` だけが書き込み可能で、`contents` を含むほかの権限は `none` です。後続の `actions/checkout` やリポジトリ内容の参照も必要なら、明示して残します。

```yaml
permissions:
  contents: read
  issues: write
```

`read-all` と `write-all` も指定できますが、恒久的な解決では操作に必要な項目だけを列挙します。`write` は同じ項目の `read` も含みます。

## まず最初に：失敗した操作・実行起点・対象を確認する

第一に、ログ中で最初に403を返した操作を確認します。後続の「処理に失敗した」という行ではなく、APIのメソッド、URL、`documentation_url`、実行した `gh` コマンド、使用したアクションの処理を見ます。

```text
POST /repos/OWNER/REPO/issues/123/comments
PATCH /repos/OWNER/REPO/pulls/123
POST /repos/OWNER/REPO/check-runs
POST /repos/OWNER/REPO/code-scanning/sarifs
```

GitHub REST APIの各エンドポイントには、必要な権限が記載されています。[REST APIのトラブルシューティング](https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api#resource-not-accessible)によれば、応答の `X-Accepted-GitHub-Permissions` ヘッダーでも受け付ける権限を確認できます。

```text
X-Accepted-GitHub-Permissions: pull_requests=write, contents=read
```

複数の組み合わせを受け付けるエンドポイントでは、候補がセミコロンで区切られることがあります。エラー文だけから `contents: write` と決め打ちせず、失敗したエンドポイントの資料または応答ヘッダーを基準にします。

第二に、実行の起点を確認します。ジョブログへ秘密を出さずに確認できる値は次のとおりです。

```yaml
- name: Show workflow context
  run: |
    echo "event=$GITHUB_EVENT_NAME"
    echo "actor=$GITHUB_ACTOR"
    echo "repository=$GITHUB_REPOSITORY"
```

`pull_request` なら、Pull Requestが同じリポジトリ内のブランチから来たのか、外部フォークから来たのかを確認します。`github.actor` が `dependabot[bot]` なら、通常の利用者によるPull Requestとは権限条件が異なります。

第三に、APIが操作しようとしている対象を確認します。`GITHUB_TOKEN` の権限は、ワークフローを含む現在のリポジトリに限定されています。`github.repository` とAPIの `OWNER/REPO` が違う場合、現在のワークフローへ権限を追加するだけでは解決しません。

最後に、ワークフロー上部、失敗したジョブ、再利用ワークフローの呼び出し元にある `permissions` をすべて確認します。

```bash
rg -n 'permissions:|workflow_call|pull_request_target|pull_request:' .github/workflows
```

## よくある原因と解決手順

### 原因1：同じリポジトリへの書き込み権限が不足している

最も直接的な原因です。たとえば、Pull Requestへコメントする処理なのに、トークンが読み取り専用なら403になります。

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

IssueコメントAPIはPull Requestの会話にも使われるため、利用するエンドポイントによっては `issues: write` が必要です。Pull Requestを操作するから常に `pull-requests: write` と推測せず、そのエンドポイントの「Fine-grained access tokens」欄を確認します。

代表的な対応は次のとおりです。

| 操作 | 主に確認する権限 |
|---|---|
| checkout、コミットやファイルの参照 | `contents: read` |
| push、タグ、Releaseの作成 | `contents: write` |
| Issueの作成・更新・コメント | `issues: write` |
| Pull Requestの作成・更新 | `pull-requests: write` |
| Check Runの作成・更新 | `checks: write` |
| commit statusの作成 | `statuses: write` |
| GitHub Packagesへの公開 | `packages: write` |
| コードスキャン結果のアップロード | `security-events: write` |
| OIDCトークンの要求 | `id-token: write` |

`id-token: write` は、クラウド向けのOIDCトークンを要求できる権限です。リポジトリの内容、Issue、Pull Requestへの書き込み権限にはなりません。

### 原因2：permissionsの一部だけを書き、必要なread権限までnoneにした

次の変更は `issues: write` を追加する一方、列挙していない `contents` を `none` にします。

```yaml
permissions:
  issues: write
```

コメント処理の前にcheckoutや設定ファイルの読み取りを行うなら、必要なread権限も残します。

```yaml
permissions:
  contents: read
  issues: write
```

`write-all` を付けると表面上は直ることがありますが、どの外部アクションやスクリプトにも不要な書き込み権限が渡ります。切り分け中に広い権限を試した場合も、最終的にはログとAPI資料を基に必要な項目へ戻します。

### 原因3：ジョブ側または再利用ワークフローの呼び出し元で権限を狭めている

ワークフロー上部の指定だけを見ても、実際のジョブ権限は確定しません。

```yaml
permissions:
  contents: read
  pull-requests: write

jobs:
  comment:
    permissions:
      contents: read
```

この `comment` ジョブでは、`pull-requests: write` がありません。ジョブ側にも必要な権限を指定します。

```yaml
jobs:
  comment:
    permissions:
      contents: read
      pull-requests: write
```

再利用ワークフローでも、呼び出された側が権限を引き上げることはできません。[再利用ワークフローの公式資料](https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations#supported-keywords-for-jobs-that-call-a-reusable-workflow)では、呼び出しの連鎖で権限を維持または引き下げることはできても、引き上げられないと説明されています。

呼び出し元のジョブで必要な権限を与えます。

```yaml
jobs:
  call-comment-workflow:
    permissions:
      contents: read
      pull-requests: write
    uses: OWNER/REPOSITORY/.github/workflows/comment.yml@main
```

### 原因4：リポジトリまたは組織の既定値が読み取り専用になっている

リポジトリの `Settings` → `Actions` → `General` → `Workflow permissions` では、`GITHUB_TOKEN` の既定権限を設定できます。[GitHub公式の設定手順](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository#configuring-the-default-github_token-permissions)によれば、組織やEnterpriseの設定を継承していると、リポジトリ側で広い既定値を選べない場合があります。

既定値が読み取り専用でも、信頼された通常実行なら、ワークフローへ必要な権限を明示して解決できます。

```yaml
permissions:
  contents: read
  issues: write
```

一方、GitHub ActionsからPull Requestの作成や承認を行う処理は、同じ画面にある `Allow GitHub Actions to create and approve pull requests` という別設定の影響も受けます。`pull-requests: write` だけで直らない場合は、この設定と、組織・Enterprise側で変更を制限されていないかを確認します。

### 原因5：外部フォークからのpull_requestで書き込みを要求している

公開リポジトリの外部フォークから実行される `pull_request` では、`GITHUB_TOKEN` は読み取り専用です。ワークフローに `write` を書いても、フォーク側のコードを起点に書き込み権限へ引き上げることはできません。

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

`pull_request_target` は基準リポジトリのコンテキストで動くため、ラベル付けやコメントなど、Pull Request側のコードを実行しない管理処理に使えます。

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

[GitHubの安全な `pull_request_target` の資料](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target)でも、信頼できないPull Requestのコードを特権付き環境で実行しないよう警告されています。テストに書き込み権限が不要なら、`pull_request` のままにします。

### 原因6：DependabotのPull Requestで通常の書き込み処理を動かしている

Dependabotが作成したPull Requestは、GitHub Actionsでは外部フォークからのPull Requestと同様に扱われます。トークンは読み取り専用で、Actionsのシークレットも通常は利用できません。

```yaml
if: github.actor != 'dependabot[bot]'
```

単に書き込み処理を除外できるなら、上のようにDependabot実行ではそのジョブを動かさない方法があります。必要な処理なら、信頼された後続ワークフローへ分離します。

コードスキャン結果の送信には、公式に個別の扱いがあります。[Dependabotでのコードスキャン403の資料](https://docs.github.com/en/code-security/reference/code-scanning/troubleshoot-analysis-errors/resource-not-accessible)は、Dependabotブランチへの `push` を起点にアップロードせず、`pull_request` イベントから解析結果をアップロードする構成を案内しています。これはコードスキャンAPIの例外を利用する対処であり、一般のIssueやPull Request書き込みを許可する方法ではありません。

### 原因7：別のリポジトリまたは組織の資源を操作している

`GITHUB_TOKEN` は、ワークフローが置かれた現在のリポジトリに限定されます。

```text
実行元: OWNER/app
操作先: OWNER/infrastructure
```

この場合、`OWNER/app` 側で `contents: write` を与えても、`OWNER/infrastructure` への書き込み権限にはなりません。

[GitHub AppをActionsで使う公式手順](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/making-authenticated-api-requests-with-a-github-app-in-a-github-actions-workflow)に沿って、対象リポジトリへインストールしたGitHub Appのトークンを発行します。

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

GitHub Appには対象操作に必要な権限を設定し、対象のアカウントとリポジトリへインストールします。個人の権限と寿命に依存するPATより、継続的な自動化にはGitHub Appを優先します。

### 原因8：GITHUB_TOKENでは利用できない権限または設定が必要

API資料で必要な権限を確認しても、`GITHUB_TOKEN` の [`permissions` で選べる項目](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#permissions)に対応するものがない場合があります。また、前述のPull Request作成・承認のように、リポジトリ設定で別途許可が必要な操作もあります。

この場合は `write-all` を追加しても解決しません。

```text
必要な設定が無効
  → リポジトリ、組織、EnterpriseのActions設定を確認する

GITHUB_TOKENが対象権限を持てない
  → 必要最小限の権限を持つGitHub Appトークンを使う
```

GitHub公式も、`GITHUB_TOKEN` で利用できない権限が必要なら、GitHub AppのインストールアクセストークンまたはPATを使うよう案内しています。

## 補足：似ているが別のもの

### 401 Bad credentials

トークンがない、失効している、形式が違う場合は、通常は認証自体の失敗です。

```text
401 Bad credentials
```

`Resource not accessible by integration` は、認証された主体は分かっていても、その操作の許可がない403です。

### 404 Not Found

対象が存在しない場合だけでなく、非公開資源の存在を見せないため、権限不足を404として返すAPIもあります。404ならURL、所有者名、リポジトリ名、対象番号に加え、トークンが対象リポジトリへアクセスできるかを確認します。

### API rate limit exceededの403

同じ403でも、レート制限ならエラー本文と応答ヘッダーが違います。

```text
x-ratelimit-remaining: 0
```

権限を追加してもレート制限は直りません。`X-Accepted-GitHub-Permissions` と `x-ratelimit-remaining` を分けて確認します。

### GITHUB_TOKENで行った操作から次のワークフローが起動しない

`GITHUB_TOKEN` を使った操作は、無限再帰を防ぐため、原則として新しいワークフロー実行を起こしません。これはAPIが403を返す権限不足とは別です。`workflow_dispatch` と `repository_dispatch` は例外です。また、Pull Requestの作成・更新による `opened`、`synchronize`、`reopened` も、承認待ちの状態で実行を作る場合があります。書き込み自体は成功するのに後続ワークフローだけが始まらない場合は、現在のイベント発生規則を確認します。

### ブランチ保護またはルールセットによる拒否

`contents: write` があっても、ブランチ保護、ルールセット、必須レビューなどが書き込みを拒否することがあります。その場合は、ログに表示される保護規則の文言を基準にします。`Resource not accessible by integration` と同じ対処にまとめません。

## 切り分けの順序

1. ログで最初に403になったAPI、`gh` コマンド、アクションの処理を特定する。
2. API資料または `X-Accepted-GitHub-Permissions` で必要な権限を確認する。
3. `GITHUB_EVENT_NAME`、`GITHUB_ACTOR`、`GITHUB_REPOSITORY` を確認する。
4. 操作先が現在のリポジトリか、別リポジトリ・組織かを確認する。
5. ワークフロー上部と失敗したジョブの `permissions` を確認する。
6. `permissions` に列挙しなかった必要なread権限が `none` になっていないか確認する。
7. 再利用ワークフローなら、呼び出し元ジョブが必要な権限を渡しているか確認する。
8. 外部フォークまたはDependabotなら、書き込み権限を追加できるという前提を外す。
9. 別リポジトリまたは対象外の権限なら、対象へインストールしたGitHub Appを使う。
10. `pull_request_target` を使う場合は、Pull Request側のコードを実行しない構成か確認する。

## 確認コマンド集

ワークフローとジョブに書かれた権限を探します。

```bash
rg -n 'permissions:|workflow_call|pull_request_target|pull_request:' .github/workflows
```

Actions上で実行起点と対象リポジトリを確認します。

```yaml
- name: Show non-secret context
  run: |
    echo "event=$GITHUB_EVENT_NAME"
    echo "actor=$GITHUB_ACTOR"
    echo "repository=$GITHUB_REPOSITORY"
```

`gh` が現在のリポジトリを読めるか確認します。

```bash
gh api "repos/$GITHUB_REPOSITORY"
```

応答ヘッダーを含めて確認します。

```bash
gh api --include "repos/$GITHUB_REPOSITORY"
```

ただし、GETが成功しても書き込み権限があるとは限りません。403になった実際のエンドポイントの資料と応答を確認します。確認のためだけにIssueやコメントを作成するなど、状態を変更するAPIを実行しないでください。

ワークフローで `gh` を使う場合は、トークンを環境変数へ渡します。

```yaml
- name: Read repository
  env:
    GH_TOKEN: ${{ github.token }}
  run: gh api "repos/$GITHUB_REPOSITORY"
```

トークン本体はログへ出しません。

```bash
# 実行しない
echo "$GH_TOKEN"
```

## Editor's Note

このエラーを「`permissions: write-all` を足せば直る」と覚えると、外部フォークで誤診します。

[GitHub CLIのIssue #10464](https://github.com/cli/cli/issues/10464)では、Pull Requestへコメントするワークフローが、個人フォークでは動くのに、上流の公開組織リポジトリでは `403 Resource not accessible by integration` になりました。原因は、外部フォークからの `pull_request` に書き込み可能な `GITHUB_TOKEN` が渡らないことでした。`permissions` の不足という同じ文言でも、YAMLで引き上げられる不足ではありません。

その事例では `pull_request_target` へ変更した後も、変更したワークフロー自体が上流の既定ブランチへ入るまでは期待どおり起動しませんでした。`pull_request_target` は基準リポジトリ側のワークフローを使うためです。そして、起動できたことと安全であることは別です。Pull Request側のheadをcheckoutして実行すれば、書き込み権限やシークレットを攻撃者のコードへ渡し得ます。

一方、[CodeQLのIssue #8843](https://github.com/github/codeql/issues/8843)では、読み取り専用の既定権限へ変えた後にコードスキャン結果のアップロードが403となり、ワークフローへ `actions: read`、`contents: read`、`security-events: write` を明示することで解決しています。こちらは操作と権限が1対1で対応する通常の不足です。

また、GitHubは[2021年4月に `permissions` キーを追加](https://github.blog/changelog/2021-04-20-github-actions-control-permissions-for-github_token/)し、列挙しなかった権限を `none` とする仕組みを導入しました。さらに[2023年2月には、新しく作成される組織や個人アカウントのリポジトリで、`GITHUB_TOKEN` の既定値を読み取り専用へ変更](https://github.blog/changelog/2023-02-02-github-actions-updating-the-default-github_token-permissions-to-read-only/)しました。古いリポジトリでは動くのに新しいリポジトリでは403になる差は、この既定値から生じることがあります。

要点は、エラー文ではなく権限の境界を見ることです。

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
