"""inspect_index_status.py のテスト（模擬の API と Git。通信なし）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import inspect_index_status as iis  # noqa: E402

SITE = "https://errorlog.jp/"


class _Req:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    def execute(self):
        if self.error is not None:
            raise self.error
        return self.result


class FakeService:
    def __init__(self, inspections: dict, sitemap_error: Exception | None = None):
        self.inspections = inspections
        self.sitemap_error = sitemap_error
        self.inspected: list[str] = []

    def sites(self):
        class _S:
            def list(self_inner):
                return _Req({"siteEntry": [{"siteUrl": SITE, "permissionLevel": "siteOwner"}]})
        return _S()

    def sitemaps(self):
        svc = self

        class _SM:
            def list(self_inner, siteUrl):
                return _Req(error=svc.sitemap_error) if svc.sitemap_error else _Req({"sitemap": [{"path": iis.SITEMAP_URL, "lastDownloaded": "2026-10-01T00:00:00Z"}]})

            def get(self_inner, siteUrl, feedpath):
                return _Req({"path": feedpath, "lastSubmitted": "2026-10-07T04:17:54Z", "lastDownloaded": "2026-10-01T00:00:00Z",
                             "isPending": False, "warnings": 0, "errors": 0,
                             "contents": [{"type": "web", "submitted": 900, "indexed": 0}]})
        return _SM()

    def urlInspection(self):
        svc = self

        class _UI:
            def index(self_inner):
                class _Idx:
                    def inspect(self_idx, body):
                        url = body["inspectionUrl"]
                        svc.inspected.append(url)
                        value = svc.inspections[url]
                        return _Req(error=value) if isinstance(value, Exception) else _Req(value)
                return _Idx()
        return _UI()


def _git_factory(history: dict[str, list[tuple[str, str, bool]]]):
    """history: stem -> [(sha, iso_time, is_draft)]"""
    contents = {}
    for stem, commits in history.items():
        for sha, _when, draft in commits:
            contents[(sha, stem)] = f"---\ntitle: \"x\"\ndraft: {'true' if draft else 'false'}\n---\nbody\n"

    def git(args):
        if args[0] == "log":
            stem = Path(args[-1]).stem
            return "\n".join(f"{sha}\t{when}" for sha, when, _ in history.get(stem, []))
        if args[0] == "show":
            sha, path = args[1].split(":", 1)
            return contents[(sha, Path(path).stem)]
        raise AssertionError(args)
    return git


@pytest.fixture
def repo(tmp_path, monkeypatch):
    posts = tmp_path / "content" / "posts"
    posts.mkdir(parents=True)
    for stem, draft in (("old", False), ("new_a", False), ("new_b", False), ("hidden", True), ("nohist", False)):
        (posts / f"{stem}.md").write_text(f"---\ntitle: \"x\"\ndraft: {'true' if draft else 'false'}\n---\n", encoding="utf-8")
    monkeypatch.setattr(iis, "BASE", tmp_path)
    monkeypatch.setattr(iis, "INSPECT_INTERVAL_S", 0)
    monkeypatch.setenv("GSC_SITE_URL", SITE)
    history = {
        "old": [("a1", "2026-05-24T10:00:00+09:00", False)],
        # date 欄に関係なく、draft でない最初の commit を初回公開とする
        "new_a": [("b1", "2026-06-20T10:00:00+09:00", True), ("b2", "2026-08-05T10:00:00+09:00", False)],
        "new_b": [("c1", "2026-09-18T10:00:00+09:00", False)],
        "hidden": [("d1", "2026-09-01T10:00:00+09:00", True)],
        "nohist": [],
    }
    return tmp_path, _git_factory(history)


def test_targets_use_first_non_draft_commit_and_separate_unresolved(repo):
    _, git = repo
    targets, unresolved = iis.select_targets("2026-07-01", git)
    assert [t["stem"] for t in targets] == ["new_a", "new_b"]
    assert targets[0]["first_published_at"].startswith("2026-08-05")
    assert [u["stem"] for u in unresolved] == ["nohist"]


def _ok(coverage, **extra):
    status = {"verdict": "NEUTRAL", "coverageState": coverage, "pageFetchState": "PAGE_FETCH_STATE_UNSPECIFIED"}
    status.update(extra)
    return {"inspectionResult": {"indexStatusResult": status, "inspectionResultLink": "https://search.google.com/x"}}


def test_full_run_records_results_missing_fields_and_failures(repo, tmp_path):
    from google.auth.exceptions import RefreshError

    _, git = repo
    url_a = "https://errorlog.jp/posts/new_a/"
    url_b = "https://errorlog.jp/posts/new_b/"
    service = FakeService({
        url_a: _ok("Discovered - currently not indexed"),
        url_b: RefreshError("unauthorized_client"),
    })
    out = tmp_path / "out"
    code = iis.main(["--since", "2026-07-01", "--out-dir", str(out)], service=service, git=git)
    assert code == 1  # 失敗した URL があるので失敗で終わる
    payload = json.loads((out / "index_status.json").read_text(encoding="utf-8"))
    by_url = {r["url"]: r for r in payload["results"]}
    a = by_url[url_a]
    assert a["status"] == "ok"
    assert a["lastCrawlTime"] is None and "lastCrawlTime" in a["missing_fields"]
    assert a["googleCanonical"] is None and "googleCanonical" in a["missing_fields"]
    b = by_url[url_b]
    assert b["status"] == "failed" and b["error_kind"] == "auth"
    assert "coverageState" not in b  # 失敗を「未登録」として記録しない
    summary = payload["summary"]
    assert summary["fetch_status"] == {"ok": 1, "failed": 1}
    assert summary["coverageState"] == {"Discovered - currently not indexed": 1}
    assert summary["canonical_match"] == {"unknown": 2}
    # サイトマップ: indexed（非推奨）は保存しない
    assert payload["sitemaps"]["detail"]["contents"] == [{"type": "web", "submitted": 900}]
    assert payload["sitemaps"]["detail"]["lastDownloaded"] == "2026-10-01T00:00:00Z"
    assert (out / "index_status.csv").exists()


def test_limit_inspects_only_first_targets(repo, tmp_path):
    _, git = repo
    service = FakeService({"https://errorlog.jp/posts/new_a/": _ok("Submitted and indexed",
                                                                     googleCanonical="https://errorlog.jp/posts/new_a/",
                                                                     userCanonical="https://errorlog.jp/posts/new_a/",
                                                                     lastCrawlTime="2026-10-01T00:00:00Z")})
    out = tmp_path / "out"
    code = iis.main(["--since", "2026-07-01", "--limit", "1", "--out-dir", str(out)], service=service, git=git)
    assert code == 0
    assert service.inspected == ["https://errorlog.jp/posts/new_a/"]
    payload = json.loads((out / "index_status.json").read_text(encoding="utf-8"))
    assert payload["summary"]["canonical_match"] == {"same": 1}
    assert payload["targets_total"] == 2 and payload["inspected"] == 1


def test_google_canonical_outside_site_is_listed(repo, tmp_path):
    _, git = repo
    zenn = "https://zenn.dev/errorlog/articles/el-new-a"
    service = FakeService({"https://errorlog.jp/posts/new_a/": _ok("Duplicate, Google chose different canonical than user",
                                                                     googleCanonical=zenn,
                                                                     userCanonical="https://errorlog.jp/posts/new_a/")})
    out = tmp_path / "out"
    iis.main(["--since", "2026-07-01", "--limit", "1", "--out-dir", str(out)], service=service, git=git)
    payload = json.loads((out / "index_status.json").read_text(encoding="utf-8"))
    assert payload["summary"]["google_canonical_not_errorlog"] == [{"url": "https://errorlog.jp/posts/new_a/", "googleCanonical": zenn}]
    assert payload["summary"]["canonical_match"] == {"different": 1}


def test_sitemap_failure_is_recorded_not_zero(repo, tmp_path):
    from google.auth.exceptions import RefreshError

    _, git = repo
    service = FakeService({"https://errorlog.jp/posts/new_a/": _ok("Submitted and indexed")}, sitemap_error=RefreshError("unauthorized_client"))
    out = tmp_path / "out"
    code = iis.main(["--since", "2026-07-01", "--limit", "1", "--out-dir", str(out)], service=service, git=git)
    assert code == 1
    payload = json.loads((out / "index_status.json").read_text(encoding="utf-8"))
    assert payload["sitemaps"]["status"] == "failed"
    assert "detail" not in payload["sitemaps"]
