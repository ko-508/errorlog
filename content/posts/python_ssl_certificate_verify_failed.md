---
title: "Python SSL証明書エラーの原因と対処法"
date: 2026-10-07T09:00:00+09:00
draft: false
description: "PythonのCERTIFICATE_VERIFY_FAILEDはHTTPS接続先の証明書を検証できない場合に出ます。末尾の理由を読み、macOSの証明書設定、社内CA、期限切れ、ホスト名の不一致を切り分ける手順を解説します。"
tags: ["Python"]
images: ["og/posts/python_ssl_certificate_verify_failed.png"]
errorCode: "CERTIFICATE_VERIFY_FAILED"
urgency: "medium"
service: "Python"
error_type: "SSLCertVerificationError"
components: ["Python", "ssl", "Requests", "OpenSSL"]
related_services: []
trend_incident: false
publish_slug: "python_ssl_certificate_verify_failed"
publish_note: "新規作成。Python・Requests公式文書、CPython実装、GitHubの実例を照合"
publish_zenn: true
---

## 冒頭まとめ

`SSL: CERTIFICATE_VERIFY_FAILED`は、HTTPS接続先の証明書を検証できなかったときに出ます。まず、`certificate verify failed:`の後ろにある理由を確認してください。発行者の証明書が見つからない場合、期限切れの場合、接続先の名前が違う場合では、直す場所が変わります。

macOSでpython.org版を入れた直後なら、`Install Certificates.command`の実行を確認します。社内ネットワークだけで失敗するなら、管理者が提供するCA証明書と、そのPythonが使う設定を確認してください。

`verify=False`で通っても証明書の問題は解消していません。相手の確認を省略しただけなので、検証を有効にしたまま接続できる状態へ直すのが基本です。

## エラー文の末尾で原因を切り分ける

Python標準の`ssl`では、次のような表示になります。行番号は説明用で、Pythonの版やビルドによって変わります。

```text
ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1007)
```

`SSLCertVerificationError`は`SSLError`の一種で、[Python公式文書](https://docs.python.org/3/library/ssl.html#ssl.SSLCertVerificationError)ではPython 3.7で追加された例外とされています。Requests経由では、`requests.exceptions.SSLError`の中に証明書検証の失敗が表示されることがあります。

[CPythonの実装](https://github.com/python/cpython/blob/3.13/Modules/_ssl.c)では、検証結果に応じて末尾の文言を作ります。ホスト名・IPアドレスの不一致にはPython側の説明を使い、それ以外はOpenSSLの検証理由を使います。

| 末尾にある理由 | 最初に確認すること |
|---|---|
| `unable to get local issuer certificate` | 信頼するCAの設定と、サーバーが送る中間証明書 |
| `self-signed certificate` | 自己署名証明書を意図して使っているか、信頼設定があるか |
| `self-signed certificate in certificate chain` | 証明書の連鎖と、信頼の起点となるCA |
| `certificate has expired` | 証明書の期限と、実行環境の時計 |
| `Hostname mismatch` / `IP address mismatch` | URLの名前・IPアドレスと証明書の対象名 |

発行者を見つけられない理由は、手元のCA不足に限りません。サーバーが必要な中間証明書を送っていない場合もあります。[OpenSSLの検証説明](https://docs.openssl.org/3.0/man1/openssl-verification-options/)に沿って、接続先から信頼するCAまで証明書をたどれるかを確認します。

## 実行中のPythonと証明書の設定を確認する

エラーが出たターミナル、仮想環境、CIジョブ、コンテナの中で確認します。以下の`python`は、失敗した処理で使うPythonのコマンド名に合わせてください。

```bash
python -c "import sys, ssl; print(sys.executable); print(ssl.OPENSSL_VERSION); print(ssl.get_default_verify_paths())"
```

`sys.executable`は実行中のPython、`get_default_verify_paths()`は既定のCAファイル・ディレクトリや、関連する環境変数名を調べるために使います。Requestsを使っている場合は、そのCAファイルも別に確認します。

```bash
python -c "import requests; print(requests.certs.where())"
```

[Requestsの公式文書](https://requests.readthedocs.io/en/latest/user/advanced/#ca-certificates)では、CA証明書に`certifi`を使うと説明されています。標準の`ssl`とRequestsが同じ信頼設定を使うとは限りません。

ブラウザで開けるかも比較材料になりますが、開けるだけで証明書全体が正常とは断定できません。利用する証明書や通信経路の違いも確認してください。

実例として、[CPythonのIssue #83107](https://github.com/python/cpython/issues/83107)には、macOSで証明書導入スクリプトを実行してもPythonの通信が失敗し、CAファイルの指定で接続できたという報告があります。ただし根本原因は確定していません。この報告を特定のパスへ変更すれば必ず直るという根拠にはせず、実際に参照しているCA設定を調べる材料として扱います。

## macOSのpython.org版では導入手順を確認する

[PythonのmacOS向け公式手順](https://docs.python.org/3/using/mac.html#installation-steps)は、インストール後に`Install Certificates.command`を実行して証明書を導入するよう案内しています。対象はpython.orgから入れたPythonです。Homebrewや別の配布元のPythonへ、そのまま同じ手順を当てはめないでください。

Finderでアプリケーション内のPythonフォルダを開き、`Install Certificates.command`を実行します。ターミナルから実行する場合の例は次のとおりです。

```bash
"/Applications/Python 3.13/Install Certificates.command"
```

`3.13`は実際に導入した版へ置き換えます。処理が成功したことを確認してから、元のプログラムを再実行してください。

この手順で直らなければ、使っているPythonの場所とエラー末尾を再確認します。別のPythonを起動している、社内CAが必要、接続先の証明書が不正などの原因は、この手順だけでは解消しません。`certifi`をインストールしただけで、すべてのPythonの信頼設定が自動的に切り替わるわけでもありません。

## 社内CAや開発用CAを検証に追加する

社内の通信検査や開発用サーバーが独自のCAを使う場合は、管理者から正規の手段でCA証明書を入手します。エラーが出た接続先から取得した証明書を、出所を確認せず信頼させないでください。

標準の`urllib.request`では、既定の証明書を読み込んだ後に、追加のCAを読み込めます。URLとファイルパスは例です。

```python
import ssl
import urllib.request

context = ssl.create_default_context()
context.load_verify_locations(cafile="/path/to/corporate-ca.pem")

with urllib.request.urlopen(
    "https://internal.example.com/",
    context=context,
    timeout=10,
) as response:
    print(response.status)
```

[SSLContextの公式説明](https://docs.python.org/3/library/ssl.html#ssl.SSLContext.load_verify_locations)にある`load_verify_locations()`で、信頼するCAを追加しています。ホスト名や有効期限の検査は無効にしていません。

Requestsでは、管理されたCAバンドルのパスを指定します。

```python
import requests

response = requests.get(
    "https://internal.example.com/",
    verify="/path/to/company-ca-bundle.pem",
    timeout=10,
)
response.raise_for_status()
print(response.status_code)
```

この`verify`指定は、その要求で使うCAバンドルを選ぶ指定です。通常の公開CAも必要なら、それを含めたバンドルを管理者に確認します。既定のバンドルへ自動的に追加されるものとして扱わないでください。

Requestsの通常の呼び出しには、環境変数`REQUESTS_CA_BUNDLE`で指定する方法もあります。次はLinux/macOSのシェルの例です。

```bash
export REQUESTS_CA_BUNDLE=/path/to/company-ca-bundle.pem
```

標準の`ssl`の既定パスに関係する`SSL_CERT_FILE`とは、対象が異なります。また、Requestsの`PreparedRequest`を独自に送る処理では、環境設定の取り込みが必要になる場合があります。[Requestsの公式説明](https://requests.readthedocs.io/en/latest/user/advanced/#prepared-requests)を確認してください。`certifi`のインストール先ファイルへ直接追記する方法は、ここでは使いません。

## 期限切れ・名前の不一致・コンテナを確認する

`certificate has expired`なら、接続先が送る証明書の期限と実行環境の時計を確認します。[OpenSSLの説明](https://docs.openssl.org/3.0/man1/openssl-verification-options/)では、連鎖内の証明書について有効期間を検査します。接続先の証明書が実際に期限切れなら、管理者による更新が必要です。CAファイルを指定するだけでは期限の問題は直りません。

名前の不一致なら、URLのホスト名が証明書の対象名に含まれるかを確認します。ドメイン用の証明書を持つサーバーへIPアドレスでアクセスしている場合などは、正しいURLか、適切な証明書へ直します。

コンテナでのみ失敗する場合は、コンテナ内でCA設定を確認してください。ホスト側の証明書設定だけを変えても、コンテナへ反映されるとは限りません。

ただし、`slim`という名前だけでCA証明書がないと決めつけないでください。[確認した公式PythonイメージのDockerfile](https://github.com/docker-library/python/blob/master/3.13/slim-bookworm/Dockerfile)は、実行時の依存として`ca-certificates`を導入しています。独自イメージや加工した最終イメージでは、その構成を調べます。

## 補足：検証の無効化と近いエラー

`verify=False`は、Requestsの証明書検証を省略する指定です。[Requests公式文書](https://requests.readthedocs.io/en/latest/user/advanced/#ssl-cert-verification)は、期限切れや名前の不一致も無視し、中間者攻撃の危険があると説明しています。第三者が通信へ割り込んでも相手を確かめられないため、公開サービスへ接続する通常の解決手順には使いません。

`InsecureRequestWarning`を消しても検証は復活しません。エラーや警告を非表示にする操作と、証明書を検証できるようにする操作を区別してください。

`SSLError`は証明書以外のTLSの失敗も含みます。TLSはHTTPSで通信を保護する仕組みです。`WRONG_VERSION_NUMBER`など別の理由が出ている場合は、CA証明書の追加だけで解決すると判断せず、接続先のプロトコルやプロキシ設定を確認します。

また、[npmのCERT_HAS_EXPIRED](/posts/npm_cert_has_expired/)はNode.js側の期限切れエラーを扱います。今回のPythonのエラーは、期限切れに加えて発行者の確認や名前の一致など、証明書検証の失敗全般が対象です。

## 解決手順のまとめ

最初にエラー末尾の理由を読み、発行者の確認、期限、名前のどこで失敗したかを切り分けます。次に、失敗した処理と同じ環境でPythonの実行場所とCA設定を確認します。

python.org版のmacOSなら証明書導入手順を確認し、社内CAが必要なら管理された証明書を検証へ追加します。サーバーの中間証明書不足、期限切れ、名前の不一致なら、接続先の設定やURLを直してください。

検証を有効にした状態で元の要求が成功することを確認して完了とします。本文のコードは設定方法の例であり、掲載した接続先への実通信結果を示すものではありません。

免責事項：本記事の内容は一般的なPythonのHTTPS接続を前提としています。証明書の参照先や検証の挙動は、Pythonの配布元、ライブラリ、OS、OpenSSLの版によって異なります。信頼するCAを変更する前に、組織の管理方針と接続先の構成を確認してください。
