from __future__ import annotations

import json

import pytest

from scripts.article_pipeline import PipelineError
from scripts.article_pipeline.config import load_config
from tests.article_pipeline_helpers import CONFIG


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("request_deadline_s", 6),
        ("source_deadline_s", 21),
        ("connect_timeout_s", 3),
        ("read_timeout_s", 3),
        ("dns_timeout_s", 3),
    ],
)
def test_invalid_deadline_relationships_stop_at_load(tmp_path, key, value) -> None:
    config = json.loads(CONFIG)
    config["acquire"][key] = value
    path = tmp_path / "config.yml"
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(PipelineError, match="deadline|上限|時間"):
        load_config(path)
