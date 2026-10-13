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

PythonでテキストやCSVを読んだとき、次のエラーが出ることがあります。

```text
UnicodeDecodeError: 'cp932' codec can't decode byte 0x86 in position 8: illegal multibyte sequence
```

Pythonがcp932という文字コードで読もうとして、その規則では読めないバイト列に当たっています。UTF-8で保存されたファイルなら、読み込み側にもUTF-8を指定します。

```python
with open("data.txt", encoding="utf-8") as f:
    text = f.read()
```

ただし、エラーに`cp932`と出ることは、ファイル自体がUTF-8である証拠ではありません。保存元の設定やファイルの仕様を確認して、実際の文字コードに合わせてください。

## cp932とファイルの文字コードが合っていない

文字コードは、文字と保存されたバイト列を対応させる規則です。cp932は日本語のWindowsで使われる文字コードの一つです。UTF-8とは異なる規則なので、UTF-8の内容をcp932として読むと失敗したり、文字化けしたりします。

[Python 3.14のio公式文書](https://docs.python.org/3.14/library/io.html#text-encoding)は、文字コードを指定しないテキスト読み込みが地域設定に依存すること、UTF-8のファイルをそのまま開くとWindowsで問題になり得ることを説明しています。UTF-8モードが有効なら、既定値はUTF-8になります。

エラーの各部分は次を示します。

| 表示 | 確認できる内容 |
|---|---|
| `'cp932' codec` | 読み込みに使われた文字コード |
| `byte 0x86` | 問題になったバイトの値 |
| `position 8` | 例外の対象となったバイト列内の位置 |
| `illegal multibyte sequence` | cp932として不正な並び |
| `incomplete multibyte sequence` | 複数バイトで表す文字の並びが途中で終わっている |

位置は行番号ではありません。テキスト読み込みで内部のバッファを処理している場合、ファイル全体の先頭からの位置とも限りません。値や位置は内容によって変わります。

また、今回の確認では、UTF-8の「日本」をcp932で読むと、例外を出さず「譌･譛ｬ」になりました。エラーが出ないことだけでは、正しく読めたと判断できません。

## 保存元と実際の読み込み設定を確認する

エディターの保存設定、出力した道具の仕様、ファイルを提供した側の説明で、UTF-8なのかcp932なのかを確認します。エディターが表示する推定値は、保存仕様そのものとは区別してください。

Python側は、エラーが出る同じ実行環境で確認します。

```python
import sys

print(sys.version)
print(sys.executable)
print(sys.flags.utf8_mode)

with open("data.txt") as f:
    print(f.encoding)
```

最後の例は読み込み前に、実際に選ばれた文字コードを表示します。`sys.flags.utf8_mode`が1ならUTF-8モードが有効です。

Python 3.11以降なら、地域設定の文字コードも調べられます。

```python
import locale
print(locale.getencoding())
```

[localeの公式文書](https://docs.python.org/3.14/library/locale.html#locale.getencoding)によると、WindowsではANSIコードページを返します。ただし、この関数はUTF-8モードを無視します。返り値がcp932でも、文字コード未指定の`open()`がUTF-8を使う場合があります。`f.encoding`と合わせて確認してください。

## UTF-8とcp932を明示して読み込む

保存元がUTF-8と確認できたら、`encoding="utf-8"`を指定します。CSVも、標準のcsvモジュールならファイルを開く箇所で指定できます。

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

cp932とPythonの`shift_jis`は、すべての文字について同じものではありません。Windows由来のファイルがcp932として出力されたなら、その指定に合わせます。

pandasなど別のライブラリで読む場合は、その読み込み関数の仕様を確認してください。標準の`open()`の既定値が、すべてのライブラリにもそのまま当てはまるとは限りません。

[Pythonのcodecs公式文書](https://docs.python.org/3/library/codecs.html)は、外部の情報なしに文字コードを確実に判定することはできないと説明しています。読めるまで指定を変えるだけでなく、読んだ日本語や列名が元の内容と一致するか確認します。

## BOM付きUTF-8ならutf-8-sigを使う

UTF-8のファイルの先頭に、BOMという目印が付いている場合があります。UTF-8のBOMは、先頭の3バイト`EF BB BF`です。

`encoding="utf-8"`で読むと、その目印は文字`U+FEFF`として残ります。CSVでは最初の列名に目に見えない文字が付いて、期待した列名と一致しないことがあります。

保存元がBOM付きUTF-8なら、次を使えます。

```python
import csv

with open("data.csv", encoding="utf-8-sig", newline="") as f:
    for row in csv.reader(f):
        print(row)
```

[codecsのutf-8-sigの説明](https://docs.python.org/3/library/codecs.html#encodings-and-unicode)は、読み込み時に先頭のBOMを取り除くと説明しています。BOMがなければ、通常のUTF-8として読み込みます。cp932やUTF-16のファイルを読むための万能な指定ではありません。

この記事では、同じBOM付きファイルを`utf-8`で読むと先頭に`U+FEFF`が残り、`utf-8-sig`で読むと取り除かれることを確認しました。

## UTF-8モードとPython 3.15の変更

自分のコードを変更できるなら、ファイルの仕様に合った`encoding`を明示します。依存する道具の内部で文字コード未指定の`open()`が使われている場合は、UTF-8モードが役立つこともあります。

```bat
python -X utf8 read.py
```

[Pythonの起動オプションの公式文書](https://docs.python.org/3.14/using/cmdline.html)は、`-X utf8`でUTF-8モードを有効にできると説明しています。この指定はPython 3.7以降で使えます。明示された`encoding="cp932"`を上書きするものではありません。

[Python 3.15の変更点](https://docs.python.org/3.15/whatsnew/3.15.html)では、UTF-8モードが既定で有効となり、文字コード未指定の`open()`がUTF-8を使うと説明されています。`PYTHONUTF8=0`や`-X utf8=0`で無効にすると、地域設定に依存する動作へ戻ります。

そのため、3.15への更新だけを解決策にすると、今度は文字コード未指定で読んでいたcp932のファイルが読めなくなる可能性があります。UTF-8のファイルにはUTF-8、cp932のファイルにはcp932を明示する方法なら、既定値の変更に左右されません。

文字コード未指定の箇所を探すには、Python 3.10以降で次を使えます。

```bat
python -X warn_default_encoding read.py
```

これにより`EncodingWarning`を出せます。警告は、ファイルの文字コードを自動で直したり、読み込みを成功させたりする機能ではありません。

[yomitokuのIssue #147](https://github.com/kotaro-kinoshita/yomitoku/issues/147)には、Windows 11・Python 3.13で設定ファイルの読み込みがcp932のエラーになり、`-X utf8`を付けた起動では動いたという報告があります。報告者は、内部の`open()`にUTF-8指定がない点を原因候補として挙げています。すべての版で同じ問題が残っているとは扱いません。

## 読み込みエラーと書き込みエラーを区別する

`UnicodeDecodeError`は、バイト列を文字へ読み直す段階の失敗です。逆方向の、文字を指定した文字コードのバイト列へ変える失敗は`UnicodeEncodeError`になります。ファイルへ書くときや、表示先に文字を送るときの問題は、今回の読み込みとは確認箇所が異なります。

cp932のファイルをUTF-8として読むと、逆に次のようなエラーになる場合があります。

```text
UnicodeDecodeError: 'utf-8' codec can't decode byte 0x93 in position 0: invalid start byte
```

この表示は、今回の確認でcp932の「日本語」をUTF-8として読んだ結果です。`encoding="utf-8"`は、ファイルの中身をUTF-8へ変換する指定ではありません。

`errors="ignore"`で読めないバイトを捨てたり、`errors="replace"`で置き換えたりすると、元の内容が失われます。処理を止めなくすることと、正しい内容を読むことは別です。元の文字を必要とするデータでは、文字コードの不一致を先に直します。

## 解決手順のまとめ

ファイルの保存元で文字コードを確認し、Pythonが実際に選んだ`f.encoding`を調べます。UTF-8なら`utf-8`、cp932なら`cp932`、BOM付きUTF-8の目印を除きたい場合は`utf-8-sig`を指定します。

Pythonの既定値や地域設定だけに頼らず、ファイルの仕様に合わせて指定してください。読み込み後には、日本語の内容やCSVの列名も確認します。

この記事の最小例は、Linux上のCPython 3.12.14で文字コードを明示して検証しました。UTF-8の「あいうえお」をcp932で読むと、冒頭に掲載した`0x86`・位置8のエラーになりました。正しい指定による読み込み、逆方向のエラー、BOMの処理、例外なしの文字化け、`-X utf8`による有効化も確認しています。日本語Windowsの既定値での実行と、Python 3.15での実行は未検証です。

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。[ソフトウェア](/glossary/ソフトウェア/)の仕様は予告なく変更されることがあります。最新の情報は各[ツール](/glossary/ツール/)の公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
