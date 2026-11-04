"""The example analysis runs end to end on synthetic runs, through the base classes'
checks, the same way run_analysis calls it."""

import json
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from analysis.decay_vs_field import DecayVsField
from wynaut import Run
from wynaut.run_analysis import load_analysis_class

SELECTION = Path(__file__).parent.parent / "selections" / "decay_vs_field" / "demo_sweep.json"


def decay_run(r: dict, tau_s: float, noise=0.01, seed=0) -> Run:
    """A Run for one entry of a selection file, with a decay of time constant tau_s."""
    t = np.linspace(0, 5e-4, 200)
    y = np.exp(-t / tau_s) + np.random.default_rng(seed).normal(0, noise, t.size)
    data = xr.Dataset({"signal": ("time", y, {"units": "V"})},
                      coords={"time": ("time", t, {"units": "s"})})
    return Run(label=r["label"], db=r["db"], run_id=r["run_id"], guid=r["guid"],
               modified_dimension=r["modified_dimension"], value=r["value"], data=data)


def test_module_defines_one_accumulated_analysis():
    assert load_analysis_class("decay_vs_field") is DecayVsField


def test_decay_time_vs_field_on_the_demo_selection():
    selection = json.loads(SELECTION.read_text())
    taus = {r["label"]: 1e-4 * (1 + r["value"]) for r in selection["runs"]}   # tau grows with field
    runs = {r["label"]: decay_run(r, taus[r["label"]], seed=i)
            for i, r in enumerate(selection["runs"])}
    out = DecayVsField().apply(runs)

    first = selection["runs"][0]["label"]
    assert out["runs"][first]["results"]["tau_s"] == pytest.approx(taus[first], rel=0.05)
    assert out["accumulated"]["results"]["n_runs_used"] == len(runs)
    longest = max(selection["runs"], key=lambda r: r["value"])
    assert out["accumulated"]["results"]["field_at_tau_max_T"] == longest["value"]
    assert set(out["accumulated"]["data"]["tau_vs_field"].data_vars) == {"tau", "tau_err"}
