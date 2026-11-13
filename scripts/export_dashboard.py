"""Export audited recordings and the existing inspector as a static Vercel site.

No mutable archives, credentials, local solve sessions or simulator workers are
published. The static site explicitly offers playback, not fresh computation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from research.serve_task_benchmark import ROOT, TaskCatalog

DATASET = "task-support-v2"
ASSETS = {
    "index.html": "web/dashboard/index.html",
    "dashboard.css": "web/dashboard/style.css",
    "dashboard.js": "web/dashboard/app.js",
    "spatial.css": "web/task-lab/spatial.css",
    "spatial.bundle.js": "web/task-lab/spatial.bundle.js",
    "geist.ttf": "web/somna-live/fonts/geist-regular.ttf",
    "geist-semibold.ttf": "web/somna-live/fonts/geist-semibold.ttf",
    **{
        f"task/{name}": f"web/task-lab/{name}"
        for name in (
            "index.html",
            "app.js",
            "style.css",
            "routing.js",
            "spatial.bundle.js",
            "spatial.css",
            "embedded.css",
            "panel-boot.js",
        )
    },
    "preview.png": "docs/media/memory-cloud-demo.png",
    "LICENSE.txt": "LICENSE",
    "THIRD_PARTY_NOTICES.md": "THIRD_PARTY_NOTICES.md",
}
CSP = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-src 'self'; frame-ancestors 'self'; object-src 'none'; base-uri 'self'"


def write_json(path: Path, value: Any) -> str:
    raw = json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def recording_path(uid: str) -> str:
    # UID text is never used as a filesystem path.
    return "/recordings/" + hashlib.sha256(uid.encode()).hexdigest() + ".json"


def export(output: Path, root: Path = ROOT) -> dict[str, Any]:
    target = output / ".vercel/output"
    if target.exists():
        raise ValueError("Use a new export directory; existing deployments are never overwritten")
    base = root / "experiments" / DATASET
    audit = json.loads((base / "INDEPENDENT_AUDIT.json").read_text())
    report = json.loads((base / "report.json").read_text())
    if not audit.get("all_passed") or not report.get("complete"):
        raise ValueError("Only a completed independently audited cohort can be exported")
    source = TaskCatalog(root)
    catalog = source.catalog()
    rows = [r for r in catalog["runs"] if r["dataset"] == DATASET]
    if len(rows) != audit["runs"] or len(rows) != len(report["runs"]) or not rows:
        raise ValueError("Hosted cohort must include every audited run, including failures")
    site = target / "static"
    site.mkdir(parents=True)
    for dest, name in ASSETS.items():
        dst = site / dest
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, dst)
        if dst.suffix == ".html":
            html = dst.read_text().replace(
                '<html lang="en">', '<html lang="en" data-hosted="recorded">'
            )
            if dest == "index.html":
                html = html.replace(
                    "<title>Memory instrument</title>", "<title>Memory Observatory</title>"
                )
                html = html.replace(
                    'content="One task, its retrieval hierarchy and its observed memory."',
                    'content="Inspect real maze experiments, hierarchical retrieval and a bounded memory workspace."',
                )
                html = html.replace(
                    "</head>",
                    '<link rel="icon" href="/favicon.svg" /><meta property="og:title" content="Memory Observatory" /><meta property="og:description" content="Real maze experiments. Hierarchical retrieval. Active and dormant memory." /><meta property="og:image" content="/preview.png" /><meta name="twitter:card" content="summary_large_image" /></head>',
                )
                html = html.replace("<h2>RUN CONFIGURATION</h2>", "<h2>MEMORY OBSERVATORY</h2>")
                html = html.replace(
                    '<button id="solve"',
                    '<p class="source-note"><a href="/data/protocol.json">Protocol</a> · <a href="/data/report.json">Results</a></p><button id="solve"',
                )
                html = html.replace(
                    "Loading recorded evidence.</p>",
                    'Recorded experiments · <a href="/data/protocol.json">Protocol</a></p>',
                )
            dst.write_text(html)
    exported = []
    for row in rows:
        artifact = recording_path(row["uid"])
        # TaskCatalog verifies frozen source checksums and official saved-action
        # replay before adapting source-owned rows for the inspector.
        payload = source.run(row["uid"])
        checksum = write_json(site / artifact.lstrip("/"), payload)
        exported.append({**row, "artifact": artifact, "artifact_sha256": checksum})
    public_catalog: dict[str, Any] = {
        "schema": "task-catalog-v1",
        "runs": exported,
        "summary": [r for r in catalog["summary"] if r.get("dataset") == DATASET],
        "deployment": {
            "mode": "recorded",
            "name": "Memory Observatory",
            "dataset": DATASET,
            "source_report_sha256": hashlib.sha256((base / "report.json").read_bytes()).hexdigest(),
        },
    }
    write_json(site / "data/catalog.json", public_catalog)
    write_json(site / "data/bank.json", {"cases": [], "boards": {}})
    write_json(
        site / "data/unavailable.json",
        {
            "error": "Recorded experiment viewer. Run the Python solver locally for fresh experiments."
        },
    )
    for name in ("report.json", "protocol.json", "INDEPENDENT_AUDIT.json"):
        shutil.copyfile(base / name, site / "data" / name)
    (site / "favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" fill="#000"/><g fill="none" stroke="#74d8d0"><path d="m3 10 13-7 13 7-13 7zM3 17l13 7 13-7M3 24l13 7 13-7"/></g></svg>'
    )
    (site / "404.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Run not found · Memory Observatory</title><link rel="stylesheet" href="/dashboard.css"><body><main><h1>Run not found</h1><p><a href="/">Return to Memory Observatory</a></p></main></body></html>'
    )
    write_json(
        target / "config.json",
        {
            "version": 3,
            "routes": [
                {
                    "src": "/(.*)",
                    "headers": {
                        "Content-Security-Policy": CSP,
                        "X-Content-Type-Options": "nosniff",
                        "Referrer-Policy": "strict-origin-when-cross-origin",
                        "X-Frame-Options": "SAMEORIGIN",
                    },
                    "continue": True,
                },
                {"src": "/api/catalog", "dest": "/data/catalog.json"},
                {"src": "/api/bank", "dest": "/data/bank.json"},
                {"src": "/api/.*", "dest": "/data/unavailable.json", "status": 405},
                {"src": "/task/?", "dest": "/task/index.html"},
                {"handle": "filesystem"},
                {"src": "/.*", "dest": "/404.html", "status": 404},
            ],
        },
    )
    manifest = {
        "schema": "static-memory-observatory-v1",
        "mode": "recorded",
        "dataset": DATASET,
        "runs": len(exported),
        "conditions": report["summary"],
        "files": {
            str(p.relative_to(site)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(site.rglob("*"))
            if p.is_file()
        },
        "source_report_sha256": public_catalog["deployment"]["source_report_sha256"],
    }
    write_json(output / "export-manifest.json", manifest)
    print(
        json.dumps(
            {
                "output": str(output),
                "runs": len(exported),
                "bytes": sum(p.stat().st_size for p in site.rglob("*") if p.is_file()),
            }
        ),
        flush=True,
    )
    return manifest


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    export(p.parse_args().output)
