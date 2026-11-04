"""Sensor values per run: local time to UTC, window statistics, fallbacks, below range.

The sensor is the cryostat thermometer of the demo project: logged in Sydney
time, and below 7 mK only as a resistance."""

import json
import subprocess
import sys
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from wynaut.paths import REPO_ROOT
from wynaut.project import BelowRange, Sensor
from wynaut.sensors import SENSOR_COLUMNS, add_sensor_values, days_needed, log_path, read_log

SENSOR = Sensor(channel="CH6 T", unit="K", timezone="Australia/Sydney",
                below_range=BelowRange(channel="CH6 R", at_least=12800, value=0.007))


def write_log(root, day, readings):
    """readings: [("HH:MM:SS", kelvin)] for one local day, written as a Bluefors cryostat controller does."""
    path = log_path(root, day, SENSOR)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{day:%d-%m-%y},{t},{v:e}\n" for t, v in readings))
    return path


def minutes(start, n, kelvin):
    """n readings one minute apart from local time start ("HH:MM:SS")."""
    t0 = datetime.strptime(start, "%H:%M:%S")
    return [((t0 + timedelta(minutes=i)).strftime("%H:%M:%S"), k)
            for i, k in zip(range(n), np.broadcast_to(kelvin, n))]


def line(start, end, guid="g"):
    return {"guid": guid, "start_time": start, "end_time": end}


@pytest.fixture
def logs(tmp_path):
    """Aug 4 10:00-10:09 Sydney (AEST, UTC+10) = 00:00-00:09 UTC, temperatures 10..19 mK;
    and Aug 5 23:58 to Aug 6 00:01 Sydney across midnight, at 7 mK."""
    root = tmp_path / "sensor_logs"
    write_log(root, date(2026, 8, 4), minutes("10:00:00", 10, np.arange(10, 20) * 1e-3))
    write_log(root, date(2026, 8, 5), minutes("23:58:00", 2, 7e-3))
    write_log(root, date(2026, 8, 6), minutes("00:00:00", 2, 7e-3))
    return root


def test_read_log_converts_sydney_time_to_utc(logs):
    readings = read_log(log_path(logs, date(2026, 8, 4), SENSOR), SENSOR)
    assert readings.index[0] == pd.Timestamp("2026-08-04T00:00:00Z")
    assert readings.iloc[0] == pytest.approx(10e-3)
    assert len(readings) == 10


def test_read_log_daylight_saving_end(tmp_path):
    """On 2026-04-05 Sydney clocks go from 03:00 AEDT back to 02:00 AEST: 02:30 occurs twice."""
    day = date(2026, 4, 5)
    path = write_log(tmp_path, day, [("01:30:00", 1.0), ("02:30:00", 2.0), ("02:30:00", 3.0),
                                     ("03:30:00", 4.0)])
    readings = read_log(path, SENSOR)
    assert list(readings.index) == [pd.Timestamp(t) for t in (
        "2026-04-04T14:30Z", "2026-04-04T15:30Z", "2026-04-04T16:30Z", "2026-04-04T17:30Z")]


def test_empty_log(tmp_path):
    path = write_log(tmp_path, date(2026, 8, 4), [])
    assert read_log(path, SENSOR).empty


def test_stats_over_the_run_window(logs):
    [out], report = add_sensor_values(
        [line("2026-08-04T00:02:00+00:00", "2026-08-04T00:05:00+00:00")], logs, SENSOR)
    window = np.array([12, 13, 14, 15]) * 1e-3          # both ends inclusive
    assert out["sensor_min"] == pytest.approx(12e-3)
    assert out["sensor_max"] == pytest.approx(15e-3)
    assert out["sensor_mean"] == pytest.approx(window.mean())
    assert out["sensor_std"] == pytest.approx(window.std())
    assert out["sensor_n"] == 4
    assert report["window"] == 1


def test_run_across_local_midnight_reads_both_days(logs):
    """Aug 5 23:58 Sydney is 13:58 UTC; the run ends Aug 6 00:01 Sydney."""
    [out], _ = add_sensor_values(
        [line("2026-08-05T13:58:00+00:00", "2026-08-05T14:01:00+00:00")], logs, SENSOR)
    assert out["sensor_n"] == 4
    assert out["sensor_std"] == 0.0


@pytest.mark.parametrize("start, end, expected", [
    ("2026-08-04T00:03:20+00:00", "2026-08-04T00:03:50+00:00", 13e-3),  # short: 00:03 is nearest
    ("2026-08-04T00:03:40+00:00", "2026-08-04T00:03:50+00:00", 14e-3),  # short: 00:04 is nearest
    ("2026-08-04T00:03:20+00:00", None, 13e-3),                         # never completed
    ("2026-08-04T00:10:30+00:00", None, 19e-3),                         # after the last reading
])
def test_no_reading_in_window_takes_nearest_to_start(logs, start, end, expected):
    [out], report = add_sensor_values([line(start, end)], logs, SENSOR)
    assert out["sensor_mean"] == pytest.approx(expected)
    assert out["sensor_min"] == out["sensor_max"] == out["sensor_mean"]
    assert out["sensor_std"] == 0.0
    assert out["sensor_n"] == 1
    assert report["nearest"] == 1


@pytest.mark.parametrize("start, end", [
    ("2026-08-04T00:12:00+00:00", "2026-08-04T00:13:00+00:00"),  # nearest reading 3 min away
    ("2026-07-01T00:00:00+00:00", "2026-07-01T01:00:00+00:00"),  # no log for that day
    (None, None),                                                 # never started
])
def test_no_reading_nearby_is_null(logs, start, end):
    [out], report = add_sensor_values([line(start, end)], logs, SENSOR)
    assert all(out[c] is None for c in SENSOR_COLUMNS)
    assert report["none"] == 1


def test_partial_coverage_uses_the_readings_that_exist(logs):
    [out], _ = add_sensor_values(
        [line("2026-08-04T00:08:00+00:00", "2026-08-04T03:00:00+00:00")], logs, SENSOR)
    assert out["sensor_n"] == 2


def test_missing_days_reported(logs):
    _, report = add_sensor_values(
        [line("2026-08-04T00:00:00+00:00", "2026-08-04T00:01:00+00:00"),
         line("2026-07-01T00:00:00+00:00", "2026-07-01T00:01:00+00:00")], logs, SENSOR)
    assert report["days_missing"] == [date(2026, 7, 1)]


def test_days_needed_in_local_time():
    """14:30 UTC on Aug 4 is 00:30 on Aug 5 in Sydney; 2 min before 00:01 is still Aug 4."""
    assert days_needed([line("2026-08-04T14:30:00+00:00", None)], SENSOR) == [date(2026, 8, 5)]
    assert days_needed([line("2026-08-04T14:01:00+00:00", "2026-08-04T14:05:00+00:00")], SENSOR) == [
        date(2026, 8, 4), date(2026, 8, 5)]


def test_input_lines_not_modified(logs):
    lines = [line("2026-08-04T00:02:00+00:00", "2026-08-04T00:05:00+00:00")]
    add_sensor_values(lines, logs, SENSOR)
    assert set(lines[0]) == {"guid", "start_time", "end_time"}


def test_tool_writes_only_out(logs, tmp_path):
    index = tmp_path / "runs.jsonl"
    run = {"db": "a.db", "run_id": 1, "guid": "g", "name": "n", "exp_name": "e", "sample": "s",
           "start_time": "2026-08-04T00:02:00+00:00", "end_time": "2026-08-04T00:05:00+00:00"}
    index.write_text(json.dumps(run) + "\n")
    out = tmp_path / "out.jsonl"
    result = subprocess.run(
        [sys.executable, "-m", "tools.index_sensor", "--sensor-logs", str(logs),
         "--index", str(index), "--out", str(out)],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    assert "1 with readings during the run" in result.stdout
    assert json.loads(index.read_text()) == run
    assert json.loads(out.read_text())["sensor_n"] == 4


def test_below_range_channel_stands_in_for_missing_readings(tmp_path):
    """Aug 4, 10:00-10:04 Sydney: T logged for the first two minutes only. Then R
    alone, at or above at_least twice and below it once (unknown, dropped)."""
    day, root = date(2026, 8, 4), tmp_path / "sensor_logs"
    write_log(root, day, minutes("10:00:00", 2, 9e-3))
    r_path = log_path(root, day, SENSOR, "CH6 R")
    r_path.write_text("".join(f"04-08-26,10:0{m}:00,{r:e}\n"
                              for m, r in enumerate([12000, 12100, 13200, 13300, 9000])))
    [out], report = add_sensor_values([line("2026-08-04T00:00:00Z", "2026-08-04T00:04:00Z")], root, SENSOR)
    assert out["sensor_n"] == 4                     # 2 logged + 2 below range
    assert out["sensor_min"] == 0.007
    assert out["sensor_mean"] == pytest.approx((9e-3 * 2 + 7e-3 * 2) / 4)


def test_day_with_only_the_below_range_channel_is_not_missing(tmp_path):
    day, root = date(2026, 8, 4), tmp_path / "sensor_logs"
    r_path = log_path(root, day, SENSOR, "CH6 R")
    r_path.parent.mkdir(parents=True)
    r_path.write_text("04-08-26,10:00:00,1.32e4\n04-08-26,10:01:00,1.32e4\n")
    [out], report = add_sensor_values([line("2026-08-04T00:00:00Z", "2026-08-04T00:01:00Z")], root, SENSOR)
    assert report["days_missing"] == []
    assert out["sensor_mean"] == 0.007 and out["sensor_n"] == 2


def test_without_below_range_other_channels_are_ignored(tmp_path):
    day, root = date(2026, 8, 4), tmp_path / "sensor_logs"
    r_path = log_path(root, day, SENSOR, "CH6 R")
    r_path.parent.mkdir(parents=True)
    r_path.write_text("04-08-26,10:00:00,1.32e4\n")
    plain = Sensor(channel="CH6 T", timezone="Australia/Sydney")
    [out], report = add_sensor_values([line("2026-08-04T00:00:00Z", "2026-08-04T00:01:00Z")], root, plain)
    assert report["days_missing"] == [day] and out["sensor_n"] is None


def test_other_log_formats(tmp_path):
    """A logger writing one file per channel and month, with ISO dates, in UTC."""
    sensor = Sensor(channel="pressure", unit="mbar", file_pattern="{channel}_{day:%Y-%m}.csv",
                    datetime_format="%Y-%m-%d %H:%M:%S", timezone="UTC")
    (tmp_path / "pressure_2026-08.csv").write_text(
        "2026-08-04,10:00:00,1.0e-6\n2026-08-04,10:01:00,3.0e-6\n")
    [out], _ = add_sensor_values([line("2026-08-04T10:00:00Z", "2026-08-04T10:01:00Z")], tmp_path, sensor)
    assert out["sensor_mean"] == pytest.approx(2e-6) and out["sensor_n"] == 2
