"""
Answer position bias analysis for MCQ and MULTI_MCQ questions.

Reads a questions CSV and prints:
1) MCQ answer position distribution + chi-square test
2) MULTI_MCQ option frequency + chi-square test
3) MULTI_MCQ answer-set-size distribution
4) Early-vs-late position clustering + binomial test

Saves three separate figures in the current working directory:
1) answer_bias_mcq.png
2) answer_bias_multi_option.png
3) answer_bias_multi_setsize.png

Run from workspace root:
    python quiz_backend/scripts/answer_bias_analysis.py

Or from inside quiz_backend/:
    python scripts/answer_bias_analysis.py
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

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
_TARGET_QUESTION_COUNT = 100
_RANDOM_SEED = 42


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
    test_cases = [
        '["A","B"]',
        '["A","B","D"]',
        '["B","C"]',
        ["A", "B"],
        "A,B",
    ]

    print("=== PARSE TEST ===")
    for case in test_cases:
        result = parse_answer(case)
        print(f"  {str(case):20s} -> {result}")


def downsample_mcq_to_target(mcq: pd.DataFrame, target_n: int) -> tuple[pd.DataFrame, bool]:
    """Downsample MCQ rows in-memory when count exceeds target_n."""
    if len(mcq) > target_n:
        return mcq.sample(n=target_n, random_state=_RANDOM_SEED).copy(), True
    return mcq.copy(), False


def scale_counter_to_target(counts: Counter, source_total: int, target_n: int) -> dict[str, float]:
    """Scale counts to a target-question equivalent."""
    if source_total <= 0:
        return {str(k): 0.0 for k in counts.keys()}
    factor = target_n / source_total
    return {str(k): float(v) * factor for k, v in counts.items()}


def round_scaled_counts(counts: dict[str, float]) -> dict[str, int]:
    """Round scaled values to whole numbers."""
    return {k: int(round(v)) for k, v in counts.items()}


def analyse_mcq_bias(mcq: pd.DataFrame) -> tuple[Counter, float, float]:
    print("\n=== MCQ ANSWER POSITION BIAS ===")

    mcq = mcq.copy()
    mcq["answer_clean"] = mcq["answer"].astype(str).str.strip().str.strip('"').str.upper()
    mcq_position_counts: Counter = Counter(mcq["answer_clean"])

    print("Correct answer distribution:")
    total_mcq = len(mcq)
    for pos in _POSITIONS:
        count = mcq_position_counts.get(pos, 0)
        pct = (count / total_mcq * 100) if total_mcq else 0.0
        bar = "#" * int(pct / 2)
        print(f"  {pos}: {count:3d} ({pct:.1f}%) {bar}")

    observed_mcq = [mcq_position_counts.get(p, 0) for p in _POSITIONS]
    expected_mcq = [total_mcq / 4] * 4 if total_mcq else [0, 0, 0, 0]

    if total_mcq and sum(observed_mcq) > 0:
        chi2_mcq, p_mcq = stats.chisquare(observed_mcq, expected_mcq)
    else:
        chi2_mcq, p_mcq = float("nan"), float("nan")

    print("\nChi-square test (uniform distribution):")
    print(f"  chi2 = {chi2_mcq:.3f}")
    print(f"  p    = {p_mcq:.4f}")
    print(
        "  Significant bias (p<0.05): "
        f"{p_mcq < 0.05 if total_mcq and sum(observed_mcq) > 0 else 'N/A'}"
    )

    return mcq_position_counts, chi2_mcq, p_mcq


def analyse_multi_mcq_bias(
    multi_mcq: pd.DataFrame,
    target_n: int,
) -> tuple[Counter, Counter, int, int, dict[str, int], dict[str, int]]:
    print("\n=== MULTI_MCQ ANSWER POSITION BIAS ===")

    if multi_mcq.empty:
        print("No MULTI_MCQ rows found; skipping multi-answer bias statistics.")
        return Counter(), Counter(), 0, 0, {}, {}

    multi_mcq = multi_mcq.copy()
    multi_mcq["answer_list"] = multi_mcq["answer"].apply(parse_answer)

    print("Sample parsed answers:")
    for _, row in multi_mcq.head(3).iterrows():
        print(f"  Raw: {row['answer']} -> Parsed: {row['answer_list']}")

    print("\nIndividual option correct frequency:")
    option_correct_counts: Counter = Counter()
    total_multi = len(multi_mcq)

    for _, row in multi_mcq.iterrows():
        for opt in row["answer_list"]:
            if opt in _POSITIONS:
                option_correct_counts[opt] += 1

    for pos in _POSITIONS:
        count = option_correct_counts.get(pos, 0)
        pct = (count / total_multi * 100) if total_multi else 0.0
        bar = "#" * int(pct / 2)
        print(f"  {pos} is correct in: {count:3d}/{total_multi} ({pct:.1f}%) {bar}")

    scaled_option_counts = round_scaled_counts(
        scale_counter_to_target(option_correct_counts, total_multi, target_n)
    )
    print(f"\nScaled option frequency (equivalent to {target_n} MULTI_MCQ questions):")
    for pos in _POSITIONS:
        print(f"  {pos}: {scaled_option_counts.get(pos, 0)}")

    observed_multi = [option_correct_counts.get(p, 0) for p in _POSITIONS]
    total_correct_options = sum(observed_multi)
    expected_multi = [total_correct_options / 4] * 4 if total_correct_options else [0, 0, 0, 0]

    if total_correct_options:
        chi2_multi, p_multi = stats.chisquare(observed_multi, expected_multi)
    else:
        chi2_multi, p_multi = float("nan"), float("nan")

    print("\nChi-square test (uniform option frequency):")
    print(f"  chi2 = {chi2_multi:.3f}")
    print(f"  p    = {p_multi:.4f}")
    print(
        "  Significant bias (p<0.05): "
        f"{p_multi < 0.05 if total_correct_options else 'N/A'}"
    )

    print("\nNumber of correct answers per question:")
    answer_counts: Counter = Counter(len(row["answer_list"]) for _, row in multi_mcq.iterrows())
    for n, count in sorted(answer_counts.items()):
        pct = (count / total_multi * 100) if total_multi else 0.0
        print(f"  {n} correct answers: {count:3d} ({pct:.1f}%)")

    scaled_answer_counts = round_scaled_counts(
        scale_counter_to_target(answer_counts, total_multi, target_n)
    )
    print(f"\nScaled answer-set size distribution (equivalent to {target_n} questions):")
    for n in sorted(answer_counts.keys()):
        print(f"  {n} correct answers: {scaled_answer_counts.get(str(n), 0)}")

    if len(answer_counts) == 1 and answer_counts:
        fixed_n = next(iter(answer_counts.keys()))
        print(f"\n  All questions have exactly {fixed_n} correct answers")
        print(f"  This reduces to guessing {fixed_n}/4 options correctly")
    elif answer_counts:
        print(
            f"\n  Variable number of correct answers "
            f"({min(answer_counts.keys())}-{max(answer_counts.keys())})"
        )

    print("\nPosition clustering analysis:")
    early_correct = 0
    middle_correct = 0
    late_correct = 0
    total_options_checked = 0

    for _, row in multi_mcq.iterrows():
        for opt in row["answer_list"]:
            if opt in ["A", "B"]:
                early_correct += 1
            if opt in ["B", "C"]:
                middle_correct += 1
            if opt in ["C", "D"]:
                late_correct += 1
            if opt in _POSITIONS:
                total_options_checked += 1

    if total_options_checked > 0:
        early_pct = early_correct / total_options_checked * 100
        middle_pct = middle_correct / total_options_checked * 100
        late_pct = late_correct / total_options_checked * 100
        print(f"  Early positions (A,B): {early_correct} ({early_pct:.1f}%)")
        print(f"  Middle positions (B,C): {middle_correct} ({middle_pct:.1f}%)")
        print(f"  Late positions  (C,D): {late_correct} ({late_pct:.1f}%)")

        binom_result = stats.binomtest(early_correct, total_options_checked, p=0.5)
        print(f"  Binomial test p = {binom_result.pvalue:.4f}")
        print(f"  Significant clustering: {binom_result.pvalue < 0.05}")

    return (
        option_correct_counts,
        answer_counts,
        total_correct_options,
        total_multi,
        scaled_option_counts,
        scaled_answer_counts,
    )


def plot_results(
    mcq_counts: Counter,
    total_mcq: int,
    mcq_display_n: int,
    total_correct_options: int,
    answer_counts: Counter,
    scaled_option_counts: dict[str, int],
    scaled_answer_counts: dict[str, int],
    target_n: int,
    has_multi_data: bool,
) -> None:
    if plt is None:
        print("\nmatplotlib not available - skipping figure generation.")
        return

    colors_pos = ["#3498db", "#2ecc71", "#e74c3c", "#9b59b6"]

    fig_mcq, ax_mcq = plt.subplots(1, 1, figsize=(6, 5))
    mcq_values = [mcq_counts.get(p, 0) for p in _POSITIONS]
    bars1 = ax_mcq.bar(_POSITIONS, mcq_values, color=colors_pos, edgecolor="black", linewidth=0.8)
    if total_mcq:
        ax_mcq.axhline(
            y=mcq_display_n / 4,
            color="red",
            linestyle="--",
            linewidth=2,
            label=f"Expected ({mcq_display_n / 4:.0f})",
        )
    ax_mcq.set_title(f"MCQ: Correct Answer\nPosition Distribution (n={mcq_display_n})", fontweight="bold")
    ax_mcq.set_xlabel("Answer Position")
    ax_mcq.set_ylabel("Frequency")
    if total_mcq:
        ax_mcq.legend()
    for bar, val in zip(bars1, mcq_values):
        ax_mcq.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3, str(val), ha="center", fontsize=10)
    fig_mcq.tight_layout()
    fig_mcq.savefig(OUTPUT_MCQ_PATH, dpi=150)

    fig_multi_opt, ax_multi_freq = plt.subplots(1, 1, figsize=(6, 5))
    if has_multi_data:
        scaled_multi_values = [scaled_option_counts.get(p, 0) for p in _POSITIONS]
        bars2 = ax_multi_freq.bar(
            _POSITIONS,
            scaled_multi_values,
            color=colors_pos,
            edgecolor="black",
            linewidth=0.8,
        )
        if total_correct_options:
            expected_per_option = sum(scaled_multi_values) / 4
            ax_multi_freq.axhline(
                y=expected_per_option,
                color="red",
                linestyle="--",
                linewidth=2,
                label=f"Expected ({expected_per_option:.0f})",
            )
            ax_multi_freq.legend()
        ax_multi_freq.set_title(f"MULTI_MCQ: Option Correct\nFrequency (scaled to {target_n})", fontweight="bold")
        ax_multi_freq.set_xlabel("Option Position")
        ax_multi_freq.set_ylabel("Times Correct (scaled)")
        for bar, val in zip(bars2, scaled_multi_values):
            ax_multi_freq.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3, str(val), ha="center", fontsize=10)
    else:
        ax_multi_freq.set_title("MULTI_MCQ: Option Correct\nFrequency", fontweight="bold")
        ax_multi_freq.set_xticks([])
        ax_multi_freq.set_yticks([])
        ax_multi_freq.text(0.5, 0.5, "No MULTI_MCQ data in input", ha="center", va="center", fontsize=11)
    fig_multi_opt.tight_layout()
    fig_multi_opt.savefig(OUTPUT_MULTI_OPTION_PATH, dpi=150)

    fig_multi_set, ax_multi_set = plt.subplots(1, 1, figsize=(6, 5))
    if has_multi_data:
        set_sizes = sorted(answer_counts.keys())
        set_counts = [scaled_answer_counts.get(str(s), 0) for s in set_sizes]
        ax_multi_set.bar([str(s) for s in set_sizes], set_counts, color="#3498db", edgecolor="black", linewidth=0.8)
        ax_multi_set.set_title(f"MULTI_MCQ: Number of\nCorrect Answers (scaled to {target_n})", fontweight="bold")
        ax_multi_set.set_xlabel("Number of Correct Answers")
        ax_multi_set.set_ylabel("Frequency (scaled)")
        for i, val in enumerate(set_counts):
            ax_multi_set.text(i, val + 0.2, str(val), ha="center", fontsize=10)
    else:
        ax_multi_set.set_title("MULTI_MCQ: Number of\nCorrect Answers per Question", fontweight="bold")
        ax_multi_set.set_xticks([])
        ax_multi_set.set_yticks([])
        ax_multi_set.text(0.5, 0.5, "No MULTI_MCQ data in input", ha="center", va="center", fontsize=11)
    fig_multi_set.tight_layout()
    fig_multi_set.savefig(OUTPUT_MULTI_SETSIZE_PATH, dpi=150)

    backend = plt.get_backend().lower()
    if "agg" not in backend:
        plt.show()

    plt.close(fig_mcq)
    plt.close(fig_multi_opt)
    plt.close(fig_multi_set)

    print(f"Saved: {OUTPUT_MCQ_PATH}")
    print(f"Saved: {OUTPUT_MULTI_OPTION_PATH}")
    print(f"Saved: {OUTPUT_MULTI_SETSIZE_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze answer position bias.")
    parser.add_argument(
        "--input",
        default=str(_WORKSPACE_ROOT / "questions.csv"),
        help="Path to questions CSV (default: workspace questions.csv)",
    )
    parser.add_argument(
        "--target-n",
        type=int,
        default=_TARGET_QUESTION_COUNT,
        help="Target question count for in-memory MCQ downsampling and MULTI scaling.",
    )
    args = parser.parse_args()

    run_parse_sanity_test()

    input_path = Path(args.input).expanduser().resolve()
    questions = read_questions_csv(input_path)
    mcq_raw = questions[questions["type"] == "MCQ"].copy()
    mcq, mcq_downsampled = downsample_mcq_to_target(mcq_raw, args.target_n)
    multi_mcq = questions[questions["type"] == "MULTI_MCQ"].copy()

    print(f"\nInput file: {input_path}")

    print(f"\nMCQ questions (raw): {len(mcq_raw)}")
    print(f"MCQ used in analysis: {len(mcq)}")
    if mcq_downsampled:
        print(
            f"MCQ was downsampled in-memory from {len(mcq_raw)} "
            f"to {args.target_n} (CSV unchanged)."
        )
    elif len(mcq_raw) < args.target_n:
        print(
            f"MCQ has fewer than target ({args.target_n}); "
            "no deletion performed."
        )
    print(f"MULTI_MCQ questions: {len(multi_mcq)}")

    mcq_counts, _chi2_mcq, _p_mcq = analyse_mcq_bias(mcq)
    (
        _option_correct_counts,
        answer_counts,
        total_correct_options,
        _total_multi,
        scaled_option_counts,
        scaled_answer_counts,
    ) = analyse_multi_mcq_bias(multi_mcq, target_n=args.target_n)

    plot_results(
        mcq_counts=mcq_counts,
        total_mcq=len(mcq),
        mcq_display_n=len(mcq),
        total_correct_options=total_correct_options,
        answer_counts=answer_counts,
        scaled_option_counts=scaled_option_counts,
        scaled_answer_counts=scaled_answer_counts,
        target_n=args.target_n,
        has_multi_data=not multi_mcq.empty,
    )


if __name__ == "__main__":
    main()
