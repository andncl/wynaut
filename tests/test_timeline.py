"""The run tracker computes each run's status from selections and outputs, and lays runs out by month."""

import json

import pandas as pd
import pytest

from tools.timeline import (build_status_table, grid_rows, read_milestones, render_html,
                            sensor_step)
from wynaut.project import BelowRange, Sensor, Tracker
from wynaut.sensors import SENSOR_COLUMNS

GUID = "aaaaaaaa-0000-0000-0000-{:012d}"


def index(*runs):
    """A run index with (run_id, start, end) runs in one database."""
    return pd.DataFrame({
        "db": "april_2026.db", "run_id": [r[0] for r in runs],
        "guid": [GUID.format(r[0]) for r in runs], "name": "decay", "exp_name": "decay_vs_field",
        "sample": "sample_a",
        "start_time": pd.to_datetime([r[1] for r in runs], utc=True),
        "end_time": pd.to_datetime([r[2] for r in runs], utc=True),
        **{c: float("nan") for c in SENSOR_COLUMNS}})


@pytest.fixture(autouse=True)
def project(monkeypatch):
    """The demo project's settings, whatever project.yaml says."""
    monkeypatch.setattr("tools.timeline.TIMEZONE", "Australia/Sydney")
    monkeypatch.setattr("tools.timeline.SENSOR", Sensor(
        channel="CH6 T", label="Fridge temperature", unit="K", timezone="Australia/Sydney",
        below_range=BelowRange(channel="CH6 R", at_least=12800, value=0.007)))
    monkeypatch.setattr("tools.timeline.TRACKER", Tracker(sensor_max=3.0, sensor_ignore_above=4.0))


def write_selection(root, name, run_ids, analysis="decay_vs_field"):
    path = root / analysis / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"analysis": analysis, "kwargs": {}, "runs": [
        {"label": f"r{i}", "db": "april_2026.db", "run_id": i, "guid": GUID.format(i),
         "modified_dimension": None, "value": None, "kwargs": {}} for i in run_ids]}))


def write_results(root, name, label=None, version="1.0", analysis="decay_vs_field", **results):
    """Per-run results of one run, or the accumulated results if label is None."""
    step = f"runs/{label}" if label else "accumulated"
    path = root / analysis / f"v{version}" / name / step / "results.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results))


T = "2026-04-20T10:00:00"


def test_status_from_selections_and_outputs(tmp_path):
    runs = index(*[(i, T, T) for i in range(1, 7)], (7, T, None), (8, None, None), (9, T, None))
    selections, outputs = tmp_path / "selections", tmp_path / "outputs"
    write_selection(selections, "Q1", [2, 3, 4, 9])
    write_selection(selections, "Q2", [5, 6])
    write_results(outputs, "Q1", "r3", fit_ok=True)
    write_results(outputs, "Q1", "r4", fit_ok=False)
    write_results(outputs, "Q1", "r9", fit_ok=True)          # aborted, but analysed
    write_results(outputs, "Q2", "r5", fit_ok=True)
    write_results(outputs, "Q2", "r6", fit_ok=False)
    write_results(outputs, "Q2", tau_max_s=1e-3)              # accumulated
    write_results(outputs, "Q1", fit_ok=False)               # accumulated, but failed

    status = build_status_table(runs, selections, outputs, tmp_path / "none.yaml")
    assert status.set_index("run_id")["status"].to_dict() == {
        1: "unprocessed", 2: "selected", 3: "analysed", 4: "selected", 5: "accumulated",
        6: "selected", 7: "failed", 8: "empty", 9: "analysed"}


def test_accumulated_needs_both_steps_of_the_same_version(tmp_path):
    write_selection(tmp_path / "selections", "Q1", [1])
    write_results(tmp_path / "outputs", "Q1", "r1", version="1.0", fit_ok=True)
    write_results(tmp_path / "outputs", "Q1", version="1.1")
    status = build_status_table(index((1, T, T)), tmp_path / "selections", tmp_path / "outputs",
                                tmp_path / "none.yaml")
    assert status["status"].tolist() == ["analysed"]


def test_without_outputs_selected_runs_are_selected(tmp_path):
    write_selection(tmp_path, "Q1", [1])
    status = build_status_table(index((1, T, T)), tmp_path, None, tmp_path / "none.yaml")
    assert status["status"].tolist() == ["selected"]
    assert status["selections"].tolist() == [["decay_vs_field/Q1"]]


def test_marks_win_and_ranges_expand(tmp_path):
    (tmp_path / "marks.yaml").write_text(
        "- {mark: not_relevant, db: april_2026.db, runs: ['1-3']}\n"
        "- {mark: paper, db: april_2026.db, runs: [5], note: Fig. 2}\n"
        "- {mark: failed, db: april_2026.db, runs: [6]}\n")
    write_selection(tmp_path / "selections", "Q1", [5])
    status = build_status_table(index(*[(i, T, T) for i in range(1, 7)]),
                                tmp_path / "selections", None, tmp_path / "marks.yaml")
    assert status["status"].tolist() == ["not_relevant"] * 3 + ["unprocessed", "paper", "failed"]
    assert status["note"].tolist()[4] == "Fig. 2"


@pytest.mark.parametrize("entry, problem", [
    ("{mark: great, db: april_2026.db, runs: [1]}", "must be one of"),
    ("{mark: paper, db: april_2026.db, runs: [9]}", "not in the run index"),
    ("{mark: paper, db: other.db, runs: [1]}", "not in the run index"),
    ("{mark: paper, db: april_2026.db, runs: [1, '1-2']}", "marked twice"),
])
def test_bad_marks_are_refused(tmp_path, entry, problem):
    (tmp_path / "marks.yaml").write_text(f"- {entry}\n")
    with pytest.raises(ValueError, match=problem):
        build_status_table(index((1, T, T), (2, T, T)), tmp_path, None, tmp_path / "marks.yaml")


def test_rows_break_at_months_and_keep_empty_months(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.timeline.ROW_LENGTH", 2)
    runs = index((1, "2026-04-10T00:00", "2026-04-10T00:01"), (2, None, None),
                 (3, "2026-04-11T00:00", "2026-04-11T00:01"),
                 (4, "2026-06-02T00:00", "2026-06-02T00:01"))
    rows = grid_rows(build_status_table(runs, tmp_path, None, tmp_path / "none.yaml"))
    assert [list(r["run_id"]) for _, r in rows] == [[1, 2], [3], [], [4]]
    assert rows[2][0] == pd.Timestamp("2026-05-01", tz="Australia/Sydney")


def test_milestone_lands_on_its_row(tmp_path):
    (tmp_path / "m.yaml").write_text("- date: 2026-05-15\n  text: Warm-up\n")
    runs = index((1, "2026-04-10T00:00", "2026-04-10T00:01"),
                 (2, "2026-06-02T00:00", "2026-06-02T00:01"))
    page = render_html(build_status_table(runs, tmp_path, None, tmp_path / "none.yaml"),
                       read_milestones(tmp_path / "m.yaml"))
    may = page.split("<b>May 2026</b>")[1].split("</section>")[0]
    assert "Warm-up" in may and "no runs" in may
    assert page.count(' mark"') == 1                         # rings run 2, the first after it


def test_rows_are_labelled_with_weekday_and_months_newest_first(tmp_path):
    runs = index((1, "2026-04-10T00:00", "2026-04-10T00:01"),
                 (2, "2026-06-02T00:00", "2026-06-02T00:01"))
    page = render_html(build_status_table(runs, tmp_path, None, tmp_path / "none.yaml"), [])
    assert '<div class="when">Fri 10</div>' in page and '<div class="when">Tue 02</div>' in page
    assert page.index("Jun 2026") < page.index("May 2026") < page.index("Apr 2026")


@pytest.mark.parametrize("value, step", [
    (0.0, 0), (0.007, 0), (0.299, 0), (0.3, 1), (1.5, 5), (2.95, 9), (3.0, 9), (3.9, 9),
    (float("nan"), None)])
def test_sensor_steps_are_linear_up_to_sensor_max(value, step):
    assert sensor_step(value) == step


def test_sensor_tab_colours_by_mean_sensor_value(tmp_path):
    runs = index((1, T, T), (2, T, T), (3, T, T))
    runs["sensor_mean"] = [0.0098, 1.5, float("nan")]
    runs["sensor_min"] = [0.0071, 1.4, float("nan")]
    runs["sensor_max"] = [0.012, 1.6, float("nan")]
    runs["sensor_n"] = [12, 1, None]
    page = render_html(build_status_table(runs, tmp_path, None, tmp_path / "none.yaml"), [])
    assert 'data-view="status"' in page and 'data-view="sensor"' in page
    assert 'class="s-unprocessed t0"' in page and 'class="s-unprocessed t5"' in page
    assert 'class="s-unprocessed t-none"' in page
    assert "fridge temperature: 9.8 mK mean, 7.1 mK to 12 mK, 12 readings" in page
    assert "fridge temperature: 1.5 K, nearest reading" in page and "fridge temperature: no reading" in page
    assert "2 of 3 runs have a reading" in page


def test_above_sensor_ignore_above_counts_as_no_reading(tmp_path):
    assert sensor_step(3.5) == 9 and sensor_step(4.0) == 9
    assert sensor_step(4.01) is None and sensor_step(80.0) is None
    runs = index((1, T, T))
    runs["sensor_mean"], runs["sensor_min"] = [51.0], [50.0]
    runs["sensor_max"], runs["sensor_n"] = [52.0], [30]
    page = render_html(build_status_table(runs, tmp_path, None, tmp_path / "none.yaml"), [])
    assert 'class="s-unprocessed t-none"' in page
    assert "51 K mean, 50 K to 52 K, 30 readings (above 4 K: shown as no reading)" in page


def test_below_range_readings_are_flagged_in_the_tip(tmp_path):
    runs = index((1, T, T))
    runs["sensor_mean"], runs["sensor_min"], runs["sensor_max"], runs["sensor_n"] = [0.008], [0.007], [0.009], [5]
    page = render_html(build_status_table(runs, tmp_path, None, tmp_path / "none.yaml"), [])
    assert "7 mK readings mean at or below the sensor&#x27;s range" in page


def test_without_a_sensor_there_is_no_sensor_tab(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.timeline.SENSOR", None)
    page = render_html(build_status_table(index((1, T, T)), tmp_path, None, tmp_path / "none.yaml"), [])
    assert '<button data-view="sensor"' not in page and "no reading" not in page
