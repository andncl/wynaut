"""Add the logged sensor quantity during each run to the run index (maintainer), then commit it.

    python -m tools.index_sensor                                # logs in DATA_ROOT/<sensor.folder>
    python -m tools.index_sensor --sensor-logs /mnt/share/my_campaign/sensor_logs
    python -m tools.index_sensor --out /tmp/runs.jsonl          # try it without touching the index
    python -m tools.index_sensor --batch-days 7 --tracker       # newest week first, index and
                                                                # run tracker updated after each week

Run from the repo root, after tools/build_index. What is read is set under
sensor: in project.yaml (wynaut/sensors.py). Recomputes every run, so rerun it
whenever new logs are uploaded. Only reads the logs; writes nothing but the
index (or --out).
"""

import argparse
import time
from datetime import timedelta
from pathlib import Path

import pandas as pd

from wynaut import project
from wynaut.index import read_index_lines, write_index_lines
from wynaut.paths import INDEX_PATH
from wynaut.sensors import add_sensor_values, days_needed


def day_ranges(days) -> str:
    """"26-04-15..26-07-28, 26-08-09" from a sorted list of dates."""
    ranges = []
    for day in days:
        if ranges and day - ranges[-1][1] == timedelta(1):
            ranges[-1][1] = day
        else:
            ranges.append([day, day])
    return ", ".join(f"{a:%y-%m-%d}" if a == b else f"{a:%y-%m-%d}..{b:%y-%m-%d}"
                     for a, b in ranges)


def batches_newest_first(lines, days: int, timezone: str = "UTC") -> list[list[int]]:
    """Positions of the index lines in batches of `days` local calendar days of
    start time, newest batch first. Runs that never started form the last batch."""
    start = {i: pd.Timestamp(l["start_time"]).tz_convert(timezone).date()
             for i, l in enumerate(lines) if l["start_time"]}
    newest = max(start.values())
    batches = {}
    for i, day in start.items():
        batches.setdefault((newest - day).days // days, []).append(i)
    never = [i for i in range(len(lines)) if i not in start]
    return [sorted(batches[k], key=lambda i: start[i], reverse=True)
            for k in sorted(batches)] + ([never] if never else [])


def missing_note(missing) -> str:
    return f", {len(missing)} days without log" if missing else ""


def add_in_batches(lines, sensor_logs, sensor, days: int, out, tracker: bool) -> tuple[list[dict], dict]:
    """add_sensor_values newest first, batch by batch, writing out after each
    batch and printing progress. With tracker, the run tracker page is rebuilt too."""
    batches = batches_newest_first(lines, days, sensor.timezone)
    lines = list(lines)
    total = {"window": 0, "nearest": 0, "none": 0, "days_needed": 0, "days_missing": []}
    done, began = 0, time.monotonic()
    for k, batch in enumerate(batches, 1):
        new, report = add_sensor_values([lines[i] for i in batch], sensor_logs, sensor)
        for i, line in zip(batch, new):
            lines[i] = line
        write_index_lines(lines, out)
        for key in ("window", "nearest", "none"):
            total[key] += report[key]
        total["days_missing"] += report["days_missing"]
        done += len(batch)
        starts = [lines[i]["start_time"] for i in batch if lines[i]["start_time"]]
        span = (f"{pd.Timestamp(min(starts)).tz_convert(sensor.timezone):%y-%m-%d}.."
                f"{pd.Timestamp(max(starts)).tz_convert(sensor.timezone):%y-%m-%d}" if starts
                else "never started")
        print(f"[{k:>2}/{len(batches)}] {span}: {len(batch):>4} runs, "
              f"{report['window']} window / {report['nearest']} nearest / {report['none']} none"
              f"{missing_note(report['days_missing'])}"
              f" · {done}/{len(lines)} runs done, {time.monotonic() - began:.0f} s", flush=True)
        if tracker:
            from tools.timeline import OUT_PATH, write_page
            write_page(index_path=out, log=lambda _: None)
            print(f"        tracker updated: {OUT_PATH}", flush=True)
    total["days_needed"] = len(days_needed(lines, sensor))   # batches share days at their edges
    total["days_missing"] = sorted(set(total["days_missing"]))
    return lines, total


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sensor-logs", help="folder with the logs "
                        "(default: DATA_ROOT/<sensor.folder of project.yaml>)")
    parser.add_argument("--index", default=INDEX_PATH, help="index to read (default: %(default)s)")
    parser.add_argument("--out", help="where to write the result (default: the index itself)")
    parser.add_argument("--batch-days", type=int, help="work newest first, this many days per "
                        "batch, and write the result after each batch")
    parser.add_argument("--tracker", action="store_true", help="with --batch-days: also rebuild "
                        "the run tracker page (tools/timeline.py) after each batch")
    args = parser.parse_args()
    sensor = project.sensor()
    if sensor is None:
        raise SystemExit("project.yaml has no sensor: section, so there is nothing to index")
    if args.sensor_logs:
        sensor_logs = args.sensor_logs
    else:
        from wynaut.paths import DATA_ROOT
        sensor_logs = DATA_ROOT / sensor.folder

    lines = read_index_lines(args.index)
    print(f"reading {sensor.label} ({sensor.channel}) from {sensor_logs} for {len(lines)} runs")
    out = Path(args.out or args.index)
    if args.batch_days:
        lines, report = add_in_batches(lines, sensor_logs, sensor, args.batch_days, out, args.tracker)
    else:
        lines, report = add_sensor_values(lines, sensor_logs, sensor)
        write_index_lines(lines, out)

    print(f"\nwrote {len(lines)} runs to {out}")
    print(f"  {report['window']} with readings during the run")
    print(f"  {report['nearest']} with the reading nearest to their start (short or unfinished runs)")
    print(f"  {report['none']} without any reading (null)")
    missing = report["days_missing"]
    print(f"{len(missing)} of {report['days_needed']} days with runs have no log", end="")
    print(f": {day_ranges(missing)}" if missing else "")
