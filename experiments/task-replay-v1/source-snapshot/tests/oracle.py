"""Literal scalar oracle: no production imports and no torch math.

Every node is summarized directly from original keys, independently of the
production recursive merge. Traversal eligibility is decided by span coverage.
"""

import math


def dot(a: list[float], b: list[float]) -> float:
    return math.fsum(x * y for x, y in zip(a, b, strict=True))


def lse(scores: list[float]) -> float:
    maximum = max(scores)
    return maximum + math.log(math.fsum(math.exp(x - maximum) for x in scores))


def summary(keys: list[list[float]], reference: list[float]) -> tuple[list[float], float]:
    scores = [dot(reference, k) / math.sqrt(len(reference)) for k in keys]
    log_total = lse(scores)
    weights = [math.exp(s - log_total) for s in scores]
    mean = [
        math.fsum(w * k[j] for w, k in zip(weights, keys, strict=True))
        for j in range(len(reference))
    ]
    return mean, log_total - dot(reference, mean) / math.sqrt(len(reference))


def attention(
    query: list[float], keys: list[list[float]], values: list[list[float]], ids: tuple[int, ...]
) -> list[float]:
    scores = [dot(query, keys[i]) / math.sqrt(len(query)) for i in ids]
    total = lse(scores)
    weights = [math.exp(s - total) for s in scores]
    return [
        math.fsum(w * values[i][j] for w, i in zip(weights, ids, strict=True))
        for j in range(len(values[0]))
    ]


def route(
    query: list[float],
    keys: list[list[float]],
    references: list[list[float]],
    chunk: int,
    depth: int,
    visible: int,
    p: float,
) -> tuple[tuple[int, ...], list[tuple[int, tuple[int, ...], tuple[int, ...]]]]:
    selected_spans: list[tuple[int, int]] = []
    chosen_leaf_spans: list[tuple[int, int]] = []
    steps = []
    for level in reversed(range(1, depth + 1)):
        span = chunk**level
        candidates = []
        for start in range(1, visible, span):
            end = start + span
            if end > visible:
                continue
            parent_span = span * chunk
            parent_start = 1 + (start - 1) // parent_span * parent_span
            has_complete_parent = level < depth and parent_start + parent_span <= visible
            descended = any(a <= start and end <= b for a, b in selected_spans)
            if has_complete_parent and not descended:
                continue
            scores = []
            for reference in references:
                mean, bias = summary(keys[start:end], reference)
                scores.append(dot(query, mean) / math.sqrt(len(query)) + bias)
            candidates.append(((start - 1) // span, start, end, max(scores)))
        if not candidates:
            selected_spans = []
            continue
        ordered = sorted(candidates, key=lambda item: (-item[3], item[0]))
        if p == 1.0:
            chosen = ordered
        else:
            partition = lse([item[3] for item in ordered])
            chosen = []
            mass = 0.0
            for item in ordered:
                chosen.append(item)
                mass += math.exp(item[3] - partition)
                if mass >= p:
                    break
        selected_spans = [(item[1], item[2]) for item in chosen]
        steps.append(
            (level, tuple(item[0] for item in candidates), tuple(item[0] for item in chosen))
        )
        if level == 1:
            chosen_leaf_spans = selected_spans
    # Determine incomplete final chunk by scanning original eligible positions.
    selected = {0}
    for start, end in chosen_leaf_spans:
        selected.update(range(start, end))
    for start in range(1, visible, chunk):
        if start + chunk > visible:
            selected.update(range(start, visible))
    return tuple(sorted(selected)), steps
