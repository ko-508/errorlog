---
title: "npm の ERESOLVE エラー：原因と解決策"
date: 2026-08-07
description: "ERESOLVE は依存関係の木を組み立てられなかったという意味なので、出力の While resolving・Found・Could not resolve dependency の3行を突き合わせれば、どのパッケージのどの要求が衝突しているかをその場で特定できます。"
tags: ["npm"]
images: ["og/posts/npm_eresolve.png"]
errorCode: "ERESOLVE"
lastmod: 2026-08-07
service: "npm"
error_type: "ERESOLVE"
components: ["Arborist", "npm CLI"]
related_services: ["Node.js", "GitHub Actions"]
trend_incident: false
---

## 結論

`ERESOLVE unable to resolve dependency tree` は、npm が依存関係の木を組み立てられなかったという意味です。実装では、peer 依存の衝突を解決できなかった時点で `unable to resolve dependency tree` という文言の[エラー](/glossary/エラー/)が投げられます。

読むべき場所は3か所です。`While resolving:` は何を導入しようとしていたか、`Found:` は木に既にある物、`Could not resolve dependency:` は満たせなかった要求です。この3行を突き合わせれば、どの[バージョン](/glossary/バージョン/)とどの要求がぶつかっているかがその場で分かります。

`--force` や `--legacy-peer-deps` を付ければ先へ進めますが、これは衝突を解決するのではなく、誤った可能性のある解決を受け入れるという操作です。出力の最後の行にもそう書かれています。まず衝突の中身を読んでください。

## 最初に確認すること

画面に出る説明は深さ4段までに省略されています。全文は[キャッシュ](/glossary/キャッシュ/)の置き場に `eresolve-report.txt` として書き出されており、こちらには省略のない説明と機械可読の内容が入っています。

```bash
cat "$(npm config get cache)/eresolve-report.txt"
```

深い階層で起きている衝突は、画面の出力だけでは追い切れません。相手が分からないときは、まずこのファイルを開いてください。

次に、npm 自身の[バージョン](/glossary/バージョン/)を確認します。peer 依存を厳密に扱う挙動は npm 7 からで、6 以前とは結果が変わります。

```bash
npm --version
```

## 原因別の確認方法と解決策

### 原因1：直接指定した2つのパッケージが、同じ物に別の版を求めている

最も多い形です。`Found:` に出ている版と、`Could not resolve dependency:` の peer の範囲を見比べてください。両方とも `from the root project` と書かれていれば、自分の[設定ファイル](/glossary/設定ファイル/)で指定した2つがぶつかっています。

対処は指定の見直しです。どちらかを、相手の peer の範囲に収まる版へ揃えます。

```bash
npm view some-lib@2.0.0 peerDependencies
```

### 原因2：上流のパッケージが古い範囲のまま更新されていない

`Could not resolve dependency:` の peer が、自分では指定していないパッケージから出ている場合です。更新版が出ていれば、それで解消します。

```bash
npm outdated
```

更新版が無く、実際には動くと確認できている場合に限り、根本の[設定ファイル](/glossary/設定ファイル/)で置き換えを指定できます。公式ドキュメントは、この指定が根本のファイルでのみ有効で、導入済みのパッケージ側の指定は解決に使われないと明記しています。

```json
{
  "overrides": {
    "some-lib": {
      "react": "$react"
    }
  }
}
```

置き換えは、上流が想定していない組み合わせを強制する操作です。動作確認をしてから使ってください。

### 原因3：CI で厳密な設定が有効になっている

手元では通るのに CI だけ失敗する場合です。`strict-peer-deps` は既定では無効で、公式の説明によれば、深い階層の peer 衝突は最も近い非 peer の指定で解決され、警告が出るだけで済みます。この設定を有効にすると、その警告が失敗として扱われます。

```bash
npm config get strict-peer-deps
```

`true` であれば、警告のまま進めてよいかを判断したうえで外してください。出力の対処案に `--no-strict-peer-deps` が含まれている場合は、この設定が有効だという印です。

### 原因4：古い記録が残っている

版を直したのに同じ衝突が出る場合です。`package-lock.json` に前回の解決結果が残っています。

```bash
rm -rf node_modules package-lock.json
npm install
```

記録を消すと、他の依存も新しい版に動く可能性があります。共同で開発している場合は、生成し直した記録の差分を確認してから共有してください。

## 近いエラーとの違い

`npm warn ERESOLVE overriding peer dependency` は警告で、導入自体は成功しています。npm が近い指定を使って自動で解決した、という通知です。同じ語が出ますが、失敗ではありません。

`ETARGET` は、要求された版がそもそも存在しない場合です。公式の説明文にも、依存のどれかが存在しない版を求めていると書かれています。衝突ではなく不在なので、`--legacy-peer-deps` では解消しません。

`E404` は、その名前のパッケージ自体が見つからない場合です。名前の誤りか、私用の置き場への認証が通っていない場合に出ます。

`--legacy-peer-deps` は peer 依存を完全に無視する設定です。公式ドキュメントは、この使用を推奨しないと明記しています。他のパッケージが前提としている取り決めを守らなくなるためです。一時的に前へ進める手段として使い、恒久的な設定にはしないでください。

## 参考資料

- [npm config（legacy-peer-deps、strict-peer-deps）](https://docs.npmjs.com/cli/latest/using-npm/config)
- [package.json（overrides）](https://docs.npmjs.com/cli/latest/configuring-npm/package-json#overrides)
- [ERESOLVE の説明生成（explain-eresolve.js）](https://github.com/npm/cli/blob/latest/lib/utils/explain-eresolve.js)
- [依存関係の組み立て（build-ideal-tree.js）](https://github.com/npm/cli/blob/latest/workspaces/arborist/lib/arborist/build-ideal-tree.js)

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*