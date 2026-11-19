"""Provenance for one eval run.

`summary.json` says what happened. This manifest says what it happened *to*:
which commit, which dataset bytes, which settings, which package versions. A
number without that is not reproducible, and a number that is not reproducible
is an anecdote.

Deliberately cheap: three local git calls, one file hash, no network. The API
key is recorded as present/missing, never by value.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

from research_agent.config import Settings

from .dataset import EvalItem, category_counts

SCHEMA = 1
REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES = (
    "deep-research-agent",
    "httpx",
    "pydantic",
    "fastapi",
    "trafilatura",
    "ddgs",
)

# Options that change the experiment. Excludes paths and output locations.
OPTION_KEYS = (
    "concurrency",
    "max_steps",
    "timeout",
    "sample",
    "seed",
    "all",
    "category",
    "id",
    "no_verify",
    "single_agent",
    "no_cache",
    "resume",
    "keep_failures",
)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _git(root: Path, *args: str) -> str | None:
    """Run git, returning None when it is missing, slow, or says no."""
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def repository_state(root: Path = REPO_ROOT) -> dict[str, Any]:
    """Commit, branch, and whether the working tree matched it."""
    commit = _git(root, "rev-parse", "HEAD")
    if not commit:
        return {"available": False}
    status = _git(root, "status", "--porcelain") or ""
    lines = [line for line in status.splitlines() if line.strip()]
    return {
        "available": True,
        "commit": commit,
        "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD") or None,
        "dirty": bool(lines),
        # Count, not names: the names are local state, the count is the caveat.
        "dirty_files": len(lines),
    }


def package_versions(names: tuple[str, ...] = PACKAGES) -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in names:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def settings_snapshot(settings: Settings) -> dict[str, Any]:
    """Everything that changes behaviour, and nothing that authenticates."""
    return {
        "provider": settings.provider,
        "model": settings.model,
        "judge_model": settings.judge_model or settings.model,
        "base_url": settings.base_url,
        "temperature": settings.temperature,
        "max_tokens": settings.max_tokens,
        "think": settings.think,
        "num_ctx": settings.num_ctx,
        "cache_path": settings.cache_path,
        "cache_ttl_s": settings.cache_ttl_s,
        "request_timeout": settings.request_timeout,
        "api_key": "set" if settings.api_key else "missing",
    }


def options_snapshot(args: argparse.Namespace | None) -> dict[str, Any]:
    if args is None:
        return {}
    return {
        key: getattr(args, key)
        for key in OPTION_KEYS
        if hasattr(args, key)
    }


def dataset_snapshot(
    path: Path, items: list[EvalItem], *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Hash the file *and* fingerprint the selected subset separately.

    A run over five ids from a 30-question file must not look like a run over a
    five-question dataset. The file hash answers "which corpus", the selected
    hash answers "which slice of it".
    """
    if path.exists():
        raw = path.read_bytes()
        digest = _sha256_bytes(raw)
        text = raw.decode("utf-8", errors="replace")
        questions_in_file = len([line for line in text.splitlines() if line.strip()])
    else:
        digest = _sha256_text("\n".join(item.model_dump_json() for item in items))
        questions_in_file = len(items)

    return {
        "path": _relative(path, root),
        "sha256": digest,
        "questions_in_file": questions_in_file,
        "selected": len(items),
        "selected_ids_sha256": _sha256_text("\n".join(item.id for item in items)),
        "categories": category_counts(items),
    }


def collect_manifest(
    *,
    settings: Settings,
    items: list[EvalItem],
    dataset_path: Path,
    args: argparse.Namespace | None = None,
    repo_root: Path = REPO_ROOT,
    now: datetime | None = None,
) -> dict[str, Any]:
    moment = now or datetime.now(timezone.utc)
    return {
        "schema": SCHEMA,
        "generated_at": moment.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "tool": "deep-research-agent eval",
        "repository": repository_state(repo_root),
        "dataset": dataset_snapshot(dataset_path, items, root=repo_root),
        "settings": settings_snapshot(settings),
        "options": options_snapshot(args),
        "runtime": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "packages": package_versions(),
        },
    }


def dumps(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, indent=2, ensure_ascii=False)
