from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import matplotlib.pyplot as plt
except ImportError:  # pragma: no cover
    plt = None

# ── Resolve data files relative to this script (../.. == workspace root) ──────
_SCRIPT_DIR = Path(__file__).resolve().parent
_WORKSPACE_ROOT = _SCRIPT_DIR.parent.parent

REVIEW_LOGS_PATH = _WORKSPACE_ROOT / "review_logs.csv"
QUESTIONS_PATH = _WORKSPACE_ROOT / "questions.csv"
OUTPUT_PATH = Path(os.getcwd()) / "irt_evaluation.png"
POSTERIOR_SD_OUTPUT_PATH = Path(os.getcwd()) / "posterior_sd_reduction.png"

_COLORS = ["#e74c3c", "#3498db", "#2ecc71", "#9b59b6", "#e67e22"]


# ── Data loading ───────────────────────────────────────────────────────────────

def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_csv(REVIEW_LOGS_PATH)
    df["created_at"] = pd.to_datetime(df["created_at"])
    df = df.sort_values(["user_id", "topic_id", "created_at"])

    df["response_index"] = (
        df.groupby(["user_id", "topic_id"]).cumcount() + 1
    )

    users = sorted(df["user_id"].unique())
    id_map = {u: f"P{i + 1}" for i, u in enumerate(users)}
    if len(users) >= 5:
        id_map[users[3]], id_map[users[4]] = id_map[users[4]], id_map[users[3]]
    df["participant"] = df["user_id"].map(id_map)

    topics = sorted(df["topic_id"].unique())
    t_map = {t: f"Topic {i + 1}" for i, t in enumerate(topics)}
    df["topic_label"] = df["topic_id"].map(t_map)

    questions = pd.read_csv(QUESTIONS_PATH)
    df = df.merge(
        questions[["id", "type", "irt_a", "irt_b"]],
        left_on="question_id",
        right_on="id",
        how="left",
    )

    return df, questions


# ── Analysis helpers ───────────────────────────────────────────────────────────

def _compute_p(row: pd.Series) -> float:
    theta, a, b = row["theta_before"], row["irt_a"], row["irt_b"]
    if pd.isna(a) or pd.isna(b) or pd.isna(theta):
        return np.nan
    if row["type"] == "MCQ":
        c = 0.25
        return c + (1 - c) / (1 + np.exp(-a * (theta - b)))
    return 1 / (1 + np.exp(-a * (theta - b)))


def analyse_calibration(df: pd.DataFrame) -> pd.DataFrame:
    print("=== CALIBRATION TRANSITION ===")
    rows: list[dict] = []

    for (pid, tid), group in df.groupby(["participant", "topic_label"]):
        below = group[group["posterior_sd"] < 0.5]
        if len(below) > 0:
            cal_at = int(below["response_index"].min())
            rows.append(
                {
                    "participant": pid,
                    "topic": tid,
                    "calibrated_at": cal_at,
                    "final_sd": group["posterior_sd"].iloc[-1],
                    "total_responses": len(group),
                }
            )
            print(
                f"  {pid} {tid}: calibrated at response {cal_at} "
                f"(final SD={group['posterior_sd'].iloc[-1]:.3f})"
            )
        else:
            print(
                f"  {pid} {tid}: NOT calibrated "
                f"(min SD={group['posterior_sd'].min():.3f})"
            )

    cal_df = pd.DataFrame(rows)
    if len(cal_df) > 0:
        n_sessions = len(df.groupby(["participant", "topic_label"]))
        print(
            f"\n  Mean calibration point: "
            f"{cal_df['calibrated_at'].mean():.1f} responses"
        )
        print(
            f"  Range: {cal_df['calibrated_at'].min()} – "
            f"{cal_df['calibrated_at'].max()} responses"
        )
        print(f"  All sessions calibrated: {len(cal_df) == n_sessions}")

    return cal_df


def analyse_p_targeting(df: pd.DataFrame) -> pd.DataFrame:
    print("\n=== P-VALUE TARGETING ===")

    learning = df[df["response_index"] > 10].copy()
    learning["p_at_selection"] = learning.apply(_compute_p, axis=1)
    learning = learning.dropna(subset=["p_at_selection"])
    learning["deviation"] = abs(learning["p_at_selection"] - 0.70)

    print(f"  Learning mode questions:  {len(learning)}")
    print(f"  Mean P at selection:      {learning['p_at_selection'].mean():.3f}")
    print(f"  Mean deviation from 0.70: {learning['deviation'].mean():.3f}")
    print(
        f"  Within ±0.10 of target:   "
        f"{(learning['deviation'] < 0.10).mean() * 100:.1f}%"
    )
    print(
        f"  Within ±0.05 of target:   "
        f"{(learning['deviation'] < 0.05).mean() * 100:.1f}%"
    )

    return learning


def analyse_theta_summary(df: pd.DataFrame) -> None:
    print("\n=== THETA SUMMARY PER PARTICIPANT ===")
    for pid, pdata in df.groupby("participant"):
        first_theta = pdata.iloc[0]["theta_before"]
        last_theta = pdata.iloc[-1]["theta_after"]
        min_sd = pdata["posterior_sd"].min()
        print(
            f"  {pid}: theta {first_theta:.3f} → {last_theta:.3f}  "
            f"(min SD={min_sd:.3f})"
        )


# ── Plotting ───────────────────────────────────────────────────────────────────

def plot_results(
    df: pd.DataFrame,
    cal_df: pd.DataFrame,
    learning: pd.DataFrame,
) -> None:
    if plt is None:
        print("\nmatplotlib not available – skipping figure generation.")
        return

    fig, axes = plt.subplots(3, 2, figsize=(15, 15))

    # Figure 1: Theta convergence
    ax1 = axes[0, 0]
    for i, (pid, pdata) in enumerate(df.groupby("participant")):
        for tid, tdata in pdata.groupby("topic_label"):
            label = pid if tid == tdata["topic_label"].iloc[0] else ""
            ax1.plot(
                tdata["response_index"],
                tdata["theta_after"],
                color=_COLORS[i % len(_COLORS)],
                alpha=0.8,
                linewidth=1.5,
                label=label,
            )
    ax1.axvline(x=10, color="red", linestyle="--", linewidth=2, label="n=10 threshold")
    ax1.set_title("θ̂ Convergence Over Response Sequence", fontweight="bold")
    ax1.set_xlabel("Response Index")
    ax1.set_ylabel("θ̂ (EAP Estimate)")
    ax1.grid(True, alpha=0.3)
    handles, labels = ax1.get_legend_handles_labels()
    unique = dict(zip(labels, handles))
    ax1.legend(unique.values(), unique.keys(), fontsize=8)

    # Figure 2: Posterior SD reduction
    ax2 = axes[0, 1]
    for i, (pid, pdata) in enumerate(df.groupby("participant")):
        for tid, tdata in pdata.groupby("topic_label"):
            label = pid if tid == tdata["topic_label"].iloc[0] else ""
            ax2.plot(
                tdata["response_index"],
                tdata["posterior_sd"],
                color=_COLORS[i % len(_COLORS)],
                alpha=0.8,
                linewidth=1.5,
                label=label,
            )
    ax2.axhline(y=0.5, color="red", linestyle="--", linewidth=2, label="SD=0.5 threshold")
    ax2.set_title("Posterior SD Reduction Over Response Sequence", fontweight="bold")
    ax2.set_xlabel("Response Index")
    ax2.set_ylabel("Posterior SD")
    ax2.grid(True, alpha=0.3)
    handles, labels = ax2.get_legend_handles_labels()
    unique = dict(zip(labels, handles))
    ax2.legend(unique.values(), unique.keys(), fontsize=8)

    # Figure 3: P-value targeting histogram
    ax3 = axes[1, 0]
    ax3.hist(learning["p_at_selection"], bins=15, color="#3498db", edgecolor="black", alpha=0.8)
    ax3.axvline(x=0.70, color="red", linewidth=2, linestyle="--", label="Target P=0.70")
    ax3.axvspan(0.60, 0.80, alpha=0.1, color="red", label="±0.10 tolerance band")
    ax3.set_title(
        "Distribution of P(θ̂) at Question Selection\n(Learning Mode)",
        fontweight="bold",
    )
    ax3.set_xlabel("P(θ̂)")
    ax3.set_ylabel("Frequency")
    ax3.legend()

    # Figure 4: Calibration point per participant
    ax4 = axes[1, 1]
    if len(cal_df) > 0:
        bar_labels = [
            f"{r['participant']}\n{r['topic']}" for _, r in cal_df.iterrows()
        ]
        bar_values = cal_df["calibrated_at"].values
        bar_colors = [_COLORS[i % len(_COLORS)] for i in range(len(cal_df))]

        bars = ax4.bar(
            range(len(bar_labels)),
            bar_values,
            color=bar_colors,
            edgecolor="black",
            linewidth=0.8,
        )
        ax4.axhline(y=10, color="red", linestyle="--", linewidth=2, label="Minimum n=10")
        ax4.set_title("Response Index at Calibration Transition", fontweight="bold")
        ax4.set_xlabel("Participant / Topic")
        ax4.set_ylabel("Response Index")
        ax4.set_xticks(range(len(bar_labels)))
        ax4.set_xticklabels(bar_labels, fontsize=8)
        ax4.legend()
        for bar, val in zip(bars, bar_values):
            ax4.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.2,
                str(int(val)),
                ha="center",
                fontsize=9,
            )

    # Figure 5: P(theta) trend over time for each participant/topic
    ax5 = axes[2, 0]
    p_series = df.copy()
    p_series["p_at_selection"] = p_series.apply(_compute_p, axis=1)
    p_series = p_series.dropna(subset=["p_at_selection"])

    participant_order = sorted(p_series["participant"].unique())
    topic_order = sorted(p_series["topic_label"].unique())
    participant_colors = {
        pid: _COLORS[i % len(_COLORS)] for i, pid in enumerate(participant_order)
    }
    topic_styles = ["-", "--", ":", "-."]
    topic_linestyles = {
        tid: topic_styles[i % len(topic_styles)] for i, tid in enumerate(topic_order)
    }

    for (pid, tid), tdata in p_series.groupby(["participant", "topic_label"]):
        ax5.plot(
            tdata["response_index"],
            tdata["p_at_selection"],
            color=participant_colors[pid],
            linestyle=topic_linestyles[tid],
            alpha=0.85,
            linewidth=1.3,
            label=f"{pid} {tid}",
        )

    ax5.axhline(y=0.70, color="red", linestyle="--", linewidth=2, label="Target P=0.70")
    ax5.axvline(x=10, color="black", linestyle=":", linewidth=1.8, label="n=10 threshold")
    ax5.set_ylim(0.0, 1.0)
    ax5.set_title("P(θ̂) at Selection Over Time by Participant/Topic", fontweight="bold")
    ax5.set_xlabel("Response Index")
    ax5.set_ylabel("P(θ̂)")
    ax5.grid(True, alpha=0.3)
    ax5.legend(fontsize=7, ncol=2)

    # Keep the 3x2 grid balanced while using five panels.
    ax6 = axes[2, 1]
    ax6.axis("off")

    plt.suptitle("IRT/EAP Adaptive Engine Evaluation", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(OUTPUT_PATH, dpi=150, bbox_inches="tight")
    plt.show()
    print(f"\nSaved: {OUTPUT_PATH}")

    posterior_fig, posterior_ax = plt.subplots(figsize=(9, 6))
    for i, (pid, pdata) in enumerate(df.groupby("participant")):
        for tid, tdata in pdata.groupby("topic_label"):
            label = pid if tid == tdata["topic_label"].iloc[0] else ""
            posterior_ax.plot(
                tdata["response_index"],
                tdata["posterior_sd"],
                color=_COLORS[i % len(_COLORS)],
                alpha=0.8,
                linewidth=1.5,
                label=label,
            )
    posterior_ax.axhline(
        y=0.5,
        color="red",
        linestyle="--",
        linewidth=2,
        label="SD=0.5 threshold",
    )
    posterior_ax.set_title("Posterior SD Reduction Over Response Sequence", fontweight="bold")
    posterior_ax.set_xlabel("Response Index")
    posterior_ax.set_ylabel("Posterior SD")
    posterior_ax.grid(True, alpha=0.3)
    handles, labels = posterior_ax.get_legend_handles_labels()
    unique = dict(zip(labels, handles))
    posterior_ax.legend(unique.values(), unique.keys(), fontsize=8)
    posterior_fig.tight_layout()
    posterior_fig.savefig(POSTERIOR_SD_OUTPUT_PATH, dpi=150, bbox_inches="tight")
    plt.close(posterior_fig)
    print(f"Saved: {POSTERIOR_SD_OUTPUT_PATH}")



def main() -> None:
    df, _questions = load_data()
    cal_df = analyse_calibration(df)
    learning = analyse_p_targeting(df)
    analyse_theta_summary(df)
    plot_results(df, cal_df, learning)


if __name__ == "__main__":
    main()
