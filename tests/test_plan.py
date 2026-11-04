"""PLAN.md must parse, and the parser rejects sections the report can't use."""

import pytest

from wynaut.plan import PLAN_PATH, parse_plan

SECTION = """\
## Decay time vs magnetic field
Owner: alice
Status: {status}
Analyses: {analyses}
Figures: alice/tau_vs_field

### Question
Is the decay limited by a field-dependent loss channel?

### What we need
Decay time (s) at five fields between 0 and 2 T, same cooldown.

### Success looks like
The decay time drops by more than a factor two between 0.5 T and 2 T.

### Outcome
{outcome}
"""


def write(tmp_path, text):
    path = tmp_path / "PLAN.md"
    path.write_text("# Analysis plan\n\nIntro text.\n\n" + text)
    return path


def section(status="open", analyses="decay_vs_field v1.0, decay_vs_temperature", outcome=""):
    return SECTION.format(status=status, analyses=analyses, outcome=outcome)


def test_repo_plan_parses():
    parse_plan(PLAN_PATH)


def test_parse(tmp_path):
    (q,) = parse_plan(write(tmp_path, section()))
    assert q.title == "Decay time vs magnetic field"
    assert q.owner == "alice"
    assert q.analyses == (("decay_vs_field", "1.0"), ("decay_vs_temperature", None))
    assert q.figures == ("alice/tau_vs_field",)
    assert q.text["Outcome"] == ""
    assert q.text["Success looks like"].startswith("The decay time drops")


def test_none_yet_and_comments(tmp_path):
    text = "<!--\n## Template\nOwner: x\n-->\n" + section(analyses="none yet")
    (q,) = parse_plan(write(tmp_path, text))
    assert q.analyses == ()


def test_measurement_failed_needs_outcome(tmp_path):
    with pytest.raises(ValueError, match="Outcome' is empty"):
        parse_plan(write(tmp_path, section(status="measurement failed")))
    (q,) = parse_plan(write(tmp_path, section(
        status="measurement failed", outcome="Magnet quenched above 1 T.")))
    assert q.status == "measurement failed"


@pytest.mark.parametrize("text, match", [
    (section(status="done"), "Status 'done'"),
    (section(analyses="decay vs field"), "malformed"),
    (section().replace("Owner: alice\n", ""), "missing"),
    (section().replace("Figures:", "Notes: x\nFigures:"), "unexpected line"),
    (section().replace("### What we need", "### Data"), "subsections must be"),
    (section().replace("Is the decay limited by a field-dependent loss channel?", ""), "empty"),
    (section() + "\n" + section(), "duplicate"),
])
def test_rejects(tmp_path, text, match):
    with pytest.raises(ValueError, match=match):
        parse_plan(write(tmp_path, text))
