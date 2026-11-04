"""The base classes enforce the analysis contract of AGENTS.md, section 7."""

import numpy as np
import pytest
import xarray as xr

from wynaut import AccumulatedAnalysis, Run, RunAnalysis


class Mean(RunAnalysis):
    """results: mean_V, fit_ok. data: trace."""

    VERSION = "1.0"
    DATA = "averaged"
    KWARGS = {"scale": 1.0, "offset_V": 0.0}

    def analyse(self, run):
        v = run.data.v * self.kwargs["scale"] + self.kwargs["offset_V"]
        return {"data": {"trace": v.to_dataset()},
                "results": {"mean_V": float(v.mean()), "fit_ok": True}}


class MeanVsField(AccumulatedAnalysis):
    """results: slope_V_per_T, n_runs_used. data: mean_vs_field."""

    VERSION = "1.0"
    RUN_ANALYSIS = Mean
    KWARGS = {"min_runs": 2}

    def accumulate(self, runs):
        ok = sorted(runs.values(), key=lambda r: r.value)
        ds = xr.Dataset({"mean": ("field", [r.results["mean_V"] for r in ok])},
                        coords={"field": [r.value for r in ok]})
        slope = float(np.polyfit(ds.field, ds["mean"], 1)[0])
        return {"data": {"mean_vs_field": ds},
                "results": {"slope_V_per_T": slope, "n_runs_used": len(ok)}}


def make_run(label, field, level):
    return Run(label=label, db="a/b.db", run_id=1,
               guid="aaaaaaaa-0000-0000-0000-000000000000",
               modified_dimension="field_T", value=field,
               data=xr.Dataset({"v": ("t", np.full(4, level))}))


RUNS = {"B_2T": make_run("B_2T", 2.0, 5.0), "B_1T": make_run("B_1T", 1.0, 3.0)}


def test_apply():
    out = MeanVsField().apply(RUNS)
    assert out["runs"]["B_1T"]["results"] == {"mean_V": 3.0, "fit_ok": True}
    assert out["accumulated"]["results"]["slope_V_per_T"] == pytest.approx(2.0)
    assert list(out["accumulated"]["data"]["mean_vs_field"].field) == [1.0, 2.0]


def test_kwargs_routed_to_the_class_that_declares_them():
    out = MeanVsField(scale=2.0, min_runs=3).apply(RUNS, {"B_1T": {"offset_V": 1.0}})
    assert out["kwargs"]["accumulated"] == {"min_runs": 3}
    assert out["kwargs"]["runs"]["B_1T"] == {"scale": 2.0, "offset_V": 1.0}
    assert out["kwargs"]["runs"]["B_2T"] == {"scale": 2.0, "offset_V": 0.0}
    assert out["runs"]["B_1T"]["results"]["mean_V"] == 7.0


def test_unknown_kwarg_rejected():
    with pytest.raises(TypeError, match="unknown kwargs"):
        MeanVsField(scael=2.0)
    with pytest.raises(TypeError, match="run 'B_1T'.*unknown kwargs"):
        MeanVsField().apply(RUNS, {"B_1T": {"min_runs": 1}})


def test_required_runs():
    class Pair(MeanVsField):
        """results: slope_V_per_T, n_runs_used. data: mean_vs_field."""
        VERSION = "1.0"
        REQUIRED_RUNS = ("reference", "interleaved")

    with pytest.raises(ValueError, match="REQUIRED_RUNS"):
        Pair().apply(RUNS)


def bad_run_analysis(results):
    class Bad(RunAnalysis):
        """results: x."""
        VERSION = "1.0"
        DATA = "raw"

        def analyse(self, run):
            return {"data": {}, "results": results(run)}

    class Acc(MeanVsField):
        """results: none."""
        VERSION = "1.0"
        RUN_ANALYSIS = Bad

        def accumulate(self, runs):
            return {"data": {}, "results": {}}

    return Acc()


@pytest.mark.parametrize("results, match", [
    (lambda run: {"x": np.float64(1.0)}, "float64"),
    (lambda run: {"x": [1.0]}, "list"),
    (lambda run: {"x": None}, "NoneType"),
    (lambda run: {"x": 1.0} if run.label == "B_1T" else {"y": 1.0}, "keys differ"),
])
def test_bad_run_results_rejected(results, match):
    with pytest.raises((TypeError, ValueError), match=match):
        bad_run_analysis(results).apply(RUNS)


def test_bad_accumulated_output_rejected():
    class Acc(MeanVsField):
        """results: none."""
        VERSION = "1.0"

        def accumulate(self, runs):
            return {"data": {"curve": xr.DataArray([1.0])}, "results": {}}

    with pytest.raises(TypeError, match="must be xr.Dataset"):
        Acc().apply(RUNS)


def test_version_must_be_own():
    class Child(Mean):
        """results: mean_V, fit_ok. data: trace."""

    with pytest.raises(TypeError, match="VERSION in its own class body"):
        Child()


def test_data_source_required():
    class NoData(RunAnalysis):
        """results: none."""
        VERSION = "1.0"

        def analyse(self, run):
            return {"data": {}, "results": {}}

    with pytest.raises(TypeError, match="DATA must be one of"):
        NoData()


def test_docstring_required():
    class NoDoc(RunAnalysis):
        VERSION = "1.0"
        DATA = "raw"

        def analyse(self, run):
            return {"data": {}, "results": {}}

    with pytest.raises(TypeError, match="docstring"):
        NoDoc()


def test_apply_cannot_be_overridden():
    with pytest.raises(TypeError, match="must not override apply"):
        class Sneaky(RunAnalysis):
            def apply(self, run):
                return {}


def test_fresh_run_analysis_per_run():
    seen = []

    class Stateful(Mean):
        """results: mean_V, fit_ok. data: trace."""
        VERSION = "1.0"

        def analyse(self, run):
            seen.append(self)  # keeps instances alive, so ids stay unique
            return super().analyse(run)

    class Acc(MeanVsField):
        """results: slope_V_per_T, n_runs_used."""
        VERSION = "1.0"
        RUN_ANALYSIS = Stateful

    Acc().apply(RUNS)
    assert len({id(s) for s in seen}) == len(RUNS)


def test_template_is_a_valid_analysis():
    from wynaut.run_analysis import load_analysis_class

    cls = load_analysis_class("_template")
    out = cls().apply(RUNS)
    assert set(out) == {"runs", "accumulated", "kwargs"}
