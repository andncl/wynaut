"""validate_selection accepts the documented format and rejects common mistakes."""

import copy
import json

import jsonschema
import pytest

from wynaut.run_analysis import validate_selection

RUN = {"label": "B_0p5T", "db": "projectA/cooldown3.db", "run_id": 520,
       "guid": "aaaaaaaa-0000-0000-0000-01924a01c3e1",
       "modified_dimension": "field_T", "value": 0.5, "kwargs": {}}
SELECTION = {"analysis": "t1", "kwargs": {}, "runs": [RUN]}


def write(tmp_path, selection):
    path = tmp_path / selection["analysis"] / "example.json"
    path.parent.mkdir()
    path.write_text(json.dumps(selection))
    return path


def with_run(**changes):
    selection = copy.deepcopy(SELECTION)
    selection["runs"][0].update(changes)
    return selection


def test_valid(tmp_path):
    validate_selection(write(tmp_path, SELECTION))


def test_nothing_varied(tmp_path):
    validate_selection(write(tmp_path, with_run(modified_dimension=None, value=None)))


@pytest.mark.parametrize("changes", [
    {"guid": "AAAAAAAA-0000-0000-0000-01924A01C3E1"},  # uppercase
    {"guid": "412"},
    {"modified_dimension": "B-field"},                 # not snake_case with unit
    {"value": "0.5"},
])
def test_schema_rejects(tmp_path, changes):
    with pytest.raises(jsonschema.ValidationError):
        validate_selection(write(tmp_path, with_run(**changes)))


@pytest.mark.parametrize("key", ["guid", "modified_dimension", "value"])
def test_key_required(tmp_path, key):
    selection = copy.deepcopy(SELECTION)
    del selection["runs"][0][key]
    with pytest.raises(jsonschema.ValidationError):
        validate_selection(write(tmp_path, selection))


@pytest.mark.parametrize("changes", [
    {"modified_dimension": None},
    {"value": None},
])
def test_dimension_and_value_together(tmp_path, changes):
    with pytest.raises(ValueError, match="both"):
        validate_selection(write(tmp_path, with_run(**changes)))
