"""Step 3 runner: validate a selection file, load its runs, call
AccumulatedAnalysis.apply() (which runs the RunAnalysis on every run, then
accumulate()), and save everything.

Runs are loaded from DATA_ROOT, or from AVERAGED_ROOT when the RunAnalysis has
DATA = "averaged". Selection files always name the raw run.

Usage:
    python -m wynaut.run_analysis selections/<analysis>/<name>.json
    python -m wynaut.run_analysis selections/<analysis>/

This is the only code that loads runs for an analysis and the only code that
writes to OUTPUT_ROOT. Checks are listed in AGENTS.md, section 7; the checks on
analysis outputs live in wynaut.base_classes.
"""

import importlib
import inspect
import json
import sys
from pathlib import Path

import jsonschema

from wynaut.base_classes import AccumulatedAnalysis

SCHEMA = json.loads((Path(__file__).parent / "selection.schema.json").read_text())


def validate_selection(path: Path) -> dict:
    """Checks that need no data: schema, folder name, unique labels,
    modified_dimension and value either both set or both null."""
    selection = json.loads(Path(path).read_text())
    jsonschema.validate(selection, SCHEMA)
    if Path(path).parent.name != selection["analysis"]:
        raise ValueError(f"{path}: folder name must equal analysis "
                         f"{selection['analysis']!r}")
    labels = [r["label"] for r in selection["runs"]]
    if len(labels) != len(set(labels)):
        raise ValueError(f"{path}: duplicate labels in {labels}")
    for r in selection["runs"]:
        if (r["modified_dimension"] is None) != (r["value"] is None):
            raise ValueError(f"{path}: run {r['label']!r}: modified_dimension "
                             "and value must both be set or both be null")
    return selection


def check_in_index(selection: dict, index_lines: list[dict]) -> None:
    """Raise unless every run of the selection is in the run index, with the same guid."""
    guids = {(line["db"], line["run_id"]): line["guid"] for line in index_lines}
    problems = []
    for r in selection["runs"]:
        key = (r["db"], r["run_id"])
        if key not in guids:
            problems.append(f"{r['label']}: {key} is not in the run index")
        elif guids[key] != r["guid"]:
            problems.append(f"{r['label']}: guid {r['guid']} does not match the "
                            f"index ({guids[key]}) for {key}")
    if problems:
        raise ValueError("; ".join(problems))


def load_analysis_class(name: str) -> type[AccumulatedAnalysis]:
    """The one concrete AccumulatedAnalysis subclass defined in analysis/<name>.py."""
    module = importlib.import_module(f"analysis.{name}")
    found = [obj for obj in vars(module).values()
             if inspect.isclass(obj) and issubclass(obj, AccumulatedAnalysis)
             and obj.__module__ == module.__name__ and not inspect.isabstract(obj)]
    if len(found) != 1:
        raise TypeError(f"analysis/{name}.py must define exactly one "
                        f"AccumulatedAnalysis subclass, found "
                        f"{[c.__name__ for c in found]}")
    return found[0]


def run_selection(path: Path) -> None:
    """Validate, load runs, call AccumulatedAnalysis.apply(), then save all of
    it or nothing. meta.json records the VERSION of both classes, DATA and the
    averaged export_version if used, and the resolved kwargs of every step."""
    raise NotImplementedError


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        target = Path(arg)
        for p in sorted(target.glob("*.json")) if target.is_dir() else [target]:
            run_selection(p)
