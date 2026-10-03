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

`import`で次のエラーが出た場合、実行中のPythonが指定したモジュールを見つけられていません。

```text
ModuleNotFoundError: No module named 'requests'
```

インストールしたつもりでも、別のPythonや仮想環境で実行していることがあります。まず、エラーが出る環境で次を確認してください。

```bash
python -c "import sys; print(sys.executable)"
python -m pip --version
python -m pip show requests
```

`requests`は例です。実際に必要な配布パッケージの名前へ置き換えます。見つからなければ、実行するPythonを指定したうえで、そのPython経由でインストールしてください。

一方、末尾に`'http' is not a package`などが付いている場合は、手元のファイル名が本来のパッケージ名と衝突している可能性があります。再インストールより先に、何を読み込んでいるかを確認します。

## エラーメッセージの意味

モジュールは、`import`で読み込む単位です。パッケージは、内部に別のモジュールを持てる種類のモジュールです。

`ModuleNotFoundError`は`ImportError`の一種で、Python 3.6で追加されました。[Pythonの例外の公式文書](https://docs.python.org/3/library/exceptions.html#ModuleNotFoundError)は、モジュールが見つからない場合と、読み込み済みモジュールを記録する`sys.modules`に`None`が入っている場合に発生すると説明しています。

| 文言 | 意味 |
|---|---|
| `No module named 'foo'` | `foo`を見つけられない |
| `No module named 'foo.bar'` | `foo.bar`を見つけられない。親の探索にも注意が必要 |
| `No module named 'foo.bar'; 'foo' is not a package` | `foo`は読み込まれたが、子モジュールを持つパッケージとして扱えない |
| `import of foo halted; None in sys.modules` | `sys.modules['foo']`が`None`で、読み込みが拒まれている |

これらの分岐は、CPythonの[importlib実装](https://github.com/python/cpython/blob/3.13/Lib/importlib/_bootstrap.py)で確認できます。`None in sys.modules`という文言だけで、別スレッドの失敗が原因だとは判断できません。

最後に表示された名前も確認してください。`import requests`を実行していても、内部で必要な別モジュールを読み込めずに停止する場合があります。エラーの直前に並ぶファイル名と行番号を読むと、どの読み込みで止まったかが分かります。

## 最初に実行するPythonとインストール先を確認する

`sys.executable`は、実行中のPythonの場所を示します。`python -m pip --version`では、そのPythonで動くpipの場所を確認できます。

```bash
python -c "import sys; print(sys.executable); print(sys.prefix); print(sys.base_prefix)"
python -m pip --version
python -m pip show requests
```

`pip show`の`Location`はインストール先です。別のPythonにインストールしたパッケージは、現在のPythonから読み込めるとは限りません。同じバージョンのPythonでも、仮想環境が異なれば確認が必要です。

この記事の確認では、独立した二つの仮想環境を作り、片方だけに説明用のモジュールを置きました。置いた環境では読み込めましたが、もう片方では`ModuleNotFoundError`になりました。確認に使ったPythonはCPython 3.12.14です。

エディター、ノートブック、CIでエラーが出る場合は、その実行環境の中で`sys.executable`を確認してください。ターミナルで成功することだけでは、別の実行環境でも読み込めるとは判断できません。

## 同じPythonにインストールし、仮想環境を揃える

[pipの公式文書](https://pip.pypa.io/en/stable/user_guide/#running-pip)は、`python -m pip`が指定したPythonでpipを実行すると説明しています。単独の`pip`コマンドではなく、アプリケーションを動かすPythonを通して実行します。

```bash
python -m pip install requests
python -c "import requests; print(requests.__file__)"
```

プロジェクトに`requirements.txt`がある場合は、その依存関係を使います。

```bash
python -m pip install -r requirements.txt
```

仮想環境は、プロジェクトごとにPythonの実行先やパッケージを分ける仕組みです。既存の`.venv`を使う場合の有効化は、シェルによって異なります。

| 環境 | 有効化するコマンド |
|---|---|
| Linux/macOSのbash・zsh | `source .venv/bin/activate` |
| Windowsのコマンドプロンプト | `.venv\Scripts\activate.bat` |
| WindowsのPowerShell | `.\.venv\Scripts\Activate.ps1` |

有効化後も、`sys.executable`で実行先を確認してください。[venvの公式文書](https://docs.python.org/3/library/venv.html#how-venvs-work)によると、`sys.prefix != sys.base_prefix`で、実行中のPythonがvenvの仮想環境を使っているかを確認できます。

有効化せず、仮想環境のPythonを直接指定する方法もあります。Windowsのコマンドプロンプトなら、次のようにインストールと実行の両方を揃えられます。

```bat
.venv\Scripts\python.exe -m pip install requests
.venv\Scripts\python.exe app.py
```

DockerやCIでも、パッケージを入れた環境とアプリケーションの実行環境を揃えます。ビルド時のログにインストール成功と出ていても、実際に動く環境で同じ確認をしてください。

## is not a packageならファイル名の衝突を調べる

次のエラーでは、`http`自体は見つかっています。ただし、`http.client`を読み込めるパッケージとして扱えません。

```text
ModuleNotFoundError: No module named 'http.client'; 'http' is not a package
```

手元に`http.py`を作り、そのディレクトリで`import http.client`を実行すると、この文言を再現できました。Pythonは標準ライブラリの`http`パッケージではなく、手元の`http.py`を読み込みます。

[探索先の公式文書](https://docs.python.org/3/library/sys_path_init.html)は、通常のスクリプト実行ではスクリプトのあるディレクトリが探索先の先頭になり、`-c`や`-m`では現在のディレクトリが先頭になると説明しています。

エラーが出る実行環境で、親モジュールの場所を確認します。

```bash
python -c "import http; print(http.__file__)"
```

自分で作った`http.py`を指していれば、`http_example.py`など衝突しない名前に変更してください。実行中のプロセスが元のモジュールを保持している場合は、Pythonやノートブックの実行環境を再起動して確認します。

[RequestsのIssue #7006](https://github.com/psf/requests/issues/7006)にも、Requestsが内部でurllib3を読み込み、その先の`http.client`で停止した報告があります。回答では、手元の`http.py`の存在が原因候補として挙げられています。報告者による解決確認は掲載されていないため、この事例の原因を確定したものとしては扱いません。

`requests.py`、`json.py`なども、読み込みたい名前と衝突しないようにしてください。ただし、名前衝突が必ず`ModuleNotFoundError`になるわけではなく、参照の書き方によって別のエラーになります。

## インストール名とimport名、自作パッケージの参照を確認する

pipに指定する名前と、Pythonで読み込む名前は一致するとは限りません。たとえばPillowは、`Pillow`をインストールして`PIL`を読み込みます。

```bash
python -m pip install Pillow
python -c "from PIL import Image; print(Image.__file__)"
```

この違いは[PyPAの公式ガイド](https://packaging.python.org/en/latest/discussions/distribution-package-vs-import-package/)にも明記されています。エラーの名前をそのままpipに渡すのではなく、利用するライブラリの公式文書やプロジェクトの依存関係で、必要な配布名を確認してください。

自作パッケージ内の参照も確認します。`mypkg`ディレクトリに`__init__.py`、`app.py`、`utils.py`がある構成で、`app.py`から同じパッケージ内の`utils.py`を読むなら、次のように書けます。

```python
# mypkg/app.py
from . import utils
```

`import utils`は、同じパッケージの子としてではなく、トップレベルの`utils`を探します。[importの公式文書](https://docs.python.org/3/reference/import.html#package-relative-imports)は、先頭のドットを使う相対インポートを説明しています。

相対インポートを使う場合は、`mypkg`の親ディレクトリからモジュールとして実行します。

```bash
python -m mypkg.app
```

`python mypkg/app.py`という直接実行では、パッケージの情報がないため、`attempted relative import with no known parent package`という別のエラーになる場合があります。ファイルの配置と起動方法を揃えてください。

## 近いエラーとの違い

`demo.py`というファイルに、存在しない名前を指定した場合の違いをCPython 3.12.14で確認しました。

| 操作・文言 | 確認する内容 |
|---|---|
| `import demo.child`で`'demo' is not a package` | 親がパッケージか、同名のファイルを読み込んでいないか |
| `from demo import missing`で`ImportError: cannot import name` | 読み込んだモジュールからその名前を取得できるか |
| `import demo`後の`demo.missing`で`AttributeError` | 読み込み済みモジュールにその属性があるか |
| `import of demo halted; None in sys.modules` | `sys.modules`への代入や、読み込みを制御する処理 |

`from requests import get`は、単純に`requests.get`という子モジュールを探す操作ではありません。モジュールが公開する関数などの名前も取得します。そのため、`from ... import ...`の失敗をすべて`is not a package`として扱うことはできません。

また、読み込んだファイル内に構文の誤りがあれば`SyntaxError`になります。循環した読み込みや依存先の問題もあるため、最後の一行だけでなく、そこへ至る実行履歴も確認してください。

## 解決手順のまとめ

最初に、エラーに出た名前と`sys.executable`を確認します。外部パッケージが必要なら、そのPythonで`pip show`を実行し、未導入なら正しい配布名でインストールしてください。

インストール済みなら、仮想環境やエディターの実行先を確認します。`is not a package`が付く場合は親の`__file__`を調べ、自作パッケージなら参照の書き方と`python -m`による起動を見直します。

探索先を確認する必要がある場合は、次で一覧を表示できます。

```bash
python -c "import sys; print('\n'.join(sys.path))"
```

外部パッケージにはインストール、自作コードには配置と参照方法の確認が必要です。すべてを再インストールで直そうとせず、実行するPythonと実際の読み込み先を揃えてください。

免責事項：本記事の内容は一般的な情報提供を目的としています。設定変更は、利用しているPythonのバージョンとプロジェクトの実行環境を確認したうえで行ってください。
