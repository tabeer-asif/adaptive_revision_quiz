from app.services import irt


"""Edge-case tests for numeric overflow and fallback behavior in IRT helpers."""

# Convention: tests below follow Arrange / Act / Assert flow.


def test_irt_overflow_and_defaults(monkeypatch):
    # Overflow paths should return bounded probability fallbacks.
    def overflow(_):
        raise OverflowError()

    monkeypatch.setattr(irt.math, "exp", overflow)

    assert irt.irt_prob_2pl(theta=10.0, a=1.0, b=0.0) == 1.0
    assert irt.irt_prob_2pl(theta=-10.0, a=1.0, b=0.0) == 0.0

    assert irt.irt_prob_3pl(theta=10.0, a=1.0, b=0.0, c=0.25) == 1.0
    assert irt.irt_prob_3pl(theta=-10.0, a=1.0, b=0.0, c=0.25) == 0.25


def test_update_theta_3pl_with_none_c_and_grm_overflow(monkeypatch):
    # `c=None` should use default guessing; GRM overflow path should still return probabilities.
    out = irt.update_theta_3pl(theta=0.0, a=1.0, b=0.0, c=None, response=1)
    assert out > 0

    def overflow(_):
        raise OverflowError()

    monkeypatch.setattr(irt.math, "exp", overflow)
    probs = irt.grm_probabilities(theta=10.0, a=1.0, b_thresholds=[-0.5, 0.5])
    assert len(probs) == 3


def test_score_multi_mcq_zero_total():
    # Empty correct-set path should return 0 score, not divide-by-zero.
    assert irt.score_multi_mcq({"A"}, set()) == 0.0
