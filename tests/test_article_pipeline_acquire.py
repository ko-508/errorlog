from __future__ import annotations

import json
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.article_pipeline import PipelineError
from scripts.article_pipeline.acquire import Acquirer, reuse_config_hash
from scripts.article_pipeline.github import git_blob_sha
from scripts.article_pipeline.net import FetchResult, NetFailure
from scripts.article_pipeline.store import RunStore
from tests.article_pipeline_helpers import CONFIG, RepoCase


def acquire_config(**updates):
    value = json.loads(CONFIG)["acquire"]
    value.update({"min_text_chars": 1, **updates})
    return value


def result(url, *, status=200, body=b"fixed source text", headers=None, attempts=None):
    return FetchResult(
        url=url,
        final_url=url,
        redirects=[],
        resolved_ip="93.184.216.34",
        http_status=status,
        headers=headers or {"content-type": "text/plain; charset=utf-8"},
        body=body,
        attempts=attempts or [{"result": "ok"}],
    )


class FakeClient:
    def __init__(self, values):
        self.values = {key: deque(items) for key, items in values.items()}
        self.calls = []
        self.call_kwargs = []

    def fetch(self, url, **kwargs):
        self.calls.append((url, kwargs.get("headers", {})))
        self.call_kwargs.append(kwargs)
        if url not in self.values or not self.values[url]:
            raise AssertionError(f"unexpected request: {url}")
        value = self.values[url].popleft()
        if isinstance(value, Exception):
            raise value
        return value


def url_candidate(source_id, key, path, *, role="official_doc", anchor=None):
    return {
        "source_id": source_id,
        "candidate_key": key,
        "kind": "url",
        "url": f"https://example.com/{path}",
        "anchor": anchor,
        "role_hint": role,
        "origins": ["url_candidates"],
    }


class TestAcquire(RepoCase):
    def setUp(self):
        super().setUp()
        self.store = RunStore(self.root)
        self.run_id = "run-fixed"

    def acquirer(self, client, *, config=None, previous_root=None, refetch=None, mode="candidate"):
        return Acquirer(
            store=self.store,
            run_id=self.run_id,
            mode=mode,
            slug="sample_error",
            config=config or acquire_config(),
            client=client,
            refetch=refetch,
            previous_root=previous_root,
            previous_quarantined=False,
        )

    def test_url_source_stages_manifest_and_all_failed_still_finalizes(self):
        candidate = url_candidate("S001", "sha256:a", "doc")
        client = FakeClient(
            {
                "https://example.com/robots.txt": [result("https://example.com/robots.txt", status=404, body=b"")],
                candidate["url"]: [result(candidate["url"])],
            }
        )
        index = self.acquirer(client).run({"schema": "research_plan/v1", "candidates": [candidate]})
        assert index["summary"]["fetched"] == 1
        assert not self.store.exists(Path("runs") / self.run_id / "sources.staging")
        assert self.store.exists(Path("runs") / self.run_id / "sources/index.json")
        assert {member["path"] for member in index["members"]} == {
            "S001/responses/01.bin",
            "S001/text.txt",
            next(member["path"] for member in index["members"] if member["path"].startswith("_robots/")),
        }

        second_run = "run-failed"
        failed = Acquirer(
            store=self.store, run_id=second_run, mode="candidate", slug="sample_error",
            config=acquire_config(),
            client=FakeClient({"https://example.com/robots.txt": [NetFailure("dns_timeout", "fixed")]}),
            refetch=None, previous_root=None, previous_quarantined=False,
        )
        with pytest.raises(PipelineError, match="fetched または reused"):
            failed.run({"schema": "research_plan/v1", "candidates": [candidate]})
        failed_index = self.store.read_json(Path("runs") / second_run / "sources/index.json")
        assert failed_index["summary"]["failed"] == 1

    def test_candidate_key_reuse_survives_source_id_shift_and_updates_metadata(self):
        old_a = url_candidate("S001", "sha256:a", "a")
        old_b = url_candidate("S002", "sha256:b", "b")
        first_client = FakeClient(
            {
                "https://example.com/robots.txt": [result("https://example.com/robots.txt", status=404, body=b"")],
                old_a["url"]: [result(old_a["url"], body=b"alpha")],
                old_b["url"]: [result(old_b["url"], body=b"bravo")],
            }
        )
        first = self.acquirer(first_client).run(
            {"schema": "research_plan/v1", "candidates": [old_a, old_b]}
        )
        old_by_key = {item["candidate_key"]: item for item in first["sources"]}
        previous_root = Path("runs") / self.run_id / "superseded/old/S2_sources"
        self.store.move_tree(
            Path("runs") / self.run_id / "sources", previous_root / "sources"
        )

        inserted = url_candidate("S001", "sha256:new", "new")
        new_a = url_candidate("S002", "sha256:a", "a", role="boundary", anchor="changed")
        new_b = url_candidate("S003", "sha256:b", "b")
        second_client = FakeClient(
            {
                "https://example.com/robots.txt": [result("https://example.com/robots.txt", status=404, body=b"")],
                inserted["url"]: [result(inserted["url"], body=b"new material")],
            }
        )
        second = self.acquirer(second_client, previous_root=previous_root).run(
            {"schema": "research_plan/v1", "candidates": [inserted, new_a, new_b]}
        )
        sources = {item["candidate_key"]: item for item in second["sources"]}
        assert sources["sha256:new"]["status"] == "fetched"
        for key, new_id in (("sha256:a", "S002"), ("sha256:b", "S003")):
            reused = sources[key]
            old = old_by_key[key]
            assert reused["status"] == "reused"
            assert reused["source_id"] == new_id
            assert reused["fetched_at"] == old["fetched_at"]
            assert reused["requests"][0]["attempts"] == old["requests"][0]["attempts"]
            assert all(request["body_path"].startswith(new_id + "/") for request in reused["requests"])
            assert reused["text"]["path"].startswith(new_id + "/")
            assert reused["robots_ref"].startswith("_robots/")
        assert sources["sha256:a"]["role_hint"] == "boundary"
        assert sources["sha256:a"]["anchor"] == "changed"
        assert any(member["path"] == "S002/text.txt" for member in second["members"])
        assert any(member["path"] == "S003/text.txt" for member in second["members"])

    def test_duplicate_previous_candidate_key_stops(self):
        previous_root = Path("runs") / self.run_id / "superseded/old/S2_sources"
        source_root = previous_root / "sources"
        self.store.mkdir(source_root)
        previous = {
            "reuse_config_sha256": reuse_config_hash(acquire_config()),
            "sources": [
                {"candidate_key": "sha256:dup"},
                {"candidate_key": "sha256:dup"},
            ],
            "members": [],
        }
        self.store.write_json(source_root / "index.json", previous)
        with pytest.raises(PipelineError, match="candidate_key の重複"):
            self.acquirer(FakeClient({}), previous_root=previous_root).run(
                {"schema": "research_plan/v1", "candidates": []}
            )

    def test_reuse_rederives_text_from_saved_response_when_extractor_changes(self):
        candidate = url_candidate("S001", "sha256:a", "a")
        original_body = b"saved response text"
        first_client = FakeClient(
            {
                "https://example.com/robots.txt": [result("https://example.com/robots.txt", status=404, body=b"")],
                candidate["url"]: [result(candidate["url"], body=original_body)],
            }
        )
        self.acquirer(first_client).run({"schema": "research_plan/v1", "candidates": [candidate]})
        previous_root = Path("runs") / self.run_id / "superseded/old/S2_sources"
        self.store.move_tree(Path("runs") / self.run_id / "sources", previous_root / "sources")
        index_path = previous_root / "sources/index.json"
        previous = self.store.read_json(index_path)
        previous["extractor_version"] = 0
        self.store.write_json(index_path, previous)
        no_fetch = FakeClient({})
        current = self.acquirer(no_fetch, previous_root=previous_root).run(
            {"schema": "research_plan/v1", "candidates": [candidate]}
        )
        source = current["sources"][0]
        assert source["status"] == "reused"
        assert source["text_rederived"] is True
        assert self.store.read_bytes(Path("runs") / self.run_id / "sources/S001/text.txt") == original_body
        assert no_fetch.calls == []

    def test_run_budget_marks_remaining_candidates(self):
        first = url_candidate("S001", "sha256:a", "a")
        second = url_candidate("S002", "sha256:b", "b")
        client = FakeClient(
            {
                "https://example.com/robots.txt": [result("https://example.com/robots.txt", status=404, body=b"")],
                first["url"]: [result(first["url"], body=b"12345")],
            }
        )
        index = self.acquirer(client, config=acquire_config(max_total_bytes=4)).run(
            {"schema": "research_plan/v1", "candidates": [first, second]}
        )
        assert [item["status"] for item in index["sources"]] == ["fetched", "rejected"]
        assert index["sources"][1]["reason"] == "run_budget_exceeded"

    def test_github_file_blob_verification_line_anchors_rate_limit_and_token_scope(self):
        sha = "a" * 40
        body = b"line one\r\nline two\r\n"
        blob = git_blob_sha(body)
        candidate = {
            "source_id": "S001", "candidate_key": "sha256:git", "kind": "github_file",
            "repo": "o/r", "path": "docs/a.txt", "ref": sha,
            "role_hint": "official_impl", "origins": ["url_candidates"], "anchor": None,
        }
        api = "https://api.github.com/repos/o/r"
        raw = f"https://raw.githubusercontent.com/o/r/{sha}/docs/a.txt"
        commit_body = json.dumps({"sha": sha, "commit": {"committer": {"date": "2026-01-01T00:00:00Z"}}}).encode()
        contents_body = json.dumps({"type": "file", "sha": blob}).encode()
        client = FakeClient(
            {
                f"{api}/commits/{sha}": [result(f"{api}/commits/{sha}", body=commit_body, headers={"content-type": "application/json", "x-ratelimit-remaining": "10"})],
                f"{api}/contents/docs/a.txt?ref={sha}": [result(f"{api}/contents/docs/a.txt?ref={sha}", body=contents_body, headers={"content-type": "application/json"})],
                "https://raw.githubusercontent.com/robots.txt": [result("https://raw.githubusercontent.com/robots.txt", status=404, body=b"")],
                raw: [result(raw, body=body, headers={"content-type": "text/plain"})],
            }
        )
        old_token = os.environ.get("ARTICLE_PIPELINE_GITHUB_TOKEN")
        os.environ["ARTICLE_PIPELINE_GITHUB_TOKEN"] = "SECRET_PIPELINE_TOKEN"
        try:
            index = self.acquirer(client).run({"schema": "research_plan/v1", "candidates": [candidate]})
        finally:
            if old_token is None:
                os.environ.pop("ARTICLE_PIPELINE_GITHUB_TOKEN", None)
            else:
                os.environ["ARTICLE_PIPELINE_GITHUB_TOKEN"] = old_token
        source = index["sources"][0]
        assert source["status"] == "fetched"
        assert source["github"]["blob_sha_verified"] is True
        assert source["github"]["line_anchor"] == "supported"
        assert source["text"]["lines"] == 2
        assert source["github"]["permalink"] == f"https://github.com/o/r/blob/{sha}/docs/a.txt"
        assert all(
            (headers.get("Authorization") == "Bearer SECRET_PIPELINE_TOKEN") == url.startswith("https://api.github.com/")
            for url, headers in client.calls
        )
        serialized = json.dumps(index)
        assert "SECRET_PIPELINE_TOKEN" not in serialized

    def test_github_blob_mismatch_and_rate_limit_stop_are_recorded(self):
        sha = "a" * 40
        candidate = {
            "source_id": "S001", "candidate_key": "sha256:git", "kind": "github_file",
            "repo": "o/r", "path": "a.txt", "ref": sha,
            "role_hint": "official_impl", "origins": [], "anchor": None,
        }
        api = "https://api.github.com/repos/o/r"
        raw = f"https://raw.githubusercontent.com/o/r/{sha}/a.txt"
        commit_url = f"{api}/commits/{sha}"
        contents_url = f"{api}/contents/a.txt?ref={sha}"
        commit_body = json.dumps({"sha": sha}).encode()
        client = FakeClient(
            {
                commit_url: [result(commit_url, body=commit_body, headers={"content-type": "application/json", "x-ratelimit-remaining": "10"})],
                contents_url: [result(contents_url, body=json.dumps({"type": "file", "sha": "0" * 40}).encode(), headers={"content-type": "application/json"})],
                "https://raw.githubusercontent.com/robots.txt": [result("https://raw.githubusercontent.com/robots.txt", status=404, body=b"")],
                raw: [result(raw, body=b"not matching")],
            }
        )
        with pytest.raises(PipelineError):
            self.acquirer(client).run({"schema": "research_plan/v1", "candidates": [candidate]})
        index = self.store.read_json(Path("runs") / self.run_id / "sources/index.json")
        assert index["sources"][0]["reason"] == "github_blob_mismatch"

        other_run = "rate-limit"
        rate_client = FakeClient(
            {commit_url: [result(commit_url, body=commit_body, headers={"content-type": "application/json", "x-ratelimit-remaining": "0"})]}
        )
        acquirer = Acquirer(
            store=self.store, run_id=other_run, mode="candidate", slug="sample_error",
            config=acquire_config(), client=rate_client, refetch=None,
            previous_root=None, previous_quarantined=False,
        )
        with pytest.raises(PipelineError):
            acquirer.run({"schema": "research_plan/v1", "candidates": [candidate]})
        rate_index = self.store.read_json(Path("runs") / other_run / "sources/index.json")
        assert rate_index["sources"][0]["reason"] == "github_rate_limit_insufficient"
        assert len(rate_client.calls) == 1

    def test_challenge_page_is_blocked(self):
        candidate = url_candidate("S001", "sha256:a", "doc")
        client = FakeClient(
            {
                "https://example.com/robots.txt": [result("https://example.com/robots.txt", status=404, body=b"")],
                candidate["url"]: [result(candidate["url"], status=403, body=b"Just a moment...", headers={"content-type": "text/html; charset=utf-8"})],
            }
        )
        with pytest.raises(PipelineError):
            self.acquirer(client).run({"schema": "research_plan/v1", "candidates": [candidate]})
        index = self.store.read_json(Path("runs") / self.run_id / "sources/index.json")
        assert index["sources"][0]["status"] == "blocked"
        assert index["sources"][0]["reason"] == "challenge_page"

    def test_github_issue_renders_two_comment_pages_and_marks_truncation(self):
        candidate = {
            "source_id": "S001", "candidate_key": "sha256:issue", "kind": "github_issue",
            "repo": "o/r", "number": 7, "role_hint": "case",
            "origins": ["url_candidates"], "anchor": None,
        }
        api = "https://api.github.com/repos/o/r/issues/7"
        issue = {
            "title": "Broken", "body": "Issue body", "state": "open", "state_reason": None,
            "created_at": "2026-01-01T00:00:00Z", "closed_at": None,
            "labels": [{"name": "bug"}], "html_url": "https://github.com/o/r/issues/7",
            "pull_request": {"url": "https://api.github.com/repos/o/r/pulls/7"},
        }
        page_one = [
            {"body": f"comment {n}", "created_at": "2026-01-01T01:00:00Z", "author_association": "MEMBER", "user": {"login": "alice"}}
            for n in range(100)
        ]
        page_two = [
            {"body": f"last {n}", "created_at": "2026-01-01T02:00:00Z", "author_association": "NONE", "user": {"login": "bob"}}
            for n in range(100)
        ]
        values = {
            api: [result(api, body=json.dumps(issue).encode(), headers={"content-type": "application/json"})],
            f"{api}/comments?per_page=100&page=1": [result(f"{api}/comments?per_page=100&page=1", body=json.dumps(page_one).encode(), headers={"content-type": "application/json"})],
            f"{api}/comments?per_page=100&page=2": [result(f"{api}/comments?per_page=100&page=2", body=json.dumps(page_two).encode(), headers={"content-type": "application/json"})],
        }
        index = self.acquirer(
            FakeClient(values), config=acquire_config(issue_comment_pages_max=2)
        ).run({"schema": "research_plan/v1", "candidates": [candidate]})
        source = index["sources"][0]
        assert source["github"]["pull_request"] is True
        assert source["github"]["truncated"] is True
        text = self.store.read_text(Path("runs") / self.run_id / "sources/S001/text.txt")
        assert "comment 1 by alice (MEMBER)" in text
        assert "comment 101 by bob (NONE)" in text
        assert len(source["requests"]) == 3

    def test_github_logical_requests_share_one_source_deadline_and_five_attempts(self):
        sha = "a" * 40
        body = b"github source"
        candidate = {
            "source_id": "S001", "candidate_key": "sha256:git", "kind": "github_file",
            "repo": "o/r", "path": "a.txt", "ref": sha,
            "role_hint": "official_impl", "origins": [], "anchor": None,
        }
        api = "https://api.github.com/repos/o/r"
        commit_url = f"{api}/commits/{sha}"
        contents_url = f"{api}/contents/a.txt?ref={sha}"
        raw = f"https://raw.githubusercontent.com/o/r/{sha}/a.txt"
        client = FakeClient(
            {
                commit_url: [result(commit_url, body=json.dumps({"sha": sha}).encode(), headers={"content-type": "application/json", "x-ratelimit-remaining": "10"}, attempts=[{"result": "ok"}])],
                contents_url: [result(contents_url, body=json.dumps({"type": "file", "sha": git_blob_sha(body)}).encode(), headers={"content-type": "application/json"}, attempts=[{"result": "http_error"}, {"result": "http_error"}, {"result": "ok"}])],
                "https://raw.githubusercontent.com/robots.txt": [result("https://raw.githubusercontent.com/robots.txt", status=404, body=b"")],
                raw: [result(raw, body=body, attempts=[{"result": "ok"}])],
            }
        )
        index = self.acquirer(client).run({"schema": "research_plan/v1", "candidates": [candidate]})
        requests = index["sources"][0]["requests"]
        assert sum(len(request["attempts"]) for request in requests) == 5
        source_deadlines = [kwargs["source_deadline"] for kwargs in client.call_kwargs]
        assert len(set(source_deadlines)) == 1

    def test_run_deadline_marks_remaining_and_refetch_failed_recovers_them(self):
        candidates = [url_candidate(f"S00{n}", f"sha256:{n}", str(n)) for n in range(1, 4)]

        class StepClock:
            def __init__(self):
                self.values = iter((0, 0, 0, 2))

            def __call__(self):
                return next(self.values)

        first_client = FakeClient(
            {
                "https://example.com/robots.txt": [result("https://example.com/robots.txt", status=404, body=b"")],
                candidates[0]["url"]: [result(candidates[0]["url"], body=b"first success")],
            }
        )
        first = Acquirer(
            store=self.store, run_id=self.run_id, mode="candidate", slug="sample_error",
            config=acquire_config(run_deadline_s=1, source_deadline_s=1, request_deadline_s=1),
            client=first_client, refetch=None, previous_root=None,
            previous_quarantined=False, monotonic=StepClock(),
        ).run({"schema": "research_plan/v1", "candidates": candidates})
        assert [item["reason"] for item in first["sources"]] == [None, "run_deadline_exceeded", "run_deadline_exceeded"]
        previous_root = Path("runs") / self.run_id / "superseded/old/S2_sources"
        self.store.move_tree(Path("runs") / self.run_id / "sources", previous_root / "sources")
        client = FakeClient(
            {
                "https://example.com/robots.txt": [result("https://example.com/robots.txt", status=404, body=b"")],
                candidates[1]["url"]: [result(candidates[1]["url"], body=b"second success")],
                candidates[2]["url"]: [result(candidates[2]["url"], body=b"third success")],
            }
        )
        second = self.acquirer(client, previous_root=previous_root, refetch="failed").run(
            {"schema": "research_plan/v1", "candidates": candidates}
        )
        assert [item["status"] for item in second["sources"]] == ["reused", "fetched", "fetched"]

    def test_content_type_rejection_and_robots_server_failure(self):
        good = url_candidate("S001", "sha256:good", "good")
        pdf = url_candidate("S002", "sha256:pdf", "file.pdf")
        client = FakeClient(
            {
                "https://example.com/robots.txt": [result("https://example.com/robots.txt", status=404, body=b"")],
                good["url"]: [result(good["url"], body=b"good material")],
                pdf["url"]: [result(pdf["url"], body=b"%PDF", headers={"content-type": "application/pdf"})],
            }
        )
        index = self.acquirer(client).run({"schema": "research_plan/v1", "candidates": [good, pdf]})
        assert index["sources"][1]["reason"] == "content_type_not_allowed"

        other_run = "robots-failure"
        acquirer = Acquirer(
            store=self.store, run_id=other_run, mode="candidate", slug="sample_error",
            config=acquire_config(),
            client=FakeClient({"https://example.com/robots.txt": [result("https://example.com/robots.txt", status=500)]}),
            refetch=None, previous_root=None, previous_quarantined=False,
        )
        with pytest.raises(PipelineError):
            acquirer.run({"schema": "research_plan/v1", "candidates": [good]})
        failed = self.store.read_json(Path("runs") / other_run / "sources/index.json")
        assert failed["sources"][0]["reason"] == "robots_unreachable"

    def test_expired_source_is_refetched_and_incomplete_previous_stops_failed_mode(self):
        candidate = url_candidate("S001", "sha256:a", "a")
        first_client = FakeClient(
            {
                "https://example.com/robots.txt": [result("https://example.com/robots.txt", status=404, body=b"")],
                candidate["url"]: [result(candidate["url"], body=b"old material")],
            }
        )
        self.acquirer(first_client).run({"schema": "research_plan/v1", "candidates": [candidate]})
        previous_root = Path("runs") / self.run_id / "superseded/old/S2_sources"
        self.store.move_tree(Path("runs") / self.run_id / "sources", previous_root / "sources")
        index_path = previous_root / "sources/index.json"
        previous = self.store.read_json(index_path)
        previous["sources"][0]["fetched_at"] = "2000-01-01T00:00:00Z"
        self.store.write_json(index_path, previous)
        refetch = FakeClient(
            {
                "https://example.com/robots.txt": [result("https://example.com/robots.txt", status=404, body=b"")],
                candidate["url"]: [result(candidate["url"], body=b"new material")],
            }
        )
        current = self.acquirer(refetch, previous_root=previous_root).run(
            {"schema": "research_plan/v1", "candidates": [candidate]}
        )
        assert current["sources"][0]["status"] == "fetched"
        assert self.store.read_bytes(Path("runs") / self.run_id / "sources/S001/text.txt") == b"new material"

        # Corrupt the archived tree for a separate run: failed-only reuse must
        # refuse it and explicitly require all.
        incomplete_run = "incomplete-previous"
        incomplete_root = Path("runs") / incomplete_run / "superseded/old/S2_sources"
        self.store.mkdir(incomplete_root / "sources")
        broken = {
            "reuse_config_sha256": reuse_config_hash(acquire_config()),
            "extractor_version": 1,
            "sources": [], "robots": [],
            "members": [{"path": "missing.bin", "sha256": "sha256:" + "0" * 64}],
        }
        self.store.write_json(incomplete_root / "sources/index.json", broken)
        acquirer = Acquirer(
            store=self.store, run_id=incomplete_run, mode="candidate", slug="sample_error",
            config=acquire_config(), client=FakeClient({}), refetch="failed",
            previous_root=incomplete_root, previous_quarantined=False,
        )
        with pytest.raises(PipelineError, match="--refetch all"):
            acquirer.run({"schema": "research_plan/v1", "candidates": []})
