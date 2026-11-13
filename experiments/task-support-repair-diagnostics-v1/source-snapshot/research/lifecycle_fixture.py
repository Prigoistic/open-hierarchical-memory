"""Authored diagnostic project stream. Labels stay outside the controller API."""

import random
from typing import Any

PROJECTS = (
    "Helix",
    "Morrow",
    "Cobalt",
    "Kestrel",
    "Juniper",
    "Vesper",
    "Tundra",
    "Orchid",
    "Harbor",
    "Saffron",
    "Birch",
    "Zephyr",
    "Quartz",
    "Ember",
    "Linden",
    "Nimbus",
    "Coral",
    "Sparrow",
    "Aspen",
    "Fjord",
    "Meridian",
    "Willow",
    "Indigo",
    "Solstice",
)


def build_stream(seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    projects = list(PROJECTS)
    rng.shuffle(projects)
    events: list[dict[str, Any]] = []
    heads: dict[str, str] = {}

    def remember(project: str, cluster: str, phase: str, version: int = 1) -> None:
        identifier = f"release-{project.lower()}-v{version}"
        heads[project] = identifier
        events.append(
            {
                "kind": "remember",
                "phase": phase,
                "identifier": identifier,
                "key": f"release/{project}",
                "text": f"Project {project} uses the {cluster} cluster for release deployment.",
            }
        )

    def query(project: str, phase: str, variant: int = 0) -> None:
        templates = (
            f"Project {project} release deployment",
            f"Which cluster does project {project} use for release deployment?",
            f"{project} release deployment cluster",
        )
        events.append(
            {
                "kind": "query",
                "phase": phase,
                "text": templates[variant % 3],
                "expected": heads[project],
            }
        )

    def distractors(start: int, count: int) -> None:
        for index in range(start, start + count):
            events.append(
                {
                    "kind": "remember",
                    "phase": "interference",
                    "identifier": f"backup-{index}",
                    "key": f"backup/{index}",
                    "text": f"The observatory backup rotation number {index} runs each weekday on storage shelf {index + 100}.",
                }
            )

    for index, project in enumerate(projects):
        remember(project, f"cedar{index}", "initial")
    for turn in range(24):
        query(projects[turn % 4], "early_repetition", turn)
    distractors(0, 32)
    delayed = projects[8:16]
    rng.shuffle(delayed)
    for turn in range(3):
        for project in delayed:
            query(project, "delayed_revisit", turn)
            query(projects[turn % 4], "interleaved_repetition", turn)
    for index, project in enumerate(projects[8:16]):
        remember(project, f"maple{index}", "correction", 2)
        query(project, "immediate_correction", 1)
    distractors(32, 16)
    for turn in range(3):
        mixed = projects[:16]
        rng.shuffle(mixed)
        for project in mixed:
            query(project, "late_revisit", turn)
    for tick, event in enumerate(events, start=1):
        event["tick"] = tick
    return events
