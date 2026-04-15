import math

from fsrs import Rating

from app.services import irt


def test_irt_probabilities_and_updates():
    p2 = irt.irt_prob_2pl(theta=0.0, a=1.0, b=0.0)
    assert 0.49 < p2 < 0.51

    p3 = irt.irt_prob_3pl(theta=0.0, a=1.0, b=0.0, c=0.25)
    assert 0.62 < p3 < 0.63

    t2 = irt.update_theta_2pl(theta=0.0, a=1.0, b=0.0, response=1)
    t3 = irt.update_theta_3pl(theta=0.0, a=1.0, b=0.0, c=0.25, response=1)
    assert t2 > 0
    assert t3 > 0


def test_default_thresholds_and_grm():
    th = irt.default_grm_thresholds(0.0)
    assert th == [-0.5, 0.5]

    probs = irt.grm_probabilities(theta=0.0, a=1.0, b_thresholds=[-0.5, 0.5])
    assert math.isclose(sum(probs), 1.0, rel_tol=1e-6)

    updated = irt.update_theta_grm(theta=0.0, a=1.0, b_thresholds=[-0.5, 0.5], observed_category=2)
    assert updated > 0


def test_scoring_helpers():
    assert irt.score_mcq("A", "A") == 1.0
    assert irt.score_mcq("A", "B") == 0.0

    assert irt.score_multi_mcq({"A", "B"}, {"A", "C"}) == 0.0
    assert irt.score_multi_mcq({"A", "C"}, {"A", "C"}) == 1.0

    assert irt.score_numeric(10.1, 10.0, 0.2) == 1.0
    assert irt.score_numeric(10.5, 10.0, 0.2) == 0.0


def test_score_short_paths():
    ok, score = irt.score_short("answer", [], "")
    assert ok is True and score == 1.0

    ok, score = irt.score_short("hello", [], "hello")
    assert ok is True and score == 1.0

    ok, score = irt.score_short("hello", [], "world")
    assert ok is False and score == 0.0

    ok, score = irt.score_short("photosynthesis process", ["photosynthesis", "process"], "")
    assert ok is True
    assert score >= 0.6


def test_select_best_question_and_rating_paths():
    questions = [
        {"id": 1, "topic_id": 1, "type": "MCQ", "irt_a": 1.0, "irt_b": 0.0, "irt_c": 0.25},
        {"id": 2, "topic_id": 1, "type": "NUMERIC", "irt_a": 1.0, "irt_b": 1.5, "irt_c": None},
    ]
    theta_map = {1: 0.0}

    q_cal = irt.select_best_question_per_topic(theta_map, questions, target=None)
    q_learn = irt.select_best_question_per_topic(theta_map, questions, target=0.7)

    assert q_cal is not None
    assert q_learn is not None

    assert irt.get_fsrs_rating("MCQ", False, 8.0) == Rating.Again
    assert irt.get_fsrs_rating("MCQ", True, 20.0) == Rating.Hard
    assert irt.get_fsrs_rating("MCQ", True, 2.0) == Rating.Easy
    assert irt.get_fsrs_rating("MCQ", True, 8.0) == Rating.Good

    assert irt.get_fsrs_rating("MULTI_MCQ", True, 6.0, score=1.0) in (Rating.Easy, Rating.Good)
    assert irt.get_fsrs_rating("MULTI_MCQ", True, 10.0, score=0.6) == Rating.Hard
    assert irt.get_fsrs_rating("MULTI_MCQ", False, 10.0, score=0.2) == Rating.Again
