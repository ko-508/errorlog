"""
firebase_400.md の ❌/✅ コードコメント形式を
**Before/After** 段落形式に変換する。
"""
import re, os

PATH = os.path.join(os.path.dirname(__file__), "..", "content", "posts", "firebase_400.md")

with open(PATH, encoding="utf-8") as f:
    text = f.read()

# コードブロック全体にマッチ: ```lang\n// ❌ ...\n...\n```
# → **Before（...）：**\n\n```lang\n...\n```
def replace_block(m):
    lang    = m.group(1)          # javascript / bash / ""
    comment = m.group(2).strip()  # ❌ or ✅ コメント行（// や # 除去済み）
    body    = m.group(3)          # 残りのコード本文

    # ❌ → Before ラベル
    if "❌" in comment:
        label_text = re.sub(r"[❌✅]\s*", "", comment).strip()
        label_text = re.sub(r"^エラーになる例[：:]\s*", "", label_text).strip()
        label = f"**Before（エラーが起きるコード）：**" if not label_text else \
                f"**Before（{label_text}）：**"
        body_clean = body.rstrip("\n")
        return f"{label}\n\n```{lang}\n{body_clean}\n```"

    # ✅ → After ラベル
    if "✅" in comment:
        label = "**After（修正後）：**"
        body_clean = body.rstrip("\n")
        return f"{label}\n\n```{lang}\n{body_clean}\n```"

    return m.group(0)  # 変更なし

# パターン: ```lang\n// ❌/✅ ...\n<code>\n```
# コメント行は // or # で始まる
pattern = re.compile(
    r"```([\w]*)\n"                          # ```lang
    r"(?://|#) ([❌✅][^\n]*)\n"             # // ❌... or # ❌...
    r"((?:(?!```).|\n)*?)"                  # コード本文（非貪欲）
    r"```",
    re.DOTALL
)

new_text = pattern.sub(replace_block, text)

with open(PATH, "w", encoding="utf-8") as f:
    f.write(new_text)

# 変換数を確認
n = len(pattern.findall(text))
print(f"変換対象ブロック数: {n}")
print("Done.")
