import copy
import hashlib
import json
from pathlib import Path

import pytest

from research.prepare_gpt2 import book_body
from research.protocol import validate_protocol


def protocol():
    config = json.loads(
        (Path(__file__).resolve().parents[1] / "research/gpt2_pilot.json").read_text()
    )
    documents = [
        {
            "book_id": identifier,
            "split": split,
            "body_sha256": hashlib.sha256(str(identifier).encode()).hexdigest(),
        }
        for split, ids in config["splits"].items()
        for identifier in ids
    ]
    return config, {
        "schema_version": 1,
        "model_id": config["model_id"],
        "model_revision": config["model_revision"],
        "documents": documents,
    }


def test_predeclared_protocol_has_disjoint_documents_and_windows():
    validate_protocol(*protocol())


def test_reused_document_id_or_content_cannot_be_called_held_out():
    config, manifest = protocol()
    reused = copy.deepcopy(config)
    reused["splits"]["test"][0] = reused["splits"]["train"][0]
    with pytest.raises(ValueError, match="duplicate"):
        validate_protocol(reused, manifest)
    manifest["documents"][-1]["body_sha256"] = manifest["documents"][0]["body_sha256"]
    with pytest.raises(ValueError, match="duplicate document content"):
        validate_protocol(config, manifest)


def test_gutenberg_wrapper_is_excluded_from_corpus():
    text = "metadata\n*** START OF THE PROJECT GUTENBERG EBOOK EXAMPLE ***\nBody goes here.\n*** END OF THE PROJECT GUTENBERG EBOOK EXAMPLE ***\nlicense"
    assert book_body(text) == "Body goes here."
    with pytest.raises(ValueError):
        book_body("No verified boundaries")
