"""Scientific figure for measured execution gains, including dense comparison."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "experiments/batched-execution-v1"


def main():
    path = RUN / "aggregate.json"
    report = json.loads(path.read_text())
    plt.rcParams.update(
        {
            "figure.facecolor": "#171b1b",
            "axes.facecolor": "#171b1b",
            "savefig.facecolor": "#171b1b",
            "text.color": "#e5e9df",
            "axes.labelcolor": "#c0cbc5",
            "xtick.color": "#b3bfb8",
            "ytick.color": "#b3bfb8",
            "axes.edgecolor": "#65746c",
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "svg.fonttype": "none",
        }
    )
    fig, (latency, gain) = plt.subplots(1, 2, figsize=(16, 9))
    fig.subplots_adjust(left=0.075, right=0.97, top=0.73, bottom=0.25, wspace=0.25)
    fig.text(
        0.075,
        0.93,
        "A faster reference implementation; dense attention still wins",
        fontsize=23,
        weight="bold",
    )
    fig.text(
        0.075,
        0.875,
        "CPU float64  /  unchanged routing  /  three fresh processes × three fixed reference seeds",
        fontsize=12,
        color="#bac8bf",
    )
    contexts = (256, 512, 1024)
    styles = [
        ("reference", "Original reference", "#aab7b1", -0.25),
        ("batched", "Batched prototype", "#e8a071", 0),
        ("sdpa", "Native dense SDPA", "#76bac7", 0.25),
    ]
    for engine, label, color, offset in styles:
        values = [
            next(
                r
                for r in report["rows"]
                if r["context"] == c and r["layout"] == "separate_four_queries"
            )["timing"][engine]["mean_seed_process_median_ms"]
            for c in contexts
        ]
        bars = latency.bar(
            [i + offset for i in range(3)], values, width=0.23, label=label, color=color
        )
        for bar, value in zip(bars, values, strict=True):
            latency.annotate(
                f"{value:.2f}",
                (bar.get_x() + bar.get_width() / 2, value),
                ha="center",
                xytext=(0, 5),
                textcoords="offset points",
                fontsize=9,
            )
    latency.set_xticks(range(3), ["256", "512", "1,024"])
    latency.set_yscale("log")
    latency.set(
        title="Eight separate windows, four queries each",
        xlabel="Context tokens",
        ylabel="Complete query batch (ms, log scale)",
    )
    latency.legend(frameon=False, fontsize=10, loc="upper left")
    latency.set_ylim(
        top=max(r["timing"]["reference"]["mean_seed_process_median_ms"] for r in report["rows"])
        * 3.5
    )
    for layout, label, color in [
        ("separate_four_queries", "Separate calls / four queries", "#e8a071"),
        ("stacked_four_queries", "One stacked batch / four queries", "#76bac7"),
        ("separate_last_query", "Separate calls / final query", "#b8c97d"),
    ]:
        rows = [
            next(r for r in report["rows"] if r["context"] == c and r["layout"] == layout)
            for c in contexts
        ]
        values = [r["reference_over_batched_speed_ratio"] for r in rows]
        gain.plot(range(3), values, color=color, marker="o", linewidth=2, label=label)
        gain.vlines(
            range(3),
            [min(r["process_speed_ratios"]) for r in rows],
            [max(r["process_speed_ratios"]) for r in rows],
            color=color,
            alpha=0.6,
            linewidth=2,
        )
    gain.axhline(1, color="#aab7b1", linestyle="--", linewidth=1)
    gain.set_xticks(range(3), ["256", "512", "1,024"])
    gain.set(
        title="Gain over the original reference",
        xlabel="Context tokens",
        ylabel="Reference time / prototype time",
    )
    gain.legend(frameon=False, fontsize=9)
    for axis in (latency, gain):
        axis.grid(axis="y", alpha=0.12)
        axis.set_title(axis.get_title(), pad=16)
    fig.text(
        0.075,
        0.17,
        "Selected IDs agree across 96,768 real query/head cases. Outputs pass the unchanged float64 tolerance.",
        fontsize=11,
        color="#c1cec5",
    )
    fig.text(
        0.075,
        0.125,
        "Times average nine seed/process medians. Right-panel ranges show three process ratios; they are not confidence intervals.",
        fontsize=10,
        color="#b3c1b8",
    )
    fig.text(
        0.075,
        0.08,
        "Query times exclude construction. The prototype retains an extra summary copy; build costs, padding and memory are in the report.",
        fontsize=10,
        color="#d9b696",
    )
    fig.text(
        0.075,
        0.043,
        "Existing development traces from one GPT-2 layer. No new model-quality, GPU or growing-cache decode claim.",
        fontsize=10,
        color="#d9b696",
    )
    fig.savefig(RUN / "execution-summary.png", dpi=160)
    fig.savefig(RUN / "execution-summary.svg")
    svg = RUN / "execution-summary.svg"
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
    plt.close(fig)
    (RUN / "plot-metadata.json").write_text(
        json.dumps(
            {
                "matplotlib_version": matplotlib.__version__,
                "aggregate_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "scope": "Measured aggregate; process-ratio ranges are not confidence intervals.",
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
