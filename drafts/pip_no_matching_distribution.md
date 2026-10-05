---
title: "pipの候補不在エラーの対処法"
date: 2026-10-05T09:00:00+09:00
draft: false
description: "pipのCould not find a version that satisfies the requirementとNo matching distribution foundの原因を解説。from versions: noneでもパッケージが存在しないとは限りません。配布名、Pythonの版、取得先、wheelの対応条件を順に確認します。"
tags: ["Python"]
errorCode: "Could not find a version that satisfies the requirement"
urgency: "medium"
service: "Python"
error_type: "distribution_not_found"
components: ["Python", "pip", "PyPI"]
related_services: []
trend_incident: false
publish_slug: "pip_no_matching_distribution"
publish_note: "新規作成。候補の絞り込みと診断をpip 26.2.1の実装・pipおよびPyPA公式文書で照合。ローカルwheelを用い、版不一致、OS不一致でのversions:none、Python要件不一致を再現。pypa/pip#10501を確認"
publish_zenn: true
---

## 冒頭まとめ

`pip install`で次のエラーが出た場合、pipは指定された要件を満たす配布ファイルを選べていません。

```text
ERROR: Could not find a version that satisfies the requirement demo_probe==99.0 (from versions: 1.0)
ERROR: No matching distribution found for demo_probe==99.0
```

`from versions: none`でも、パッケージが公開されていないとは限りません。Pythonの版やOSに合わないファイルが候補から外れた場合、取得先に接続できなかった場合にも、候補が残らないことがあります。

まず、エラーが出た環境で、使っているPythonとpipを確認してください。

```bash
python -c "import sys; print(sys.executable); print(sys.version)"
python -m pip --version
```

そのうえで、最後の2行より前に出ている接続エラーや候補の除外理由を読みます。名前、版の指定、Pythonへの対応、取得先、OS向けの形式を順に確認すると、直す場所を絞れます。

## エラーの意味とfrom versionsの読み方

pipは、取得先から見つけたファイルをすべてインストール候補にするわけではありません。[候補選択の公式文書](https://pip.pypa.io/en/stable/development/architecture/package-finding/)では、リンクから候補を作る段階で、ファイル形式やPythonへの対応などを評価すると説明しています。

[pip 26.2.1の実装](https://github.com/pypa/pip/blob/26.2.1/src/pip/_internal/index/package_finder.py)でも、wheelの対応条件や`Requires-Python`に合わないリンクを除外しています。wheelは、インストール用に用意された`.whl`形式の配布ファイルです。

そのため、`from versions`はPyPIに公開された全バージョンの一覧ではありません。

| 表示 | 分かること | それだけでは分からないこと |
|---|---|---|
| `from versions: none` | 表示対象の候補が残っていない | パッケージ自体が存在しないのか、環境や取得先の問題なのか |
| `from versions: 1.0, 2.0` | その版の候補は見つかっている | 指定した版や依存関係を満たしてインストールできるか |

[pip 26.2.1の診断処理](https://github.com/pypa/pip/blob/26.2.1/src/pip/_internal/resolution/resolvelib/factory.py)は、候補の版を集めて一覧を作り、一覧が空なら`none`を表示します。Python要件で除外した版があれば、その案内を先に出す処理もあります。Python要件の不一致が別の診断として出る場合もあり、エラーが常にこの2行になるわけではありません。

冒頭の出力は、CPython 3.12.14とpip 26.2.1で、ローカルに作成した検証用wheelを使って再現したものです。`demo_probe`は説明用の名前で、PyPIから取得したパッケージではありません。1.0だけがある場所で99.0を要求すると、候補一覧には1.0が出てもインストールには進めませんでした。

## パッケージ名とバージョン指定を確認する

エラーに出た名前を、利用するライブラリの公式インストール手順と照合します。Pythonの`import`に書く名前と、pipに渡す配布名は一致するとは限りません。[PyPAの公式ガイド](https://packaging.python.org/en/latest/discussions/distribution-package-vs-import-package/)には、Pillowをインストールして`PIL`を読み込む例が示されています。

標準ライブラリを、外部パッケージとしてインストールしようとしていないかも確認してください。知らない名前を別のパッケージに置き換える前に、プロジェクトが何を要求しているかを確かめます。

利用中の取得先で見つかる版は、次で確認できます。`requests`は調べたい配布名に置き換えてください。

```bash
python -m pip index versions requests
```

[このコマンドの公式文書](https://pip.pypa.io/en/stable/cli/pip_index/)は、Pythonやプラットフォームの条件を指定できることも説明しています。表示結果は実行環境やオプションに左右されるため、PyPIにある全配布ファイルの一覧とは区別してください。

版を`==`で固定している場合は、その版が存在し、対象環境で使えるかを確認します。`requirements.txt`や制約ファイルを使っているなら、コマンドだけでなくファイル内の指定も見直してください。

指定が誤っていた場合は、プロジェクトが対応する版へ修正します。版の指定を外すと選ばれる版が変わるため、動作確認なしに固定を外す対処は避けます。

## Pythonの版とRequires-Pythonを確認する

パッケージには、使えるPythonの範囲を示す`Requires-Python`が設定されていることがあります。実行中のPythonが範囲外なら、その版は利用できません。

先ほどの`sys.version`で実行環境を確認し、PyPIの対象版のページやライブラリの公式文書にある対応条件と照合してください。`pip index versions`は版の一覧を見るためのコマンドで、各版のPython要件を一覧表示するものではありません。

ログには、Pythonの条件で無視された版の案内が出る場合があります。また、候補の情報を読み込んだあとで、パッケージが別のPythonを要求しているという診断が出る場合もあります。

ローカル検証では、`Requires-Python: >=4`を持つ検証用wheelをPython 3.12.14で指定すると、`requires a different Python`を含む診断になりました。候補が残らない場合と、候補のPython要件が満たせない場合で、表示される経路が異なります。

Pythonを変更する場合は、アプリケーション側も対応している版を選び、そのPythonの環境でインストールし直します。既存のPythonを維持する場合は、ライブラリの対応表を確認して互換性のある版を指定してください。特定の版番号を推測して選ばず、対応条件を根拠に決めます。

## 取得先と接続エラーを確認する

PyPIではなく、社内の取得先やローカルのファイルだけを見ている場合があります。次で設定の読み込み元と値を確認できます。

```bash
python -m pip config debug
```

[pip configの公式文書](https://pip.pypa.io/en/stable/cli/pip_config/)は、`debug`で設定ファイルと値を表示できると説明しています。[設定の優先順位](https://pip.pypa.io/en/stable/topics/configuration/)では、コマンドのオプション、環境変数、設定ファイルの順に優先されます。

`index-url`、`extra-index-url`、`no-index`、`find-links`に加え、実行したコマンドや`requirements.txt`内の取得先指定も確認してください。社内パッケージは、正しい取得先と認証が必要です。公開PyPIへ切り替えれば直るとは限りません。

ログの前半に名前解決、接続の再試行、証明書検証の失敗があれば、先にその接続問題を直します。取得先から候補を受け取れていない状態で、パッケージ名や版を変えても原因が残るためです。

必要なら、詳細ログで候補を除外した理由を確認します。

```bash
python -m pip install -vvv requests
```

これは調査だけのコマンドではなく、条件が満たされれば実際にインストールします。変更してよい仮想環境で実行し、`requests`を対象の配布名や実際の要件に置き換えてください。設定やログを共有するときは、認証情報を含むURLや社内の情報を伏せます。

## OSとCPUに対応するwheelを確認する

wheelには、Pythonの実装や版、OSなどの対応条件が付いています。手元の環境がその条件に合わなければ、ファイルは候補から外れます。

ローカル検証では、Windows向けのwheelだけを置いた場所をLinuxから参照すると、ファイルが存在していても`from versions: none`になりました。これは、`none`をパッケージ不在と断定できない例です。

実行環境が受け付ける条件は、次で確認できます。

```bash
python -m pip debug --verbose
```

[pip debugの公式文書](https://pip.pypa.io/en/stable/cli/pip_debug/)と、対象パッケージの配布ファイル一覧を照合してください。DockerではホストのOSではなく、コンテナ内のPythonと環境を確認します。

[pipのIssue #10501](https://github.com/pypa/pip/issues/10501)には、Jetson Xavier NXでTensorFlowのインストールが止まり、CPU、OS、Pythonなどの何が合わないのかを表示してほしいという報告があります。この報告だけでは原因を確定できませんが、診断の最後の一行では不一致の種類が分からない実例です。

ソース配布があれば、対応するwheelがなくてもビルドできる場合があります。ただし、ソース配布の有無、必要なコンパイラや外部ライブラリ、対象環境への対応を確認する必要があります。

[インストールの公式文書](https://pip.pypa.io/en/stable/cli/pip_install/)にある`--only-binary`はソース配布を使わない指定です。これを付けた場合だけ失敗するなら、wheelの有無が手がかりになります。反対に、ソースからのビルドが始まったあとの失敗は、ビルドログの別のエラーとして調べてください。

## 近いエラーとの違い

| 文言・状況 | 確認する内容 |
|---|---|
| `No matching distribution found` | 取得先と実行環境で、要件を満たす候補を選べるか |
| `ResolutionImpossible`と依存関係の競合説明 | 複数の要求を同時に満たせるか |
| `requires a different Python` | 対象パッケージのPython要件 |
| `Failed building wheel` | 候補を取得したあとのビルド処理 |
| `ModuleNotFoundError` | 実行中のPythonがモジュールを読み込めるか |

依存関係が競合している場合は、[pipの依存関係解決の公式文書](https://pip.pypa.io/en/stable/topics/dependency-resolution/)にあるように、競合の説明から各パッケージの要求を確認します。

たとえば、一方が`requests==2.25.0`、もう一方が`requests>=2.28.0`を必須とするなら、両方を満たす版はありません。requestsの指定だけを広げても解決せず、要求元のパッケージの組み合わせや版を変更する必要があります。

一方、インストール後の読み込みで止まる場合は、[PythonのModuleNotFoundErrorの記事](/posts/python_modulenotfounderror/)で、実行するPythonとインストール先の違いを確認してください。

## 解決手順のまとめ

最初に、使っているPythonとpipを確認し、ログの前半に接続エラーや候補の除外理由がないかを読みます。`from versions: none`だけで名前の誤りと決めつけないでください。

接続に問題がなければ、配布名、固定した版、Pythonの対応範囲、取得先の指定を確認します。OS向けのwheelが候補から外れている場合は、その環境を正式にサポートする配布方法を選びます。

最後に、修正した要件でインストールし、アプリケーションの動作を確認してください。候補選び、ビルド、実行時の読み込みは別の段階なので、実際に止まった段階のログに沿って対処します。