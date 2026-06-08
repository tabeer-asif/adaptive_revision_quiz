import numpy as np
from scipy import stats
import matplotlib.pyplot as plt


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

# Human rater means -- ANKI questions
human_anki = {
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

# GPT-4o scores -- ANKI questions
gpt_anki = {
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
    # ======================================================================
    # 1. CORRECTED MEAN SCORES
    # ======================================================================
    print("=" * 70)
    print("CORRECTED MEAN SCORES -- ALL FOUR EVALUATION SETS")
    print("=" * 70)
    print(
        f"\n{'Criterion':<22} {'Human-Yours':>12} "
        f"{'GPT-Yours':>10} {'Human-Anki':>12} "
        f"{'GPT-Anki':>10}"
    )
    print("-" * 68)

    means = {}
    for c in criteria:
        h_y = np.mean(human_your[c])
        g_y = np.mean(gpt_your[c])
        h_a = np.mean(human_anki[c])
        g_a = np.mean(gpt_anki[c])
        means[c] = {"hY": h_y, "gY": g_y, "hA": h_a, "gA": g_a}
        print(
            f"{criteria_display[c]:<22} "
            f"{h_y:>12.2f} {g_y:>10.2f} "
            f"{h_a:>12.2f} {g_a:>10.2f}"
        )

    # ======================================================================
    # 2. CORRELATION ANALYSIS
    # ======================================================================
    print("\n" + "=" * 70)
    print("HUMAN vs GPT-4o CORRELATION")
    print("=" * 70)

    correlations = {"your": {}, "anki": {}}

    for label, human, gpt, key in [
        ("YOUR QUESTIONS", human_your, gpt_your, "your"),
        ("ANKI BASELINE", human_anki, gpt_anki, "anki"),
    ]:
        print(f"\n--- {label} ---")
        print(f"{'Criterion':<22} {'r':>8} {'p':>10} {'Strength':>12} {'Valid r>0.7':>12}")
        print("-" * 68)

        for c in criteria:
            h = np.array(human[c])
            g = np.array(gpt[c], dtype=float)
            r, p = stats.pearsonr(h, g)
            correlations[key][c] = r

            strength = (
                "Strong"
                if r > 0.80
                else "Moderate"
                if r > 0.60
                else "Fair"
                if r > 0.40
                else "Poor"
            )
            validated = "Yes" if r > 0.70 else "No"

            print(
                f"{criteria_display[c]:<22} "
                f"{r:>8.3f} {p:>10.4f} "
                f"{strength:>12} {validated:>12}"
            )

    # ======================================================================
    # 3. COGNITIVE LEVEL -- KEY FINDING
    # ======================================================================
    print("\n" + "=" * 70)
    print("KEY FINDING: COGNITIVE LEVEL COMPARISON")
    print("=" * 70)
    print(f"\n  Your questions (Human):  {means['Cognitive']['hY']:.2f}")
    print(f"  Your questions (GPT-4o): {means['Cognitive']['gY']:.2f}")
    print(f"  Anki baseline (Human):   {means['Cognitive']['hA']:.2f}")
    print(f"  Anki baseline (GPT-4o):  {means['Cognitive']['gA']:.2f}")
    print(
        f"\n  Human advantage (yours vs Anki):  "
        f"+{means['Cognitive']['hY'] - means['Cognitive']['hA']:.2f}"
    )
    print(
        f"  GPT-4o advantage (yours vs Anki): "
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

    # ======================================================================
    # 4. FIGURES
    # ======================================================================
    fig, axes = plt.subplots(2, 3, figsize=(15, 10))
    axes = axes.flatten()

    # -- Plots 1-5: Bar chart per criterion ---------------------------------
    for i, c in enumerate(criteria):
        ax = axes[i]
        labels_bar = ["Human\n(Yours)", "GPT-4o\n(Yours)", "Human\n(Anki)", "GPT-4o\n(Anki)"]
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
            [correlations["your"][c] for c in criteria],
            [correlations["anki"][c] for c in criteria],
        ]
    )

    im = ax6.imshow(corr_matrix, cmap="RdYlGn", vmin=-1, vmax=1, aspect="auto")
    ax6.set_xticks(range(len(criteria)))
    ax6.set_xticklabels([criteria_display[c].replace(" ", "\n") for c in criteria], fontsize=8)
    ax6.set_yticks([0, 1])
    ax6.set_yticklabels(["Your Qs", "Anki Qs"])
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
