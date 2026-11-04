"""The objects an analysis receives for each run in a selection file.

Run       is passed to RunAnalysis.analyse and carries the measured data.
RunOutput is passed to AccumulatedAnalysis.accumulate and carries what
          RunAnalysis.analyse returned for that run.
"""

from dataclasses import dataclass

import xarray as xr


@dataclass(frozen=True)
class _RunInfo:
    label: str
    db: str  # relative to DATA_ROOT
    run_id: int
    guid: str  # must match the run index for (db, run_id)
    modified_dimension: str | None  # what was varied, with SI unit suffix, e.g. "field_T"
    value: float | None  # value of modified_dimension in that unit


@dataclass(frozen=True)
class Run(_RunInfo):
    data: xr.Dataset  # the measured run


@dataclass(frozen=True)
class RunOutput(_RunInfo):
    kwargs: dict  # resolved kwargs the RunAnalysis used for this run
    data: dict[str, xr.Dataset]  # "data" returned by RunAnalysis.analyse
    results: dict  # "results" returned by RunAnalysis.analyse
