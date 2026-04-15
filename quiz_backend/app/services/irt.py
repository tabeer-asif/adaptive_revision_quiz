# app/services/irt.py

import math
from fsrs import Rating
from rapidfuzz import fuzz

AVG_RESPONSE_TIMES = {
    "MCQ": 10.0,
    "MULTI_MCQ": 15.0,
    "NUMERIC": 20.0,
    "SHORT": 15.0,
    "OPEN": 30.0,
}

def irt_prob_2pl(theta: float, a: float, b: float) -> float:
    try:
        return 1 / (1 + math.exp(-a * (theta - b)))
    except OverflowError:
        return 1.0 if theta > b else 0.0

def irt_prob_3pl(theta: float, a: float, b: float, c: float) -> float:
    try:
        return c + (1 - c) / (1 + math.exp(-a * (theta - b)))
    except OverflowError:
        return 1.0 if theta > b else c

def update_theta_2pl(theta, a, b, response, learning_rate=0.3) -> float:
    p = irt_prob_2pl(theta, a, b)  # your IRT model
    # response = 1 (correct) or 0 (incorrect)
    delta = learning_rate * a * (response - p)
    return theta + delta

def update_theta_3pl(theta, a, b, c, response, lr=0.3) -> float:
    if c is None:
        c = 0.25 # default guessing parameter if not provided
    p = irt_prob_3pl(theta, a, b, c)
    # 3PL gradient is slightly different — weight by (P - c)
    weight = (p - c) / (p * (1 - c) +  1e-9) # epsilon to avoid div by zero
    delta = lr * a * weight * (response - p)
    return theta + delta

def default_grm_thresholds(b: float) -> list[float]:
    """
    Generate default GRM thresholds centred on b.
    For 3 categories (0, 1, 2) we need 2 thresholds.
    Spread them ±0.5 around the central difficulty.
    """
    return [round(b - 0.5, 2), round(b + 0.5, 2)]

# Examples:
# Easy question   b=-1.0 → thresholds = [-1.5, -0.5]
# Medium question b= 0.0 → thresholds = [-0.5,  0.5]
# Hard question   b= 1.0 → thresholds = [ 0.5,  1.5]

def grm_probabilities(theta, a, b_thresholds) -> list[float]:
    """
    a: discrimination
    b_thresholds: list of difficulty thresholds [b1, b2, b3]
                  e.g. [threshold for >0%, >50%, 100% correct]
    Returns probability of each category
    """
    b_thresholds = sorted(b_thresholds)  # enforce ordering
    # Cumulative probabilities P*(θ) for each threshold
    cum_probs = [1.0]  # P(score >= 0) = 1 always
    for b_k in b_thresholds:
        try:
            p_star = 1 / (1 + math.exp(-a * (theta - b_k)))
        except OverflowError:
            p_star = 1.0 if theta > b_k else 0.0
        cum_probs.append(p_star)
    cum_probs.append(0.0)  # P(score >= max+1) = 0 always
    
    # Category probabilities = difference between adjacent cumulative probs
    category_probs = [
        cum_probs[k] - cum_probs[k+1]
        for k in range(len(cum_probs) - 1)
    ]
    return category_probs


def update_theta_grm(theta, a, b_thresholds, observed_category, lr=0.3) -> float:
    probs = grm_probabilities(theta, a, b_thresholds)
    expected = sum(k * p for k, p in enumerate(probs))
    # Gradient approximation
    delta = lr * a * (observed_category - expected)
    return theta + delta

def score_mcq(selected_key, db_answer) -> float:
    correct_key = str(db_answer).strip() if db_answer is not None else ""
    return 1.0 if selected_key == correct_key else 0.0

def score_multi_mcq(selected_set, correct_set) -> float:
    n_correct = len(selected_set & correct_set)
    n_wrong = len(selected_set - correct_set)
    n_total = len(correct_set)
    if n_total == 0:
        return 0.0
    return max(0.0, (n_correct - n_wrong) / n_total)
    

def score_numeric(user_answer, correct_answer, tolerance) -> float:
    return 1.0 if abs(user_answer - correct_answer) <= tolerance else 0.0
    # questions with tighter tolerance are effectively harder, so will have higher effective b

def score_short(submitted_text: str, keywords: list[str], model_answer: str = "") -> tuple[bool, float]:
    # If no keywords and no model answer exist, accept the response.
    if not keywords and not model_answer:
        return True, 1.0

    if not keywords:
        is_exact_match = submitted_text == model_answer
        return is_exact_match, 1.0 if is_exact_match else 0.0

    matched = 0
    for keyword in keywords:
        # Single-word keywords use a stricter threshold to reduce false positives.
        # Multi-word phrases keep a lower threshold where partial matching helps.
        keyword_threshold = 90 if len(keyword.split()) == 1 else 80
        ratio = max(
            fuzz.partial_ratio(keyword, submitted_text),
            fuzz.token_sort_ratio(keyword, submitted_text),
        )
        if ratio >= keyword_threshold:
            matched += 1

    score = matched / len(keywords)
    # Require matching at least 60% of keywords to pass SHORT answers.
    return score >= 0.6, score



def select_best_question_per_topic(theta_map, questions, target=None):
    best_q = None
    best_fisher = float("-inf")   # for calibration mode
    best_dist = float("inf")      # for learning mode

    for q in questions:
        topic_theta = theta_map.get(q["topic_id"], 0.0)
        a = q.get("irt_a") or 1.0
        b = q.get("irt_b") or 0.0
        c = q.get("irt_c")

        if q["type"] == "MCQ" and c is not None:
            p = irt_prob_3pl(topic_theta, a, b, c)
        else:
            p = irt_prob_2pl(topic_theta, a, b)

        if target is None:
            # Calibration mode — maximise Fisher Information
            fisher = (a ** 2) * p * (1 - p)
            if fisher > best_fisher:
                best_fisher = fisher
                best_q = q
        else:
            # Learning mode — minimise distance from target probability
            dist = abs(p - target)
            if dist < best_dist:
                best_dist = dist
                best_q = q

    return best_q
'''
Optional / advanced things not yet included
Updating a and b automatically
3PL / guessing parameter (c)
For MCQs, accounts for chance of guessing correctly
Can improve accuracy, but not required for a simple adaptive engine
Using IRT to compute expected information
You can pick the question that maximizes learning (information function)
Right now we just pick closest to P=0.7
Integration with FSRS for scheduling
Right now FSRS is separate → you could make IRT + FSRS fully joint (update interval based on ability)
Optional for first implementation
'''


def get_fsrs_rating(question_type: str, correct: bool, response_time: float, score: float | None = None) -> Rating:
    avg_response_time = AVG_RESPONSE_TIMES.get(question_type, 10.0)
    if question_type == "MULTI_MCQ" and score is not None:
        # For multi-MCQ, use partial credit score to determine rating
        if score == 1.0:
            return Rating.Easy if response_time < avg_response_time * 0.6 else Rating.Good
        elif score >= 0.5:
            return Rating.Hard
        else:
            return Rating.Again
    
    if not correct:
        return Rating.Again
    if response_time > avg_response_time * 1.5: # correct but slow — struggled
        return Rating.Hard
    elif response_time < avg_response_time * 0.6: # correct and fast — well known
        return Rating.Easy
    return Rating.Good # correct, normal time