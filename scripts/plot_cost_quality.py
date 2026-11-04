"""Render measured work/quality frontiers and validation-selected CPU latency."""

import hashlib
import json
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "experiments/gpt2-cost-quality-v1"


def main():
    path = RUN / "report.json"
    report = json.loads(path.read_text())
    config = report["config"]
    colors = {4: "#a8b6b1", 16: "#75bac5", 32: "#e9a172"}
    markers = {0.73: "^", 0.9: "s", 0.95: "o"}
    plt.rcParams.update(
        {
            "figure.facecolor": "#171b1b",
            "axes.facecolor": "#171b1b",
            "savefig.facecolor": "#171b1b",
            "text.color": "#e4e9df",
            "axes.labelcolor": "#c0cbc5",
            "xtick.color": "#b0bdb7",
            "ytick.color": "#b0bdb7",
            "axes.edgecolor": "#65736c",
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "svg.fonttype": "none",
        }
    )
    fig = plt.figure(figsize=(16, 10))
    grid = fig.add_gridspec(
        2, 3, left=0.065, right=0.97, top=0.80, bottom=0.16, hspace=0.55, wspace=0.25
    )
    fig.text(
        0.065,
        0.94,
        "Fewer vector operations; does the implementation get faster?",
        fontsize=22,
        weight="bold",
    )
    fig.text(
        0.065,
        0.895,
        "Frozen GPT-2 layer 5  /  CPU float64  /  three seeds  /  four fresh held-out books",
        fontsize=12,
        color="#b2c1b9",
    )
    for column, context in enumerate(config["contexts"]):
        axis = fig.add_subplot(grid[0, column])
        for item in config["geometries"]:
            for p in config["routing_thresholds"]:
                rows = [
                    r
                    for r in report["test_grid"]
                    if r["context"] == context
                    and r["geometry"] == item["id"]
                    and r["p"] == p
                    and r["variant"] == "trained"
                ]
                x = statistics.fmean(
                    r["metrics"]["qk_plus_av_vector_work_ratio"]["mean"] for r in rows
                )
                y = 100 * statistics.fmean(r["metrics"]["relative_l2_error"]["mean"] for r in rows)
                axis.scatter(
                    x,
                    y,
                    s=25 + item["reference_count"] * 9,
                    color=colors[item["chunk_size"]],
                    marker=markers[p],
                    edgecolors="#171b1b",
                    linewidths=0.6,
                    alpha=0.85,
                )
        chosen = next((r for r in report["selections"] if r and r["context"] == context), None)
        if chosen:
            rows = [
                r
                for r in report["test_grid"]
                if r["context"] == context
                and r["geometry"] == chosen["geometry"]
                and r["p"] == chosen["p"]
                and r["variant"] == "trained"
            ]
            axis.scatter(
                statistics.fmean(
                    r["metrics"]["qk_plus_av_vector_work_ratio"]["mean"] for r in rows
                ),
                100 * statistics.fmean(r["metrics"]["relative_l2_error"]["mean"] for r in rows),
                s=260,
                marker="*",
                color="#e4d99a",
                edgecolors="#171b1b",
                linewidths=1,
                zorder=5,
            )
        axis.axvline(1, color="#9baba1", linestyle=":", linewidth=1)
        axis.axhline(
            100 * config["selection"]["max_mean_relative_l2"],
            color="#d4c48f",
            linestyle="--",
            alpha=0.7,
            linewidth=1,
        )
        axis.set(
            title=f"{context:,}-token windows",
            xlabel="QK + AV vector-work ratio / dense",
            ylabel="Mean relative output error (%)",
        )
        axis.grid(alpha=0.12, axis="y")
    latency = fig.add_subplot(grid[1, :])
    chosen_rows = [r for r in report["selections"] if r]
    if chosen_rows:
        labels = []
        series = {
            "Query only": [],
            "Query + build / 128 static uses": [],
            "Query + one full build": [],
        }
        for chosen in chosen_rows:
            rows = [
                r
                for r in report["benchmarks"]
                if r["context"] == chosen["context"]
                and r["geometry"] == chosen["geometry"]
                and r["p"] == chosen["p"]
            ]
            dense = statistics.fmean(r["timing"]["sdpa_dense"]["median"] for r in rows)
            query = statistics.fmean(r["timing"]["hierarchical"]["median"] for r in rows)
            build = statistics.fmean(r["tree_build_ms_per_window_batch"]["median"] for r in rows)
            series["Query only"].append(query / dense)
            series["Query + build / 128 static uses"].append((query + build / 128) / dense)
            series["Query + one full build"].append((query + build) / dense)
            labels.append(f"{chosen['context']:,} tokens · {chosen['geometry']} · p={chosen['p']}")
        for offset, (label, values), color in zip(
            [-0.25, 0, 0.25], series.items(), ["#75bac5", "#e9a172", "#a8b6b1"], strict=True
        ):
            bars = latency.bar(
                [i + offset for i in range(len(labels))],
                values,
                width=0.23,
                label=label,
                color=color,
            )
            for bar, value in zip(bars, values, strict=True):
                latency.annotate(
                    f"{value:.1f}×",
                    (bar.get_x() + bar.get_width() / 2, value),
                    xytext=(0, 4),
                    textcoords="offset points",
                    ha="center",
                    fontsize=9,
                )
        latency.set_xticks(range(len(labels)), labels)
        latency.set_yscale("log")
        latency.axhline(1, color="#ded4a0", linestyle="--", linewidth=1)
        latency.set_ylim(top=max(max(v) for v in series.values()) * 2.2)
        latency.legend(
            frameon=False, loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=3, fontsize=9
        )
    else:
        latency.text(
            0.5,
            0.5,
            "No configuration qualified on validation; no selected timing headline.",
            ha="center",
        )
    latency.set(
        title="Validation-selected settings on test: actual latency relative to PyTorch SDPA",
        ylabel="Latency / dense SDPA (log scale)",
    )
    latency.set_title(latency.get_title(), pad=40)
    latency.grid(axis="y", alpha=0.12)
    fig.legend(
        handles=[
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor=color,
                label=f"Chunk {chunk}",
                markersize=7,
            )
            for chunk, color in colors.items()
        ]
        + [
            Line2D(
                [0],
                [0],
                marker="*",
                color="none",
                markerfacecolor="#e4d99a",
                markersize=12,
                label="Chosen on validation",
            )
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, 0.855),
        ncol=4,
        frameon=False,
    )
    fig.text(
        0.065,
        0.092,
        "Top: means across three seeds; marker size encodes reference count. Dashed line: 5% mean-error budget; p95 is checked separately.",
        fontsize=10,
        color="#b5c2ba",
    )
    fig.text(
        0.065,
        0.06,
        "Bottom: ratios of mean seed-median times for eight windows. Values above 1 are slower. Static reuse is not growing-cache decode.",
        fontsize=10,
        color="#b5c2ba",
    )
    fig.text(
        0.065,
        0.028,
        "Vector work excludes sorting, softmax, traffic and Python overhead. One-layer diagnostics; no whole-model or GPU-speed claim.",
        fontsize=10,
        color="#d9b996",
    )
    fig.savefig(RUN / "cost-quality.png", dpi=160)
    fig.savefig(RUN / "cost-quality.svg")
    svg = RUN / "cost-quality.svg"
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
    plt.close(fig)
    (RUN / "plot-metadata.json").write_text(
        json.dumps(
            {
                "matplotlib_version": matplotlib.__version__,
                "report_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "aggregation": "Top: mean seed-level query means. Bottom: ratio of mean seed-median times. No confidence intervals; highlighted settings fixed using validation only.",
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
