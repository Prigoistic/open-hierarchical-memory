"""Independent progress-state, numerical-route and fallback-attribution audit."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import sys
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_complex_tasks import (
    audit_minigrid,
    digest,
    mini_feature,
    mini_queries,
    read_json,
    require,
)  # noqa: E402
from scripts.audit_dependency_memory import (
    WORK_KEYS,
    ReferenceGraph,
    adjacent,
    audit_dependency_episode,
    audit_mask,
    audit_planner_view,
    navigable,
    point,
)  # noqa: E402

REPAIR_KEYS = (
    "payload_novelty_checks",
    "history_pose_checks",
    "cue_vectors_created",
    "cue_query_rows",
    "source_candidate_facts",
    "requery_reads",
    "widened_reads",
    "graph_fallback_reads",
    "graph_fallback_episodes",
    "novel_information_resets",
    "stage_transitions",
    "trace_index_ids",
    "trace_node_spans",
)
SOURCE_KEYS = (
    "scored_nodes",
    "summary_dot_products",
    "raw_attention_pairs",
    "rerank_pairs",
    "exact_score_pairs",
    "returned_facts",
    "routing_passes",
    "full_candidate_fallbacks",
)


def close(actual: Any, expected: Any, label: str) -> None:
    a, b = np.asarray(actual, dtype=float), np.asarray(expected, dtype=float)
    require(
        a.shape == b.shape
        and bool(np.isfinite(a).all())
        and bool(np.allclose(a, b, rtol=1e-9, atol=1e-9)),
        label,
    )


def position_vector(p: tuple[int, int] | list[int]) -> list[float]:
    return [
        2 * f(k * math.pi * coordinate / 128)
        for coordinate in p
        for k in (1, 2, 4)
        for f in (math.cos, math.sin)
    ]


class TreeOracle:
    """Independent NumPy affine/entropy tree; cache only the last head snapshot."""

    def __init__(self) -> None:
        self.identity = ""
        self.keys: Any = None
        self.values: Any = None
        self.levels: list[tuple[Any, Any]] = []
        self.spans: list[dict[str, int]] = []
        self.snapshot = ""

    def update(self, heads: list[dict[str, Any]]) -> None:
        identity = digest(heads)
        if identity == self.identity:
            return
        self.identity = identity
        self.keys = np.asarray([[0.0] * 30, *(mini_feature(f) for f in heads)])
        self.values = np.asarray(
            [[0.0] * 3, *[[f[k] for k in ("object", "color", "state")] for f in heads]]
        )
        refs = np.zeros((8, 30), dtype=np.float64)
        for i, obj in enumerate((8, 5, 4, 6)):
            refs[i, 12 + obj] = 8.0
        refs[4, 29] = 8.0
        for i, p in enumerate(((-16, 0), (16, 0), (0, 16)), 5):
            refs[i, :12] = position_vector(p)
        h = hashlib.sha256(
            json.dumps(
                {
                    "formula": "nope-v1",
                    "config": {
                        "chunk_size": 4,
                        "depth": 3,
                        "max_nodes": 100000,
                        "max_snapshot_tensor_bytes": 134217728,
                    },
                },
                sort_keys=True,
            ).encode()
        )
        for array in (self.keys[None, None], self.values[None, None], refs[None]):
            h.update(json.dumps(list(array.shape)).encode())
            h.update(array.tobytes())
        self.snapshot = h.hexdigest()
        self.levels, self.spans = [], []
        for level in range(1, 4):
            means, biases = [], []
            for index in range(len(heads) // 4**level):
                if level == 1:
                    raw = self.keys[1 + index * 4 : 1 + (index + 1) * 4]
                    logits = refs @ raw.T / math.sqrt(30)
                    logw = logits - np.max(logits, axis=1, keepdims=True)
                    logw -= np.log(np.exp(logw).sum(axis=1, keepdims=True))
                    weights = np.exp(logw)
                    mean = weights @ raw
                    bias = -(weights * logw).sum(axis=1)
                else:
                    cm, cb = self.levels[-1]
                    m, b = cm[index * 4 : (index + 1) * 4], cb[index * 4 : (index + 1) * 4]
                    logits = np.einsum("crd,rd->cr", m, refs) / math.sqrt(30) + b
                    logw = logits - np.max(logits, axis=0, keepdims=True)
                    logw -= np.log(np.exp(logw).sum(axis=0, keepdims=True))
                    weights = np.exp(logw)
                    mean = (weights[:, :, None] * m).sum(axis=0)
                    bias = (weights * (b - logw)).sum(axis=0)
                means.append(mean)
                biases.append(bias)
                self.spans.append(
                    {
                        "level": level,
                        "index": index,
                        "start": 1 + index * 4**level,
                        "stop": 1 + (index + 1) * 4**level,
                    }
                )
            self.levels.append((np.asarray(means), np.asarray(biases)))

    def route(
        self, route: dict[str, Any], query: list[float], p: float, heads: list[dict[str, Any]]
    ) -> tuple[int, int]:
        require(
            route["index_fact_ids"] == [f["id"] for f in heads]
            and route["node_spans"] == self.spans
            and route["snapshot_id"] == self.snapshot,
            "false core index/span/snapshot identity",
        )
        require(
            route["chunk_size"] == 4
            and route["depth"] == 3
            and route["logical_key_count"] == len(heads) + 1
            and route["used"] is True
            and route["decision_source"] == "zha_adaptive",
            "false routing configuration/use attribution",
        )
        counts = [len(heads) // 4**level for level in range(1, 4)]
        parents: list[int] = []
        leaves: list[int] = []
        trace = iter(route["steps"])
        scored = 0
        for level in (3, 2, 1):
            parented = counts[level] * 4 if level < 3 else 0
            candidates = sorted(
                {i for parent in parents for i in range(parent * 4, parent * 4 + 4)}
                | set(range(parented, counts[level - 1]))
            )
            if not candidates:
                parents = []
                continue
            step: dict[str, Any] = next(trace, {})
            require(bool(step), "missing actual branch level")
            require(
                step["level"] == level and step["candidates"] == candidates,
                "false branch candidate topology",
            )
            means, biases = self.levels[level - 1]
            scores = (
                np.einsum("nrd,d->nr", means[candidates], np.asarray(query)) / math.sqrt(30)
                + biases[candidates]
            ).max(axis=1)
            close(step["scores"], scores, "false affine branch scores")
            ordered = sorted(candidates, key=lambda i: (-step["scores"][candidates.index(i)], i))
            parents = step["selected"]
            require(
                bool(parents) and parents == ordered[: len(parents)], "false top-p branch prefix"
            )
            weights = np.exp(
                np.asarray([step["scores"][candidates.index(i)] for i in ordered])
                - max(step["scores"])
            )
            weights /= weights.sum()
            require(
                (p == 1 and len(parents) == len(candidates))
                or (
                    p < 1
                    and float(weights[: len(parents)].sum()) >= p - 1e-12
                    and float(weights[: len(parents) - 1].sum()) <= p + 1e-12
                ),
                "top-p threshold violated",
            )
            scored += len(candidates)
            if level == 1:
                leaves = parents
        require(next(trace, None) is None, "invented extra branch level")
        remainder = 1 + len(heads) // 4 * 4
        ids = sorted(
            {
                0,
                *range(remainder, len(heads) + 1),
                *(i for leaf in leaves for i in range(1 + leaf * 4, 1 + (leaf + 1) * 4)),
            }
        )
        require(
            route["selected_logical_ids"] == ids
            and route["selected_fact_ids"] == [heads[i - 1]["id"] for i in ids if i],
            "branch decision does not match original facts",
        )
        logits = self.keys[ids] @ np.asarray(query) / math.sqrt(30)
        weights = np.exp(logits - logits.max())
        weights /= weights.sum()
        close(
            route["attention_output"],
            weights @ self.values[ids],
            "false selected numerical attention output",
        )
        return scored, len(ids)


def prefix_projection(episode: dict[str, Any]) -> dict[str, Any]:
    """Neutral prefix/transition check, not a claim that full memory acted."""
    projected = {**episode, "reader": "full", "trajectory": [], "costs": dict(episode["costs"])}
    heads: dict[tuple[int, int], dict[str, Any]] = {}
    returned = 0
    for row in episode["trajectory"]:
        for f in row["new_facts"]:
            heads[point(f)] = f
        current = sorted(heads.values(), key=lambda f: f["id"])
        returned += len(current)
        decision = {
            **row["decision"],
            "memory_ids": [f["id"] for f in current],
            "memory_facts": current,
            "route": [],
            "queries": mini_queries(row["decision"]["pose"], row["observation"]["mission"]),
            "work": dict(row["decision"]["work"]),
        }
        for name in SOURCE_KEYS:
            decision["work"][name] = returned if name == "returned_facts" else 0
        projected["trajectory"].append({**row, "decision": decision})
    for name in SOURCE_KEYS:
        projected["costs"][name] = returned if name == "returned_facts" else 0
    return projected


def audit_closure(row: dict[str, Any], heads: list[dict[str, Any]], work: dict[str, int]) -> None:
    decision = row["decision"]
    receipt = decision["dependency"]
    context = receipt["context"]
    expected_context = {
        "position": decision["pose"][:2],
        "direction": decision["pose"][2],
        "mission": row["observation"]["mission"],
        "inventory": decision["inventory"],
        "current_facts": decision["current_facts"],
        "step": row["step"],
    }
    require(context == expected_context, "repair context differs from observed information")
    by_id = {f["id"]: f for f in heads}
    current = {point(f): f for f in heads}
    require(
        receipt["source_head_ids"] == list(by_id)
        and receipt["source_head_hash"] == digest(heads)
        and receipt["source_version"] == max(by_id),
        "false repaired source identity",
    )
    require(
        set(receipt["seed_ids"]) <= set(by_id)
        and receipt["returned_ids"] == decision["memory_ids"]
        and decision["memory_facts"] == [by_id[i] for i in receipt["returned_ids"]],
        "foreign/stale repaired evidence",
    )
    require(len(receipt["returned_ids"]) <= 96, "raw planner budget exceeded")
    for k in (
        "head_scan_items",
        "head_hash_items",
        "source_head_scan_items",
        "coverage_bit_writes",
    ):
        work[k] = len(heads)
    work["current_context_lookups"] = len(context["current_facts"])
    work["output_facts"] = len(receipt["returned_ids"])
    work["coverage_binary_bytes"] = 512
    work["coverage_json_bytes"] = audit_mask(decision["coverage"], heads, max(by_id))
    graph = ReferenceGraph(heads, context, work)
    nominated = graph.nominate(receipt["seed_ids"])
    work["seed_role_scan_items"] += len(receipt["seed_ids"])
    cues = [
        by_id[i] for i in receipt["seed_ids"] if by_id[i]["cue"] and by_id[i]["object"] in (5, 6)
    ]
    cue = min(cues, key=lambda f: (f["first_seen"], f["id"])) if cues else None
    require(len(nominated) == len(receipt["bundles"]), "undeclared repair endpoint nomination")
    packed: set[int] = set()
    completed = 0
    for actual, (seed, kind) in zip(receipt["bundles"], nominated, strict=True):
        bundle = graph.bundle(
            seed, kind, (cue["id"],) if cue and kind == "matching_landmark" else ()
        )
        require(
            all(actual[k] == v for k, v in bundle.items()),
            "false repair path/key/sample/halo receipt",
        )
        candidate = packed | set(bundle["historical_ids"])
        work["packing_checks"] += len(candidate)
        if bundle["missing"]:
            status = "missing_prerequisite"
            work["bundles_missing"] += 1
        elif len(candidate) > 96:
            status = "overbudget"
            work["bundles_overbudget"] += 1
        else:
            status = "complete"
            completed += 1
            work["bundles_complete"] += 1
            work["bundles_packed"] += 1
            packed = candidate
        require(
            actual["status"] == status
            and actual["required_historical_count"] == len(bundle["historical_ids"])
            and actual["candidate_packed_count"] == len(candidate)
            and actual["omitted_ids"] == sorted(set(bundle["historical_ids"]) - packed),
            "false repair packing/completeness",
        )
    require(
        receipt["returned_ids"] == sorted(packed)
        and receipt["status"] == ("packed" if completed else "structural_rejection"),
        "repaired output differs from admitted whole supports",
    )
    effective = {point(f) for f in [*decision["memory_facts"], *context["current_facts"]]}
    residual = []
    for f in [*decision["memory_facts"], *context["current_facts"]]:
        if navigable(f):
            for p in adjacent(point(f)):
                work["residual_neighbor_checks"] += 1
                if p in current and p not in effective:
                    residual.append([*point(f), *p, current[p]["id"]])
    require(
        receipt["residual_known_neighbor_omissions"] == residual and receipt["work_delta"] == work,
        "false residual or structural cost accounting",
    )
    audit_planner_view(decision)


def effective_cues(base: list[list[float]], pose: list[int], stage: int) -> list[dict[str, Any]]:
    labels = ["Local position", "Mission objects", "Remembered sample"][: len(base)]
    vectors = [list(v) for v in base]
    if stage in (1, 2):
        for (dx, dy), label in zip(
            ((1, 0), (0, 1), (-1, 0), (0, -1)),
            ("Explore east", "Explore south", "Explore west", "Explore north"),
            strict=True,
        ):
            q = [0.0] * 30
            here = position_vector(pose[:2])
            there = position_vector((pose[0] + dx * 8, pose[1] + dy * 8))
            q[:12] = [a - 0.5 * b for a, b in zip(there, here, strict=True)]
            q[13] = q[15] = 6.0
            vectors.append(q)
            labels.append(label)
    return [
        {"label": name, "query_index": i, "vector": v, "used": stage != 3}
        for i, (name, v) in enumerate(zip(labels, vectors, strict=True))
    ]


def expand_wire(episode: dict[str, Any]) -> dict[str, Any]:
    if "routing_snapshots" not in episode:
        return episode
    bank = episode["routing_snapshots"]
    used = set()
    events = episode.get("routing_events", {})
    event_used: set[str] = set()
    if "routing_events" in episode:
        require(
            all(digest(event) == key for key, event in events.items()),
            "routing event bank hash mismatch",
        )
        require(
            episode["costs"]["wire_routing_event_count"] == len(events)
            and episode["costs"]["wire_routing_event_json_bytes"]
            == len(json.dumps(events, separators=(",", ":")).encode()),
            "routing event bank cost mismatch",
        )
    expected_fields = {
        "index_fact_ids",
        "node_spans",
        "chunk_size",
        "depth",
        "logical_key_count",
        "source_snapshot_label",
    }
    for key, layout in bank.items():
        require(
            set(layout) == expected_fields and digest(layout) == key,
            "routing bank layout identity/fields mismatch",
        )
    require(
        episode["costs"]["wire_routing_snapshot_count"] == len(bank)
        and episode["costs"]["wire_routing_snapshot_json_bytes"]
        == len(json.dumps(bank, separators=(",", ":")).encode()),
        "compact routing-bank cost mismatch",
    )
    result = {**episode, "trajectory": []}
    for row in episode["trajectory"]:
        d = dict(row["decision"])
        if "repair" in d:
            if "routing_events" in episode:
                decoded = []
                for ref in d["route"]:
                    require(
                        set(ref) == {"route_ref"} and ref["route_ref"] in events,
                        "missing/false routing event reference",
                    )
                    event_used.add(ref["route_ref"])
                    decoded.append(events[ref["route_ref"]])
                d["route"] = decoded
            repair = dict(d["repair"])
            routes = []
            refs = [
                {
                    "route_index": i,
                    "cue_label": repair["cues"][r["query_index"]]["label"],
                    "query_index": r["query_index"],
                    "attempt": r["attempt"],
                    "p": r["p"],
                    "snapshot_id": r["snapshot_id"],
                }
                for i, r in enumerate(d["route"])
            ]
            require(repair["attempts"] == refs, "compact attempt reference mismatch")
            for route in d["route"]:
                key = route["snapshot_id"]
                require(key in bank, "missing routing-bank layout")
                used.add(key)
                layout = bank[key]
                routes.append(
                    {
                        **route,
                        **{k: v for k, v in layout.items() if k != "source_snapshot_label"},
                        "snapshot_id": layout["source_snapshot_label"],
                    }
                )
            repair["attempts"] = [
                {**r, "cue_label": repair["cues"][r["query_index"]]["label"]} for r in routes
            ]
            d["repair"], d["route"] = repair, routes
            d["dependency"] = {**d["dependency"], "repair": repair}
        result["trajectory"].append({**row, "decision": d})
    require(used == set(bank), "unused/hidden routing-bank payload")
    require(event_used == set(events), "unused/hidden routing event payload")
    return result


def audit_episode(episode: dict[str, Any]) -> dict[str, Any]:
    if episode["reader"] in ("bundle_zha", "bundle_exact", "graph"):
        return {
            **audit_dependency_episode(episode),
            "repair_reads_checked": 0,
            "graph_reads": 0,
            "outcome_attribution": "unchanged_baseline",
        }
    episode = expand_wire(episode)
    require(
        episode["reader"] in ("progress_zha", "progress_exact", "cues_zha", "cues_exact")
        and episode["capacity"] == 96
        and episode["coverage_allowance_bytes"] == 512,
        "unknown repair variant/raw or mask budget",
    )
    prefix_result = audit_minigrid(prefix_projection(episode))
    heads: dict[tuple[int, int], dict[str, Any]] = {}
    payloads = set()
    history: deque[list[int]] = deque(maxlen=24)
    no_info = previous_stage = graph_reads = 0
    fallback = False
    cumulative = dict.fromkeys(REPAIR_KEYS, 0)
    source_work = dict.fromkeys(SOURCE_KEYS, 0)
    dependency_work = dict.fromkeys(WORK_KEYS, 0)
    oracle = TreeOracle()
    allows_graph = episode["reader"].startswith("progress_")
    for row in episode["trajectory"]:
        d = row["decision"]
        repair = d["repair"]
        receipt = d["dependency"]
        require(
            repair == receipt["repair"]
            and repair["variant"] == episode["reader"]
            and receipt["mode"] == episode["reader"],
            "repair metadata/variant mismatch",
        )
        delta = dict.fromkeys(REPAIR_KEYS, 0)
        novel = []
        for f in row["new_facts"]:
            heads[point(f)] = f
            delta["payload_novelty_checks"] += 1
            payload = tuple(f[k] for k in ("x", "y", "object", "color", "state", "cue"))
            if payload not in payloads:
                payloads.add(payload)
                novel.append(f["id"])
        require(
            len(payloads) <= len(episode["archive"]) <= 8192,
            "novelty/archive state exceeds declared bound",
        )
        ordered = sorted(heads.values(), key=lambda f: f["id"])
        base = mini_queries(d["pose"], row["observation"]["mission"])
        if novel:
            no_info = 0
            fallback = False
            delta["novel_information_resets"] += 1
        else:
            no_info += 1
        history.append(d["pose"])
        delta["history_pose_checks"] += len(history)
        repeats = sum(p == d["pose"] for p in history)
        repeated = repeats >= 2
        if novel:
            stage, trigger = 0, "new_observed_information"
        elif fallback:
            stage, trigger = 3, "continue_graph_until_information"
        elif allows_graph and (no_info >= 48 or (no_info >= 24 and repeated)):
            stage, trigger = (
                3,
                "hard_no_information_limit" if no_info >= 48 else "repeated_stall_after_widening",
            )
            fallback = True
            delta["graph_fallback_episodes"] += 1
        elif no_info >= 16:
            stage, trigger = 2, "candidate_budget_widening"
        elif no_info >= 8 and repeated:
            stage, trigger = 1, "repeated_pose_without_information"
        else:
            stage, trigger = 0, "ordinary_retrieval"
        if stage != previous_stage:
            delta["stage_transitions"] += 1
        previous_stage = stage
        cap = 192 if stage == 2 else 96
        source = "full" if stage == 3 else "zha_adaptive" if "zha" in episode["reader"] else "exact"
        expected = {
            "stage": stage,
            "trigger": trigger,
            "no_information_reads": no_info,
            "repeated_pose": repeated,
            "repeat_count": repeats,
            "history": list(history),
            "history_limit": 24,
            "novel_observed_ids": novel,
            "fallback_allowed": allows_graph,
            "fallback_active": stage == 3,
            "executed_source": "full_observed_graph" if stage == 3 else source,
            "candidate_budget": None if stage == 3 else cap,
            "raw_fact_budget": 96,
        }
        require(
            all(repair[k] == v for k, v in expected.items()),
            "fake novelty/history/stage/fallback evidence",
        )
        require(
            repair["context"] == receipt["context"]
            and repair["source_original_ids"] == receipt["seed_ids"]
            and receipt["seed_reader"] == source,
            "repair context or executed source mismatch",
        )
        cues = effective_cues(base, d["pose"], stage)
        for cue in cues:
            cue["decision_source"] = "full_observed_graph" if stage == 3 else source
        require(len(repair["cues"]) == len(cues), "cue count mismatch")
        for a, b in zip(repair["cues"], cues, strict=True):
            require(
                {k: v for k, v in a.items() if k != "vector"}
                == {k: v for k, v in b.items() if k != "vector"},
                "cue label/use attribution mismatch",
            )
            close(a["vector"], b["vector"], "cue vector contains unobserved/incorrect information")
        queries = [c["vector"] for c in cues]
        close(d["queries"], queries, "recorded effective queries mismatch")
        routes = d["route"]
        require(
            repair["attempts"]
            == [{**r, "cue_label": cues[r["query_index"]]["label"]} for r in routes],
            "invented or stale routing attempt",
        )
        keys = np.asarray([[0.0] * 30, *(mini_feature(f) for f in ordered)])
        candidates = list(range(1, len(ordered) + 1))
        work = dict.fromkeys(SOURCE_KEYS, 0)
        if source == "zha_adaptive":
            oracle.update(ordered)
            q_count = len(queries)
            require(
                len(routes) > 0 and len(routes) % q_count == 0 and len(routes) // q_count <= 5,
                "unbounded/missing hierarchy attempts",
            )
            passes = len(routes) // q_count
            work["routing_passes"] = passes
            union: set[int] = set()
            for j, route in enumerate(routes):
                attempt, q = divmod(j, q_count)
                p = (0.4, 0.6, 0.8, 0.95, 1.0)[attempt]
                require(
                    route["attempt"] == attempt and route["p"] == p and route["query_index"] == q,
                    "false adaptive repair schedule",
                )
                scored, pairs = oracle.route(route, queries[q], p, ordered)
                work["scored_nodes"] += scored
                work["summary_dot_products"] += scored * 8
                work["raw_attention_pairs"] += pairs
                union.update(i for i in route["selected_logical_ids"] if i)
                if q == 0 and p == 1:
                    work["full_candidate_fallbacks"] += 1
                if q == q_count - 1:
                    require(
                        (len(union) < min(cap, len(ordered)))
                        if attempt + 1 < passes
                        else (len(union) >= min(cap, len(ordered))),
                        "unjustified widening or premature repair stop",
                    )
            candidates = sorted(union)
            work["rerank_pairs"] = len(candidates) * len(queries)
        elif source == "exact":
            require(not routes, "exact repair invents hierarchy routes")
            work["exact_score_pairs"] = len(ordered) * len(queries)
        else:
            require(not routes, "graph fallback masquerades as a hierarchy decision")
        ids = receipt["seed_ids"]
        require(
            len(ids) == len(set(ids)) and set(ids) <= {f["id"] for f in ordered},
            "foreign/duplicate source candidate",
        )
        if source == "full":
            require(ids == [f["id"] for f in ordered], "graph fallback secretly uses another bank")
        else:
            scores = (np.asarray(queries) @ keys[candidates].T / math.sqrt(30)).max(axis=0)
            scores_by_id = {
                ordered[i - 1]["id"]: float(s) for i, s in zip(candidates, scores, strict=True)
            }
            require(
                len(ids) == min(cap, len(candidates)) and set(ids) <= set(scores_by_id),
                "candidate budget/source mismatch",
            )
            selected_scores = [scores_by_id[i] for i in ids]
            excluded = set(scores_by_id) - set(ids)
            require(
                all(a + 1e-9 >= b for a, b in itertools.pairwise(selected_scores))
                and (
                    not excluded
                    or max(scores_by_id[i] for i in excluded) <= min(selected_scores) + 1e-9
                ),
                "repair candidates not actual top-scored originals",
            )
        work["returned_facts"] = len(ids)
        for k, value in work.items():
            source_work[k] += value
            require(d["work"][k] == source_work[k], "source routing/score work mismatch")
        delta["source_candidate_facts"] = len(ids)
        delta["cue_vectors_created"] = len(cues) - len(base)
        delta["cue_query_rows"] = len(cues)
        delta["requery_reads"] = int(stage in (1, 2))
        delta["widened_reads"] = int(stage == 2)
        delta["graph_fallback_reads"] = int(stage == 3)
        delta["trace_index_ids"] = sum(len(r["index_fact_ids"]) for r in routes)
        delta["trace_node_spans"] = sum(len(r["node_spans"]) for r in routes)
        require(repair["work_delta"] == delta, "uncharged progress/trace/requery work")
        for k, v in delta.items():
            cumulative[k] += v
            require(d["work"]["repair_" + k] == cumulative[k], "cumulative repair work mismatch")
        structural = dict.fromkeys(WORK_KEYS, 0)
        audit_closure(row, ordered, structural)
        for k, v in structural.items():
            dependency_work[k] += v
            require(
                d["work"]["dependency_" + k] == dependency_work[k],
                "cumulative repaired support work mismatch",
            )
        graph_reads += int(stage == 3)
    for prefix, values in (
        ("", source_work),
        ("repair_", cumulative),
        ("dependency_", dependency_work),
    ):
        require(
            all(episode["costs"][prefix + k] == v for k, v in values.items()),
            "final episode cost differs from actual progress events",
        )
    return {
        **prefix_result,
        "reader": episode["reader"],
        "repair_reads_checked": len(episode["trajectory"]),
        "graph_reads": graph_reads,
        "affine_branch_scores_checked": source_work["scored_nodes"],
        "hierarchy_routes_checked": source_work["routing_passes"]
        and sum(len(r["decision"]["route"]) for r in episode["trajectory"]),
        "outcome_attribution": "hybrid_graph_assisted" if graph_reads else "no_graph_repair",
    }


def audit_directory(output: Path) -> dict[str, Any]:
    manifest, protocol, report = (
        read_json(output / name) for name in ("manifest.json", "protocol.json", "report.json")
    )
    require(
        hashlib.sha256(json.dumps(protocol, indent=2, sort_keys=True).encode()).hexdigest()
        == manifest["protocol_hash"]
        and report["protocol"] == protocol
        and not report["source_changed_during_run"],
        "mixed/falsely frozen progress run",
    )
    required = {
        "research/progress_retrieval.py",
        "research/run_progress_benchmark.py",
        "research/dependency_memory.py",
        "research/minigrid_benchmark.py",
        "uv.lock",
    }
    require(required <= set(manifest["source_hashes"]), "progress implementation not frozen")
    for name, h in manifest["source_hashes"].items():
        require(
            hashlib.sha256((output / "source-snapshot" / name).read_bytes()).hexdigest() == h,
            "progress source snapshot mismatch",
        )
    require(
        protocol["progress"]
        == {
            "history_limit": 24,
            "cue_after": 8,
            "widen_after": 16,
            "graph_after_repeated": 24,
            "hard_graph_after": 48,
            "candidate_budget": 192,
            "fallback": "full observed graph until new canonical payload; not a ZHA win",
        },
        "unreviewed progress limits",
    )
    require(
        protocol["official_versions"] == {"minigrid": "3.1.0", "gymnasium": "1.4.0"},
        "unreviewed official environment",
    )
    expected_seeds = (
        protocol["development_seeds"]
        if protocol["split"] == "development"
        else protocol["previously_exposed_seeds"]
        if protocol["split"] == "diagnostic"
        else protocol["evaluation_seeds"]
    )
    require(
        protocol["selected_seeds"] == expected_seeds
        and not set(protocol["evaluation_seeds"])
        & {0, 1, 1001, 1002, 1003, 2001, 2002, 2003, 2004, 2005, 2006},
        "reused or unregistered fresh cohort",
    )
    expected = set(
        itertools.product(
            protocol["selected_environments"],
            protocol["selected_readers"],
            protocol["selected_seeds"],
        )
    )
    seen = set()
    audits = []
    for row in report["episodes"]:
        p = output / row["trace_file"]
        require(
            hashlib.sha256(p.read_bytes()).hexdigest() == row["sha256"], "progress trace checksum"
        )
        e = read_json(p)
        key = e["environment_id"], e["reader"], e["seed"]
        require(
            key in expected
            and key not in seen
            and e["protocol_hash"] == manifest["protocol_hash"]
            and e["capacity"] == 96
            and e["split"] == protocol["split"],
            "foreign/duplicate progress episode",
        )
        seen.add(key)
        require(
            len(e["trajectory"]) <= protocol["external_step_cap"], "progress episode cap exceeded"
        )
        require(
            all(e[k] == row[k] for k in ("environment_id", "seed", "reader", "costs"))
            and all(row[k] == v for k, v in e["result"].items()),
            "progress table contradicts real trace",
        )
        audits.append(audit_episode(e))
    require(seen == expected, "missing progress condition")
    for s in report["summaries"]:
        rows = [
            r
            for r in report["episodes"]
            if r["environment_id"] == s["environment_id"] and r["reader"] == s["reader"]
        ]
        require(
            s["episodes"] == len(rows)
            and s["successes"] == sum(r["success"] for r in rows)
            and s["mean_steps"] == sum(r["steps"] for r in rows) / len(rows)
            and s["mean_return"] == sum(r["return"] for r in rows) / len(rows),
            "false progress outcome aggregate",
        )
        require(
            all(v == sum(r["costs"][k] for r in rows) for k, v in s["costs"].items()),
            "false progress cost aggregate",
        )
    return {
        "all_passed": True,
        "episodes_checked": len(audits),
        "official_steps_checked": sum(a["steps_checked"] for a in audits),
        "repair_reads_checked": sum(a["repair_reads_checked"] for a in audits),
        "graph_fallback_reads": sum(a["graph_reads"] for a in audits),
        "new_variant_hierarchy_routes_checked": sum(
            a.get("hierarchy_routes_checked", 0) for a in audits
        ),
        "affine_branch_scores_checked": sum(
            a.get("affine_branch_scores_checked", 0) for a in audits
        ),
        "new_variant_outcomes": [
            {
                "reader": name,
                "episodes": sum(a["reader"] == name for a in audits),
                "successes": sum(a["success"] for a in audits if a["reader"] == name),
                "successful_without_graph": sum(
                    a["success"] and a["graph_reads"] == 0 for a in audits if a["reader"] == name
                ),
                "successful_with_graph": sum(
                    a["success"] and a["graph_reads"] > 0 for a in audits if a["reader"] == name
                ),
            }
            for name in protocol["selected_readers"]
            if name.startswith(("progress_", "cues_"))
        ],
        "scope": "official observed-prefix replay, bounded progress state, actual cue and independent affine-tree routing/output numerics, structural budgets/costs and explicit graph attribution; not a semantic correctness certificate",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit_directory(args.results), indent=2))


if __name__ == "__main__":
    main()
