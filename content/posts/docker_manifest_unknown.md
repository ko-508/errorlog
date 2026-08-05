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

`manifest unknown` は、レジストリとの通信自体は成立しているのに、指定した image reference（タグまたはダイジェスト）に対応する manifest がそのリポジトリで解決できなかったときに出るエラーです。OCI Distribution Specification では、リポジトリに blob または manifest が見つからない場合の応答は 404 Not Found と定められており、この系統のエラーは「サーバーが壊れている」ではなく「参照先が存在するか」を疑うところから始めます（[OCI Distribution Specification](https://github.com/opencontainers/distribution-spec/blob/main/spec.md)）。

調査は次の3点を順に確認するのが最短です。

1. 指定したタグまたはダイジェストが、そのリポジトリに実在するか
2. image reference の各要素（レジストリホスト、名前空間、リポジトリ名、タグ、プラットフォーム）が意図したものになっているか
3. 直前の build・tag・push、マルチアーキテクチャの manifest 公開が本当に完了しているか

## エラーの概要

`manifest unknown` は、レジストリが「そのリポジトリに、要求された manifest がない」と応答している状態です。名前解決や TLS の失敗とは違い、リクエストはレジストリまで届いています。認証エラーとも異なり、レジストリはリクエストを受け付けたうえで「該当なし」を返しています。

近いエラーとの違いを整理すると、次のように分類できます。

| 出力の傾向 | 意味するもの | 最初に見る場所 |
| --- | --- | --- |
| `manifest unknown`（manifest が見つからない） | 参照先のタグ・ダイジェストが存在しない | image reference とタグ一覧 |
| `denied` / `unauthorized` などの権限系の文言 | 認証・認可が足りない、または対象が非公開 | ログイン状態とアクセス権 |
| 接続タイムアウト、名前解決失敗、証明書エラー | レジストリまで到達できていない | ネットワーク、プロキシ、TLS 設定 |
| 500・502・503・504 | レジストリ側の障害 | レジストリの稼働状況 |

なお、非公開リポジトリに対して存在を隠すために「見つからない」相当の応答を返すレジストリもあります。権限系と参照先不在の切り分けで迷う場合は、対象レジストリの公式ドキュメントで応答の仕様を確認してください。

本記事が扱う範囲は、`docker pull` や `docker push` の時点で発生する、レジストリ上の manifest 解決失敗です。認証・認可エラー、レジストリへの到達性そのものの問題、および Kubernetes の Pod sandbox 作成段階のイベント（`FailedCreatePodSandbox` など）は、発生する層が異なるため本記事の対象外とします。

## エラーメッセージの読み方

このエラーの出力には、原因を絞り込むための情報が2つ含まれています。

- **解決に失敗した image reference**：どのレジストリの、どのリポジトリの、どのタグ（またはダイジェスト）を探したか
- **エラーコードにあたる語句**：`manifest unknown` という表現

文言そのものは、クライアントとレジストリの実装や版によって異なります。ここで例文を暗記するのではなく、手元の実際の出力をそのまま基準にしてください。読むときのポイントは次のとおりです。

- reference を要素ごとに分解する：`<registry>/<namespace>/<image>:<tag>` のどこが自分の想定と違うかを見る
- 出力に `latest` が現れている場合、タグを省略したために暗黙で `latest` が補われた可能性を疑う
- `@sha256:` で始まるダイジェスト参照が出ている場合は、ダイジェストの取り違えや、参照先 manifest が既に存在しないケースを疑う
- プラットフォームの不一致は `manifest unknown` とは別の文言になることがあります。判断は実際の出力の文言で行ってください

## 原因と解決策

### 早見表

| 原因 | 主な確認 | 対処 |
| --- | --- | --- |
| タグが存在しない、`latest` が公開されていない | タグ一覧、`docker manifest inspect` | 実在するタグを明示して pull する |
| image reference の指定違い（ホスト、名前空間、名前、プラットフォーム） | reference の各要素、認証済みアカウント | reference を完全な形で指定し直す |
| push や manifest 公開が未完了 | CI/CD のログ、push 後のタグ確認 | 公開を完了させてから pull する |

### 原因1：指定したタグがリポジトリに存在しない

タグ名の打ち間違い、タグの削除や付け替え、そしてタグを省略して `latest` が暗黙に指定されるケースが典型です。リポジトリに `latest` を公開していないプロジェクトは珍しくありません。

対処は、reference を省略せずに指定し、存在するタグを確認することです。

```bash
# タグを明示して pull する
docker pull <your-registry>/<your-namespace>/<your-image>:<your-tag>

# 指定した reference の manifest が存在するかを確認する
docker manifest inspect <your-registry>/<your-namespace>/<your-image>:<your-tag>
```

タグの一覧は、対象レジストリの管理画面か、OCI Distribution Specification で定義されているタグ一覧の API で確認します。エンドポイントの正確な形式は、上記の仕様書と各レジストリの公式リファレンスで確認してください。

`docker manifest` はクライアントの版によって利用可否や構文が異なることがあるため、実行前に手元で確認しておくと確実です。

```bash
docker manifest --help
docker manifest inspect --help
```

### 原因2：image reference が意図した対象を指していない

レジストリホストの誤り、名前空間や組織名の誤り、似た名前のリポジトリ、そしてプラットフォーム指定の不一致により、意図した manifest list や image manifest とは別の対象を参照している場合があります。レジストリホストを省略したときの既定の参照先は、クライアントとその設定によって変わります。切り分け中は省略せず、完全な形で指定してください。

```bash
# レジストリホストから明示して確認する
docker manifest inspect <your-registry>/<your-namespace>/<your-image>:<your-tag>
```

`docker manifest inspect` の出力で、対象が manifest list（マルチアーキテクチャ）である場合は、含まれるプラットフォームの一覧を確認できます。目的のプラットフォームが含まれていなければ、pull 側の指定を変えるより、公開側に必要なアーキテクチャを追加するのが本筋の対処です。

また、対象が非公開の場合は、認証済みのアカウントがそのリポジトリを参照できるかどうかも切り分け対象になります。

```bash
docker login <your-registry>
```

### 原因3：参照先の manifest がレジストリに存在しない

ビルドや push の途中失敗、マルチアーキテクチャ manifest の未作成、タグ付け忘れによって、pull しようとしている manifest がまだ公開されていないケースです。

ここは仕様上の裏付けがあります。OCI Distribution Specification では、push はイメージを構成する blob を先に、manifest を最後にアップロードする順序が一般的とされています。つまり push が途中で失敗すると、blob だけが存在して manifest が未登録という状態が起こり得ます。ログ上は「アップロードが進んでいた」ように見えても、タグは解決できません（[OCI Distribution Specification](https://github.com/opencontainers/distribution-spec/blob/main/spec.md)）。

対処は、公開側の工程を順序どおりに完了させ、公開を確認してから pull することです。

```bash
# 1. タグを付ける
docker tag <your-local-image> <your-registry>/<your-namespace>/<your-image>:<your-tag>

# 2. push する（終了コードと出力を必ず確認する）
docker push <your-registry>/<your-namespace>/<your-image>:<your-tag>

# 3. レジストリ側で解決できることを確認する
docker manifest inspect <your-registry>/<your-namespace>/<your-image>:<your-tag>
```

マルチアーキテクチャで配布する場合は、各アーキテクチャのイメージを push したうえで、manifest の作成と公開まで終える必要があります。構文は版により異なるため、`docker manifest create --help` と `docker manifest push --help` で確認してから実行してください。CI/CD では、build → tag → push → manifest 作成 → manifest 公開の順序と、各ステップの終了コードをパイプラインのログで確認します。前段が失敗しているのに後段が走っている構成では、このエラーが再発します。

## 確認・切り分け手順

上から順に実行すると、原因を機械的に絞り込めます。

1. **実際の出力を保存する**：文言と reference を一字も変えずに記録します。ここが以降の判断材料になります。

    ```bash
    docker pull <your-registry>/<your-namespace>/<your-image>:<your-tag>
    ```

2. **エラーの種類を分類する**：`manifest unknown` なのか、権限系の文言なのか、接続エラーなのか、5xx なのかを確認します。権限系や接続系であれば、本記事ではなくそれぞれの原因を追います。

3. **reference を完全な形にして再試行する**：レジストリホスト、名前空間、リポジトリ名、タグをすべて明示します。ここで成功した場合、原因は省略時の既定値（`latest` や既定レジストリ）でした。

4. **manifest の存在を直接確認する**：

    ```bash
    docker manifest inspect <your-registry>/<your-namespace>/<your-image>:<your-tag>
    ```

    - 成功する場合：参照先は存在します。プラットフォーム指定や、pull を実行している環境側の設定を疑います
    - 失敗する場合：参照先が存在しません。タグ一覧と公開側の工程を確認します

5. **タグ一覧と突き合わせる**：レジストリの管理画面またはタグ一覧 API で、実在するタグを列挙して比較します。

6. **ダイジェストで確認する**：タグではなくダイジェストで解決できるかを試すと、タグの付け替えと manifest 自体の不在を切り分けられます。

    ```bash
    docker manifest inspect <your-registry>/<your-namespace>/<your-image>@sha256:<your-digest>
    ```

7. **ローカルの状態と混同していないか確認する**：手元にあるイメージと、レジストリ上の公開状況は別です。

    ```bash
    docker image ls --digests
    ```

8. **公開側のログを確認する**：CI/CD の push ステップが成功しているか、manifest の公開まで到達しているかを確認します。

対処後は、手順4と手順1を再実行し、`docker manifest inspect` が manifest を返し、`docker pull` が完了することを確認してください。

## それでも解決しない場合

原因が絞り込めないときは、次の情報を揃えてから問い合わせや調査を進めると早く進みます。

- 実行したコマンドと、その完全な出力（reference と文言を省略しないもの）
- 対象レジストリの種類（Docker Hub、GHCR、Amazon ECR など）とリポジトリ名
- ログイン済みのアカウント、およびそのアカウントが対象リポジトリを参照できるか
- 対象タグがレジストリの管理画面やタグ一覧 API で見えるか
- 対象が manifest list かどうか、含まれるプラットフォーム
- 直近の push、manifest 公開が成功しているか（CI/CD のログの該当箇所）
- 別の環境や別のアカウントで同じ reference を pull した結果

そのうえで、次の点も確認してください。

- **レジストリミラーやプロキシを経由していないか**：経由している場合、参照しているのは本来のレジストリではない可能性があります。デーモンのミラー設定と、その経路で対象タグが取得できるかを確認します。設定項目名は、利用しているクライアントの公式リファレンスで確認してください。
- **クライアントとレジストリの応答仕様**：manifest やタグの取得 API の挙動は [OCI Distribution Specification](https://github.com/opencontainers/distribution-spec/blob/main/spec.md) が基準です。レジジストリ固有の挙動は、各レジストリの公式ドキュメントで確認します。
- **レジストリ側の稼働状況**：応答が 5xx に変わっている場合は、参照先の問題ではなくレジストリ側の障害です。

なお、認証を外す、TLS 検証を無効にする、意図しないタグを `latest` として上書きするといった操作は、原因の解消ではなく別の問題を持ち込みます。切り分けの主手段にはしないでください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
