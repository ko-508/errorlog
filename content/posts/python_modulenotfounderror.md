---
title: "Pythonのモジュール不在エラーの対処法"
date: 2026-10-04
draft: false
description: "PythonのModuleNotFoundError: No module namedが出たときは、実行するPython、インストール先、読み込む名前を確認します。仮想環境の違い、ファイル名の衝突、パッケージ名とimport名の違い、相対インポートの直し方を解説します。"
tags: ["Python"]
images: ["og/posts/python_modulenotfounderror.png"]
errorCode: "ModuleNotFoundError: No module named"
urgency: "medium"
service: "Python"
error_type: "module_not_found"
components: ["Python", "pip", "import"]
related_services: []
trend_incident: false
publish_slug: "python_modulenotfounderror"
publish_note: "新規作成。importの診断と探索、pipの実行先、venv、配布名とimport名の違いをPython・pip・PyPA公式文書およびCPython実装で照合。CPython 3.12.14で不在、環境差、名前衝突、相対import、近い診断を再現。requests#7006の報告と回答を確認"
publish_zenn: true
---

## 冒頭まとめ

`import`で次の[エラー](/glossary/エラー/)が出た場合、実行中のPythonが指定した[モジュール](/glossary/モジュール/)を見つけられていません。

```text
ModuleNotFoundError: No module named 'requests'
```

[インストール](/glossary/インストール/)したつもりでも、別のPythonや仮想環境で実行していることがあります。まず、[エラー](/glossary/エラー/)が出る[環境](/glossary/環境/)で次を確認してください。

```bash
python -c "import sys; print(sys.executable)"
python -m pip --version
python -m pip show requests
```

`requests`は例です。実際に必要な配布[パッケージ](/glossary/パッケージ/)の名前へ置き換えます。見つからなければ、実行するPythonを指定したうえで、そのPython経由で[インストール](/glossary/インストール/)してください。

一方、末尾に`'http' is not a package`などが付いている場合は、手元の[ファイル名](/glossary/ファイル名/)が本来の[パッケージ](/glossary/パッケージ/)名と衝突している可能性があります。再[インストール](/glossary/インストール/)より先に、何を読み込んでいるかを確認します。

## エラーメッセージの意味

[モジュール](/glossary/モジュール/)は、`import`で読み込む単位です。[パッケージ](/glossary/パッケージ/)は、内部に別の[モジュール](/glossary/モジュール/)を持てる種類の[モジュール](/glossary/モジュール/)です。

`ModuleNotFoundError`は`ImportError`の一種で、Python 3.6で追加されました。[Pythonの例外の公式文書](https://docs.python.org/3/library/exceptions.html#ModuleNotFoundError)は、[モジュール](/glossary/モジュール/)が見つからない場合と、読み込み済み[モジュール](/glossary/モジュール/)を記録する`sys.modules`に`None`が入っている場合に発生すると説明しています。

| 文言 | 意味 |
|---|---|
| `No module named 'foo'` | `foo`を見つけられない |
| `No module named 'foo.bar'` | `foo.bar`を見つけられない。親の探索にも注意が必要 |
| `No module named 'foo.bar'; 'foo' is not a package` | `foo`は読み込まれたが、子[モジュール](/glossary/モジュール/)を持つ[パッケージ](/glossary/パッケージ/)として扱えない |
| `import of foo halted; None in sys.modules` | `sys.modules['foo']`が`None`で、読み込みが拒まれている |

これらの分岐は、CPythonの[importlib実装](https://github.com/python/cpython/blob/3.13/Lib/importlib/_bootstrap.py)で確認できます。`None in sys.modules`という文言だけで、別スレッドの失敗が原因だとは判断できません。

最後に表示された名前も確認してください。`import requests`を実行していても、内部で必要な別[モジュール](/glossary/モジュール/)を読み込めずに停止する場合があります。[エラー](/glossary/エラー/)の直前に並ぶ[ファイル名](/glossary/ファイル名/)と[行番号](/glossary/行番号/)を読むと、どの読み込みで止まったかが分かります。

## 最初に実行するPythonとインストール先を確認する

`sys.executable`は、実行中のPythonの場所を示します。`python -m pip --version`では、そのPythonで動くpipの場所を確認できます。

```bash
python -c "import sys; print(sys.executable); print(sys.prefix); print(sys.base_prefix)"
python -m pip --version
python -m pip show requests
```

`pip show`の`Location`は[インストール](/glossary/インストール/)先です。別のPythonに[インストール](/glossary/インストール/)した[パッケージ](/glossary/パッケージ/)は、現在のPythonから読み込めるとは限りません。同じ[バージョン](/glossary/バージョン/)のPythonでも、仮想環境が異なれば確認が必要です。

この記事の確認では、独立した二つの仮想環境を作り、片方だけに説明用の[モジュール](/glossary/モジュール/)を置きました。置いた[環境](/glossary/環境/)では読み込めましたが、もう片方では`ModuleNotFoundError`になりました。確認に使ったPythonはCPython 3.12.14です。

エディター、ノートブック、CIで[エラー](/glossary/エラー/)が出る場合は、その実行環境の中で`sys.executable`を確認してください。[ターミナル](/glossary/ターミナル/)で成功することだけでは、別の実行環境でも読み込めるとは判断できません。

## 同じPythonにインストールし、仮想環境を揃える

[pipの公式文書](https://pip.pypa.io/en/stable/user_guide/#running-pip)は、`python -m pip`が指定したPythonでpipを実行すると説明しています。単独の`pip`[コマンド](/glossary/コマンド/)ではなく、[アプリケーション](/glossary/アプリケーション/)を動かすPythonを通して実行します。

```bash
python -m pip install requests
python -c "import requests; print(requests.__file__)"
```

[プロジェクト](/glossary/プロジェクト/)に`requirements.txt`がある場合は、その依存関係を使います。

```bash
python -m pip install -r requirements.txt
```

仮想環境は、[プロジェクト](/glossary/プロジェクト/)ごとにPythonの実行先や[パッケージ](/glossary/パッケージ/)を分ける仕組みです。既存の`.venv`を使う場合の有効化は、[シェル](/glossary/シェル/)によって異なります。

| [環境](/glossary/環境/) | 有効化する[コマンド](/glossary/コマンド/) |
|---|---|
| [Linux](/glossary/linux/)/macOSの[bash](/glossary/bash/)・zsh | `source .venv/bin/activate` |
| Windowsの[コマンドプロンプト](/glossary/コマンドプロンプト/) | `.venv\Scripts\activate.bat` |
| WindowsのPowerShell | `.\.venv\Scripts\Activate.ps1` |

有効化後も、`sys.executable`で実行先を確認してください。[venvの公式文書](https://docs.python.org/3/library/venv.html#how-venvs-work)によると、`sys.prefix != sys.base_prefix`で、実行中のPythonがvenvの仮想環境を使っているかを確認できます。

有効化せず、仮想環境のPythonを直接指定する方法もあります。Windowsの[コマンドプロンプト](/glossary/コマンドプロンプト/)なら、次のように[インストール](/glossary/インストール/)と実行の両方を揃えられます。

```bat
.venv\Scripts\python.exe -m pip install requests
.venv\Scripts\python.exe app.py
```

[Docker](/glossary/docker/)やCIでも、[パッケージ](/glossary/パッケージ/)を入れた[環境](/glossary/環境/)と[アプリケーション](/glossary/アプリケーション/)の実行環境を揃えます。ビルド時の[ログ](/glossary/ログ/)に[インストール](/glossary/インストール/)成功と出ていても、実際に動く[環境](/glossary/環境/)で同じ確認をしてください。

## is not a packageならファイル名の衝突を調べる

次の[エラー](/glossary/エラー/)では、`http`自体は見つかっています。ただし、`http.client`を読み込める[パッケージ](/glossary/パッケージ/)として扱えません。

```text
ModuleNotFoundError: No module named 'http.client'; 'http' is not a package
```

手元に`http.py`を作り、その[ディレクトリ](/glossary/ディレクトリ/)で`import http.client`を実行すると、この文言を再現できました。Pythonは[標準](/glossary/標準/)[ライブラリ](/glossary/ライブラリ/)の`http`[パッケージ](/glossary/パッケージ/)ではなく、手元の`http.py`を読み込みます。

[探索先の公式文書](https://docs.python.org/3/library/sys_path_init.html)は、通常の[スクリプト](/glossary/スクリプト/)実行では[スクリプト](/glossary/スクリプト/)のある[ディレクトリ](/glossary/ディレクトリ/)が探索先の先頭になり、`-c`や`-m`では現在の[ディレクトリ](/glossary/ディレクトリ/)が先頭になると説明しています。

[エラー](/glossary/エラー/)が出る実行環境で、親[モジュール](/glossary/モジュール/)の場所を確認します。

```bash
python -c "import http; print(http.__file__)"
```

自分で作った`http.py`を指していれば、`http_example.py`など衝突しない名前に変更してください。実行中の[プロセス](/glossary/プロセス/)が元の[モジュール](/glossary/モジュール/)を保持している場合は、Pythonやノートブックの実行環境を再起動して確認します。

[RequestsのIssue #7006](https://github.com/psf/requests/issues/7006)にも、Requestsが内部でurllib3を読み込み、その先の`http.client`で停止した報告があります。回答では、手元の`http.py`の存在が原因候補として挙げられています。報告者による解決確認は掲載されていないため、この事例の原因を確定したものとしては扱いません。

`requests.py`、`json.py`なども、読み込みたい名前と衝突しないようにしてください。ただし、名前衝突が必ず`ModuleNotFoundError`になるわけではなく、参照の書き方によって別の[エラー](/glossary/エラー/)になります。

## インストール名とimport名、自作パッケージの参照を確認する

pipに指定する名前と、Pythonで読み込む名前は一致するとは限りません。たとえばPillowは、`Pillow`を[インストール](/glossary/インストール/)して`PIL`を読み込みます。

```bash
python -m pip install Pillow
python -c "from PIL import Image; print(Image.__file__)"
```

この違いは[PyPAの公式ガイド](https://packaging.python.org/en/latest/discussions/distribution-package-vs-import-package/)にも明記されています。[エラー](/glossary/エラー/)の名前をそのままpipに渡すのではなく、利用する[ライブラリ](/glossary/ライブラリ/)の公式文書や[プロジェクト](/glossary/プロジェクト/)の依存関係で、必要な配布名を確認してください。

自作[パッケージ](/glossary/パッケージ/)内の参照も確認します。`mypkg`[ディレクトリ](/glossary/ディレクトリ/)に`__init__.py`、`app.py`、`utils.py`がある構成で、`app.py`から同じ[パッケージ](/glossary/パッケージ/)内の`utils.py`を読むなら、次のように書けます。

```python
# mypkg/app.py
from . import utils
```

`import utils`は、同じ[パッケージ](/glossary/パッケージ/)の子としてではなく、トップレベルの`utils`を探します。[importの公式文書](https://docs.python.org/3/reference/import.html#package-relative-imports)は、先頭のドットを使う相対インポートを説明しています。

相対インポートを使う場合は、`mypkg`の親[ディレクトリ](/glossary/ディレクトリ/)から[モジュール](/glossary/モジュール/)として実行します。

```bash
python -m mypkg.app
```

`python mypkg/app.py`という直接実行では、[パッケージ](/glossary/パッケージ/)の情報がないため、`attempted relative import with no known parent package`という別の[エラー](/glossary/エラー/)になる場合があります。[ファイル](/glossary/ファイル/)の配置と起動方法を揃えてください。

## 近いエラーとの違い

`demo.py`という[ファイル](/glossary/ファイル/)に、存在しない名前を指定した場合の違いをCPython 3.12.14で確認しました。

| 操作・文言 | 確認する内容 |
|---|---|
| `import demo.child`で`'demo' is not a package` | 親が[パッケージ](/glossary/パッケージ/)か、同名の[ファイル](/glossary/ファイル/)を読み込んでいないか |
| `from demo import missing`で`ImportError: cannot import name` | 読み込んだ[モジュール](/glossary/モジュール/)からその名前を取得できるか |
| `import demo`後の`demo.missing`で`AttributeError` | 読み込み済み[モジュール](/glossary/モジュール/)にその[属性](/glossary/属性/)があるか |
| `import of demo halted; None in sys.modules` | `sys.modules`への代入や、読み込みを制御する処理 |

`from requests import get`は、単純に`requests.get`という子[モジュール](/glossary/モジュール/)を探す操作ではありません。[モジュール](/glossary/モジュール/)が公開する[関数](/glossary/関数/)などの名前も取得します。そのため、`from ... import ...`の失敗をすべて`is not a package`として扱うことはできません。

また、読み込んだ[ファイル](/glossary/ファイル/)内に構文の誤りがあれば`SyntaxError`になります。循環した読み込みや依存先の問題もあるため、最後の一行だけでなく、そこへ至る実行履歴も確認してください。

## 解決手順のまとめ

最初に、[エラー](/glossary/エラー/)に出た名前と`sys.executable`を確認します。外部[パッケージ](/glossary/パッケージ/)が必要なら、そのPythonで`pip show`を実行し、未導入なら正しい配布名で[インストール](/glossary/インストール/)してください。

[インストール](/glossary/インストール/)済みなら、仮想環境やエディターの実行先を確認します。`is not a package`が付く場合は親の`__file__`を調べ、自作[パッケージ](/glossary/パッケージ/)なら参照の書き方と`python -m`による起動を見直します。

探索先を確認する必要がある場合は、次で一覧を表示できます。

```bash
python -c "import sys; print('\n'.join(sys.path))"
```

外部[パッケージ](/glossary/パッケージ/)には[インストール](/glossary/インストール/)、自作[コード](/glossary/コード/)には配置と参照方法の確認が必要です。すべてを再[インストール](/glossary/インストール/)で直そうとせず、実行するPythonと実際の読み込み先を揃えてください。

免責事項：本記事の内容は一般的な情報提供を目的としています。[設定変更](/glossary/設定変更/)は、利用しているPythonの[バージョン](/glossary/バージョン/)と[プロジェクト](/glossary/プロジェクト/)の実行環境を確認したうえで行ってください。
