"""Generate a small, fictional campaign to try the framework on.

    python -m tools.make_demo                 # writes demo/ (gitignored)
    export WYNAUT_CONFIG=demo/config.yaml     # point the tools at it
    python -m tools.timeline                  # then open build/tracker/runs.html

The demo is a made-up low-temperature lab, matching project.yaml: two cooldowns
of a cryostat with a warm-up in between, about 1700 runs of five kinds of
measurement in QCoDeS-style SQLite databases, and a thermometer log once a
minute. It exercises what real data does: aborted and never-started runs, runs
shorter than the log interval, temperature sweeps, days without a log, a
warm-up far above the tracker's scale, and base temperature below the
thermometer's calibration, where only its resistance is logged.

Everything is generated from a fixed seed, so every machine gets the same
runs and guids, and index/runs.jsonl and the example selection file in the
repo match. To regenerate those after changing this script:

    python -m tools.make_demo --update-repo

Only writes under --out, plus, with --update-repo, index/runs.jsonl and
selections/decay_vs_field/demo_sweep.json.
"""

import argparse
import json
import random
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from wynaut.paths import REPO_ROOT

SEED = 7
TZ = ZoneInfo("Australia/Sydney")   # matches timezone: in project.yaml
FIRST_DAY = datetime(2026, 3, 2, tzinfo=TZ)
DAYS = 91
WARM_UP = (datetime(2026, 4, 11, 9, tzinfo=TZ), datetime(2026, 4, 18, 9, tzinfo=TZ))
LOGGER_OFF = (datetime(2026, 5, 6, tzinfo=TZ).date(), datetime(2026, 5, 7, tzinfo=TZ).date())
BASE_K = 0.0068                     # below the thermometer's calibration (7 mK)
SELECTION = REPO_ROOT / "selections" / "decay_vs_field" / "demo_sweep.json"

# exp_name: (run name, minutes per run (min, max), runs per session (min, max), weight)
KINDS = {
    "decay_vs_field":       ("decay field={:.2f} T", (3, 12), (6, 14), 4),
    "decay_vs_temperature": ("decay T={:.2f} K", (4, 10), (8, 16), 2),
    "spectroscopy":         ("spectrum f={:.3f} GHz", (1, 5), (10, 40), 3),
    "readout_calibration":  ("readout calibration", (0.2, 0.8), (5, 20), 3),
    "noise":                ("noise spectrum", (10, 30), (2, 6), 1),
}


@dataclass
class DemoRun:
    db: str
    exp_name: str
    sample: str
    name: str
    start: datetime | None
    end: datetime | None
    guid: str
    value: float | None = None      # field in T, or set temperature in K


def _sessions(rng):
    """Measurement sessions, (start, exp_name), for every day outside the warm-up."""
    for d in range(DAYS):
        day = FIRST_DAY + timedelta(days=d)
        if WARM_UP[0] - timedelta(days=1) <= day <= WARM_UP[1]:
            if rng.random() < 0.5:                # a noise check while the cryostat is warm
                yield day + timedelta(hours=rng.uniform(10, 16)), "noise"
            continue
        for _ in range(rng.choice([0, 1, 1, 2, 2, 3])):
            start = day + timedelta(hours=rng.uniform(8, 22))
            kind = rng.choices(list(KINDS), weights=[k[3] for k in KINDS.values()])[0]
            yield start, kind


def make_runs(rng) -> list[DemoRun]:
    runs = []
    for start, kind in sorted(_sessions(rng)):
        name, minutes, count, _ = KINDS[kind]
        cooldown = 1 if start < WARM_UP[0] else 2
        n = rng.randint(*count)
        values = {"decay_vs_field": np.linspace(0, 2, n), "decay_vs_temperature": np.linspace(0.05, 2.6, n),
                  "spectroscopy": np.linspace(4.1, 4.3, n)}.get(kind, [None] * n)
        t = start
        for value in values:
            length = timedelta(minutes=rng.uniform(*minutes))
            fate = rng.random()
            run = DemoRun(db=f"setup_a/cooldown_{cooldown}.db", exp_name=kind,
                          sample="sample_a" if cooldown == 1 else "sample_b",
                          name=name.format(value) if value is not None else name,
                          start=None if fate < 0.004 else t,
                          end=None if fate < 0.03 else t + length,
                          guid=str(uuid.UUID(int=rng.getrandbits(128))),
                          value=None if value is None else round(float(value), 4))
            runs.append(run)
            t += length + timedelta(seconds=rng.uniform(5, 90))
    return runs


def write_databases(runs: list[DemoRun], data_root: Path) -> None:
    """One QCoDeS-style database per cooldown, with only the tables the index reads."""
    for db in sorted({r.db for r in runs}):
        path = data_root / db
        path.parent.mkdir(parents=True, exist_ok=True)
        path.unlink(missing_ok=True)
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE experiments (exp_id INTEGER PRIMARY KEY, name TEXT, sample_name TEXT)")
        con.execute("CREATE TABLE runs (run_id INTEGER PRIMARY KEY, exp_id INTEGER, name TEXT, "
                    "result_table_name TEXT, result_counter INTEGER, run_timestamp REAL, "
                    "completed_timestamp REAL, is_completed INTEGER, parameters TEXT, guid TEXT, "
                    "run_description TEXT, snapshot TEXT)")
        experiments = {}
        for run_id, run in enumerate((r for r in runs if r.db == db), 1):
            key = (run.exp_name, run.sample)
            if key not in experiments:
                experiments[key] = len(experiments) + 1
                con.execute("INSERT INTO experiments VALUES (?, ?, ?)", (experiments[key], *key))
            con.execute("INSERT INTO runs VALUES (?, ?, ?, ?, 0, ?, ?, ?, '', ?, '{}', '{}')", (
                run_id, experiments[key], run.name, f"results-{run_id}",
                run.start.timestamp() if run.start else None,
                run.end.timestamp() if run.end else None, run.end is not None, run.guid))
        con.commit()
        con.close()


def temperatures(runs: list[DemoRun], rng) -> np.ndarray:
    """Thermometer temperature in K for every minute from FIRST_DAY on."""
    minutes = DAYS * 24 * 60
    t = BASE_K * np.exp(np.random.default_rng(SEED).normal(0, 0.01, minutes))
    i0 = int((WARM_UP[0] - FIRST_DAY).total_seconds() // 60)
    i1 = int((WARM_UP[1] - FIRST_DAY).total_seconds() // 60)
    ramp = np.sin(np.linspace(0, np.pi, i1 - i0)) ** 0.3
    t[i0:i1] = BASE_K + ramp * 295            # warm up to room temperature and back
    for run in runs:                          # temperature sweeps hold the set temperature
        if run.exp_name == "decay_vs_temperature" and run.start:
            a = int((run.start - FIRST_DAY).total_seconds() // 60)
            b = int(((run.end or run.start + timedelta(minutes=5)) - FIRST_DAY).total_seconds() // 60) + 1
            t[a:b] = run.value * (1 + rng.uniform(-0.01, 0.01))
    return t


def write_logs(temps: np.ndarray, logs: Path) -> None:
    """Daily CH6 T and CH6 R logs, as a Bluefors controller writes them. Below 7 mK
    only the resistance is logged; LOGGER_OFF days have no logs at all."""
    for d in range(DAYS):
        day = (FIRST_DAY + timedelta(days=d)).date()
        if LOGGER_OFF[0] <= day <= LOGGER_OFF[1]:
            continue
        folder = logs / f"{day:%y-%m-%d}"
        folder.mkdir(parents=True, exist_ok=True)
        t_lines, r_lines = [], []
        for m in range(24 * 60):
            stamp = datetime.combine(day, datetime.min.time()) + timedelta(minutes=m, seconds=12)
            local = f"{stamp:%d-%m-%y},{stamp:%H:%M:%S}"
            k = temps[d * 24 * 60 + m]
            r_lines.append(f"{local},{12800 * (0.007 / k) ** 0.12:e}\n")
            if k >= 0.007:
                t_lines.append(f"{local},{k:e}\n")
        (folder / f"CH6 R {day:%y-%m-%d}.log").write_text("".join(r_lines))
        if t_lines:
            (folder / f"CH6 T {day:%y-%m-%d}.log").write_text("".join(t_lines))


def write_selection(runs: list[DemoRun], path: Path = SELECTION) -> None:
    """The example selection file: the first complete field sweep of cooldown 2."""
    from itertools import groupby
    sweeps = [list(g) for _, g in groupby(
        (r for r in runs if r.exp_name == "decay_vs_field" and r.db.endswith("2.db")),
        key=lambda r: r.start.date() if r.start else None)]
    sweep = next(s for s in sweeps if all(r.start and r.end for r in s))
    ids = {r.guid: i for i, r in enumerate((r for r in runs if r.db == sweep[0].db), 1)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"analysis": "decay_vs_field", "kwargs": {}, "runs": [
        {"label": f"B_{r.value:.2f}T".replace(".", "p"), "db": r.db, "run_id": ids[r.guid],
         "guid": r.guid, "modified_dimension": "field_T", "value": r.value, "kwargs": {}}
        for r in sweep]}, indent=2) + "\n")


def write_config(out: Path) -> Path:
    root = out.resolve()
    path = out / "config.yaml"
    path.write_text(f"# Config for the demo campaign, written by tools/make_demo.py.\n"
                    f"data_root: {root / 'data'}\n"
                    f"averaged_root: {root / 'averaged'}\n"
                    f"output_root: {root / 'outputs'}\n")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "demo")
    parser.add_argument("--update-repo", action="store_true",
                        help="also rebuild index/runs.jsonl and the example selection file")
    args = parser.parse_args()

    rng = random.Random(SEED)
    runs = make_runs(rng)
    data_root = args.out / "data"
    write_databases(runs, data_root)
    write_logs(temperatures(runs, rng), data_root / "sensor_logs")
    config = write_config(args.out)
    print(f"wrote {len(runs)} runs and {DAYS} days of sensor logs to {data_root}")
    print(f"wrote {config}")

    if args.update_repo:
        from wynaut.index import build_index, read_index_lines, write_index_lines
        from wynaut.paths import INDEX_PATH
        from wynaut.project import sensor
        from wynaut.sensors import add_sensor_values
        build_index(data_root, log=lambda msg: None)
        lines, _ = add_sensor_values(read_index_lines(), data_root / "sensor_logs", sensor())
        write_index_lines(lines, INDEX_PATH)
        write_selection(runs)
        print(f"updated {INDEX_PATH} and {SELECTION}")
    else:
        print(f"\nnext: export WYNAUT_CONFIG={config} and run python -m tools.timeline")


if __name__ == "__main__":
    main()
