# Analysis plan

The questions this campaign has to answer, one `##` section per question, in
natural language. Write a section **before** selecting runs, and write
"Success looks like" before the results exist: git history then shows the goal
wasn't moved after seeing the data. The report (step 5) has one chapter per
section, so this file is how you check progress and record what was found.

Rules for each section (checked by `pytest`):
- The four lines under the title are fixed: `Owner:`, `Status:`, `Analyses:`,
  `Figures:`. They are the only part read by code.
- `Status:` is one of `open`, `confirmed`, `refuted`, `inconclusive`,
  `measurement failed`. Only a person changes it, together with `### Outcome`.
  Use `measurement failed` when the data can't answer the question, and
  `refuted` when the data is good and the answer is no.
- `Analyses:` lists `<analysis> v<VERSION>` (pin the version once results
  exist), `Figures:` lists `<person>/<script>`. Write `none yet` until they exist.
- The four `###` subsections are free text, in this order. Only `### Outcome`
  may be empty, and only while `Status: open`.

Copy the template below to add a question.

<!--
## <The question, as a short title>
Owner: <name>
Status: open
Analyses: none yet
Figures: none yet

### Question
What we want to know, and why it matters.

### What we need
Which measurements, which quantities to extract (with units), and over what range.

### Success looks like
What result would answer the question, and what would count against it.
Write this before the results exist.

### Outcome
Written after the results: what was found and what it means, or why the
measurement failed and what would be needed instead.
-->

## Decay time vs magnetic field
Owner: alice
Status: open
Analyses: decay_vs_field v1.0
Figures: none yet

### Question
An example question for the demo campaign (python -m tools.make_demo): does the
decay time of the signal depend on the magnetic field, which would point to a
field-dependent loss channel?

### What we need
The decay time (s) from at least five runs at different fields between 0 and
2 T, from the same cooldown and sample, with the fit converging in each run.

### Success looks like
The decay time changes by more than a factor two across the field range. A
flat decay time, within the fit errors, counts against a field-dependent loss.

### Outcome
