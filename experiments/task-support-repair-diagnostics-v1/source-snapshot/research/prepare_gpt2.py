"""Download only the pinned public model files and a fixed book-level corpus."""

import hashlib
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def download_book(url: str) -> bytes:
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                if response.status != 200:
                    raise ValueError("expected complete HTTP 200 text")
                raw = response.read(8_000_001)
            if len(raw) > 8_000_000:
                raise ValueError("book download exceeds declared 8MB limit")
            book_body(raw.decode("utf-8-sig"))
            return raw
        except (ValueError, OSError) as error:
            print(f"Corpus transfer attempt {attempt} failed validation: {error}", flush=True)
            if attempt == 3:
                raise
    raise RuntimeError("unreachable")


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def book_body(text: str) -> str:
    start = re.search(r"\*\*\* START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK[^\n]*\n", text, re.I)
    end = re.search(r"\*\*\* END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK", text, re.I)
    if not start or not end or end.start() <= start.end():
        raise ValueError("expected explicit Gutenberg body boundaries")
    return text[start.end() : end.start()].strip()


def main() -> None:
    from huggingface_hub import snapshot_download

    config = json.loads((ROOT / "research/gpt2_pilot.json").read_text())
    cache = ROOT / ".cache/gpt2-pilot"
    cache.mkdir(parents=True, exist_ok=True)
    model = snapshot_download(
        config["model_id"],
        revision=config["model_revision"],
        cache_dir=cache / "hf",
        allow_patterns=[
            "config.json",
            "model.safetensors",
            "tokenizer.json",
            "tokenizer_config.json",
            "vocab.json",
            "merges.txt",
        ],
    )
    records = []
    for split, identifiers in config["splits"].items():
        for identifier in identifiers:
            if type(identifier) is not int or identifier < 1:
                raise ValueError("book IDs must be positive integers")
            url = f"https://www.gutenberg.org/ebooks/{identifier}.txt.utf-8"
            destination = cache / f"book-{identifier}.txt"
            if not destination.exists():
                raw = download_book(url)
                destination.write_bytes(raw)
            raw = destination.read_bytes()
            body = book_body(raw.decode("utf-8-sig"))
            record = {
                "book_id": identifier,
                "split": split,
                "source": url,
                "raw_sha256": hashlib.sha256(raw).hexdigest(),
                "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
                "bytes": len(raw),
            }
            records.append(record)
            print(f"Prepared {split} book {identifier}: {len(raw)} bytes", flush=True)
    manifest = {
        "schema_version": 1,
        "model_id": config["model_id"],
        "model_revision": config["model_revision"],
        "model_weights_sha256": sha256_file(Path(model) / "model.safetensors"),
        "documents": records,
    }
    destination = ROOT / "research/gpt2_data_manifest.json"
    if destination.exists() and json.loads(destination.read_text()) != manifest:
        raise ValueError("cached sources changed against the pinned manifest; refusing replacement")
    destination.write_text(json.dumps(manifest, indent=2) + "\n")
    (cache / "model_path.txt").write_text(model)
    print("Pinned manifest written before training", flush=True)


if __name__ == "__main__":
    main()
