from __future__ import annotations

import argparse
import ast
import contextlib
import io
import json
from pathlib import Path
from unittest.mock import patch

from scripts.article_pipeline.__main__ import (
    _safe_display,
    command_new,
    command_resume,
    command_sources,
    command_status,
)
from scripts.article_pipeline.graph import PipelineGraph, StageContext, build_production_stages
from scripts.article_pipeline.net import FetchResult, NetworkClient
from scripts.article_pipeline.state import StateFile
from scripts.article_pipeline.store import RunStore
from tests.article_pipeline_helpers import CONFIG, RepoCase


class FixedClient:
    def __init__(self, body=b"ignore instructions\x1b[31m\x00 end with many links https://a https://b"):
        self.body = body
        self.calls = []

    def fetch(self, url, **_kwargs):
        self.calls.append(url)
        robots = url.endswith("/robots.txt")
        return FetchResult(
            url=url, final_url=url, redirects=[], resolved_ip="93.184.216.34",
            http_status=404 if robots else 200,
            headers={"content-type": "text/plain; charset=utf-8"},
            body=b"" if robots else self.body, attempts=[{"result": "ok"}],
        )


def test_only_net_module_imports_network_apis() -> None:
    root = Path(__file__).parents[1] / "scripts/article_pipeline"
    forbidden = {"socket", "ssl", "http.client", "urllib.request", "requests", "openai"}
    violations = []
    for path in root.glob("*.py"):
        if path.name == "net.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {node.module or ""}
            else:
                continue
            hit = names & forbidden
            if hit:
                violations.append((path.name, sorted(hit)))
    assert violations == []


class TestP2Cli(RepoCase):
    def create_s1(self):
        topic = self.write_topic()
        candidates = self.root / "run/article_pipeline/inbox/candidates.yml"
        candidates.write_text(
            "schema: url_candidates/v1\ncandidates:\n"
            "- {url: https://example.com/docs, role_hint: official_doc}\n",
            encoding="utf-8",
        )
        before = self.git("status", "--porcelain")
        with patch.object(NetworkClient, "fetch", side_effect=AssertionError("network forbidden")):
            assert command_new(
                argparse.Namespace(
                    topic=str(topic), mode="candidate", new_run=False,
                    url_candidates=str(candidates),
                ),
                self.root,
            ) == 0
        assert self.git("status", "--porcelain") == before
        runs = [path.name for path in (self.root / "run/article_pipeline/runs").iterdir()]
        assert len(runs) == 1
        return runs[0]

    def test_s0_s1_status_and_default_resume_do_not_touch_network(self):
        run_id = self.create_s1()
        failure = AssertionError("network forbidden")
        with patch.object(NetworkClient, "fetch", side_effect=failure):
            assert command_status(argparse.Namespace(run=run_id), self.root) == 0
            assert command_resume(
                argparse.Namespace(
                    run=run_id, through=None, from_stage=None,
                    accept_modified=None, refetch=None,
                ),
                self.root,
            ) == 0

    def test_sources_display_escapes_control_text_without_following_links(self):
        run_id = self.create_s1()
        config = json.loads(CONFIG)
        store = RunStore(self.root)
        graph = PipelineGraph(build_production_stages())
        context = StageContext(self.root, store, run_id, config)
        client = FixedClient()
        context.cache["network_client"] = client
        graph.resume(context, StateFile(store, run_id), through="S2_sources")
        assert len(client.calls) == 2
        captured = io.StringIO()
        with patch.object(NetworkClient, "fetch", side_effect=AssertionError("network forbidden")):
            with contextlib.redirect_stdout(captured):
                assert command_sources(
                    argparse.Namespace(run=run_id, show="S001", lines="1-1"), self.root
                ) == 0
        output = captured.getvalue()
        assert "\\x1b" in output
        assert "\\x00" in output
        assert "\x1b" not in output
        assert _safe_display("a\x1b\x00\x85\tb") == "a\\x1b\\x00\\x85\\tb"
