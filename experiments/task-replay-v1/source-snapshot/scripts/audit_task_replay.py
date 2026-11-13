"""Independent scalar update/gradient and official-task audit for routing replay.

No production optimizer, training loss, feature function, summary or router import.
Recorded gradients are algebraically replayed at every step. Sampled smooth
coordinates also receive independent scalar central-difference checks.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any

from scripts.audit_persistent_tasks import audit_episode, features
from tests import oracle

ROOT = Path(__file__).resolve().parents[1]


def sha(v: Any) -> str:
    return hashlib.sha256(
        json.dumps(v, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def load(path: Path, checksum: str | None = None) -> Any:
    raw = path.read_bytes()
    if checksum is not None:
        assert hashlib.sha256(raw).hexdigest() == checksum, "artifact checksum"
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    return json.loads(raw)


def scalar_kl(item: dict[str, Any], refs: list[list[float]]) -> tuple[float, list[tuple[int, ...]]]:
    keys, queries = item["keys"], item["queries"]
    losses = []
    winners = []
    for q in queries:
        logits = [oracle.dot(q, k) / math.sqrt(30) for k in keys]
        for level in (1, 2, 3):
            span = 4**level
            full = (len(keys) - 1) // span
            stop = 1 + full * span
            teacher = [logits[0]]
            predicted = [logits[0]]
            for start in range(1, stop, span):
                scores = []
                for ref in refs:
                    mean, bias = oracle.summary(keys[start : start + span], ref)
                    scores.append(oracle.dot(q, mean) / math.sqrt(30) + bias)
                maximum = max(scores)
                winners.append(tuple(i for i, v in enumerate(scores) if v >= maximum - 1e-10))
                predicted.append(maximum)
                teacher.append(oracle.lse(logits[start : start + span]))
            if stop < len(keys):
                tail = oracle.lse(logits[stop:])
                teacher.append(tail)
                predicted.append(tail)
            tz, pz = oracle.lse(teacher), oracle.lse(predicted)
            losses.append(
                math.fsum(
                    math.exp(t - tz) * ((t - tz) - (p - pz))
                    for t, p in zip(teacher, predicted, strict=True)
                )
            )
    return math.fsum(losses) / len(queries), winners


def audit_learning(
    trace: dict[str, Any],
    parent: dict[str, Any],
    child: dict[str, Any],
    corpus: dict[str, dict[str, Any]],
) -> dict[str, int]:
    assert trace["parent_hash"] == parent["sha256"] and trace["child_hash"] == child["sha256"]
    pool = [corpus[i] for i in trace["pool_ids"]]
    assert len(pool) == len({i["id"] for i in pool}) and pool
    assert all(
        i["role"] in (("wake",) if trace["schedule"] == "recent" else ("anchor", "wake"))
        for i in pool
    )
    train_contexts = {i["context"] for i in pool} | set(parent["training_contexts"])
    validation = [
        corpus[i] for name in ("validation_old_ids", "validation_new_ids") for i in trace[name]
    ]
    assert not train_contexts & {i["context"] for i in validation}, "replay split leakage"
    assert trace["work"]["gradient_calls"] == trace["steps"] == len(trace["updates"])
    refs = [[list(row) for row in parent["references"]]]
    rng = random.Random(trace["seed"])
    probabilities = [1 / len(pool)] * len(pool)
    refreshes = {r["before_step"]: r for r in trace["priority_refreshes"]}
    assert set(refreshes) == (
        set(range(1, trace["steps"] + 1, 8)) if trace["schedule"] == "priority" else set()
    )
    history = {r["step"]: r for r in trace["history"]}
    selected = copy.deepcopy(refs)
    best_score = history[0]["selection_kl"]
    best_step = 0
    numeric = skipped = 0
    work = {
        k: 0
        for k in (
            "loss_calls",
            "gradient_calls",
            "priority_calls",
            "validation_calls",
            "dense_teacher_pairs",
            "reference_key_pairs",
        )
    }

    def charge(item: dict[str, Any], purpose: str) -> None:
        work["loss_calls"] += 1
        work[purpose + "_calls"] += 1
        n, q = len(item["keys"]), len(item["queries"])
        work["dense_teacher_pairs"] += n * q
        work["reference_key_pairs"] += (
            q * 8 * sum(((n - 1) // 4**level) * 4**level for level in (1, 2, 3))
        )

    def check_validation(step: int) -> None:
        row = history[step]
        for name in ("old", "new"):
            assert trace["validation_" + name + "_ids"]
            for uid in trace["validation_" + name + "_ids"]:
                charge(corpus[uid], "validation")
        assert math.isclose(
            row["selection_kl"],
            (row["old_validation_kl"] + row["new_validation_kl"]) / 2,
            abs_tol=1e-13,
        )
        assert row["reference_hash"] == sha(refs)
        # Independent validation construction at the initial and selected endpoints.
        if step in (0, trace["selected_step"]):
            for name in ("old", "new"):
                items = [corpus[uid] for uid in trace["validation_" + name + "_ids"]]
                value = math.fsum(scalar_kl(i, refs[0])[0] for i in items) / len(items)
                assert math.isclose(
                    value, row[name + "_validation_kl"], abs_tol=1e-9, rel_tol=1e-8
                ), "independent validation KL"

    check_validation(0)
    for step, update in enumerate(trace["updates"], start=1):
        assert update["step"] == step and update["before_hash"] == sha(refs), "parameter chain"
        if step in refreshes:
            refresh = refreshes[step]
            losses = refresh["losses"]
            assert len(losses) == len(pool) and all(math.isfinite(x) for x in losses)
            weights = [(max(0.0, v) + 1e-6) ** 0.6 for v in losses]
            total = math.fsum(weights)
            probabilities = [0.1 / len(pool) + 0.9 * w / total for w in weights]
            assert all(
                math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-14)
                for a, b in zip(probabilities, refresh["probabilities"], strict=True)
            ), "priority probabilities"
            for item in pool:
                charge(item, "priority")
            # Verify sampled priority losses independently, rather than pretending
            # to independently recompute every expensive scoring pass.
            for index in sorted({0, len(pool) // 2, len(pool) - 1}):
                value, _ = scalar_kl(pool[index], refs[0])
                assert math.isclose(value, losses[index], abs_tol=1e-9, rel_tol=1e-8), (
                    "priority source loss"
                )
        index = rng.choices(range(len(pool)), weights=probabilities, k=1)[0]
        item = pool[index]
        assert index == update["pool_index"] and item["id"] == update["sample_id"], (
            "replay sampling/source"
        )
        assert math.isclose(probabilities[index], update["probability"], abs_tol=1e-14)
        gradient = update["gradient"]
        assert (
            len(gradient) == 1 and len(gradient[0]) == 8 and all(len(r) == 30 for r in gradient[0])
        )
        assert all(math.isfinite(v) for row in gradient[0] for v in row)
        norm = math.sqrt(math.fsum(v * v for row in gradient[0] for v in row))
        factor = min(1.0, 1.0 / (norm + 1e-12))
        assert math.isclose(norm, update["gradient_norm"], abs_tol=1e-12, rel_tol=1e-10)
        assert math.isclose(factor, update["clip_factor"], abs_tol=1e-12, rel_tol=1e-10)
        charge(item, "gradient")
        if step in {1, max(1, trace["steps"] // 2), trace["steps"]}:
            value, base_winners = scalar_kl(item, refs[0])
            assert math.isclose(value, update["loss"], abs_tol=1e-9, rel_tol=1e-8), (
                "gradient source objective"
            )
            ranked = sorted(
                range(240), key=lambda i: abs(gradient[0][i // 30][i % 30]), reverse=True
            )[:2]
            for coordinate in ranked:
                a, b = divmod(coordinate, 30)
                plus, minus = copy.deepcopy(refs[0]), copy.deepcopy(refs[0])
                h = 1e-5
                plus[a][b] += h
                minus[a][b] -= h
                vp, wp = scalar_kl(item, plus)
                vm, wm = scalar_kl(item, minus)
                if wp != base_winners or wm != base_winners:
                    skipped += 1
                    continue
                numeric += 1
                assert math.isclose(
                    (vp - vm) / (2 * h), gradient[0][a][b], abs_tol=2e-7, rel_tol=1e-3
                ), "independent smooth replay gradient"
        after = update["parameters"]
        assert len(after) == 1 and len(after[0]) == 8 and all(len(r) == 30 for r in after[0])
        for a in range(8):
            for b in range(30):
                expected = refs[0][a][b] - trace["learning_rate"] * factor * gradient[0][a][b]
                assert math.isfinite(after[0][a][b]) and math.isclose(
                    expected, after[0][a][b], abs_tol=1e-11, rel_tol=1e-11
                ), "SGD update algebra"
        assert sha(after) == update["after_hash"], "published parameter digest"
        refs = copy.deepcopy(after)
        if step in history:
            check_validation(step)
            if history[step]["selection_kl"] < best_score - 1e-12:
                best_score, best_step, selected = (
                    history[step]["selection_kl"],
                    step,
                    copy.deepcopy(refs),
                )
    assert best_step == trace["selected_step"] == child["selected_step"], (
        "validation-only selection"
    )
    assert selected[0] == [list(row) for row in child["references"]], "selected child parameters"
    assert work == trace["work"], "teacher/priority/validation work accounting"
    return {
        "updates": len(trace["updates"]),
        "smooth_gradient_coordinates": numeric,
        "nonsmooth_coordinates_skipped": skipped,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    args = parser.parse_args()
    root = args.results
    manifest = load(root / "manifest.json")
    for name, checksum in manifest["sources"].items():
        assert (
            hashlib.sha256((root / "source-snapshot" / name).read_bytes()).hexdigest() == checksum
        ), "frozen source integrity"
    protocol = load(root / "protocol.json")
    report = load(root / "report.json")
    assert (
        report["complete"] and sha(protocol) == report["protocol_hash"] == manifest["protocol_hash"]
    )
    corpus_list = load(
        root / report["corpus_artifact"]["file"], report["corpus_artifact"]["sha256"]
    )
    corpus = {i["id"]: i for i in corpus_list}
    assert len(corpus) == len(corpus_list)
    numerical = set()
    by_role: dict[str, set[str]] = {}
    for item in corpus_list:
        assert sha({k: v for k, v in item.items() if k != "id"}) == item["id"]
        key = sha([item["queries"], item["keys"]])
        assert key not in numerical, "numerical corpus leakage"
        numerical.add(key)
        by_role.setdefault(item["role"], set()).add(item["context"])
    assert not (by_role["anchor"] | by_role["wake"]) & (
        by_role["validation_old"] | by_role["validation_new"] | by_role["comparison"]
    )
    assert not (by_role["validation_old"] | by_role["validation_new"]) & by_role["comparison"]
    collections = load(root / "collections.json")
    rebuilt: dict[str, list[dict[str, Any]]] = {role: [] for role in protocol["dataset_order"]}
    for collection in collections["sources"]:
        source = load(root / collection["file"], collection["sha256"])
        rows = source["trajectory"]
        count = protocol["samples_per_episode"]
        wanted = {int((len(rows) - 1) * i / (count - 1)) for i in range(count)}
        context = f"{source['environment_id']}/seed={source['seed']}"
        heads: dict[tuple[int, int], dict[str, Any]] = {}
        for step, row in enumerate(rows):
            assert row["step"] == step
            for fact in row["new_facts"]:
                assert fact["observed_step"] <= step and fact["id"] > 0
                prior = heads.get((fact["x"], fact["y"]))
                assert fact["previous"] == (prior["id"] if prior else None), (
                    "source correction chain"
                )
                heads[(fact["x"], fact["y"])] = fact
            if step in wanted:
                ordered = sorted(heads.values(), key=lambda f: f["id"])
                rebuilt[collection["role"]].append(
                    {
                        "context": context,
                        "step": step,
                        "role": collection["role"],
                        "source_ids": [f["id"] for f in ordered],
                        "queries": row["decision"]["queries"],
                        "keys": [[0.0] * 30] + [features(f) for f in ordered],
                    }
                )
    seen = set()
    expected_items = []
    expected_dropped = {}
    for role in protocol["dataset_order"]:
        dropped = 0
        for item in rebuilt[role]:
            key = sha([item["queries"], item["keys"]])
            if key in seen:
                dropped += 1
                continue
            seen.add(key)
            expected_items.append(item)
        expected_dropped[role] = dropped
    assert expected_dropped == collections["dropped"], "outcome-independent corpus filtering"
    assert len(expected_items) == len(corpus_list)
    for expected_item, actual_item in zip(expected_items, corpus_list, strict=True):
        for key in ("context", "step", "role", "source_ids", "queries"):
            assert expected_item[key] == actual_item[key], "corpus observed prefix provenance"
        assert all(
            math.isclose(a, b, abs_tol=1e-12, rel_tol=1e-12)
            for ka, kb in zip(expected_item["keys"], actual_item["keys"], strict=True)
            for a, b in zip(ka, kb, strict=True)
        ), "corpus key provenance/future boundary"
    parent = load(root / "parent-references.json")
    models = {"parent": parent, "random": load(root / "random-references.json")}
    totals = {"updates": 0, "smooth_gradient_coordinates": 0, "nonsmooth_coordinates_skipped": 0}
    learning = load(root / "learning.json")
    for run in learning["runs"]:
        name = run["condition"]
        child = load(root / (name + "-references.json"))
        assert sha({k: v for k, v in child.items() if k != "sha256"}) == child["sha256"]
        trace = load(root / run["file"], run["sha256"])
        counts = audit_learning(trace, parent, child, corpus)
        for k, v in counts.items():
            totals[k] += v
        models[name] = child
    conditions = set(models) | {"exact", "no_recovery", "parent-cap96", "exact-cap96"}
    expected = {
        (c, e, s)
        for c in conditions
        for e in protocol["environments"]
        for s in protocol["comparison_seeds"]
    }
    actual = {(r["condition"], r["environment"], r["seed"]) for r in report["runs"]}
    assert actual == expected and len(report["runs"]) == len(expected), (
        "comparison cohort completeness"
    )
    decisions = routes = numerical_route_cases = 0
    for run in report["runs"]:
        episode = load(root / run["file"], run["sha256"])
        model = models.get(run["condition"], parent)
        assert episode["reference_hash"] == model["sha256"] == run["reference_hash"]
        assert all(
            r["decision"]["dependency"]["active_capacity"] == run["capacity"]
            for r in episode["trajectory"]
        )
        stats = audit_episode(episode, model, protocol["threshold"])
        decisions += stats["decisions"]
        routes += stats["routes"]
        numerical_route_cases += stats["numerical_route_cases"]
        assert all(
            run[k] == episode["result"][k]
            for k in ("success", "steps", "error", "truncated", "external_cutoff")
        )
    for summary in report["summary"]:
        rows = [r for r in report["runs"] if r["condition"] == summary["condition"]]
        assert summary["successes"] == sum(r["success"] for r in rows) and summary[
            "episodes"
        ] == len(rows)
    qualities = load(root / "quality.json")["conditions"]
    common = {(i["context"], i["step"]): i for i in corpus_list if i["role"] == "comparison"}
    mass_cases = 0
    for condition, quality in qualities.items():
        cases = load(root / quality["file"], quality["sha256"])
        for row in cases:
            item = common[(row["context"], row["step"])]
            assert row["reference_hash"] == models[condition]["sha256"]
            logits = [
                oracle.dot(item["queries"][row["query"]], k) / math.sqrt(30) for k in item["keys"]
            ]
            z = oracle.lse(logits)
            weights = [math.exp(v - z) for v in logits]
            assert math.isclose(
                math.fsum(weights[i] for i in row["selected_ids"]),
                row["retained_mass"],
                abs_tol=1e-9,
                rel_tol=1e-9,
            )
            assert math.isclose(
                math.fsum(sorted(weights, reverse=True)[: len(row["selected_ids"])]),
                row["same_k_oracle_mass"],
                abs_tol=1e-9,
                rel_tol=1e-9,
            )
            mass_cases += 1
        assert math.isclose(
            math.fsum(r["retained_mass"] for r in cases) / len(cases),
            quality["mean_retained_mass"],
            abs_tol=1e-12,
        )
    result = {
        "all_passed": True,
        **totals,
        "task_runs": len(report["runs"]),
        "decisions": decisions,
        "routes": routes,
        "numerical_route_cases": numerical_route_cases,
        "offline_mass_cases": mass_cases,
        "scope": "all recorded SGD update algebra and work/sampling/selection checks, sampled scalar objectives and smooth gradient coordinates, official task replay and source/graph/selected-route audit; not exhaustive gradient or semantic correctness proof",
    }
    destination = root / "INDEPENDENT_AUDIT.json"
    if destination.exists():
        assert load(destination) == result
    else:
        destination.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
