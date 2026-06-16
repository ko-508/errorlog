"""daily_publish.py の pending_articles.json フロー（生成5本・公開最大3本・保留管理）の検証スクリプト。

検証する内容:
  (a) 保留0件の状態で5本生成 → 3本公開・2本保留になること
  (b) 保留2件がある状態で実行 → 保留2件が先に公開され、残り1枠が新規生成で埋まること
  (c) 保留6件（PENDING_SKIP_THRESHOLD以上）の状態 → 新規生成がスキップされること
  (d) 各シナリオで公開済みファイルと保留データの間に二重公開・取りこぼしがないこと

実際の Anthropic API・lint gate・fact-check gate は呼ばない。daily_publish._try_generate_article
をスタブに置き換え、生成・検査が常に成功する前提でフロー制御ロジック（公開件数・保留件数・
生成スキップ判定）のみを検証する。一時ディレクトリ上で POSTS_DIR / QUEUE_PATH / PENDING_PATH /
BASE を差し替えて実行するため、本番の content/posts・queue.csv・data/pending_articles.json には
一切影響しない。

実行方法:
  python scripts/_test_pending_flow.py

daily_publish.py の生成・公開フローを変更した際の回帰確認に再利用できる。
"""
import csv
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("ANTHROPIC_API_KEY", "dummy-test-key")

sys.path.insert(0, str(Path(__file__).parent))
import daily_publish as dp

PASS = []
FAIL = []


def check(label: str, cond: bool, detail: str = ""):
    if cond:
        PASS.append(label)
        print(f"  [OK] {label}")
    else:
        FAIL.append(label)
        print(f"  [NG] {label}  {detail}")


def make_env(tmp: Path, queue_rows: list[dict], pending: list[dict], existing_posts: list[str] | None = None):
    posts_dir = tmp / "content" / "posts"
    posts_dir.mkdir(parents=True, exist_ok=True)
    data_dir = tmp / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    queue_path = tmp / "scripts" / "queue.csv"
    queue_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ["tool", "status_code", "official_meaning", "causes", "solutions"]
    with open(queue_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(queue_rows)

    pending_path = data_dir / "pending_articles.json"
    pending_path.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")

    for name in (existing_posts or []):
        (posts_dir / name).write_text(f"---\ntitle: \"x\"\ndate: {dp.date.today().isoformat()}\n---\nx", encoding="utf-8")

    dp.BASE = tmp / "scripts"
    dp.POSTS_DIR = posts_dir
    dp.QUEUE_PATH = queue_path
    dp.PENDING_PATH = pending_path
    return posts_dir, queue_path, pending_path


def queue_rows(n: int, prefix="tool"):
    return [
        {
            "tool": f"{prefix}{i}",
            "status_code": "400",
            "official_meaning": "テスト用の意味説明文がここに入ります。",
            "causes": "原因A|原因B|原因C",
            "solutions": "解決策A|解決策B",
        }
        for i in range(1, n + 1)
    ]


def pending_entry(name: str, today_placeholder=True):
    date_val = dp.DATE_PLACEHOLDER if today_placeholder else "2026-01-01"
    return {
        "filename": f"{name}.md",
        "title": f"{name} test",
        "stem": name,
        "article_content": f"---\ntitle: \"{name}\"\ndate: {date_val}\n---\n\nbody of {name}",
        "tool": name,
        "status_code": "400",
        "staged_at": "2026-01-01",
    }


def make_stub_generator(success_filenames: list[str]):
    """呼ばれた順に success_filenames を使った成功エントリを返すスタブ。全件成功・critical無し。"""
    state = {"i": 0}

    def stub(client, row, remaining, today):
        i = state["i"]
        state["i"] += 1
        name = success_filenames[i] if i < len(success_filenames) else f"{row['tool']}_{row['status_code']}"
        entry = {
            "filename": f"{name}.md",
            "title": f"{name} test",
            "stem": name,
            "article_content": f"---\ntitle: \"{name}\"\ndate: {dp.DATE_PLACEHOLDER}\n---\n\nbody of {name}",
            "tool": row["tool"],
            "status_code": row["status_code"],
            "staged_at": today,
        }
        return entry, False

    return stub


def scenario_a():
    print("\n=== シナリオ(a): 保留0件、5本生成 → 3本公開・2本保留 ===")
    tmp = Path(tempfile.mkdtemp(prefix="el_test_a_"))
    try:
        posts_dir, queue_path, pending_path = make_env(tmp, queue_rows(5), pending=[])
        orig = dp._try_generate_article
        dp._try_generate_article = make_stub_generator([f"gen{i}" for i in range(1, 6)])
        try:
            dp.main()
        finally:
            dp._try_generate_article = orig

        posts = sorted(p.name for p in posts_dir.glob("*.md"))
        pending_after = json.loads(pending_path.read_text(encoding="utf-8"))
        session = json.loads((tmp / "data" / "publish_session.json").read_text(encoding="utf-8"))

        check("公開ファイル数が3件", len(posts) == 3, f"actual={posts}")
        check("保留が2件", len(pending_after) == 2, f"actual={len(pending_after)}")
        check("publish_session.jsonの件数が3件", len(session) == 3, f"actual={len(session)}")
        check(
            "公開ファイルと保留ファイル名が重複していない",
            not (set(p[:-3] for p in posts) & set(e["filename"][:-3] for e in pending_after)),
        )
        for p in posts:
            content = (posts_dir / p).read_text(encoding="utf-8")
            check(f"{p}: dateが確定済み(placeholderが残っていない)", dp.DATE_PLACEHOLDER not in content)
        return tmp, posts_dir, pending_path
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def scenario_b():
    print("\n=== シナリオ(b): 保留2件が先に公開され、残り1枠が新規生成で埋まる ===")
    tmp = Path(tempfile.mkdtemp(prefix="el_test_b_"))
    try:
        pending_pre = [pending_entry("pend1"), pending_entry("pend2")]
        posts_dir, queue_path, pending_path = make_env(tmp, queue_rows(5), pending=pending_pre)
        orig = dp._try_generate_article
        dp._try_generate_article = make_stub_generator([f"gen{i}" for i in range(1, 6)])
        try:
            dp.main()
        finally:
            dp._try_generate_article = orig

        posts = sorted(p.name for p in posts_dir.glob("*.md"))
        pending_after = json.loads(pending_path.read_text(encoding="utf-8"))
        session = json.loads((tmp / "data" / "publish_session.json").read_text(encoding="utf-8"))

        check("公開ファイル数が3件(保留2+新規1)", len(posts) == 3, f"actual={posts}")
        check("公開された記事に保留分(pend1,pend2)が含まれる", {"pend1.md", "pend2.md"}.issubset(set(posts)))
        check("保留が4件に増えている(0+4個新規分が積み上がる)", len(pending_after) == 4, f"actual={len(pending_after)}")
        check(
            "公開ファイルと保留ファイル名が重複していない",
            not (set(p[:-3] for p in posts) & set(e["filename"][:-3] for e in pending_after)),
        )
        pending_sources = [a for a in session if a["source_type"] == "pending"]
        daily_sources = [a for a in session if a["source_type"] == "daily"]
        check("publish_session.jsonでpending起源が2件", len(pending_sources) == 2, f"actual={len(pending_sources)}")
        check("publish_session.jsonでdaily起源が1件", len(daily_sources) == 1, f"actual={len(daily_sources)}")
        return tmp
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def scenario_c():
    print("\n=== シナリオ(c): 保留6件 → 新規生成がスキップされる ===")
    tmp = Path(tempfile.mkdtemp(prefix="el_test_c_"))
    try:
        pending_pre = [pending_entry(f"pend{i}") for i in range(1, 7)]
        posts_dir, queue_path, pending_path = make_env(tmp, queue_rows(5), pending=pending_pre)
        call_count = {"n": 0}
        orig = dp._try_generate_article

        def counting_stub(client, row, remaining, today):
            call_count["n"] += 1
            return None, False

        dp._try_generate_article = counting_stub
        try:
            dp.main()
        finally:
            dp._try_generate_article = orig

        posts = sorted(p.name for p in posts_dir.glob("*.md"))
        pending_after = json.loads(pending_path.read_text(encoding="utf-8"))

        check("新規生成が一度も呼ばれていない(スキップ確認)", call_count["n"] == 0, f"calls={call_count['n']}")
        check("保留からの公開が3件(枠の上限まで)", len(posts) == 3, f"actual={posts}")
        check("保留の残数が3件(6-3)", len(pending_after) == 3, f"actual={len(pending_after)}")
        check(
            "queue.csvが変更されていない(新規生成しなかったため)",
            queue_path.read_text(encoding="utf-8") == _rows_to_csv(queue_rows(5)),
        )
        return tmp
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def _rows_to_csv(rows):
    import io
    buf = io.StringIO()
    fieldnames = ["tool", "status_code", "official_meaning", "causes", "solutions"]
    w = csv.DictWriter(buf, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().replace("\r\n", "\n")


if __name__ == "__main__":
    tmp_dirs = []
    try:
        tmp_dirs.append(scenario_a()[0])
        tmp_dirs.append(scenario_b())
        tmp_dirs.append(scenario_c())
    finally:
        for t in tmp_dirs:
            shutil.rmtree(t, ignore_errors=True)

    print(f"\n=== 結果: PASS={len(PASS)} FAIL={len(FAIL)} ===")
    if FAIL:
        print("失敗項目:", FAIL)
        sys.exit(1)
