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

`pip install`で次のエラーが出たら、使っているPythonがOSやHomebrewなどの管理対象になっている。パッケージ名や要求する版を変える前に、インストール先の環境を確認する。

```text
error: externally-managed-environment

× This environment is externally managed
```

自分のコードから読み込むライブラリは、プロジェクト用の仮想環境に入れる。仮想環境とは、Pythonのパッケージの保存先を分けた環境のこと。コマンドとして使うPython製ツールは、ツールごとに仮想環境を作るpipxを使う方法もある。

`sudo`で権限を上げたり、`--user`でユーザー用の保存先へ変えたりしても、この管理対象の検査は解除されない。まずはvenvで環境を分ける手順へ進む。

## エラーが出るPythonを確認する

エラーを出したPythonと同じ実行ファイルで確認する。以下はmacOS・Linuxで`python3`を使っていた場合の例である。

```bash
python3 -m pip --version
python3 -c "import sys; print(sys.executable); print('venv:', sys.prefix != sys.base_prefix)"
python3 -c "import pathlib, sysconfig; p = pathlib.Path(sysconfig.get_path('stdlib')) / 'EXTERNALLY-MANAGED'; print(p); print('marker exists:', p.is_file())"
```

`pip --version`の出力にはpipの版と配置先が含まれる。裸の`pip`コマンドと`python3 -m pip`で違うPythonを使っている場合があるため、以後は対象のPythonからpipを呼び出す。

`venv: False`で、標準ライブラリのディレクトリに`EXTERNALLY-MANAGED`があれば、この検査の条件に当てはまる。[PyPAの現行仕様](https://packaging.python.org/en/latest/specifications/externally-managed-environments/)は、仮想環境の外であることと、この管理用ファイルの存在を検査するよう定めている。

ファイルは、パッケージを消してよいか調べるためではなく、そのPythonの管理元を確認するために見る。削除はしない。

## OSやHomebrewの更新で出る理由

OSやHomebrewは、自分が提供したPythonとパッケージを管理している。そこへpipで別の版を入れると、管理元が想定した構成と食い違う可能性がある。管理用ファイルは、その環境を通常のpip操作で変更しないよう示すものだ。

[pipの変更履歴](https://pip.pypa.io/en/stable/news/#v23-0)では、このファイルを読む処理が23.0で追加されている。管理用ファイルを置くかどうかはPythonの提供元が決めるため、pipの版が新しいだけで必ず発生するわけではない。

[Debian 12のリリースノート](https://www.debian.org/releases/bookworm/amd64/release-notes/ch-information.en.html#python-interpreters-marked-externally-managed)は、提供するPythonを外部管理対象にしたことと、ライブラリには仮想環境、アプリにはpipxを使う方針を説明している。[Homebrewの現行文書](https://docs.brew.sh/Language-Runtimes-and-Packages#python)も、現在提供するPythonの外部管理と仮想環境の利用を案内している。

エラー本文は環境ごとに変わる。管理用ファイルの`[externally-managed]`内にある`Error`や言語別の項目から案内を読むため、Debianのapt案内とHomebrewのbrew案内は同じ文面にはならない。適切な案内を読み取れなければpipの既定文面になる。空のファイルでも、存在による検査自体はなくならない。

## venvのPythonからインストールする

プロジェクトのディレクトリで、まだ使っていない`.venv`という名前に仮想環境を作る。

```bash
python3 -m venv .venv
.venv/bin/python -m pip --version
.venv/bin/python -m pip install requests
```

`requests`は例なので、必要なパッケージ名に置き換える。実行するコードも、同じ環境のPythonから呼ぶ。

```bash
.venv/bin/python your_script.py
```

環境を有効化する操作は必須ではない。[Pythonのvenv文書](https://docs.python.org/3/library/venv.html)にも、有効化せず実行ファイルのパスを直接指定できると説明されている。上の書き方なら、どのPythonへ入れ、どのPythonで実行するかを揃えられる。

有効化して短いコマンドを使いたい場合は、macOS・Linuxのbashやzshでは次のようにする。

```bash
source .venv/bin/activate
python -m pip install requests
```

Windowsのコマンドプロンプトでは、実行ファイルの場所が異なる。

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install requests
```

Debian・Ubuntuで作成時に`ensurepip`が利用できないなどと表示されたら、エラー本文が指定するvenv用パッケージを入れる。標準の`python3`向けには次が候補になる。

```bash
sudo apt install python3-venv
```

別の版のPythonを指定している場合は、それに対応するvenvパッケージが必要になることがある。作成に失敗したまま、システムのpipで代わりにインストールしない。

## コマンド用ツールはpipxを使う

blackなど、コマンドとして使いたいアプリにはpipxを使う方法がある。ライブラリを自分のコードから`import`したい場合は、前の節のvenvを使う。pipxの環境へ入れたライブラリが、自分のプロジェクトからそのまま読めるようになるわけではない。

Debian・Ubuntuでは、提供されているpipxパッケージを使う。

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

`ensurepath`の案内に従ってターミナルを開き直し、`black --version`などで確認する。システムが提供するライブラリを使う目的なら、pipの代わりにaptなどで入れる方法もある。たとえばDebian・Ubuntuで提供されているrequestsなら`sudo apt install python3-requests`を使う。OS側のパッケージ名とPyPI上の名前が常に一致するとは限らない。

## userやsudoで回避しない

`--user`はユーザー用の保存先を選ぶ指定であり、外部管理の検査を解除する指定ではない。ユーザー側に入れた版が、そのPythonから見えるOS側の版より優先して読み込まれれば、ファイルを直接上書きしなくても動作を変える可能性がある。

[pipのinstall実装](https://github.com/pypa/pip/blob/main/src/pip/_internal/commands/install.py)でも、通常の現在環境へのインストールでは、ユーザー用保存先の決定より先に外部管理を検査する。[Issue #13249](https://github.com/pypa/pip/issues/13249)には、Ubuntu 24.04・Python 3.12.3・pip 24.0で`pip install --user flake8`が同じエラーになった報告がある。2025年の報告であり、ユーザー用の保存先なら必ず通るという説明は使えない。

`sudo`も管理対象を解除しない。仮想環境を作ったのに同じエラーが出る場合は、システムのpipを呼んでいないかを確認し、`.venv/bin/python -m pip`で指定する。仮想環境の作成・実行自体に失敗する場合は、その別のエラーを先に解決する。

`--break-system-packages`は、この検査を明示的に解除する指定である。[pipの変更履歴](https://pip.pypa.io/en/stable/news/#v23-0-1)では23.0.1で追加されている。管理元との整合性を保証するものではなく、権限や依存関係など他の失敗まで解除するものでもない。通常のプロジェクトではvenvを使い、恒久設定への追加や管理用ファイルの削除から始めない。

`--target`・`--prefix`・`--root`は保存先を変える指定で、現行pipにはこの検査を省く経路がある。ただし、元の環境が管理対象でなくなるわけではない。読み込み先や実行スクリプトの扱いも変わるため、venvの代わりとなる一般的な対処としては使わない。

## 補足：似ているが別のエラー

`Permission denied`は、対象ファイルへの書き込みなどが権限で拒否された表示である。外部管理の検査とは別なので、権限エラーへの対処をそのまま当てはめない。

`WARNING: Running pip as the 'root' user`はrootでの実行に関する警告であり、外部管理の解除を意味しない。rootであっても今回のエラーが出る場合がある。

`Could not find a version that satisfies the requirement`や`No matching distribution found`は、要求を満たす配布物を取得・選択できないときの表示である。今回のエラーはインストール先の管理方針の検査なので、パッケージの版を変えることより、使う環境を分けることが先になる。

## 解決手順のまとめ

エラーを出したPythonの実行パスとpipの配置先を確認し、プロジェクト用のvenvを作る。その中のPythonからpipを呼び、コードも同じPythonで実行する。コマンド用アプリはpipx、OSが提供するパッケージはOSの管理コマンドを使う方法を検討する。

本記事では、ローカルのPython 3.12.14でvenvの作成と、そのPythonからのpip起動を確認した。pip 26.2.1の検査関数には一時的な管理用ファイルと模擬の環境判定を渡し、仮想環境外で拒否、仮想環境内で省略、ファイルなしで省略、独自本文の読み取りを確認した。システムの管理用ファイルは変更していない。requests・blackのインストールとapt・brew操作は未実行である。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
