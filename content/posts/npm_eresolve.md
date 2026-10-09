---
title: "npm ERESOLVEの対処法"
date: 2026-08-07T09:00:00+09:00
slug: npm_eresolve
tags: ["npm", "Node.js", "JavaScript"]
description: "npm installのERESOLVEをFoundとpeerの要求から切り分ける。互換性のある版への調整とlegacy-peer-deps・forceの違いを説明。"
draft: false
images: ["og/posts/npm_eresolve.png"]
errorCode: "ERESOLVE"
urgency: "medium"
service: "npm"
error_type: "ERESOLVE"
components: ["npm", "peerDependencies", "package.json", "package-lock.json"]
related_services: []
trend_incident: false
publish_slug: "npm_eresolve"
publish_note: "新規作成。npm公式文書・現行実装、GitHub実例を照合"
publish_zenn: true
---

## 冒頭まとめ

`npm install` が `ERESOLVE` で止まったら、まずログの `Found:` と、その下の `peer` が要求する版を比べる。パッケージ本体と、それを利用するプラグインなどの要求が合わず、npmが依存関係を配置できない場合に起きる。

```text
npm error code ERESOLVE
npm error ERESOLVE unable to resolve dependency tree
```

`could not resolve` と表示される場合もある。古いnpmでは接頭辞が `npm ERR!` になる。文言の違いだけで対処を変える必要はない。

基本の対処は、競合する両側を互換性のある版に揃えること。`--legacy-peer-deps` はpeerの要求を無視する回避策であり、`--force` はさらに広い保護を外す。インストール完了だけでは動作確認にならない。

## Foundとpeerの要求を読み比べる

peer dependencyは、プラグインなどが利用側に求めるパッケージと版の条件を表す。たとえば次は説明用の例である。

```text
Found: host-lib@2.0.0
Could not resolve dependency:
peer host-lib@"^1.0.0" from plugin-lib@1.0.0
```

`host-lib@2.0.0` は `^1.0.0` を満たさない。`plugin-lib`を2系のhostに対応した版へ変えるか、host側を1系へ揃える必要がある。

| 表示 | 読み取る内容 |
|---|---|
| `While resolving:` | 解決中のプロジェクトやパッケージ。必ずしも競合元そのものではない |
| `Found:` | 解決中のツリーで使おうとしている版。既にインストール済みとは限らない |
| `peer ... from ...` | 要求されるパッケージ・範囲と、その要求を出したパッケージ |
| `Conflicting peer dependency:` | 競合するpeerを満たす候補。これを単独で入れれば直るとは限らない |

ログにレポートのパスが表示されたら、そのファイルも読む。保存先はnpmの版や設定で変わるため、`~/.npm/eresolve-report.txt`に固定しない。

[npm/cli Issue #6476](https://github.com/npm/cli/issues/6476)には、npm 9.5.1・Node.js 18.16.0での実例がある。rootがcommonを1.0.6に固定する一方、解決されたdecoratorsがcommonの1.0.8以上を要求していた。投稿者がcoreを1.0.6へ固定していても、そのpeer範囲から別パッケージの1.0.8が選ばれていた。これは過去の報告であり、現在のnpm全般に同じ不具合があると示すものではない。

## npmの版と設定を確認する

```bash
node -v
npm -v
npm config get strict-peer-deps
npm config get legacy-peer-deps
npm config get force
```

npm 7からpeer dependencyが既定で自動インストールされるようになった。npmを変えたことで、以前は通った組合せが解決に失敗することがある。Node.jsの版だけで判断せず、実際のnpmの版を確認する。

ただし「npm 7以降ではすべてのpeer競合で停止する」という説明は正確ではない。既定では、深い依存関係の競合を非peerの要求から解決し、警告で進む場合がある。`strict-peer-deps=true`は、そうした推測で進められる競合も失敗にする設定である。

現行の[npm CLI内のplace-dep.js](https://github.com/npm/cli/blob/latest/workspaces/arborist/lib/place-dep.js)でも、配置できないときにforce・root/workspace由来か・strict設定を確認し、エラーと警告を分けている。アーカイブ済みのnpm/arboristの行番号を現行実装へそのまま当てはめない。

## 互換性のあるパッケージの版に揃える

ログの `peer ... from ...` に出た要求元と、要求されている側を調べる。以下の名前と版は実際の対象へ置き換える。

```bash
npm view plugin-lib@1.0.0 peerDependencies
npm view plugin-lib versions
npm ls host-lib plugin-lib
npm explain host-lib
```

`npm view`は通常レジストリへ問い合わせる。`npm ls`と`npm explain`はインストール済みツリーの調査に使うため、初回インストール前や途中失敗後には十分な情報がないこともある。`npm ls`は不整合を表示して終了コードが非0になる場合がある。

要求元の新版が現在のhostに対応しているなら、要求元を更新する。hostを変更するなら、ほかのプラグインのpeer範囲も満たす版を選ぶ。変更後は `npm install` でlockfileを更新し、差分・ビルド・テストを確認する。devDependenciesならインストール時の `-D` も維持する。

lockfile削除やキャッシュ削除から始めても、互いに交わらない要求範囲は直らない。lockfileを消すと関係のない依存まで更新される可能性がある。

## legacy-peer-depsとforceを区別する

| 操作 | 挙動 | 注意点 |
|---|---|---|
| `npm install --legacy-peer-deps` | ツリー構築時にpeerの要求を無視する | 要求の整合性が保証されない |
| `npm install --force` | peer競合の許容を含む、複数の保護を外す | peer以外にも影響する |
| `npm install --omit=peer` | peerをディスクへ展開しない | peerの要求を考慮したツリー解決は行う |

一時的にpeerの扱いを回避する必要がある場合は、影響を理解したうえで使う。

```bash
npm install --legacy-peer-deps
```

[npm公式の設定説明](https://docs.npmjs.com/cli/v11/using-npm/config#legacy-peer-deps)は、この設定を推奨していない。peerを無視して入った組合せは、実際に利用する機能で検証する。

`.npmrc`に常設すると以後の操作にも効く。共有する場合は、その理由と解除する条件をプロジェクトで管理する。`--force`も同等の代替として気軽に追加しない。

## overridesとCIで注意する点

`overrides`は依存ツリーのパッケージを指定した版などへ置き換える仕組みであり、置き換えた先の互換性を証明するものではない。webpack 3を要求するプラグインへwebpack 4を指定しても、そのプラグインが4に対応するようにはならない。

[npmのpackage.json仕様](https://docs.npmjs.com/cli/v11/configuring-npm/package-json#overrides)には、直接依存を上書きする場合は依存指定とoverrideの指定を一致させる制約もある。違う指定を置くと `EOVERRIDE` の原因になる。rootのoverridesで何を置き換えるのか確認してから使う。

`--legacy-peer-deps`でlockfileを作った場合、CIの `npm ci` にも同じ設定が必要になる。[npm ciの公式説明](https://docs.npmjs.com/cli/v11/commands/npm-ci)がこの条件を案内している。

```bash
npm ci --legacy-peer-deps
```

これは回避策を採用したプロジェクト向けの例である。CIだけ通すために追加する前に、開発環境で使った設定とlockfileを確認する。`npm ci`は既存のnode_modulesを削除してからインストールするため、調査だけの目的では実行しない。

## 補足：似ているが別のエラー

`npm warn ERESOLVE overriding peer dependency`は、競合を警告として扱って解決を続けた表示である。その行だけではコマンド全体の成功・失敗を判断できない。最後の終了結果も確認する。

`EBADENGINE`はNode.jsやnpmの版とengines条件の不一致、`EBADPLATFORM`はOS・CPUなどの条件の不一致を示す。peerの要求を無視するフラグで一律に直す問題ではない。

`EOVERRIDE`はoverridesの指定の問題、`ETARGET`は要求を満たす公開版が見つからない場合などに出る。`Found`に正常な版が表示されない場合は、公開版や取得条件の確認も必要になる。

Yarnやpnpmへ変更する場合も、npmの設定名や既定動作をそのまま当てはめない。パッケージマネージャーの変更は互換性のある版を選ぶ作業の代わりにはならない。

## 解決手順のまとめ

`Found:`の版と、`peer ... from ...`の要求範囲を比べ、要求元と要求先を互換性のある版に揃える。npmの版とstrict設定も確認する。回避が必要な場合はlegacy-peer-depsとforceの違いを理解し、lockfile作成時とCIの設定を揃えて、ビルド・テストで確認する。

本記事のコマンドは調査・対処の例であり、外部パッケージを使ったインストール結果は未検証です。公式仕様・現行ソース・過去のGitHub報告を2026年10月9日に確認しました。

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
