"""Template: copy to analysis/<name>.py and create selections/<name>/.

A module defines exactly one AccumulatedAnalysis subclass, which run_analysis
finds automatically. Its RUN_ANALYSIS can be defined here or imported, e.g. a
shared fit from analysis/_common/.
"""

from wynaut import AccumulatedAnalysis, RunAnalysis


class MyRunAnalysis(RunAnalysis):
    """<What is extracted from one run, from which measurement type.>

    results:
        <key_unit>      <description>
        <key_unit>_err  <uncertainty>
        fit_ok          bool, False if the fit failed (values are NaN)
    data:
        <key>           xr.Dataset, <description>
    """

    VERSION = "1.0"
    DATA = "averaged"  # or "raw" if you need shot-by-shot data
    KWARGS = {}  # every accepted kwarg with its default, e.g. {"fit_model": "exp_decay"}

    def analyse(self, run):
        """run: Run with run.data (xr.Dataset). Settings: self.kwargs."""
        data = {}
        results = {}
        return {"data": data, "results": results}


class MyAnalysis(AccumulatedAnalysis):
    """<What is extracted from all runs together.>

    results:
        <key_unit>      <description>
        n_runs_used     int, runs with fit_ok that went into the result
    data:
        <key>           xr.Dataset, <description>
    """

    VERSION = "1.0"
    RUN_ANALYSIS = MyRunAnalysis
    REQUIRED_RUNS = None  # tuple of labels, or None = any labels
    KWARGS = {}

    def accumulate(self, runs):
        """runs: {label: RunOutput}, with .results / .data from MyRunAnalysis
        and .modified_dimension / .value. Settings: self.kwargs."""
        data = {}
        results = {}
        return {"data": data, "results": results}
