---
title: "pipの外部管理エラー対処法"
date: 2026-10-09T09:00:00+09:00
slug: pip_externally_managed_environment
description: "externally-managed-environmentはOSやHomebrewが管理するPythonへの変更を止める表示。venv・pipxの使い分けと、--userで回避できない理由を解説。"
tags: ["pip", "Python"]
images: ["og/posts/pip_externally_managed_environment.png"]
draft: false
errorCode: "externally-managed-environment"
service: "pip"
error_type: "externally-managed-environment"
components: ["pip", "venv", "EXTERNALLY-MANAGED"]
related_services: ["Python", "Homebrew"]
trend_incident: false
---

## 冒頭まとめ

`pip install`で次の[エラー](/glossary/エラー/)が出たら、使っているPythonが[OS](/glossary/os/)やHomebrewなどの管理対象になっている。[パッケージ](/glossary/パッケージ/)名や要求する版を変える前に、[インストール](/glossary/インストール/)先の[環境](/glossary/環境/)を確認する。

```text
error: externally-managed-environment

× This environment is externally managed
```

自分の[コード](/glossary/コード/)から読み込む[ライブラリ](/glossary/ライブラリ/)は、[プロジェクト](/glossary/プロジェクト/)用の仮想環境に入れる。仮想環境とは、Pythonの[パッケージ](/glossary/パッケージ/)の保存先を分けた[環境](/glossary/環境/)のこと。[コマンド](/glossary/コマンド/)として使うPython製[ツール](/glossary/ツール/)は、[ツール](/glossary/ツール/)ごとに仮想環境を作るpipxを使う方法もある。

`sudo`で[権限](/glossary/権限/)を上げたり、`--user`でユーザー用の保存先へ変えたりしても、この管理対象の検査は解除されない。まずはvenvで[環境](/glossary/環境/)を分ける手順へ進む。

## エラーが出るPythonを確認する

[エラー](/glossary/エラー/)を出したPythonと同じ実行[ファイル](/glossary/ファイル/)で確認する。以下はmacOS・[Linux](/glossary/linux/)で`python3`を使っていた場合の例である。

```bash
python3 -m pip --version
python3 -c "import sys; print(sys.executable); print('venv:', sys.prefix != sys.base_prefix)"
python3 -c "import pathlib, sysconfig; p = pathlib.Path(sysconfig.get_path('stdlib')) / 'EXTERNALLY-MANAGED'; print(p); print('marker exists:', p.is_file())"
```

`pip --version`の出力にはpipの版と配置先が含まれる。裸の`pip`[コマンド](/glossary/コマンド/)と`python3 -m pip`で違うPythonを使っている場合があるため、以後は対象のPythonからpipを呼び出す。

`venv: False`で、[標準](/glossary/標準/)[ライブラリ](/glossary/ライブラリ/)の[ディレクトリ](/glossary/ディレクトリ/)に`EXTERNALLY-MANAGED`があれば、この検査の条件に当てはまる。[PyPAの現行仕様](https://packaging.python.org/en/latest/specifications/externally-managed-environments/)は、仮想環境の外であることと、この管理用[ファイル](/glossary/ファイル/)の存在を検査するよう定めている。

[ファイル](/glossary/ファイル/)は、[パッケージ](/glossary/パッケージ/)を消してよいか調べるためではなく、そのPythonの管理元を確認するために見る。[削除](/glossary/削除/)はしない。

## OSやHomebrewの更新で出る理由

[OS](/glossary/os/)やHomebrewは、自分が提供したPythonと[パッケージ](/glossary/パッケージ/)を管理している。そこへpipで別の版を入れると、管理元が想定した構成と食い違う可能性がある。管理用[ファイル](/glossary/ファイル/)は、その[環境](/glossary/環境/)を通常のpip操作で変更しないよう示すものだ。

[pipの変更履歴](https://pip.pypa.io/en/stable/news/#v23-0)では、この[ファイル](/glossary/ファイル/)を読む処理が23.0で追加されている。管理用[ファイル](/glossary/ファイル/)を置くかどうかはPythonの提供元が決めるため、pipの版が新しいだけで必ず発生するわけではない。

[Debian 12のリリースノート](https://www.debian.org/releases/bookworm/amd64/release-notes/ch-information.en.html#python-interpreters-marked-externally-managed)は、提供するPythonを外部管理対象にしたことと、[ライブラリ](/glossary/ライブラリ/)には仮想環境、アプリにはpipxを使う方針を説明している。[Homebrewの現行文書](https://docs.brew.sh/Language-Runtimes-and-Packages#python)も、現在提供するPythonの外部管理と仮想環境の利用を案内している。

[エラー](/glossary/エラー/)本文は[環境](/glossary/環境/)ごとに変わる。管理用[ファイル](/glossary/ファイル/)の`[externally-managed]`内にある`Error`や言語別の項目から案内を読むため、Debianのapt案内とHomebrewのbrew案内は同じ文面にはならない。適切な案内を読み取れなければpipの既定文面になる。空の[ファイル](/glossary/ファイル/)でも、存在による検査自体はなくならない。

## venvのPythonからインストールする

[プロジェクト](/glossary/プロジェクト/)の[ディレクトリ](/glossary/ディレクトリ/)で、まだ使っていない`.venv`という名前に仮想環境を作る。

```bash
python3 -m venv .venv
.venv/bin/python -m pip --version
.venv/bin/python -m pip install requests
```

`requests`は例なので、必要な[パッケージ](/glossary/パッケージ/)名に置き換える。実行する[コード](/glossary/コード/)も、同じ[環境](/glossary/環境/)のPythonから呼ぶ。

```bash
.venv/bin/python your_script.py
```

[環境](/glossary/環境/)を有効化する操作は必須ではない。[Pythonのvenv文書](https://docs.python.org/3/library/venv.html)にも、有効化せず実行[ファイル](/glossary/ファイル/)の[パス](/glossary/パス/)を直接指定できると説明されている。上の書き方なら、どのPythonへ入れ、どのPythonで実行するかを揃えられる。

有効化して短い[コマンド](/glossary/コマンド/)を使いたい場合は、macOS・[Linux](/glossary/linux/)の[bash](/glossary/bash/)やzshでは次のようにする。

```bash
source .venv/bin/activate
python -m pip install requests
```

Windowsの[コマンドプロンプト](/glossary/コマンドプロンプト/)では、実行[ファイル](/glossary/ファイル/)の場所が異なる。

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install requests
```

Debian・Ubuntuで作成時に`ensurepip`が利用できないなどと表示されたら、[エラー](/glossary/エラー/)本文が指定するvenv用[パッケージ](/glossary/パッケージ/)を入れる。[標準](/glossary/標準/)の`python3`向けには次が候補になる。

```bash
sudo apt install python3-venv
```

別の版のPythonを指定している場合は、それに[対応](/glossary/対応/)するvenv[パッケージ](/glossary/パッケージ/)が必要になることがある。作成に失敗したまま、システムのpipで代わりに[インストール](/glossary/インストール/)しない。

## コマンド用ツールはpipxを使う

blackなど、[コマンド](/glossary/コマンド/)として使いたいアプリにはpipxを使う方法がある。[ライブラリ](/glossary/ライブラリ/)を自分の[コード](/glossary/コード/)から`import`したい場合は、前の節のvenvを使う。pipxの[環境](/glossary/環境/)へ入れた[ライブラリ](/glossary/ライブラリ/)が、自分の[プロジェクト](/glossary/プロジェクト/)からそのまま読めるようになるわけではない。

Debian・Ubuntuでは、提供されているpipx[パッケージ](/glossary/パッケージ/)を使う。

```bash
sudo apt install pipx
pipx ensurepath
pipx install black
```

Homebrewでは次のようにする。

```bash
brew install pipx
pipx ensurepath
pipx install black
```

`ensurepath`の案内に従って[ターミナル](/glossary/ターミナル/)を開き直し、`black --version`などで確認する。システムが提供する[ライブラリ](/glossary/ライブラリ/)を使う目的なら、pipの代わりにaptなどで入れる方法もある。たとえばDebian・Ubuntuで提供されているrequestsなら`sudo apt install python3-requests`を使う。[OS](/glossary/os/)側の[パッケージ](/glossary/パッケージ/)名とPyPI上の名前が常に一致するとは限らない。

## userやsudoで回避しない

`--user`はユーザー用の保存先を選ぶ指定であり、外部管理の検査を解除する指定ではない。ユーザー側に入れた版が、そのPythonから見える[OS](/glossary/os/)側の版より優先して読み込まれれば、[ファイル](/glossary/ファイル/)を直接上書きしなくても動作を変える可能性がある。

[pipのinstall実装](https://github.com/pypa/pip/blob/main/src/pip/_internal/commands/install.py)でも、通常の現在環境への[インストール](/glossary/インストール/)では、ユーザー用保存先の決定より先に外部管理を検査する。[Issue #13249](https://github.com/pypa/pip/issues/13249)には、Ubuntu 24.04・Python 3.12.3・pip 24.0で`pip install --user flake8`が同じ[エラー](/glossary/エラー/)になった報告がある。2025年の報告であり、ユーザー用の保存先なら必ず通るという説明は使えない。

`sudo`も管理対象を解除しない。仮想環境を作ったのに同じ[エラー](/glossary/エラー/)が出る場合は、システムのpipを呼んでいないかを確認し、`.venv/bin/python -m pip`で指定する。仮想環境の作成・実行自体に失敗する場合は、その別の[エラー](/glossary/エラー/)を先に解決する。

`--break-system-packages`は、この検査を明示的に解除する指定である。[pipの変更履歴](https://pip.pypa.io/en/stable/news/#v23-0-1)では23.0.1で追加されている。管理元との整合性を保証するものではなく、[権限](/glossary/権限/)や依存関係など他の失敗まで解除するものでもない。通常の[プロジェクト](/glossary/プロジェクト/)ではvenvを使い、恒久設定への追加や管理用[ファイル](/glossary/ファイル/)の[削除](/glossary/削除/)から始めない。

`--target`・`--prefix`・`--root`は保存先を変える指定で、現行pipにはこの検査を省く経路がある。ただし、元の[環境](/glossary/環境/)が管理対象でなくなるわけではない。読み込み先や実行[スクリプト](/glossary/スクリプト/)の扱いも変わるため、venvの代わりとなる一般的な対処としては使わない。

## 補足：似ているが別のエラー

`Permission denied`は、対象[ファイル](/glossary/ファイル/)への書き込みなどが[権限](/glossary/権限/)で拒否された表示である。外部管理の検査とは別なので、[権限](/glossary/権限/)[エラー](/glossary/エラー/)への対処をそのまま当てはめない。

`WARNING: Running pip as the 'root' user`はrootでの実行に関する警告であり、外部管理の解除を意味しない。rootであっても今回の[エラー](/glossary/エラー/)が出る場合がある。

`Could not find a version that satisfies the requirement`や`No matching distribution found`は、要求を満たす配布物を取得・選択できないときの表示である。今回の[エラー](/glossary/エラー/)は[インストール](/glossary/インストール/)先の管理方針の検査なので、[パッケージ](/glossary/パッケージ/)の版を変えることより、使う[環境](/glossary/環境/)を分けることが先になる。

## 解決手順のまとめ

[エラー](/glossary/エラー/)を出したPythonの実行[パス](/glossary/パス/)とpipの配置先を確認し、[プロジェクト](/glossary/プロジェクト/)用のvenvを作る。その中のPythonからpipを呼び、[コード](/glossary/コード/)も同じPythonで実行する。[コマンド](/glossary/コマンド/)用アプリはpipx、[OS](/glossary/os/)が提供する[パッケージ](/glossary/パッケージ/)は[OS](/glossary/os/)の管理[コマンド](/glossary/コマンド/)を使う方法を検討する。

本記事では、ローカルのPython 3.12.14でvenvの作成と、そのPythonからのpip起動を確認した。pip 26.2.1の検査関数には一時的な管理用[ファイル](/glossary/ファイル/)と模擬の環境判定を渡し、仮想環境外で拒否、仮想環境内で省略、[ファイル](/glossary/ファイル/)なしで省略、独自本文の読み取りを確認した。システムの管理用[ファイル](/glossary/ファイル/)は変更していない。requests・blackの[インストール](/glossary/インストール/)とapt・brew操作は未実行である。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の[仕様](/glossary/仕様/)は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
