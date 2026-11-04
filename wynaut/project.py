"""Project settings, read from project.yaml in the repo root.

project.yaml is committed: it holds what everyone in the campaign shares, such
as the lab's timezone and the format of the sensor logs. Paths that differ
between machines go in config.yaml instead (wynaut/paths.py). Set
WYNAUT_PROJECT to use a project file elsewhere.

    timezone   IANA name, e.g. "Europe/Berlin": the local time of the sensor
               logs, and of the months and dates in the run tracker
    sensor     optional: one logged quantity attached to every run in the index
               (wynaut/sensors.py). Without it the sensor columns stay empty.
    tracker    optional: how the run tracker colours the sensor values
"""

import os
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml

from wynaut.paths import REPO_ROOT

PROJECT_PATH = Path(os.environ.get("WYNAUT_PROJECT", REPO_ROOT / "project.yaml"))


@dataclass(frozen=True)
class BelowRange:
    """Readings of another channel that stand in where the sensor is below its range.

    A reading of channel at or above at_least, with no sensor reading at the same
    time, counts as a sensor reading of value: a bound, not a measurement.
    Example: a thermometer whose calibration ends at 7 mK logs no temperature
    below it, only its resistance; a resistance of 12.8 kOhm or more means 7 mK
    or colder.
    """

    channel: str
    at_least: float
    value: float


@dataclass(frozen=True)
class Sensor:
    """How to read one logged quantity. The defaults read daily log files

        <folder>/<YY-MM-DD>/<channel> <YY-MM-DD>.log
        lines "DD-MM-YY,HH:MM:SS,<value>", in local time

    as written by e.g. Bluefors cryostat software. Change file_pattern and
    datetime_format for other loggers that write one CSV line per reading.
    """

    channel: str
    label: str = "Sensor"
    unit: str = ""
    folder: str = "sensor_logs"
    file_pattern: str = "{day:%y-%m-%d}/{channel} {day:%y-%m-%d}.log"
    datetime_format: str = "%d-%m-%y %H:%M:%S"
    timezone: str = "UTC"
    nearest_within_s: float = 120
    below_range: BelowRange | None = None


@dataclass(frozen=True)
class Tracker:
    """Colour scale of the sensor tab: steps linear from 0 to sensor_max, the
    top step also for values up to sensor_ignore_above, and above that 'no
    reading'. sensor_colors are spread evenly from 0 to sensor_max; the default
    goes from vivid blue through white to vivid red."""

    sensor_max: float = 1.0
    sensor_steps: int = 10
    sensor_ignore_above: float | None = None
    sensor_colors: tuple[str, ...] = ("#0022cc", "#2f6dff", "#ffffff", "#ff3d2e", "#c40000")


@cache
def project(path: Path = PROJECT_PATH) -> dict:
    path = Path(path)
    return (yaml.safe_load(path.read_text()) or {}) if path.exists() else {}


def timezone() -> str:
    return project().get("timezone", "UTC")


def sensor() -> Sensor | None:
    """The sensor of project.yaml, or None if it has none."""
    settings = dict(project().get("sensor") or {})
    if not settings:
        return None
    below = settings.pop("below_range", None)
    return Sensor(**settings, timezone=timezone(),
                  below_range=BelowRange(**below) if below else None)


def tracker() -> Tracker:
    return Tracker(**(project().get("tracker") or {}))
