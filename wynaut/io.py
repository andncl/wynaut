"""Step 4 input and output: read saved analysis outputs, save rendered figures.
Figure scripts use only these functions to touch outputs."""

import re
from pathlib import Path

import pandas as pd

from wynaut.paths import BUILD_DIR

FIGURE_NAME = re.compile(r"^[A-Za-z0-9_-]+/[A-Za-z0-9_-]+$")


def load(analysis: str, name: str, version: str) -> dict:
    """Return the outputs of one call:
    {"runs":        {label: {"data": {key: xr.Dataset}, "results": {key: scalar}}},
     "accumulated": {"data": {key: xr.Dataset}, "results": {key: scalar}}}
    """
    raise NotImplementedError


def load_results_table(analysis: str, version: str,
                       step: str = "accumulated") -> pd.DataFrame:
    """All results of one analysis version.

    step="accumulated": one row per selection name, columns name + the
                        AccumulatedAnalysis results.
    step="run":         one row per run, columns name, label, db, run_id, guid,
                        modified_dimension, value + the RunAnalysis results.
    """
    raise NotImplementedError


def save_figure(fig, name: str) -> Path:
    """Save a matplotlib figure as build/figures/<name>.png and .pdf.

    name is "<person>/<script>", the path of the figure script without
    figures/ and .py. PLAN.md and the report refer to the figure by this name.
    """
    if not FIGURE_NAME.match(name):
        raise ValueError(f"figure name {name!r} must be '<person>/<script>'")
    path = BUILD_DIR / "figures" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(path.with_suffix(f".{ext}"), dpi=200, bbox_inches="tight")
    return path.with_suffix(".png")
