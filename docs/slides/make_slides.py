"""Slides explaining how a wynaut analysis campaign is organised.

Writes three images to docs/img/ (embedded in the README):
  analysis_campaign_roles.png     - who does what at each step, text vs code, gates
  analysis_campaign_overview.png  - the steps on one worked example
  analysis_campaign_formats.png   - the structured files and classes between the steps
and all three as one vector PDF, analysis_campaign_slides.pdf, for presenting.

Run: python docs/slides/make_slides.py
"""

from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Ellipse, FancyArrowPatch, FancyBboxPatch, Rectangle

GIT = "#2E6FBA"
DRIVE = "#D9822B"
INK = "#1F2933"
MUTED = "#5F6B7A"
PANEL = "#F4F6F8"
CODE_BG = "#EEF1F5"
BORDER = "#C9CFD6"
HIGHLIGHT = "#D6E4F5"

PROGRESS = {"done": "#3A9E6F", "in progress": "#F2C14E", "not yet": "#D5DAE0"}
VERDICT = {"confirmed": "#3A9E6F", "open": "#8A94A3", "measurement failed": "#C2453D"}

# Kinds of file, as used on the roles slide: (symbol and short name, meaning, colour).
# TEXT is blue rather than violet so it doesn't read as the agents' colour.
KIND = {"TEXT": ("✎ text", "natural language", "#2E6FBA"),
        "CODE": ("⟨/⟩ code", "code, by you or your agent", "#17877E"),
        "JSON": ("{ } data", "structured data", "#C04F7A"),
        "AUTO": ("⚙ auto", "generated for you", "#8A94A3")}
GENERATED = KIND["AUTO"][2]

# One colour per role on the roles slide: (accent, lane background, cell border)
RESEARCHER = ("#E07A2F", "#FDF0E4", "#EFA36A")
AGENT = ("#6C5CE7", "#EFEDFC", "#A79DF2")
MAINTAINER = ("#7A8796", "#F1F3F5", "#D5DAE0")
RESEARCHER_DARK = "#B85A16"

# The plan feeding forward to the report, on the roles and overview slides
FEED = "#D7263D"
FEED_LABEL = "feed forward: the report checks results against what success looks like"
AGENT_DARK = "#4B3CC4"

# The worked example on the overview slide: T1 measured at three fields
SWEEP = [("0.5 T", 41), ("1 T", 35), ("2 T", 22)]  # (field, T1 in µs)
SWEEP_FIELDS_T = [0.5, 1.0, 2.0]

STAGES = [
    {"num": "0", "title": "Raw data", "sub": "what was measured?",
     "caption": "QCoDeS databases,\nread-only",
     "where": [("drive", DRIVE)], "human": False, "w": 1.55},
    {"num": "1", "title": "Index", "sub": "what runs exist?",
     "caption": "all runs, plus\naveraged copies",
     "where": [("index: git", GIT), ("copies: drive", DRIVE)],
     "human": False, "w": 1.55},
    {"num": "2a", "title": "Plan", "sub": "what's the question?",
     "caption": "question, needs and\nsuccess, in words",
     "where": [("PLAN.md", GIT)], "human": True, "w": 1.8},
    {"num": "2b", "title": "Select", "sub": "which runs answer it?",
     "caption": "an agent proposes,\nyou confirm",
     "where": [("selections/", GIT)], "human": True, "w": 1.8},
    {"num": "3", "title": "Analysis", "sub": "runs → numbers, never plots",
     "where": [("code: git", GIT), ("outputs: drive", DRIVE)],
     "human": True, "w": 3.7},
    {"num": "4", "title": "Figures", "sub": "numbers → plots",
     "caption": "read outputs only,\nrestyle freely",
     "where": [("figures/", GIT)], "human": True, "w": 1.55},
    {"num": "5", "title": "Report", "sub": "did it work?",
     "caption": "progress & outcome\nper question",
     "where": [("generated", GENERATED)], "human": True, "w": 1.55},
]

# Roles slide: one row per role, one cell per step: (text, kinds, gate number)
ROLE_STEPS = ["0", "1", "2a", "2b", "3", "4", "5"]
ROLE_STEP_NAMES = ["Raw data", "Index &\naveraged", "Plan", "Select",
                   "Analysis", "Figures", "Report"]
ROLES = [
    ("Researchers", "you: bring the questions\nand own the science", RESEARCHER, [
        ("run the\nmeasurements", [], None),
        (None, [], None),
        ("describe the\nmeasurements to\nanalyse, what to\nextract and what\nsuccess looks like", ["TEXT"], None),
        ("describe the runs\nyou need, pick from\nthe candidates", ["TEXT"], 1),
        ("choose the fit model\nand what to extract,\ncheck the results", ["CODE"], 2),
        ("make your figures,\nin your style", ["CODE"], None),
        ("give the verdict:\nconfirmed, refuted,\ninconclusive or\nmeasurement failed", ["TEXT"], 3),
    ]),
    ("Agents", "your assistant: does\nthe legwork on request", AGENT, [
        ("never touches\nraw data", [], None),
        (None, [], None),
        ("turns your words\ninto a PLAN.md\nsection, asks what's\nmissing", ["TEXT"], None),
        ("searches every\ndatabase, shows you\nmatching runs", ["JSON"], None),
        ("writes the analysis\ncode and runs it", ["CODE"], None),
        ("drafts plotting\ncode on request", ["CODE"], None),
        ("builds the report,\nflags results that\ndisagree with the plan", ["AUTO"], None),
    ]),
    ("Maintainers", "keep the stack running:\nnothing to do for you", MAINTAINER, [
        ("keep raw data safe\nand read-only", [], None),
        ("build the run index\nand averaged copies", ["CODE", "AUTO"], None),
        ("PLAN.md format", ["CODE"], None),
        ("index, schema, tests", ["CODE"], None),
        ("base classes, runner,\nchecks", ["CODE"], None),
        ("figure rendering", ["CODE"], None),
        ("Slidev deck,\npublishing", ["CODE"], None),
    ]),
]
# Where researchers and agents work together, step 2a to 5
TOGETHER = ["plan together", "find runs", "build the analysis", "make plots",
            "review results"]
HOSTING = "optional: report hosted\non GitHub Pages"
CONTROL = "You stay in control at three points:"
CONTROL_POINTS = ["the runs", "the method", "the verdict"]
HANDLED = ("Everything else is handled for you: finding runs, file paths, checks, "
           "versions, averaging, rendering figures and building the report.")

# Progress view of the report, on the overview slide
REPORT_ROWS = [
    ("T1 vs magnetic field", ["done"] * 5, "confirmed"),
    ("Charge noise vs temperature", ["done", "done", "in progress", "not yet", "not yet"], "open"),
    ("RB gate fidelity", ["done", "done", "done", "done", "done"], "measurement failed"),
]
REPORT_COLS = ["planned", "runs selected", "analysed", "figures", "outcome"]

RULES = [
    "Raw data is read-only",
    "A run is (db, run_id) + guid,\nnever a bare run_id",
    "Each step reads only\nthe step before it",
    "Analysis changed\n→ bump VERSION",
    "Success criteria before\nresults, verdicts by people",
]

SELECTION_JSON = """\
{
  "analysis": "t1_vs_field",
  "kwargs": {"fit_model": "exp_decay"},
  "runs": [
    {"label": "B_0p5T",
     "db": "setup_a/cooldown_2.db",
     "run_id": 520,
     "guid": "aaaaaaaa-...-01924a01c3e1",
     "modified_dimension": "field_T",
     "value": 0.5,
     "kwargs": {}},
    {"label": "B_1T", ...}
  ]
}"""

SELECTION_FIELDS = [
    ("analysis", "module in analysis/ to call", 0),
    ("kwargs", "settings, routed by KWARGS", 0),
    ("runs", "the runs accumulated in this call", 0),
    ("label", "name of the run, unique in file", 1),
    ("db, run_id, guid", "which run, checked vs. the index", 1),
    ("modified_dimension", "what is varied, e.g. field_T", 1),
    ("value", "its value in that unit, or null", 1),
    ("kwargs", "overrides for this run only", 1),
]

ANALYSIS_CODE = """\
class T1Fit(RunAnalysis):            # 3a
    VERSION = "1.0"
    DATA = "averaged"                # or "raw"
    KWARGS = {"fit_model": "exp_decay"}

    def analyse(self, run):
        # once per run, on a fresh instance
        # run.data    -> xr.Dataset (measured)
        # self.kwargs -> resolved settings
        ...                          # fit one decay
        return {"data": {"decay": ds},
                "results": {"t1_s": 4.1e-5,
                            "fit_ok": True}}

class T1VsField(AccumulatedAnalysis):  # 3b
    VERSION = "1.0"
    RUN_ANALYSIS = T1Fit

    def accumulate(self, runs):
        # runs[label].results / .data / .value
        ...                          # T1 vs field
        return {"data": {"t1_vs_field": ds},
                "results": {"t1_max_s": 4.1e-5}}"""

ANALYSIS_NOTES = [
    "top-level kwargs → each class that declares them in KWARGS",
    "per-run kwargs → the RunAnalysis · undeclared keys are an error",
]

OUTPUT_CODE = """\
{"data":    {key: xr.Dataset},
 "results": {key: scalar}}"""

STORAGE_TREE = """\
<name>/
├── meta.json
├── runs/
│   ├── B_0p5T/
│   │   ├── results.json
│   │   └── data/decay.nc
│   └── B_1T/ ...
└── accumulated/
    ├── results.json
    └── data/t1_vs_field.nc"""

LOAD_CODE = """\
out = load("t1_vs_field", name, version="1.0")
out["runs"]["B_0p5T"]     out["accumulated"]
load_results_table(..., step="run")"""

CHECKS_TITLE = "Checked by run_analysis() on every call  ·  any failure → nothing is saved"
CHECKS = [
    "before:  schema · labels unique · modified_dimension and value both set or "
    "both null · every (db, run_id, guid) is in the run index",
    "classes:  one AccumulatedAnalysis per module · VERSION in each class's own "
    "body · every kwarg declared in KWARGS · labels match REQUIRED_RUNS",
    "after each analyse:  only \"data\" (xr.Dataset values) and \"results\" "
    "(scalars), same results keys for every run          "
    "after accumulate:  the same",
]


# ---------------------------------------------------------------- helpers

def new_slide(title, subtitle):
    fig = plt.figure(figsize=(16, 9))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 9)
    ax.axis("off")
    ax.text(0.45, 8.5, title, fontsize=26, weight="bold", color=INK,
            va="center")
    ax.text(0.45, 8.03, subtitle, fontsize=13, color=MUTED, va="center")
    return fig, ax


def rounded_box(ax, x, y, w, h, fc, ec="none", lw=1.5, ls="-", r=0.18, z=1):
    box = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0,rounding_size={r}",
        fc=fc, ec=ec, lw=lw, ls=ls, zorder=z,
    )
    ax.add_patch(box)
    return box


def arrow(ax, start, end, color=MUTED, lw=2.2, style="-|>", ls="-", z=3,
          scale=18):
    ax.add_patch(FancyArrowPatch(
        start, end, arrowstyle=style, mutation_scale=scale,
        color=color, lw=lw, ls=ls, zorder=z, shrinkA=0, shrinkB=0,
    ))


def chip(ax, x, y, text, color):
    w = 0.105 * len(text) + 0.3
    rounded_box(ax, x - w / 2, y - 0.16, w, 0.32, fc=color, r=0.16, z=4)
    ax.text(x, y, text, ha="center", va="center", fontsize=9.5,
            color="white", weight="bold", zorder=5)


def code_block(ax, x, y_top, w, text, size=10.5, line_h=0.205):
    """Monospace block, comment lines muted; returns its bottom y."""
    lines = text.split("\n")
    h = len(lines) * line_h + 0.25
    rounded_box(ax, x, y_top - h, w, h, fc=CODE_BG, r=0.1, z=2)
    for i, line in enumerate(lines):
        code, _, comment = line.partition("#")
        y = y_top - 0.12 - (i + 0.5) * line_h
        ax.text(x + 0.18, y, code, fontsize=size, family="monospace",
                color=INK, va="center", zorder=3)
        if comment:
            ax.text(x + 0.18 + 0.6 * size / 72 * len(code), y, "#" + comment,
                    fontsize=size, family="monospace", color=MUTED,
                    va="center", zorder=3)
    return y_top - h


def panel_header(ax, x, y, number, title, path):
    ax.text(x, y, number, fontsize=20, weight="bold", color=BORDER,
            va="center")
    ax.text(x + 0.45, y, title, fontsize=15, weight="bold", color=INK,
            va="center")
    ax.text(x + 0.45, y - 0.36, path, fontsize=10.5, family="monospace",
            color=GIT, va="center")


def sub_header(ax, x, y, text):
    ax.text(x, y, text, fontsize=9, weight="bold", color=MUTED, va="center")


# ------------------------------------------------- overview illustrations

def draw_databases(ax, cx, cy):
    """Two database cylinders."""
    for dx, dy in ((-0.28, 0.12), (0.28, -0.12)):
        x, y, w, h, e = cx + dx - 0.3, cy + dy - 0.38, 0.6, 0.76, 0.2
        ax.add_patch(Rectangle((x, y + e / 2), w, h - e, fc="white",
                               ec="none", zorder=3))
        ax.plot([x, x], [y + e / 2, y + h - e / 2], color=MUTED, lw=1.4,
                zorder=4)
        ax.plot([x + w, x + w], [y + e / 2, y + h - e / 2], color=MUTED,
                lw=1.4, zorder=4)
        ax.add_patch(Ellipse((x + w / 2, y + e / 2), w, e, fc="white",
                             ec=MUTED, lw=1.4, zorder=2))
        ax.add_patch(Ellipse((x + w / 2, y + h - e / 2), w, e, fc=CODE_BG,
                             ec=MUTED, lw=1.4, zorder=5))
        ax.text(x + w / 2, y + 0.3, ".db", fontsize=9, family="monospace",
                color=INK, ha="center", va="center", zorder=5)


def draw_index_table(ax, cx, cy):
    """Small table; the three T1 runs of the example are highlighted."""
    cols, rows, cw, ch = 4, 6, 0.3, 0.17
    x0, y0 = cx - cols * cw / 2, cy - rows * ch / 2
    for r in range(rows):
        y = y0 + (rows - 1 - r) * ch
        fc = BORDER if r == 0 else HIGHLIGHT if r in (2, 3, 5) else "white"
        for c in range(cols):
            ax.add_patch(Rectangle((x0 + c * cw, y), cw, ch, fc=fc,
                                   ec="white" if r == 0 else BORDER,
                                   lw=0.8, zorder=3))


def draw_selection_card(ax, cx, cy):
    """A selection file listing the three runs of the example."""
    w, h = 1.5, 1.05
    rounded_box(ax, cx - w / 2, cy - h / 2, w, h, fc="white", ec=BORDER,
                lw=1.2, r=0.08, z=3)
    ax.text(cx - w / 2 + 0.1, cy + h / 2 - 0.17, "Q2_wk14.json",
            fontsize=8, family="monospace", color=GIT, va="center", zorder=4)
    for i, (field, _) in enumerate(SWEEP):
        y = cy + h / 2 - 0.42 - i * 0.22
        ax.text(cx - w / 2 + 0.1, y, f"✓ run {520 + 4 * i}", fontsize=8.5,
                family="monospace", color=INK, va="center", zorder=4)
        ax.text(cx + w / 2 - 0.1, y, field, fontsize=8.5, family="monospace",
                color=MUTED, ha="right", va="center", zorder=4)


def draw_plan_card(ax, cx, cy):
    """A PLAN.md section: four fixed lines' worth of structure, then prose."""
    w, h = 1.5, 1.15
    x0, top = cx - w / 2, cy + h / 2
    rounded_box(ax, x0, cy - h / 2, w, h, fc="white", ec=BORDER, lw=1.2,
                r=0.08, z=3)
    ax.text(x0 + 0.1, top - 0.17, "PLAN.md", fontsize=8, family="monospace",
            color=GIT, va="center", zorder=4)
    ax.text(x0 + 0.1, top - 0.42, "## T1 vs field", fontsize=8.5,
            weight="bold", color=INK, va="center", zorder=4)
    ax.text(x0 + 0.1, top - 0.62, "Status: open", fontsize=7.5,
            family="monospace", color=MUTED, va="center", zorder=4)
    for i, bw in enumerate((1.25, 1.1, 0.8)):  # prose
        ax.add_patch(Rectangle((x0 + 0.1, top - 0.82 - i * 0.12), bw, 0.055,
                               fc=BORDER, ec="none", zorder=4))


def draw_decay(ax, x, y, w, h, t1_us):
    """Measured points and fitted curve of one T1 decay."""
    noise = [0.03, -0.04, 0.05, -0.02, 0.04, -0.03, 0.02]
    k = 90 / t1_us
    t = np.linspace(0, 1, 40)
    ax.plot(x + t * w, y + h * np.exp(-k * t), color=GIT, lw=1.4, zorder=4)
    tp = np.linspace(0.05, 0.95, len(noise))
    ax.scatter(x + tp * w, y + h * (np.exp(-k * tp) + noise), s=6,
               color=INK, zorder=5, lw=0)


def draw_analysis(ax, x, y, w, h):
    """3a: one panel per run, each giving T1; 3b: all T1 values together."""
    top = y + h
    col_a, col_b = x + 0.2, x + 2.05
    cb_w = w - 2.05 - 0.2
    sub_header(ax, col_a, top - 1.15, "3a  each run on its own")
    sub_header(ax, col_b, top - 1.15, "3b  all runs together")

    ph, pgap, pw = 0.5, 0.1, 1.3
    py0 = top - 1.38
    cb_h = 3 * ph + 2 * pgap
    for i, (field, t1) in enumerate(SWEEP):
        py = py0 - (i + 1) * ph - i * pgap
        rounded_box(ax, col_a, py, pw, ph, fc=CODE_BG, r=0.06, z=3)
        ax.text(col_a + 0.08, py + ph / 2, field, fontsize=9, color=INK,
                va="center", zorder=4)
        draw_decay(ax, col_a + 0.5, py + 0.08, 0.72, ph - 0.2, t1)
        arrow(ax, (col_a + pw + 0.05, py + ph / 2),
              (col_b - 0.05, py0 - cb_h / 2 + (1 - i) * 0.3),
              color=MUTED, lw=1.4, scale=10)

    rounded_box(ax, col_b, py0 - cb_h, cb_w, cb_h, fc=CODE_BG, r=0.06, z=3)
    ax.text(col_b + cb_w / 2, py0 - 0.2, "T1 vs B", fontsize=9.5,
            weight="bold", color=INK, ha="center", va="center", zorder=4)
    for i, ((_, t1), b) in enumerate(zip(SWEEP, SWEEP_FIELDS_T)):
        yy = py0 - 0.55 - i * 0.28
        ax.text(col_b + 0.15, yy, f"{b:g} T", fontsize=9, family="monospace",
                color=MUTED, va="center", zorder=4)
        ax.text(col_b + cb_w - 0.15, yy, f"{t1} µs", fontsize=9,
                family="monospace", color=INK, ha="right", va="center",
                zorder=4)
    ax.text(col_b + cb_w / 2, py0 - cb_h + 0.18, "+ fit across fields",
            fontsize=8, style="italic", color=MUTED, ha="center",
            va="center", zorder=4)


def draw_t1_points(ax, x0, y0, w, h, size=22):
    """T1 vs B points with a guide line, inside the box (x0, y0, w, h)."""
    bs = np.array(SWEEP_FIELDS_T)
    t1 = np.array([t for _, t in SWEEP])
    sx = lambda b: x0 + 0.12 * w + (b - bs.min()) / (bs.max() - bs.min()) * 0.76 * w
    sy = lambda t: y0 + 0.15 * h + (t - 15) / 30 * 0.7 * h
    ax.plot(sx(bs), sy(t1), color=GIT, lw=1.3, zorder=4)
    ax.scatter(sx(bs), sy(t1), s=size, color=INK, zorder=5, lw=0)


def draw_mini_plot(ax, cx, cy):
    """T1 vs B, as it would appear in a figure."""
    w, h = 1.15, 0.95
    x0, y0 = cx - w / 2 + 0.08, cy - h / 2
    ax.plot([x0, x0, x0 + w], [y0 + h, y0, y0], color=INK, lw=1.2, zorder=3)
    draw_t1_points(ax, x0, y0, w, h)
    ax.text(x0 + w, y0 - 0.12, "B", fontsize=8.5, color=MUTED, ha="right",
            va="center")
    ax.text(x0 - 0.08, y0 + h, "T1", fontsize=8.5, color=MUTED, ha="right",
            va="top")


def draw_report_thumb(ax, cx, cy):
    """One report slide: title, figure, and the verdict from PLAN.md."""
    w, h = 1.3, 0.73
    x0, y0 = cx - w / 2, cy - 0.2
    rounded_box(ax, x0, y0, w, h, fc="white", ec=INK, lw=1.1, r=0.05, z=3)
    ax.text(x0 + 0.08, y0 + h - 0.12, "T1 vs field", fontsize=7,
            weight="bold", color=INK, va="center", zorder=4)
    draw_t1_points(ax, x0 + 0.1, y0 + 0.05, w - 0.2, h - 0.25, size=8)
    pw = 1.0
    rounded_box(ax, cx - pw / 2, y0 - 0.4, pw, 0.25, fc=VERDICT["confirmed"],
                r=0.12, z=3)
    ax.text(cx, y0 - 0.275, "confirmed", fontsize=7.5, weight="bold",
            color="white", ha="center", va="center", zorder=4)


ILLUSTRATIONS = {"Raw data": draw_databases, "Index": draw_index_table,
                 "Plan": draw_plan_card, "Select": draw_selection_card,
                 "Analysis": draw_analysis, "Figures": draw_mini_plot,
                 "Report": draw_report_thumb}


# ---------------------------------------------------------- roles slide

def kind_chip(ax, x, y, kind):
    """Coloured pill naming the kind of file; x is its left edge. Returns its width."""
    text, _, color = KIND[kind]
    w = 0.072 * len(text) + 0.26
    rounded_box(ax, x, y - 0.125, w, 0.25, fc=color, r=0.125, z=4)
    ax.text(x + w / 2, y, text, fontsize=8, weight="bold", color="white",
            ha="center", va="center", zorder=5)
    return w


def gate_badge(ax, x, y, number, color=RESEARCHER_DARK):
    ax.add_patch(Ellipse((x, y), 0.28, 0.28, fc=color, ec="none", zorder=5))
    ax.text(x, y, number, fontsize=8.5, weight="bold", color="white",
            ha="center", va="center", zorder=6)


def icon_person(ax, cx, cy, color="white"):
    ax.add_patch(Ellipse((cx, cy + 0.08), 0.15, 0.15, fc=color, ec="none", zorder=4))
    rounded_box(ax, cx - 0.14, cy - 0.16, 0.28, 0.15, fc=color, r=0.07, z=4)


def icon_agent(ax, cx, cy, color="white", accent=AGENT[0]):
    ax.plot([cx, cx], [cy + 0.12, cy + 0.2], color=color, lw=1.5, zorder=4)
    ax.add_patch(Ellipse((cx, cy + 0.21), 0.06, 0.06, fc=color, ec="none", zorder=4))
    rounded_box(ax, cx - 0.16, cy - 0.15, 0.32, 0.27, fc=color, r=0.07, z=4)
    for dx in (-0.065, 0.065):
        ax.add_patch(Ellipse((cx + dx, cy - 0.01), 0.06, 0.06, fc=accent,
                             ec="none", zorder=5))


def icon_stack(ax, cx, cy, color="white", accent=MAINTAINER[0]):
    for i in range(3):
        y = cy - 0.16 + i * 0.12
        rounded_box(ax, cx - 0.16, y, 0.32, 0.09, fc=color, r=0.03, z=4)
        ax.add_patch(Ellipse((cx + 0.1, y + 0.045), 0.035, 0.035, fc=accent,
                             ec="none", zorder=5))


ICONS = {"Researchers": icon_person, "Agents": icon_agent, "Maintainers": icon_stack}


def roles_slide(path="analysis_campaign_roles.png"):
    fig, ax = new_slide(
        "You do the science. The stack does the rest.",
        "Who does what at each step of the campaign, and where you and your "
        "agent work together.",
    )

    # Legend: kinds of file, gates
    x, y = 0.45, 7.6
    for kind, (_, label, _) in KIND.items():
        x += kind_chip(ax, x, y, kind) + 0.12
        ax.text(x, y, label, fontsize=9.5, color=INK, va="center")
        x += 0.066 * len(label) + 0.42
    gate_badge(ax, x + 0.14, y, "1")
    ax.text(x + 0.38, y, "you approve here", fontsize=9.5, color=INK,
            va="center")

    label_w, gap = 1.9, 0.09
    gx = 0.45 + label_w + 0.12
    cw = (15.55 - gx - 6 * gap) / 7
    col_x = [gx + i * (cw + gap) for i in range(7)]

    # Step headers, and the plan feeding forward to the report
    hy, hh = 6.32, 0.55
    for cx, num, name in zip(col_x, ROLE_STEPS, ROLE_STEP_NAMES):
        rounded_box(ax, cx, hy, cw, hh, fc=INK, r=0.08, z=2)
        ax.text(cx + 0.14, hy + hh / 2, num, fontsize=11, weight="bold",
                color="#9AA5B1", va="center", zorder=3)
        ax.text(cx + 0.5, hy + hh / 2, name, fontsize=10.5, weight="bold",
                color="white", va="center", linespacing=1.05, zorder=3)
    draw_feed_forward(ax, col_x[2] + cw / 2, col_x[6] + cw / 2, hy + hh, 7.1)

    # Optional publishing of the report, top right above the Report column
    bw, bh = 2.75, 0.66
    bx, by = 15.55 - bw, 7.72
    rounded_box(ax, bx, by, bw, bh, fc=MAINTAINER[1], ec=MAINTAINER[0],
                lw=2.2, ls="--", r=0.12, z=2)
    icon_stack(ax, bx + 0.32, by + bh / 2, color=MAINTAINER[0], accent=MAINTAINER[1])
    ax.text(bx + 0.62, by + bh / 2, HOSTING, fontsize=10, weight="bold",
            color=INK, va="center", linespacing=1.2, zorder=3)

    # One coloured lane per role
    lanes = {"Researchers": (4.4, 1.75), "Agents": (2.5, 1.45),
             "Maintainers": (1.2, 1.1)}
    style = {  # cell border width, text size, text colour
        "Researchers": (1.8, 10, INK), "Agents": (1.4, 9.6, INK),
        "Maintainers": (1.0, 9, MUTED)}
    for role, desc, (accent, bg, border), cells in ROLES:
        ly, lh = lanes[role]
        lw, size, color = style[role]
        rounded_box(ax, 0.45, ly, 15.1, lh, fc=bg, r=0.14, z=0)
        rounded_box(ax, 0.45, ly, label_w, lh, fc=accent, r=0.14, z=1)
        ICONS[role](ax, 0.76, ly + lh - 0.36)
        ax.text(1.02, ly + lh - 0.36, role, fontsize=12.5, weight="bold",
                color="white", va="center", zorder=4)
        ax.text(0.62, ly + lh - 0.64, desc, fontsize=8.8, color="white",
                va="top", linespacing=1.3, zorder=4)
        for cx, (text, kinds, gate) in zip(col_x, cells):
            if text is None:
                ax.text(cx + cw / 2, ly + lh / 2, "—", fontsize=12,
                        color=border, ha="center", va="center", zorder=3)
                continue
            rounded_box(ax, cx, ly + 0.08, cw, lh - 0.16,
                        fc="white" if role != "Maintainers" else "#FAFBFC",
                        ec=border, lw=lw, r=0.1, z=2)
            ax.text(cx + 0.12, ly + lh - 0.22, text, fontsize=size,
                    color=color, va="top", linespacing=1.25, zorder=3)
            kx = cx + 0.12
            for kind in kinds:
                kx += kind_chip(ax, kx, ly + 0.3, kind) + 0.08
            if gate:
                gate_badge(ax, cx + cw - 0.26, ly + 0.3, str(gate))

    # Where researchers and agents work together
    p_bottom, a_top = lanes["Researchers"][0] + 0.08, sum(lanes["Agents"]) - 0.08
    mid = (p_bottom + a_top) / 2
    ax.text(0.62, mid, "⇅ where you and\n    your agent meet", fontsize=8.8,
            style="italic", weight="bold", color=AGENT_DARK, va="center",
            linespacing=1.15)
    for cx, label in zip(col_x[2:], TOGETHER):
        c = cx + cw / 2
        ax.plot([c, c], [a_top, p_bottom], color=AGENT[2], lw=2.5, zorder=1)
        text = f"⇅  {label}"
        w = 0.068 * len(text) + 0.4
        rounded_box(ax, c - w / 2, mid - 0.15, w, 0.3, fc=AGENT[0], r=0.15, z=4)
        ax.text(c, mid, text, fontsize=8.8, weight="bold", color="white",
                ha="center", va="center", zorder=5)

    # What it means for researchers
    rounded_box(ax, 0.45, 0.15, 15.1, 0.88, fc=INK)
    ax.text(0.75, 0.76, CONTROL, fontsize=11.5, weight="bold", color="white",
            va="center")
    x = 0.75 + 0.098 * len(CONTROL) + 0.3
    for i, point in enumerate(CONTROL_POINTS):
        gate_badge(ax, x + 0.14, 0.76, str(i + 1), color=RESEARCHER[0])
        ax.text(x + 0.38, 0.76, point, fontsize=11.5, weight="bold",
                color="white", va="center")
        x += 0.38 + 0.098 * len(point) + 0.5
    ax.text(0.75, 0.4, HANDLED, fontsize=10.5, color="#D5DAE0", va="center")

    fig.savefig(path, dpi=150, facecolor="white")
    return fig


# ---------------------------------------------------------- overview slide

def draw_stage(ax, x, y, w, h, stage):
    human = stage["human"]
    rounded_box(ax, x, y, w, h, fc="white",
                ec=INK if human else BORDER,
                lw=2.2 if human else 1.4, ls="--" if human else "-", z=2)

    top = y + h
    ax.text(x + 0.14, top - 0.34, stage["num"], fontsize=16, weight="bold",
            color=BORDER, va="center", zorder=3)
    ax.text(x + w / 2 + 0.14, top - 0.34, stage["title"], fontsize=13,
            weight="bold", color=INK, ha="center", va="center", zorder=3)
    ax.text(x + w / 2, top - 0.7, stage["sub"], fontsize=9,
            style="italic", color=MUTED, ha="center", va="center", zorder=3)
    ax.plot([x + 0.15, x + w - 0.15], [top - 0.92] * 2,
            color="#E1E5EA", lw=1.2, zorder=3)

    if stage["title"] == "Analysis":
        draw_analysis(ax, x, y, w, h)
    else:
        ILLUSTRATIONS[stage["title"]](ax, x + w / 2, top - 1.65)
        ax.text(x + w / 2, top - 2.45, stage["caption"], fontsize=9.5,
                color=INK, ha="center", va="top", linespacing=1.35, zorder=3)

    where = stage["where"]
    if w > 3:  # wide box: chips side by side, centred as a group
        widths = [0.105 * len(label) + 0.3 for label, _ in where]
        cx = x + (w - sum(widths) - 0.2 * (len(where) - 1)) / 2
        for (label, color), cw in zip(where, widths):
            chip(ax, cx + cw / 2, y + 0.32, label, color)
            cx += cw + 0.2
    else:
        for i, (label, color) in enumerate(where):
            chip(ax, x + w / 2, y + 0.32 + 0.4 * (len(where) - 1 - i),
                 label, color)


def draw_report_panel(ax, x, y, w, h):
    """The progress view of the report: one row per question in PLAN.md."""
    rounded_box(ax, x, y, w, h, fc=PANEL, z=1)
    ax.text(x + 0.3, y + h - 0.35, "Report: progress per question",
            fontsize=13, weight="bold", color=INK, va="center")
    ax.text(x + 0.3, y + h - 0.62,
            "computed from PLAN.md, selections\n"
            "and outputs; Status set by the owner",
            fontsize=9.5, color=MUTED, va="top", linespacing=1.35)

    gx0, cw, ch, gap = x + 5.2, 1.2, 0.28, 0.06
    for c, name in enumerate(REPORT_COLS):
        ax.text(gx0 + c * (cw + gap) + cw / 2, y + h - 0.25, name,
                fontsize=8.5, color=MUTED, ha="center", va="center")
    ax.text(gx0 + 5 * (cw + gap) + 0.1 + 0.82, y + h - 0.25, "Status",
            fontsize=8.5, color=MUTED, ha="center", va="center")
    for r, (name, cells, verdict) in enumerate(REPORT_ROWS):
        ry = y + h - 0.45 - (r + 1) * ch - r * gap
        ax.text(gx0 - 0.15, ry + ch / 2, name, fontsize=9.5, color=INK,
                ha="right", va="center")
        for c, state in enumerate(cells):
            ax.add_patch(Rectangle((gx0 + c * (cw + gap), ry), cw, ch,
                                   fc=PROGRESS[state], ec="none", zorder=2))
        px = gx0 + 5 * (cw + gap) + 0.1
        rounded_box(ax, px, ry, 1.65, ch, fc=VERDICT[verdict], r=0.12, z=2)
        ax.text(px + 0.82, ry + ch / 2, verdict, fontsize=8.5, weight="bold",
                color="white", ha="center", va="center", zorder=3)

    lx = x + w - 1.3
    for i, (name, color) in enumerate(PROGRESS.items()):
        ly = y + h - 0.55 - i * 0.32
        ax.add_patch(Rectangle((lx, ly - 0.1), 0.2, 0.2, fc=color, ec="none"))
        ax.text(lx + 0.3, ly, name, fontsize=8.5, color=INK, va="center")


def draw_feed_forward(ax, x_plan, x_report, y_box, y_line):
    """Thick red line from the plan to the report, with its label in a pill.
    y_box is the edge of the plan and report boxes, y_line the height of the line."""
    ax.add_patch(Ellipse((x_plan, y_box), 0.2, 0.2, fc=FEED, ec="white",
                         lw=1.5, zorder=6))
    ax.plot([x_plan, x_plan, x_report], [y_box, y_line, y_line], color=FEED,
            lw=3.2, solid_joinstyle="round", solid_capstyle="round", zorder=5)
    arrow(ax, (x_report, y_line), (x_report, y_box), color=FEED, lw=3.2,
          scale=24, z=5)
    text = FEED_LABEL
    w = 0.075 * len(text) + 0.45
    xm = (x_plan + x_report) / 2
    rounded_box(ax, xm - w / 2, y_line - 0.16, w, 0.32, fc=FEED, r=0.16, z=6)
    ax.text(xm, y_line, text, fontsize=9.2, weight="bold", color="white",
            ha="center", va="center", zorder=7)


def draw_legend(ax, x, y):
    chip(ax, x + 0.45, y, "git", GIT)
    ax.text(x + 0.85, y, "code, plan, selections, figures", fontsize=10,
            color=INK, va="center")
    chip(ax, x + 4.1, y, "drive", DRIVE)
    ax.text(x + 4.6, y, "raw data, averaged copies, outputs", fontsize=10,
            color=INK, va="center")
    rounded_box(ax, x + 8.35, y - 0.16, 0.55, 0.32, fc="white", ec=INK,
                lw=2.0, ls="--", r=0.08, z=3)
    ax.text(x + 9.05, y, "researchers provide content", fontsize=10,
            color=INK, va="center")
    ax.text(15.55, y, "roles: previous slide  ·  formats: next slide →",
            fontsize=10, style="italic", color=MUTED, ha="right",
            va="center")


def draw_rules(ax, x, y, w, h):
    rounded_box(ax, x, y, w, h, fc=INK, z=1)
    ax.text(x + 0.3, y + h / 2, "Rules", fontsize=13, weight="bold",
            color="white", va="center")
    cell = (w - 1.4) / len(RULES)
    for i, rule in enumerate(RULES):
        cx = x + 1.4 + i * cell
        ax.text(cx, y + h / 2, f"{i + 1}", fontsize=17, weight="bold",
                color=DRIVE, va="center")
        ax.text(cx + 0.35, y + h / 2, rule, fontsize=10, color="white",
                va="center", linespacing=1.3)


def overview_slide(path="analysis_campaign_overview.png"):
    fig, ax = new_slide(
        "Organising an analysis campaign",
        "Example: is T1 limited by field-dependent loss? From the question "
        "to the verdict, each step hands a fixed format to the next.",
    )

    gap, x, h, y0 = 0.265, 0.45, 4.0, 3.2
    centres = {}
    for i, stage in enumerate(STAGES):
        if i:
            arrow(ax, (x - gap + 0.04, y0 + h / 2), (x - 0.04, y0 + h / 2),
                  color=INK, scale=14)
        draw_stage(ax, x, y0, stage["w"], h, stage)
        centres[stage["title"]] = x + stage["w"] / 2
        x += stage["w"] + gap

    draw_legend(ax, 0.45, 7.55)
    draw_feed_forward(ax, centres["Plan"], centres["Report"], y0, 2.85)
    draw_report_panel(ax, 0.45, 1.0, 15.1, 1.55)
    draw_rules(ax, 0.45, 0.15, 15.1, 0.7)

    fig.savefig(path, dpi=150, facecolor="white")
    return fig


# ----------------------------------------------------------- formats slide

def formats_slide(path="analysis_campaign_formats.png"):
    fig, ax = new_slide(
        "File formats between the steps",
        "The structured files and classes (PLAN.md is natural language). One "
        "selection file = one call of the analysis.",
    )
    py, ph = 1.3, 6.3
    top = py + ph

    # 1. Selection file
    x, w = 0.45, 5.0
    rounded_box(ax, x, py, w, ph, fc="white", ec=BORDER, lw=1.4)
    panel_header(ax, x + 0.3, top - 0.42, "1", "Selection file",
                 "selections/<analysis>/<name>.json")
    bottom = code_block(ax, x + 0.3, top - 0.95, w - 0.6, SELECTION_JSON,
                        size=9.5, line_h=0.19)
    for i, (name, desc, indent) in enumerate(SELECTION_FIELDS):
        fy = bottom - 0.27 - i * 0.235
        if i == 3:
            sub_header(ax, x + 0.3, fy + 0.02, "each run:")
        fy -= 0.22 if i >= 3 else 0
        ax.text(x + 0.3 + 0.2 * indent, fy, name, fontsize=9.5,
                family="monospace", weight="bold", color=INK, va="center")
        ax.text(x + 2.45, fy, desc, fontsize=9.5, color=MUTED, va="center")

    # 2. Analysis module
    x, w = 5.7, 5.0
    rounded_box(ax, x, py, w, ph, fc="white", ec=INK, lw=2.2, ls="--")
    panel_header(ax, x + 0.3, top - 0.42, "2", "Analysis module",
                 "analysis/<analysis>.py")
    bottom = code_block(ax, x + 0.3, top - 0.95, w - 0.6, ANALYSIS_CODE,
                        size=9.5, line_h=0.178)
    sub_header(ax, x + 0.3, bottom - 0.2, "kwargs from the selection file")
    for i, note in enumerate(ANALYSIS_NOTES):
        ax.text(x + 0.3, bottom - 0.42 - i * 0.22, note, fontsize=9.5,
                color=INK, va="center")

    # 3. Saved outputs
    x, w = 10.95, 4.6
    rounded_box(ax, x, py, w, ph, fc="white", ec=BORDER, lw=1.4)
    panel_header(ax, x + 0.3, top - 0.42, "3", "Saved outputs",
                 "OUTPUT_ROOT/<analysis>/v<VERSION>/")
    sub_header(ax, x + 0.3, top - 1.05, "analyse and accumulate both return")
    bottom = code_block(ax, x + 0.3, top - 1.2, w - 0.6, OUTPUT_CODE,
                        size=9.5, line_h=0.2)
    sub_header(ax, x + 0.3, bottom - 0.25, "saved on the drive by run_analysis()")
    bottom = code_block(ax, x + 0.3, bottom - 0.4, w - 0.6, STORAGE_TREE,
                        size=9.5, line_h=0.2)
    sub_header(ax, x + 0.3, bottom - 0.25, "read in figures with wynaut.io")
    code_block(ax, x + 0.3, bottom - 0.4, w - 0.6, LOAD_CODE,
               size=9, line_h=0.2)

    # Checks strip
    rounded_box(ax, 0.45, 0.15, 15.1, 0.95, fc=INK)
    ax.text(0.75, 0.92, CHECKS_TITLE, fontsize=11, weight="bold",
            color="white", va="center")
    for i, line in enumerate(CHECKS):
        ax.text(0.75, 0.68 - i * 0.2, line, fontsize=9.5, color="#D5DAE0",
                va="center")

    fig.savefig(path, dpi=150, facecolor="white")
    return fig


if __name__ == "__main__":
    img_dir = Path(__file__).resolve().parent.parent / "img"
    figs = [roles_slide(img_dir / "analysis_campaign_roles.png"),
            overview_slide(img_dir / "analysis_campaign_overview.png"),
            formats_slide(img_dir / "analysis_campaign_formats.png")]
    with PdfPages(img_dir / "analysis_campaign_slides.pdf") as pdf:
        for fig in figs:
            pdf.savefig(fig, facecolor="white")
