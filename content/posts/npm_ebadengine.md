---
title: "npm EBADENGINEの原因と対処法"
date: 2026-10-06T09:00:00+09:00
draft: false
description: "npmのEBADENGINEは、パッケージのenginesが要求するNode.jsやnpmの版を現在の環境が満たさないときに出ます。警告の読み方、間接依存の確認、engine-strictで停止する場合の対処を解説します。"
tags: ["npm"]
images: ["og/posts/npm_ebadengine.png"]
errorCode: "EBADENGINE"
urgency: "medium"
service: "npm"
error_type: "EBADENGINE"
components: ["npm", "Node.js", "package.json"]
related_services: []
trend_incident: false
publish_slug: "npm_ebadengine"
publish_note: "新規作成。enginesの判定、engine-strictの既定値と警告・停止の分岐をnpm公式文書および実装で照合"
publish_zenn: true
---

## 冒頭まとめ

`npm warn EBADENGINE`は、パッケージが要求するNode.jsまたはnpmのバージョンを、現在の環境が満たしていないという警告です。最初に、ログの`package`、`required`、`current`を確認します。

通常は警告として表示され、これだけではインストールを止めません。ただし、`engine-strict=true`が有効な場合は、同じ不一致で`npm error code EBADENGINE`となり、インストールが停止する場合があります。

警告のままインストールできても、動作確認が済んだことにはなりません。プロジェクトが指定するNode.js・npmの版と、警告に出たパッケージの要件を合わせてから、インストールとテストをやり直してください。

## EBADENGINEが示していること

パッケージの`package.json`には、実行環境の要件を`engines`として記述できます。

```json
{
  "engines": {
    "node": ">=24",
    "npm": ">=11"
  }
}
```

この例はNode.js 24以上、npm 11以上を要求しています。数値は説明用で、すべてのプロジェクトにこの版を推奨するものではありません。

[npm公式文書のenginesの説明](https://docs.npmjs.com/cli/v11/configuring-npm/package-json/#engines)では、`engine-strict`が設定されていない場合、この指定は原則として助言的な扱いになると説明されています。

[npm-install-checksの実装](https://github.com/npm/npm-install-checks/blob/main/lib/index.js)は、`engines.node`と`engines.npm`をそれぞれ現在の版と比較し、どちらかが条件を満たさなければ`EBADENGINE`を生成します。Node.jsだけ確認しても、npm側の不一致が残ることがあります。

新しい版なら必ず通るわけでもありません。たとえば`>=18 <24`という要件では、Node.js 24は範囲外です。要求されている下限と上限の両方を確認します。

## 警告にある3項目を確認する

表示例は次のとおりです。パッケージ名と値は説明用です。npmの版によって、接頭辞が`npm WARN`などになることがあります。

```text
npm warn EBADENGINE Unsupported engine {
npm warn EBADENGINE   package: 'example-package@1.2.3',
npm warn EBADENGINE   required: { node: '>=24', npm: '>=11' },
npm warn EBADENGINE   current: { node: 'v22.0.0', npm: '11.0.0' }
npm warn EBADENGINE }
```

`package`は要件に合わないパッケージと版、`required`はそのパッケージの要求、`current`は実行時のNode.js・npmの版です。この例ではnpmの条件は満たしていますが、Node.jsの条件を満たしていません。

失敗した処理と同じターミナルやCIジョブで確認します。

```bash
node -v
npm -v
node -p "process.execPath"
```

バージョン管理ツールを使っている場合、別のターミナルやIDEでは別のNode.jsが選ばれていることがあります。`process.execPath`は、実際に起動したNode.jsの場所を確認するために使います。

実例として、[npm/cliのIssue #2728](https://github.com/npm/cli/issues/2728)には、Angular CLI 11.2.1がnpm `^6.11.0`を要求するのに、npm 7.5.3でインストールして警告が出た報告があります。報告中のNode.js 15.9.0は要求された`>=10.13.0`を満たしており、不一致はnpm側でした。インストール自体は完了していますが、この過去の報告は現在のAngularの対応版を示すものではありません。

## Node.jsとnpmの版を合わせる

まず、プロジェクトのREADME、`package.json`、`.nvmrc`、`.node-version`、CI設定などに指定された環境を確認します。警告を消すためだけに最新版へ変えると、ほかの依存パッケージの上限に合わなくなる場合があります。

対象パッケージの要件は、版を指定して確認できます。次の名前と版は、ログの`package`に表示された実際の値へ置き換えてください。

```bash
npm view example-package@1.2.3 engines
```

版を省略すると、警告に出た版とは異なる要件を確認してしまう可能性があります。取得先へのアクセスが必要なコマンドなので、通信に失敗した場合は、そのエラーも別に確認します。

Node.jsとnpmをプロジェクトの要件に合わせたら、版を再確認し、元の`npm install`または`npm ci`を再実行します。その後、プロジェクトが定めたテストやビルドを実行してください。

環境の版を変更できない場合は、その環境に対応するパッケージ版を調べます。古い版へ戻す際は、必要な機能や修正が含まれるかも確認します。`package-lock.json`を先に削除することは、EBADENGINEの一般的な解決手順ではありません。

## 間接的な依存が原因の場合

警告に出たパッケージが`package.json`の直接依存に見当たらない場合は、別のパッケージが内部で使っている依存かもしれません。

インストールが完了している場合は、次で依存経路を調べられます。名前は実際のパッケージへ置き換えます。

```bash
npm explain example-package
```

[npm explainの公式文書](https://docs.npmjs.com/cli/v11/commands/npm-explain/)は、このコマンドを、パッケージがインストールされた理由となる依存関係の表示に使うと説明しています。

間接依存が原因なら、そのパッケージを直接追加する前に、どの直接依存から入っているかを確認します。直接依存の更新で対応できるか、現在の依存構成が求めるNode.jsを使うかを判断してください。インストールが途中で止まった場合は、`npm explain`で十分な情報が得られないこともあるため、警告の名前とlockfileも手がかりにします。

手元では警告がなくCIだけに出る場合は、CIのNode.js・npmの指定を確認します。Dockerで起きる場合は、コンテナ内の版とDockerfileのベースイメージを確認してください。ホスト側のNode.jsだけ変更しても、コンテナの環境は変わりません。

## engine-strictで停止する場合

現在の設定は次で確認できます。

```bash
npm config get engine-strict
```

[npmの設定文書](https://docs.npmjs.com/cli/v11/using-npm/config/#engine-strict)によると、既定値は`false`です。[npmの依存ツリー構築の実装](https://github.com/npm/cli/blob/latest/workspaces/arborist/lib/arborist/build-ideal-tree.js)では、通常の対象依存について、要件不一致を`engine-strict`が有効なら例外として扱い、無効なら警告として記録します。省略可能な依存などには別の処理もあるため、すべての依存が同じように扱われるとは限りません。

`true`なら、プロジェクトやユーザーの`.npmrc`、CIの環境変数、実行時のフラグを確認します。要件を守るために設定されている場合は、Node.js・npmの版を合わせるのが基本です。

一時的に警告扱いへ変更することが意図に合う場合は、次の指定もできます。

```bash
npm install --no-engine-strict
```

これは不一致を直す操作ではありません。インストールを継続させた後も、実行時の互換性を確認する必要があります。

`--force`にも要件不一致を許容する効果がありますが、[公式文書](https://docs.npmjs.com/cli/v11/using-npm/config/#force)では、ほかの保護も解除する設定として説明されています。EBADENGINEを解消するための通常の第一候補にはしません。

## 補足：似ているが別のもの

| 表示・設定 | 確認すること |
|---|---|
| `npm warn EBADENGINE` | Node.js・npmの要件不一致。警告以外の失敗もログで確認 |
| `npm error code EBADENGINE` | 要件不一致に加え、`engine-strict`など停止する条件を確認 |
| `EBADPLATFORM` | OS・CPUなどの対象環境に関する条件を確認 |
| `devEngines` | 開発に使う環境を検査する別のフィールド。`engines`と区別する |
| `ERESOLVE` | 依存関係の解決ができない問題。Node.jsの版チェックとは区別する |

`devEngines`は`engines.devEngines`ではなく、`package.json`の別のトップレベル項目です。[公式文書](https://docs.npmjs.com/cli/v11/configuring-npm/package-json/#devengines)では、`engines`とは形式も目的も異なる仕組みとして説明されています。

警告の後に別のエラーが出てインストールが止まった場合は、EBADENGINEだけを原因と決めつけないでください。最後のエラーコードと、失敗した処理も確認します。

## 解決手順のまとめ

まず警告の`package`、`required`、`current`を読み、Node.jsとnpmのどちらが条件を満たしていないかを確認します。次に、同じ実行環境で現在の版を調べ、プロジェクトと対象パッケージの要求に合わせます。

間接依存が原因なら依存経路を調べ、CIやDockerだけで発生する場合は、その環境の版を確認します。エラーで停止する場合は`engine-strict`の設定元も確認してください。

インストールが通った後は、テストとビルドで動作を確かめます。「警告だから問題ない」「新しいNode.jsなら必ず解決する」とは判断せず、要求された範囲に合わせることが基本です。

免責事項：本記事の内容は一般的なnpmおよびNode.jsの構成を前提としています。対応する版や検査の挙動は、パッケージとnpmのバージョンによって異なります。環境や依存関係を変更する前に、プロジェクトの要件を確認してください。
