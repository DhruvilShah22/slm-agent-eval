"""Paper figures from analysis/results.json (run analyze.py first).

Colors follow the validated reference palette from the dataviz method:
categorical slots for series identity (fixed order, never cycled), status
colors for fault-outcome states, muted inks for chrome. Sub-3:1 slots (aqua,
yellow) carry direct value labels per the relief rule.
"""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIGS = ROOT / "analysis" / "figures"

# Reference palette (light mode)
CAT = {"blue": "#2a78d6", "aqua": "#1baf7a", "yellow": "#eda100",
       "green": "#008300", "violet": "#4a3aa7", "red": "#e34948",
       "magenta": "#e87ba4", "orange": "#eb6834"}
STATUS = {"good": "#0ca30c", "warning": "#fab219",
          "serious": "#ec835a", "critical": "#d03b3b"}
INK = {"primary": "#0b0b0b", "secondary": "#52514e", "muted": "#898781",
       "grid": "#e1e0d9", "baseline": "#c3c2b7", "surface": "#fcfcfb"}

FAIL_COLORS = {  # fixed category -> hue mapping, identical across figures
    "no_tool_call": CAT["blue"], "wrong_tool": CAT["aqua"],
    "malformed_args": CAT["yellow"], "bad_arg_values": CAT["green"],
    "ignored_tool_error": CAT["violet"], "synthesis_error": CAT["red"],
    "max_turns": CAT["orange"],
}
GROUPS = [("C1", "C2", "1.5B Q4_K_M"), ("C3", "C4", "1.5B Q8_0"),
          ("C5", "C6", "3B Q4_K_M")]


def style_axes(ax):
    ax.set_facecolor(INK["surface"])
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(INK["baseline"])
    ax.tick_params(colors=INK["muted"], labelcolor=INK["secondary"])
    ax.yaxis.grid(True, color=INK["grid"], linewidth=0.8)
    ax.set_axisbelow(True)


def fig_success(cells: dict) -> None:
    fig, ax = plt.subplots(figsize=(6.4, 3.6), dpi=200)
    xs = range(len(GROUPS))
    w = 0.34
    for off, cond, color in ((-w / 2, "baseline", CAT["blue"]),
                             (w / 2, "guardrail", CAT["aqua"])):
        ids = [g[0] if cond == "baseline" else g[1] for g in GROUPS]
        rates = [cells[i]["rate"] for i in ids]
        los = [cells[i]["rate"] - cells[i]["wilson95"][0] for i in ids]
        his = [cells[i]["wilson95"][1] - cells[i]["rate"] for i in ids]
        pos = [x + off for x in xs]
        ax.bar(pos, rates, width=w - 0.04, color=color, label=cond, zorder=3)
        ax.errorbar(pos, rates, yerr=[los, his], fmt="none",
                    ecolor=INK["secondary"], elinewidth=1.2, capsize=3,
                    zorder=4)
        for x, r, hi in zip(pos, rates, his):  # relief rule: direct labels
            ax.text(x, r + hi + 0.018, f"{r:.2f}", ha="center", fontsize=8,
                    color=INK["primary"])
    ax.set_xticks(list(xs), [g[2] for g in GROUPS])
    ax.set_ylim(0, 0.55)
    ax.set_ylabel("Task success rate (Wilson 95% CI)", color=INK["secondary"])
    ax.legend(frameon=False, loc="upper left")
    style_axes(ax)
    fig.tight_layout()
    fig.savefig(FIGS / "fig1_success_rates.png", facecolor=INK["surface"])
    plt.close(fig)


def fig_passk(cells: dict) -> None:
    fig, ax = plt.subplots(figsize=(6.4, 3.6), dpi=200)
    ks = [1, 2, 4, 8]
    colors = [CAT["blue"], CAT["aqua"], CAT["yellow"]]
    for (base, guard, label), color in zip(GROUPS, colors):
        for cell, ls, suffix in ((base, "-", "baseline"),
                                 (guard, "--", "guardrail")):
            ys = [cells[cell].get(f"pass^{k}") for k in ks]
            ax.plot(ks, ys, ls, color=color, linewidth=2, marker="o",
                    markersize=5, label=f"{label} ({suffix})")
    ax.set_xticks(ks, [f"k={k}" for k in ks])
    ax.set_ylabel("pass^k (all k trials succeed)", color=INK["secondary"])
    ax.legend(frameon=False, fontsize=7.5, ncol=1)
    style_axes(ax)
    fig.tight_layout()
    fig.savefig(FIGS / "fig2_passk.png", facecolor=INK["surface"])
    plt.close(fig)


def fig_failures(cells: dict) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 3.8), dpi=200)
    order = list(FAIL_COLORS)
    rows = [g[i] for g in GROUPS for i in (0, 1)]
    labels = [f"{g[2]}\n{c}" for g in GROUPS
              for c in ("baseline", "guardrail")]
    for y, cell in enumerate(rows):
        n = cells[cell]["n"]
        left = 0.0
        segs = [("success", cells[cell]["successes"] / n, INK["baseline"])]
        segs += [(k, cells[cell]["first_failures"].get(k, 0) / n,
                  FAIL_COLORS[k]) for k in order]
        for name, frac, color in segs:
            if frac == 0:
                continue
            ax.barh(y, frac, left=left, color=color, height=0.62,
                    edgecolor=INK["surface"], linewidth=1.5, zorder=3)
            if frac >= 0.08:  # selective direct labels
                ax.text(left + frac / 2, y, f"{frac:.0%}", ha="center",
                        va="center", fontsize=7, color="#ffffff"
                        if name in ("synthesis_error", "no_tool_call",
                                    "ignored_tool_error", "bad_arg_values")
                        else INK["primary"])
            left += frac
    ax.set_yticks(range(len(rows)), labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel("share of 200 episodes (first failure)",
                  color=INK["secondary"])
    handles = ([plt.Rectangle((0, 0), 1, 1, color=INK["baseline"])]
               + [plt.Rectangle((0, 0), 1, 1, color=FAIL_COLORS[k])
                  for k in order])
    ax.legend(handles, ["success"] + order, frameon=False, fontsize=7,
              ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.18))
    ax.xaxis.grid(True, color=INK["grid"], linewidth=0.8)
    ax.yaxis.grid(False)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(INK["baseline"])
    ax.set_facecolor(INK["surface"])
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(FIGS / "fig3_first_failures.png", facecolor=INK["surface"],
                bbox_inches="tight")
    plt.close(fig)


def fig_s5(s5: dict) -> None:
    fig, ax = plt.subplots(figsize=(6.8, 3.4), dpi=200)
    rows = [g[i] for g in GROUPS for i in (0, 1)]
    labels = [f"{g[2]}\n{c}" for g in GROUPS
              for c in ("baseline", "guardrail")]
    segs = [("recovered", STATUS["good"]), ("refused, no retry",
            STATUS["warning"]), ("hallucinated answer", STATUS["critical"]),
            ("other unrecovered", INK["baseline"])]
    for y, cell in enumerate(rows):
        v = s5[cell]
        fired = max(v["fault_fired"], 1)
        other = (v["answered_unrecovered"] - v["refused"]
                 - v["hallucinated_answer"])
        other += v["fault_fired"] - v["recovered"] - v["answered_unrecovered"]
        vals = [v["recovered"], v["refused"], v["hallucinated_answer"], other]
        left = 0.0
        for (name, color), val in zip(segs, vals):
            frac = val / fired
            if frac == 0:
                continue
            ax.barh(y, frac, left=left, color=color, height=0.62,
                    edgecolor=INK["surface"], linewidth=1.5, zorder=3)
            if frac >= 0.10:
                ax.text(left + frac / 2, y, str(val), ha="center",
                        va="center", fontsize=7.5, color=INK["primary"]
                        if color in (STATUS["warning"], INK["baseline"])
                        else "#ffffff")
            left += frac
    ax.set_yticks(range(len(rows)), labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel("share of fired faults (n varies by cell)",
                  color=INK["secondary"])
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for _, c in segs]
    ax.legend(handles, [s for s, _ in segs], frameon=False, fontsize=7.5,
              ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.2))
    ax.xaxis.grid(True, color=INK["grid"], linewidth=0.8)
    ax.yaxis.grid(False)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(INK["baseline"])
    ax.set_facecolor(INK["surface"])
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(FIGS / "fig4_fault_recovery.png", facecolor=INK["surface"],
                bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    FIGS.mkdir(parents=True, exist_ok=True)
    res = json.loads((ROOT / "analysis" / "results.json")
                     .read_text(encoding="utf-8"))["core_v1"]
    plt.rcParams.update({"font.family": "sans-serif", "font.size": 9,
                         "text.color": INK["primary"],
                         "axes.labelcolor": INK["secondary"],
                         "figure.facecolor": INK["surface"]})
    fig_success(res["cells"])
    fig_passk(res["cells"])
    fig_failures(res["cells"])
    fig_s5(res["s5"])
    print("wrote 4 figures to", FIGS)


if __name__ == "__main__":
    main()
