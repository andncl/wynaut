"""Step 1: averaged copies of the raw data, exported by the maintainer.

Many analyses don't need shot-by-shot data. For those, export_averaged() writes
one netCDF file per run with every shot dimension averaged out:

    AVERAGED_ROOT/<db without .db>/<run_id>.nc

    <var>        mean over the shot dimensions
    <var>_sem    standard error of that mean, so error bars stay possible
    attrs        guid, db, run_id, n_shots, shot_dims, export_version

A copy keeps the identity of its raw run, (db, run_id, guid): selection files
always name the raw run, and a RunAnalysis with DATA = "averaged" receives this
file instead. Copying runs into new .db files is deliberately avoided, because
QCoDeS gives copied runs new run_ids. Runs without a shot dimension are exported
unchanged, without _sem variables.
"""

from pathlib import Path

import xarray as xr

EXPORT_VERSION = "1.0"  # bump when the averaging changes; recorded in meta.json

# Dimension names that count as repeated shots. Maintainer-owned.
SHOT_DIMS = ("shot", "repetition")


def averaged_path(db: str, run_id: int) -> Path:
    """AVERAGED_ROOT/<db without .db>/<run_id>.nc"""
    from wynaut.paths import AVERAGED_ROOT
    return AVERAGED_ROOT / db.removesuffix(".db") / f"{run_id}.nc"


def export_averaged(overwrite: bool = False) -> None:
    """Export every completed run in the index that has no copy at the current
    EXPORT_VERSION yet. Opens raw databases read-only and writes only under
    AVERAGED_ROOT."""
    raise NotImplementedError


def load_averaged(db: str, run_id: int, guid: str) -> xr.Dataset:
    """The averaged copy of one run. Raises if it doesn't exist yet (ask the
    maintainer to run tools/export_averaged.py) or if its guid differs."""
    raise NotImplementedError
