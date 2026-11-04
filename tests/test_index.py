"""build_index reads only small columns, skips what it must, and never loses runs."""

import json
import sqlite3

import pytest

from wynaut.index import (EXCLUDE, build_index, find_databases, load_index, read_index_lines,
                            write_index_lines)
from wynaut.run_analysis import check_in_index
from wynaut.sensors import SENSOR_COLUMNS

GUID = "aaaaaaaa-0000-0000-0000-{:012d}"


def make_db(path, runs, exp=("decay_vs_field", "sample_a")):
    """A minimal database with the QCoDeS runs/experiments columns build_index reads."""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE experiments (exp_id INTEGER PRIMARY KEY, name TEXT, sample_name TEXT)")
    con.execute("CREATE TABLE runs (run_id INTEGER PRIMARY KEY, exp_id INTEGER, name TEXT, "
                "result_table_name TEXT, result_counter INTEGER, run_timestamp REAL, "
                "completed_timestamp REAL, is_completed INTEGER, parameters TEXT, guid TEXT, "
                "run_description TEXT, snapshot TEXT)")
    con.execute("INSERT INTO experiments VALUES (1, ?, ?)", exp)
    for run_id, guid, start, end in runs:
        con.execute("INSERT INTO runs VALUES (?, 1, 'decay', 'results', 0, ?, ?, ?, '', ?, '{}', ?)",
                    (run_id, start, end, end is not None, guid, "x" * 10_000))
    con.commit()
    con.close()


@pytest.fixture
def data_root(tmp_path):
    root = tmp_path / "data"
    make_db(root / "april_2026.db", [(2, GUID.format(2), 1.78e9, 1.78e9 + 60),
                                     (1, GUID.format(1), 1.78e9 - 600, None)])
    make_db(root / "may_2026.db", [(1, GUID.format(3), 1.781e9, 1.781e9 + 5)])
    make_db(root / "september_avg_export.db", [(1, GUID.format(9), 1.79e9, None)])
    make_db(root / "mock.db", [(1, GUID.format(8), 1.79e9, None)])
    make_db(root / "Copies" / "x.db",
            [(1, GUID.format(2), 1.78e9, None)])
    return root


@pytest.fixture(autouse=True)
def project_excludes(monkeypatch):
    """What a project.yaml would add under index: exclude:."""
    monkeypatch.setattr("wynaut.index.exclude_patterns", lambda: EXCLUDE + ("mock.db", "copies/*"))


def test_find_databases(data_root):
    included, excluded = find_databases(data_root)
    assert included == ["april_2026.db", "may_2026.db"]
    assert set(excluded) == {"mock.db", "september_avg_export.db", "Copies/x.db"}


def test_build_index(data_root, tmp_path):
    out = tmp_path / "index" / "runs.jsonl"
    report = build_index(data_root, out, log=lambda msg: None)
    lines = read_index_lines(out)
    assert [(l["db"], l["run_id"]) for l in lines] == [
        ("april_2026.db", 1), ("april_2026.db", 2), ("may_2026.db", 1)]
    assert lines[0] == {"db": "april_2026.db", "run_id": 1, "guid": GUID.format(1),
                        "name": "decay", "exp_name": "decay_vs_field", "sample": "sample_a",
                        "start_time": "2026-05-28T20:16:40+00:00", "end_time": None,
                        **dict.fromkeys(SENSOR_COLUMNS)}
    assert report["indexed"] == {"april_2026.db": 2, "may_2026.db": 1}
    assert report["duplicate_guids"] == []
    assert "x" * 100 not in out.read_text()  # snapshots never end up in the index


def test_unmerged_wal_keeps_previous_lines(data_root, tmp_path):
    out = tmp_path / "runs.jsonl"
    build_index(data_root, out, log=lambda msg: None)
    (data_root / "may_2026.db-wal").write_bytes(b"\0" * 100)

    report = build_index(data_root, out, log=lambda msg: None)
    assert "WAL not merged" in report["failed"]["may_2026.db"]
    assert report["kept_previous"] == {"may_2026.db": 1}
    assert ("may_2026.db", 1) in {(l["db"], l["run_id"]) for l in read_index_lines(out)}


def test_empty_wal_is_fine(data_root, tmp_path):
    (data_root / "may_2026.db-wal").write_bytes(b"")
    report = build_index(data_root, tmp_path / "runs.jsonl", log=lambda msg: None)
    assert report["failed"] == {}


def test_duplicate_guids_reported(data_root, tmp_path):
    make_db(data_root / "june_2026.db", [(5, GUID.format(3), 1.782e9, None)])
    report = build_index(data_root, tmp_path / "runs.jsonl", log=lambda msg: None)
    assert report["duplicate_guids"] == [(("june_2026.db", 5), ("may_2026.db", 1))]


def test_load_index(data_root, tmp_path):
    out = tmp_path / "runs.jsonl"
    build_index(data_root, out, log=lambda msg: None)
    df = load_index(out)
    assert list(df.columns) == ["db", "run_id", "guid", "name", "exp_name", "sample",
                                "start_time", "end_time", *SENSOR_COLUMNS]
    assert str(df.start_time.dt.tz) == "UTC"
    assert df.end_time.isna().sum() == 1
    assert df.sensor_mean.dtype == float and df.sensor_mean.isna().all()
    assert str(df.sensor_n.dtype) == "Int64"


def test_rebuild_keeps_sensor_values_of_unchanged_runs(data_root, tmp_path):
    """Sensor values come from tools/index_sensor; a rebuild must not wipe them,
    but drops them for a run whose end_time changed (it was still running)."""
    out = tmp_path / "runs.jsonl"
    build_index(data_root, out, log=lambda msg: None)
    temps = {"sensor_min": 0.007, "sensor_max": 0.009,
             "sensor_mean": 0.008, "sensor_std": 0.0005, "sensor_n": 3}
    write_index_lines([{**l, **temps} for l in read_index_lines(out)], out)
    con = sqlite3.connect(data_root / "april_2026.db")
    con.execute("UPDATE runs SET completed_timestamp = run_timestamp + 60 WHERE run_id = 1")
    con.commit()
    con.close()

    build_index(data_root, out, log=lambda msg: None)
    lines = {(l["db"], l["run_id"]): l for l in read_index_lines(out)}
    assert all(lines[("april_2026.db", 1)][c] is None for c in SENSOR_COLUMNS)
    assert {c: lines[("april_2026.db", 2)][c] for c in SENSOR_COLUMNS} == temps
    assert {c: lines[("may_2026.db", 1)][c] for c in SENSOR_COLUMNS} == temps


def test_check_in_index():
    index = [{"db": "a.db", "run_id": 1, "guid": GUID.format(1)}]
    selection = {"runs": [{"label": "x", "db": "a.db", "run_id": 1, "guid": GUID.format(1)}]}
    check_in_index(selection, index)
    selection["runs"][0]["guid"] = GUID.format(2)
    with pytest.raises(ValueError, match="does not match"):
        check_in_index(selection, index)
    selection["runs"][0]["run_id"] = 7
    with pytest.raises(ValueError, match="not in the run index"):
        check_in_index(selection, index)


def test_read_with_wal_opt_in(data_root, tmp_path, monkeypatch):
    """A listed database is read with its WAL; runs that exist only in the WAL appear."""
    import shutil
    live = tmp_path / "live" / "wal_2026.db"
    make_db(live, [(1, GUID.format(5), 1.78e9, None)])
    writer = sqlite3.connect(live, isolation_level=None)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.execute("INSERT INTO runs VALUES (2, 1, 'decay', 'r', 0, 1.78e9, NULL, 0, '', ?, '{}', '')",
                   (GUID.format(6),))
    for suffix in ("", "-wal", "-shm"):     # copy while the writer still holds the WAL
        shutil.copy(f"{live}{suffix}", data_root / f"wal_2026.db{suffix}")
    writer.close()

    out = tmp_path / "runs.jsonl"
    report = build_index(data_root, out, log=lambda msg: None)
    assert "WAL not merged" in report["failed"]["wal_2026.db"]

    monkeypatch.setattr("wynaut.index.READ_WITH_WAL", ("wal_2026.db",))
    report = build_index(data_root, out, log=lambda msg: None)
    assert report["indexed"]["wal_2026.db"] == 2   # run 2 lives only in the WAL
