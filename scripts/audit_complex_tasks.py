"""Independent primitive-state and scalar-read audit for complex-task artifacts.

This module deliberately never imports the production puzzle simulator, planner,
feature codec, or hierarchical reader. Synthetic fixtures test this auditor;
official-data executions are audited separately by the command-line entry point.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import itertools
import json
import math
from collections import deque
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any


class AuditError(ValueError):
    """Recorded evidence disagrees with independently reconstructed state."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


@dataclass(frozen=True)
class Board:
    rows: tuple[str, ...]
    width: int
    height: int
    floor: frozenset[tuple[int, int]]
    goals: frozenset[tuple[int, int]]
    player: tuple[int, int]
    boxes: frozenset[tuple[int, int]]


@dataclass(frozen=True)
class Position:
    player: tuple[int, int]
    boxes: frozenset[tuple[int, int]]


DIRS = {"U": (0, -1), "R": (1, 0), "D": (0, 1), "L": (-1, 0)}


def parse_board(rows: list[str] | tuple[str, ...]) -> Board:
    require(bool(rows) and 0 < len(rows[0]) <= 40 and len(rows) <= 40, "board size")
    require(
        all(len(row) == len(rows[0]) and not set(row) - set("# @$.*+") for row in rows),
        "board symbols/rectangle",
    )
    cells = {(x, y): c for y, row in enumerate(rows) for x, c in enumerate(row)}
    floor = frozenset(p for p, c in cells.items() if c != "#")
    goals = frozenset(p for p, c in cells.items() if c in ".*+")
    boxes = frozenset(p for p, c in cells.items() if c in "$*")
    players = [p for p, c in cells.items() if c in "@+"]
    require(len(players) == 1 and 1 <= len(boxes) == len(goals) <= 4, "board actors")
    return Board(tuple(rows), len(rows[0]), len(rows), floor, goals, players[0], boxes)


def parse_source(text: str) -> dict[int, Board]:
    result: dict[int, Board] = {}
    for block in text.split(";")[1:]:
        header, *lines = block.splitlines()
        identifier = int(header.strip())
        require(identifier not in result, "duplicate source ID")
        result[identifier] = parse_board([line for line in lines if line != ""])
    require(bool(result), "missing source levels")
    return result


def position(board: Board, row: dict[str, Any]) -> Position:
    player, boxes = row["player"], row["boxes"]
    require(type(player) is int and all(type(b) is int for b in boxes), "noninteger cell")
    require(
        0 <= player < board.width * board.height
        and all(0 <= b < board.width * board.height for b in boxes),
        "cell outside board",
    )
    state = Position(
        (player % board.width, player // board.width),
        frozenset((b % board.width, b // board.width) for b in boxes),
    )
    require(len(state.boxes) == len(boxes) == len(board.boxes), "box conservation")
    require(
        state.player in board.floor - state.boxes and state.boxes <= board.floor,
        "occupied/wall state",
    )
    return state


def replay(board: Board, moves: str, start: Position | None = None) -> tuple[Position, int]:
    state = start or Position(board.player, board.boxes)
    pushes = 0
    require(len(moves) <= 200000, "oversized move sequence")
    for action in moves:
        require(action in DIRS, "unknown primitive action")
        dx, dy = DIRS[action]
        nxt = state.player[0] + dx, state.player[1] + dy
        require(nxt in board.floor, "illegal walk into wall")
        boxes = set(state.boxes)
        if nxt in boxes:
            beyond = nxt[0] + dx, nxt[1] + dy
            require(beyond in board.floor and beyond not in boxes, "illegal box push")
            boxes.remove(nxt)
            boxes.add(beyond)
            pushes += 1
        state = Position(nxt, frozenset(boxes))
    return state, pushes


def region(board: Board, state: Position) -> set[tuple[int, int]]:
    found = {state.player}
    todo = deque([state.player])
    while todo:
        x, y = todo.popleft()
        for dx, dy in DIRS.values():
            p = x + dx, y + dy
            if p in board.floor - state.boxes and p not in found:
                found.add(p)
                todo.append(p)
    return found


def symmetry(board: Board) -> str:
    variants = []
    for reflected, turns in itertools.product((False, True), range(4)):
        groups = []
        for cells in (
            board.floor,
            board.goals,
            board.boxes,
            region(board, Position(board.player, board.boxes)),
        ):
            changed = []
            for x, y in cells:
                if reflected:
                    x = board.width - 1 - x
                width, height = board.width, board.height
                for _ in range(turns):
                    x, y, width, height = height - 1 - y, x, height, width
                changed.append((x, y))
            groups.append(sorted(changed))
        variants.append(json.dumps(groups, separators=(",", ":")))
    return hashlib.sha256(min(variants).encode()).hexdigest()


def lower_bound(board: Board, state: Position) -> float:
    costs = []
    for goal in sorted(board.goals):
        distance = {goal: 0}
        todo = deque([goal])
        while todo:
            x, y = todo.popleft()
            for dx, dy in DIRS.values():
                previous, support = (x - dx, y - dy), (x - 2 * dx, y - 2 * dy)
                if previous in board.floor and support in board.floor and previous not in distance:
                    distance[previous] = distance[x, y] + 1
                    todo.append(previous)
        costs.append(distance)
    return min(
        sum(costs[g].get(box, math.inf) for box, g in zip(sorted(state.boxes), order, strict=True))
        for order in itertools.permutations(range(len(costs)))
    )


def features(board: Board, state: Position) -> list[float]:
    walls: list[float] = []
    goals: list[float] = []
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            near = [(x + dx, y + dy) for x, y in state.boxes]
            walls.extend(
                (
                    sum(p not in board.floor for p in near) / 4,
                    sum(p in state.boxes and (dx != 0 or dy != 0) for p in near) / 4,
                )
            )
            goals.append(sum(p in board.goals for p in near) / 4)
    distances = sorted(
        min(abs(x - gx) + abs(y - gy) for gx, gy in board.goals) / 20 for x, y in state.boxes
    )
    raw = [
        1.0,
        *walls,
        *goals,
        *distances,
        *([0.0] * (4 - len(distances))),
        lower_bound(board, state) / 40,
        len(region(board, state)) / 100,
        len(state.boxes & board.goals) / 4,
    ]
    norm = math.sqrt(sum(x * x for x in raw))
    return [x * 12 / norm for x in raw]


def close_vector(actual: list[float], expected: list[float], message: str) -> None:
    require(
        len(actual) == len(expected)
        and all(
            math.isfinite(a) and math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
            for a, b in zip(actual, expected, strict=True)
        ),
        message,
    )


def read_parameters(cases: list[dict[str, Any]], method: str) -> tuple[Any, Any, Any]:
    import numpy as np

    keys = np.asarray([[0.0] * len(cases[0]["feature"]), *(case["feature"] for case in cases)])
    values = np.asarray([0.0, *(case["remaining_pushes"] - case["lower_bound"] for case in cases)])
    if method == "random_values":
        values[1:] = np.random.default_rng(23).permutation(values[1:])
    coefficients = None
    if method == "linear":
        design = np.column_stack((np.ones(len(cases)), keys[1:]))
        coefficients = np.linalg.solve(
            design.T @ design + np.eye(keys.shape[1] + 1) * 0.1, design.T @ values[1:]
        )
    return keys, values, coefficients


def audit_read(
    read: dict[str, Any],
    cases: list[dict[str, Any]],
    method: str,
    parameters: tuple[Any, Any, Any] | None = None,
) -> None:
    import numpy as np

    query = read["query"]
    keys, values, coefficients = parameters or read_parameters(cases, method)
    if method == "linear":
        expected = float(np.r_[1.0, query] @ coefficients)
        require(
            read["selected_count"] == read["raw_key_scores"] == read["summary_dot_products"] == 0,
            "linear attention accounting",
        )
    else:
        scores = (np.asarray(keys) @ np.asarray(query) / math.sqrt(len(query))).tolist()
        selected = read["selected_ids"]
        if selected is None:
            require(method in ("dense", "random_values"), "missing selected IDs")
            selected = list(range(len(keys)))
        require(
            bool(selected)
            and len(set(selected)) == len(selected)
            and all(type(i) is int and 0 <= i < len(keys) for i in selected),
            "invalid selected IDs",
        )
        require(0 in selected, "missing attention sink")
        if method == "top16":
            exact = sorted(range(len(keys)), key=lambda i: (-scores[i], i))[:16]
            if 0 not in exact:
                exact.append(0)
            require(selected == exact, "incorrect exact top16 selection")
        require(read["selected_count"] == len(selected), "selected count")
        require(
            read["raw_key_scores"] == (len(selected) if method == "zha" else len(keys)),
            "key work",
        )
        if method != "zha":
            require(read["summary_dot_products"] == 0, "nonhierarchical summary work")
        shift = max(scores[i] for i in selected)
        weights = [math.exp(scores[i] - shift) for i in selected]
        expected = float(
            sum(w * values[i] for w, i in zip(weights, selected, strict=True)) / sum(weights)
        )
    require(
        math.isclose(read["value"], expected, rel_tol=1e-8, abs_tol=1e-8),
        "incorrect scalar selected read",
    )


def audit_boxoban(run: dict[str, Any], cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    require(run["schema"] == "boxoban-search-v1", "search schema")
    board = parse_board(run["rows"])
    require(run["level_hash"] == digest({"rows": run["rows"]}), "board hash")
    require(run["success"] is (run["status"] == "solved"), "success/status mismatch")
    require(
        run["status"]
        in (
            "solved",
            "exhausted",
            "expansion_limit",
            "wall_timeout",
            "retrieval_budget",
        ),
        "unknown search status",
    )
    require(
        len(run["expanded_trace"]) == run["expanded"] <= run["expansion_limit"],
        "expansion cap/count",
    )
    require(run["wall_seconds"] >= 0 and run["wall_limit"] > 0, "wall-time accounting")
    if run["status"] == "expansion_limit":
        require(
            run["expanded"] == run["expansion_limit"],
            "premature expansion-limit failure",
        )
    if run["status"] == "wall_timeout":
        require(run["wall_seconds"] >= run["wall_limit"], "premature wall-time failure")
    observed_frontier = {(Position(board.player, board.boxes), 0)}
    for row in run["expanded_trace"]:
        state = position(board, row)
        require(
            (state, row["pushes"]) in observed_frontier,
            "expanded state has no legal earlier-parent witness",
        )
        free = region(board, state)
        for box in state.boxes:
            for dx, dy in DIRS.values():
                support, target = (box[0] - dx, box[1] - dy), (box[0] + dx, box[1] + dy)
                if support in free and target in board.floor - state.boxes:
                    nxt = Position(box, (state.boxes - {box}) | {target})
                    observed_frontier.add((nxt, row["pushes"] + 1))
        require(row["pushes"] >= 0 and row["frontier"] >= 0, "negative search state count")
    checked_pushes = 0
    if run["success"]:
        require(bool(run["path"]), "success without path")
        state = Position(board.player, board.boxes)
        macros = []
        for i, row in enumerate(run["path"]):
            macro = row["moves_from_previous"]
            require(i != 0 or macro == "", "root macro must be empty")
            state, pushes = replay(board, macro, state)
            require(pushes == (0 if i == 0 else 1), "macro must contain exactly one push")
            checked_pushes += pushes
            require(
                position(board, row) == state and row["pushes"] == checked_pushes,
                "intermediate state/push mismatch",
            )
            macros.append(macro)
        require("".join(macros) == run["moves"], "macro/full moves mismatch")
        require(
            state.boxes == board.goals and checked_pushes == run["pushes"],
            "false goal/push count",
        )
    else:
        require(
            not run["path"] and run["moves"] == "" and run["pushes"] is None,
            "failed run carries solved path",
        )
    reads = run["reads"]
    work = run["read_work"]
    if work:
        require(
            all(isinstance(v, int | float) and math.isfinite(v) and v >= 0 for v in work.values()),
            "invalid work counter",
        )
        require(work["calls"] == len(reads) + work["failed_calls"], "read-call count")
        require(
            work["raw_key_scores"] == sum(r["raw_key_scores"] for r in reads),
            "total key work",
        )
        require(
            work["raw_value_reads"] == sum(r["selected_count"] for r in reads),
            "total value work",
        )
        require(
            work["summary_dot_products"] == sum(r["summary_dot_products"] for r in reads),
            "total summary work",
        )
        require(
            work["failed_query_work_unknown"] == work["failed_calls"],
            "failed query accounting",
        )
        require(
            run["status"] != "retrieval_budget" or work["failed_calls"] > 0,
            "unrecorded retrieval failure",
        )
    else:
        require(not reads and run["method"] == "matching", "missing work counters")
    parameters = read_parameters(cases, run["method"]) if cases is not None else None
    feature_cache = {}
    for read in reads:
        state = position(board, read)
        if state not in feature_cache:
            feature_cache[state] = features(board, state)
        close_vector(read["query"], feature_cache[state], "query provenance/geometry mismatch")
        if cases is not None:
            audit_read(read, cases, run["method"], parameters)
    guidance: dict[Position, float] = {}
    for read in reads:
        state = position(board, read)
        gap = max(0.0, min(40.0, float(read["value"])))
        require(
            state not in guidance or math.isclose(guidance[state], gap, abs_tol=1e-9),
            "inconsistent repeated-state guidance",
        )
        guidance[state] = gap
    for i, row in enumerate(run["expanded_trace"]):
        state = position(board, row)
        bound = lower_bound(board, state)
        if i == 0:
            expected_priority = bound
        else:
            if run["method"] == "matching" or state.boxes == board.goals:
                gap = 0.0
            else:
                require(state in guidance, "expanded state lacks recalled guidance")
                gap = guidance[state]
            expected_priority = row["pushes"] + run["weight"] * (bound + gap)
        require(
            math.isclose(row["priority"], expected_priority, rel_tol=1e-9, abs_tol=1e-9),
            "expanded priority ignores or contradicts recalled guidance",
        )
    return {
        "status": "pass",
        "split": run["split"],
        "level_id": run["level_id"],
        "method": run["method"],
        "success": run["success"],
        "pushes_checked": checked_pushes,
        "reads_checked": len(reads),
        "priorities_checked": len(run["expanded_trace"]),
    }


def read_json(path: Path) -> Any:
    data = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
    # Long official episodes retain every adaptive route and can exceed64MiB.
    require(len(data) <= 128 * 1024 * 1024, "oversized artifact")
    return json.loads(data)


def mini_observation(observation: dict[str, Any]) -> dict[str, Any]:
    return {
        "image": observation["image"].tolist(),
        "direction": int(observation["direction"]),
        "mission": observation["mission"],
    }


def mini_visible(
    observation: dict[str, Any], pose: list[int]
) -> dict[tuple[int, int], tuple[int, int, int, bool]]:
    """Independent projection of the official egocentric encoded observation."""
    x, y, direction = pose
    compass = ((1, 0), (0, 1), (-1, 0), (0, -1))
    dx, dy = compass[direction]
    rx, ry = compass[(direction + 1) % 4]
    cells = {}
    for u, column in enumerate(observation["image"]):
        for v, encoded in enumerate(column):
            obj, color, state = encoded
            if obj == 0:
                continue
            point = x + dx * (6 - v) + rx * (u - 3), y + dy * (6 - v) + ry * (u - 3)
            cells[point] = (1, 0, 0) if (u, v) == (3, 6) else (obj, color, state)
    result = {}
    for point, (obj, color, state) in cells.items():
        free_directions = [
            i
            for i, (sx, sy) in enumerate(compass)
            if cells.get((point[0] + sx, point[1] + sy), (0, 0, 0))[0] in (1, 3, 8)
        ]
        cue = obj in (5, 6) and any(
            (a - b) % 2 == 1 for a in free_directions for b in free_directions
        )
        result[point] = obj, color, state, cue
    return result


def mini_feature(fact: dict[str, Any]) -> list[float]:
    spatial = [
        2 * function(frequency * math.pi * coordinate / 128)
        for coordinate in (fact["x"], fact["y"])
        for frequency in (1, 2, 4)
        for function in (math.cos, math.sin)
    ]
    feature = spatial + [0.0] * 18
    feature[12 + fact["object"]] = 4.0
    feature[23 + fact["color"]] = 2.0
    feature[29] = 6.0 * fact["cue"]
    return feature


def mini_queries(pose: list[int], mission: str) -> list[list[float]]:
    local = mini_feature({"x": pose[0], "y": pose[1], "object": 0, "color": 0, "cue": False})
    local[12:] = [0.0] * 18
    task = [0.0] * 30
    task[20], task[17], task[16] = 8.0, 6.0, 4.0
    if "pick up" in mission:
        kind = next((name for name in ("ball", "box", "key") if name in mission), "ball")
        task[12 + {"ball": 6, "box": 7, "key": 5}[kind]] = 8.0
        for name, index in {
            "red": 0,
            "green": 1,
            "blue": 2,
            "purple": 3,
            "yellow": 4,
            "grey": 5,
        }.items():
            if name in mission:
                task[23 + index] = 3.0
    result = [local, task]
    if "matching" in mission:
        sample = [0.0] * 30
        sample[29] = 8.0
        result.append(sample)
    return result


def audit_minigrid(episode: dict[str, Any]) -> dict[str, Any]:
    """Replay in pinned official MiniGrid, independently bind every fact to sight.

    The auditor may inspect the environment for scoring pose, but never passes
    telemetry to a controller. This establishes trace/provenance correctness;
    separate policy information-flow tests establish controller isolation.
    """
    import gymnasium as gym
    import minigrid  # noqa: F401 - registers the official environments
    import numpy as np

    require(
        version("minigrid") == "3.1.0" and version("gymnasium") == "1.4.0",
        "unreviewed environment version",
    )
    env: Any = gym.make(episode["environment_id"], **episode.get("environment_kwargs", {}))
    archive: dict[int, dict[str, Any]] = {}
    heads: dict[tuple[int, int], int] = {}
    last_seen: dict[int, int] = {}
    reward_sum = 0.0
    observed_success = False
    checked_routes = 0
    pass_work = {"routing_passes": 0, "full_candidate_fallbacks": 0}
    recent: deque[list[int]] = deque(maxlen=16)
    cumulative = {
        name: 0
        for name in (
            "scored_nodes",
            "summary_dot_products",
            "raw_attention_pairs",
            "rerank_pairs",
            "exact_score_pairs",
            "returned_facts",
        )
    }
    try:
        obs, _ = env.reset(seed=episode["seed"])
        origin = tuple(int(v) for v in env.unwrapped.agent_pos)
        ended = False
        for step, row in enumerate(episode["trajectory"]):
            require(
                not ended and row["step"] == step,
                "trajectory continues after terminal or skips step",
            )
            serialized = mini_observation(obs)
            require(row["observation"] == serialized, "fabricated pre-action observation")
            decision = row["decision"]
            expected_pose = [
                int(env.unwrapped.agent_pos[0]) - origin[0],
                int(env.unwrapped.agent_pos[1]) - origin[1],
                int(obs["direction"]),
            ]
            require(
                decision["pose"] == expected_pose,
                "pose disagrees with official executed egomotion",
            )
            visible = mini_visible(serialized, expected_pose)
            expected_current = [
                {
                    "id": 0,
                    "x": point[0],
                    "y": point[1],
                    "object": tile[0],
                    "color": tile[1],
                    "state": tile[2],
                    "first_seen": step,
                    "observed_step": step,
                    "previous": None,
                    "cue": tile[3],
                }
                for point, tile in visible.items()
            ]
            require(
                decision["current_facts"] == expected_current,
                "current view includes unseen/fabricated facts",
            )
            require(
                decision["recent_history"] == list(recent),
                "controller history exceeds observed16-pose prefix",
            )
            recent.append(expected_pose)
            additions = row["new_facts"]
            admitted = []
            for point, (obj, color, state, cue) in visible.items():
                previous_id = heads.get(point)
                previous = archive.get(previous_id or 0)
                sticky_cue = cue or bool(
                    previous
                    and (previous["object"], previous["color"]) == (obj, color)
                    and previous["cue"]
                )
                if previous is not None and (
                    previous["object"],
                    previous["color"],
                    previous["state"],
                    previous["cue"],
                ) == (obj, color, state, sticky_cue):
                    require(previous_id is not None, "missing previous version")
                    last_seen[int(previous["id"])] = step
                    continue
                candidates = [f for f in additions if (f["x"], f["y"]) == point]
                require(len(candidates) == 1, "missing/duplicate observed fact")
                fact = candidates[0]
                require(
                    fact["id"] == len(archive) + 1 and fact["previous"] == previous_id,
                    "fact ID/version chain",
                )
                require(
                    (fact["object"], fact["color"], fact["state"], fact["cue"])
                    == (obj, color, state, sticky_cue),
                    "fact not supported by visible tile/topology",
                )
                require(
                    fact["observed_step"] == step
                    and fact["first_seen"] == (previous["first_seen"] if previous else step),
                    "future/fabricated fact timestamp",
                )
                archive[fact["id"]] = fact
                admitted.append(fact)
                heads[point] = fact["id"]
                last_seen[fact["id"]] = step
            require(additions == admitted, "unobserved/duplicate addition")
            carried = serialized["image"][3][6]
            inventory = carried[:2] if carried[0] in (5, 6, 7) else None
            require(
                decision["inventory"] == inventory,
                "inventory not supported by current image",
            )
            current = [archive[i] for i in sorted(heads.values())]
            memory_ids = decision["memory_ids"]
            require(
                len(set(memory_ids)) == len(memory_ids) and set(memory_ids) <= set(heads.values()),
                "future/foreign/stale recalled source",
            )
            require(
                decision["memory_facts"] == [archive[i] for i in memory_ids],
                "memory source payload mismatch",
            )
            require(
                set(decision.get("goal_sources", [])) <= set(memory_ids)
                and set(decision.get("plan_fact_ids", [])) <= set(memory_ids),
                "planner source outside selected memory",
            )
            require(
                episode["reader"] == "full" or len(memory_ids) <= episode["capacity"],
                "active capacity overflow",
            )
            queries = mini_queries(expected_pose, serialized["mission"])
            require(len(queries) == len(decision["queries"]), "query count")
            for actual, expected in zip(decision["queries"], queries, strict=True):
                close_vector(actual, expected, "query uses unobserved information")
            reader = episode["reader"]
            route = decision["route"]
            candidate_ids = sorted(heads.values())
            keys = np.asarray([[0.0] * 30, *(mini_feature(f) for f in current)])
            if reader in ("zha", "zha_adaptive"):
                schedule = (0.4, 0.6, 0.8, 0.95, 1.0) if reader == "zha_adaptive" else (0.4,)
                require(
                    len(route) > 0
                    and len(route) % len(queries) == 0
                    and len(route) // len(queries) <= len(schedule),
                    "missing/extra hierarchy attempt routes",
                )
                attempts = len(route) // len(queries)
                pass_work["routing_passes"] += attempts
                logical_union: set[int] = set()
                for route_number, routed in enumerate(route):
                    attempt, q = divmod(route_number, len(queries))
                    require(
                        routed.get("attempt", 0) == attempt
                        and routed.get("p", 0.4) == schedule[attempt],
                        "adaptive attempt/p schedule mismatch",
                    )
                    ids = routed["selected_logical_ids"]
                    require(
                        routed["query_index"] == q
                        and len(set(ids)) == len(ids)
                        and 0 in ids
                        and all(0 <= i <= len(current) for i in ids),
                        "invalid logical route",
                    )
                    require(
                        routed["selected_fact_ids"] == [current[i - 1]["id"] for i in ids if i],
                        "route/index version mismatch",
                    )
                    scores = keys[ids] @ np.asarray(queries[q]) / math.sqrt(30)
                    weights = np.exp(scores - scores.max())
                    weights /= weights.sum()
                    values = np.asarray(
                        [
                            [0.0, 0.0, 0.0]
                            if i == 0
                            else [current[i - 1][name] for name in ("object", "color", "state")]
                            for i in ids
                        ]
                    )
                    close_vector(
                        routed["attention_output"],
                        (weights @ values).tolist(),
                        "hierarchical selected-output mismatch",
                    )
                    logical_union.update(i for i in ids if i)
                    if schedule[attempt] == 1.0:
                        require(
                            set(ids) == set(range(len(current) + 1)),
                            "full candidate fallback omitted originals",
                        )
                        if q == 0:
                            pass_work["full_candidate_fallbacks"] += 1
                    if reader == "zha_adaptive" and q == len(queries) - 1:
                        target = min(episode["capacity"], len(current))
                        if attempt + 1 < attempts:
                            require(
                                len(logical_union) < target,
                                "adaptive reader widened after sufficient candidate coverage",
                            )
                        else:
                            require(
                                len(logical_union) >= target,
                                "adaptive reader stopped before candidate coverage",
                            )
                    nodes = sum(len(trace["candidates"]) for trace in routed["steps"])
                    cumulative["scored_nodes"] += nodes
                    cumulative["summary_dot_products"] += nodes * 8
                    cumulative["raw_attention_pairs"] += len(ids)
                    checked_routes += 1
                candidates = sorted(logical_union)
                cumulative["rerank_pairs"] += len(candidates) * len(queries)
                candidate_ids = [current[i - 1]["id"] for i in candidates]
            elif reader == "exact":
                require(not route, "exact reader claims hierarchy")
                cumulative["exact_score_pairs"] += len(current) * len(queries)
            if reader in ("zha", "zha_adaptive", "exact"):
                by_id = {f["id"]: f for f in current}
                scores_by_id = {
                    i: max(
                        sum(a * b for a, b in zip(query, mini_feature(by_id[i]), strict=True))
                        for query in queries
                    )
                    for i in candidate_ids
                }
                expected_ids = sorted(candidate_ids, key=lambda i: (-scores_by_id[i], i))[
                    : episode["capacity"]
                ]
            elif reader == "none":
                expected_ids = []
            elif reader == "full":
                expected_ids = sorted(heads.values())
            elif reader == "fifo":
                expected_ids = sorted(heads.values())[: episode["capacity"]]
            else:
                require(reader == "recency", "unknown reader")
                expected_ids = sorted(heads.values(), key=lambda i: (-last_seen[i], -i))[
                    : episode["capacity"]
                ]
            if reader in ("zha", "zha_adaptive", "exact"):
                # Independent scalar and backend matrix reductions may reverse
                # numerical ties; validate top-k scores, never hide a real gap.
                require(
                    len(memory_ids) == len(expected_ids) and set(memory_ids) <= set(candidate_ids),
                    "reader candidate/count mismatch",
                )
                ranked_scores = [scores_by_id[i] for i in memory_ids]
                require(
                    all(a + 1e-9 >= b for a, b in itertools.pairwise(ranked_scores)),
                    "reader score ordering",
                )
                excluded = set(candidate_ids) - set(memory_ids)
                require(
                    not excluded
                    or not memory_ids
                    or max(scores_by_id[i] for i in excluded) <= min(ranked_scores) + 1e-9,
                    "reader omitted higher-scoring candidate",
                )
            else:
                require(
                    memory_ids == expected_ids,
                    "reader selection differs from observed candidates",
                )
            cumulative["returned_facts"] += len(memory_ids)
            for name, count in pass_work.items():
                if reader == "zha_adaptive" or name in decision["work"]:
                    require(
                        decision["work"].get(name) == count,
                        "adaptive pass/fallback accounting mismatch",
                    )
            require(
                all(decision["work"][k] == v for k, v in cumulative.items()),
                "cumulative reader work mismatch",
            )
            require(type(row["action"]) is int and 0 <= row["action"] <= 6, "invalid action")
            obs, reward, terminated, truncated, _ = env.step(row["action"])
            require(
                row["next_observation"] == mini_observation(obs),
                "fabricated post-action observation",
            )
            require(
                math.isclose(row["reward"], reward, abs_tol=1e-12)
                and row["terminated"] is bool(terminated)
                and row["truncated"] is bool(truncated),
                "reward/termination mismatch",
            )
            reward_sum += float(reward)
            observed_success |= float(reward) > 0
            ended = bool(terminated or truncated)
        result = episode["result"]
        for name, count in pass_work.items():
            if episode["reader"] == "zha_adaptive" or name in episode["costs"]:
                require(
                    episode["costs"].get(name) == count,
                    "episode adaptive pass/fallback accounting mismatch",
                )
        require(
            all(
                isinstance(v, int | float) and math.isfinite(v) and v >= 0
                for v in episode["costs"].values()
            ),
            "invalid episode cost",
        )
        require(
            all(episode["costs"][k] == v for k, v in cumulative.items()),
            "episode cost contradicts decision events",
        )
        for field in ("planning_seconds", "policy_seconds"):
            expected_seconds = sum(row["decision"][field] for row in episode["trajectory"])
            require(
                math.isclose(episode["costs"][field], expected_seconds, rel_tol=1e-9, abs_tol=1e-9),
                "episode timing contradicts decision events",
            )
        require(
            result["success"] is observed_success
            and math.isclose(result["return"], reward_sum, abs_tol=1e-12)
            and result["steps"] == len(episode["trajectory"]),
            "episode success/return mismatch",
        )
        require(
            episode["archive"] == list(archive.values()),
            "exported archive contains unsupported records",
        )
        require(
            result["external_cutoff"] is (not ended and result.get("error") is None),
            "external cutoff mismatch",
        )
        if episode["trajectory"]:
            require(
                result["terminated"] is episode["trajectory"][-1]["terminated"]
                and result["truncated"] is episode["trajectory"][-1]["truncated"],
                "terminal summary mismatch",
            )
        return {
            "all_passed": True,
            "environment": episode["environment_id"],
            "seed": episode["seed"],
            "steps_checked": len(episode["trajectory"]),
            "facts_checked": len(archive),
            "routes_checked": checked_routes,
            **pass_work,
            "success": observed_success,
        }
    finally:
        env.close()


def audit_directory(output: Path, data: Path) -> dict[str, Any]:
    manifest = read_json(output / "manifest.json")
    for name, info in manifest["data_manifest"]["files"].items():
        require(
            hashlib.sha256((data / name).read_bytes()).hexdigest() == info["sha256"],
            "source checksum: " + name,
        )
    for name, key in (
        ("protocol.json", "protocol_sha256"),
        ("cases.json", "cases_sha256"),
        ("cohorts.json", "cohorts_sha256"),
    ):
        require(
            hashlib.sha256((output / name).read_bytes()).hexdigest() == manifest[key],
            "frozen input checksum: " + name,
        )
    for name, expected in manifest["source_hashes"].items():
        require(
            hashlib.sha256((output / "source-snapshot" / name).read_bytes()).hexdigest()
            == expected,
            "source snapshot checksum",
        )
    sources = {
        split: parse_source(
            (data / ("validation.txt" if split == "validation" else split + ".txt")).read_text()
        )
        for split in ("train", "validation", "test", "hard")
    }
    bank = read_json(output / "cases.json")
    require(
        bank["schema"] == "boxoban-cases-v1"
        and bank["feature_version"] == "boxoban-local-geometry-v1"
        and digest(bank["cases"]) == bank["hash"],
        "case identity",
    )
    train_runs = {
        int(path.name.split("-")[1].split(".")[0]): read_json(path)
        for path in output.glob("train-*.json.gz")
    }
    cohorts = read_json(output / "cohorts.json")["cohorts"]
    protocol = read_json(output / "protocol.json")
    require(
        set(train_runs) == set(protocol["train_ids"]),
        "missing or foreign training runs",
    )
    seen = {symmetry(sources["train"][i]) for i in protocol["train_ids"]}
    for split, ids in cohorts.items():
        for identifier in ids:
            fingerprint = symmetry(sources[split][identifier])
            require(fingerprint not in seen, "train/test or evaluation symmetry duplicate")
            seen.add(fingerprint)
    checked = []
    for run in train_runs.values():
        require(
            run["split"] == "train" and run["level_id"] in protocol["train_ids"],
            "foreign training source",
        )
        require(
            tuple(run["rows"]) == sources["train"][run["level_id"]].rows,
            "training board/source mismatch",
        )
        checked.append(audit_boxoban(run))
    for case in bank["cases"]:
        require(
            case["split"] == "train" and case["level_id"] in train_runs,
            "case is not an observed training source",
        )
        run = train_runs[case["level_id"]]
        require(
            run["success"] and case["level_hash"] == run["level_hash"],
            "case source not solved/matching",
        )
        board = sources["train"][case["level_id"]]
        state = position(board, case)
        witnesses = [
            row
            for row in run["path"]
            if position(board, row) == state
            and run["pushes"] - row["pushes"] == case["remaining_pushes"]
        ]
        require(bool(witnesses), "case does not match real training suffix")
        require(case["lower_bound"] == lower_bound(board, state), "case lower bound")
        require(case["remaining_pushes"] >= case["lower_bound"], "negative case gap")
        close_vector(case["feature"], features(board, state), "case feature mismatch")
    evaluation = []
    condition_keys = set()
    configs = {name: (method, p) for name, method, p in protocol["configs"]}
    for path in sorted((output / "evaluation").glob("*.json.gz")):
        run = read_json(path)
        require(run["level_id"] in cohorts[run["split"]], "unfrozen evaluation level")
        require(
            tuple(run["rows"]) == sources[run["split"]][run["level_id"]].rows,
            "evaluation board/source mismatch",
        )
        require(
            run["case_hash"] == bank["hash"]
            and run["expansion_limit"] in protocol["expansion_limits"]
            and run["weight"] == protocol["weight"]
            and run["wall_limit"] == protocol["wall_seconds"],
            "evaluation protocol mismatch",
        )
        require(
            run["config"] in configs and (run["method"], run["p"]) == tuple(configs[run["config"]]),
            "reader/config mismatch",
        )
        condition_key = (
            run["split"],
            run["level_id"],
            run["expansion_limit"],
            run["config"],
        )
        require(condition_key not in condition_keys, "duplicated evaluation condition")
        condition_keys.add(condition_key)
        evaluation.append(audit_boxoban(run, bank["cases"]))
    report_path = output / "evaluation/report.json"
    require(report_path.is_file(), "evaluation not complete")
    report = read_json(report_path)
    require(
        report["complete"] is True and len(report["runs"]) == len(evaluation),
        "incomplete comparison",
    )
    expected_count = (
        sum(len(ids) for ids in cohorts.values())
        * len(protocol["expansion_limits"])
        * len(protocol["configs"])
    )
    require(len(evaluation) == expected_count, "missing evaluation conditions")
    for row in report["runs"]:
        require(
            hashlib.sha256((output / "evaluation" / row["file"]).read_bytes()).hexdigest()
            == row["sha256"],
            "report artifact checksum",
        )
        run = read_json(output / "evaluation" / row["file"])
        require(
            all(run[k] == v for k, v in row.items() if k not in ("file", "sha256")),
            "report row contradicts artifact",
        )
    return {
        "all_passed": True,
        "training_runs": len(checked),
        "evaluation_runs": len(evaluation),
        "cases_checked": len(bank["cases"]),
        "solved_evaluations": sum(r["success"] for r in evaluation),
        "legal_pushes_checked": sum(r["pushes_checked"] for r in checked + evaluation),
        "scalar_reads_checked": sum(r["reads_checked"] for r in evaluation),
        "priorities_checked": sum(r["priorities_checked"] for r in checked + evaluation),
        "scope": "independent replay, legal expansion witnesses, geometry/scalar reads, recalled-priority formula, frozen provenance and event counters; full heap-choice order and hierarchy router are not rederived here",
    }


def audit_minigrid_directory(output: Path) -> dict[str, Any]:
    manifest = read_json(output / "manifest.json")
    protocol = read_json(output / "protocol.json")
    raw_protocol = json.dumps(protocol, indent=2, sort_keys=True).encode()
    require(
        hashlib.sha256(raw_protocol).hexdigest() == manifest["protocol_hash"],
        "MiniGrid protocol identity",
    )
    for name, expected_hash in manifest["source_hashes"].items():
        require(
            hashlib.sha256((output / "source-snapshot" / name).read_bytes()).hexdigest()
            == expected_hash,
            "MiniGrid source snapshot hash",
        )
    require(
        protocol["official_versions"] == {"minigrid": "3.1.0", "gymnasium": "1.4.0"},
        "MiniGrid protocol versions",
    )
    require(
        not set(protocol["development_seeds"]) & set(protocol["evaluation_seeds"]),
        "MiniGrid seed overlap",
    )
    require(
        set(protocol["selected_seeds"])
        == set(
            protocol["development_seeds"]
            if protocol["split"] == "development"
            else protocol["evaluation_seeds"]
        ),
        "unfrozen MiniGrid seeds",
    )
    report = read_json(output / "report.json")
    require(report["protocol"] == protocol, "MiniGrid report protocol mismatch")
    expected_conditions = set(
        itertools.product(
            protocol["selected_environments"],
            protocol["selected_readers"],
            protocol["selected_seeds"],
        )
    )
    seen: set[tuple[str, str, int]] = set()
    audits = []
    for row in report["episodes"]:
        path = output / row["trace_file"]
        require(
            hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"],
            "MiniGrid trace checksum",
        )
        episode = read_json(path)
        key = episode["environment_id"], episode["reader"], episode["seed"]
        require(
            key in expected_conditions and key not in seen,
            "MiniGrid duplicate/foreign condition",
        )
        seen.add(key)
        require(
            episode["capacity"] == protocol["capacity"]
            and episode["split"] == protocol["split"]
            and len(episode["trajectory"]) <= protocol["external_step_cap"],
            "MiniGrid condition budget/split",
        )
        require(
            all(row[k] == episode[k] for k in ("environment_id", "reader", "seed", "costs"))
            and all(row[k] == v for k, v in episode["result"].items()),
            "MiniGrid report/trace mismatch",
        )
        audits.append(audit_minigrid(episode))
    require(seen == expected_conditions, "MiniGrid missing configurations")
    return {
        "all_passed": True,
        "episodes_checked": len(audits),
        "steps_checked": sum(a["steps_checked"] for a in audits),
        "facts_checked": sum(a["facts_checked"] for a in audits),
        "routes_checked": sum(a["routes_checked"] for a in audits),
        "routing_passes_checked": sum(a["routing_passes"] for a in audits),
        "full_candidate_fallbacks_checked": sum(a["full_candidate_fallbacks"] for a in audits),
        "successes": sum(a["success"] for a in audits),
        "scope": "official-environment replay plus observation-bound fact/version/query/selection and work audit; policy isolation needs separate information-flow tests",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--results", type=Path)
    group.add_argument("--minigrid", type=Path)
    parser.add_argument(
        "--data",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data/boxoban",
    )
    args = parser.parse_args()
    result = (
        audit_directory(args.results, args.data)
        if args.results
        else audit_minigrid_directory(args.minigrid)
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
