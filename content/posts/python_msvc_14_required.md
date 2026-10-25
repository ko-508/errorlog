---
title: "PythonのMSVC 14.0要求エラー対処法"
date: 2026-10-19
slug: python_msvc_14_required
draft: false
description: "Microsoft Visual C++ 14.0 or greater is required が出たら、組み立て済みの配布物を使えるかを確認します。ソースから組み立てる必要がある場合は、Build ToolsのC++部品とWindows SDKを確認します。"
tags: ["Python", "pip", "Windows"]
images: ["og/posts/python_msvc_14_required.png"]
errorCode: "Microsoft Visual C++ 14.0 or greater is required"
service: "Python"
error_type: "MSVC build tools not found"
components: ["setuptools", "MSVC", "pip"]
related_services: ["Windows"]
trend_incident: false
---

## 冒頭まとめ

WindowsでPythonの[パッケージ](/glossary/パッケージ/)を入れる途中に、次の[エラー](/glossary/エラー/)が出ることがあります。

```text
error: Microsoft Visual C++ 14.0 or greater is required. Get it with "Microsoft C++ Build Tools": https://visualstudio.microsoft.com/visual-cpp-build-tools/
```

setuptoolsが、CやC++の[コード](/glossary/コード/)を組み立てるためのMicrosoft製の道具を見つけられなかったことを示します。確認した[setuptoolsの実装](https://github.com/pypa/setuptools/blob/main/setuptools/_distutils/compilers/C/msvc.py)では、[環境](/glossary/環境/)を[設定](/glossary/設定/)する `vcvarsall.bat` が見つからないと、この文言を出します。

対処は、組み立て済みの配布物を使うか、ソースから組み立てるためのC++部品を導入するかです。Visual Studioの編集画面を含む本体を、必ず入れる必要はありません。

## どのパッケージの組み立てで止まったかを読む

最後の[エラー](/glossary/エラー/)行だけでなく、その前にある[パッケージ](/glossary/パッケージ/)名を確認してください。自分が指定した[パッケージ](/glossary/パッケージ/)ではなく、その依存先の組み立てが失敗していることもあります。

実例として、[setuptoolsのIssue #4431](https://github.com/pypa/setuptools/issues/4431)では、Windows上でpyvexを導入する過程でcffiのソース配布物が選ばれ、その処理中に同じMSVCの要求が出ています。報告時の[環境](/glossary/環境/)はPython 3.13の開発版とpip 24.1です。この報告だけで、現在の同じ[パッケージ](/glossary/パッケージ/)も必ず失敗するとは言えません。

実行に使うPythonの場所と版も記録します。以下はWindowsの[コマンドプロンプト](/glossary/コマンドプロンプト/)用です。

```bat
python --version
python -m pip --version
python -c "import sys, platform; print(sys.executable); print(platform.machine())"
```

以降の `SomePackage` は、実際に導入する配布名に置き換えてください。仮想環境を使っている場合は、その[環境](/glossary/環境/)のPythonで実行します。

## 組み立て済みの配布物だけで導入できるかを確認する

wheelは、導入用に組み立てて配布される[ファイル](/glossary/ファイル/)です。[Python Packaging User Guide](https://packaging.python.org/en/latest/tutorials/installing-packages/#source-distributions-vs-wheels)によると、pipは[対応](/glossary/対応/)するwheelを優先し、見つからなければソース配布物からwheelを作ります。C/C++の拡張を含むソースを使うと、手元の組み立て用の道具が必要になる場合があります。

ソースを使わずに導入したい場合は、次を実行します。

```bat
python -m pip install --only-binary=:all: SomePackage
```

[pipの公式説明](https://pip.pypa.io/en/stable/cli/pip_install/#cmdoption-only-binary)では、この指定はソース配布物を使用しません。必要な依存先も含めて条件に合うwheelが無ければ、導入は失敗します。失敗した場合は、表示された配布名について、[対応](/glossary/対応/)するPythonの版やWindows向けの配布[ファイル](/glossary/ファイル/)を確認してください。

これはMSVCを導入する指定ではありません。ソースからの組み立てを避けられるかを判断する方法です。

`--prefer-binary` は、より新しいソース配布物があってもwheelを優先する別の指定です。ソースの利用自体を禁止するものではないため、組み立てを確実に避けたい場合は `--only-binary=:all:` を使います。

## Build ToolsではC++の部品を選ぶ

ソースから組み立てる必要がある場合は、[Microsoft C++ Build Toolsの配布ページ](https://visualstudio.microsoft.com/visual-cpp-build-tools/)から入手します。

[Microsoftの導入案内](https://learn.microsoft.com/en-us/cpp/build/building-on-the-command-line)は、[コマンド](/glossary/コマンド/)だけで組み立てる道具が必要ならBuild Toolsを入れ、Desktop development with C++を選ぶよう案内しています。日本語の画面ではC++によるデスクトップ開発に相当する項目を確認します。

導入済みならVisual Studio Installerで対象製品を変更し、C++の項目を確認してください。[Build Tools 2022の構成一覧](https://learn.microsoft.com/en-us/visualstudio/install/workload-component-id-vs-build-tools?view=vs-2022#desktop-development-with-c)では、MSVCのx64/x86用[ツール](/glossary/ツール/)とWindows [SDK](/glossary/sdk/)が推奨部品に含まれています。実際の部品名や版は、導入する製品と対象の[CPU](/glossary/cpu/)によって異なります。

[エラー](/glossary/エラー/)に14.0と書かれていても、それだけを理由に古いVisual Studio 2015を探す必要はありません。確認したsetuptoolsは、Visual Studio 2017以降の導入先を先に探します。ただし、個々の[パッケージ](/glossary/パッケージ/)が指定する[対応](/glossary/対応/)コンパイラや[SDK](/glossary/sdk/)の条件は、別に満たす必要があります。

## 導入済みなのに見つからない場合を調べる

Build Toolsという製品が入っていることと、必要なC++部品が見つかることは別です。setuptoolsの実装は `vswhere.exe` でC++の[ツール](/glossary/ツール/)を含む導入先を探し、その中の `vcvarsall.bat` の存在を確認します。

x86/x64向けの部品を調べる場合は、[コマンドプロンプト](/glossary/コマンドプロンプト/)で次を実行できます。

```bat
"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
```

これはsetuptoolsの探索条件の一部を使った確認です。実装で指定される `-prerelease` は省略しており、ARM64向けの判定もこの[コマンド](/glossary/コマンド/)には含めていません。

導入先が出なければ、まずInstallerでC++部品を確認します。`vswhere.exe` 自体が見つからない場合は、上の[コマンド](/glossary/コマンド/)では部品の有無を判断できません。導入先が表示された場合は、その下の `VC\Auxiliary\Build\vcvarsall.bat` があるかも確認します。

確認した実装には、`DISTUTILS_USE_SDK` が[設定](/glossary/設定/)されていると探索を飛ばし、現在の[環境](/glossary/環境/)を使う分岐もあります。この[変数](/glossary/変数/)を[設定](/glossary/設定/)するだけではコンパイラは追加されないため、[エラー](/glossary/エラー/)を消す目的だけで[設定](/glossary/設定/)する対処は避けます。

## 再実行後はエラーが変わったかを確認する

導入が終わったら、新しい[コマンドプロンプト](/glossary/コマンドプロンプト/)で対象の仮想環境を有効にし、同じ導入を試します。

```bat
python -m pip install SomePackage
```

同じ[エラー](/glossary/エラー/)なら、C++部品の選択と探索結果を再確認します。別のコンパイルエラーや、ヘッダーファイルが無いという[エラー](/glossary/エラー/)に変わった場合は、その新しい文言を調べてください。MSVCを見つけられても、[パッケージ](/glossary/パッケージ/)固有の追加部品が必要な場合があります。

なお、通常の[コマンドプロンプト](/glossary/コマンドプロンプト/)で `cl` が見つからないことだけでは、MSVC未導入とは判断できません。Microsoftは[開発者向けコマンドプロンプト](https://learn.microsoft.com/en-us/cpp/build/building-on-the-command-line#developer-command-prompt-shortcuts)で組み立て用の[環境](/glossary/環境/)を[設定](/glossary/設定/)する仕組みを説明しています。setuptoolsにも、見つけた `vcvarsall.bat` を呼び出して[環境](/glossary/環境/)を取得する[処理](/glossary/処理/)があります。

本記事のWindows向け[コマンド](/glossary/コマンド/)と導入操作は実機では未検証です。説明は2026年10月19日に確認した公式資料とsetuptoolsの実装に基づきます。

## 似ている導入エラーとの違い

[pipのNo matching distribution found](/posts/pip_no_matching_distribution/)は、条件に合う配布物が見つからない段階の[エラー](/glossary/エラー/)です。本件はソースの組み立てに進んだあと、MSVCの[環境](/glossary/環境/)を見つけられない場合に出ます。`--only-binary` を指定した結果、前者に変わることもあります。

[pipのexternally-managed-environment](/posts/pip_externally_managed_environment/)は、外部の管理者が管理するPython[環境](/glossary/環境/)への導入を制限する仕組みです。C++の部品不足とは別の問題です。

[node-gypのbuild error](/posts/npm_gyp_err_build_error/)もWindowsではC++の道具が関わる場合がありますが、Node.js側の組み立てです。本記事のPython用[コマンド](/glossary/コマンド/)とは分けて確認します。

`subprocess-exited-with-error` は、Issue #4431でも同じMSVC[エラー](/glossary/エラー/)に続いて表示されています。その行だけで原因を決めず、前にある具体的な[エラー](/glossary/エラー/)を読みます。

## 解決手順のまとめ

まず組み立てに失敗した配布名と、使用しているPythonを確認します。[対応](/glossary/対応/)するwheelがあるなら、組み立てを避けて導入できます。

ソースが必要ならBuild ToolsのC++部品を確認し、導入先と `vcvarsall.bat` の存在を調べます。Build Toolsを入れただけで終わりにせず、同じPythonで再実行して、MSVCの要求が解消したかまで確認してください。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の[仕様](/glossary/仕様/)は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
