"""Independent observation, seed, structural-bundle and known-mask evidence audit.

The reference graph uses integer original IDs and its own BFS/packing logic.
It never imports the production dependency reader or common planner. Seed-only
projection delegates official replay/numerical retrieval to the independent T0
auditor; actual returned evidence and planner routes are checked separately.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from collections import deque
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_complex_tasks import audit_minigrid, digest, read_json, require  # noqa: E402

STEPS = ((1, 0), (0, 1), (-1, 0), (0, -1))
WORK_KEYS = (
    "flat_history_filter_items",
    "source_head_scan_items",
    "output_facts",
    "current_context_lookups",
    "graph_materialization_items",
    "path_node_visits",
    "seed_role_scan_items",
    "support_classification_items",
    "seed_identity_lookups",
    "head_scan_items",
    "head_hash_items",
    "graph_build_nodes",
    "graph_neighbor_checks",
    "nomination_items",
    "landmark_checks",
    "prerequisite_checks",
    "bfs_calls",
    "bfs_nodes",
    "bfs_edge_checks",
    "halo_lookups",
    "packing_checks",
    "coverage_bit_writes",
    "coverage_binary_bytes",
    "coverage_json_bytes",
    "residual_neighbor_checks",
    "bundles_complete",
    "bundles_overbudget",
    "bundles_missing",
    "bundles_packed",
)


def point(fact: dict[str, Any]) -> tuple[int, int]:
    return fact["x"], fact["y"]


def adjacent(position: tuple[int, int]) -> list[tuple[int, int]]:
    return [(position[0] + dx, position[1] + dy) for dx, dy in STEPS]


def navigable(fact: dict[str, Any]) -> bool:
    return fact["object"] in (1, 3, 4, 8)


class ReferenceGraph:
    """Observed integer-ID graph with explicit work events, no production code."""

    def __init__(self, heads: list[dict[str, Any]], context: dict[str, Any], work: dict[str, int]):
        self.facts = {f["id"]: f for f in heads}
        self.at = {point(f): f["id"] for f in heads}
        self.context, self.work = context, work
        self.start = self.at[tuple(context["position"])]
        work["graph_materialization_items"] += 2 * len(heads)
        self.edges: dict[int, list[int]] = {}
        self.cache: dict[frozenset[int] | None, dict[int, int | None]] = {}
        for f in heads:
            work["graph_build_nodes"] += 1
            if navigable(f):
                targets = []
                for p in adjacent(point(f)):
                    work["graph_neighbor_checks"] += 1
                    if p in self.at and navigable(self.facts[self.at[p]]):
                        targets.append(self.at[p])
                self.edges[f["id"]] = targets

    def search(self, colors: frozenset[int] | None) -> dict[int, int | None]:
        if colors in self.cache:
            return self.cache[colors]
        self.work["bfs_calls"] += 1
        parent: dict[int, int | None] = {self.start: None}
        pending = deque([self.start])
        while pending:
            current = pending.popleft()
            self.work["bfs_nodes"] += 1
            for nxt in self.edges.get(current, []):
                self.work["bfs_edge_checks"] += 1
                fact = self.facts[nxt]
                locked = fact["object"] == 4 and fact["state"] == 2
                if nxt not in parent and (colors is None or not locked or fact["color"] in colors):
                    parent[nxt] = current
                    pending.append(nxt)
        self.cache[colors] = parent
        return parent

    def path(self, identifier: int, colors: frozenset[int] | None) -> list[int]:
        parent = self.search(colors)
        f = self.facts[identifier]
        endings = (
            [identifier]
            if navigable(f)
            else [self.at[p] for p in adjacent(point(f)) if p in self.at]
        )
        routes = []
        for end in endings:
            if end not in parent:
                continue
            chain = [end]
            while parent[chain[-1]] is not None:
                previous = parent[chain[-1]]
                if previous is None:
                    raise ValueError("broken independent parent chain")
                chain.append(previous)
            self.work["path_node_visits"] += len(chain)
            routes.append(list(reversed(chain)))
        return (
            min(routes, key=lambda path: (len(path), point(self.facts[path[-1]]))) if routes else []
        )

    def nominate(self, seeds: list[int], modern: bool = True) -> list[tuple[int, str]]:
        reachable = self.search(None)
        mission = self.context["mission"]
        matching = "matching" in mission
        self.work["seed_role_scan_items"] += len(seeds)
        samples = [
            self.facts[i]
            for i in seeds
            if self.facts[i]["cue"] and self.facts[i]["object"] in (5, 6)
        ]
        sample = min(samples, key=lambda f: (f["first_seen"], f["id"])) if samples else None
        kind = next(
            (value for name, value in (("ball", 6), ("box", 7), ("key", 5)) if name in mission), 6
        )
        color = next(
            (
                value
                for name, value in (
                    ("red", 0),
                    ("green", 1),
                    ("blue", 2),
                    ("purple", 3),
                    ("yellow", 4),
                    ("grey", 5),
                )
                if name in mission
            ),
            None,
        )
        candidates = []
        for identifier in seeds:
            seed = self.facts[identifier]
            self.work["nomination_items"] += 1
            self.work["landmark_checks"] += 1
            priority, role = 5, None
            if seed["cue"] and matching:
                priority, role = 0, "cue"
            elif (
                matching
                and sample
                and not seed["cue"]
                and (seed["object"], seed["color"]) == (sample["object"], sample["color"])
            ):
                priority, role = 0, "matching_landmark"
            elif (
                "pick up" in mission
                and seed["object"] == kind
                and (color is None or seed["color"] == color)
            ):
                priority, role = 0, "mission_landmark"
            elif not matching and "pick up" not in mission and seed["object"] == 8:
                priority, role = 0, "goal_landmark"
            elif seed["object"] == 5 and not matching:
                priority, role = 1, "key_landmark"
            elif seed["object"] == 4 and seed["state"] != 0:
                priority, role = 2, "door_landmark"
            elif (
                identifier in reachable
                and navigable(seed)
                and any(p not in self.at for p in adjacent(point(seed)))
            ):
                priority, role = 3, "true_observed_frontier"
            if role is not None:
                route = self.path(identifier, None)
                if route or (modern and role != "true_observed_frontier"):
                    candidates.append((priority, len(route) if route else 8193, identifier, role))
        return [(i, role) for _, _, i, role in sorted(candidates)[:8]]

    def bundle(
        self, seed: int, kind: str, semantic_support: tuple[int, ...] = (), modern: bool = True
    ) -> dict[str, Any]:
        if modern:
            self.work["seed_identity_lookups"] += 1 + len(semantic_support)
        inventory = self.context["inventory"]
        colors = (
            frozenset([inventory[1]])
            if inventory is not None and inventory[0] == 5
            else frozenset()
        )
        route = self.path(seed, colors) or self.path(seed, None)
        missing = [] if route else ["no_observed_route"]
        keys, supporting = [], []
        locks = [i for i in route if self.facts[i]["object"] == 4 and self.facts[i]["state"] == 2]
        if self.facts[seed]["object"] == 4 and self.facts[seed]["state"] == 2 and seed not in locks:
            locks.append(seed)
        for door in locks:
            color = self.facts[door]["color"]
            if color in colors:
                continue
            choices = []
            for i, f in self.facts.items():
                self.work["prerequisite_checks"] += 1
                if f["object"] == 5 and f["color"] == color:
                    path = self.path(i, colors)
                    if path:
                        choices.append((len(path), i, path))
            if choices:
                _, key, path = min(choices)
                keys.append(key)
                supporting.append(path)
                colors = colors | {self.facts[key]["color"]}
            else:
                missing.append(f"unreachable_matching_key:{door}:{color}")
        paths = [route, *supporting]
        path_ids = list(dict.fromkeys(i for path in paths for i in path))
        halo: set[int] = set()
        for i in path_ids:
            for p in adjacent(point(self.facts[i])):
                self.work["halo_lookups"] += 1
                if p in self.at:
                    halo.add(self.at[p])
        required = {seed, *path_ids, *keys, *halo, *semantic_support}
        self.work["support_classification_items"] += len(required)
        visible = {point(f): f for f in self.context["current_facts"]}
        current = {
            i
            for i in required
            if point(self.facts[i]) in visible
            and self.facts[i]["cue"] == visible[point(self.facts[i])]["cue"]
        }
        result = {
            "seed_id": seed,
            "kind": kind,
            "required_ids": sorted(required),
            "path_ids": sorted(path_ids),
            "support_edges": sorted(
                [
                    list(edge)
                    for edge in {
                        (a, b) for path in paths for a, b in zip(path, path[1:], strict=False)
                    }
                ]
            ),
            "prerequisite_ids": sorted(set(keys)),
            "halo_ids": sorted(halo),
            "current_support_ids": sorted(current),
            "historical_ids": sorted(required - current),
            "missing": missing,
        }
        if modern:
            result.update(paths=paths, semantic_support_ids=list(semantic_support))
        return result


def audit_mask(mask: dict[str, Any], heads: list[dict[str, Any]], version: int) -> int:
    require(
        set(mask)
        == {"origin", "width", "height", "version", "head_hash", "bits_hex", "binary_bytes"},
        "mask includes undeclared information",
    )
    require(
        mask["origin"] == [-32, -32]
        and mask["width"] == mask["height"] == 64
        and mask["binary_bytes"] == 512,
        "mask bounds/binary budget",
    )
    require(
        mask["version"] == version and mask["head_hash"] == digest(heads),
        "mask head/version identity",
    )
    expected = bytearray(512)
    for f in heads:
        x, y = point(f)
        require(-32 <= x < 32 and -32 <= y < 32, "known coordinate outside fixed mask support")
        index = (y + 32) * 64 + x + 32
        expected[index // 8] |= 1 << (index % 8)
    require(
        type(mask["bits_hex"]) is str and mask["bits_hex"] == bytes(expected).hex(),
        "mask does not equal observed-prefix known cells",
    )
    return len(json.dumps(mask, separators=(",", ":")).encode())


def audit_planner_view(decision: dict[str, Any]) -> None:
    """A mask can suppress frontiers but cannot supply a typed walking cell."""
    recalled = decision["memory_facts"]
    require(decision["memory_ids"] == [f["id"] for f in recalled], "returned raw IDs/payload order")
    require(len({f["id"] for f in recalled}) == len(recalled), "duplicate returned raw fact")
    view = {point(f): f for f in recalled}
    view.update({point(f): f for f in decision["current_facts"]})
    position = tuple(decision["pose"][:2])
    plan = [tuple(p) for p in decision["plan"]]
    require(bool(plan) and plan[0] == position, "planner path must start at its observed pose")
    held = decision["inventory"]
    for a, b in zip(plan, plan[1:], strict=False):
        require(
            b in adjacent(a) and b in view, "planner navigates through unseen or mask-only cell"
        )
        f = view[b]
        permissible = f["object"] in (1, 3, 8) or (
            f["object"] == 4 and (f["state"] != 2 or held == [5, f["color"]])
        )
        require(permissible, "planner path crosses unsupported locked/object cell")
    ids = set(decision["memory_ids"])
    require(
        set(decision["goal_sources"]) <= ids and set(decision["plan_fact_ids"]) <= ids,
        "planner source outside returned raw facts",
    )
    require(
        decision["plan_fact_ids"] == [view[p]["id"] for p in plan if p in view and view[p]["id"]],
        "planner path source provenance",
    )


def seed_projection(episode: dict[str, Any]) -> dict[str, Any]:
    """Audit seed reads without pretending those seeds were the packed output.

    Actual bundle returns/actions remain in the original and receive separate
    checks. Dropping planner source fields here avoids binding actual bundle
    planning sources to the *different*, explicitly projected seed workspace.
    """
    projected = {
        **episode,
        "trajectory": [{**row, "decision": dict(row["decision"])} for row in episode["trajectory"]],
    }
    archive = {f["id"]: f for f in episode["archive"]}
    source = None
    for row in projected["trajectory"]:
        decision = row["decision"]
        receipt = decision["dependency"]
        if source is None:
            source = receipt["seed_reader"]
        require(receipt["seed_reader"] == source, "seed method changes within episode")
        decision["memory_ids"] = receipt["seed_ids"]
        require(all(i in archive for i in decision["memory_ids"]), "foreign seed original")
        decision["memory_facts"] = [archive[i] for i in decision["memory_ids"]]
        decision["goal_sources"], decision["plan_fact_ids"] = [], []
    require(source in ("zha_adaptive", "exact", "recency", "full"), "unsupported seed reader")
    projected["reader"] = source
    if episode["reader"] == "flat_exact_history_mask":
        projected["capacity"] = episode["capacity"] + 49
    return projected


def audit_dependency_episode(
    episode: dict[str, Any], declared_work_keys: tuple[str, ...] = WORK_KEYS
) -> dict[str, Any]:
    require(set(declared_work_keys) <= set(WORK_KEYS), "unknown structural work schema")
    if episode["reader"] in ("zha_adaptive", "exact", "full", "none"):
        require(
            episode["coverage_allowance_bytes"] == 0
            and all(
                "coverage" not in r["decision"] and "dependency" not in r["decision"]
                for r in episode["trajectory"]
            ),
            "legacy baseline gained undeclared metadata",
        )
        return {
            **audit_minigrid(episode),
            "dependency_reads_checked": 0,
            "bundles_checked": 0,
            "historical_facts_returned": 0,
            "raw_fact_json_bytes": 0,
            "mask_json_bytes": 0,
        }
    seed_result = audit_minigrid(seed_projection(episode))
    require(episode["coverage_allowance_bytes"] == 512, "mask allowance not declared")
    names = {
        "flat_zha_mask": "zha_adaptive",
        "flat_exact_mask": "exact",
        "flat_exact_history_mask": "exact",
        "bundle_zha": "zha_adaptive",
        "bundle_exact": "exact",
        "bundle_recency": "recency",
        "graph": "full",
    }
    require(episode["reader"] in names, "unknown dependency condition")
    current: dict[tuple[int, int], dict[str, Any]] = {}
    version = 0
    cumulative = dict.fromkeys(declared_work_keys, 0)
    bundles_checked = history_count = fact_bytes = mask_bytes = 0
    for row in episode["trajectory"]:
        for f in row["new_facts"]:
            current[point(f)] = f
            version = f["id"]
        heads = sorted(current.values(), key=lambda f: f["id"])
        by_id = {f["id"]: f for f in heads}
        decision = row["decision"]
        actual = decision["dependency"]
        context = {
            "position": decision["pose"][:2],
            "direction": decision["pose"][2],
            "mission": row["observation"]["mission"],
            "inventory": decision["inventory"],
            "current_facts": decision["current_facts"],
            "step": row["step"],
        }
        require(actual["context"] == context, "context carries unobserved or future state")
        require(
            actual["mode"] == episode["reader"]
            and actual["seed_reader"] == names[episode["reader"]],
            "condition/seed method mismatch",
        )
        require(
            actual["closure_scope"] == "one-hop halo of stated paths; not global frontier closure",
            "undeclared/global closure claim",
        )
        require(
            actual["source_head_ids"] == [f["id"] for f in heads]
            and actual["source_head_hash"] == digest(heads)
            and actual["source_version"] == version,
            "structural source heads/version mismatch",
        )
        require(set(actual["seed_ids"]) <= set(by_id), "foreign/future/stale seed")
        require(
            actual["returned_ids"] == decision["memory_ids"]
            and set(actual["returned_ids"]) <= set(by_id),
            "foreign/future/stale returned source",
        )
        require(
            decision["memory_facts"] == [by_id[i] for i in actual["returned_ids"]],
            "returned payload differs from canonical observation",
        )
        require(
            len(actual["returned_ids"]) <= episode["capacity"],
            "historical raw output exceeds capacity",
        )
        work = dict.fromkeys(WORK_KEYS, 0)
        work["source_head_scan_items"] = len(heads)
        work["current_context_lookups"] = len(context["current_facts"])
        work["output_facts"] = len(actual["returned_ids"])
        work["head_scan_items"] = work["head_hash_items"] = len(heads)
        work["coverage_bit_writes"] = len(heads)
        work["coverage_binary_bytes"] = 512
        work["coverage_json_bytes"] = audit_mask(decision["coverage"], heads, version)
        mask_bytes += work["coverage_json_bytes"]
        packed: set[int] = set()
        if episode["reader"].startswith("flat_"):
            require(
                actual["bundles"] == [] and actual["status"] == "flat_mask_only",
                "flat-mask control performed undisclosed closure",
            )
            expected_flat = actual["seed_ids"]
            if episode["reader"] == "flat_exact_history_mask":
                visible = {point(f) for f in context["current_facts"]}
                work["flat_history_filter_items"] = len(expected_flat)
                expected_flat = [i for i in expected_flat if point(by_id[i]) not in visible][
                    : episode["capacity"]
                ]
            require(
                actual["returned_ids"] == expected_flat,
                "flat-mask output changed seed/history selection",
            )
        else:
            graph = ReferenceGraph(heads, context, work)
            modern = "seed_identity_lookups" in declared_work_keys
            nominations = graph.nominate(actual["seed_ids"], modern)
            cue = None
            if modern:
                work["seed_role_scan_items"] += len(actual["seed_ids"])
                cues = [
                    by_id[i]
                    for i in actual["seed_ids"]
                    if by_id[i]["cue"] and by_id[i]["object"] in (5, 6)
                ]
                cue = min(cues, key=lambda f: (f["first_seen"], f["id"])) if cues else None
            require(len(actual["bundles"]) == len(nominations), "extra/omitted semantic nomination")
            for recorded, (seed, kind) in zip(actual["bundles"], nominations, strict=True):
                semantic = (cue["id"],) if kind == "matching_landmark" and cue else ()
                bundle = graph.bundle(seed, kind, semantic, modern)
                for key, value in bundle.items():
                    require(recorded[key] == value, "false structural bundle field: " + key)
                candidate = packed | set(bundle["historical_ids"])
                work["packing_checks"] += len(candidate)
                if bundle["missing"]:
                    status = "missing_prerequisite"
                    work["bundles_missing"] += 1
                elif len(candidate) > episode["capacity"]:
                    status = "overbudget"
                    work["bundles_overbudget"] += 1
                else:
                    status = "complete"
                    work["bundles_complete"] += 1
                    work["bundles_packed"] += 1
                    packed = candidate
                require(
                    recorded["status"] == status
                    and recorded["required_historical_count"] == len(bundle["historical_ids"])
                    and recorded["candidate_packed_count"] == len(candidate)
                    and recorded["omitted_ids"] == sorted(set(bundle["historical_ids"]) - packed),
                    "false whole-bundle packing/completeness receipt",
                )
                bundles_checked += 1
            require(
                actual["returned_ids"] == sorted(packed),
                "packed output omits or invents structural support",
            )
            require(
                actual["status"]
                == ("packed" if work["bundles_complete"] else "structural_rejection"),
                "outer structural status mismatch",
            )
        effective = {point(f) for f in [*decision["memory_facts"], *context["current_facts"]]}
        residual = []
        for f in [*decision["memory_facts"], *context["current_facts"]]:
            if navigable(f):
                for p in adjacent(point(f)):
                    work["residual_neighbor_checks"] += 1
                    if p in current and p not in effective:
                        residual.append([f["x"], f["y"], p[0], p[1], current[p]["id"]])
        require(
            actual["residual_known_neighbor_omissions"] == residual,
            "hidden residual known-neighbor omission",
        )
        require(
            actual["work_delta"] == {k: work[k] for k in declared_work_keys},
            "structural scan/BFS/packing/serialization cost mismatch",
        )
        for name in declared_work_keys:
            count = work[name]
            cumulative[name] += count
            require(
                decision["work"]["dependency_" + name] == cumulative[name],
                "cumulative dependency cost mismatch",
            )
        audit_planner_view(decision)
        visible_by_position = {point(f): f for f in context["current_facts"]}
        history_count += sum(
            point(f) not in visible_by_position or f["cue"] != visible_by_position[point(f)]["cue"]
            for f in decision["memory_facts"]
        )
        fact_bytes += len(json.dumps(decision["memory_facts"], separators=(",", ":")).encode())
    require(
        all(episode["costs"]["dependency_" + k] == v for k, v in cumulative.items()),
        "episode structural costs contradict events",
    )
    return {
        **seed_result,
        "reader": episode["reader"],
        "dependency_reads_checked": len(episode["trajectory"]),
        "bundles_checked": bundles_checked,
        "historical_facts_returned": history_count,
        "raw_fact_json_bytes": fact_bytes,
        "mask_json_bytes": mask_bytes,
        "unrecorded_work_categories": sorted(set(WORK_KEYS) - set(declared_work_keys)),
    }


def declared_work_schema(path: Path) -> tuple[str, ...]:
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "WORK_KEYS" for t in node.targets
        ):
            value = ast.literal_eval(node.value)
            require(
                isinstance(value, tuple)
                and all(isinstance(k, str) for k in value)
                and set(value) <= set(WORK_KEYS),
                "unsupported frozen work schema",
            )
            return tuple(value)
    raise ValueError("frozen structural work declaration missing")


def audit_directory(output: Path) -> dict[str, Any]:
    manifest = read_json(output / "manifest.json")
    protocol = read_json(output / "protocol.json")
    require(
        hashlib.sha256(json.dumps(protocol, indent=2, sort_keys=True).encode()).hexdigest()
        == manifest["protocol_hash"],
        "frozen protocol hash mismatch",
    )
    required = {
        "research/dependency_memory.py",
        "research/run_dependency_benchmark.py",
        "research/minigrid_benchmark.py",
        "research/run_minigrid_benchmark.py",
        "uv.lock",
    }
    require(
        required <= set(manifest["source_hashes"])
        and any(
            name.startswith("src/open_hierarchical_memory/") for name in manifest["source_hashes"]
        ),
        "executed implementation not completely frozen",
    )
    for name, expected in manifest["source_hashes"].items():
        require(
            hashlib.sha256((output / "source-snapshot" / name).read_bytes()).hexdigest()
            == expected,
            "frozen source checksum mismatch: " + name,
        )
    declared = declared_work_schema(output / "source-snapshot/research/dependency_memory.py")
    require(
        protocol["official_versions"] == {"minigrid": "3.1.0", "gymnasium": "1.4.0"},
        "environment version changed",
    )
    require(
        not set(protocol["evaluation_seeds"])
        & (set(protocol["development_seeds"]) | set(protocol["previously_exposed_seeds"])),
        "fresh cohort overlaps exposed data",
    )
    require(
        protocol["selected_seeds"] == protocol["development_seeds"]
        if protocol["split"] == "development"
        else protocol["selected_seeds"] == protocol["evaluation_seeds"],
        "undeclared evaluation cohort",
    )
    report = read_json(output / "report.json")
    require(
        report["protocol"] == protocol and report["source_changed_during_run"] == [],
        "mixed source/protocol run",
    )
    expected_conditions = set(
        __import__("itertools").product(
            protocol["selected_environments"],
            protocol["selected_readers"],
            protocol["selected_seeds"],
        )
    )
    seen = set()
    audits = []
    for entry in report["episodes"]:
        path = output / entry["trace_file"]
        require(
            hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"],
            "trace checksum mismatch",
        )
        episode = read_json(path)
        key = episode["environment_id"], episode["reader"], episode["seed"]
        require(key in expected_conditions and key not in seen, "foreign or duplicate condition")
        seen.add(key)
        require(
            episode["protocol_hash"] == manifest["protocol_hash"]
            and episode["capacity"] == protocol["capacity"]
            and episode["split"] == protocol["split"],
            "episode not bound to frozen configuration",
        )
        require(
            len(episode["trajectory"]) <= protocol["external_step_cap"], "episode exceeds step cap"
        )
        require(
            all(entry[k] == episode[k] for k in ("environment_id", "reader", "seed", "costs"))
            and all(entry[k] == v for k, v in episode["result"].items()),
            "episode table contradicts raw trace",
        )
        audits.append(audit_dependency_episode(episode, declared))
    require(seen == expected_conditions, "missing comparison conditions")
    for summary in report["summaries"]:
        rows = [
            e
            for e in report["episodes"]
            if e["environment_id"] == summary["environment_id"] and e["reader"] == summary["reader"]
        ]
        require(
            summary["episodes"] == len(rows)
            and summary["successes"] == sum(r["success"] for r in rows)
            and summary["mean_steps"] == sum(r["steps"] for r in rows) / len(rows)
            and summary["mean_return"] == sum(r["return"] for r in rows) / len(rows),
            "false outcome aggregate",
        )
        require(
            summary["errors"] == sum(r["error"] is not None for r in rows)
            and summary["truncations"] == sum(r["truncated"] for r in rows)
            and summary["cutoffs"] == sum(r["external_cutoff"] for r in rows),
            "false failure aggregate",
        )
        require(
            all(v == sum(r["costs"][k] for r in rows) for k, v in summary["costs"].items()),
            "false cost aggregate",
        )
    return {
        "all_passed": True,
        "episodes_checked": len(audits),
        "official_transitions_checked": sum(a["steps_checked"] for a in audits),
        "fact_versions_checked": sum(a["facts_checked"] for a in audits),
        "seed_query_routes_checked": sum(a["routes_checked"] for a in audits),
        "dependency_reads_checked": sum(a["dependency_reads_checked"] for a in audits),
        "bundles_checked": sum(a["bundles_checked"] for a in audits),
        "historical_facts_returned": sum(a["historical_facts_returned"] for a in audits),
        "raw_fact_json_bytes": sum(a["raw_fact_json_bytes"] for a in audits),
        "mask_json_bytes": sum(a["mask_json_bytes"] for a in audits),
        "successes": sum(a["success"] for a in audits),
        "unrecorded_work_categories": sorted(set(WORK_KEYS) - set(declared)),
        "scope": "official replay and independent seed numerics, observed-head/mask identity, nomination, path/key/halo support, whole-bundle packing, known residual omissions and declared work events; no semantic correctness certificate or ZHA-advantage claim",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit_directory(args.results), indent=2))


if __name__ == "__main__":
    main()
