"""Run tracker: the processing status of every run in the index, as an HTML grid.

    python -m tools.timeline            # writes build/tracker/runs.html
    python -m tools.timeline --demo     # made-up statuses and sensor values, to work on the layout

The status is computed when the table is built, never stored: index/runs.jsonl
stays as the maintainer built it. It comes from the selection files, the saved
outputs, and report/run_marks.yaml, where people mark runs by hand as paper,
failed or not_relevant. build_status_table() returns the run index with three
extra columns:

    status       one of STATUSES, see run_status()
    selections   "<analysis>/<name>" of every selection file the run is in
    note         the note of the run's mark, or ""

The grid has one square per run in start order, ROW_LENGTH per row, and starts
a new row at every month, newest row on top. Left: the months and the date of
each row's first run. Right: the milestones from report/milestones.yaml, on
the row their date falls in. Two tabs colour the same grid: by status, and, if
project.yaml has a sensor, by the mean sensor value during the run (sensor_mean
of the index), in tracker.sensor_steps linear steps from 0 to tracker.sensor_max.
Months, dates and milestones are in the project's timezone.
"""

import argparse
import html
import json
import random
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from wynaut import project
from wynaut.index import load_index
from wynaut.paths import BUILD_DIR, INDEX_PATH, REPO_ROOT

SELECTIONS_DIR = REPO_ROOT / "selections"
MILESTONES_PATH = REPO_ROOT / "report" / "milestones.yaml"
MARKS_PATH = REPO_ROOT / "report" / "run_marks.yaml"
OUT_PATH = BUILD_DIR / "tracker" / "runs.html"

# Display settings, for tinkering. The sensor tab's scale is under tracker: in project.yaml.
ROW_LENGTH = 100
NEWEST_FIRST = True             # newest row on top; squares in a row still run left to right
TIMEZONE = project.timezone()   # months and dates are shown in lab time
SENSOR = project.sensor()       # None: no sensor tab
TRACKER = project.tracker()

# In legend order. Colours are in _CSS.
STATUSES = {
    "accumulated":  "run and accumulated analysis both succeeded",
    "analysed":     "run analysed, accumulated analysis not done yet",
    "selected":     "in a selection file, not analysed successfully yet",
    "not_relevant": "good run, marked not relevant for the analysis",
    "paper":        "standout run, marked for the paper figures",
    "failed":       "failed measurement: marked failed, or never completed",
    "unprocessed":  "complete, not selected or marked",
    "empty":        "never started (no start_time)",
}
MARKS = ("paper", "failed", "not_relevant")   # statuses set by hand in run_marks.yaml


def read_selections(selections_dir: Path = SELECTIONS_DIR) -> pd.DataFrame:
    """One row per run in every selection file: analysis, name, label, db, run_id."""
    rows = []
    for path in sorted(Path(selections_dir).glob("*/*.json")):
        selection = json.loads(path.read_text())
        rows += [{"analysis": selection["analysis"], "name": path.stem, "label": r["label"],
                  "db": r["db"], "run_id": r["run_id"]} for r in selection["runs"]]
    return pd.DataFrame(rows, columns=["analysis", "name", "label", "db", "run_id"])


def _ok(results_path: Path) -> bool:
    """Results count as ok unless they say fit_ok False."""
    return json.loads(results_path.read_text()).get("fit_ok", True) is not False


def read_outputs(output_root: Path, analysis: str, name: str, label: str) -> list[tuple[bool, bool]]:
    """(run ok, accumulated ok) for every saved VERSION of this selection that has
    an output for the run. Accumulated is ok once its results exist and are ok."""
    found = []
    for run in sorted(Path(output_root).glob(f"{analysis}/v*/{name}/runs/{label}/results.json")):
        accumulated = run.parents[2] / "accumulated" / "results.json"
        found.append((_ok(run), accumulated.exists() and _ok(accumulated)))
    return found


def read_marks(index: pd.DataFrame, path: Path = MARKS_PATH) -> dict:
    """{(db, run_id): (mark, note)} from run_marks.yaml. Raises on an unknown mark,
    a run that isn't in the index, or a run marked twice."""
    if not Path(path).exists():
        return {}
    known = set(zip(index["db"], index["run_id"]))
    marks = {}
    for entry in yaml.safe_load(Path(path).read_text()) or []:
        mark, db, note = entry["mark"], entry["db"], str(entry.get("note", ""))
        if mark not in MARKS:
            raise ValueError(f"{path}: mark {mark!r} must be one of {MARKS}")
        for item in entry["runs"]:
            first, _, last = str(item).partition("-")
            for run_id in range(int(first), int(last or first) + 1):
                key = (db, run_id)
                if key not in known:
                    raise ValueError(f"{path}: {key} is not in the run index")
                if key in marks:
                    raise ValueError(f"{path}: {key} is marked twice")
                marks[key] = (mark, note)
    return marks


def run_status(start_time, end_time, outputs: list[tuple[bool, bool]], selected: bool,
               mark: str | None = None) -> str:
    """Status of one run. A mark set by hand wins, then what has been done with
    the run, then what is wrong with its data: an aborted run that was analysed
    shows as analysed."""
    if mark:
        return mark
    if any(run_ok and accumulated_ok for run_ok, accumulated_ok in outputs):
        return "accumulated"
    if any(run_ok for run_ok, _ in outputs):
        return "analysed"
    if selected:
        return "selected"
    if pd.isna(start_time):
        return "empty"
    if pd.isna(end_time):
        return "failed"
    return "unprocessed"


def build_status_table(index: pd.DataFrame | None = None,
                       selections_dir: Path = SELECTIONS_DIR,
                       output_root: Path | None = None,
                       marks_path: Path = MARKS_PATH) -> pd.DataFrame:
    """The run index plus status, selections and note columns. Without
    output_root, no outputs are looked up and selected runs show as selected."""
    df = (load_index() if index is None else index).copy()
    marks = read_marks(df, marks_path)
    outputs, names = {}, {}
    for s in read_selections(selections_dir).itertuples():
        key = (s.db, s.run_id)
        names.setdefault(key, []).append(f"{s.analysis}/{s.name}")
        if output_root is not None:
            outputs.setdefault(key, []).extend(read_outputs(output_root, s.analysis, s.name, s.label))
    keys = list(zip(df["db"], df["run_id"]))
    df["selections"] = [names.get(k, []) for k in keys]
    df["note"] = [marks.get(k, (None, ""))[1] for k in keys]
    df["status"] = [run_status(start, end, outputs.get(k, []), k in names, marks.get(k, (None,))[0])
                    for k, start, end in zip(keys, df["start_time"], df["end_time"])]
    return df


def demo_statuses(status: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    """Made-up statuses for working on the layout: every measurement name of a
    complete run gets one random status, so they come in realistic blocks, and
    a few single runs are marked for the paper."""
    rng = random.Random(seed)
    choices = {"unprocessed": 4, "selected": 2, "analysed": 2, "accumulated": 3,
               "not_relevant": 2, "failed": 1}
    by_name = {name: rng.choices(list(choices), weights=list(choices.values()))[0]
               for name in sorted(status["name"].dropna().unique())}
    df = status.copy()
    complete = df.index[df["status"] == "unprocessed"]
    df.loc[complete, "status"] = df.loc[complete, "name"].map(by_name).fillna("unprocessed")
    df.loc[rng.sample(list(complete), 12), "status"] = "paper"
    return df


def demo_sensor_values(status: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    """Made-up sensor values for working on the layout: per measurement name
    mostly near zero, some spread over the scale, a few above it, some without a log."""
    rng = random.Random(seed)
    top = TRACKER.sensor_max
    df = status.copy()
    level = {}
    for name in sorted(df["name"].dropna().unique()):
        kind = rng.choices(["low", "sweep", "high", "none"], weights=[13, 4, 1, 2])[0]
        level[name] = {"low": 0.003 * top, "sweep": rng.uniform(0.02, 0.95) * top,
                       "high": rng.uniform(1.05, 20) * top, "none": None}[kind]
    for i, name in zip(df.index, df["name"]):
        v = level.get(name)
        if v is None or pd.isna(df.at[i, "start_time"]):
            continue
        mean = v * rng.lognormvariate(0, 0.08)
        df.loc[i, ["sensor_mean", "sensor_min", "sensor_max", "sensor_std", "sensor_n"]] = \
            [mean, 0.97 * mean, 1.03 * mean, 0.01 * mean, rng.randint(1, 30)]
    return df


def sensor_step(value) -> int | None:
    """Colour step of a sensor value, 0 to tracker.sensor_steps - 1, or None
    without a reading or above tracker.sensor_ignore_above."""
    ignore = TRACKER.sensor_ignore_above
    if pd.isna(value) or (ignore is not None and value > ignore):
        return None
    step = int(value * TRACKER.sensor_steps / TRACKER.sensor_max + 1e-9)   # 0.3 is step 1 of 10 to 3
    return min(max(step, 0), TRACKER.sensor_steps - 1)


_PREFIXES = ((1e9, "G"), (1e6, "M"), (1e3, "k"), (1, ""), (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"))


def _quantity(value: float) -> str:
    """A sensor value with its unit, SI-prefixed if it has one: 0.0098 K is "9.8 mK"."""
    unit = SENSOR.unit if SENSOR else ""
    if not unit or value == 0:
        return f"{value:.3g} {unit}".strip()
    factor, prefix = next(((f, p) for f, p in _PREFIXES if abs(value) >= f), _PREFIXES[-1])
    return f"{value / factor:.3g} {prefix}{unit}"


def read_milestones(path: Path = MILESTONES_PATH) -> list[dict]:
    """[{"date": Timestamp in TIMEZONE, "text": str}], sorted by date."""
    if not Path(path).exists():
        return []
    entries = yaml.safe_load(Path(path).read_text()) or []
    milestones = [{"date": pd.Timestamp(str(m["date"])), "text": str(m["text"])} for m in entries]
    for m in milestones:
        m["date"] = (m["date"].tz_localize(TIMEZONE) if m["date"].tzinfo is None
                     else m["date"].tz_convert(TIMEZONE))
    return sorted(milestones, key=lambda m: m["date"])


def grid_rows(status: pd.DataFrame) -> list[tuple[pd.Timestamp, pd.DataFrame]]:
    """(start, runs) per grid row: runs in start order, at most ROW_LENGTH per row,
    a new row at every month, and an empty row for a month without runs. start is
    the time of the row's first run, or the first of the month for an empty row.
    A run that never started is placed after the run before it in its database."""
    df = status.sort_values(["db", "run_id"]).copy()
    df["time"] = df.groupby("db")["start_time"].transform(lambda t: t.ffill().bfill())
    df = df.dropna(subset=["time"]).sort_values(["time", "db", "run_id"], kind="stable")
    df["time"] = df["time"].dt.tz_convert(TIMEZONE)
    months = df["time"].dt.tz_localize(None).dt.to_period("M")
    rows = []
    for month in pd.period_range(months.min(), months.max(), freq="M"):
        runs = df[months == month]
        if runs.empty:
            rows.append((month.start_time.tz_localize(TIMEZONE), runs))
        rows += [(runs["time"].iloc[i], runs.iloc[i:i + ROW_LENGTH])
                 for i in range(0, len(runs), ROW_LENGTH)]
    return rows


def _tip(run) -> str:
    start = "never started" if pd.isna(run.start_time) else \
        run.start_time.tz_convert(TIMEZONE).strftime("%Y-%m-%d %H:%M")
    lines = [f"{run.db} #{run.run_id}", str(run.name), f"{run.exp_name} · {run.sample}",
             start, run.status.replace("_", " ") + (f": {run.note}" if run.note else "")]
    if run.selections:
        lines.append("in " + ", ".join(run.selections))
    if SENSOR:
        lines += _sensor_tip(run)
    return "\n".join(lines)


def _sensor_tip(run) -> list[str]:
    label = SENSOR.label.lower()
    if pd.isna(run.sensor_mean):
        return [f"{label}: no reading"]
    if run.sensor_n == 1:
        lines = [f"{label}: {_quantity(run.sensor_mean)}, nearest reading"]
    else:
        lines = [f"{label}: {_quantity(run.sensor_mean)} mean, {_quantity(run.sensor_min)} to "
                 f"{_quantity(run.sensor_max)}, {int(run.sensor_n)} readings"]
    ignore = TRACKER.sensor_ignore_above
    if ignore is not None and run.sensor_mean > ignore:
        lines[-1] += f" (above {_quantity(ignore)}: shown as no reading)"
    below = SENSOR.below_range
    if below and run.sensor_min <= below.value:
        lines.append(f"  {_quantity(below.value)} readings mean at or below the sensor's range")
    return lines


def render_html(status: pd.DataFrame, milestones: list[dict], title: str = "Run tracker") -> str:
    rows = grid_rows(status)
    # A milestone goes on the last row that starts on or before its date, and
    # rings the first run on or after it.
    notes = [[] for _ in rows]
    marked = set()
    for m in milestones:
        i = max([i for i, (start, _) in enumerate(rows) if start <= m["date"]], default=0)
        notes[i].append(m)
        later = [runs[runs["time"] >= m["date"]] for _, runs in rows[i:]]
        run = next((r.iloc[0] for r in later if len(r)), None)
        if run is not None:
            marked.add((run["db"], run["run_id"]))

    counts = status["status"].value_counts()
    legend = "".join(
        f'<li><i class="s-{s}"></i><b>{s.replace("_", " ")}</b> {counts.get(s, 0)}'
        f'<span>{html.escape(desc)}</span></li>' for s, desc in STATUSES.items())
    sensor_tab, sensor_legend = _sensor_legend(status) if SENSOR else ("", "")

    shown = list(zip(rows, notes))
    if NEWEST_FIRST:
        shown.reverse()
    # One block per month: the month label, rotated, beside that month's rows.
    months = {}
    for (first, row), row_notes in shown:
        cells = "".join(
            f'<i class="s-{r.status} {_step_class(r.sensor_mean)}'
            f'{" mark" if (r.db, r.run_id) in marked else ""}" '
            f'data-tip="{html.escape(_tip(r))}"></i>' for r in row.itertuples()) \
            or '<span class="none">no runs</span>'
        note = "".join(f'<p><span>{m["date"]:%d %b}</span> {html.escape(m["text"])}</p>'
                       for m in row_notes)
        day = f"{first:%a %d}" if len(row) else ""
        months.setdefault(f"{first:%b %Y}", []).append(
            f'<div class="row"><div class="when">{day}</div>'
            f'<div class="cells">{cells}</div><div class="note">{note}</div></div>')
    body = [f'<section class="month"><div class="mlabel"><b>{label}</b></div>'
            f'<div>{"".join(month_rows)}</div></section>' for label, month_rows in months.items()]

    generated = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<title>{html.escape(title)}</title><style>{_CSS}{_sensor_css()}</style></head>'
            f'<body><div class="viz-root view-status" style="--row-length: {ROW_LENGTH}">'
            f'<h1>{html.escape(title)}</h1>'
            f'<p class="sub">{len(status)} runs · one square per run, {ROW_LENGTH} per row, '
            f'new row each month, {"newest" if NEWEST_FIRST else "oldest"} on top · times in {TIMEZONE} · generated {generated}</p>'
            f'<nav class="tabs"><button data-view="status">Status</button>{sensor_tab}</nav>'
            f'<ul class="legend for-status">{legend}</ul>{sensor_legend}'
            f'<div class="head"><div></div><div class="row"><div>date</div><div>runs</div>'
            f'<div>milestones</div></div></div>'
            f'{"".join(body)}</div><div id="tip"></div><script>{_JS}</script></body></html>')


def _sensor_legend(status: pd.DataFrame) -> tuple[str, str]:
    """(tab button, legend) of the sensor tab."""
    steps = status["sensor_mean"].map(sensor_step)
    counts, n = steps.value_counts(), TRACKER.sensor_steps
    width, unit = TRACKER.sensor_max / n, SENSOR.unit
    items = "".join(
        f'<li><i class="t{i}"></i><b>' + (f"{i * width:.3g}–{(i + 1) * width:.3g} {unit}" if i < n - 1
                                          else f"≥ {i * width:.3g} {unit}") +
        f'</b> {counts.get(i, 0)}</li>' for i in range(n))
    ignore = TRACKER.sensor_ignore_above
    items += (f'<li><i class="t-none"></i><b>no reading'
              f'{f" or above {ignore:g} {unit}" if ignore is not None else ""}</b> '
              f'{int(steps.isna().sum())}</li>')
    with_reading = int(status["sensor_mean"].notna().sum())
    legend = (f'<div class="for-sensor"><p class="sub">Mean {html.escape(SENSOR.label.lower())} '
              f'({html.escape(SENSOR.channel)}) during each run, linear from 0 (blue) to '
              f'{TRACKER.sensor_max:g} {unit} (red). {with_reading} of {len(status)} runs have a '
              f'reading.</p><ul class="legend">{items}</ul></div>')
    return f'<button data-view="sensor">{html.escape(SENSOR.label)}</button>', legend


def _step_class(value) -> str:
    step = sensor_step(value)
    return "t-none" if step is None else f"t{step}"


def _sensor_css() -> str:
    """CSS for the sensor tab: tracker.sensor_steps colours, sampled at the step
    centres from tracker.sensor_colors."""
    from matplotlib.colors import LinearSegmentedColormap, to_hex

    n = TRACKER.sensor_steps
    scale = LinearSegmentedColormap.from_list("sensor", TRACKER.sensor_colors)
    colors = [to_hex(scale((i + 0.5) / n)) for i in range(n)]
    css = ".viz-root {" + "".join(f"--t{i}: {c};" for i, c in enumerate(colors)) + "}\n"
    css += "".join(f".view-sensor .cells i.t{i}, .legend i.t{i} "
                   f"{{ background: var(--t{i}); border: 0; }}\n" for i in range(n))
    return css


_CSS = """
.viz-root {
  color-scheme: light;
  --surface-1: #fcfcfb; --text-primary: #0b0b0b; --text-secondary: #52514e; --rule: #e4e3de;
  --unprocessed: #dcdbd5; --accumulated: #015814; --analysed: #3bc54c; --selected: #ffd040;
  --not_relevant: #0554a3; --failed: #e8453f; --paper: #954fd5;
  --empty-ring: #a3a29b; --mark-ring: #0b0b0b;
}
@media (prefers-color-scheme: dark) {
  .viz-root {
    color-scheme: dark;
    --surface-1: #1a1a19; --text-primary: #f0efec; --text-secondary: #c3c2b7; --rule: #2e2e2b;
    --unprocessed: #3b3b38; --accumulated: #16893a; --analysed: #5fd86c; --selected: #feda77;
    --not_relevant: #2a8eff; --failed: #f14e46; --paper: #b45ee8;
    --empty-ring: #6b6a64; --mark-ring: #f0efec;
  }
  body { background: #1a1a19; }
}
body { margin: 0; font: 13px/1.4 system-ui, sans-serif; }
.viz-root { background: var(--surface-1); color: var(--text-primary); padding: 24px 32px;
            min-height: 100vh; box-sizing: border-box; }
h1 { font-size: 20px; margin: 0 0 4px; }
.sub { color: var(--text-secondary); margin: 0 0 16px; }
.legend { list-style: none; padding: 0; margin: 0 0 20px; display: flex; flex-wrap: wrap; gap: 6px 20px; }
.legend li { display: flex; align-items: center; gap: 6px; }
.legend span { color: var(--text-secondary); }
.legend span::before { content: "– "; }
.head, .month { display: grid; grid-template-columns: 16px 1fr; column-gap: 8px; }
.row { display: grid; column-gap: 16px;
       grid-template-columns: 44px calc(var(--row-length) * 10px - 2px) minmax(200px, 1fr); }
.head { color: var(--text-secondary); font-size: 11px; text-transform: uppercase; letter-spacing: .05em;
        padding-bottom: 4px; }
.month { border-top: 1px solid var(--rule); padding: 6px 0; }
.mlabel b { display: block; writing-mode: vertical-rl; transform: rotate(180deg); white-space: nowrap;
            font-size: 12px; font-weight: 600; }
.when { color: var(--text-secondary); font-size: 11px; font-variant-numeric: tabular-nums; }
.cells { display: grid; grid-template-columns: repeat(var(--row-length), 8px); gap: 2px; padding: 1px 0; }
.cells .none { grid-column: 1 / -1; color: var(--text-secondary); font-size: 11px; font-style: italic; }
.note { font-size: 12px; }
.note p { margin: 0; }
.note span { color: var(--text-secondary); font-variant-numeric: tabular-nums; }
i { display: block; width: 8px; height: 8px; border-radius: 1px; box-sizing: border-box; }
.s-unprocessed { background: var(--unprocessed); }
.s-accumulated { background: var(--accumulated); }
.s-analysed { background: var(--analysed); }
.s-selected { background: var(--selected); }
.s-not_relevant { background: var(--not_relevant); }
.s-failed { background: var(--failed); }
.s-paper { background: var(--paper); }
.s-empty { border: 1px solid var(--empty-ring); }
.legend i { width: 12px; height: 12px; border-radius: 2px; }
.view-sensor .cells i.t-none, .legend i.t-none { background: var(--unprocessed); border: 0; }
.view-status .for-sensor, .view-sensor .for-status { display: none; }
.tabs { display: flex; gap: 4px; margin: 0 0 16px; border-bottom: 1px solid var(--rule); }
.tabs button { font: inherit; color: var(--text-secondary); background: none; border: 0;
               border-bottom: 2px solid transparent; padding: 6px 12px; margin-bottom: -1px; cursor: pointer; }
.view-status .tabs [data-view="status"], .view-sensor .tabs [data-view="sensor"] {
  color: var(--text-primary); border-bottom-color: var(--text-primary); font-weight: 600; }
.cells i.mark { outline: 2px solid var(--mark-ring); outline-offset: 1px; }
.cells i:hover { outline: 2px solid var(--mark-ring); }
#tip { position: fixed; pointer-events: none; display: none; white-space: pre; z-index: 1;
       font: 12px/1.4 system-ui, sans-serif; padding: 6px 8px; border-radius: 4px;
       background: #0b0b0b; color: #f0efec; box-shadow: 0 2px 8px rgba(0,0,0,.25); }
"""

_JS = """
const root = document.querySelector(".viz-root");
const show = (view) => {
  root.classList.remove("view-status", "view-sensor");
  root.classList.add(`view-${view}`);
};
document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => {
  show(b.dataset.view);
  history.replaceState(null, "", `#${b.dataset.view}`);
}));
if (location.hash === "#sensor") show("sensor");
const tip = document.getElementById("tip");
document.addEventListener("mouseover", (e) => {
  const t = e.target.dataset && e.target.dataset.tip;
  tip.style.display = t ? "block" : "none";
  if (t) tip.textContent = t;
});
document.addEventListener("mousemove", (e) => {
  const x = Math.min(e.clientX + 12, innerWidth - tip.offsetWidth - 8);
  tip.style.left = x + "px"; tip.style.top = (e.clientY + 14) + "px";
});
"""


def write_page(out: Path = OUT_PATH, index_path: Path = INDEX_PATH,
               milestones: Path = MILESTONES_PATH, marks: Path = MARKS_PATH,
               demo: bool = False, log=print) -> pd.DataFrame:
    """Build the status table and write the tracker page to out. Returns the table."""
    try:
        from wynaut.paths import OUTPUT_ROOT
        output_root = OUTPUT_ROOT
    except FileNotFoundError as err:
        log(f"WARNING: {err}\n  outputs not checked: selected runs show as selected")
        output_root = None
    status = build_status_table(load_index(index_path), output_root=output_root, marks_path=marks)
    if demo:
        status = demo_sensor_values(demo_statuses(status))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(status, read_milestones(milestones),
                               "Run tracker (demo data)" if demo else "Run tracker"),
                   encoding="utf-8")
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--demo", action="store_true", help="made-up statuses and sensor values, for the layout")
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    parser.add_argument("--milestones", type=Path, default=MILESTONES_PATH)
    parser.add_argument("--marks", type=Path, default=MARKS_PATH)
    args = parser.parse_args()
    status = write_page(args.out, milestones=args.milestones, marks=args.marks, demo=args.demo)
    print(status["status"].value_counts().to_string())
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
