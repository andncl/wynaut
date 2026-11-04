"""Merge a QCoDeS database's WAL into its .db (maintainer, needs write access).

    python merge_wal.py                                # every .db next to this script
                                                       #   that has a non-empty -wal
    python merge_wal.py <path to .db> [<path> ...]     # or these databases

Needs only Python's standard library, so it can be copied to any machine: put it
in the folder with the databases (each .db together with its -wal, and -shm if
there is one) and run it there. Work on copies on a local disk, not on the only
copy and not on a network drive.
For each database it:
  1. opens it with an exclusive lock: fails at once if anything else has it
     open, and keeps SQLite away from the -shm file, which is unreliable on
     network drives
  2. counts runs, the highest run_id and the total result rows, WAL included
  3. runs PRAGMA wal_checkpoint(TRUNCATE): copies every page from the WAL into
     the .db, then empties the WAL. If it is interrupted, nothing is lost: the
     WAL is only emptied after every page has been copied, so just rerun it.
  4. reopens read-only and checks the same numbers, the last runs' results
     tables, and that the WAL is now empty
It changes nothing else. Prints RESULT: OK or RESULT: CHECK MANUALLY per database.
"""

import os
import platform
import sqlite3
import sys
import time
from pathlib import Path


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


def summary(con):
    n, max_id = con.execute("SELECT count(*), max(run_id) FROM runs").fetchone()
    rows = con.execute("SELECT coalesce(sum(result_counter), 0) FROM runs").fetchone()[0]
    return {"runs": n, "max_run_id": max_id, "result_rows": rows}


def last_runs_ok(con, k=5):
    """(run_id, result_counter, rows in its results table, match) for the last k runs."""
    out = []
    for run_id, table, counter in con.execute(
            "SELECT run_id, result_table_name, result_counter FROM runs "
            "ORDER BY run_id DESC LIMIT ?", (k,)).fetchall():
        rows = con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
        out.append((run_id, counter, rows, rows == counter))
    return out


def write_access_problems(path: Path, wal: Path) -> list[str]:
    """Open each file with write access, writing nothing. Returns what failed."""
    problems = []
    for f in (path, wal):
        try:
            with open(f, "r+b"):
                pass
        except OSError as err:
            problems.append(f"{f.name}: no write access ({err.__class__.__name__}, "
                            f"winerror {getattr(err, 'winerror', None)}: {err.strerror}; "
                            f"read-only attribute: {not os.access(f, os.W_OK)})")
    return problems


def merge(path: Path) -> bool:
    wal = Path(f"{path}-wal")
    if not wal.exists() or wal.stat().st_size == 0:
        log(f"=== {path.name}: no WAL to merge")
        return True
    log(f"=== {path.name}: db {path.stat().st_size / 1e9:.1f} GB, "
        f"wal {wal.stat().st_size / 1e9:.1f} GB")

    problems = write_access_problems(path, wal)
    if problems:
        for p in problems:
            log(f"ERROR {p}")
        log("RESULT: CHECK MANUALLY (no write access, nothing was merged)")
        return False

    step = "open"
    try:
        con = sqlite3.connect(path, isolation_level=None, timeout=0)
        step = "PRAGMA locking_mode=EXCLUSIVE"
        con.execute("PRAGMA locking_mode=EXCLUSIVE")
        step = "PRAGMA journal_mode"
        mode = con.execute("PRAGMA journal_mode").fetchone()[0]
    except sqlite3.Error as err:
        log(f"ERROR at step '{step}': {getattr(err, 'sqlite_errorname', '')} {err}")
        log("RESULT: CHECK MANUALLY (nothing was merged)")
        return False
    if mode != "wal":
        log(f"journal_mode is {mode!r}, not 'wal': not touching it")
        con.close()
        return False

    log("taking the exclusive lock and reading the WAL (can take a long time)...")
    t0 = time.time()
    con.execute("BEGIN EXCLUSIVE")  # 'database is locked' if anything else has it open
    before = summary(con)
    con.execute("COMMIT")
    log(f"before: {before}  ({(time.time() - t0) / 60:.1f} min)")

    log("merging: PRAGMA wal_checkpoint(TRUNCATE)...")
    t0 = time.time()
    busy, frames, done = con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    log(f"checkpoint: busy={busy}, wal_frames={frames}, checkpointed={done} "
        f"({(time.time() - t0) / 60:.1f} min)")
    con.close()
    if busy:
        log("RESULT: CHECK MANUALLY (checkpoint was blocked, WAL left as it was)")
        return False

    con = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    after = summary(con)
    tail = last_runs_ok(con)
    con.close()
    wal_size = wal.stat().st_size if wal.exists() else 0
    log(f"after:  {after}")
    log(f"last runs (run_id, result_counter, rows, ok): {tail}")
    log(f"db now {path.stat().st_size / 1e9:.1f} GB, wal now {wal_size} bytes")
    ok = after == before and all(t[3] for t in tail) and wal_size == 0
    log("RESULT: OK" if ok else "RESULT: CHECK MANUALLY")
    return ok


def databases_with_wal(folder: Path) -> list[Path]:
    """Every .db in folder whose -wal exists and is not empty."""
    return [p for p in sorted(folder.glob("*.db"))
            if Path(f"{p}-wal").exists() and Path(f"{p}-wal").stat().st_size > 0]


if __name__ == "__main__":
    log(f"python {platform.python_version()}, sqlite {sqlite3.sqlite_version}, {platform.platform()}")
    if len(sys.argv) > 1:
        targets = sys.argv[1:]
    else:
        here = Path(__file__).resolve().parent
        targets = databases_with_wal(here)
        log(f"looking in {here}: {len(targets)} database(s) with a WAL to merge: "
            f"{[p.name for p in targets]}")
        if not targets:
            sys.exit(0)
    results = []
    for arg in targets:
        try:
            results.append(merge(Path(arg)))
        except sqlite3.Error as err:
            log(f"ERROR on {arg}: {getattr(err, 'sqlite_errorname', '')} {err}  "
                "(nothing was merged for this file)")
            results.append(False)
    sys.exit(0 if all(results) else 1)
