from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from scripts.article_pipeline.__main__ import command_new
from scripts.article_pipeline import PipelineError
from scripts.article_pipeline import intake, posts_index


def install_json_yaml_test_adapter() -> None:
    if intake.yaml is not None:
        return

    def reject_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise PipelineError(f"YAML を解析できません: duplicate key: {key!r}")
            result[key] = value
        return result

    def load_json_path(path: Path):
        try:
            return json.loads(
                path.read_text(encoding="utf-8"),
                object_pairs_hook=reject_duplicates,
            )
        except json.JSONDecodeError as exc:
            raise PipelineError(
                f"YAML を解析できません: path={path}, line={exc.lineno}, column={exc.colno}, error={exc.msg}"
            ) from exc

    class JsonYamlAdapter:
        class YAMLError(Exception):
            pass

        @staticmethod
        def safe_load(text: str):
            return json.loads(text, object_pairs_hook=reject_duplicates)

    intake.load_strict_yaml = load_json_path
    posts_index.yaml = JsonYamlAdapter()


CONFIG = json.dumps(
    {
        "paths": {
            "run_root": "run/article_pipeline",
            "posts_dir": "content/posts",
            "drafts_dir": "drafts",
        },
        "intake": {"overlap_threshold": 0.5, "overlap_top_n": 5},
    },
    ensure_ascii=False,
    indent=2,
)


def topic_text(slug: str = "sample_error", *, comment: str = "") -> str:
    value = {
        "slug": slug,
        "service": "Sample",
        "error_text": "Sample connection error",
        "error_code": "E100",
        "hint_urls": ["https://example.com/docs"],
        "notes": "",
    }
    return json.dumps(value, ensure_ascii=False, indent=2) + comment + "\n"


def article_text(slug: str = "sample_error") -> str:
    frontmatter = json.dumps(
        {
            "title": "Sample connection E100 error",
            "date": "2026-10-04",
            "description": "Sample",
            "tags": ["Sample", "connection"],
            "errorCode": "E100",
            "top_queries": ["sample error"],
        },
        ensure_ascii=False,
        indent=2,
    )
    return f"""\
---
{frontmatter}
---

## 冒頭まとめ

本文 {slug}

### 原因
"""


class RepoCase(TestCase):
    def setUp(self) -> None:
        install_json_yaml_test_adapter()
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "config").mkdir()
        (self.root / "content/posts").mkdir(parents=True)
        (self.root / "drafts").mkdir()
        (self.root / "run/article_pipeline/inbox").mkdir(parents=True)
        (self.root / ".gitignore").write_text("run/\n", encoding="utf-8")
        (self.root / "config/openai_article_pipeline.yml").write_text(CONFIG, encoding="utf-8")
        self.git("init", "-q")
        self.git("add", ".gitignore", "config/openai_article_pipeline.yml")
        self.git(
            "-c",
            "user.name=Pipeline Test",
            "-c",
            "user.email=pipeline@example.invalid",
            "commit",
            "-qm",
            "initial",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return result.stdout.strip()

    def write_topic(self, slug: str = "sample_error", *, comment: str = "") -> Path:
        path = self.root / "run/article_pipeline/inbox/topic.yml"
        path.write_text(topic_text(slug, comment=comment), encoding="utf-8")
        return path

    def write_post(self, slug: str = "sample_error", *, commit: bool = True) -> Path:
        path = self.root / f"content/posts/{slug}.md"
        path.write_text(article_text(slug), encoding="utf-8")
        if commit:
            self.git("add", path.relative_to(self.root).as_posix())
            self.git(
                "-c",
                "user.name=Pipeline Test",
                "-c",
                "user.email=pipeline@example.invalid",
                "commit",
                "-qm",
                f"add {slug}",
            )
        return path

    def run_new(
        self,
        *,
        slug: str = "sample_error",
        mode: str = "candidate",
        new_run: bool = False,
    ) -> int:
        topic = self.write_topic(slug)
        args = argparse.Namespace(
            topic=str(topic),
            mode=mode,
            new_run=new_run,
        )
        return command_new(args, self.root)
