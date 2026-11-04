"""Step 2a: the analysis plan, PLAN.md at the repo root.

One file, written in natural language. Each question is a "## " section that
starts with four fixed lines, followed by four "### " subsections of free text:

    ## <the question, as a short title>
    Owner: <name>
    Status: open | confirmed | refuted | inconclusive | measurement failed
    Analyses: <analysis> v<VERSION>, ...      ("none yet" before they exist)
    Figures: <person>/<script>, ...            ("none yet" before they exist)

    ### Question
    ### What we need
    ### Success looks like
    ### Outcome

Only the four fixed lines are read by code: the report uses them to link each
question to its outputs and figures. The subsections are copied into the
report as written. HTML comments are ignored.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from wynaut.paths import REPO_ROOT

PLAN_PATH = REPO_ROOT / "PLAN.md"
FIELDS = ("Owner", "Status", "Analyses", "Figures")
SUBSECTIONS = ("Question", "What we need", "Success looks like", "Outcome")
STATUSES = ("open", "confirmed", "refuted", "inconclusive", "measurement failed")
NONE_YET = "none yet"
ANALYSIS_REF = re.compile(r"^([a-z][a-z0-9_]*)(?: v(\S+))?$")
FIGURE_REF = re.compile(r"^[A-Za-z0-9_-]+/[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class Question:
    title: str
    owner: str
    status: str
    analyses: tuple[tuple[str, str | None], ...]  # (analysis, version or None = not pinned)
    figures: tuple[str, ...]  # "<person>/<script>", as passed to wynaut.io.save_figure
    text: dict[str, str]  # subsection name -> free text


def parse_plan(path: Path = PLAN_PATH) -> list[Question]:
    """All questions in PLAN.md, in file order. Raises on a malformed section."""
    text = re.sub(r"<!--.*?-->", "", Path(path).read_text(), flags=re.S)
    questions = [_parse_question(chunk, path)
                 for chunk in re.split(r"^## ", text, flags=re.M)[1:]]
    titles = [q.title for q in questions]
    duplicates = sorted({t for t in titles if titles.count(t) > 1})
    if duplicates:
        raise ValueError(f"{path}: duplicate questions {duplicates}")
    return questions


def _parse_question(chunk: str, path) -> Question:
    title, _, body = chunk.partition("\n")
    title = title.strip()
    where = f"{path}: ## {title}"
    head, *subs = re.split(r"^### ", body, flags=re.M)

    fields = {}
    for line in head.strip().splitlines():
        key, sep, value = line.partition(":")
        if not line.strip():
            continue
        if not sep or key.strip() not in FIELDS:
            raise ValueError(f"{where}: unexpected line {line.strip()!r}; before "
                             f"the first ### only {', '.join(FIELDS)} are allowed")
        fields[key.strip()] = value.strip()
    missing = [f for f in FIELDS if f not in fields]
    if missing:
        raise ValueError(f"{where}: missing {missing}")

    text = {}
    for sub in subs:
        name, _, content = sub.partition("\n")
        text[name.strip()] = content.strip()
    if tuple(text) != SUBSECTIONS:
        raise ValueError(f"{where}: subsections must be {list(SUBSECTIONS)} in "
                         f"this order, got {list(text)}")
    for name in ("Question", "What we need", "Success looks like"):
        if not text[name]:
            raise ValueError(f"{where}: '### {name}' is empty")

    status = fields["Status"]
    if status not in STATUSES:
        raise ValueError(f"{where}: Status {status!r} must be one of {list(STATUSES)}")
    if status != "open" and not text["Outcome"]:
        raise ValueError(f"{where}: Status is {status!r} but '### Outcome' is empty")

    return Question(
        title=title, owner=fields["Owner"], status=status,
        analyses=tuple(_refs(fields["Analyses"], ANALYSIS_REF, where, "Analyses",
                             lambda m: (m.group(1), m.group(2)))),
        figures=tuple(_refs(fields["Figures"], FIGURE_REF, where, "Figures",
                            lambda m: m.group(0))),
        text=text,
    )


def _refs(value, pattern, where, field, convert):
    if value == NONE_YET:
        return []
    refs = []
    for item in (v.strip() for v in value.split(",")):
        match = pattern.match(item)
        if not match:
            raise ValueError(f"{where}: {field} entry {item!r} is malformed")
        refs.append(convert(match))
    return refs
