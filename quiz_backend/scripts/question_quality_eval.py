import numpy as np
from scipy import stats
import matplotlib.pyplot as plt


def pearson_with_ci(
    x: np.ndarray, y: np.ndarray, confidence: float = 0.95
) -> tuple[float, float, float, float]:
    """Return Pearson r, p-value, and Fisher z confidence interval bounds."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    if x.size != y.size or x.size < 4:
        return np.nan, np.nan, np.nan, np.nan

    if np.std(x) == 0 or np.std(y) == 0:
        return np.nan, np.nan, np.nan, np.nan

    r, p = stats.pearsonr(x, y)

    # Clip r very slightly to keep arctanh numerically stable near +/-1.
    r_clip = float(np.clip(r, -0.999999, 0.999999))
    z = np.arctanh(r_clip)
    se = 1.0 / np.sqrt(x.size - 3)
    z_crit = stats.norm.ppf((1.0 + confidence) / 2.0)

    z_lower = z - z_crit * se
    z_upper = z + z_crit * se
    r_lower = float(np.tanh(z_lower))
    r_upper = float(np.tanh(z_upper))

    return float(r), float(p), r_lower, r_upper


def correlation_strength(r: float) -> str:
    if not np.isfinite(r):
        return "Undefined"
    if r > 0.80:
        return "Strong"
    if r > 0.60:
        return "Moderate"
    if r > 0.40:
        return "Fair"
    return "Poor"


def fmt_num(value: float, width: int, decimals: int = 3) -> str:
    if not np.isfinite(value):
        return f"{'N/A':>{width}}"
    return f"{value:>{width}.{decimals}f}"


def min_detectable_correlation(n: int, alpha: float = 0.05) -> float:
    """Two-sided significance threshold for Pearson r at sample size n."""
    if n <= 2:
        return np.nan
    df = n - 2
    t_crit = stats.t.ppf(1.0 - alpha / 2.0, df)
    return float(t_crit / np.sqrt(df + t_crit**2))


# -- CORRECTED Human rater means -- YOUR questions -----------------------------
human_your = {
    "Factual": [
        5.00,
        5.00,
        5.00,
        5.00,
        5.00,
        5.00,
        4.33,
        4.00,
        4.33,
        5.00,
        5.00,
        5.00,
        5.00,
        5.00,
        5.00,
        5.00,
        5.00,
        5.00,
        4.33,
        4.00,
    ],
    "Clarity": [
        5.0,
        4.7,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        3.3,
        4.3,
        5.0,
        5.0,
        5.0,
        4.3,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        4.3,
        3.6,
    ],
    "Curriculum": [
        1.3,
        3.3,
        5.0,
        5.0,
        1.0,
        5.0,
        5.0,
        4.0,
        5.0,
        5.0,
        5.0,
        5.0,
        3.7,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        3.7,
    ],
    "Cognitive": [
        1.0,
        1.3,
        1.7,
        1.7,
        1.0,
        1.0,
        3.3,
        4.7,
        3.0,
        3.0,
        2.7,
        2.7,
        4.3,
        4.3,
        4.0,
        4.3,
        4.7,
        4.7,
        4.3,
        5.0,
    ],
    "Independence": [
        5.0,
        5.0,
        5.0,
        5.0,
        1.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
    ],
}

# GPT-4o scores -- YOUR questions
gpt_your = {
    "Factual": [
        5,
        5,
        2,
        5,
        4,
        5,
        4,
        5,
        5,
        4,
        5,
        4,
        5,
        5,
        5,
        5,
        5,
        4,
        5,
        5,
    ],
    "Clarity": [
        5,
        5,
        3,
        5,
        5,
        5,
        4,
        5,
        5,
        5,
        5,
        4,
        5,
        5,
        5,
        5,
        5,
        4,
        5,
        5,
    ],
    "Curriculum": [
        2,
        4,
        5,
        5,
        1,
        5,
        5,
        4,
        5,
        5,
        5,
        4,
        5,
        5,
        5,
        5,
        5,
        5,
        5,
        5,
    ],
    "Cognitive": [
        1,
        2,
        3,
        2,
        1,
        2,
        3,
        3,
        4,
        3,
        2,
        2,
        4,
        4,
        3,
        4,
        4,
        3,
        5,
        5,
    ],
    "Independence": [
        5,
        5,
        5,
        5,
        2,
        5,
        5,
        5,
        5,
        5,
        5,
        4,
        5,
        5,
        5,
        5,
        5,
        4,
        5,
        5,
    ],
}

# Human rater means-Quizlet questions
human_quizlet = {
    "Factual": [
        4.3,
        4.7,
        5.0,
        5.0,
        5.0,
        4.0,
        5.0,
        4.0,
        5.0,
        5.0,
        4.0,
        4.7,
        5.0,
        5.0,
        5.0,
        5.0,
        4.0,
        5.0,
        4.3,
        3.7,
    ],
    "Clarity": [
        5.0,
        5.0,
        5.0,
        4.3,
        5.0,
        3.6,
        4.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
    ],
    "Curriculum": [
        3.7,
        4.7,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        2.7,
        3.3,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
    ],
    "Cognitive": [
        1.7,
        2.7,
        1.3,
        1.7,
        2.3,
        1.0,
        2.0,
        1.7,
        1.0,
        1.0,
        3.0,
        2.7,
        2.3,
        2.3,
        1.0,
        1.0,
        2.7,
        1.7,
        1.3,
        2.0,
    ],
    "Independence": [
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
    ],
}

# GPT-4o scores -- Quizlet questions
gpt_quizlet = {
    "Factual": [
        5,
        5,
        5,
        4,
        4,
        5,
        5,
        5,
        5,
        4,
        5,
        4,
        4,
        4,
        5,
        5,
        4,
        4,
        5,
        5,
    ],
    "Clarity": [
        4,
        4,
        5,
        4,
        4,
        4,
        4,
        4,
        5,
        4,
        4,
        4,
        4,
        4,
        5,
        5,
        3,
        4,
        5,
        5,
    ],
    "Curriculum": [
        5,
        5,
        5,
        4,
        5,
        5,
        5,
        5,
        5,
        5,
        5,
        4,
        5,
        5,
        5,
        5,
        5,
        5,
        5,
        5,
    ],
    "Cognitive": [
        2,
        2,
        2,
        1,
        2,
        2,
        2,
        2,
        1,
        2,
        2,
        2,
        3,
        3,
        2,
        2,
        3,
        3,
        2,
        3,
    ],
    "Independence": [
        5,
        5,
        5,
        5,
        5,
        5,
        5,
        5,
        5,
        5,
        5,
        5,
        5,
        5,
        5,
        5,
        5,
        5,
        5,
        5,
    ],
}

criteria = ["Factual", "Clarity", "Curriculum", "Cognitive", "Independence"]

criteria_display = {
    "Factual": "Factual Correctness",
    "Clarity": "Clarity",
    "Curriculum": "Curriculum Relevance",
    "Cognitive": "Cognitive Level",
    "Independence": "Independence",
}


def main() -> None:
    n_questions = len(next(iter(human_your.values())))

    print("=" * 70)
    print("MEAN SCORES -- ALL FOUR EVALUATION SETS")
    print("=" * 70)
    print(
        f"\n{'Criterion':<22} {'Human-Yours':>12} "
        f"{'GPT-Yours':>10} {'Human-Quizlet':>12} "
        f"{'GPT-Quizlet':>10}"
    )
    print("-" * 68)

    means = {}
    for c in criteria:
        h_y = np.mean(human_your[c])
        g_y = np.mean(gpt_your[c])
        h_a = np.mean(human_quizlet[c])
        g_a = np.mean(gpt_quizlet[c])
        means[c] = {"hY": h_y, "gY": g_y, "hA": h_a, "gA": g_a}
        print(
            f"{criteria_display[c]:<22} "
            f"{h_y:>12.2f} {g_y:>10.2f} "
            f"{h_a:>12.2f} {g_a:>10.2f}"
        )


    # 2. CORRELATION ANALYSIS
    
    print("\n" + "=" * 70)
    print("HUMAN vs GPT-4o CORRELATION")
    print("=" * 70)

    correlations = {"your": {}, "quizlet": {}}

    for label, human, gpt, key in [
        ("YOUR QUESTIONS", human_your, gpt_your, "your"),
        ("QUIZLET BASELINE", human_quizlet, gpt_quizlet, "quizlet"),
    ]:
        print(f"\n--- {label} ---")
        print(
            f"{'Criterion':<22} {'r':>8} {'95% CI':>22} "
            f"{'p':>10} {'Strength':>12} {'Valid r>0.7':>12}"
        )
        print("-" * 96)

        for c in criteria:
            h = np.array(human[c])
            g = np.array(gpt[c], dtype=float)
            r, p, r_lower, r_upper = pearson_with_ci(h, g)
            correlations[key][c] = {
                "r": r,
                "p": p,
                "r_lower": r_lower,
                "r_upper": r_upper,
            }

            strength = correlation_strength(r)
            validated = "Yes" if np.isfinite(r) and r > 0.70 else "No"
            ci_str = (
                f"[{r_lower:>6.3f}, {r_upper:>6.3f}]"
                if np.isfinite(r_lower) and np.isfinite(r_upper)
                else f"{'N/A (constant)':>22}"
            )

            print(
                f"{criteria_display[c]:<22} "
                f"{fmt_num(r, 8, 3)} {ci_str} {fmt_num(p, 10, 4)} "
                f"{strength:>12} {validated:>12}"
            )



    
    print("\n" + "=" * 70)
    print("VARIANCE ANALYSIS")
    print("=" * 70)

    for label, human, gpt in [
        ("YOUR QUESTIONS", human_your, gpt_your),
        ("QUIZLET BASELINE", human_quizlet, gpt_quizlet),
    ]:
        print(f"\n--- {label} ---")
        print(
            f"{'Criterion':<22} {'Human Var':>12} {'GPT Var':>12} "
            f"{'Human SD':>12} {'GPT SD':>10}"
        )
        print("-" * 74)

        for c in criteria:
            h_var = float(np.var(human[c]))
            g_var = float(np.var(gpt[c]))
            h_sd = float(np.std(human[c]))
            g_sd = float(np.std(gpt[c]))
            print(
                f"{criteria_display[c]:<22} "
                f"{h_var:>12.3f} {g_var:>12.3f} {h_sd:>12.3f} {g_sd:>10.3f}"
            )

    # 4. STATISTICAL POWER THRESHOLD

    print("\n" + "=" * 70)
    print("STATISTICAL POWER THRESHOLD")
    print("=" * 70)
    r_threshold = min_detectable_correlation(n_questions, alpha=0.05)
    print(f"\nWith n={n_questions} questions and alpha=0.05 (two-sided):")
    print(f"Minimum |r| needed for p<0.05 is approximately: {r_threshold:.3f}")

    # ======================================================================
    # 5. SCRIPT REVIEW SUMMARY
    # ======================================================================
    print("\n" + "=" * 70)
    print("SCRIPT REVIEW SUMMARY")
    print("=" * 70)
    print("Status: YES, mostly correct.")
    print("Pearson computation is valid for question-level paired data.")
    print("Added: confidence intervals, variance checks, and power threshold.")
    print("Note: criteria with near-constant scores can yield unstable or undefined r.")

    # ======================================================================
    # 6. COGNITIVE LEVEL -- KEY FINDING
    # ======================================================================
    print("\n" + "=" * 70)
    print("KEY FINDING: COGNITIVE LEVEL COMPARISON")
    print("=" * 70)
    print(f"\n  Your questions (Human):  {means['Cognitive']['hY']:.2f}")
    print(f"  Your questions (GPT-4o): {means['Cognitive']['gY']:.2f}")
    print(f"  Quizlet baseline (Human):   {means['Cognitive']['hA']:.2f}")
    print(f"  Quizlet baseline (GPT-4o):  {means['Cognitive']['gA']:.2f}")
    print(
        f"\n  Human advantage (yours vs Quizlet):  "
        f"+{means['Cognitive']['hY'] - means['Cognitive']['hA']:.2f}"
    )
    print(
        f"  GPT-4o advantage (yours vs Quizlet): "
        f"+{means['Cognitive']['gY'] - means['Cognitive']['gA']:.2f}"
    )
    agree = (
        means["Cognitive"]["hY"] > means["Cognitive"]["hA"]
        and means["Cognitive"]["gY"] > means["Cognitive"]["gA"]
    )
    print(
        f"\n  Both methods agree your questions are cognitively superior: "
        f"{'Yes' if agree else 'No'}"
    )

    
    # 7. FIGURES (MEANS + CORRELATION HEATMAP)
    fig, axes = plt.subplots(2, 3, figsize=(15, 10))
    axes = axes.flatten()

    for i, c in enumerate(criteria):
        ax = axes[i]
        labels_bar = ["Human\n(Yours)", "GPT-4o\n(Yours)", "Human\n(Quizlet)", "GPT-4o\n(Quizlet)"]
        values = [means[c]["hY"], means[c]["gY"], means[c]["hA"], means[c]["gA"]]
        bar_colors = ["#2ecc71", "#27ae60", "#3498db", "#2980b9"]

        bars = ax.bar(labels_bar, values, color=bar_colors, edgecolor="black", linewidth=0.8)
        ax.set_ylim(0, 5.8)
        ax.set_title(criteria_display[c], fontweight="bold")
        ax.set_ylabel("Mean Score (out of 5)")
        ax.axhline(y=4.0, color="orange", linestyle="--", alpha=0.5, linewidth=1)
        ax.grid(True, alpha=0.2, axis="y")

        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.05,
                f"{val:.2f}",
                ha="center",
                va="bottom",
                fontsize=9,
                fontweight="bold",
            )

    # -- Plot 6: Correlation heatmap -----------------------------------------
    ax6 = axes[5]
    corr_matrix = np.array(
        [
            [correlations["your"][c]["r"] for c in criteria],
            [correlations["quizlet"][c]["r"] for c in criteria],
        ]
    )

    im = ax6.imshow(corr_matrix, cmap="RdYlGn", vmin=-1, vmax=1, aspect="auto")
    ax6.set_xticks(range(len(criteria)))
    ax6.set_xticklabels([criteria_display[c].replace(" ", "\n") for c in criteria], fontsize=8)
    ax6.set_yticks([0, 1])
    ax6.set_yticklabels(["Your Qs", "Quizlet Qs"])
    ax6.set_title("Human vs GPT-4o\nCorrelation (r)", fontweight="bold")

    for i in range(2):
        for j in range(len(criteria)):
            val = corr_matrix[i, j]
            ax6.text(
                j,
                i,
                f"{val:.2f}",
                ha="center",
                va="center",
                fontsize=10,
                fontweight="bold",
                color="black",
            )

    plt.colorbar(im, ax=ax6, shrink=0.8)

    plt.suptitle(
        "Question Quality Evaluation:\n"
        "Human Raters vs GPT-4o "
        "(n=20 questions per set, 3 human raters)",
        fontsize=13,
        fontweight="bold",
    )
    plt.tight_layout()
    plt.savefig("question_quality_full.png", dpi=150, bbox_inches="tight")

    backend = plt.get_backend().lower()
    if "agg" not in backend:
        plt.show()
    else:
        plt.close(fig)

    print("\nSaved: question_quality_full.png")


if __name__ == "__main__":
    main()
