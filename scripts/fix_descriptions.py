"""
全記事の description を「エラーの概要」冒頭文に置き換える。
- マークダウンリンク・記号を除去してプレーンテキスト化
- 2文まで・最大 120 文字でトリミング
- 既に固有の説明が書かれている記事はスキップ
"""
import os
import re

POSTS_DIR = os.path.join(os.path.dirname(__file__), "..", "content", "posts")
GENERIC_PATTERN = re.compile(r"^.{0,20}の\s*\d+\s*エラーの原因と解決策")

def strip_md(text: str) -> str:
    """マークダウン記法を除去してプレーンテキスト化"""
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)   # [text](url) → text
    text = re.sub(r"`([^`]+)`", r"\1", text)                # `code` → code
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)          # **bold** → bold
    text = re.sub(r"\*([^*]+)\*", r"\1", text)              # *italic* → italic
    text = re.sub(r"\s+", " ", text).strip()
    return text

def extract_overview(body: str) -> str:
    """「エラーの概要」セクションの冒頭 1〜2 文を抽出"""
    m = re.search(r"##\s*エラーの概要\s*\n+(.+?)(?:\n\n|\n##)", body, re.DOTALL)
    if not m:
        # 概要セクションがない場合は本文の最初の段落
        paras = [p.strip() for p in body.split("\n\n") if p.strip() and not p.startswith("#")]
        raw = paras[0] if paras else ""
    else:
        raw = m.group(1).strip()

    # 複数段落がある場合は最初の段落だけ
    raw = raw.split("\n\n")[0]
    # 改行を除去
    raw = raw.replace("\n", " ")
    text = strip_md(raw)

    # 句点で 2 文まで
    sentences = re.split(r"(?<=[。！？])", text)
    result = "".join(sentences[:2]).strip()

    # 120 文字上限（句点で切り捨て）
    if len(result) > 120:
        m2 = re.search(r"^.{60,120}[。！？]", result)
        result = m2.group(0) if m2 else result[:120]

    return result

def fix_file(path: str) -> bool:
    with open(path, encoding="utf-8") as f:
        raw = f.read()

    if not raw.startswith("---"):
        return False

    parts = raw.split("---", 2)
    if len(parts) < 3:
        return False

    fm_str, body = parts[1], parts[2]

    # 現在の description を取得
    m = re.search(r'^description:\s*"([^"]*)"', fm_str, re.MULTILINE)
    if not m:
        m = re.search(r"^description:\s*'([^']*)'", fm_str, re.MULTILINE)
    if not m:
        return False

    current_desc = m.group(1)

    # 固有の説明がある場合はスキップ
    if not GENERIC_PATTERN.match(current_desc) and len(current_desc) > 40:
        return False

    new_desc = extract_overview(body)
    if not new_desc or len(new_desc) < 15:
        return False

    # description フィールドを置換
    new_fm = re.sub(
        r'^(description:\s*)"[^"]*"',
        lambda _: f'description: "{new_desc}"',
        fm_str,
        flags=re.MULTILINE,
    )
    if new_fm == fm_str:
        # シングルクォート版も試す
        new_fm = re.sub(
            r"^(description:\s*)'[^']*'",
            lambda _: f'description: "{new_desc}"',
            fm_str,
            flags=re.MULTILINE,
        )

    if new_fm == fm_str:
        return False

    with open(path, "w", encoding="utf-8") as f:
        f.write(f"---{new_fm}---{body}")

    return True

if __name__ == "__main__":
    updated = []
    skipped = []

    for fname in sorted(os.listdir(POSTS_DIR)):
        if not fname.endswith(".md"):
            continue
        path = os.path.join(POSTS_DIR, fname)
        if fix_file(path):
            updated.append(fname)
        else:
            skipped.append(fname)

    print(f"Updated : {len(updated)}")
    print(f"Skipped : {len(skipped)}")
    for f in updated:
        print(f"  ✓ {f}")
