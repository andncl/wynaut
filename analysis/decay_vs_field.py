"""Example analysis: decay time vs magnetic field.

Shows the two steps of an analysis on a made-up measurement: each run records a
signal decaying in time, and the runs of a sweep differ in field. Selection
file: selections/decay_vs_field/demo_sweep.json (runs of the demo campaign,
python -m tools.make_demo).

Step 3a fits one decay per run; step 3b relates the runs to each other. Neither
step plots or touches files; run_analysis loads the runs and saves the outputs.
"""

import numpy as np
import xarray as xr
from scipy.optimize import curve_fit

from wynaut import AccumulatedAnalysis, RunAnalysis


def exp_decay(t, amplitude, tau, offset):
    return amplitude * np.exp(-t / tau) + offset


class DecayFit(RunAnalysis):
    """Fit an exponential decay to one run.

    Input: run.data with a variable "signal" (V) over the coordinate "time" (s).

    results:
        tau_s       decay time (s), NaN if the fit failed
        tau_s_err   its standard error (s)
        fit_ok      bool, False if the fit did not converge
    data:
        decay       xr.Dataset: measured signal and fitted curve (V) over time (s)
    """

    VERSION = "1.0"
    DATA = "averaged"
    KWARGS = {"t_max_s": None}   # fit only up to this time; None = the whole trace

    def analyse(self, run):
        signal = run.data["signal"]
        if self.kwargs["t_max_s"] is not None:
            signal = signal.sel(time=slice(None, self.kwargs["t_max_s"]))
        t, y = signal["time"].values, signal.values
        guess = (y[0] - y[-1], (t[-1] - t[0]) / 3, y[-1])
        try:
            popt, pcov = curve_fit(exp_decay, t, y, p0=guess, maxfev=10_000)
            tau, tau_err, ok = float(popt[1]), float(np.sqrt(pcov[1, 1])), bool(popt[1] > 0)
            fit = exp_decay(t, *popt)
        except RuntimeError:
            tau, tau_err, ok, fit = float("nan"), float("nan"), False, np.full_like(y, np.nan)
        decay = xr.Dataset(
            {"signal": ("time", y, {"units": "V"}), "fit": ("time", fit, {"units": "V"})},
            coords={"time": ("time", t, {"units": "s"})})
        return {"data": {"decay": decay},
                "results": {"tau_s": tau, "tau_s_err": tau_err, "fit_ok": ok}}


class DecayVsField(AccumulatedAnalysis):
    """Decay time as a function of magnetic field, over the runs of one sweep.

    results:
        tau_max_s           longest decay time (s), NaN if no fit succeeded
        field_at_tau_max_T  field where it occurs (T)
        n_runs_used         int, runs with fit_ok
    data:
        tau_vs_field        xr.Dataset: tau and its error (s) over field (T)
    """

    VERSION = "1.0"
    RUN_ANALYSIS = DecayFit
    KWARGS = {}

    def accumulate(self, runs):
        ok = sorted((r for r in runs.values() if r.results["fit_ok"]), key=lambda r: r.value)
        tau = xr.Dataset(
            {"tau": ("field", [r.results["tau_s"] for r in ok], {"units": "s"}),
             "tau_err": ("field", [r.results["tau_s_err"] for r in ok], {"units": "s"})},
            coords={"field": ("field", [r.value for r in ok], {"units": "T"})})
        i = int(tau.tau.argmax("field")) if ok else None
        return {
            "data": {"tau_vs_field": tau},
            "results": {
                "tau_max_s": float(tau.tau[i]) if ok else float("nan"),
                "field_at_tau_max_T": float(tau.field[i]) if ok else float("nan"),
                "n_runs_used": len(ok),
            },
        }
