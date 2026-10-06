"""
experiments.py - runs the three experiments and saves plots + raw numbers.

  A. Correctness : violation rate vs eps for naive / start-only / spanner
  B. Cost        : mean commit-wait latency vs eps (spanner mode)
  C. Broken bound: spanner-mode violations when real clock error exceeds
                   the advertised eps (violation_factor k > 1)

Usage:  python experiments.py
Output: results/*.png and results/results.csv (the numbers behind the plots)
"""

import csv
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sim import MODES, run_trials

N = 20000          # trials per data point
GAP_MAX = 20.0     # ms; real-time gap between T1's ack and T2's start is U(0, GAP_MAX]
SEED = 7           # same seed for every mode => identical offsets and gaps (controlled comparison)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

# Chart styling (light surface). Categorical colors validated as an all-pairs
# colorblind-safe set; the aqua is below 3:1 contrast, so every series is also
# direct-labeled and has its own marker shape, and results.csv is the table view.
SURFACE, INK, INK2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
COLORS = {"naive": "#2a78d6", "start_only": "#eb6834", "spanner": "#1baf7a"}
NAMES = {
    "naive": "naive (local clock)",
    "start_only": "start rule only",
    "spanner": "start rule + commit wait",
}


def style_axes(ax, xlabel, ylabel, title):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.set_xlabel(xlabel, color=INK2, fontsize=10)
    ax.set_ylabel(ylabel, color=INK2, fontsize=10)
    ax.set_title(title, color=INK, fontsize=12, loc="left", pad=12)


def new_figure():
    fig, ax = plt.subplots(figsize=(7, 4.2), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    return fig, ax


def save(fig, name):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    print("saved", path)


# ---------------------------------------------------------------- Experiment A
def experiment_a():
    eps_values = [0, 1, 2, 3, 4, 6, 8, 10]
    rows = []
    for mode in MODES:
        for eps in eps_values:
            r = run_trials(N, eps, mode, violation_factor=1.0, gap_max=GAP_MAX, seed=SEED)
            r["experiment"] = "A"
            rows.append(r)

    fig, ax = new_figure()
    style = {
        "naive": dict(marker="o", markersize=6, linestyle="-"),
        # hollow, larger marker + dashes so it stays visible where it overlaps naive
        "start_only": dict(marker="o", markersize=10, linestyle="--",
                           markerfacecolor=SURFACE, markeredgewidth=1.5),
        "spanner": dict(marker="s", markersize=6, linestyle="-"),
    }
    for mode in MODES:
        pts = [r for r in rows if r["mode"] == mode]
        ax.plot([p["eps"] for p in pts], [100 * p["violation_rate"] for p in pts],
                color=COLORS[mode], linewidth=2, label=NAMES[mode], **style[mode])

    naive_last = [r for r in rows if r["mode"] == "naive"][-1]
    ax.annotate("naive and start-only are identical\n(the two curves coincide)",
                xy=(naive_last["eps"], 100 * naive_last["violation_rate"]),
                xytext=(9.5, 5.5), textcoords="data", ha="right", va="center",
                color=INK2, fontsize=9,
                arrowprops=dict(arrowstyle="-", color=AXIS, linewidth=1))
    ax.annotate("full protocol: 0 violations",
                xy=(eps_values[-1], 0), xytext=(-8, 12), textcoords="offset points",
                ha="right", color=INK2, fontsize=9)
    ax.set_ylim(-1.0, None)
    ax.legend(loc="upper left", frameon=False, labelcolor=INK2, fontsize=9)
    style_axes(ax, "clock uncertainty bound ε (ms)",
               "external-consistency violations (% of pairs)",
               "Only commit wait preserves external consistency")
    save(fig, "violations_vs_eps.png")
    return rows


# ---------------------------------------------------------------- Experiment B
def experiment_b(rows_a):
    pts = [r for r in rows_a if r["mode"] == "spanner"]
    fig, ax = new_figure()
    xs = [p["eps"] for p in pts]
    ax.plot(xs, [p["mean_commit_wait"] for p in pts], color=COLORS["spanner"],
            linewidth=2.5, marker="s", markersize=6, label="measured mean commit wait")
    # drawn on top so it stays visible where it coincides with the measurements
    ax.plot(xs, [2 * x for x in xs], color=INK, linewidth=1.2, linestyle=(0, (4, 3)),
            label="2ε (expected wait)")
    ax.text(xs[-1], 3.0, "measured points sit on the 2ε line", ha="right",
            color=INK2, fontsize=9)
    ax.legend(loc="upper left", frameon=False, labelcolor=INK2, fontsize=9)
    style_axes(ax, "clock uncertainty bound ε (ms)", "mean commit wait per transaction (ms)",
               "Commit wait costs about 2ε of latency")
    save(fig, "commit_wait_vs_eps.png")


# ---------------------------------------------------------------- Experiment C
def experiment_c():
    eps = 4.0
    ks = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0]
    rows = []
    for k in ks:
        r = run_trials(N, eps, "spanner", violation_factor=k, gap_max=GAP_MAX, seed=SEED)
        r["experiment"] = "C"
        rows.append(r)

    fig, ax = new_figure()
    ax.axvline(1.0, color=AXIS, linewidth=1.2, linestyle="--")
    ax.plot(ks, [100 * r["violation_rate"] for r in rows], color=COLORS["spanner"],
            linewidth=2, marker="s", markersize=6)
    ax.set_ylim(-1.0, None)
    top = ax.get_ylim()[1]
    ax.text(0.97, 0.93 * top, "ε valid (k ≤ 1)", ha="right", color=INK2, fontsize=9)
    ax.text(1.03, 0.93 * top, "ε broken (k > 1)", ha="left", color=INK2, fontsize=9)
    style_axes(ax, "real clock error / advertised ε  (k)",
               "external-consistency violations (% of pairs)",
               f"Commit wait fails when the ε bound is wrong (advertised ε = {eps:g} ms)")
    save(fig, "broken_bound.png")
    return rows


def write_csv(rows):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "results.csv")
    fields = ["experiment", "mode", "eps", "violation_factor", "n",
              "violations", "violation_rate", "mean_commit_wait"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in fields})
    print("saved", path)


def print_table(title, rows, key):
    print(f"\n{title}")
    for r in rows:
        print(f"  {r['mode']:11s} {key}={r[key]:<5g} violations={r['violations']:5d} "
              f"({r['violation_rate']:6.2%})  mean wait={r['mean_commit_wait']:6.2f} ms")


if __name__ == "__main__":
    rows_a = experiment_a()
    experiment_b(rows_a)
    rows_c = experiment_c()
    write_csv(rows_a + rows_c)
    print_table("Experiment A/B (k = 1, sweeping eps)", rows_a, "eps")
    print_table("Experiment C (eps = 4 ms, sweeping k)", rows_c, "violation_factor")