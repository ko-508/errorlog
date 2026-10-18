---
title: "Pythonのcp932読み込みエラー対処法"
date: 2026-10-13
slug: python_unicodedecodeerror_cp932
draft: false
description: "UnicodeDecodeError: 'cp932' codec can't decode byteで止まる場合、ファイルの文字コードとPythonが読む方式を確認します。UTF-8・cp932の明示、BOM付きCSV、UTF-8モード、Python 3.15での既定値の変更を説明します。"
tags: ["Python", "Windows"]
images: ["og/posts/python_unicodedecodeerror_cp932.png"]
errorCode: "UnicodeDecodeError: cp932"
service: "Python"
error_type: "unicode_decode_cp932"
components: ["open", "TextIOWrapper"]
related_services: ["Windows"]
trend_incident: false
---

## 冒頭まとめ

PythonでテキストやCSVを読んだとき、次の[エラー](/glossary/エラー/)が出ることがあります。

```text
UnicodeDecodeError: 'cp932' codec can't decode byte 0x86 in position 8: illegal multibyte sequence
```

Pythonがcp932という文字[コード](/glossary/コード/)で読もうとして、その規則では読めない[バイト](/glossary/バイト/)列に当たっています。[UTF-8](/glossary/utf-8/)で[保存](/glossary/保存/)された[ファイル](/glossary/ファイル/)なら、読み込み側にも[UTF-8](/glossary/utf-8/)を指定します。

```python
with open("data.txt", encoding="utf-8") as f:
    text = f.read()
```

ただし、[エラー](/glossary/エラー/)に`cp932`と出ることは、[ファイル](/glossary/ファイル/)自体が[UTF-8](/glossary/utf-8/)である証拠ではありません。保存元の[設定](/glossary/設定/)や[ファイル](/glossary/ファイル/)の[仕様](/glossary/仕様/)を確認して、実際の文字[コード](/glossary/コード/)に合わせてください。

## cp932とファイルの文字コードが合っていない

文字[コード](/glossary/コード/)は、文字と[保存](/glossary/保存/)された[バイト](/glossary/バイト/)列を[対応](/glossary/対応/)させる規則です。cp932は日本語のWindowsで使われる文字[コード](/glossary/コード/)の一つです。[UTF-8](/glossary/utf-8/)とは異なる規則なので、[UTF-8](/glossary/utf-8/)の内容をcp932として読むと失敗したり、文字化けしたりします。

[Python 3.14のio公式文書](https://docs.python.org/3.14/library/io.html#text-encoding)は、文字[コード](/glossary/コード/)を指定しないテキスト読み込みが地域設定に依存すること、[UTF-8](/glossary/utf-8/)の[ファイル](/glossary/ファイル/)をそのまま開くとWindowsで問題になり得ることを説明しています。[UTF-8](/glossary/utf-8/)モードが有効なら、既定値は[UTF-8](/glossary/utf-8/)になります。

[エラー](/glossary/エラー/)の各部分は次を示します。

| 表示 | 確認できる内容 |
|---|---|
| `'cp932' codec` | 読み込みに使われた文字[コード](/glossary/コード/) |
| `byte 0x86` | 問題になった[バイト](/glossary/バイト/)の値 |
| `position 8` | 例外の対象となった[バイト](/glossary/バイト/)列内の位置 |
| `illegal multibyte sequence` | cp932として不正な並び |
| `incomplete multibyte sequence` | 複数[バイト](/glossary/バイト/)で表す文字の並びが途中で終わっている |

位置は[行番号](/glossary/行番号/)ではありません。テキスト読み込みで内部の[バッファ](/glossary/バッファ/)を処理している場合、[ファイル](/glossary/ファイル/)全体の先頭からの位置とも限りません。値や位置は内容によって変わります。

また、今回の確認では、[UTF-8](/glossary/utf-8/)の「日本」をcp932で読むと、例外を出さず「譌･譛ｬ」になりました。[エラー](/glossary/エラー/)が出ないことだけでは、正しく読めたと判断できません。

## 保存元と実際の読み込み設定を確認する

エディターの保存設定、出力した道具の[仕様](/glossary/仕様/)、[ファイル](/glossary/ファイル/)を提供した側の説明で、[UTF-8](/glossary/utf-8/)なのかcp932なのかを確認します。エディターが表示する推定値は、保存仕様そのものとは区別してください。

Python側は、[エラー](/glossary/エラー/)が出る同じ実行環境で確認します。

```python
import sys

print(sys.version)
print(sys.executable)
print(sys.flags.utf8_mode)

with open("data.txt") as f:
    print(f.encoding)
```

最後の例は読み込み前に、実際に選ばれた文字[コード](/glossary/コード/)を表示します。`sys.flags.utf8_mode`が1なら[UTF-8](/glossary/utf-8/)モードが有効です。

Python 3.11以降なら、地域設定の文字[コード](/glossary/コード/)も調べられます。

```python
import locale
print(locale.getencoding())
```

[localeの公式文書](https://docs.python.org/3.14/library/locale.html#locale.getencoding)によると、WindowsではANSIコードページを返します。ただし、この[関数](/glossary/関数/)は[UTF-8](/glossary/utf-8/)モードを無視します。返り値がcp932でも、文字[コード](/glossary/コード/)未指定の`open()`が[UTF-8](/glossary/utf-8/)を使う場合があります。`f.encoding`と合わせて確認してください。

## UTF-8とcp932を明示して読み込む

保存元が[UTF-8](/glossary/utf-8/)と確認できたら、`encoding="utf-8"`を指定します。CSVも、[標準](/glossary/標準/)のcsv[モジュール](/glossary/モジュール/)なら[ファイル](/glossary/ファイル/)を開く箇所で指定できます。

```python
import csv

with open("data.csv", encoding="utf-8", newline="") as f:
    for row in csv.reader(f):
        print(row)
```

保存元がcp932なら、次のようにします。

```python
with open("data_cp932.txt", encoding="cp932") as f:
    text = f.read()
```

cp932とPythonの`shift_jis`は、すべての文字について同じものではありません。Windows由来の[ファイル](/glossary/ファイル/)がcp932として出力されたなら、その指定に合わせます。

pandasなど別の[ライブラリ](/glossary/ライブラリ/)で読む場合は、その読み込み[関数](/glossary/関数/)の[仕様](/glossary/仕様/)を確認してください。[標準](/glossary/標準/)の`open()`の既定値が、すべての[ライブラリ](/glossary/ライブラリ/)にもそのまま当てはまるとは限りません。

[Pythonのcodecs公式文書](https://docs.python.org/3/library/codecs.html)は、外部の情報なしに文字[コード](/glossary/コード/)を確実に判定することはできないと説明しています。読めるまで指定を変えるだけでなく、読んだ日本語や列名が元の内容と一致するか確認します。

## BOM付きUTF-8ならutf-8-sigを使う

[UTF-8](/glossary/utf-8/)の[ファイル](/glossary/ファイル/)の先頭に、BOMという目印が付いている場合があります。[UTF-8](/glossary/utf-8/)のBOMは、先頭の3[バイト](/glossary/バイト/)`EF BB BF`です。

`encoding="utf-8"`で読むと、その目印は文字`U+FEFF`として残ります。CSVでは最初の列名に目に見えない文字が付いて、期待した列名と一致しないことがあります。

保存元がBOM付き[UTF-8](/glossary/utf-8/)なら、次を使えます。

```python
import csv

with open("data.csv", encoding="utf-8-sig", newline="") as f:
    for row in csv.reader(f):
        print(row)
```

[codecsのutf-8-sigの説明](https://docs.python.org/3/library/codecs.html#encodings-and-unicode)は、読み込み時に先頭のBOMを取り除くと説明しています。BOMがなければ、通常の[UTF-8](/glossary/utf-8/)として読み込みます。cp932やUTF-16の[ファイル](/glossary/ファイル/)を読むための万能な指定ではありません。

この記事では、同じBOM付き[ファイル](/glossary/ファイル/)を`utf-8`で読むと先頭に`U+FEFF`が残り、`utf-8-sig`で読むと取り除かれることを確認しました。

## UTF-8モードとPython 3.15の変更

自分の[コード](/glossary/コード/)を変更できるなら、[ファイル](/glossary/ファイル/)の[仕様](/glossary/仕様/)に合った`encoding`を明示します。依存する道具の内部で文字[コード](/glossary/コード/)未指定の`open()`が使われている場合は、[UTF-8](/glossary/utf-8/)モードが役立つこともあります。

```bat
python -X utf8 read.py
```

[Pythonの起動オプションの公式文書](https://docs.python.org/3.14/using/cmdline.html)は、`-X utf8`で[UTF-8](/glossary/utf-8/)モードを有効にできると説明しています。この指定はPython 3.7以降で使えます。明示された`encoding="cp932"`を上書きするものではありません。

[Python 3.15の変更点](https://docs.python.org/3.15/whatsnew/3.15.html)では、[UTF-8](/glossary/utf-8/)モードが既定で有効となり、文字[コード](/glossary/コード/)未指定の`open()`が[UTF-8](/glossary/utf-8/)を使うと説明されています。`PYTHONUTF8=0`や`-X utf8=0`で無効にすると、地域設定に依存する動作へ戻ります。

そのため、3.15への更新だけを解決策にすると、今度は文字[コード](/glossary/コード/)未指定で読んでいたcp932の[ファイル](/glossary/ファイル/)が読めなくなる可能性があります。[UTF-8](/glossary/utf-8/)の[ファイル](/glossary/ファイル/)には[UTF-8](/glossary/utf-8/)、cp932の[ファイル](/glossary/ファイル/)にはcp932を明示する方法なら、既定値の変更に左右されません。

文字[コード](/glossary/コード/)未指定の箇所を探すには、Python 3.10以降で次を使えます。

```bat
python -X warn_default_encoding read.py
```

これにより`EncodingWarning`を出せます。警告は、[ファイル](/glossary/ファイル/)の文字[コード](/glossary/コード/)を自動で直したり、読み込みを成功させたりする機能ではありません。

[yomitokuのIssue #147](https://github.com/kotaro-kinoshita/yomitoku/issues/147)には、Windows 11・Python 3.13で[設定ファイル](/glossary/設定ファイル/)の読み込みがcp932の[エラー](/glossary/エラー/)になり、`-X utf8`を付けた起動では動いたという報告があります。報告者は、内部の`open()`に[UTF-8](/glossary/utf-8/)指定がない点を原因候補として挙げています。すべての版で同じ問題が残っているとは扱いません。

## 読み込みエラーと書き込みエラーを区別する

`UnicodeDecodeError`は、[バイト](/glossary/バイト/)列を文字へ読み直す段階の失敗です。逆方向の、文字を指定した文字[コード](/glossary/コード/)の[バイト](/glossary/バイト/)列へ変える失敗は`UnicodeEncodeError`になります。[ファイル](/glossary/ファイル/)へ書くときや、表示先に文字を送るときの問題は、今回の読み込みとは確認箇所が異なります。

cp932の[ファイル](/glossary/ファイル/)を[UTF-8](/glossary/utf-8/)として読むと、逆に次のような[エラー](/glossary/エラー/)になる場合があります。

```text
UnicodeDecodeError: 'utf-8' codec can't decode byte 0x93 in position 0: invalid start byte
```

この表示は、今回の確認でcp932の「日本語」を[UTF-8](/glossary/utf-8/)として読んだ結果です。`encoding="utf-8"`は、[ファイル](/glossary/ファイル/)の中身を[UTF-8](/glossary/utf-8/)へ変換する指定ではありません。

`errors="ignore"`で読めない[バイト](/glossary/バイト/)を捨てたり、`errors="replace"`で置き換えたりすると、元の内容が失われます。処理を止めなくすることと、正しい内容を読むことは別です。元の文字を必要とするデータでは、文字[コード](/glossary/コード/)の不一致を先に直します。

## 解決手順のまとめ

[ファイル](/glossary/ファイル/)の保存元で文字[コード](/glossary/コード/)を確認し、Pythonが実際に選んだ`f.encoding`を調べます。[UTF-8](/glossary/utf-8/)なら`utf-8`、cp932なら`cp932`、BOM付き[UTF-8](/glossary/utf-8/)の目印を除きたい場合は`utf-8-sig`を指定します。

Pythonの既定値や地域設定だけに頼らず、[ファイル](/glossary/ファイル/)の[仕様](/glossary/仕様/)に合わせて指定してください。読み込み後には、日本語の内容やCSVの列名も確認します。

この記事の最小例は、[Linux](/glossary/linux/)上のCPython 3.12.14で文字[コード](/glossary/コード/)を明示して検証しました。[UTF-8](/glossary/utf-8/)の「あいうえお」をcp932で読むと、冒頭に掲載した`0x86`・位置8の[エラー](/glossary/エラー/)になりました。正しい指定による読み込み、逆方向の[エラー](/glossary/エラー/)、BOMの処理、例外なしの文字化け、`-X utf8`による有効化も確認しています。日本語Windowsの既定値での実行と、Python 3.15での実行は未検証です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の[仕様](/glossary/仕様/)は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
