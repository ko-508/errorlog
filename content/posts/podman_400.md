---
title: "Podman の 400 エラー：原因と解決策"
date: 2026-05-28
description: "Podman APIまたはレジストリへのリクエストの形式が正しくない。podman runコマンドのオプション指定が誤っているなど、Podman 400 エラーの原因と解決策を解説。"
tags: ["Podman"]
errorCode: "400"
service: "Podman"
error_type: "400"
components: []
related_services: ["Docker", "systemd", "jq", "curl"]
lastmod: 2026-06-14
---

## Podman の 400 エラー：原因と解決策

## エラーの概要

Podman の 400 エラーは、Podman API またはレジストリへのリクエスト形式が不正であることを示します。コマンド構文の誤り、イメージ指定の形式違反、レジストリ認証情報の不備などが原因として起こり、コンテナの起動やプル操作が失敗します。

## 実際のエラーメッセージ例

```json
{
  "cause": "invalid parameter",
  "message": "Error response from daemon: 400 Bad Request",
  "response": 400
}
```

```bash
$ podman run --memory mycontainer ubuntu:latest
Error: invalid argument "mycontainer" for "--memory" flag: invalid format
400 Bad Request
```

## よくある原因と解決手順

**1. podman run のオプション指定が誤っている**

値が必須のオプション（`--memory`、`--cpus`、`--name` など）に値を指定しない、または不正な形式で指定した場合に発生します。また、イメージ名の前に全てのオプションを配置する必要があり、順序を間違えると 400 エラーが発生します。

**Before（エラーが起きるコード）：**

```bash
podman run --memory mycontainer ubuntu:latest
podman run ubuntu:latest --name test-container
```

**After（修正後）：**

```bash
podman run --memory 512m --name test-container ubuntu:latest
podman run --name test-container ubuntu:latest
```

**2. イメージ名またはタグの形式が不正である**

イメージ名に大文字が含まれている、タグに不正な文字が使用されている、またはレジストリURL の書き方が間違っている場合、リクエストが解析できず 400 エラーが返されます。イメージ名は小文字で、タグには英数字とハイフン、アンダースコア、ドット、コロンのみが許可されます。

**Before（エラーが起きるコード）：**

```bash
podman pull MyImage:Latest
podman run myregistry.com:5000/app image:v1@sha256
```

**After（修正後）：**

```bash
podman pull myimage:latest
podman run myregistry.com:5000/app:v1
```

**3. レジストリ認証情報の形式が不正である**

`podman login` 時にレジストリURL の形式が間違っていたり、認証トークンが `auth.json` に不正な形式で保存されたりすると、プル操作で 400 エラーが発生します。特にプライベートレジストリを使用する場合、URL にプロトコルスキーム（`https://` など）を含める必要があります。

**Before（エラーが起きるコード）：**

```bash
podman login myregistry.com:5000
# auth.json が破損している場合
podman pull myregistry.com:5000/private-app:latest
```

**After（修正後）：**

```bash
podman login https://myregistry.com:5000
podman pull myregistry.com:5000/private-app:latest
```

**4. ポート指定やネットワークオプションの形式が不正である**

`-p` フラグでポートマッピングを指定する際、形式が違うと 400 エラーが発生します。正しい形式は `-p <host-port>:<container-port>` または `-p <host-ip>:<host-port>:<container-port>` です。また、`--net` オプションで存在しないネットワークを指定した場合も同様です。

**Before（エラーが起きるコード）：**

```bash
podman run -p 8080-80 ubuntu:latest
podman run --net invalid-network ubuntu:latest
```

**After（修正後）：**

```bash
podman run -p 8080:80 ubuntu:latest
podman run --net bridge ubuntu:latest
```

## Podman 固有の注意点

Podman のリモートAPIサーバーを使用している場合、HTTP リクエストの `Content-Type` ヘッダーが正しく設定されていないと 400 エラーが発生します。`application/json` を指定し、リクエストボディが有効な JSON 形式であることを確認してください。

Podman Socket API を直接操作する際、リクエストパスが `/v1.0.0/libpod/...` の形式で正しく構成されているか確認します。古いバージョンの API パスを使用すると 400 エラーが返されます。

また、SELinux が有効な環境では、socket ファイルのパーミッションが不正な場合もリクエスト解析失敗につながります。`ls -Z ~/.local/share/podman/podman/podman.sock` で確認し、必要に応じてラベルを修正してください。

## それでも解決しない場合

Podman デーモンの詳細ログを有効にしてエラーの詳細を確認します。

```bash
podman --log-level debug run <options>
```

ログファイルが記録されている場合は以下で確認します。

```bash
journalctl -u podman --no-pager | tail -50
```

公式ドキュメント「Podman Run Options」および「Podman API」ページで、各オプションの正確な形式と使用例を確認してください。

GitHub の Podman Issues ページ（https://github.com/containers/podman/issues）で、類似の問題が報告されていないか検索することも有効です。環境固有の問題（Podman バージョン、ホストOS、コンテナランタイム）を報告する際は、`podman --version` と `podman info` の出力を含めてください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*