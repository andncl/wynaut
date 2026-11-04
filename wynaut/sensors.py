"""A logged sensor quantity during each run, e.g. a cryostat temperature, a
pressure or a laser power, from log files on the shared drive.

What is read, and how, is set under sensor: in project.yaml (wynaut.project.Sensor):
by default daily log files

    <sensor_logs>/<YY-MM-DD>/<channel> <YY-MM-DD>.log
    lines "DD-MM-YY,HH:MM:SS,<value>", one per reading, in local time

Times are in the project's timezone, daylight saving included; they are
converted to UTC to match the run index. The logs are read-only, like the
databases, and stay on the drive (default location DATA_ROOT/<sensor.folder>).

Each index line gets, over all readings from start_time to end_time (inclusive):

    sensor_min, sensor_max, sensor_mean
    sensor_std    spread of the readings (ddof=0), not the error of the mean
    sensor_n      number of readings used

in the sensor's unit. A run with no reading in its window (shorter than the log
interval, or no end_time) gets the reading closest to its start_time, if one
lies within sensor.nearest_within_s: n = 1 and std = 0. Otherwise every column
is null. A run that the logs cover only partly uses the readings that exist;
n shows how many.

Below its range, a sensor may log nothing while another channel still does
(sensor.below_range). Example: a thermometer whose calibration ends at 7 mK
logs no temperature below it, only its resistance. A below_range.channel
reading at or above below_range.at_least, with no sensor reading at the same
time, then counts as a reading of below_range.value: a bound, not a
measurement. Readings of that channel below at_least are dropped.
"""

from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from wynaut.project import Sensor

SENSOR_COLUMNS = ("sensor_min", "sensor_max", "sensor_mean", "sensor_std", "sensor_n")


def log_path(root, day, sensor: Sensor, channel: str | None = None) -> Path:
    """The log of one channel (default: the sensor's) for one local calendar day."""
    return Path(root) / sensor.file_pattern.format(day=day, channel=channel or sensor.channel)


def read_log_empty() -> pd.Series:
    return pd.Series([], index=pd.DatetimeIndex([], tz="UTC"), dtype=float)


def read_log(path, sensor: Sensor) -> pd.Series:
    """Readings of one log file, indexed by UTC time.

    In the hour repeated when daylight saving ends, the order of the lines
    tells the two passes apart; if that fails, those readings are dropped.
    """
    try:
        df = pd.read_csv(path, header=None, names=["date", "time", "value"],
                         dtype={"date": str, "time": str, "value": float})
    except pd.errors.EmptyDataError:
        return read_log_empty()
    local = pd.DatetimeIndex(pd.to_datetime(df["date"] + " " + df["time"],
                                            format=sensor.datetime_format))
    try:
        times = local.tz_localize(sensor.timezone, ambiguous="infer", nonexistent="NaT")
    except Exception:  # the error type differs between pandas/pytz/zoneinfo versions
        times = local.tz_localize(sensor.timezone, ambiguous="NaT", nonexistent="NaT")
    readings = pd.Series(df["value"].to_numpy(), index=times.tz_convert("UTC"))
    return readings[readings.index.notna()]


def days_needed(lines, sensor: Sensor) -> list:
    """Local calendar days whose logs can hold readings for these index lines."""
    near = pd.Timedelta(seconds=sensor.nearest_within_s)
    days = set()
    for line in lines:
        if line["start_time"] is None:
            continue
        start = pd.Timestamp(line["start_time"])
        end = pd.Timestamp(line["end_time"]) if line["end_time"] else start
        first = (start - near).tz_convert(sensor.timezone).date()
        last = (max(start, end) + near).tz_convert(sensor.timezone).date()
        days.update(first + timedelta(d) for d in range((last - first).days + 1))
    return sorted(days)


def below_range(readings: pd.Series, other: pd.Series, sensor: Sensor) -> pd.Series:
    """below_range.value at the times of `other` readings that have no sensor
    reading and are at or above below_range.at_least."""
    rule = sensor.below_range
    out = other[(other >= rule.at_least) & ~other.index.isin(readings.index)]
    return pd.Series(rule.value, index=out.index, dtype=float)


def load_readings(root, days, sensor: Sensor) -> tuple[np.ndarray, np.ndarray, list]:
    """(times as UTC ns, values, days without a log), sorted by time. Values
    include the below-range stand-ins (module docstring); a day counts as without
    a log if it has neither a sensor log nor a below_range.channel log."""
    parts, missing = [], []
    for day in days:
        path = log_path(root, day, sensor)
        other = log_path(root, day, sensor, sensor.below_range.channel) if sensor.below_range else None
        if not (path.exists() or (other and other.exists())):
            missing.append(day)
            continue
        readings = read_log(path, sensor) if path.exists() else read_log_empty()
        parts.append(readings)
        if other and other.exists():
            parts.append(below_range(readings, read_log(other, sensor), sensor))
    if not parts:
        return np.array([], dtype=np.int64), np.array([]), missing
    readings = pd.concat(parts).sort_index()
    return readings.index.as_unit("ns").asi8, readings.to_numpy(), missing


def _round(x) -> float:
    return float(f"{x:.7g}")


def _readings_for(times, values, start_time, end_time, sensor: Sensor) -> tuple[np.ndarray, str]:
    """(readings used for one run, "window" | "nearest" | "none")."""
    if start_time is None:
        return values[:0], "none"
    start = pd.Timestamp(start_time).value
    lo = int(np.searchsorted(times, start, side="left"))
    hi = int(np.searchsorted(times, pd.Timestamp(end_time).value, side="right")) if end_time else lo
    if hi > lo:
        return values[lo:hi], "window"
    within = pd.Timedelta(seconds=sensor.nearest_within_s).value
    near = [i for i in (lo - 1, lo) if 0 <= i < len(times) and abs(times[i] - start) <= within]
    if not near:
        return values[:0], "none"
    return values[[min(near, key=lambda i: abs(times[i] - start))]], "nearest"


def _stats(window) -> dict:
    if not len(window):
        return dict.fromkeys(SENSOR_COLUMNS)
    return dict(zip(SENSOR_COLUMNS, (
        _round(window.min()), _round(window.max()), _round(window.mean()),
        _round(window.std()), len(window))))


def run_sensor_values(times, values, start_time, end_time, sensor: Sensor) -> dict:
    """The SENSOR_COLUMNS of one run, from sorted readings (see module docstring)."""
    return _stats(_readings_for(times, values, start_time, end_time, sensor)[0])


def add_sensor_values(lines, root, sensor: Sensor) -> tuple[list[dict], dict]:
    """Copies of the index lines with SENSOR_COLUMNS from the logs under root.

    Every run is recomputed, so logs added later fill in runs that had none.
    Returns the new lines and a report: how many runs got their readings from
    their window, from the nearest reading, or none, and which days had no log.
    """
    days = days_needed(lines, sensor)
    times, values, missing = load_readings(root, days, sensor)
    out, report = [], {"window": 0, "nearest": 0, "none": 0,
                       "days_needed": len(days), "days_missing": missing}
    for line in lines:
        window, source = _readings_for(times, values, line["start_time"], line["end_time"], sensor)
        report[source] += 1
        out.append({**line, **_stats(window)})
    return out, report
