
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

try:
    import matplotlib.pyplot as plt
except ImportError:  # pragma: no cover
    plt = None


_SCRIPT_DIR = Path(__file__).resolve().parent
_WORKSPACE_ROOT = _SCRIPT_DIR.parent.parent

OUTPUT_MCQ_PATH = Path.cwd() / "answer_bias_mcq.png"
OUTPUT_MULTI_OPTION_PATH = Path.cwd() / "answer_bias_multi_option.png"
OUTPUT_MULTI_SETSIZE_PATH = Path.cwd() / "answer_bias_multi_setsize.png"

_POSITIONS = ["A", "B", "C", "D"]


def parse_answer(answer_val: object) -> list[str]:
    """Parse MULTI_MCQ answers into normalized option letters."""
    if isinstance(answer_val, list):
        return [str(x).strip().upper() for x in answer_val]

    if isinstance(answer_val, str):
        answer_val = answer_val.strip()
        try:
            parsed = json.loads(answer_val)
            if isinstance(parsed, list):
                return [str(x).strip().upper() for x in parsed]
            return [str(parsed).strip().upper()]
        except (json.JSONDecodeError, ValueError):
            pass

        if "," in answer_val:
            return [x.strip().strip('"').upper() for x in answer_val.split(",")]

        return [answer_val.strip().strip('"').upper()]

    return []


def read_questions_csv(path: Path) -> pd.DataFrame:
    """Load CSV with resilient parsing for mixed encodings and bad rows."""
    errors: list[str] = []
    for enc in ["utf-8", "latin-1"]:
        try:
            return pd.read_csv(path, encoding=enc, engine="python", on_bad_lines="skip")
        except Exception as exc:  # pragma: no cover
            errors.append(f"{enc}: {exc}")

    raise RuntimeError(f"Unable to parse {path}: {' | '.join(errors)}")


def run_parse_sanity_test() -> None:
    """Verify answer parsing works correctly."""
    test_cases = [
        '["A","B"]',
        '["A","B","D"]',
        '["B","C"]',
        ["A", "B"],
        "A,B",
    ]

    print("=== PARSE SANITY TEST ===")
    for case in test_cases:
        result = parse_answer(case)
        print(f"  {str(case):20s} -> {result}")


def cramers_v(chi2: float, n: int, k: int) -> float:
    """Calculate Cramer's V effect size for a chi-square test."""
    if n <= 0 or chi2 < 0 or k <= 1:
        return float("nan")
    return float(np.sqrt(chi2 / (n * (k - 1))))


def interpret_cramers_v(v: float) -> str:
    """Interpret Cramer's V effect size."""
    if not np.isfinite(v):
        return "undefined"
    if v < 0.1:
        return "negligible"
    if v < 0.3:
        return "small"
    if v < 0.5:
        return "medium"
    return "large"


def format_p(p_value: float) -> str:
    """Human-readable p-value formatting for reports and figure titles."""
    if not np.isfinite(p_value):
        return "N/A"
    if p_value < 0.0001:
        return "< 0.0001"
    return f"= {p_value:.4f}"


def analyse_mcq_bias(mcq: pd.DataFrame) -> tuple[Counter, float, float, float]:
    """Analyze MCQ answer position bias."""
    print("\n" + "=" * 70)
    print("MCQ ANSWER POSITION BIAS ANALYSIS")
    print("=" * 70)

    mcq = mcq.copy()
    mcq["answer_clean"] = mcq["answer"].astype(str).str.strip().str.strip('"').str.upper()
    mcq_position_counts: Counter = Counter(mcq["answer_clean"])

    total_mcq = len(mcq)
    print(f"\nTotal MCQ questions analyzed: {total_mcq}")
    print("\nCorrect answer position distribution:")
    print(f"{'Position':<12} {'Count':<10} {'Percentage':<12} {'Expected':<12} {'Visualization'}")
    print("-" * 70)

    for pos in _POSITIONS:
        count = mcq_position_counts.get(pos, 0)
        pct = (count / total_mcq * 100) if total_mcq else 0.0
        expected_pct = 25.0
        bar = "#" * int(pct / 2)
        print(f"{pos:<12} {count:<10} {pct:>10.1f}% {expected_pct:>10.1f}% {bar}")

    observed_mcq = [mcq_position_counts.get(p, 0) for p in _POSITIONS]
    expected_mcq = [total_mcq / 4] * 4 if total_mcq else [0, 0, 0, 0]

    if total_mcq and sum(observed_mcq) > 0:
        chi2_mcq, p_mcq = stats.chisquare(observed_mcq, expected_mcq)
        v_mcq = cramers_v(chi2_mcq, total_mcq, len(_POSITIONS))
    else:
        chi2_mcq, p_mcq, v_mcq = float("nan"), float("nan"), float("nan")

    print("\n" + "-" * 70)
    print("Chi-square Goodness-of-Fit Test (H0: uniform distribution)")
    print("-" * 70)
    print(f"  chi2 statistic:      {chi2_mcq:.3f}")
    print(f"  p-value:            {p_mcq:.4f}" if np.isfinite(p_mcq) else "  p-value:            N/A")
    print(f"  Cramer's V:         {v_mcq:.3f} ({interpret_cramers_v(v_mcq)} effect)")
    print(
        "  Significant bias:   "
        + (
            "YES (p < 0.05)"
            if np.isfinite(p_mcq) and p_mcq < 0.05
            else "NO (p >= 0.05)"
            if np.isfinite(p_mcq)
            else "N/A"
        )
    )

    return mcq_position_counts, float(chi2_mcq), float(p_mcq), float(v_mcq)


def analyse_multi_mcq_bias(
    multi_mcq: pd.DataFrame,
) -> tuple[Counter, Counter, int, int, float, float, float]:
    """Analyze MULTI_MCQ option frequency and answer-set-size bias."""
    print("\n" + "=" * 70)
    print("MULTI_MCQ ANSWER BIAS ANALYSIS")
    print("=" * 70)

    if multi_mcq.empty:
        print("\nNo MULTI_MCQ rows found; skipping analysis.")
        return Counter(), Counter(), 0, 0, float("nan"), float("nan"), float("nan")

    multi_mcq = multi_mcq.copy()
    multi_mcq["answer_list"] = multi_mcq["answer"].apply(parse_answer)

    print(f"\nTotal MULTI_MCQ questions analyzed: {len(multi_mcq)}")
    print("\nSample parsed answers (first 3 questions):")
    for idx, (_, row) in enumerate(multi_mcq.head(3).iterrows(), 1):
        print(f"  Q{idx}: Raw={row['answer']} -> Parsed={row['answer_list']}")

    print("\n" + "-" * 70)
    print("Individual Option Correct Frequency")
    print("-" * 70)
    option_correct_counts: Counter = Counter()
    total_multi = len(multi_mcq)

    for _, row in multi_mcq.iterrows():
        for opt in row["answer_list"]:
            if opt in _POSITIONS:
                option_correct_counts[opt] += 1

    total_correct_options = sum(option_correct_counts.values())

    print(f"{'Position':<12} {'Frequency':<15} {'Percentage':<12} {'Visualization'}")
    print("-" * 70)

    for pos in _POSITIONS:
        count = option_correct_counts.get(pos, 0)
        pct = (count / total_multi * 100) if total_multi else 0.0
        bar = "#" * int(pct / 2)
        print(f"{pos:<12} {count:>3}/{total_multi:<8} {pct:>10.1f}% {bar}")

    observed_multi = [option_correct_counts.get(p, 0) for p in _POSITIONS]
    expected_multi = [total_correct_options / 4] * 4 if total_correct_options else [0, 0, 0, 0]

    if total_correct_options:
        chi2_multi, p_multi = stats.chisquare(observed_multi, expected_multi)
        v_multi = cramers_v(chi2_multi, total_correct_options, len(_POSITIONS))
    else:
        chi2_multi, p_multi, v_multi = float("nan"), float("nan"), float("nan")

    print("\n" + "-" * 70)
    print("Chi-square Test (H0: uniform option frequency)")
    print("-" * 70)
    print(f"  chi2 statistic:      {chi2_multi:.3f}")
    print(f"  p-value:            {p_multi:.4f}" if np.isfinite(p_multi) else "  p-value:            N/A")
    print(f"  Cramer's V:         {v_multi:.3f} ({interpret_cramers_v(v_multi)} effect)")
    print(
        "  Significant bias:   "
        + (
            "YES (p < 0.05)"
            if np.isfinite(p_multi) and p_multi < 0.05
            else "NO (p >= 0.05)"
            if np.isfinite(p_multi)
            else "N/A"
        )
    )

    print("\n" + "-" * 70)
    print("Number of Correct Answers per Question")
    print("-" * 70)
    answer_counts: Counter = Counter(len(row["answer_list"]) for _, row in multi_mcq.iterrows())
    for n, count in sorted(answer_counts.items()):
        pct = (count / total_multi * 100) if total_multi else 0.0
        print(f"  {n} correct answer(s): {count:3d} ({pct:.1f}%)")

    if len(answer_counts) == 1 and answer_counts:
        fixed_n = next(iter(answer_counts.keys()))
        print(f"\n  All questions have exactly {fixed_n} correct answers")
        print(f"  This reduces to guessing {fixed_n}/4 options correctly")
    elif answer_counts:
        min_n = min(answer_counts.keys())
        max_n = max(answer_counts.keys())
        print(
            f"\n  Variable number of correct answers "
            f"({min_n}-{max_n})"
        )
        print("  This helps prevent fixed-pattern guessing strategies")

    print("\n" + "-" * 70)
    print("Position Clustering Analysis (Early vs Late)")
    print("-" * 70)
    early_correct = 0
    late_correct = 0
    total_options_checked = 0

    for _, row in multi_mcq.iterrows():
        for opt in row["answer_list"]:
            if opt in ["A", "B"]:
                early_correct += 1
            if opt in ["C", "D"]:
                late_correct += 1
            if opt in _POSITIONS:
                total_options_checked += 1

    if total_options_checked > 0:
        early_pct = early_correct / total_options_checked * 100
        late_pct = late_correct / total_options_checked * 100
        print(f"  Early positions (A, B): {early_correct:3d} ({early_pct:.1f}%)")
        print(f"  Late positions  (C, D): {late_correct:3d} ({late_pct:.1f}%)")

        binom_result = stats.binomtest(
            early_correct,
            total_options_checked,
            p=0.5,
            alternative="two-sided",
        )
        print("\n  Binomial test (H0: 50% early):")
        print(f"    p-value:              {binom_result.pvalue:.4f}")
        print(
            "    Significant clustering: "
            + ("YES (p < 0.05)" if binom_result.pvalue < 0.05 else "NO (p >= 0.05)")
        )

    return (
        option_correct_counts,
        answer_counts,
        total_correct_options,
        total_multi,
        float(chi2_multi),
        float(p_multi),
        float(v_multi),
    )


def plot_results(
    mcq_counts: Counter,
    total_mcq: int,
    chi2_mcq: float,
    p_mcq: float,
    v_mcq: float,
    option_correct_counts: Counter,
    answer_counts: Counter,
    total_multi: int,
    chi2_multi: float,
    p_multi: float,
    v_multi: float,
    has_multi_data: bool,
) -> None:
    """Generate and save visualization figures."""
    if plt is None:
        print("\nmatplotlib not available - skipping figure generation.")
        return

    colors_pos = ["#3498db", "#2ecc71", "#e74c3c", "#9b59b6"]

    # Figure 1: MCQ position distribution
    fig_mcq, ax_mcq = plt.subplots(1, 1, figsize=(8, 6))
    mcq_values = [mcq_counts.get(p, 0) for p in _POSITIONS]
    expected_mcq = total_mcq / 4 if total_mcq else 0

    bars1 = ax_mcq.bar(
        _POSITIONS,
        mcq_values,
        color=colors_pos,
        edgecolor="black",
        linewidth=1.2,
        alpha=0.85,
    )
    if total_mcq:
        ax_mcq.axhline(
            y=expected_mcq,
            color="red",
            linestyle="--",
            linewidth=2.2,
            label=f"Expected (uniform, n={total_mcq})",
        )
    ax_mcq.set_title(
        "MCQ: Correct Answer Position Distribution\n"
        f"chi2={chi2_mcq:.2f}, p {format_p(p_mcq)}, Cramer's V={v_mcq:.3f}",
        fontweight="bold",
        fontsize=12,
    )
    ax_mcq.set_xlabel("Answer Position", fontsize=11, fontweight="bold")
    ax_mcq.set_ylabel("Frequency", fontsize=11, fontweight="bold")
    ax_mcq.set_ylim(0, (max(mcq_values) * 1.15) if mcq_values and max(mcq_values) > 0 else 1)
    if total_mcq:
        ax_mcq.legend(fontsize=10, loc="upper right")

    for bar, val in zip(bars1, mcq_values):
        height = bar.get_height()
        pct = (val / total_mcq * 100) if total_mcq else 0
        ax_mcq.text(
            bar.get_x() + bar.get_width() / 2,
            height + 0.5,
            f"{val}\n({pct:.1f}%)",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
        )
    ax_mcq.grid(True, alpha=0.3, axis="y")
    fig_mcq.tight_layout()
    fig_mcq.savefig(OUTPUT_MCQ_PATH, dpi=150, bbox_inches="tight")
    print(f"\nSaved: {OUTPUT_MCQ_PATH}")

    # Figure 2: MULTI_MCQ option frequency
    fig_multi_opt, ax_multi_freq = plt.subplots(1, 1, figsize=(8, 6))
    if has_multi_data and option_correct_counts:
        multi_values = [option_correct_counts.get(p, 0) for p in _POSITIONS]
        expected_multi = sum(multi_values) / 4 if sum(multi_values) else 0

        bars2 = ax_multi_freq.bar(
            _POSITIONS,
            multi_values,
            color=colors_pos,
            edgecolor="black",
            linewidth=1.2,
            alpha=0.85,
        )

        if sum(multi_values):
            ax_multi_freq.axhline(
                y=expected_multi,
                color="red",
                linestyle="--",
                linewidth=2.2,
                label="Expected (uniform)",
            )
            ax_multi_freq.legend(fontsize=10, loc="upper right")

        ax_multi_freq.set_title(
            "MULTI_MCQ: Option Correct Frequency\n"
            f"chi2={chi2_multi:.2f}, p {format_p(p_multi)}, Cramer's V={v_multi:.3f}",
            fontweight="bold",
            fontsize=12,
        )
        ax_multi_freq.set_xlabel("Option Position", fontsize=11, fontweight="bold")
        ax_multi_freq.set_ylabel("Times Correct", fontsize=11, fontweight="bold")
        ax_multi_freq.set_ylim(0, (max(multi_values) * 1.15) if multi_values and max(multi_values) > 0 else 1)

        for bar, val in zip(bars2, multi_values):
            ax_multi_freq.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.5,
                str(val),
                ha="center",
                va="bottom",
                fontsize=10,
                fontweight="bold",
            )
        ax_multi_freq.grid(True, alpha=0.3, axis="y")
    else:
        ax_multi_freq.set_title("MULTI_MCQ: Option Correct Frequency", fontweight="bold", fontsize=12)
        ax_multi_freq.set_xticks([])
        ax_multi_freq.set_yticks([])
        ax_multi_freq.text(
            0.5,
            0.5,
            "No MULTI_MCQ data available",
            ha="center",
            va="center",
            fontsize=12,
            transform=ax_multi_freq.transAxes,
        )

    fig_multi_opt.tight_layout()
    fig_multi_opt.savefig(OUTPUT_MULTI_OPTION_PATH, dpi=150, bbox_inches="tight")
    print(f"Saved: {OUTPUT_MULTI_OPTION_PATH}")

    # Figure 3: MULTI_MCQ answer set size
    fig_multi_set, ax_multi_set = plt.subplots(1, 1, figsize=(8, 6))
    if has_multi_data and answer_counts:
        set_sizes = sorted(answer_counts.keys())
        set_counts = [answer_counts.get(s, 0) for s in set_sizes]

        bars3 = ax_multi_set.bar(
            [str(s) for s in set_sizes],
            set_counts,
            color="#3498db",
            edgecolor="black",
            linewidth=1.2,
            alpha=0.85,
        )

        ax_multi_set.set_title(
            "MULTI_MCQ: Number of Correct Answers per Question\n"
            f"(n={total_multi})",
            fontweight="bold",
            fontsize=12,
        )
        ax_multi_set.set_xlabel("Number of Correct Answers", fontsize=11, fontweight="bold")
        ax_multi_set.set_ylabel("Frequency", fontsize=11, fontweight="bold")
        ax_multi_set.set_ylim(0, (max(set_counts) * 1.15) if set_counts and max(set_counts) > 0 else 1)

        for bar, val in zip(bars3, set_counts):
            pct = (val / total_multi * 100) if total_multi else 0
            ax_multi_set.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.5,
                f"{val}\n({pct:.1f}%)",
                ha="center",
                va="bottom",
                fontsize=10,
                fontweight="bold",
            )
        ax_multi_set.grid(True, alpha=0.3, axis="y")
    else:
        ax_multi_set.set_title("MULTI_MCQ: Number of Correct Answers per Question", fontweight="bold", fontsize=12)
        ax_multi_set.set_xticks([])
        ax_multi_set.set_yticks([])
        ax_multi_set.text(
            0.5,
            0.5,
            "No MULTI_MCQ data available",
            ha="center",
            va="center",
            fontsize=12,
            transform=ax_multi_set.transAxes,
        )

    fig_multi_set.tight_layout()
    fig_multi_set.savefig(OUTPUT_MULTI_SETSIZE_PATH, dpi=150, bbox_inches="tight")
    print(f"Saved: {OUTPUT_MULTI_SETSIZE_PATH}")

    backend = plt.get_backend().lower()
    if "agg" not in backend:
        plt.show()

    plt.close(fig_mcq)
    plt.close(fig_multi_opt)
    plt.close(fig_multi_set)

def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Analyze answer position bias in question bank.")
    parser.add_argument(
        "--input",
        default=str(_WORKSPACE_ROOT / "questions.csv"),
        help="Path to questions CSV (default: workspace questions.csv)",
    )
    args = parser.parse_args()

    run_parse_sanity_test()

    input_path = Path(args.input).expanduser().resolve()
    print("\n" + "=" * 70)
    print("ANSWER POSITION BIAS ANALYSIS")
    print("=" * 70)
    print(f"\nInput file: {input_path}")

    if not input_path.exists():
        print(f"ERROR: File not found: {input_path}")
        return

    questions = read_questions_csv(input_path)
    mcq = questions[questions["type"] == "MCQ"].copy()
    multi_mcq = questions[questions["type"] == "MULTI_MCQ"].copy()

    print("\nDataset Summary:")
    print(f"  Total questions:     {len(questions)}")
    print(f"  MCQ questions:       {len(mcq)}")
    print(f"  MULTI_MCQ questions: {len(multi_mcq)}")

    mcq_counts, chi2_mcq, p_mcq, v_mcq = analyse_mcq_bias(mcq)
    (
        option_correct_counts,
        answer_counts,
        _total_correct_options,
        total_multi,
        chi2_multi,
        p_multi,
        v_multi,
    ) = analyse_multi_mcq_bias(multi_mcq)

    print("\n" + "=" * 70)
    print("GENERATING VISUALIZATIONS")
    print("=" * 70)

    plot_results(
        mcq_counts=mcq_counts,
        total_mcq=len(mcq),
        chi2_mcq=chi2_mcq,
        p_mcq=p_mcq,
        v_mcq=v_mcq,
        option_correct_counts=option_correct_counts,
        answer_counts=answer_counts,
        total_multi=total_multi,
        chi2_multi=chi2_multi,
        p_multi=p_multi,
        v_multi=v_multi,
        has_multi_data=not multi_mcq.empty,
    )

    print("\n" + "=" * 70)
    print("ANALYSIS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
