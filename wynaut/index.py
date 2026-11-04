"""Step 1: the run index, one JSON line per run, committed to git at index/runs.jsonl.

Built by the maintainer with tools/build_index.py. Agents search it to find runs
(step 2b), and pytest checks every selection file against it, so a selection
always matches the index of the same commit. It holds only the small columns of
each database's runs table, never snapshots or run descriptions:

    db           path relative to DATA_ROOT, POSIX, e.g. "setup_a/april.db"
    run_id       int
    guid         str
    name         measurement name
    exp_name     experiment name
    sample       sample name
    start_time   ISO 8601 in UTC, or null if the run never started
    end_time     ISO 8601 in UTC, or null if the run didn't complete
    sensor_min, sensor_max, sensor_mean, sensor_std, sensor_n
                 the logged sensor quantity of project.yaml during the run (e.g.
                 a cryostat temperature), in its unit; null where no log covers
                 it or the project has no sensor. Filled in by
                 tools/index_sensor.py (wynaut/sensors.py)

The database format is QCoDeS's SQLite layout (tables runs and experiments);
qcodes itself is not needed. For other sources, write a reader that returns
the same columns as read_runs().

Lines are sorted by (db, run_id), so a rebuild only adds lines for new runs. A
rebuild keeps the sensor columns of runs whose start and end are unchanged;
new or finished runs get them on the next tools/index_sensor.py.
"""

import fnmatch
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from wynaut.paths import INDEX_PATH
from wynaut.project import project
from wynaut.sensors import SENSOR_COLUMNS

RUN_COLUMNS = ("db", "run_id", "guid", "name", "exp_name", "sample", "start_time", "end_time")
COLUMNS = RUN_COLUMNS + SENSOR_COLUMNS

# Databases under DATA_ROOT that are not indexed: case-insensitive glob patterns
# on the path relative to DATA_ROOT ("*" also matches "/"). These two always
# apply; add your own under index: exclude: in project.yaml, e.g. mock data,
# copies of runs (duplicate guids) or broken databases.
EXCLUDE = (
    "*avg*",        # averaged exports, replaced by wynaut.averaged
    "*unmerged*",   # kept as backup before a WAL merge
)

# Databases whose WAL hasn't been merged into the .db, read anyway with the WAL
# included. Read-only and correct, but slow: without write access SQLite scans the
# whole WAL on every open. Only list a database that nothing writes to any more and
# that has no merged copy elsewhere under DATA_ROOT, or its runs are indexed twice.
# Listed under index: read_with_wal: in project.yaml.
READ_WITH_WAL: tuple[str, ...] = ()


def exclude_patterns() -> tuple[str, ...]:
    return EXCLUDE + tuple((project().get("index") or {}).get("exclude") or ())


def read_with_wal() -> tuple[str, ...]:
    return READ_WITH_WAL + tuple((project().get("index") or {}).get("read_with_wal") or ())

# Only columns stored before run_description and snapshot in each row, so SQLite
# never loads those (often large) values.
_QUERY = """
    SELECT r.run_id, r.guid, r.name, e.name, e.sample_name,
           r.run_timestamp, r.completed_timestamp
    FROM runs AS r JOIN experiments AS e ON r.exp_id = e.exp_id
    ORDER BY r.run_id
"""


def _iso(timestamp):
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(timespec="seconds")


def find_databases(data_root, exclude: tuple[str, ...] | None = None) -> tuple[list[str], list[str]]:
    """(included, excluded): every .db under data_root, relative POSIX paths,
    sorted. exclude defaults to exclude_patterns()."""
    root = Path(data_root)
    patterns = exclude_patterns() if exclude is None else exclude
    found = sorted(p.relative_to(root).as_posix() for p in root.rglob("*.db"))
    excluded = [db for db in found
                if any(fnmatch.fnmatch(db.lower(), pattern.lower()) for pattern in patterns)]
    return [db for db in found if db not in excluded], excluded


def read_runs(path: Path, db: str) -> list[dict]:
    """Index lines of one database.

    Opened with immutable=1: read-only, no locks, nothing written next to the
    file. That is only correct if the WAL is empty, so a database with a
    non-empty WAL is refused rather than read incompletely, unless it is listed
    in read_with_wal(): then it is opened read-only with its WAL (mode=ro).
    """
    wal = Path(f"{path}-wal")
    mode = "immutable=1"
    if wal.exists() and wal.stat().st_size > 0:
        if db not in read_with_wal():
            raise RuntimeError(f"WAL not merged into the .db ({wal.stat().st_size / 1e9:.1f} GB); "
                               "needs a checkpoint by someone with write access")
        mode = "mode=ro"
    con = sqlite3.connect(f"{path.resolve().as_uri()}?{mode}", uri=True)
    try:
        rows = con.execute(_QUERY).fetchall()
    finally:
        con.close()
    return [dict(zip(RUN_COLUMNS, (db, run_id, guid, name, exp_name, sample,
                               _iso(start), _iso(end))))
            for run_id, guid, name, exp_name, sample, start, end in rows]


def read_index_lines(path: Path = INDEX_PATH) -> list[dict]:
    if not Path(path).exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_index_lines(lines, out: Path = INDEX_PATH) -> None:
    """Write the index atomically, with every column of COLUMNS (null if absent)."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        for line in lines:
            f.write(json.dumps({c: line.get(c) for c in COLUMNS}, ensure_ascii=False) + "\n")
    tmp.replace(out)


def _keep_sensor_values(lines, previous) -> None:
    """Copy the sensor columns from the previous index, for runs whose
    guid, start_time and end_time are unchanged."""
    old = {(l["guid"], l["start_time"], l["end_time"]): l for l in previous}
    for line in lines:
        match = old.get((line["guid"], line["start_time"], line["end_time"]), {})
        line.update({c: match.get(c) for c in SENSOR_COLUMNS})


def build_index(data_root, out: Path = INDEX_PATH, log=print) -> dict:
    """Scan every .db under data_root and write the index to out.

    A database that can't be read keeps its lines from the previous index, so a
    failed read never removes runs. Returns a report of what happened.
    """
    root = Path(data_root)
    included, excluded = find_databases(root)
    previous = {}
    previous_lines = read_index_lines(out)
    for line in previous_lines:
        previous.setdefault(line["db"], []).append(line)

    lines, report = [], {"indexed": {}, "kept_previous": {}, "failed": {},
                         "excluded": excluded}
    for db in included:
        try:
            runs = read_runs(root / db, db)
            report["indexed"][db] = len(runs)
            log(f"  {db}: {len(runs)} runs")
        except (RuntimeError, sqlite3.Error, OSError) as err:
            runs = previous.get(db, [])
            report["failed"][db] = str(err)
            if runs:
                report["kept_previous"][db] = len(runs)
            log(f"  {db}: FAILED ({err}); kept {len(runs)} runs from the previous index")
        lines += runs

    lines.sort(key=lambda r: (r["db"], r["run_id"]))
    _keep_sensor_values(lines, previous_lines)
    first, duplicates = {}, []
    for r in lines:
        key = (r["db"], r["run_id"])
        if r["guid"] in first:
            duplicates.append((first[r["guid"]], key))
        else:
            first[r["guid"]] = key
    report["duplicate_guids"] = duplicates

    write_index_lines(lines, out)
    report["total_runs"] = len(lines)
    return report


def load_index(path: Path = INDEX_PATH):
    """The run index as a pandas DataFrame, with start_time / end_time as UTC
    datetimes. Sensor columns are NaN where no sensor log covers the run."""
    import pandas as pd

    df = pd.DataFrame(read_index_lines(path), columns=list(COLUMNS))
    for col in ("start_time", "end_time"):
        df[col] = pd.to_datetime(df[col], utc=True)
    for col in SENSOR_COLUMNS:
        df[col] = df[col].astype("Int64" if col == "sensor_n" else float)
    return df


def describe_run(db: str, run_id: int) -> str:
    """Readable summary of one run, for checking a candidate before it is
    selected: parameters and shapes, key snapshot values, start/end time,
    completed or aborted. Opens the .db read-only."""
    raise NotImplementedError
