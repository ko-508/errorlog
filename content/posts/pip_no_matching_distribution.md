---
title: "pipの候補不在エラーの対処法"
date: 2026-10-05T09:00:00+09:00
draft: false
description: "pipのCould not find a version that satisfies the requirementとNo matching distribution foundの原因を解説。from versions: noneでもパッケージが存在しないとは限りません。配布名、Pythonの版、取得先、wheelの対応条件を順に確認します。"
tags: ["Python"]
images: ["og/posts/pip_no_matching_distribution.png"]
errorCode: "Could not find a version that satisfies the requirement"
urgency: "medium"
service: "Python"
error_type: "distribution_not_found"
components: ["Python", "pip", "PyPI"]
related_services: []
trend_incident: false
---

## 冒頭まとめ

`pip install`で次の[エラー](/glossary/エラー/)が出た場合、pipは指定された[要件](/glossary/要件/)を満たす配布[ファイル](/glossary/ファイル/)を選べていません。

```text
ERROR: Could not find a version that satisfies the requirement demo_probe==99.0 (from versions: 1.0)
ERROR: No matching distribution found for demo_probe==99.0
```

`from versions: none`でも、[パッケージ](/glossary/パッケージ/)が公開されていないとは限りません。Pythonの版や[OS](/glossary/os/)に合わない[ファイル](/glossary/ファイル/)が候補から外れた場合、取得先に接続できなかった場合にも、候補が残らないことがあります。

まず、[エラー](/glossary/エラー/)が出た[環境](/glossary/環境/)で、使っているPythonとpipを確認してください。

```bash
python -c "import sys; print(sys.executable); print(sys.version)"
python -m pip --version
```

そのうえで、最後の2行より前に出ている接続[エラー](/glossary/エラー/)や候補の除外理由を読みます。名前、版の指定、Pythonへの[対応](/glossary/対応/)、取得先、[OS](/glossary/os/)向けの形式を順に確認すると、直す場所を絞れます。

## エラーの意味とfrom versionsの読み方

pipは、取得先から見つけた[ファイル](/glossary/ファイル/)をすべて[インストール](/glossary/インストール/)候補にするわけではありません。[候補選択の公式文書](https://pip.pypa.io/en/stable/development/architecture/package-finding/)では、リンクから候補を作る段階で、[ファイル形式](/glossary/ファイル形式/)やPythonへの[対応](/glossary/対応/)などを評価すると説明しています。

[pip 26.2.1の実装](https://github.com/pypa/pip/blob/26.2.1/src/pip/_internal/index/package_finder.py)でも、wheelの対応条件や`Requires-Python`に合わないリンクを除外しています。wheelは、[インストール](/glossary/インストール/)用に用意された`.whl`形式の配布[ファイル](/glossary/ファイル/)です。

そのため、`from versions`はPyPIに公開された全[バージョン](/glossary/バージョン/)の一覧ではありません。

| 表示 | 分かること | それだけでは分からないこと |
|---|---|---|
| `from versions: none` | 表示対象の候補が残っていない | [パッケージ](/glossary/パッケージ/)自体が存在しないのか、[環境](/glossary/環境/)や取得先の問題なのか |
| `from versions: 1.0, 2.0` | その版の候補は見つかっている | 指定した版や依存関係を満たして[インストール](/glossary/インストール/)できるか |

[pip 26.2.1の診断処理](https://github.com/pypa/pip/blob/26.2.1/src/pip/_internal/resolution/resolvelib/factory.py)は、候補の版を集めて一覧を作り、一覧が空なら`none`を表示します。Python[要件](/glossary/要件/)で除外した版があれば、その案内を先に出す[処理](/glossary/処理/)もあります。Python[要件](/glossary/要件/)の不一致が別の診断として出る場合もあり、[エラー](/glossary/エラー/)が常にこの2行になるわけではありません。

冒頭の出力は、CPython 3.12.14とpip 26.2.1で、ローカルに作成した検証用wheelを使って再現したものです。`demo_probe`は説明用の名前で、PyPIから取得した[パッケージ](/glossary/パッケージ/)ではありません。1.0だけがある場所で99.0を要求すると、候補一覧には1.0が出ても[インストール](/glossary/インストール/)には進めませんでした。

## パッケージ名とバージョン指定を確認する

[エラー](/glossary/エラー/)に出た名前を、利用する[ライブラリ](/glossary/ライブラリ/)の公式[インストール](/glossary/インストール/)手順と照合します。Pythonの`import`に書く名前と、pipに渡す配布名は一致するとは限りません。[PyPAの公式ガイド](https://packaging.python.org/en/latest/discussions/distribution-package-vs-import-package/)には、Pillowを[インストール](/glossary/インストール/)して`PIL`を読み込む例が示されています。

[標準](/glossary/標準/)[ライブラリ](/glossary/ライブラリ/)を、外部[パッケージ](/glossary/パッケージ/)として[インストール](/glossary/インストール/)しようとしていないかも確認してください。知らない名前を別の[パッケージ](/glossary/パッケージ/)に置き換える前に、[プロジェクト](/glossary/プロジェクト/)が何を要求しているかを確かめます。

利用中の取得先で見つかる版は、次で確認できます。`requests`は調べたい配布名に置き換えてください。

```bash
python -m pip index versions requests
```

[このコマンドの公式文書](https://pip.pypa.io/en/stable/cli/pip_index/)は、Pythonやプラットフォームの条件を指定できることも説明しています。表示結果は実行環境やオプションに左右されるため、PyPIにある全配布[ファイル](/glossary/ファイル/)の一覧とは区別してください。

版を`==`で固定している場合は、その版が存在し、対象環境で使えるかを確認します。`requirements.txt`や制約[ファイル](/glossary/ファイル/)を使っているなら、[コマンド](/glossary/コマンド/)だけでなく[ファイル](/glossary/ファイル/)内の指定も見直してください。

指定が誤っていた場合は、[プロジェクト](/glossary/プロジェクト/)が[対応](/glossary/対応/)する版へ[修正](/glossary/修正/)します。版の指定を外すと選ばれる版が変わるため、動作確認なしに固定を外す対処は避けます。

## Pythonの版とRequires-Pythonを確認する

[パッケージ](/glossary/パッケージ/)には、使えるPythonの範囲を示す`Requires-Python`が[設定](/glossary/設定/)されていることがあります。実行中のPythonが範囲外なら、その版は利用できません。

先ほどの`sys.version`で実行環境を確認し、PyPIの対象版のページや[ライブラリ](/glossary/ライブラリ/)の公式文書にある対応条件と照合してください。`pip index versions`は版の一覧を見るための[コマンド](/glossary/コマンド/)で、各版のPython[要件](/glossary/要件/)を一覧表示するものではありません。

[ログ](/glossary/ログ/)には、Pythonの条件で無視された版の案内が出る場合があります。また、候補の情報を読み込んだあとで、[パッケージ](/glossary/パッケージ/)が別のPythonを要求しているという診断が出る場合もあります。

ローカル検証では、`Requires-Python: >=4`を持つ検証用wheelをPython 3.12.14で指定すると、`requires a different Python`を含む診断になりました。候補が残らない場合と、候補のPython[要件](/glossary/要件/)が満たせない場合で、表示される経路が異なります。

Pythonを変更する場合は、[アプリケーション](/glossary/アプリケーション/)側も[対応](/glossary/対応/)している版を選び、そのPythonの[環境](/glossary/環境/)で[インストール](/glossary/インストール/)し直します。既存のPythonを維持する場合は、[ライブラリ](/glossary/ライブラリ/)の対応表を確認して[互換性](/glossary/互換性/)のある版を指定してください。特定の版番号を推測して選ばず、対応条件を根拠に決めます。

## 取得先と接続エラーを確認する

PyPIではなく、社内の取得先やローカルの[ファイル](/glossary/ファイル/)だけを見ている場合があります。次で[設定](/glossary/設定/)の読み込み元と値を確認できます。

```bash
python -m pip config debug
```

[pip configの公式文書](https://pip.pypa.io/en/stable/cli/pip_config/)は、`debug`で[設定ファイル](/glossary/設定ファイル/)と値を表示できると説明しています。[設定の優先順位](https://pip.pypa.io/en/stable/topics/configuration/)では、[コマンド](/glossary/コマンド/)のオプション、[環境変数](/glossary/環境変数/)、[設定ファイル](/glossary/設定ファイル/)の順に優先されます。

`index-url`、`extra-index-url`、`no-index`、`find-links`に加え、実行した[コマンド](/glossary/コマンド/)や`requirements.txt`内の取得先指定も確認してください。社内[パッケージ](/glossary/パッケージ/)は、正しい取得先と[認証](/glossary/認証/)が必要です。公開PyPIへ切り替えれば直るとは限りません。

[ログ](/glossary/ログ/)の前半に名前解決、接続の再試行、証明書検証の失敗があれば、先にその接続問題を直します。取得先から候補を受け取れていない状態で、[パッケージ](/glossary/パッケージ/)名や版を変えても原因が残るためです。

必要なら、詳細[ログ](/glossary/ログ/)で候補を除外した理由を確認します。

```bash
python -m pip install -vvv requests
```

これは調査だけの[コマンド](/glossary/コマンド/)ではなく、条件が満たされれば実際に[インストール](/glossary/インストール/)します。変更してよい仮想環境で実行し、`requests`を対象の配布名や実際の[要件](/glossary/要件/)に置き換えてください。[設定](/glossary/設定/)や[ログ](/glossary/ログ/)を共有するときは、認証情報を含む[URL](/glossary/url/)や社内の情報を伏せます。

## OSとCPUに対応するwheelを確認する

wheelには、Pythonの実装や版、[OS](/glossary/os/)などの対応条件が付いています。手元の[環境](/glossary/環境/)がその条件に合わなければ、[ファイル](/glossary/ファイル/)は候補から外れます。

ローカル検証では、Windows向けのwheelだけを置いた場所を[Linux](/glossary/linux/)から参照すると、[ファイル](/glossary/ファイル/)が存在していても`from versions: none`になりました。これは、`none`を[パッケージ](/glossary/パッケージ/)不在と断定できない例です。

実行環境が受け付ける条件は、次で確認できます。

```bash
python -m pip debug --verbose
```

[pip debugの公式文書](https://pip.pypa.io/en/stable/cli/pip_debug/)と、対象[パッケージ](/glossary/パッケージ/)の配布[ファイル](/glossary/ファイル/)一覧を照合してください。[Docker](/glossary/docker/)ではホストの[OS](/glossary/os/)ではなく、[コンテナ](/glossary/コンテナ/)内のPythonと[環境](/glossary/環境/)を確認します。

[pipのIssue #10501](https://github.com/pypa/pip/issues/10501)には、Jetson Xavier NXでTensorFlowの[インストール](/glossary/インストール/)が止まり、[CPU](/glossary/cpu/)、[OS](/glossary/os/)、Pythonなどの何が合わないのかを表示してほしいという報告があります。この報告だけでは原因を確定できませんが、診断の最後の一行では不一致の種類が分からない実例です。

ソース配布があれば、[対応](/glossary/対応/)するwheelがなくてもビルドできる場合があります。ただし、ソース配布の有無、必要なコンパイラや外部[ライブラリ](/glossary/ライブラリ/)、対象環境への[対応](/glossary/対応/)を確認する必要があります。

[インストールの公式文書](https://pip.pypa.io/en/stable/cli/pip_install/)にある`--only-binary`はソース配布を使わない指定です。これを付けた場合だけ失敗するなら、wheelの有無が手がかりになります。反対に、ソースからのビルドが始まったあとの失敗は、ビルドログの別の[エラー](/glossary/エラー/)として調べてください。

## 近いエラーとの違い

| 文言・状況 | 確認する内容 |
|---|---|
| `No matching distribution found` | 取得先と実行環境で、[要件](/glossary/要件/)を満たす候補を選べるか |
| `ResolutionImpossible`と依存関係の競合説明 | 複数の要求を同時に満たせるか |
| `requires a different Python` | 対象[パッケージ](/glossary/パッケージ/)のPython[要件](/glossary/要件/) |
| `Failed building wheel` | 候補を取得したあとのビルド[処理](/glossary/処理/) |
| `ModuleNotFoundError` | 実行中のPythonが[モジュール](/glossary/モジュール/)を読み込めるか |

依存関係が競合している場合は、[pipの依存関係解決の公式文書](https://pip.pypa.io/en/stable/topics/dependency-resolution/)にあるように、競合の説明から各[パッケージ](/glossary/パッケージ/)の要求を確認します。

たとえば、一方が`requests==2.25.0`、もう一方が`requests>=2.28.0`を必須とするなら、両方を満たす版はありません。requestsの指定だけを広げても解決せず、要求元の[パッケージ](/glossary/パッケージ/)の組み合わせや版を変更する必要があります。

一方、[インストール](/glossary/インストール/)後の読み込みで止まる場合は、[PythonのModuleNotFoundErrorの記事](/posts/python_modulenotfounderror/)で、実行するPythonと[インストール](/glossary/インストール/)先の違いを確認してください。

## 解決手順のまとめ

最初に、使っているPythonとpipを確認し、[ログ](/glossary/ログ/)の前半に接続[エラー](/glossary/エラー/)や候補の除外理由がないかを読みます。`from versions: none`だけで名前の誤りと決めつけないでください。

接続に問題がなければ、配布名、固定した版、Pythonの対応範囲、取得先の指定を確認します。[OS](/glossary/os/)向けのwheelが候補から外れている場合は、その[環境](/glossary/環境/)を正式にサポートする配布方法を選びます。

最後に、[修正](/glossary/修正/)した[要件](/glossary/要件/)で[インストール](/glossary/インストール/)し、[アプリケーション](/glossary/アプリケーション/)の動作を確認してください。候補選び、ビルド、実行時の読み込みは別の段階なので、実際に止まった段階の[ログ](/glossary/ログ/)に沿って対処します。

免責事項：本記事の内容は一般的な情報提供を目的としています。[インストール](/glossary/インストール/)や[設定変更](/glossary/設定変更/)は、利用するPythonの[バージョン](/glossary/バージョン/)と[プロジェクト](/glossary/プロジェクト/)の依存関係を確認したうえで行ってください。