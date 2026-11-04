"""index_sensor --batch-days works newest first and covers every run exactly once."""

from tools.index_sensor import batches_newest_first


def line(start):
    return {"start_time": start, "end_time": start}


def test_batches_newest_first_cover_every_run_once():
    lines = [line("2026-04-01T00:00:00+00:00"), line(None), line("2026-04-20T00:00:00+00:00"),
             line("2026-04-19T00:00:00+00:00"), line("2026-04-09T00:00:00+00:00")]
    batches = batches_newest_first(lines, days=7)
    assert batches == [[2, 3], [4], [0], [1]]          # 20+19 Apr, 9 Apr, 1 Apr, never started
    assert sorted(i for b in batches for i in b) == list(range(len(lines)))
