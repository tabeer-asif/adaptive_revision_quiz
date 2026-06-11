# app/services/irt.py

import math
import re
from typing import Any, Dict, List, Tuple

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

def default_grm_thresholds(b: float) -> list[float]:
    """
    Generate default GRM thresholds centred on b.
    For 3 categories (0, 1, 2) we need 2 thresholds.
    Spread them ±0.5 around the central difficulty.
    """
    return [round(b - 0.5, 2), round(b + 0.5, 2)]


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


THETA_GRID = [-4.0 + (8.0 * i / 40.0) for i in range(41)]
PRIOR_WEIGHTS = [math.exp(-0.5 * theta ** 2) for theta in THETA_GRID]
_PRIOR_TOTAL = sum(PRIOR_WEIGHTS) or 1.0
PRIOR_WEIGHTS = [weight / _PRIOR_TOTAL for weight in PRIOR_WEIGHTS]


def _clean_response_times(response_times: list[float] | None) -> list[float]:
    values = []
    for value in response_times or []:
        if isinstance(value, (int, float)) and value > 0:
            values.append(float(value))
    return sorted(values)


def _percentile_cont(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])

    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return float(ordered[lower_index])

    lower_value = ordered[lower_index]
    upper_value = ordered[upper_index]
    return float(lower_value + (upper_value - lower_value) * (position - lower_index))


def _remove_iqr_outliers(values: list[float]) -> list[float]:
    if len(values) < 4:
        return values

    q1 = _percentile_cont(values, 0.25)
    q3 = _percentile_cont(values, 0.75)
    if q1 is None or q3 is None:
        return values

    iqr = q3 - q1
    if iqr <= 0:
        return values

    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    filtered = [value for value in values if lower_bound <= value <= upper_bound]
    return filtered or values


def _quartile_thresholds(response_times: list[float] | None) -> tuple[float | None, float | None]:
    values = _clean_response_times(response_times)
    values = _remove_iqr_outliers(values)

    if len(values) < 10:
        return None, None

    return _percentile_cont(values, 0.25), _percentile_cont(values, 0.75)


def _fallback_thresholds(question_type: str) -> tuple[float, float]:
    mean_response_time = AVG_RESPONSE_TIMES.get(question_type, 10.0)
    return mean_response_time * 0.7, mean_response_time * 1.3


def resolve_response_time_thresholds(
    question_type: str,
    question_response_times: list[float] | None = None,
    type_response_times: list[float] | None = None,
) -> tuple[float, float]:
    q1, q3 = _quartile_thresholds(question_response_times)
    if q1 is not None and q3 is not None:
        return q1, q3

    q1, q3 = _quartile_thresholds(type_response_times)
    if q1 is not None and q3 is not None:
        return q1, q3

    return _fallback_thresholds(question_type)


def grm_category_probability(theta: float, a: float, b_thresholds: List[float], category: int) -> float:
    thresholds = sorted(b_thresholds or [])
    if not thresholds:
        return irt_prob_2pl(theta, a, 0.0)

    category = max(0, min(int(category), len(thresholds)))

    def cumulative(b_value: float) -> float:
        return irt_prob_2pl(theta, a, b_value)

    if category == 0:
        return 1.0 - cumulative(thresholds[0])
    if category == len(thresholds):
        return cumulative(thresholds[-1])

    return cumulative(thresholds[category - 1]) - cumulative(thresholds[category])


def compute_log_likelihood(responses: List[Dict[str, Any]], theta_grid: List[float]) -> List[float]:
    log_likelihood = [0.0 for _ in theta_grid]

    for response in responses:
        item_type = response.get("item_type")
        a = float(response.get("a") or 1.0)

        for index, theta in enumerate(theta_grid):
            if item_type == "3pl":
                p = irt_prob_3pl(theta, a, float(response.get("b") or 0.0), float(response.get("c") or 0.25))
                p = min(max(p, 1e-10), 1 - 1e-10)
                log_likelihood[index] += math.log(p) if response.get("correct") else math.log(1.0 - p)
            elif item_type == "2pl":
                p = irt_prob_2pl(theta, a, float(response.get("b") or 0.0))
                p = min(max(p, 1e-10), 1 - 1e-10)
                log_likelihood[index] += math.log(p) if response.get("correct") else math.log(1.0 - p)
            elif item_type == "grm":
                p = grm_category_probability(theta, a, list(response.get("b_list") or []), int(response.get("score") or 0))
                p = min(max(p, 1e-10), 1.0)
                log_likelihood[index] += math.log(p)

    return log_likelihood


def eap_estimate(
    responses: List[Dict[str, Any]],
    theta_grid: List[float] = THETA_GRID,
    prior_weights: List[float] = PRIOR_WEIGHTS,
) -> Tuple[float, float]:
    if not responses:
        return 0.0, 1.0

    log_lik = compute_log_likelihood(responses, theta_grid)
    max_log_lik = max(log_lik)
    likelihood = [math.exp(value - max_log_lik) for value in log_lik]

    posterior_unnorm = [like * prior for like, prior in zip(likelihood, prior_weights)]
    total = sum(posterior_unnorm)
    if total < 1e-300:
        return 0.0, 1.0

    posterior = [value / total for value in posterior_unnorm]
    theta_hat = sum(theta * weight for theta, weight in zip(theta_grid, posterior))
    variance = sum(((theta - theta_hat) ** 2) * weight for theta, weight in zip(theta_grid, posterior))
    posterior_sd = math.sqrt(max(variance, 0.0))

    return float(theta_hat), float(posterior_sd)

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


def _normalize_short_alias(value: str) -> str:
    normalized = re.sub(r"[-_/]+", " ", str(value).strip().lower())
    normalized = re.sub(r"[^a-z0-9\s]", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _tokenize_short_alias(value: str) -> list[str]:
    return [token for token in _normalize_short_alias(value).split(" ") if token]


def _short_alias_matches(alias: str, submitted_tokens: set[str]) -> bool:
    alias_tokens = _tokenize_short_alias(alias)
    if not alias_tokens:
        return False
    return set(alias_tokens).issubset(submitted_tokens)


def _short_alias_near_match(alias: str, submitted_text: str) -> bool:
    normalized_alias = _normalize_short_alias(alias)
    normalized_submitted = _normalize_short_alias(submitted_text)
    if not normalized_alias or not normalized_submitted:
        return False

    if len(_tokenize_short_alias(alias)) == 1:
        return fuzz.ratio(normalized_alias, normalized_submitted) >= 92

    return fuzz.token_sort_ratio(normalized_alias, normalized_submitted) >= 92

def score_short(submitted_text: str, keywords: list[str], model_answer: str = "") -> tuple[bool, float]:
    submitted_text = _normalize_short_alias(submitted_text)
    model_answer = _normalize_short_alias(model_answer)
    keywords = list(dict.fromkeys(
        _normalize_short_alias(keyword) for keyword in (keywords or []) if _normalize_short_alias(keyword)
    ))
    submitted_tokens = set(_tokenize_short_alias(submitted_text))

    # Exact alias coverage or a very close typo should count as correct for the canonical answer.
    if model_answer:
        if _short_alias_matches(model_answer, submitted_tokens) or _short_alias_near_match(model_answer, submitted_text):
            return True, 1.0

    # If no keywords and no model answer exist, accept the response.
    if not keywords and not model_answer:
        return True, 1.0

    if not keywords:
        is_exact_match = submitted_text == model_answer
        return is_exact_match, 1.0 if is_exact_match else 0.0

    matched = sum(
        1 for keyword in keywords
        if _short_alias_matches(keyword, submitted_tokens) or _short_alias_near_match(keyword, submitted_text)
    )

    # Keywords are accepted aliases, so matching any one should pass with full credit.
    correct = matched >= 1
    return correct, 1.0 if correct else 0.0


def grm_fisher_information(theta: float, a: float, b_thresholds: list[float]) -> float:
    thresholds = sorted(b_thresholds or [])
    if not thresholds:
        p = irt_prob_2pl(theta, a, 0.0)
        return (a ** 2) * p * (1 - p)

    # Cumulative boundary probabilities
    cum_probs = [1.0]
    for b_k in thresholds:
        try:
            p_star = 1 / (1 + math.exp(-a * (theta - b_k)))
        except OverflowError:
            p_star = 1.0 if theta > b_k else 0.0
        cum_probs.append(p_star)
    cum_probs.append(0.0)

    # Derivatives of cumulative probs
    cum_derivs = [a * p * (1 - p) for p in cum_probs]

    total = 0.0
    for k in range(len(thresholds) + 1):
        p_k = cum_probs[k] - cum_probs[k + 1]
        dp_k = cum_derivs[k] - cum_derivs[k + 1]
        if p_k > 1e-10:
            total += (dp_k ** 2) / p_k
    return total


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
            if q["type"] == "MCQ" and c is not None and c < 1.0:
                p_clipped = max(min(p, 1 - 1e-10), 1e-10)
                fisher = (a ** 2) * (((p_clipped - c) ** 2) / ((1 - c) ** 2)) * ((1 - p_clipped) / p_clipped)
            elif q["type"] == "MULTI_MCQ":
                thresholds = q.get("irt_thresholds") or default_grm_thresholds(b)
                fisher = grm_fisher_information(topic_theta, a, thresholds)
            else:
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

def get_fsrs_rating(
    question_type: str,
    correct: bool,
    response_time: float,
    score: float | None = None,
    question_response_times: list[float] | None = None,
    type_response_times: list[float] | None = None,
) -> Rating:
    q1, q3 = resolve_response_time_thresholds(question_type, question_response_times, type_response_times)

    if question_type == "MULTI_MCQ" and score is not None:
        if score == 1.0:
            if response_time < q1:
                return Rating.Easy
            if response_time > q3:
                return Rating.Hard
            return Rating.Good
        elif score >= 0.5:
            return Rating.Hard
        else:
            return Rating.Again
    
    if not correct:
        return Rating.Again
    if response_time > q3:
        return Rating.Hard
    elif response_time < q1:
        return Rating.Easy
    return Rating.Good