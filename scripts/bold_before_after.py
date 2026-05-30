"""
plain-text の Before/After ラベルを **bold** に変換する。
対象ファイルと置換パターンを明示的に列挙して安全に処理する。
"""
import os, re

POSTS = os.path.join(os.path.dirname(__file__), "..", "content", "posts")

# (ファイル名, [(old, new), ...])
TARGETS = [
    ("aws_429.md", [
        ("Before（エラーが起きるコード）：",      "**Before（エラーが起きるコード）：**"),
        ("Before（エラーが起きる設定）：",         "**Before（エラーが起きる設定）：**"),
        ("After（修正後：[リクエスト](/glossary/リクエスト/)制限の引き上げ）：",
         "**After（修正後：[リクエスト](/glossary/リクエスト/)制限の引き上げ）：**"),
        ("After（修正後）：",                      "**After（修正後）：**"),
    ]),
    ("firebase_404.md", [
        ("Before（エラーが発生するコード）:",       "**Before（エラーが発生するコード）:**"),
        ("Before（エラーが発生する呼び出し）:",     "**Before（エラーが発生する呼び出し）:**"),
        ("Before（エラーが発生）:",                 "**Before（エラーが発生）:**"),
        ("After（修正後）:",                        "**After（修正後）:**"),
        ("After（事前に初期化）:",                  "**After（事前に初期化）:**"),
    ]),
    ("github_api_504.md", [
        ("Before（エラーが起きる実装）：",          "**Before（エラーが起きる実装）：**"),
        ("Before（[認証](/glossary/認証/)エラーの実装）：",
         "**Before（[認証](/glossary/認証/)エラーの実装）：**"),
        ("Before（並列[リクエスト](/glossary/リクエスト/)で504になる実装）：",
         "**Before（並列[リクエスト](/glossary/リクエスト/)で504になる実装）：**"),
        ("After（[リクエスト](/glossary/リクエスト/)を制御する修正）：",
         "**After（[リクエスト](/glossary/リクエスト/)を制御する修正）：**"),
        ("After（修正後）：",                       "**After（修正後）：**"),
    ]),
    ("stripe_400.md", [
        ("Before（エラーが起きるコード）:",         "**Before（エラーが起きるコード）:**"),
        ("After（修正後）:",                        "**After（修正後）:**"),
    ]),
    ("stripe_401.md", [
        ("Before：",                               "**Before（エラーが起きるコード）：**"),
        ("After：",                                "**After（修正後）：**"),
    ]),
    ("stripe_404.md", [
        ("Before（エラーが起きるコード）：",        "**Before（エラーが起きるコード）：**"),
        ("After（修正後）：",                       "**After（修正後）：**"),
    ]),
]

for fname, pairs in TARGETS:
    path = os.path.join(POSTS, fname)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    for old, new in pairs:
        count = text.count(old)
        text = text.replace(old, new)
        print(f"{fname}: '{old[:30]}' -> {count}箇所")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

print("Done.")
