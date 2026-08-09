---
title: "Docker の manifest unknown エラー：原因と解決策"
date: 2026-08-05
description: "Docker の manifest unknown は、レジストリ到達後に指定タグや digest の manifest が見つからない状態です。"
tags: ["Docker"]
images: ["og/posts/docker_manifest_unknown.png"]
errorCode: "manifest_unknown"
urgency: "medium"
service: "Docker"
error_type: "manifest_unknown"
components: []
related_services: []
---

## 冒頭まとめ

`manifest unknown` は、[レジストリ](/glossary/レジストリ/)との通信自体は成立しているのに、指定した image reference（[タグ](/glossary/タグ/)またはダイジェスト）に対応する manifest がその[リポジトリ](/glossary/リポジトリ/)で解決できなかったときに出る[エラー](/glossary/エラー/)です。OCI Distribution Specification では、[リポジトリ](/glossary/リポジトリ/)に blob または manifest が見つからない場合の応答は 404 Not Found と定められており、この系統の[エラー](/glossary/エラー/)は「[サーバー](/glossary/サーバー/)が壊れている」ではなく「参照先が存在するか」を疑うところから始めます（[OCI Distribution Specification](https://github.com/opencontainers/distribution-spec/blob/main/spec.md)）。

調査は次の3点を順に確認するのが最短です。

1. 指定した[タグ](/glossary/タグ/)またはダイジェストが、その[リポジトリ](/glossary/リポジトリ/)に実在するか
2. image reference の各要素（レジストリホスト、名前空間、[リポジトリ](/glossary/リポジトリ/)名、[タグ](/glossary/タグ/)、プラットフォーム）が意図したものになっているか
3. 直前の build・tag・push、マルチアーキテクチャの manifest 公開が本当に完了しているか

## エラーの概要

`manifest unknown` は、[レジストリ](/glossary/レジストリ/)が「その[リポジトリ](/glossary/リポジトリ/)に、要求された manifest がない」と応答している状態です。名前解決や [TLS](/glossary/tls/) の失敗とは違い、[リクエスト](/glossary/リクエスト/)は[レジストリ](/glossary/レジストリ/)まで届いています。[認証](/glossary/認証/)[エラー](/glossary/エラー/)とも異なり、[レジストリ](/glossary/レジストリ/)は[リクエスト](/glossary/リクエスト/)を受け付けたうえで「該当なし」を返しています。

近い[エラー](/glossary/エラー/)との違いを整理すると、次のように分類できます。

| 出力の傾向 | 意味するもの | 最初に見る場所 |
| --- | --- | --- |
| `manifest unknown`（manifest が見つからない） | 参照先の[タグ](/glossary/タグ/)・ダイジェストが存在しない | image reference と[タグ](/glossary/タグ/)一覧 |
| `denied` / `unauthorized` などの権限系の文言 | [認証](/glossary/認証/)・[認可](/glossary/認可/)が足りない、または対象が非公開 | [ログイン](/glossary/ログイン/)状態と[アクセス権](/glossary/アクセス権/) |
| 接続[タイムアウト](/glossary/タイムアウト/)、名前解決失敗、[証明書](/glossary/証明書/)[エラー](/glossary/エラー/) | [レジストリ](/glossary/レジストリ/)まで到達できていない | [ネットワーク](/glossary/ネットワーク/)、[プロキシ](/glossary/プロキシ/)、[TLS](/glossary/tls/) 設定 |
| 500・502・503・504 | [レジストリ](/glossary/レジストリ/)側の障害 | [レジストリ](/glossary/レジストリ/)の稼働状況 |

なお、非公開[リポジトリ](/glossary/リポジトリ/)に対して存在を隠すために「見つからない」相当の応答を返す[レジストリ](/glossary/レジストリ/)もあります。権限系と参照先不在の切り分けで迷う場合は、対象[レジストリ](/glossary/レジストリ/)の公式ドキュメントで応答の仕様を確認してください。

本記事が扱う範囲は、`docker pull` や `docker push` の時点で発生する、[レジストリ](/glossary/レジストリ/)上の manifest 解決失敗です。[認証](/glossary/認証/)・[認可](/glossary/認可/)[エラー](/glossary/エラー/)、[レジストリ](/glossary/レジストリ/)への到達性そのものの問題、および [Kubernetes](/glossary/kubernetes/) の Pod sandbox 作成段階の[イベント](/glossary/イベント/)（`FailedCreatePodSandbox` など）は、発生する層が異なるため本記事の対象外とします。

## エラーメッセージの読み方

この[エラー](/glossary/エラー/)の出力には、原因を絞り込むための情報が2つ含まれています。

- **解決に失敗した image reference**：どの[レジストリ](/glossary/レジストリ/)の、どの[リポジトリ](/glossary/リポジトリ/)の、どの[タグ](/glossary/タグ/)（またはダイジェスト）を探したか
- **エラーコードにあたる語句**：`manifest unknown` という表現

文言そのものは、[クライアント](/glossary/クライアント/)と[レジストリ](/glossary/レジストリ/)の実装や版によって異なります。ここで例文を暗記するのではなく、手元の実際の出力をそのまま基準にしてください。読むときのポイントは次のとおりです。

- reference を要素ごとに分解する：`<registry>/<namespace>/<image>:<tag>` のどこが自分の想定と違うかを見る
- 出力に `latest` が現れている場合、[タグ](/glossary/タグ/)を省略したために暗黙で `latest` が補われた可能性を疑う
- `@sha256:` で始まるダイジェスト参照が出ている場合は、ダイジェストの取り違えや、参照先 manifest が既に存在しないケースを疑う
- プラットフォームの不一致は `manifest unknown` とは別の文言になることがあります。判断は実際の出力の文言で行ってください

## 原因と解決策

### 早見表

| 原因 | 主な確認 | 対処 |
| --- | --- | --- |
| [タグ](/glossary/タグ/)が存在しない、`latest` が公開されていない | [タグ](/glossary/タグ/)一覧、`docker manifest inspect` | 実在する[タグ](/glossary/タグ/)を明示して pull する |
| image reference の指定違い（ホスト、名前空間、名前、プラットフォーム） | reference の各要素、認証済み[アカウント](/glossary/アカウント/) | reference を完全な形で指定し直す |
| push や manifest 公開が未完了 | [CI/CD](/glossary/ci-cd/) の[ログ](/glossary/ログ/)、push 後の[タグ](/glossary/タグ/)確認 | 公開を完了させてから pull する |

### 原因1：指定したタグがリポジトリに存在しない

[タグ](/glossary/タグ/)名の打ち間違い、[タグ](/glossary/タグ/)の削除や付け替え、そして[タグ](/glossary/タグ/)を省略して `latest` が暗黙に指定されるケースが典型です。[リポジトリ](/glossary/リポジトリ/)に `latest` を公開していない[プロジェクト](/glossary/プロジェクト/)は珍しくありません。

対処は、reference を省略せずに指定し、存在する[タグ](/glossary/タグ/)を確認することです。

```bash
# タグを明示して pull する
docker pull <your-registry>/<your-namespace>/<your-image>:<your-tag>

# 指定した reference の manifest が存在するかを確認する
docker manifest inspect <your-registry>/<your-namespace>/<your-image>:<your-tag>
```

[タグ](/glossary/タグ/)の一覧は、対象[レジストリ](/glossary/レジストリ/)の管理画面か、OCI Distribution Specification で定義されている[タグ](/glossary/タグ/)一覧の [API](/glossary/api/) で確認します。[エンドポイント](/glossary/エンドポイント/)の正確な形式は、上記の仕様書と各[レジストリ](/glossary/レジストリ/)の公式リファレンスで確認してください。

`docker manifest` は[クライアント](/glossary/クライアント/)の版によって利用可否や構文が異なることがあるため、実行前に手元で確認しておくと確実です。

```bash
docker manifest --help
docker manifest inspect --help
```

### 原因2：image reference が意図した対象を指していない

レジストリホストの誤り、名前空間や組織名の誤り、似た名前の[リポジトリ](/glossary/リポジトリ/)、そしてプラットフォーム指定の不一致により、意図した manifest list や image manifest とは別の対象を参照している場合があります。レジストリホストを省略したときの既定の参照先は、[クライアント](/glossary/クライアント/)とその設定によって変わります。切り分け中は省略せず、完全な形で指定してください。

```bash
# レジストリホストから明示して確認する
docker manifest inspect <your-registry>/<your-namespace>/<your-image>:<your-tag>
```

`docker manifest inspect` の出力で、対象が manifest list（マルチアーキテクチャ）である場合は、含まれるプラットフォームの一覧を確認できます。目的のプラットフォームが含まれていなければ、pull 側の指定を変えるより、公開側に必要なアーキテクチャを追加するのが本筋の対処です。

また、対象が非公開の場合は、認証済みの[アカウント](/glossary/アカウント/)がその[リポジトリ](/glossary/リポジトリ/)を参照できるかどうかも切り分け対象になります。

```bash
docker login <your-registry>
```

### 原因3：参照先の manifest がレジストリに存在しない

ビルドや push の途中失敗、マルチアーキテクチャ manifest の未作成、[タグ](/glossary/タグ/)付け忘れによって、pull しようとしている manifest がまだ公開されていないケースです。

ここは仕様上の裏付けがあります。OCI Distribution Specification では、push は[イメージ](/glossary/イメージ/)を構成する blob を先に、manifest を最後に[アップロード](/glossary/アップロード/)する順序が一般的とされています。つまり push が途中で失敗すると、blob だけが存在して manifest が未登録という状態が起こり得ます。[ログ](/glossary/ログ/)上は「[アップロード](/glossary/アップロード/)が進んでいた」ように見えても、[タグ](/glossary/タグ/)は解決できません（[OCI Distribution Specification](https://github.com/opencontainers/distribution-spec/blob/main/spec.md)）。

対処は、公開側の工程を順序どおりに完了させ、公開を確認してから pull することです。

```bash
# 1. タグを付ける
docker tag <your-local-image> <your-registry>/<your-namespace>/<your-image>:<your-tag>

# 2. push する（終了コードと出力を必ず確認する）
docker push <your-registry>/<your-namespace>/<your-image>:<your-tag>

# 3. レジストリ側で解決できることを確認する
docker manifest inspect <your-registry>/<your-namespace>/<your-image>:<your-tag>
```

マルチアーキテクチャで配布する場合は、各アーキテクチャの[イメージ](/glossary/イメージ/)を push したうえで、manifest の作成と公開まで終える必要があります。構文は版により異なるため、`docker manifest create --help` と `docker manifest push --help` で確認してから実行してください。[CI/CD](/glossary/ci-cd/) では、build → tag → push → manifest 作成 → manifest 公開の順序と、各ステップの終了[コード](/glossary/コード/)をパイプラインの[ログ](/glossary/ログ/)で確認します。前段が失敗しているのに後段が走っている構成では、この[エラー](/glossary/エラー/)が再発します。

## 確認・切り分け手順

上から順に実行すると、原因を機械的に絞り込めます。

1. **実際の出力を保存する**：文言と reference を一字も変えずに記録します。ここが以降の判断材料になります。

    ```[bash](/glossary/bash/)
    docker pull <your-registry>/<your-namespace>/<your-image>:<your-tag>
    ```

2. **[エラー](/glossary/エラー/)の種類を分類する**：`manifest unknown` なのか、権限系の文言なのか、接続[エラー](/glossary/エラー/)なのか、5xx なのかを確認します。権限系や接続系であれば、本記事ではなくそれぞれの原因を追います。

3. **reference を完全な形にして再試行する**：レジストリホスト、名前空間、[リポジトリ](/glossary/リポジトリ/)名、[タグ](/glossary/タグ/)をすべて明示します。ここで成功した場合、原因は省略時の既定値（`latest` や既定[レジストリ](/glossary/レジストリ/)）でした。

4. **manifest の存在を直接確認する**：

    ```[bash](/glossary/bash/)
    docker manifest inspect <your-registry>/<your-namespace>/<your-image>:<your-tag>
    ```

    - 成功する場合：参照先は存在します。プラットフォーム指定や、pull を実行している環境側の設定を疑います
    - 失敗する場合：参照先が存在しません。[タグ](/glossary/タグ/)一覧と公開側の工程を確認します

5. **[タグ](/glossary/タグ/)一覧と突き合わせる**：[レジストリ](/glossary/レジストリ/)の管理画面または[タグ](/glossary/タグ/)一覧 [API](/glossary/api/) で、実在する[タグ](/glossary/タグ/)を列挙して比較します。

6. **ダイジェストで確認する**：[タグ](/glossary/タグ/)ではなくダイジェストで解決できるかを試すと、[タグ](/glossary/タグ/)の付け替えと manifest 自体の不在を切り分けられます。

    ```[bash](/glossary/bash/)
    docker manifest inspect <your-registry>/<your-namespace>/<your-image>@sha256:<your-digest>
    ```

7. **ローカルの状態と混同していないか確認する**：手元にある[イメージ](/glossary/イメージ/)と、[レジストリ](/glossary/レジストリ/)上の公開状況は別です。

    ```[bash](/glossary/bash/)
    docker image ls --digests
    ```

8. **公開側の[ログ](/glossary/ログ/)を確認する**：[CI/CD](/glossary/ci-cd/) の push ステップが成功しているか、manifest の公開まで到達しているかを確認します。

対処後は、手順4と手順1を再実行し、`docker manifest inspect` が manifest を返し、`docker pull` が完了することを確認してください。

## それでも解決しない場合

原因が絞り込めないときは、次の情報を揃えてから問い合わせや調査を進めると早く進みます。

- 実行した[コマンド](/glossary/コマンド/)と、その完全な出力（reference と文言を省略しないもの）
- 対象[レジストリ](/glossary/レジストリ/)の種類（[Docker](/glossary/docker/) Hub、GHCR、Amazon ECR など）と[リポジトリ](/glossary/リポジトリ/)名
- [ログイン](/glossary/ログイン/)済みの[アカウント](/glossary/アカウント/)、およびその[アカウント](/glossary/アカウント/)が対象[リポジトリ](/glossary/リポジトリ/)を参照できるか
- 対象[タグ](/glossary/タグ/)が[レジストリ](/glossary/レジストリ/)の管理画面や[タグ](/glossary/タグ/)一覧 [API](/glossary/api/) で見えるか
- 対象が manifest list かどうか、含まれるプラットフォーム
- 直近の push、manifest 公開が成功しているか（[CI/CD](/glossary/ci-cd/) の[ログ](/glossary/ログ/)の該当箇所）
- 別の[環境](/glossary/環境/)や別の[アカウント](/glossary/アカウント/)で同じ reference を pull した結果

そのうえで、次の点も確認してください。

- **レジストリミラーや[プロキシ](/glossary/プロキシ/)を経由していないか**：経由している場合、参照しているのは本来の[レジストリ](/glossary/レジストリ/)ではない可能性があります。[デーモン](/glossary/デーモン/)のミラー設定と、その経路で対象[タグ](/glossary/タグ/)が取得できるかを確認します。設定項目名は、利用している[クライアント](/glossary/クライアント/)の公式リファレンスで確認してください。
- **[クライアント](/glossary/クライアント/)と[レジストリ](/glossary/レジストリ/)の応答仕様**：manifest や[タグ](/glossary/タグ/)の取得 [API](/glossary/api/) の挙動は [OCI Distribution Specification](https://github.com/opencontainers/distribution-spec/blob/main/spec.md) が基準です。レジジストリ固有の挙動は、各[レジストリ](/glossary/レジストリ/)の公式ドキュメントで確認します。
- **[レジストリ](/glossary/レジストリ/)側の稼働状況**：応答が 5xx に変わっている場合は、参照先の問題ではなく[レジストリ](/glossary/レジストリ/)側の障害です。

なお、[認証](/glossary/認証/)を外す、[TLS](/glossary/tls/) 検証を無効にする、意図しない[タグ](/glossary/タグ/)を `latest` として上書きするといった操作は、原因の解消ではなく別の問題を持ち込みます。切り分けの主手段にはしないでください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
