"""Plot the measured pilot. Optional tool: matplotlib==3.10.1, outside core deps."""

import hashlib
import json
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "experiments/gpt2-layer5-pilot-v1"


def main() -> None:
    report_path = RUN / "report.json"
    report = json.loads(report_path.read_text())
    plt.rcParams.update(
        {
            "figure.facecolor": "#171b1b",
            "axes.facecolor": "#171b1b",
            "savefig.facecolor": "#171b1b",
            "text.color": "#e5e8df",
            "axes.labelcolor": "#c8cfca",
            "xtick.color": "#b1bcb7",
            "ytick.color": "#b1bcb7",
            "axes.edgecolor": "#59625f",
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "svg.fonttype": "none",
        }
    )
    fig, (training, cost) = plt.subplots(1, 2, figsize=(14, 7.875))
    fig.subplots_adjust(left=0.075, right=0.96, bottom=0.24, top=0.73, wspace=0.28)
    fig.text(
        0.075,
        0.925,
        "A frozen GPT-2 layer; only routing references learn",
        fontsize=22,
        weight="bold",
    )
    fig.text(
        0.075,
        0.875,
        "Layer 5  /  6,144 trainable reference parameters  /  backbone parameter hashes unchanged",
        fontsize=11,
        color="#b2beb7",
    )
    for fit, color in zip(report["fitting"], ["#79bac5", "#e4a175", "#b9c87b"], strict=True):
        training.plot(
            [row["step"] for row in fit["history"]],
            [row["validation_kl"] for row in fit["history"]],
            color=color,
            linewidth=2,
            marker="o",
            markersize=3,
            label=f"Seed {fit['seed']}",
        )
    training.set(
        title="Validation loss during fitting",
        xlabel="Optimizer step",
        ylabel="Pooled KL (sum over two levels)",
    )
    training.legend(frameon=False, fontsize=10)
    styles = [
        ("initial_query_samples", "Untrained query samples", "#aab4b0"),
        ("random_gaussian", "Untrained random references", "#76b6c3"),
        ("trained", "Fitted references", "#e5a06c"),
    ]
    for variant, label, color in styles:
        xs, ys = [], []
        for p in report["config"]["routing_thresholds"]:
            rows = [
                row for row in report["test_results"] if row["variant"] == variant and row["p"] == p
            ]
            xs.append(
                100
                * statistics.fmean(row["metrics"]["selected_key_fraction"]["mean"] for row in rows)
            )
            ys.append(
                statistics.fmean(row["metrics"]["attention_l2_error"]["mean"] for row in rows)
            )
        cost.plot(xs, ys, color=color, linewidth=2, marker="o", markersize=5, label=label)
    cost.set(
        title="Held-out error and actual keys read",
        xlabel="Selected keys (% of eligible prefix)",
        ylabel="Mean attention-output L2 error",
    )
    cost.legend(frameon=False, fontsize=10)
    for axis in (training, cost):
        axis.grid(axis="y", color="#74847c", alpha=0.18, linewidth=0.7)
        axis.tick_params(length=3)
        axis.title.set_fontsize(13)
        axis.set_title(axis.get_title(), pad=16)
    fig.text(
        0.075,
        0.145,
        "Held-out: Tom Sawyer + War and Peace. Right-panel points: p = .73, .90, .95; mean across three seeds.",
        fontsize=10,
        color="#b4c0b9",
    )
    fig.text(
        0.075,
        0.107,
        "192 query/head pairs per seed, reused across variants. Same threshold can select different numbers of keys.",
        fontsize=10,
        color="#b4c0b9",
    )
    fig.text(
        0.075,
        0.069,
        "One-layer, 256-token teacher-forced pilot. No generation-quality, runtime-speed or certified-error claim.",
        fontsize=10,
        color="#d4b697",
    )
    fig.savefig(RUN / "pilot-summary.png", dpi=160)
    fig.savefig(RUN / "pilot-summary.svg")
    svg_path = RUN / "pilot-summary.svg"
    svg_path.write_text(
        "\n".join(line.rstrip() for line in svg_path.read_text().splitlines()) + "\n"
    )
    plt.close(fig)
    (RUN / "plot-metadata.json").write_text(
        json.dumps(
            {
                "matplotlib_version": matplotlib.__version__,
                "source_report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
                "right_panel_aggregation": "mean of three seeds at each fixed threshold; no confidence intervals",
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
