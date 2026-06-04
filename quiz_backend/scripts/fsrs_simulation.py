"""
FSRS verification and configuration analysis.
Uses the fsrs API used by this project's backend.

What this script verifies:
- Target adherence for desired_retention values (0.70, 0.80, 0.90)
- Stability under repeated failures
- Stability after long inactivity gaps

What this script does not verify:
- External validity against real human memory outcomes
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import random
from statistics import mean

from fsrs import Card, Rating, Scheduler

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional plotting dependency
    np = None

try:
    import matplotlib.pyplot as plt
except ImportError:  # pragma: no cover - optional plotting dependency
    plt = None

SEED = 42
BASE_TIME = datetime(2024, 1, 1, tzinfo=timezone.utc)


@dataclass
class SimulationResults:
    recalls: list[int]
    intervals: list[float]
    stability: list[float]
    review_numbers: list[int]
    predicted_r: list[float]


def get_scheduled_days(card: Card) -> float:
    """Compute scheduled interval in days from card timestamps."""
    if card.last_review is None:
        return 0.0
    return (card.due - card.last_review).total_seconds() / 86400.0


def simulate_recall(true_r: float, rng: random.Random) -> bool:
    return rng.random() < true_r


def outcome_to_rating(recalled: bool, true_r: float) -> Rating:
    if not recalled:
        return Rating.Again
    if true_r > 0.85:
        return Rating.Easy
    if true_r > 0.70:
        return Rating.Good
    return Rating.Hard


def run_simulation(
    scheduler: Scheduler,
    n_learners: int = 50,
    n_reviews: int = 8,
    seed: int = SEED,
) -> SimulationResults:
    rng = random.Random(seed)

    all_recalls: list[int] = []
    all_intervals: list[float] = []
    all_stability: list[float] = []
    all_review_numbers: list[int] = []
    all_predicted_r: list[float] = []

    for _learner_idx in range(n_learners):
        card = Card()
        current_time = BASE_TIME

        for review_num in range(1, n_reviews + 1):
            predicted_r = scheduler.get_card_retrievability(card, current_time)

            if card.last_review is None:
                # First review for a new card: seed schedule state, exclude from adherence stats.
                true_r = 1.0
                recalled = True
                rating = Rating.Good
            else:
                true_r = predicted_r
                recalled = simulate_recall(true_r, rng)
                rating = outcome_to_rating(recalled, true_r)
                all_recalls.append(1 if recalled else 0)
                all_predicted_r.append(predicted_r)

            all_review_numbers.append(review_num)

            card, _ = scheduler.review_card(card, rating, current_time)

            interval = get_scheduled_days(card)
            all_intervals.append(interval)
            all_stability.append(card.stability if card.stability else 0.0)

            # Advance close to the scheduled due date; cap suppresses extreme outlier horizons.
            days_to_advance = max(1, min(int(interval), 365))
            current_time += timedelta(days=days_to_advance)

    return SimulationResults(
        recalls=all_recalls,
        intervals=all_intervals,
        stability=all_stability,
        review_numbers=all_review_numbers,
        predicted_r=all_predicted_r,
    )


def run_repeated_failures() -> tuple[list[float], list[float], list[float]]:
    print("=== EDGE CASE: REPEATED FAILURES ===")
    card = Card()
    current_time = BASE_TIME
    scheduler = Scheduler(
        desired_retention=0.90,
        enable_fuzzing=False,
        learning_steps=(),
        relearning_steps=(),
    )

    failure_intervals: list[float] = []
    failure_stability: list[float] = []
    failure_difficulty: list[float] = []

    for i in range(5):
        card, _ = scheduler.review_card(card, Rating.Again, current_time)

        interval = get_scheduled_days(card)
        stability = card.stability if card.stability else 0.0
        difficulty = card.difficulty if card.difficulty else 0.0

        failure_intervals.append(interval)
        failure_stability.append(stability)
        failure_difficulty.append(difficulty)

        print(
            f"  Failure {i + 1}: interval={interval:.4f}d  "
            f"stability={stability:.4f}  difficulty={difficulty:.4f}"
        )

        assert interval >= 0, f"FAIL: Negative interval at failure {i + 1}"
        assert stability > 0, f"FAIL: Zero stability at failure {i + 1}"
        assert 1 <= difficulty <= 10, (
            f"FAIL: Difficulty {difficulty} out of bounds at failure {i + 1}"
        )

        current_time += timedelta(days=max(1, int(interval)))

    print("\n  All assertions passed - system stable after 5 failures\n")
    return failure_intervals, failure_stability, failure_difficulty


def run_long_gap() -> None:
    print("=== EDGE CASE: LONG INACTIVITY GAP (90 days) ===")
    card = Card()
    current_time = BASE_TIME
    scheduler = Scheduler(
        desired_retention=0.90,
        enable_fuzzing=False,
        learning_steps=(),
        relearning_steps=(),
    )

    for i in range(3):
        card, _ = scheduler.review_card(card, Rating.Good, current_time)
        interval = get_scheduled_days(card)
        print(
            f"  Review {i + 1} (Good): interval={interval:.1f}d  "
            f"stability={card.stability:.3f}"
        )
        current_time += timedelta(days=max(1, int(interval)))

    gap_days = 90
    current_time += timedelta(days=gap_days)
    r_after_gap = scheduler.get_card_retrievability(card, current_time)

    print(f"\n  After {gap_days} day gap:")
    print(
        f"  Predicted R: {r_after_gap:.4f}  "
        f"({'severely degraded' if r_after_gap < 0.3 else 'partially retained'})"
    )

    card, _ = scheduler.review_card(card, Rating.Again, current_time)
    interval_after_gap = get_scheduled_days(card)
    print(f"  Post-gap interval: {interval_after_gap:.4f}d")
    print("  System stable:     yes\n")

    assert interval_after_gap >= 0, "FAIL: Negative interval after gap"


def print_target_adherence(
    results_090: SimulationResults,
    results_080: SimulationResults,
    results_070: SimulationResults,
) -> None:
    print("=== TARGET ADHERENCE ===")
    rows = [
        ("0.90 (chosen)", results_090, 0.90),
        ("0.80", results_080, 0.80),
        ("0.70", results_070, 0.70),
    ]

    for label, results, target in rows:
        if not results.recalls:
            print(f"desired_retention={label}: no recall data")
            continue

        recall_rate = mean(results.recalls)
        mean_interval = mean(results.intervals)
        diff = abs(target - recall_rate)
        print(f"desired_retention={label}:")
        print(
            f"  Actual recall rate: {recall_rate:.3f}  "
            f"(target={target}, diff={diff:.3f})"
        )
        print(f"  Mean interval:      {mean_interval:.1f} days")
        print(f"  Target adherence:   {'PASS' if diff < 0.05 else 'FAIL'}\n")


def _to_numpy(values: list[float] | list[int]):
    if np is None:
        raise RuntimeError(
            "numpy is required for plotting. Install with: pip install numpy matplotlib"
        )
    return np.array(values)


def generate_plots(
    results_090: SimulationResults,
    results_080: SimulationResults,
    results_070: SimulationResults,
    failure_intervals: list[float],
    output_path: str = "fsrs_simulation.png",
) -> None:
    if plt is None or np is None:
        print("Skipping plots (numpy/matplotlib not installed).")
        print("Install plotting deps with: pip install numpy matplotlib")
        return

    r090_reviews = _to_numpy(results_090.review_numbers)
    r090_intervals = _to_numpy(results_090.intervals)
    r090_stability = _to_numpy(results_090.stability)

    fig, axes = plt.subplots(2, 2, figsize=(13, 10))

    review_nums = sorted(set(results_090.review_numbers))
    mean_ivl_by_review = [float(np.mean(r090_intervals[r090_reviews == r])) for r in review_nums]
    p25_ivl = [float(np.percentile(r090_intervals[r090_reviews == r], 25)) for r in review_nums]
    p75_ivl = [float(np.percentile(r090_intervals[r090_reviews == r], 75)) for r in review_nums]

    axes[0, 0].plot(
        review_nums,
        mean_ivl_by_review,
        marker="o",
        color="#2ecc71",
        linewidth=2,
        markersize=7,
        label="Mean interval",
    )
    axes[0, 0].fill_between(
        review_nums,
        p25_ivl,
        p75_ivl,
        alpha=0.2,
        color="#2ecc71",
        label="IQR",
    )
    axes[0, 0].set_title(
        "Interval Growth Over Reviews\n(desired_retention=0.90)",
        fontweight="bold",
    )
    axes[0, 0].set_xlabel("Review Number")
    axes[0, 0].set_ylabel("Scheduled Days")
    axes[0, 0].legend()
    axes[0, 0].grid(True, alpha=0.3)

    labels = ["0.70", "0.80", "0.90\n(chosen)"]
    actuals = [
        mean(results_070.recalls),
        mean(results_080.recalls),
        mean(results_090.recalls),
    ]
    mean_ivls = [
        mean(results_070.intervals),
        mean(results_080.intervals),
        mean(results_090.intervals),
    ]
    colors = ["#e74c3c", "#e67e22", "#2ecc71"]

    x = np.arange(len(labels))
    width = 0.35
    ax2 = axes[0, 1]
    ax2b = ax2.twinx()

    bars1 = ax2.bar(
        x - width / 2,
        actuals,
        width,
        color=colors,
        edgecolor="black",
        linewidth=0.8,
        label="Actual Recall Rate",
    )
    ax2b.bar(
        x + width / 2,
        mean_ivls,
        width,
        color=colors,
        edgecolor="black",
        linewidth=0.8,
        alpha=0.5,
        label="Mean Interval (days)",
    )

    ax2.set_title("Retention Target Comparison", fontweight="bold")
    ax2.set_xlabel("Desired Retention")
    ax2.set_ylabel("Actual Recall Rate")
    ax2b.set_ylabel("Mean Interval (days)")
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels)
    ax2.set_ylim(0.5, 1.05)

    for bar, val in zip(bars1, actuals):
        ax2.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.01,
            f"{val:.3f}",
            ha="center",
            fontsize=8,
        )

    axes[1, 0].bar(
        range(1, 6),
        failure_intervals,
        color="#e74c3c",
        edgecolor="black",
        linewidth=0.8,
        alpha=0.8,
    )
    axes[1, 0].set_title(
        "Edge Case: Intervals After\nRepeated Failures (Again x 5)",
        fontweight="bold",
    )
    axes[1, 0].set_xlabel("Consecutive Failure Number")
    axes[1, 0].set_ylabel("Scheduled Days")
    axes[1, 0].set_xticks(range(1, 6))
    for i, val in enumerate(failure_intervals):
        axes[1, 0].text(i + 1, val + 0.001, f"{val:.3f}d", ha="center", va="bottom", fontsize=9)

    mean_stab_by_review = [float(np.mean(r090_stability[r090_reviews == r])) for r in review_nums]
    axes[1, 1].plot(
        review_nums,
        mean_stab_by_review,
        marker="s",
        color="#9b59b6",
        linewidth=2,
        markersize=7,
    )
    axes[1, 1].set_title(
        "Mean Stability Growth Over Reviews\n(desired_retention=0.90)",
        fontweight="bold",
    )
    axes[1, 1].set_xlabel("Review Number")
    axes[1, 1].set_ylabel("Stability (S)")
    axes[1, 1].grid(True, alpha=0.3)

    plt.suptitle("FSRS Verification and Configuration Analysis", fontsize=13, fontweight="bold")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.show()
    print(f"Saved: {output_path}")


def main() -> None:
    # Explicitly disable learning/relearning so this sim evaluates review-state behavior.
    common_kwargs = {
        "enable_fuzzing": False,
        "learning_steps": (),
        "relearning_steps": (),
    }

    scheduler_090 = Scheduler(desired_retention=0.90, **common_kwargs)
    scheduler_080 = Scheduler(desired_retention=0.80, **common_kwargs)
    scheduler_070 = Scheduler(desired_retention=0.70, **common_kwargs)

    print(f"Learning steps:   {getattr(scheduler_090, 'learning_steps', None)}")
    print(f"Relearning steps: {getattr(scheduler_090, 'relearning_steps', None)}")
    print(f"Fuzzing:          {getattr(scheduler_090, 'enable_fuzzing', None)}")
    print()

    print("Running simulations...")
    results_090 = run_simulation(scheduler_090)
    results_080 = run_simulation(scheduler_080)
    results_070 = run_simulation(scheduler_070)
    print("Done.\n")

    print_target_adherence(results_090, results_080, results_070)

    failure_intervals, _, _ = run_repeated_failures()
    run_long_gap()

    generate_plots(
        results_090=results_090,
        results_080=results_080,
        results_070=results_070,
        failure_intervals=failure_intervals,
    )


if __name__ == "__main__":
    main()
