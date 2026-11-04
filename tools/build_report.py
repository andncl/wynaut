"""Step 5: build the Slidev report from PLAN.md, the analysis outputs and the figures.

    python tools/build_report.py      # renders figures, writes report/slides.md
    cd report && npx slidev build     # static HTML in report/dist/ (maintainer)

The deck has an overview slide (every question with its progress and Status),
the weekly run timeline (tools/timeline.py), and then one chapter per "##"
question in PLAN.md:

  1. Question and Success looks like, as written in the plan
  2. Progress, computed: planned -> runs selected -> analysed -> figures -> outcome
  3. The figures listed under Figures:, rendered fresh by running their scripts
  4. A results table for every analysis listed under Analyses:, at its pinned
     version, loaded through wynaut.io
  5. Status and Outcome, as written in the plan

Every number in the deck comes from wynaut.io; none is typed by hand.
report/slides.md is generated and gitignored: never edit it. Hand-written
slides (e.g. an introduction) go in report/pages/ and are included as they are.
"""

from wynaut.plan import Question, parse_plan


def progress(question: Question) -> dict[str, bool | None]:
    """Which stages are done: selected, analysed, figures, outcome.
    None where it can't be known yet, e.g. analysed while a version is unpinned."""
    raise NotImplementedError


def render_figures(question: Question) -> list:
    """Run figures/<person>/<script>.py for every figure of the question and
    return the paths of the images it saved through wynaut.io.save_figure."""
    raise NotImplementedError


def write_slides(questions: list[Question]) -> None:
    """Write report/slides.md."""
    raise NotImplementedError


if __name__ == "__main__":
    write_slides(parse_plan())
