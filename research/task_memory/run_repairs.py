"""Reviewed progress repairs, kept separate from the frozen v1 policy."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from research.persistent_task_memory import Backend
from research.run_persistent_tasks import persistent_episode
from research.task_memory.run_study import main as study_main
from research.task_memory.support import SupportTaskReader
from research.task_references import RouterCheckpoint
from research.task_store import WorkspaceConfig

PROTOCOL = json.loads(Path(__file__).with_name("repair_protocol.json").read_text())


def run(
    condition: str,
    path: Path,
    env: str,
    seed: int,
    checkpoint: RouterCheckpoint,
    *,
    cap: int = 256,
    on_step: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if condition not in PROTOCOL["conditions"]:
        raise ValueError("unsupported repaired support condition")
    repaired = condition.startswith("repaired_")
    backend: Backend = (
        "exact" if condition.endswith("exact") else "none" if condition.endswith("graph") else "zha"
    )
    result = persistent_episode(
        path,
        env,
        seed,
        checkpoint,
        backend,
        cap,
        workspace=WorkspaceConfig(**PROTOCOL["workspace"]),
        reader_factory=lambda s, c: SupportTaskReader(
            s, c, backend=backend, progress_repairs=repaired
        ),
        progress_repairs=repaired,
        on_step=on_step,
    )
    result["condition"] = condition
    return result


if __name__ == "__main__":
    study_main(protocol=PROTOCOL, runner=run)
