"""Experiment protocol checks, including document-level holdout isolation."""

import re
from itertools import pairwise


def validate_protocol(config: dict, manifest: dict) -> None:
    if config.get("schema_version") != 1 or manifest.get("schema_version") != 1:
        raise ValueError("unsupported experiment schema")
    for field in ("model_id", "model_revision"):
        if config.get(field) != manifest.get(field):
            raise ValueError(f"model identity mismatch: {field}")
    if not re.fullmatch(r"[0-9a-f]{40}", config["model_revision"]):
        raise ValueError("model must be pinned to a commit")
    context = config["context_tokens"]
    if type(context) is not int or not 1 <= context <= 1024:
        raise ValueError("invalid GPT-2 context length")
    positions = config["query_positions"]
    if (
        not positions
        or positions != sorted(set(positions))
        or any(type(p) is not int or not 0 <= p < context for p in positions)
    ):
        raise ValueError("invalid query positions")
    offsets = config["window_offsets"]
    if (
        not offsets
        or offsets != sorted(set(offsets))
        or any(type(x) is not int or x < 0 for x in offsets)
    ):
        raise ValueError("invalid token offsets")
    if any(b - a < context for a, b in pairwise(offsets)):
        raise ValueError("within-document windows must not overlap")
    split_ids = config["splits"]
    if set(split_ids) != {"train", "validation", "test"} or any(
        not ids for ids in split_ids.values()
    ):
        raise ValueError("all three nonempty splits are required")
    owners = {}
    for split, ids in split_ids.items():
        for identifier in ids:
            if type(identifier) is not int or identifier <= 0 or identifier in owners:
                raise ValueError("duplicate/invalid document ID across splits")
            owners[identifier] = split
    documents = manifest["documents"]
    if len(documents) != len(owners) or {d["book_id"] for d in documents} != set(owners):
        raise ValueError("manifest corpus does not match protocol")
    seen_bodies = set()
    for doc in documents:
        if owners[doc["book_id"]] != doc["split"]:
            raise ValueError("manifest split mismatch")
        if not re.fullmatch(r"[0-9a-f]{64}", doc["body_sha256"]):
            raise ValueError("invalid document content hash")
        if doc["body_sha256"] in seen_bodies:
            raise ValueError("duplicate document content; holdout is not independent")
        seen_bodies.add(doc["body_sha256"])
