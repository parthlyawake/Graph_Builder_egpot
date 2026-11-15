"""Compact source-audited flow and call fixture (not a realistic-repository sample)."""

def triple(n):
    return n * 3


def compute(x):
    result = triple(x)
    return result


def plus_one(n):
    return n + 1


def run(y):
    answer = plus_one(y)
    return answer
