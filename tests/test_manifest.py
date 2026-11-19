from __future__ import annotations

import json
from datetime import datetime, timezone

import evals.manifest as manifest_module
from evals.dataset import EvalItem
from evals.manifest import (
    collect_manifest,
    dataset_snapshot,
    options_snapshot,
    repository_state,
    settings_snapshot,
)
from evals.run import parse_args
from research_agent.config import Settings


def make_item(**overrides) -> EvalItem:
    payload = {
        "id": "t-1",
        "question": "A question long enough to validate?",
        "category": "asyncio",
        "must_include": ["return_exceptions"],
    }
    payload.update(overrides)
    return EvalItem(**payload)


def test_manifest_hashes_the_corpus_and_separates_the_selected_slice(tmp_path):
    first = make_item()
    second = make_item(
        id="t-2",
        question="Another question long enough to validate?",
        category="http",
    )
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(
        first.model_dump_json() + "\n" + second.model_dump_json() + "\n",
        encoding="utf-8",
    )

    snapshot = dataset_snapshot(dataset, [first], root=tmp_path)

    assert snapshot["questions_in_file"] == 2
    assert snapshot["selected"] == 1
    assert snapshot["categories"] == {"asyncio": 1}
    assert len(snapshot["sha256"]) == 64
    assert len(snapshot["selected_ids_sha256"]) == 64


def test_manifest_never_records_the_api_key(tmp_path):
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(make_item().model_dump_json() + "\n", encoding="utf-8")

    manifest = collect_manifest(
        settings=Settings(
            provider="openrouter",
            model="openai/gpt-oss-20b",
            judge_model="openai/gpt-oss-120b",
            api_key="sk-do-not-print",
        ),
        items=[make_item()],
        dataset_path=dataset,
        repo_root=tmp_path,
        now=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
    )

    rendered = json.dumps(manifest)
    assert "sk-do-not-print" not in rendered
    assert manifest["settings"]["api_key"] == "set"
    assert manifest["generated_at"] == "2026-01-02T03:04:05+00:00"
    assert settings_snapshot(Settings())["api_key"] == "missing"


def test_repository_state_records_commit_branch_and_dirty_count(monkeypatch):
    responses = {
        "rev-parse HEAD": "abc123",
        "rev-parse --abbrev-ref HEAD": "main",
        "status --porcelain": " M a.py\n?? b.txt\n",
    }

    def fake_git(root, *args):
        return responses[" ".join(args)]

    monkeypatch.setattr(manifest_module, "_git", fake_git)

    assert repository_state() == {
        "available": True,
        "commit": "abc123",
        "branch": "main",
        "dirty": True,
        "dirty_files": 2,
    }


def test_repository_state_degrades_when_git_is_unavailable(monkeypatch):
    monkeypatch.setattr(manifest_module, "_git", lambda *args: None)

    assert repository_state() == {"available": False}


def test_options_snapshot_keeps_only_experiment_switches():
    args = parse_args(["--no-cache", "--single-agent", "--all"])

    options = options_snapshot(args)

    assert options["no_cache"] is True
    assert options["single_agent"] is True
    assert options["all"] is True
    assert "out" not in options
    assert "dataset" not in options
    assert options_snapshot(None) == {}
