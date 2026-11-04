"""Every selection file in the repo must pass the data-free checks, including
the lookup in the committed run index."""

from pathlib import Path

import pytest

from wynaut.index import read_index_lines
from wynaut.run_analysis import check_in_index, validate_selection

SELECTIONS = sorted((Path(__file__).parent.parent / "selections").glob("*/*.json"))


@pytest.mark.parametrize("path", SELECTIONS,
                         ids=[f"{p.parent.name}/{p.name}" for p in SELECTIONS])
def test_selection_valid(path):
    validate_selection(path)


@pytest.mark.parametrize("path", SELECTIONS,
                         ids=[f"{p.parent.name}/{p.name}" for p in SELECTIONS])
def test_selection_in_index(path):
    """Every run is in the committed run index, with the same guid."""
    check_in_index(validate_selection(path), INDEX)


INDEX = read_index_lines()
