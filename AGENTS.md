# wynaut analysis campaign: conventions for LLM assistants

You are helping a researcher on a shared, multi-month data-analysis campaign.
Several people (and their LLMs) work in this repo at the same time. Everything
below is a **hard contract**: code or files that deviate from it will be
rejected by the tooling or by review. When a request conflicts with this
document, say so and ask. Do not quietly work around it.

MUST / MUST NOT are strict. SHOULD means "default unless the user says otherwise".

---

## 1. The pipeline

```
0 Raw data ─► 1 Index & ─► 2a Plan ─► 2b Select ─► 3 Analysis ──────────────► 4 Figures ─► 5 Report
              averaged     PLAN.md    selection    3a per run ► 3b accumulate   figure       Slidev
              copies                  files                                     scripts      deck
                              │                                                                ▲
                              └──── question, what we need, what success looks like ──────────┘
```

| Step | Input | Output | Lives in |
|---|---|---|---|
| 0 Raw data | — | QCoDeS `.db` files | drive, `DATA_ROOT` (read-only) |
| 1 Index & averaged copies | all `.db` under `DATA_ROOT` | `index/runs.jsonl`; one averaged `.nc` per run | index and script: git; averaged copies: drive |
| 2a Plan | the researchers' questions | one `##` section per question in `PLAN.md` | git |
| 2b Select | `PLAN.md` + the run index | `selections/<analysis>/<name>.json` | git |
| 3a `RunAnalysis` | one run of a selection file | `{"data": ..., "results": ...}` per run | code: git `analysis/`; outputs: drive `OUTPUT_ROOT` |
| 3b `AccumulatedAnalysis` | the 3a outputs of all runs in the file | `{"data": ..., "results": ...}` | code: git `analysis/`; outputs: drive `OUTPUT_ROOT` |
| 4 Figures | saved analysis outputs (3a and 3b) | figure images | code: git `figures/<person>/`; images: `build/figures/` |
| 5 Report | `PLAN.md` + outputs + figure images | Slidev deck: progress, figures, results, outcome per question | generator: git `tools/`, `report/`; deck: `build/`, published |

Each step reads **only** the output of the step before it. In particular:
- The per-run step sees one run only. The accumulate step never sees raw data.
- An analysis never plots.
- A figure script never reads raw data and never re-runs a fit.
- The report never computes anything and contains no hand-typed results.

The plan feeds forward to the report: every question in `PLAN.md` becomes one
chapter of the deck, which shows how far it has got and whether it succeeded.

## 2. Who does what

Three roles. Researchers (whoever asks the questions: experimentalists,
theorists, analysts) decide and own the science; agents do the mechanical work
on request; maintainers keep the stack running. **It doesn't matter whether code is typed by a person or an
agent: what matters is what kind of file it is, and who has to approve it.**

| Step | Researcher | Agent | Maintainer |
|---|---|---|---|
| 0 Raw data | runs the measurements | — never touches raw data | keeps the drive read-only and backed up |
| 1 Index & averaged | — | — | runs `build_index`, `export_averaged`; owns their columns and format |
| 2a Plan | **writes** the question, what is needed, what success looks like | turns a conversation into a `PLAN.md` section, asks about gaps | owns the `PLAN.md` format |
| 2b Select | describes the runs in words, **confirms** the candidates | searches the index, proposes candidates, writes selection files | owns schema, index columns, tests |
| 3 Analysis | **owns the method**: fit model, what is extracted; **checks** the results | drafts the classes, runs `run_analysis`, reports | owns `wynaut/`, base classes, CI |
| 4 Figures | owns their figure code | drafts plotting code on request | owns `wynaut.io`, figure rendering |
| 5 Report | **writes** `Status` and `### Outcome` | builds the deck; points out where results and plan disagree | owns the generator, Slidev theme, publishing |

**Approval gates.** An agent never passes these on its own:
1. **Runs** (2b): the researcher confirms the candidate runs before a selection file is written.
2. **Method** (3): the researcher approves the fit model and checks the results.
3. **Verdict** (5): only the researcher sets `Status` and writes `### Outcome`.

### Natural language, code and structured files

| File | Kind | Written by | Rule |
|---|---|---|---|
| Requests to agents | natural language | researcher | How researchers drive steps 2a, 2b, 3, 4 and 5 |
| `PLAN.md` | **natural language**, 4 fixed lines per question | researcher (agent may draft) | §5 |
| `selections/**/*.json` | **structured data**, never hand-edited prose | agent, after gate 1 | §6 |
| `analysis/**/*.py` | **code** | researcher or agent; researcher approves (gate 2) | §7 |
| `figures/<person>/*.py` | **code** | researcher or agent | §10 |
| `wynaut/`, `tools/`, `tests/`, `report/` | **code** | maintainer | §3 |
| `project.yaml` | **structured data**: project settings (timezone, sensor logs, tracker scale) | maintainer | §3, §4 |
| `report/milestones.yaml`, `report/run_marks.yaml` | **structured data**: events and hand-set run marks for the run tracker | researcher or agent, on request | §11 |
| index, averaged copies, outputs, figure images, deck | **generated**, never edited | tools | §4, §8, §11 |

## 3. Repo layout

```
<campaign>/
├── AGENTS.md              # this file (CLAUDE.md just includes it)
├── PLAN.md                # step 2a: the questions of the campaign, natural language
├── project.yaml           # project settings, committed: timezone, sensor logs, tracker scale
├── index/runs.jsonl       # step 1: the run index, generated, committed
├── config.example.yaml    # copy to config.yaml (gitignored), set shared-drive paths
├── wynaut/                # maintainer code: DO NOT modify without the user's explicit request
│   ├── paths.py           # DATA_ROOT, AVERAGED_ROOT, OUTPUT_ROOT, INDEX_PATH, BUILD_DIR
│   ├── project.py         # the settings of project.yaml
│   ├── index.py           # build_index(), load_index(), describe_run()
│   ├── sensors.py         # a logged sensor quantity per run (e.g. a cryostat temperature)
│   ├── averaged.py        # export_averaged(), load_averaged()
│   ├── plan.py            # parse_plan(): reads the fixed lines of PLAN.md
│   ├── base_classes.py    # RunAnalysis, AccumulatedAnalysis: subclass these for step 3
│   ├── run.py             # Run (input to step 3a), RunOutput (input to step 3b)
│   ├── run_analysis.py    # validates, loads runs, calls AccumulatedAnalysis.apply(), saves outputs
│   ├── io.py              # load(), load_results_table(), save_figure()
│   └── selection.schema.json
├── selections/<analysis>/<name>.json
├── analysis/
│   ├── _template.py       # copy to start a new analysis
│   ├── _common/           # shared RunAnalysis classes, fit models and helpers
│   └── <analysis>.py
├── figures/<person>/...   # figures/paper/ = agreed final figures
├── report/                # step 5: Slidev setup, milestones.yaml and run_marks.yaml for the tracker
├── tools/                 # build_index, index_sensor, export_averaged, merge_wal, build_report,
│                          # timeline (run tracker), make_demo (a fictional campaign to try it on)
├── tests/                 # pytest: selection files, PLAN.md, base classes, index, sensors, tracker
├── build/                 # generated, gitignored: figure images, run tracker, report deck
└── docs/                  # slides (docs/slides/make_slides.py → docs/img/)
```

## 4. Identifying runs, raw and averaged data

- A run is identified by **`(db, run_id)`**. A bare `run_id` is meaningless because
  every database restarts at 1. Selection files also carry the run's `guid`, copied
  from the run index, so a renamed, moved or replaced `.db` is caught instead of
  silently loading a different run.
- `db` is a POSIX path **relative to `DATA_ROOT`**, e.g. `"setup_a/cooldown_2.db"`.
  Never use absolute paths, drive letters or backslashes.
- To find runs, filter the run index (`wynaut.index.load_index()`), a pandas
  DataFrame with columns `db, run_id, guid, name, exp_name, sample, start_time,
  end_time, sensor_min, sensor_max, sensor_mean, sensor_std, sensor_n`. Times
  are UTC; `end_time` is empty for runs that didn't complete. The sensor columns
  give the logged quantity set under `sensor:` in `project.yaml` (its `label`
  and `unit` say what it is, e.g. the cryostat temperature in K) during the
  run, and are empty where no log covers it or the project has no sensor.
  Runs with no reading inside their window use the single reading nearest to
  their start (`sensor_n` 1). Where `below_range` is set, a value equal to
  `below_range.value` is a bound, not a measurement (e.g. "7 mK or colder").
  The rules are in `wynaut/sensors.py`.
  To check a single candidate in detail (parameters, settings), use
  `wynaut.index.describe_run(db, run_id)`.
- The index is **committed** at `index/runs.jsonl`, one JSON line per run, so
  every selection file is checked against the index of the same commit. It holds
  only these small columns, never snapshots. The maintainer rebuilds it with
  `python -m tools.build_index`, then `python -m tools.index_sensor`; never
  edit it by hand.
- The databases are QCoDeS-style SQLite files (tables `runs` and `experiments`);
  `qcodes` itself is not needed to index them.
- The sensor logs stay on the drive in `DATA_ROOT/<sensor.folder>/`, in the
  project's local time (`timezone:` in `project.yaml`), and are read-only like
  the databases.
- Not indexed: averaged exports (`*avg*`), backups kept before a WAL merge
  (`*unmerged*`), and every pattern under `index: exclude:` in `project.yaml`
  (e.g. mock data, copies of runs with duplicate guids, broken databases). A
  database whose WAL hasn't been merged into the `.db` is refused, because the
  fast read would miss runs; its previous index lines are kept. Databases listed
  under `index: read_with_wal:` are read anyway, read-only with their WAL:
  correct but slow, because without write access SQLite scans the whole WAL.
- Never open a `.db` file in write mode. Never copy raw data into the repo.

**Averaged copies.** For every run, the maintainer exports a copy with all shot
dimensions averaged out (`wynaut/averaged.py`): one netCDF file per run, holding
the mean and the standard error (`<var>_sem`) of every variable. A copy keeps the
identity `(db, run_id, guid)` of its raw run. Selection files **always name the raw
run**; each `RunAnalysis` declares which version it receives (`DATA`, §7). If a run
has no averaged copy yet, the analysis fails with a clear error; the maintainer
runs `tools/export_averaged.py`.

## 5. Plan (step 2a)

**Path:** `PLAN.md`, one file for the whole campaign. **Natural language**, with
one `##` section per question. A section starts with four fixed lines, followed
by four `###` subsections of free text:

```markdown
## Decay time vs magnetic field
Owner: alice
Status: open
Analyses: decay_vs_field v1.0, decay_vs_temperature
Figures: alice/tau_vs_field

### Question
Is the decay limited by a field-dependent loss channel?

### What we need
Decay time (s) at five or more fields between 0 and 2 T, same cooldown, same sample.

### Success looks like
The decay time falls by more than a factor two between 0.5 T and 2 T. A flat decay time counts against it.

### Outcome
```

| Line | Rule |
|---|---|
| `Owner:` | who answers for this question |
| `Status:` | `open`, `confirmed`, `refuted`, `inconclusive` or `measurement failed`. Only a person changes it |
| `Analyses:` | `<analysis> v<VERSION>, ...`, or `none yet`. Pin the version once results exist, like figures do |
| `Figures:` | `<person>/<script>, ...` (the name passed to `save_figure`), or `none yet` |

- The four fixed lines are the **only** part read by code (`wynaut/plan.py`).
  Everything else is free text and goes into the report as written.
- `### Question`, `### What we need` and `### Success looks like` must not be
  empty. Write `### Success looks like` **before** the results exist: git history
  then shows the goal wasn't moved after seeing the data.
- `### Outcome` is written after the results, together with `Status`. It may
  be empty only while `Status: open`.
- `measurement failed` means the data can't answer the question (and Outcome says
  why, and what would be needed). `refuted` means the data is good and the answer
  is no. Never mix them up: they are different results.
- Add no other fixed lines and no other `###` subsections. `pytest` checks the format.

## 6. Selection file (step 2b)

**Path:** `selections/<analysis>/<name>.json`
- `<analysis>` is the analysis module name and MUST equal the `"analysis"` field.
- `<name>` identifies this particular call (e.g. `Q2_wk14`) and names the output folder.
  Pattern: `^[A-Za-z0-9_-]+$`.

**One selection file = one call of the analysis:** the `RunAnalysis` once for
each run in the file, then the `AccumulatedAnalysis` once on all of their outputs.
The runs in a file are the runs that get accumulated. To run the same analysis on
other runs, create another file. Do not add a list of calls inside one file.

Selection files are structured data. They are linked to questions only through
`Analyses:` in `PLAN.md`; they never refer to the plan.

### Format: exactly these keys, nothing else

A sweep, where each run differs in one physical quantity:

```json
{
  "analysis": "decay_vs_field",
  "kwargs": {"fit_model": "exp_decay"},
  "runs": [
    {"label": "B_0p5T", "db": "setup_a/cooldown_2.db", "run_id": 520,
     "guid": "aaaaaaaa-0000-0000-0000-01924a01c3e1",
     "modified_dimension": "field_T", "value": 0.5, "kwargs": {}},
    {"label": "B_1T",   "db": "setup_a/cooldown_2.db", "run_id": 524,
     "guid": "aaaaaaaa-0000-0000-0000-01924a0e9f02",
     "modified_dimension": "field_T", "value": 1.0, "kwargs": {"t_max_s": 2e-4}}
  ]
}
```

Runs with fixed roles, where nothing is swept:

```json
{
  "analysis": "rb_fidelity",
  "kwargs": {"fit_model": "exp_decay"},
  "runs": [
    {"label": "reference",   "db": "setup_a/cooldown_2.db", "run_id": 412,
     "guid": "aaaaaaaa-0000-0000-0000-01923f8a1b2c",
     "modified_dimension": null, "value": null, "kwargs": {}},
    {"label": "interleaved", "db": "setup_a/cooldown_2.db", "run_id": 413,
     "guid": "aaaaaaaa-0000-0000-0000-01923f8b7d40",
     "modified_dimension": null, "value": null, "kwargs": {"gate": "X90"}}
  ]
}
```

| Key | Type | Rule |
|---|---|---|
| `analysis` | string | Name of a module in `analysis/` |
| `kwargs` | object | Settings for the whole call, routed to the class(es) that declare them (see below). Required, may be `{}` |
| `runs` | array, ≥1 item | The runs this call needs |
| `runs[].label` | string | Unique within the file, pattern `^[A-Za-z0-9_]+$`. How the analysis refers to the run |
| `runs[].db` | string | Path relative to `DATA_ROOT`, ends in `.db` |
| `runs[].run_id` | integer ≥ 1 | Must exist in the run index for that `db` |
| `runs[].guid` | string | QCoDeS guid of the run, lowercase. Must match the run index for `(db, run_id)` |
| `runs[].modified_dimension` | string or null | The quantity varied between runs, snake_case with SI unit suffix as in §7: `field_T`, `temperature_K`, `gate_V`. `null` if nothing is varied |
| `runs[].value` | number or null | Value of `modified_dimension`, in that unit. `null` exactly when `modified_dimension` is `null` |
| `runs[].kwargs` | object | Case-by-case settings for this run's `RunAnalysis`. Required, may be `{}` |

- All keys are required, and no extra keys are allowed at any level (no `note`,
  `description`, `exclude`, ...). Explanations go in the git commit message.
- kwargs values MUST be JSON-native (number, string, bool, null, list, object).
- **kwargs routing:** each class declares the kwargs it accepts in `KWARGS` (§7).
  - A top-level key goes to every class that declares it: the `AccumulatedAnalysis`,
    the `RunAnalysis` (as the default for every run), or both.
  - A per-run key MUST be declared by the `RunAnalysis`, and **overrides** the
    top-level value for that run.
  - A key that no class declares is an error, so typos are caught instead of
    silently falling back to a default.
- `modified_dimension` / `value` describe the run; they are not kwargs. Use one
  unit per dimension within a file (`temperature_K` with `0.015`, not a mix of `K` and `mK`).
  The analysis reads them as `run.modified_dimension` / `run.value` and MUST NOT
  parse physical values out of labels.
- **Failed runs.** Leave out runs that are known to be broken (aborted, wrong
  settings) and say why in the commit message. Keep runs that are valid
  measurements but may fit badly: the analysis reports them with `fit_ok: False`,
  which is evidence too.

### JSON Schema

The source of truth is `wynaut/selection.schema.json`; this copy is for reference.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": ["analysis", "kwargs", "runs"],
  "properties": {
    "analysis": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
    "kwargs":   {"type": "object"},
    "runs": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["label", "db", "run_id", "guid", "modified_dimension", "value", "kwargs"],
        "properties": {
          "label":  {"type": "string", "pattern": "^[A-Za-z0-9_]+$"},
          "db":     {"type": "string", "pattern": "^[^/\\\\:][^\\\\:]*\\.db$"},
          "run_id": {"type": "integer", "minimum": 1},
          "guid":   {"type": "string",
                     "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"},
          "modified_dimension": {"type": ["string", "null"], "pattern": "^[a-z][A-Za-z0-9_]*$"},
          "value":  {"type": ["number", "null"]},
          "kwargs": {"type": "object"}
        }
      }
    }
  }
}
```

Label uniqueness, `modified_dimension`/`value` both set or both null, and the
run-index lookup (including the guid match) are checked in code, not by the schema.
`pytest` checks every selection file in the repo, including the lookup in the committed index.

## 7. Analysis module (step 3)

**Path:** `analysis/<analysis>.py`. The module name is lowercase snake_case.
This is **code**, written by a researcher or an agent; the researcher approves the
method (gate 2).

An analysis has two steps, each written as a subclass of a base class in
`wynaut/base_classes.py`:

```
                RunAnalysis.analyse (3a)                 AccumulatedAnalysis.accumulate (3b)
              ┌──► run "B_0p5T" ──► per-run output ──┐
selection ────┼──► run "B_1T"   ──► per-run output ──┼──► accumulate ──► accumulated output
file          └──► run "B_2T"   ──► per-run output ──┘
```

- **3a `RunAnalysis`**: `analyse(run)` is called once for each run in the
  selection file, on a fresh instance, and sees that one run only.
- **3b `AccumulatedAnalysis`**: `accumulate(runs)` is called once, with the outputs
  of every run. It never sees raw data.

Both return the same format: `{"data": ..., "results": ...}`.

### Required module contents

`analysis/<analysis>.py` MUST define **exactly one** `AccumulatedAnalysis` subclass;
`run_analysis` finds it automatically. Its `RUN_ANALYSIS` is a `RunAnalysis`
subclass, either defined in the same module or imported (e.g. a shared decay fit from
`analysis/_common/`).

```python
import xarray as xr

from wynaut import AccumulatedAnalysis, RunAnalysis


class DecayFit(RunAnalysis):
    """Fit an exponential decay to one run.

    results: tau_s, tau_s_err, fit_ok
    data:    decay  (xr.Dataset: measured trace + fit curve, time in s)
    """

    VERSION = "1.0"
    DATA = "averaged"                                      # or "raw" for shot-by-shot data
    KWARGS = {"fit_model": "exp_decay", "t_max_s": None}   # every accepted kwarg, with default

    def analyse(self, run):
        # run.data is the measured xr.Dataset; settings are in self.kwargs
        ...
        return {"data": {"decay": decay}, "results": {"tau_s": tau, "tau_s_err": err, "fit_ok": ok}}


class DecayVsField(AccumulatedAnalysis):
    """Decay time as a function of magnetic field.

    results: tau_max_s, field_at_tau_max_T, n_runs_used
    data:    tau_vs_field  (xr.Dataset: tau in s vs field in T)
    """

    VERSION = "1.0"
    RUN_ANALYSIS = DecayFit
    REQUIRED_RUNS = None      # tuple of labels (exact set), or None = any labels
    KWARGS = {}

    def accumulate(self, runs):
        ok = sorted((r for r in runs.values() if r.results["fit_ok"]), key=lambda r: r.value)
        tau = xr.Dataset(
            {"tau": ("field", [r.results["tau_s"] for r in ok], {"units": "s"})},
            coords={"field": ("field", [r.value for r in ok], {"units": "T"})},
        )
        i = int(tau.tau.argmax("field")) if ok else None
        return {
            "data": {"tau_vs_field": tau},
            "results": {
                "tau_max_s": float(tau.tau[i]) if ok else float("nan"),
                "field_at_tau_max_T": float(tau.field[i]) if ok else float("nan"),
                "n_runs_used": len(ok),
            },
        }
```

Class attributes:

| Attribute | On | Rule |
|---|---|---|
| `VERSION` | both | str, see §9. MUST be set in the class's own body, never inherited |
| `DATA` | `RunAnalysis` | `"averaged"` (mean ± sem per point, fast, §4) or `"raw"` (shot by shot). Prefer `"averaged"` unless the analysis needs individual shots (histograms, single-shot readout, ...) |
| `KWARGS` | both | dict of every accepted kwarg with its default. Values JSON-native |
| `RUN_ANALYSIS` | `AccumulatedAnalysis` | the `RunAnalysis` subclass for step 3a |
| `REQUIRED_RUNS` | `AccumulatedAnalysis` | tuple of labels the file must contain exactly, or `None` = any labels |
| docstring | both | MUST list every `results` and `data` key of that step, with units |

`self.kwargs` is a read-only mapping holding the resolved settings: `KWARGS`
defaults overridden by the selection file (§6 kwargs routing).

`Run` (3a input) and `RunOutput` (3b input) are provided by `campaign`. They
describe the same run; only `data` differs, and `RunOutput` adds `kwargs` and `results`:

| Attribute | `Run` | `RunOutput` | Meaning |
|---|---|---|---|
| `label` | str | str | from the selection file |
| `db` | str | str | relative db path |
| `run_id` | int | int | |
| `guid` | str | str | QCoDeS guid, checked against the run index |
| `modified_dimension` | str or None | str or None | what was varied, with unit suffix, e.g. `"field_T"` |
| `value` | float or None | float or None | value of `modified_dimension` in that unit |
| `data` | `xr.Dataset` | `dict[str, xr.Dataset]` | `Run`: the measured run, raw or averaged per `DATA`. `RunOutput`: the `"data"` that `analyse` returned |
| `kwargs` | — | dict | the resolved kwargs `RUN_ANALYSIS` used for this run |
| `results` | — | `dict[str, scalar]` | the `"results"` that `analyse` returned |

### What goes in which step

- **`RunAnalysis.analyse`**: everything that needs only one run, such as
  preprocessing, the fit of one decay, the processed trace and its fit curve.
- **`AccumulatedAnalysis.accumulate`**: everything that relates runs to each
  other, such as decay time vs field, a model fitted across the sweep, or gate fidelity
  from a reference and an interleaved decay. A global fit with shared parameters
  also belongs here, and works on the processed traces that `analyse` returned in `"data"`.
- If `accumulate` needs something from a run, `analyse` must return it.
- For a sweep, `accumulate` takes the swept quantity from `run.modified_dimension` /
  `run.value`, sorted by `value`. It does not rely on file order or parse labels.
- `accumulate` decides what to do with runs whose fit failed (`results["fit_ok"]`
  is `False`). Usually it leaves them out and reports how many it used, e.g. `n_runs_used`.
- If there is nothing to accumulate (a single-run analysis), `accumulate` returns
  `{"data": {}, "results": {}}`.

### Rules for both classes

MUST:
- Implement only `analyse` / `accumulate` (plus private helper methods). Never
  override `apply` or `__init__`: they run the checks. Overriding `apply` fails
  at class creation.
- Return a dict with **exactly** the keys `"data"` and `"results"`.
- `"data"`: `dict[str, xr.Dataset]`. Keys are snake_case identifiers (they become
  file names). Each value is an `xr.Dataset`, not a DataArray, numpy array or DataFrame.
  Put units in `attrs["units"]` on variables and coordinates. Typical contents:
  processed traces, fit curves on a dense grid, residuals.
- `"results"`: `dict[str, int | float | str | bool]`. Only scalars: no arrays,
  lists, dicts, numpy scalars (convert with `float()`), or None.
  - Put the SI unit in the key as a suffix: `tau_s`, `field_T`, `freq_Hz`.
    Dimensionless quantities have no suffix: `fidelity`.
  - Uncertainties use the suffix `_err` after the unit: `tau_s_err`.
  - A failed fit returns `float("nan")` values plus `"fit_ok": False`. It does not raise.
- Use the same `results` keys every time for a given class and `VERSION`:
  `analyse` for every run, and `accumulate` for every selection file. Per-run
  results then stack into one table with a row per run, and accumulated results
  into one table with a row per selection file.
- Be deterministic. Seed any randomness from kwargs.

MUST NOT:
- Keep state between calls. Don't store results on `self` or on the class, and
  don't use module-level caches. A `RunAnalysis` instance exists for one run only.
- Add plotting methods, or import matplotlib, plotly or any other plotting
  library. Quick-look plots belong in `figures/`.
- Read or write files, open databases, or touch `DATA_ROOT` / `AVERAGED_ROOT` /
  `OUTPUT_ROOT`. `run_analysis` does all I/O.
- In `analyse`, depend on any other run. Its output for a run depends only on
  that run and its kwargs.
- In `accumulate`, use raw data or redo per-run fits.
- Hard-code run ids, paths or dates.
- Mutate its inputs in place, such as `run.data` (use `.copy()` or build new datasets).

SHOULD:
- Reuse a `RunAnalysis` by importing it, e.g. `DecayVsField` and `DecayVsTemperature`
  both set `RUN_ANALYSIS = DecayFit`. Put shared `RunAnalysis` classes, fit models
  and helpers in `analysis/_common/`.
- Prefer composition (`RUN_ANALYSIS = DecayFit`, helper functions) over subclassing
  another concrete analysis. If you do subclass one, set your own `VERSION`
  (enforced) and remember that changes to the parent change your outputs (§9).
- Read every setting from `self.kwargs`; never `.get()` with a default inside the
  method. Defaults belong in `KWARGS`, so they are recorded in `meta.json`.

### Running

```bash
python -m wynaut.run_analysis selections/decay_vs_field/demo_sweep.json
python -m wynaut.run_analysis selections/decay_vs_field/       # every file in the folder
```

`run_analysis` loads the runs (raw or averaged, per `DATA`) and calls
`AccumulatedAnalysis.apply()`, which creates a fresh `RUN_ANALYSIS` for every
run and then calls `accumulate`. The checks, in order:

1. **Before** (`run_analysis`): the schema in §6, labels unique, `analysis`
   matches the folder name, `modified_dimension`/`value` both set or both null,
   every `(db, run_id)` is in the run index, its `guid` matches the index, and
   an averaged copy exists if `DATA = "averaged"`.
2. **Class** (`base_classes`): exactly one `AccumulatedAnalysis` subclass in the module,
   `VERSION` set in each class's own body, `DATA` valid, docstrings present,
   `RUN_ANALYSIS` is a `RunAnalysis`, labels match `REQUIRED_RUNS`, no kwargs that
   neither class declares in `KWARGS`, and no per-run kwargs that `RUN_ANALYSIS`
   doesn't declare.
3. **After each `analyse`:** keys are exactly `data`/`results`, the types
   above, and the same `results` keys for every run in the file.
4. **After `accumulate`:** keys are exactly `data`/`results`, plus the types above.

Any failure means nothing is saved, not even the per-run outputs. Fix the cause
and never bypass the checks.

## 8. Saved outputs (written only by `run_analysis`)

```
OUTPUT_ROOT/<analysis>/v<VERSION>/<name>/      # VERSION of the AccumulatedAnalysis
├── meta.json             # selection file, guids, both classes and VERSIONs, DATA and
│                         # averaged export_version, resolved kwargs, git commit, timestamp
├── runs/<label>/         # step 3a, one folder per run
│   ├── results.json      #   the "results" dict of analyse
│   └── data/<key>.nc     #   one netCDF file per entry in its "data"
└── accumulated/          # step 3b
    ├── results.json      #   the "results" dict of accumulate
    └── data/<key>.nc     #   one netCDF file per entry in its "data"
```

Existing output folders are never overwritten by hand. To change results,
bump `VERSION` (§9) or rerun through `run_analysis`.

## 9. Versioning

Each class has its own `VERSION`. Bump it whenever a change can alter **any**
output of that class: numbers, keys, fit model, `KWARGS` defaults, `DATA` or
preprocessing. Outputs are filed under the `AccumulatedAnalysis` `VERSION` (§8),
so **when a `RunAnalysis` `VERSION` is bumped, also bump every
`AccumulatedAnalysis` that uses it.** `meta.json` records both versions.
- `"1.0" → "1.1"`: same keys, different numbers (e.g. better initial guess).
- `"1.x" → "2.0"`: keys in `data` or `results` of either step added, removed or renamed.

Pure refactors with identical outputs don't need a bump. If unsure, bump.

## 10. Figures (step 4)

**Path:** `figures/<person>/<script>.py` (or `.ipynb` paired with jupytext).
This is **code**. `figures/paper/` holds the agreed final figures and changes there
need review.

```python
from wynaut.io import load, load_results_table, save_figure

out = load("decay_vs_field", name="demo_sweep", version="1.0")
out["runs"]["B_0p29T"]["data"]["decay"]        # 3a output of one run
out["accumulated"]["results"]["tau_max_s"]    # 3b output

df  = load_results_table("decay_vs_field", version="1.0")              # 3b: one row per selection name
runs_df = load_results_table("decay_vs_field", version="1.0", step="run")
# 3a: one row per run, columns name, label, db, run_id, guid,
#     modified_dimension, value, then the per-run results

save_figure(fig, "alice/tau_vs_field")   # → build/figures/alice/tau_vs_field.png and .pdf
```

- Figure code MUST read analysis outputs only through `wynaut.io`.
- Figure code MUST NOT import from `analysis/`, re-fit, or open `.db` files.
  If a number is missing, add it to the `results` of the right step and bump `VERSION`.
- Always pin `version=`, so a new analysis version never changes an existing figure silently.
- One figure per script, saved with `save_figure(fig, "<person>/<script>")`: the
  name is the script path without `figures/` and `.py`. That name goes under
  `Figures:` in `PLAN.md`, which is how the report finds it.
- A script MUST run top to bottom without user input, because the report
  re-runs it to render the figure fresh.

## 11. Report (step 5)

The report is a **generated** Slidev deck summarising the whole campaign. It is
the place to check progress and to see whether each question succeeded.

```bash
python tools/build_report.py      # renders figures, writes report/slides.md
cd report && npx slidev build     # maintainer: HTML in report/dist/, published
```

The deck has an overview of every question with its progress and `Status`, the
run tracker (below), and one chapter per `##` question in `PLAN.md`:

1. `### Question` and `### Success looks like`, as written in the plan.
2. Progress, computed: planned → runs selected → analysed → figures → outcome.
3. The figures listed under `Figures:`, rendered fresh by running their scripts.
4. A results table for every analysis under `Analyses:`, at its pinned version,
   loaded through `wynaut.io`.
5. `Status` and `### Outcome`, as written in the plan.

- Researchers provide content only through `PLAN.md` (text) and `figures/` (code).
- `report/slides.md` is generated and gitignored: never edit it. Hand-written
  slides (e.g. an introduction) go in `report/pages/` and contain no results numbers.
- Every number in the deck comes from `wynaut.io`, never typed by hand.
- The generator, theme and publishing are maintainer code. Researchers never need Node.
- Hosting is optional: the built deck (`report/dist/`) can be published with GitHub or GitLab Pages,
  so everyone reads the same, current report in the browser.

### Run tracker

`python -m tools.timeline` writes `build/tracker/runs.html`: one square per run
of the index, in start order, one row per hundred runs and a new row each month,
newest on top. Months and dates are on the left, milestones on the right.

- **Status tab.** Each run's status is computed when the page is built, never
  stored: from the selection files, the saved outputs, and hand-set marks.
  `accumulated` (the run and the accumulated analysis of the same selection and
  version succeeded), `analysed`, `selected`, `unprocessed`, `empty` (never
  started), and `failed` (never completed). A mark in `report/run_marks.yaml`
  (`paper`, `failed`, `not_relevant`, by `db` and run ids or `"first-last"`
  ranges, with an optional `note`) wins over all of these.
- **Sensor tab** (only if `project.yaml` has a `sensor:`). Each run coloured by
  `sensor_mean`, linear from 0 to `tracker.sensor_max` in `tracker.sensor_steps`
  steps; above `tracker.sensor_ignore_above` and without a reading it is grey.
- **Milestones** in `report/milestones.yaml` (`date`, in the project's timezone,
  and `text`) go on the row their date falls in, and ring the first run after them.
- `python -m tools.timeline --demo` fills in made-up statuses and sensor values,
  to work on the layout. `python -m tools.index_sensor --batch-days 7 --tracker`
  rebuilds the page after every week of runs it processes.
- The tracker never sets a status by itself that belongs to a person: marks are
  written only when the user asks for them, like `Status` in `PLAN.md`.

## 12. Workflow for common requests

**"I want to find out X." (step 2a)** Ask what the question is, what quantities
(with units) and which measurements are needed, and what result would count as
success or against it. Draft a `##` section in `PLAN.md` with `Status: open`,
`Analyses: none yet`, `Figures: none yet` and an empty `### Outcome`. The
researcher reviews it before it is committed. Never write `### Outcome` or change
`Status` yourself.

**"Find the runs for X." (step 2b)** Start from the `PLAN.md` section. Filter
`load_index()` by `name`, `exp_name`, `sample`, `start_time` and so on, check
promising runs with `describe_run()`, and show the candidates to the user as a
table: `db`, `run_id`, time, settings and why each matches. Flag runs that didn't
complete (`end_time` empty) and gaps against "What we need".
The user confirms which runs to use (gate 1). Only then write the selection
file(s) and run `pytest`.

**"Add a new analysis." (step 3)** Copy `analysis/_template.py` to `analysis/<name>.py`.
Decide what needs only one run (`RunAnalysis`) and what relates runs to each
other (`AccumulatedAnalysis`), choose `DATA`, and confirm the split and the fit
model with the user (gate 2). Check `analysis/_common/` for an existing
`RunAnalysis` to reuse first. Then create `selections/<name>/`, write one
selection file, run it, report the results of both steps, and add the analysis
under `Analyses:` in `PLAN.md` once the user is happy with the results.

**"Change how X is fitted."** Edit the analysis, bump `VERSION`, rerun all
selections for that analysis, and tell the user which figures and `PLAN.md`
entries pin the old version.

**"Make a plot of X." (step 4)** Work in `figures/<person>/`. Use `load` /
`load_results_table` and `save_figure`, and add the figure under `Figures:` in `PLAN.md`.

**"Mark these runs as failed / not relevant / for the paper."** Add an entry to
`report/run_marks.yaml` with `db`, the run ids (ranges as `"first-last"`) and a
`note` saying why, then rebuild the tracker. A run can carry only one mark.

**"Add a milestone."** Add `date` and `text` to `report/milestones.yaml`.

**"How far are we?" / "Build the report." (step 5)** For a quick look, run
`python -m tools.timeline` and summarise the status counts. For the full picture,
run `python tools/build_report.py` and summarise the overview. Point out where
results and `### Success looks like` appear to disagree, as a question to the
owner, never as a verdict.

## 13. Never

- Never write to `DATA_ROOT` (including its sensor logs) or `AVERAGED_ROOT`, or write anything to `OUTPUT_ROOT`
  except through `run_analysis`.
- Never set `Status` or write `### Outcome` in `PLAN.md` on your own; only the researcher does.
- Never change `### Success looks like` after results exist without the owner's
  explicit request.
- Never edit `report/slides.md` or type results numbers into slides.
- Never edit `index/runs.jsonl` by hand; rebuild it with `python -m tools.build_index`
  and `python -m tools.index_sensor`.
- Never edit another person's `figures/<person>/` folder, `PLAN.md` section, or
  another owner's selection files, without the user explicitly asking.
- Never edit `wynaut/` to make a failing check pass.
- Never add keys to the selection format, fixed lines to `PLAN.md`, or keys to the
  output dict "just this once".
- Never commit data files (`.db`, `.nc`, `.parquet`), `build/` or `config.yaml`.

## 14. Checklist before you finish

- [ ] Every `PLAN.md` section has the four fixed lines and four subsections, and `pytest` passes.
- [ ] Every selection file validates against §6 and lives in `selections/<analysis>/`.
- [ ] Every run is given as `(db, run_id)` with `db` relative to `DATA_ROOT`, plus its `guid` from the run index.
- [ ] `modified_dimension` carries an SI unit suffix and `value` is in that unit, or both are `null`.
- [ ] The module defines exactly one `AccumulatedAnalysis` subclass, with `VERSION`, `RUN_ANALYSIS`, `KWARGS` and a docstring listing its output keys with units; the same for its `RunAnalysis`, plus `DATA`.
- [ ] Only `analyse` / `accumulate` are implemented; they return exactly `{"data": {str: xr.Dataset}, "results": {str: scalar}}`, with no plotting, no I/O and no state on `self`.
- [ ] `analyse` uses only its one run; `accumulate` uses only the per-run outputs, never raw data.
- [ ] Every setting comes from `self.kwargs`, with its default in `KWARGS`.
- [ ] `VERSION` is bumped if any output can change, including the `AccumulatedAnalysis` when its `RunAnalysis` was bumped.
- [ ] Figures load through `wynaut.io` with a pinned `version`, save with `save_figure`, and are listed under `Figures:` in `PLAN.md`.
- [ ] Gates were respected: runs confirmed, method approved, verdict left to the researcher.
- [ ] No data files, `build/` or local config are staged in git.
