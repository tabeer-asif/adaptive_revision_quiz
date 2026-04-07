# app/services/irt.py

import math

def irt_probability(theta, a, b):
    return 1 / (1 + math.exp(-a * (theta - b)))

def select_best_question(theta, questions, target=0.7):
    best_q = None
    best_diff = float("inf")

    for q in questions:
        a = q.get("irt_a", 1)
        b = q.get("irt_b", 0)

        p = irt_probability(theta, a, b)
        diff = abs(p - target)

        if diff < best_diff:
            best_diff = diff
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