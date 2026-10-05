from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock, skipUnless

from scripts.article_pipeline import PipelineError
from scripts.article_pipeline.__main__ import command_new
from scripts.article_pipeline.graph import PipelineGraph
from scripts.article_pipeline.locks import SlugLock
from scripts.article_pipeline.store import RunStore
from tests.article_pipeline_helpers import RepoCase, install_json_yaml_test_adapter


def _new_process(root_text, topic_text, entered, release, result, delayed):
    install_json_yaml_test_adapter()
    args = argparse.Namespace(topic=topic_text, mode="candidate", new_run=False)
    try:
        if delayed:
            original = PipelineGraph.resume

            def wait_then_resume(graph, *resume_args, **resume_kwargs):
                entered.set()
                if not release.wait(10):
                    raise RuntimeError("test release timeout")
                return original(graph, *resume_args, **resume_kwargs)

            with mock.patch.object(PipelineGraph, "resume", wait_then_resume):
                command_new(args, Path(root_text))
        else:
            command_new(args, Path(root_text))
        result.put(("ok", ""))
    except Exception as exc:
        result.put(("error", str(exc)))


class RunStoreTest(RepoCase):
    @skipUnless(os.name == "nt", "Windows path-length regression")
    def test_write_bytes_uses_short_temp_at_windows_path_boundary(self) -> None:
        store = RunStore(self.root)
        filename = f"{'d' * 64}.bin"
        base_parent = store.root / "runs" / "path-length"
        padding_length = 222 - len(str(base_parent)) - len(filename) - 2
        self.assertGreater(padding_length, 0)
        target = base_parent / ("p" * padding_length) / filename
        relative = target.relative_to(store.root)
        legacy_temp = target.with_name(f".{target.name}.{'0' * 32}.tmp")

        self.assertEqual(len(str(target)), 222)
        self.assertEqual(len(str(legacy_temp)), 260)

        written = store.write_bytes(relative, b"windows path boundary")

        self.assertEqual(written, target)
        self.assertEqual(target.read_bytes(), b"windows path boundary")
        self.assertEqual(list(target.parent.glob(".tmp-*.tmp")), [])

    def test_write_bytes_reports_final_replace_error_and_removes_temp(self) -> None:
        store = RunStore(self.root)
        relative = Path("runs/final-target/file.bin")
        target = store.root / relative
        error = OSError(206, "The filename or extension is too long", str(target))

        with mock.patch("scripts.article_pipeline.store.os.replace", side_effect=error):
            with self.assertRaises(PipelineError) as raised:
                store.write_bytes(relative, b"not committed")

        message = str(raised.exception)
        self.assertIn("ファイルを原子的に書き込めません", message)
        self.assertIn(f"path={target}", message)
        self.assertIn("206", message)
        self.assertFalse(target.exists())
        self.assertEqual(list(target.parent.glob(".tmp-*.tmp")), [])

    def test_rejects_parent_absolute_and_link_writes(self) -> None:
        store = RunStore(self.root)
        with self.assertRaisesRegex(PipelineError, "不正な相対パス"):
            store.write_text("../outside.txt", "x")
        with self.assertRaisesRegex(PipelineError, "絶対パス"):
            store.write_text(self.root / "outside.txt", "x")

        outside = self.root / "outside"
        outside.mkdir()
        link = self.root / "run/article_pipeline/link"
        try:
            os.symlink(outside, link, target_is_directory=True)
        except OSError as exc:
            print(f"UNEXECUTED symbolic-link case: {exc}", file=sys.stderr)
        else:
            with self.assertRaisesRegex(PipelineError, "リンク経由"):
                store.write_text("link/escape.txt", "x")

    def test_rejects_junction_write_on_windows(self) -> None:
        if os.name != "nt":
            print("UNEXECUTED junction case: Windows only", file=sys.stderr)
            return
        store = RunStore(self.root)
        outside = self.root / "junction-target"
        outside.mkdir()
        link = self.root / "run/article_pipeline/junction"
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(
                f"UNEXECUTED junction case: returncode={result.returncode}, stderr={result.stderr.strip()}",
                file=sys.stderr,
            )
            return
        with self.assertRaisesRegex(PipelineError, "junction"):
            store.write_text("junction/escape.txt", "x")

    def test_stops_when_run_is_not_gitignored(self) -> None:
        (self.root / ".gitignore").write_text("public/\n", encoding="utf-8")
        store = RunStore(self.root)
        with self.assertRaisesRegex(PipelineError, "gitignore"):
            store.ensure_gitignored()

    def test_new_does_not_change_git_status(self) -> None:
        before = self.git("status", "--porcelain")
        self.assertEqual(self.run_new(), 0)
        after = self.git("status", "--porcelain")
        self.assertEqual(after, before)

    def test_second_new_process_reports_lock_holder_and_first_releases(self) -> None:
        topic = self.write_topic()
        context = multiprocessing.get_context("spawn")
        entered = context.Event()
        release = context.Event()
        first_result = context.Queue()
        second_result = context.Queue()
        first = context.Process(
            target=_new_process,
            args=(str(self.root), str(topic), entered, release, first_result, True),
        )
        second = context.Process(
            target=_new_process,
            args=(str(self.root), str(topic), entered, release, second_result, False),
        )
        try:
            first.start()
            self.assertTrue(entered.wait(10), "first new process did not acquire the lock")
            second.start()
            second.join(10)
            self.assertFalse(second.is_alive(), "second new process did not stop")
            second_status, second_message = second_result.get(timeout=2)
            self.assertEqual(second_status, "error")
            self.assertIn("holder_run_id=cand_", second_message)
            release.set()
            first.join(10)
            self.assertFalse(first.is_alive(), "first new process did not finish")
            self.assertEqual(first_result.get(timeout=2)[0], "ok")
            self.assertFalse(
                (self.root / "run/article_pipeline/locks/sample_error.lock").exists()
            )
        finally:
            release.set()
            for process in (second, first):
                if process.pid is not None and process.is_alive():
                    process.terminate()
                if process.pid is not None:
                    process.join(2)

    def test_lock_collision_reports_holder_and_releases(self) -> None:
        store = RunStore(self.root)
        store.ensure_gitignored()
        first = SlugLock(store, "sample_error", "cand_holder")
        first.acquire()
        try:
            with self.assertRaisesRegex(PipelineError, "holder_run_id=cand_holder"):
                SlugLock(store, "sample_error", "cand_second").acquire()
        finally:
            first.release()
        self.assertFalse(store.exists("locks/sample_error.lock"))

    def test_s0_exception_releases_lock_and_marks_failed(self) -> None:
        topic = self.write_topic()
        args = argparse.Namespace(topic=str(topic), mode="candidate", new_run=False)

        def fail_after_running(graph, context, state_file, **_kwargs):
            state = state_file.read()
            state_file.transition(state, "S0_intake", "running", started_at="test")
            raise RuntimeError("forced S0 failure")

        with mock.patch(
            "scripts.article_pipeline.__main__.PipelineGraph.resume",
            autospec=True,
            side_effect=fail_after_running,
        ):
            with self.assertRaisesRegex(RuntimeError, "forced S0 failure"):
                command_new(args, self.root)

        states = list((self.root / "run/article_pipeline/runs").glob("*/state.json"))
        self.assertEqual(len(states), 1)
        state = json.loads(states[0].read_text(encoding="utf-8"))
        self.assertEqual(state["stages"]["S0_intake"]["status"], "failed")
        self.assertFalse((self.root / "run/article_pipeline/locks/sample_error.lock").exists())
