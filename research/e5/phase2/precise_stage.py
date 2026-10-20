"""Exact-clock staged interface for E5; historical stages are not active alternatives."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..execution.core import digest, freeze_json, utcnow
from .engine import ORDER
from .precise_engine import PreciseExecution as Execution
from .sources import eligible_universe


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=ORDER+('build-universe',))
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--manifest', action='append', type=Path, default=[])
    parser.add_argument('--previous-270', type=Path)
    parser.add_argument('--availability', type=Path)
    parser.add_argument('--power', type=Path)
    parser.add_argument('--endpoint-qualification', type=Path)
    parser.add_argument('--start')
    parser.add_argument('--end')
    parser.add_argument('--as-of', default=utcnow())
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[3]
    run = Execution(root, args.run)
    if args.stage == 'build-universe':
        result = eligible_universe(args.manifest, start=args.start, end=args.end, as_of=args.as_of)
        freeze_json(args.run/'universe.json', result)
    elif args.stage == 'protocol':
        result = run.protocol(args.input, args.power, args.endpoint_qualification)
    elif args.stage == 'cohort':
        result = run.cohort(args.input, args.previous_270, args.availability)
    elif args.stage == 'features':
        result = run.features(args.manifest)
    elif args.stage == 'predictions':
        result = run.predictions(args.manifest)
    elif args.stage == 'pre-outcome-audit':
        result = run.pre_outcome_audit(args.input)
    elif args.stage == 'outcome-unlock':
        result = run.unlock()
    elif args.stage == 'outcomes':
        result = run.outcomes(args.manifest, as_of=args.as_of)
    else:
        result = getattr(run, args.stage.replace('-', '_'))()
    print(json.dumps({'stage': args.stage, 'artifact_hash': digest(result)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
