"""Pin the fresh cost-quality corpus without running any model evaluation."""

import hashlib
import json
from pathlib import Path

from .cost_quality import validate_study
from .prepare_gpt2 import book_body, download_book, sha256_file

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    config = json.loads((ROOT / "research/cost_quality_protocol.json").read_text())
    previous = json.loads((ROOT / "research/gpt2_data_manifest.json").read_text())
    previous_cache = ROOT / ".cache/gpt2-pilot"
    cache = ROOT / ".cache/cost-quality-v1"
    cache.mkdir(parents=True, exist_ok=True)
    model_path = Path((previous_cache / "model_path.txt").read_text())
    if (
        model_path.name != config["model_revision"]
        or sha256_file(model_path / "model.safetensors") != previous["model_weights_sha256"]
    ):
        raise ValueError("pinned pilot model unavailable or changed; prepare the GPT-2 pilot first")
    records = []
    for split, identifiers in config["splits"].items():
        for identifier in identifiers:
            destination = cache / f"book-{identifier}.txt"
            url = f"https://www.gutenberg.org/ebooks/{identifier}.txt.utf-8"
            if not destination.exists():
                old = previous_cache / destination.name
                raw = old.read_bytes() if old.exists() else download_book(url)
                destination.write_bytes(raw)
            raw = destination.read_bytes()
            body = book_body(raw.decode("utf-8-sig"))
            records.append(
                {
                    "book_id": identifier,
                    "split": split,
                    "source": url,
                    "raw_sha256": hashlib.sha256(raw).hexdigest(),
                    "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
                    "bytes": len(raw),
                }
            )
            print(f"Pinned {split} book {identifier}: {len(raw)} bytes", flush=True)
    old_hashes = {doc["body_sha256"] for doc in previous["documents"]}
    if any(doc["body_sha256"] in old_hashes for doc in records if doc["split"] == "test"):
        raise ValueError("fresh test content duplicates previous corpus")
    manifest = {
        "schema_version": 1,
        "model_id": config["model_id"],
        "model_revision": config["model_revision"],
        "model_weights_sha256": previous["model_weights_sha256"],
        "documents": records,
    }
    validate_study(config, manifest)
    destination = ROOT / "research/cost_quality_manifest.json"
    if destination.exists() and json.loads(destination.read_text()) != manifest:
        raise ValueError("sources changed against pinned cost-quality manifest")
    destination.write_text(json.dumps(manifest, indent=2) + "\n")
    (cache / "model_path.txt").write_text(str(model_path))
    print("Manifest pinned. Commit the protocol and source before running the study.", flush=True)


if __name__ == "__main__":
    main()
