"""Local JSON-lines interface to the experimental archive and session controller.

No LLM, embedding model, networking or model-specific KV is involved. Original
records persist; session-use metadata restarts. See docs/MEMORY_LIFECYCLE.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, TextIO, cast

from research.memory_lifecycle import (
    POLICIES,
    Archive,
    Config,
    LifecycleError,
    MemorySession,
    Policy,
)


def dispatch(session: MemorySession, request: Any) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise LifecycleError("request must be an object")
    operation = request.get("operation")
    if operation == "remember":
        if set(request) != {"operation", "identifier", "key", "text", "tick"}:
            raise LifecycleError("remember requires operation, identifier, key, text, tick only")
        record = session.remember(
            request["identifier"], request["key"], request["text"], request["tick"]
        )
        return {
            "ok": True,
            "operation": operation,
            "record": asdict(record),
            "active": session.active_ids,
        }
    if operation == "query":
        if set(request) != {"operation", "text", "tick"}:
            raise LifecycleError("query requires operation, text, tick only")
        return {
            "ok": True,
            "operation": operation,
            **asdict(session.query(request["text"], request["tick"])),
        }
    if operation == "status":
        if set(request) != {"operation"}:
            raise LifecycleError("status accepts operation only")
        return {
            "ok": True,
            "operation": operation,
            "policy": session.config.policy,
            "tick": session.tick,
            "queries_this_session": session.queries,
            "original_records": session.archive.count,
            "active": session.active_ids,
            "active_utf8_payload_bytes": session.active_text_bytes,
            "controller_state_persistent": False,
        }
    raise LifecycleError("operation must be remember, query or status")


def serve(session: MemorySession, source: TextIO, destination: TextIO) -> int:
    while line := source.readline(65537):
        if len(line) > 65536:
            destination.write(
                json.dumps({"ok": False, "error": "request exceeds 65536 characters; stopping"})
                + "\n"
            )
            destination.flush()
            return 2
        try:
            request = json.loads(line)
            result = dispatch(session, request)
        except (json.JSONDecodeError, LifecycleError) as error:
            result = {"ok": False, "error": str(error)}
        destination.write(json.dumps(result, ensure_ascii=False) + "\n")
        destination.flush()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--capacity", type=int, default=8)
    parser.add_argument("--policy", choices=POLICIES, default="decay_replay")
    args = parser.parse_args()
    config = Config(policy=cast(Policy, args.policy), capacity=args.capacity)
    archive = Archive(args.archive)
    try:
        return serve(MemorySession(archive, config), sys.stdin, sys.stdout)
    finally:
        archive.close()


if __name__ == "__main__":
    sys.exit(main())
