"""Post-hoc observed-prefix diagnosis, not a new evaluation cohort."""
from __future__ import annotations
import argparse,gzip,hashlib,json
from collections import Counter
from pathlib import Path
from typing import Any


def inspect_episode(episode: dict[str, Any]) -> dict[str, int]:
    heads: dict[tuple[int,int],dict[str,Any]] = {}
    counts: Counter[str] = Counter()
    for row in episode['trajectory']:
        for fact in row['new_facts']:
            heads[fact['x'],fact['y']] = fact
        decision = row['decision']
        returned = {(f['x'],f['y']) for f in decision['memory_facts']+decision['current_facts']}
        counts['actions'] += 1
        counts['known_landmarks_omitted'] += sum((f['x'],f['y']) not in returned for f in heads.values() if f['object'] in (4,5,6,8) or f.get('cue'))
        goal = decision.get('goal')
        if goal is not None and decision['objective'] in ('explore','scan-frontier'):
            missing = [(goal[0]+dx,goal[1]+dy) for dx,dy in ((1,0),(0,1),(-1,0),(0,-1)) if (goal[0]+dx,goal[1]+dy) not in returned]
            if missing and all(p in heads for p in missing):
                counts['frontier_only_omitted_known_cells'] += 1
                if all(heads[p]['object'] in (2,9) for p in missing):
                    counts['frontier_only_omitted_known_obstacles'] += 1
    return dict(counts)


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report_path=args.source/'report.json';report=json.loads(report_path.read_text())
    totals: dict[tuple[str,str],Counter[str]] = {}
    for entry in report['episodes']:
        path=args.source/entry['trace_file']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:
            raise ValueError('trace checksum mismatch')
        with gzip.open(path,'rt') as stream:episode=json.load(stream)
        key=episode['environment_id'],episode['reader']
        totals.setdefault(key,Counter()).update(inspect_episode(episode))
    payload={'scope':'Post-hoc development diagnosis of already evaluated traces. Uses only observed-prefix current heads. Omission boundaries do not establish globally wrong actions.','report_sha256':hashlib.sha256(report_path.read_bytes()).hexdigest(),'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'summary':[{'environment':k[0],'reader':k[1],**v} for k,v in totals.items()]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as stream:json.dump(payload,stream,indent=2)
    for row in payload['summary']:
        if row['reader'] in ('zha_adaptive','exact'):print(row)


if __name__=='__main__':main()
