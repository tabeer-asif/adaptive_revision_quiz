from app.services import irt


def test_irt_overflow_and_defaults(monkeypatch):
    def overflow(_):
        raise OverflowError()

    monkeypatch.setattr(irt.math, "exp", overflow)

    assert irt.irt_prob_2pl(theta=10.0, a=1.0, b=0.0) == 1.0
    assert irt.irt_prob_2pl(theta=-10.0, a=1.0, b=0.0) == 0.0

    assert irt.irt_prob_3pl(theta=10.0, a=1.0, b=0.0, c=0.25) == 1.0
    assert irt.irt_prob_3pl(theta=-10.0, a=1.0, b=0.0, c=0.25) == 0.25


def test_update_theta_3pl_with_none_c_and_grm_overflow(monkeypatch):
    out = irt.update_theta_3pl(theta=0.0, a=1.0, b=0.0, c=None, response=1)
    assert out > 0

    def overflow(_):
        raise OverflowError()

    monkeypatch.setattr(irt.math, "exp", overflow)
    probs = irt.grm_probabilities(theta=10.0, a=1.0, b_thresholds=[-0.5, 0.5])
    assert len(probs) == 3


def test_score_multi_mcq_zero_total():
    assert irt.score_multi_mcq({"A"}, set()) == 0.0
