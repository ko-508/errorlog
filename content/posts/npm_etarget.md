---
title: "npm の ETARGET エラー：原因と解決策"
date: 2026-08-08
description: "ETARGET は要求した版が候補に無いという意味なので、パッケージ名は存在するという前提のうえで、要求側と候補側のどちらがずれているかを notarget の1行目から切り分けます。"
tags: ["npm"]
images: ["og/posts/npm_etarget.png"]
errorCode: "ETARGET"
error_name: "No matching version found for <package>@<range>."
error_aliases:
  - "npm error code ETARGET"
  - "npm ERR! code ETARGET"
  - "notarget No matching version found"
  - "No avoidable versions for"
  - "In most cases you or one of your dependencies are requesting a package version that doesn't exist"
lastmod: 2026-08-08
service: "npm"
error_type: "ETARGET"
components: ["npm CLI", "npm-pick-manifest"]
related_services: ["Node.js", "GitHub Actions"]
error_cases:
  - id: "version-does-not-exist"
    situation: "自分で package.json に書いた版、または npm install で直接指定した版でだけ失敗する"
    messages:
      - "npm error code ETARGET"
      - "npm error notarget No matching version found for <package>@<range>."
    cause: "指定した範囲に合う版が公開されていない可能性がある"
    check: "npm view <package> versions を実行し、出力の一覧に指定した範囲へ入る版があるかを確認する"
    fix: "一覧にある版へ指定を直す"
  - id: "dist-tag-not-published"
    situation: "latest では成功するが、next や beta のような別のタグを指定したときだけ失敗する"
    messages:
      - "npm error code ETARGET"
      - "npm error notarget No matching version found for <package>@<tag>."
    cause: "そのタグが公開されていない可能性がある"
    check: "npm view <package> dist-tags を実行し、指定したタグが一覧に出るかを確認する"
    fix: "存在するタグへ変えるか、タグではなく版で指定する"
  - id: "time-cutoff-applied"
    situation: "同じ package.json が以前は通っていたのに、CI や共有設定の変更後から失敗するようになった"
    messages:
      - "npm error code ETARGET"
      - "npm error notarget No matching version found for <package>@<range> with a date before <date>."
    cause: "before または min-release-age による時刻の絞り込みが効いている可能性がある"
    check: "文言に with a date before が含まれるかを確認し、npm config get before と npm config get min-release-age の値を見る"
    fix: "絞り込みの値を見直すか、その時点で公開されていた版へ指定を合わせる"
  - id: "registry-mirror-lag"
    situation: "公開レジストリからは取得できるが、社内や私用のレジストリを向けたときだけ失敗する"
    messages:
      - "npm error code ETARGET"
      - "npm error notarget No matching version found for <package>@<range>."
    cause: "向き先のレジストリにその版がまだ同期されていない可能性がある"
    check: "npm config get registry で向き先を確認し、npm view <package> versions --registry https://registry.npmjs.org の結果と見比べる"
    fix: "向き先のレジストリへ該当の版を取り込むか、そのレジストリに存在する版へ指定を合わせる"
  - id: "audit-fix-no-candidate"
    situation: "npm audit fix を実行したときだけ失敗する"
    messages:
      - "npm error code ETARGET"
      - "npm error notarget No avoidable versions for <package>"
    cause: "脆弱性を避けられる版が候補の中に無い可能性がある"
    check: "npm audit の出力で対象パッケージの修正先が示されているかを確認し、npm view <package> versions と見比べる"
    fix: "上流の更新を待つか、依存元の版を上げて別の系統へ移す"
trend_incident: false
---

## 結論

`npm error code ETARGET` は、要求した版が候補の中に無いという意味です。npm が加える説明は1文だけで、「多くの場合、あなたか依存のどれかが存在しない版を要求している」と述べます。

前提として、パッケージ名そのものは見つかっています。名前が見つからない場合は `E404` になります。つまり `ETARGET` が出ている時点で、確認すべきは名前ではなく版です。

読む場所は `notarget` の1行目です。実装は要求した名前と範囲を組み立てて `No matching version found for <名前>@<範囲>.` という文を作ります。ここに出ている範囲が、自分が書いたものと一致するかをまず見てください。一致しなければ、要求しているのは自分ではなく依存のどれかです。

もう1つ、この1行目には条件が付くことがあります。時刻による絞り込みが有効な場合、範囲の後ろに `with a date before <日時>` が加わります。この語句が見えたら、原因は版の指定ではなく絞り込みの設定です。

## エラーが発生する処理段階

npm は依存の木を組み立てる過程で、パッケージごとに候補の一覧を取得し、その中から要求に合う1つを選びます。`ETARGET` はこの選択の段階で出ます。

第一段階は名前の解決です。[レジストリ](/glossary/レジストリ/)から、そのパッケージの全版の情報をまとめた文書を取得します。ここで見つからなければ `E404` になります。

第二段階は候補の絞り込みです。時刻による制約が設定されていれば、その日時より後に公開された版を候補から外します。この段階で候補が1つも残らなければ、別の[コード](/glossary/コード/)が返ります。

第三段階が選択です。残った候補から、要求された範囲や[タグ](/glossary/タグ/)に合うものを探します。見つからなければ `ETARGET` になります。

第四段階は取得です。ここまで来ていれば版は決まっているため、`ETARGET` は出ません。

つまり `ETARGET` は、候補の一覧は手に入っているが、その中に該当が無いという状態を指します。[ネットワーク](/glossary/ネットワーク/)や[認証](/glossary/認証/)の問題ではありません。

## 最初に確認すること

まず、`notarget` の1行目を正確に読みます。

```text
npm error code ETARGET
npm error notarget No matching version found for react@^99.0.0.
npm error notarget In most cases you or one of your dependencies are requesting
npm error notarget a package version that doesn't exist.
```

`@` の後ろが、実際に要求されている範囲です。自分の[設定ファイル](/glossary/設定ファイル/)に書いた内容と一致するかを確かめてください。

```bash
grep -n "\"<パッケージ名>\"" package.json
```

一致しない場合、要求しているのは依存のどれかです。どこから来ているかを追えます。

```bash
npm ls <パッケージ名>
```

次に、候補の一覧を取得して突き合わせます。

```bash
npm view <パッケージ名> versions
npm view <パッケージ名> dist-tags
```

一覧に該当する版があるのに失敗する場合は、時刻の絞り込みか向き先の[レジストリ](/glossary/レジストリ/)を疑います。1行目に `with a date before` が含まれていれば前者で確定です。

## 原因別の確認方法と解決策

### 原因1：指定した範囲に合う版が存在しない {#version-does-not-exist}

最も多い形です。打ち間違いか、まだ公開されていない版を指定しています。

確認方法は一覧との突き合わせです。

```bash
npm view react versions --json | tail -20
```

出力の末尾が公開済みの最新です。要求されている範囲がこれを超えていれば確定します。範囲の書き方そのものが間違っている場合もあります。`^99.0.0` のように大きな番号を書いていないか、`~` と `^` を取り違えていないかを見てください。

対処は実在する版へ直すことです。

```bash
npm install react@^18.3.1
```

[設定ファイル](/glossary/設定ファイル/)を直接書き換えた場合は、記録[ファイル](/glossary/ファイル/)との整合も取り直してください。

### 原因2：指定したタグが公開されていない {#dist-tag-not-published}

`@next` や `@beta` のように[タグ](/glossary/タグ/)で指定している場合です。版と同じ扱いで解決されるため、[タグ](/glossary/タグ/)が無ければ同じ文言になります。

確認方法は[タグ](/glossary/タグ/)の一覧です。

```bash
npm view <パッケージ名> dist-tags
```

`latest` しか出てこないパッケージは多くあります。過去に `next` があっても、公開が止まれば消えます。

対処は、存在する[タグ](/glossary/タグ/)へ変えるか、版で直接指定することです。継続的インテグレーションで使う場合、[タグ](/glossary/タグ/)は指す先が変わるため、版での指定のほうが安定します。

### 原因3：時刻による絞り込みが効いている {#time-cutoff-applied}

1行目に `with a date before <日時>` が含まれている場合です。実装は、絞り込みが有効なときにこの語句を範囲の後ろへ足します。

この絞り込みは2つの設定から来ます。1つは日付を直接指定するもので、公式の説明によれば、指定した日付以前に公開されていた版だけを導入する動きになります。もう1つは日数で指定するもので、公開から指定した日数より前に出ていた版だけを導入します。後者は内部で前者へ変換されます。

確認方法は現在値の照会です。

```bash
npm config get before
npm config get min-release-age
```

どちらかに値が入っていれば確定です。共有の[設定ファイル](/glossary/設定ファイル/)や継続的インテグレーションの[環境変数](/glossary/環境変数/)で設定されていることが多く、手元では再現しない形になります。

対処は絞り込みの見直しです。新しい版を取り込む必要があるなら値を緩め、方針として維持するなら、その時点で公開されていた版へ指定を合わせます。値そのものを消す前に、なぜ設定されたのかを確認してください。供給元の安全確認のために意図的に置かれている場合があります。

なお公式の説明には、[タグ](/glossary/タグ/)で指定した場合の動きも書かれています。[タグ](/glossary/タグ/)が絞り込みを通らない場合、その[タグ](/glossary/タグ/)が指す版以下で最も新しいものが使われます。この経路では失敗せずに、想定より古い版が入ります。

### 原因4：向き先のレジストリに版が無い {#registry-mirror-lag}

社内の中継用[レジストリ](/glossary/レジストリ/)や、範囲ごとに向き先を変えている構成で起きます。公開[レジストリ](/glossary/レジストリ/)には存在する版が、向き先には届いていません。

確認方法は、向き先と候補の突き合わせです。

```bash
npm config get registry
npm view <パッケージ名> versions --registry https://registry.npmjs.org
```

公開[レジストリ](/glossary/レジストリ/)側にあって向き先に無ければ確定です。範囲ごとに向き先を変えている場合は、その設定も確認してください。

```bash
npm config list | grep registry
```

対処は、向き先へ該当の版を取り込むことです。中継の設定によっては、初回の要求をきっかけに取り込む動きになっているものもあります。取り込みが行えない場合は、向き先に存在する版へ指定を合わせてください。向き先を公開[レジストリ](/glossary/レジストリ/)へ切り替える対処は、社内の方針に反する場合があります。切り替える前に確認してください。

### 原因5：脆弱性を避けられる版が候補に無い {#audit-fix-no-candidate}

`npm audit fix` を実行したときだけ出る形です。文言も違い、`No avoidable versions for <名前>` になります。実装では、避けるべき版を除いたうえで候補を探し、それでも見つからない場合にこの文言で失敗します。

確認方法は、報告されている修正先の照会です。

```bash
npm audit
npm view <パッケージ名> versions --json | tail -20
```

修正先として示された版が一覧に無ければ、上流がまだ対応していません。

対処は2つです。上流の更新を待つか、その依存を引き込んでいる側の版を上げて、別の系統へ移すことです。

```bash
npm ls <パッケージ名>
```

出力で依存元を特定し、そちらを更新できるかを確認してください。`--force` を付けて実行すると、想定外の版へ動くことがあります。まず依存元の更新を検討してください。

## 近いエラーとの境界

`E404` は名前そのものが見つからない場合です。npm は要求された対象が見つからないか、アクセスの[権限](/glossary/権限/)が無いと説明します。版ではなく名前の綴りや、私用[レジストリ](/glossary/レジストリ/)への[認証](/glossary/認証/)を疑うことになります。

`ENOVERSIONS` は、候補の一覧が空の場合です。実装では `No versions available for <名前>` という文言になります。版が1つも公開されていないか、絞り込みで全部が除かれた状態です。要求に合う版が無い `ETARGET` とは、残っている候補の有無が違います。

`E403` は、候補は見つかったが方針によって取得が禁じられている場合です。実装では、選ばれた版が制限の一覧に含まれるときに `Could not download <名前>@<範囲> due to policy violations:` という文言と共にこの[コード](/glossary/コード/)へ切り替わります。同じ選択処理から出るため紛らわしいですが、[コード](/glossary/コード/)で区別できます。

`ERESOLVE` は、版は存在するが依存どうしの要求がぶつかっている場合です。`ETARGET` は候補に無い、`ERESOLVE` は候補はあるが両立しない、という違いになります。

`EBADPLATFORM` は、版はあるが動作環境が合っていない場合です。`os` や `cpu` の条件に外れています。

## 内部動作または公式仕様

版の選択は `npm-pick-manifest` が担当します。この処理は、[レジストリ](/glossary/レジストリ/)から取得した全版の情報から候補を組み立て、要求に合う1つを選びます。

候補の組み立てでは、通常の版に加えて、公開準備中のものと制限付きのものも一度は一覧へ入ります。そのうえで時刻の条件が適用され、指定された日時より後のものが除かれます。ここで候補が1つも残らなければ `ENOVERSIONS` になります。

選択に失敗した場合の文言は、その場で組み立てられます。要求の対象は名前と範囲を `@` でつないだもので、時刻の絞り込みが有効であればその後ろに `with a date before <日時>` が加わります。日時は実行環境の表記で出力されます。

そのうえで、選ばれた版が制限の一覧に含まれるかどうかで分岐します。含まれていれば `E403` と方針違反の文言、含まれていなければ `ETARGET` と `No matching version found` の文言です。同じ[関数](/glossary/関数/)から2つの[コード](/glossary/コード/)が出るため、[コード](/glossary/コード/)を見ずに文言だけで判断すると取り違えます。

脆弱性を避ける経路は別に用意されています。避けるべき版が指定されている場合、まず要求どおりの範囲で探し、次に上位互換の範囲、最後に全候補と順に広げます。どれでも避けられる版が見つからなければ `No avoidable versions for <名前>` という文言で失敗します。文言が違うので、`npm audit fix` の経路かどうかはここで判別できます。

npm 側の説明文は1文だけで、[コード](/glossary/コード/)ごとの分岐に固定で書かれています。追加の情報は、この1行目にしかありません。

## バージョン差・注意点

時刻による絞り込みには、日数で指定する設定が加わりました。公式の説明によれば、指定した日数より前から公開されている版だけを導入する動きになり、日付を直接指定する設定を補うものと位置づけられています。両方が同じ設定元にある場合は日付の指定が優先され、設定元をまたぐ場合は通常の優先順位が適用されます。

この設定は、公開直後の版を避ける目的で導入されることがあります。導入すると、それまで通っていた `package.json` が突然 `ETARGET` になります。文言に `with a date before` が付くため区別はできますが、設定した本人以外には理由が見えません。共有の[設定ファイル](/glossary/設定ファイル/)へ置く場合は、意図を記録しておいてください。

出力の接頭辞も変わりました。現在の npm は `npm error` で始まり、古い版は `npm ERR!` でした。`ETARGET` の分岐そのものは変わっていないため、古い記事の説明文は現在も一致します。

対処として版の指定を緩める方法が広く共有されていますが、範囲を広げると別の衝突を招くことがあります。`ETARGET` の解消と引き換えに `ERESOLVE` が出る、という順序で進むこともあります。まず一覧を取得し、実在する版へ合わせるのが確実です。

## Editor's Note

同じ選択処理から `ETARGET` と `E403` の2つが出る点は、調査の手順に影響します。実装を確認すると、選ばれた版が制限の一覧に含まれるかどうかだけで分岐し、含まれていれば `E403` と方針違反の文言、含まれていなければ `ETARGET` と `No matching version found` の文言になります。

当時の状態としては、制限の仕組みが入る前は、この[関数](/glossary/関数/)から出るのは `ETARGET` だけでした。そのため古い解説の多くは「版が見つからない場合はすべて `ETARGET`」という前提で書かれています。実際には、候補が見つかっていても方針で止められる経路が増えています。

現在も適用できるかという点では、切り分けの手順を1段追加する必要があります。`No matching version found` が出ていれば候補に無い、`due to policy violations` が出ていれば候補はあるが取得が禁じられている、という読み分けです。後者で版の指定を直しても解消しません。

もう1つ、時刻による絞り込みが加わったことで、`ETARGET` の意味が広がりました。以前は「その版が存在しない」とほぼ同義でしたが、現在は「その条件下では候補に入らない」という状態も含みます。1行目に `with a date before` が付くかどうかで、この2つを区別してください。

## 参考資料

- [npm config（before、min-release-age、registry）](https://docs.npmjs.com/cli/latest/using-npm/config)
- [npm view](https://docs.npmjs.com/cli/latest/commands/npm-view)
- [npm audit](https://docs.npmjs.com/cli/latest/commands/npm-audit)
- [版の選択処理（npm-pick-manifest）](https://github.com/npm/cli/blob/latest/node_modules/npm-pick-manifest/lib/index.js)
- [エラー文言の生成（error-message.js）](https://github.com/npm/cli/blob/latest/lib/utils/error-message.js)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*