"""Paths to the shared drive, read from config.yaml in the repo root.

Usage: from wynaut.paths import DATA_ROOT, AVERAGED_ROOT, OUTPUT_ROOT, INDEX_PATH
Set WYNAUT_CONFIG to use a config file elsewhere.

INDEX_PATH (the run index) is in the repo and committed, so selection files are
always checked against the index of the same commit. BUILD_DIR (rendered figures,
generated report) is local to the repo and gitignored.
"""

import os
from functools import cache
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = REPO_ROOT / "build"
INDEX_PATH = REPO_ROOT / "index" / "runs.jsonl"

_KEYS = {"DATA_ROOT": "data_root", "AVERAGED_ROOT": "averaged_root",
         "OUTPUT_ROOT": "output_root"}


@cache
def _config():
    path = Path(os.environ.get("WYNAUT_CONFIG", REPO_ROOT / "config.yaml"))
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found: copy config.example.yaml to config.yaml "
            "and set the shared-drive paths")
    return yaml.safe_load(path.read_text())


def __getattr__(name):
    if name in _KEYS:
        return Path(_config()[_KEYS[name]])
    raise AttributeError(name)
