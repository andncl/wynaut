"""Base classes for analyses (step 3). See AGENTS.md, section 7.

An analysis is two classes:

    RunAnalysis          step 3a: one run -> {"data", "results"}
    AccumulatedAnalysis  step 3b: the outputs of all runs -> {"data", "results"}

Subclasses implement analyse() / accumulate() only. apply() runs the step and
checks its output; it must not be overridden. run_analysis calls
AccumulatedAnalysis.apply(), which creates a fresh RunAnalysis for every run,
so nothing stored on self can leak from one run into another.
"""

import re
from abc import ABC, abstractmethod
from types import MappingProxyType

import xarray as xr

from wynaut.run import Run, RunOutput

DATA_KEY = re.compile(r"^[a-z][a-z0-9_]*$")
RESULTS_KEY = re.compile(r"^[a-z][A-Za-z0-9_]*$")
SCALAR_TYPES = (bool, int, float, str)
DATA_SOURCES = ("raw", "averaged")


def check_output(out, where: str) -> None:
    """Raise unless out is {"data": {key: xr.Dataset}, "results": {key: scalar}}."""
    if not isinstance(out, dict) or set(out) != {"data", "results"}:
        got = sorted(out) if isinstance(out, dict) else type(out).__name__
        raise TypeError(f"{where}: must return a dict with exactly the keys "
                        f"'data' and 'results', got {got}")
    data, results = out["data"], out["results"]
    if not isinstance(data, dict) or not isinstance(results, dict):
        raise TypeError(f"{where}: 'data' and 'results' must both be dicts")
    for key, value in data.items():
        if not isinstance(key, str) or not DATA_KEY.match(key):
            raise TypeError(f"{where}: data key {key!r} is not snake_case")
        if not isinstance(value, xr.Dataset):
            raise TypeError(f"{where}: data[{key!r}] is {type(value).__name__}, "
                            "must be xr.Dataset")
    for key, value in results.items():
        if not isinstance(key, str) or not RESULTS_KEY.match(key):
            raise TypeError(f"{where}: results key {key!r} is not snake_case "
                            "with an optional unit suffix")
        # type() rather than isinstance(): numpy scalars subclass float
        if type(value) not in SCALAR_TYPES:
            raise TypeError(f"{where}: results[{key!r}] is "
                            f"{type(value).__name__}, must be one of "
                            "bool, int, float, str (convert with float())")


def _check_class(cls, required: dict) -> None:
    """Checks on a concrete subclass, run when it is first instantiated."""
    for name, kind in required.items():
        if name not in cls.__dict__:
            raise TypeError(f"{cls.__name__} must define {name} in its own "
                            "class body, not inherit it")
        if not isinstance(cls.__dict__[name], kind):
            raise TypeError(f"{cls.__name__}.{name} must be {kind}")
    if not (cls.__doc__ or "").strip():
        raise TypeError(f"{cls.__name__} needs a docstring listing every "
                        "output key with its unit")


class _Step(ABC):
    VERSION: str
    KWARGS: dict = {}  # every accepted kwarg with its default

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.__module__ != __name__ and "apply" in cls.__dict__:
            raise TypeError(f"{cls.__name__} must not override apply(); "
                            "implement analyse() / accumulate() instead")

    @property
    def kwargs(self):
        """Resolved kwargs: KWARGS defaults overridden by the selection file."""
        return self._kwargs

    def _set_kwargs(self, given: dict, allowed: set) -> None:
        unknown = set(given) - allowed
        if unknown:
            raise TypeError(f"{type(self).__name__}: unknown kwargs "
                            f"{sorted(unknown)}, allowed are {sorted(allowed)}")
        self._kwargs = MappingProxyType(
            {**self.KWARGS, **{k: v for k, v in given.items() if k in self.KWARGS}})


class RunAnalysis(_Step):
    """Step 3a: analyse one run on its own.

    Subclasses define VERSION, DATA, KWARGS, a docstring listing the output
    keys, and analyse(run).
    """

    DATA: str  # "raw" (shot by shot) or "averaged" (wynaut.averaged)

    def __init__(self, **kwargs):
        cls = type(self)
        _check_class(cls, {"VERSION": str})
        if getattr(cls, "DATA", None) not in DATA_SOURCES:
            raise TypeError(f"{cls.__name__}.DATA must be one of {DATA_SOURCES}")
        self._set_kwargs(kwargs, set(self.KWARGS))

    @abstractmethod
    def analyse(self, run: Run) -> dict:
        """Return {"data": dict[str, xr.Dataset], "results": dict[str, scalar]}
        for this one run. Settings come from self.kwargs."""

    def apply(self, run: Run) -> dict:
        out = self.analyse(run)
        check_output(out, f"{type(self).__name__}.analyse (run {run.label!r})")
        return out


class AccumulatedAnalysis(_Step):
    """Step 3b: combine the outputs of all runs in a selection file.

    Subclasses define VERSION, RUN_ANALYSIS, KWARGS, optionally REQUIRED_RUNS,
    a docstring listing the output keys, and accumulate(runs).
    """

    RUN_ANALYSIS: type[RunAnalysis]
    REQUIRED_RUNS: tuple[str, ...] | None = None  # exact set of labels, None = any

    def __init__(self, **kwargs):
        """kwargs: the top-level kwargs of the selection file. Each key goes to
        whichever of this class and RUN_ANALYSIS declares it in KWARGS."""
        cls = type(self)
        _check_class(cls, {"VERSION": str})
        if not (isinstance(getattr(cls, "RUN_ANALYSIS", None), type)
                and issubclass(cls.RUN_ANALYSIS, RunAnalysis)):
            raise TypeError(f"{cls.__name__}.RUN_ANALYSIS must be a RunAnalysis subclass")
        self._set_kwargs(kwargs, set(self.KWARGS) | set(self.RUN_ANALYSIS.KWARGS))
        self._run_defaults = {k: v for k, v in kwargs.items()
                              if k in self.RUN_ANALYSIS.KWARGS}

    @abstractmethod
    def accumulate(self, runs: dict[str, RunOutput]) -> dict:
        """Return {"data": dict[str, xr.Dataset], "results": dict[str, scalar]}
        from the per-run outputs. runs is keyed by label, in selection-file order.
        Settings come from self.kwargs."""

    def apply(self, runs: dict[str, Run],
              run_kwargs: dict[str, dict] | None = None) -> dict:
        """Run RUN_ANALYSIS on every run, then accumulate().

        runs       : {label: Run}, in selection-file order
        run_kwargs : {label: that run's own kwargs from the selection file}
        returns    : {"runs": {label: {"data", "results"}},
                      "accumulated": {"data", "results"},
                      "kwargs": {"runs": {label: resolved}, "accumulated": resolved}}
        """
        name = type(self).__name__
        run_kwargs = run_kwargs or {}
        if not runs:
            raise ValueError(f"{name}: needs at least one run")
        if self.REQUIRED_RUNS is not None and set(runs) != set(self.REQUIRED_RUNS):
            raise ValueError(f"{name}: labels {sorted(runs)} do not match "
                             f"REQUIRED_RUNS {sorted(self.REQUIRED_RUNS)}")
        if set(run_kwargs) - set(runs):
            raise ValueError(f"{name}: run_kwargs for unknown labels "
                             f"{sorted(set(run_kwargs) - set(runs))}")

        outputs = {}
        for label, run in runs.items():
            if run.label != label:
                raise ValueError(f"{name}: run keyed {label!r} has label {run.label!r}")
            try:
                step = self.RUN_ANALYSIS(**{**self._run_defaults,
                                            **run_kwargs.get(label, {})})
            except TypeError as err:
                raise TypeError(f"run {label!r}: {err}") from None
            out = step.apply(run)
            outputs[label] = RunOutput(
                label=run.label, db=run.db, run_id=run.run_id, guid=run.guid,
                modified_dimension=run.modified_dimension, value=run.value,
                kwargs=dict(step.kwargs), data=out["data"], results=out["results"])

        keys = {label: sorted(o.results) for label, o in outputs.items()}
        if len({tuple(k) for k in keys.values()}) > 1:
            raise ValueError(f"{self.RUN_ANALYSIS.__name__}: results keys differ "
                             f"between runs: {keys}")

        accumulated = self.accumulate(outputs)
        check_output(accumulated, f"{name}.accumulate")
        return {
            "runs": {label: {"data": o.data, "results": o.results}
                     for label, o in outputs.items()},
            "accumulated": accumulated,
            "kwargs": {"runs": {label: o.kwargs for label, o in outputs.items()},
                       "accumulated": dict(self.kwargs)},
        }
