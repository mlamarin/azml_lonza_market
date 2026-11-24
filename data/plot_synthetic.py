"""Plot the SYNTHETIC dataset written by data.generate.

Run with: uv run python -m data.plot_synthetic
"""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from data.generate import PHASES


def load(data_dir: Path) -> pd.DataFrame:
    raw = pd.concat(pd.read_csv(p) for p in sorted((data_dir / "raw").glob("batch_*.csv")))
    truth = pd.concat(pd.read_csv(p) for p in sorted((data_dir / "truth").glob("batch_*.csv")))
    return raw.merge(truth, on="record_id", validate="one_to_one")


def plot_p_true_by_phase(df: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 4))
    for phase in PHASES:
        ax.hist(df.loc[df["from_phase"] == phase, "p_true"], bins=20, alpha=0.5, label=f"Phase {phase}")
    ax.set_xlabel("p_true (truth model)")
    ax.set_ylabel("Transitions")
    ax.set_title("Synthetic data: true progression probability by starting phase")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_rate_by_modality(df: pd.DataFrame, path: Path) -> None:
    batches = sorted(df["batch_id"].unique())
    fig, axes = plt.subplots(1, len(batches), figsize=(4 * len(batches), 4), sharey=True)
    for ax, batch_id in zip(axes, batches):
        rates = (
            df[df["batch_id"] == batch_id]
            .groupby(["modality", "from_phase"])["progressed"]
            .mean()
            .unstack("from_phase")
            .reindex(columns=PHASES)
        )
        rates.plot.barh(ax=ax, legend=batch_id == batches[0])
        ax.set_title(batch_id)
        ax.set_xlabel("Observed progression rate")
        ax.set_xlim(0, 1)
    fig.suptitle("Synthetic data: observed progression rate by modality and starting phase")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_observed_vs_true(df: pd.DataFrame, path: Path) -> None:
    groups = df.groupby(["from_phase", "modality", "indication_area"]).agg(
        observed=("progressed", "mean"), expected=("p_true", "mean"), n=("progressed", "size")
    )
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.scatter(groups["expected"], groups["observed"], s=groups["n"], alpha=0.5)
    ax.plot([0, 1], [0, 1], linestyle="--", color="grey")
    ax.set_xlabel("Mean p_true in group")
    ax.set_ylabel("Observed progression rate in group")
    ax.set_title("Synthetic data: observed vs true\n(phase x modality x area, size = n)")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=Path("data/output"))
    args = parser.parse_args()

    df = load(args.data_dir)
    plot_dir = args.data_dir / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    plot_p_true_by_phase(df, plot_dir / "p_true_by_phase.png")
    plot_rate_by_modality(df, plot_dir / "rate_by_modality.png")
    plot_observed_vs_true(df, plot_dir / "observed_vs_true.png")
    print(f"Plots written to {plot_dir}")


if __name__ == "__main__":
    main()
