---
title: "Docker Compose の .env 読み込みエラー：UTF-16 BOM問題と解決策"
date: 2026-05-30
description: "PowerShellのechoで.envを作成するとUTF-16 LE（BOM付き）になりDocker Composeが起動失敗する。原因と恒久的な回避策を解説します。"
tags: ["Docker Compose", "Docker"]
---

Windows環境でDocker Composeを使う際、PowerShellで作成した`.env`ファイルが原因でコンテナが起動できないケースがあります。エラーメッセージに`\xff\xfe`や`unexpected character`が含まれている場合、ファイルのエンコードが原因です。

## エラーの全文

```
failed to read C:\Users\user\project\.env: line 1: unexpected character "?" in variable name "\xff\xfeG\x00O\x00O\x00G\x00L\x00E\x00_\x00A\x00P\x00I\x00_\x00K\x00E\x00Y\x00=\x00A\x00I\x00z\x00a\x00..."
```

`\xff\xfe` はUTF-16 LEのBOM（Byte Order Mark）です。続く`\x00`が各文字の後ろに並んでいることから、ファイル全体がUTF-16 LEで保存されていることがわかります。Docker Composeのenvファイルパーサーは**UTF-8（BOMなし）のみ**を受け付けるため、このファイルを読み込もうとした瞬間にクラッシュします。

## よくある原因

### PowerShellのechoコマンドはUTF-16 LEで書き出す

WindowsのPowerShell（5.1系）では、リダイレクト演算子`>`や`echo`コマンドがデフォルトでUTF-16 LE（BOM付き）を使用します。

```powershell
# これをやってはいけない
echo GOOGLE_API_KEY=AIzaSy... > .env
# → .envがUTF-16 LE（BOM付き）で保存される
```

Linuxや macOSのシェルと違い、PowerShellは歴史的な経緯からUTF-16をデフォルトエンコードとして採用しています。`echo`や`Set-Content`を使う限り、意識しない限りこの問題が発生します。

### VSCodeのエンコード設定が変わっている場合

VSCodeでファイルを新規作成・保存する際、右下のステータスバーが「UTF-16 LE」になっているとDocker Composeが読めないファイルが生成されます。

## 診断方法

`.env`ファイルの先頭バイトを確認します。

```powershell
# 先頭4バイトを16進数で確認
$bytes = [System.IO.File]::ReadAllBytes(".env")
$bytes[0..3] | ForEach-Object { $_.ToString("X2") }
```

**正常（UTF-8 BOMなし）:**
```
47 4F 4F 47   ← "GOOG"の文字コード（例：GOOGLE_API_KEY=...）
```

**異常（UTF-16 LE BOM付き）:**
```
FF FE 47 00   ← \xff\xfe がBOM、その後\x00が混入
```

## 解決手順

### 方法1：既存の.envファイルをUTF-8に変換する（即時対応）

```powershell
# UTF-16で書かれた.envをUTF-8（BOMなし）に変換して上書き
$content = Get-Content ".env" -Encoding Unicode -Raw
[System.IO.File]::WriteAllText(
    (Resolve-Path ".env").Path,
    $content.Trim() + "`n",
    [System.Text.UTF8Encoding]::new($false)
)
```

`$false`は「BOMを付けない」を意味します。`UTF8Encoding::new($true)`にするとBOM付きになるため注意してください。

### 方法2：最初からUTF-8で.envを作成する（恒久対応）

```powershell
# Before（NGパターン）
echo GOOGLE_API_KEY=AIzaSy... > .env

# After（OKパターン）
[System.IO.File]::WriteAllText(
    "$PWD\.env",
    "GOOGLE_API_KEY=AIzaSy...`n",
    [System.Text.UTF8Encoding]::new($false)
)
```

複数の変数を書く場合はヒアストリングを使います。

```powershell
$envContent = @"
GOOGLE_API_KEY=AIzaSy...
DATABASE_URL=postgresql://...
DEBUG=false
"@
[System.IO.File]::WriteAllText(
    "$PWD\.env",
    $envContent,
    [System.Text.UTF8Encoding]::new($false)
)
```

### 方法3：VSCodeで修正する

1. `.env`をVSCodeで開く
2. 右下のステータスバーで現在のエンコードを確認（「UTF-16 LE」と表示されているはず）
3. クリックして「エンコード付きで保存」→「UTF-8」を選択

## Before / After の対比

**Before（問題のあるファイル）:**

```
バイト列: FF FE 47 00 4F 00 4F 00 47 00 4C 00 45 00 ...
文字列:   （BOM）G  O  O  G  L  E  ...（各文字の後ろに\x00が混入）
```

Docker Composeの起動結果:
```
failed to read .env: line 1: unexpected character "?" in variable name "\xff\xfeG\x00O\x00O\x00G\x00..."
```

**After（修正後のファイル）:**

```
バイト列: 47 4F 4F 47 4C 45 5F 41 50 49 5F 4B 45 59 ...
文字列:   G  O  O  G  L  E  _  A  P  I  _  K  E  Y  ...（クリーンなASCII）
```

Docker Composeの起動結果:
```
[+] Running 2/2
 ✔ Container app-backend   Started
 ✔ Container app-frontend  Started
```

## 根本的な対策：.gitattributesで管理する

チーム開発の場合、リポジトリに`.gitattributes`を追加することでエンコードを強制できます。

```gitattributes
# .gitattributes
.env*    text eol=lf
*.md     text eol=lf
*.py     text eol=lf
*.yml    text eol=lf
```

ただし`.env`はGit管理対象外（`.gitignore`に記載）にするのが一般的なので、あくまで`.env.example`などのテンプレートファイルに適用するのが現実的です。

## それでも解決しない場合

- **WSL2を経由する**: WSL2のシェル（bash/zsh）から`echo`でファイルを作成するとデフォルトがUTF-8になります
- **PowerShell 7以降に移行**: PowerShell 7（pwsh）はデフォルトエンコードがUTF-8に変わっています。`winget install Microsoft.PowerShell`でインストール可能です
- **docker composeではなくdocker-composeを使う**: 古いv1系は挙動が違うことがありますが、現在は非推奨のため根本解決にはなりません

---

*免責事項：本記事の内容は、執筆時点の公開情報をもとに作成したものです。ソフトウェアの仕様は予告なく変更されることがあります。最新の情報は各ツールの公式サポートページをご確認ください。本記事の情報を利用した結果生じたいかなる損害についても、著者および運営者は責任を負いかねます。*
