"""Official outcome acquisition, executable only behind the real unlock journal."""
from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

from ..execution.core import digest, file_hash, freeze_json, read_json, require, utcnow
from .acquire_sec import USER_AGENT, download
from .engine import Execution


def acquire(root: Path, directory: Path, quarters: list[str]):
    run = Execution(root, directory)
    run.check_protocol()
    unlock = run.load('outcome-unlock')
    require(quarters and len(quarters) == len(set(quarters)) and all(re.fullmatch(r'20\d{2}q[1-4]', q) for q in quarters),
            'unique official outcome quarter identities required')
    folder = directory/'outcome-inputs'
    folder.mkdir(parents=True, exist_ok=True)
    outputs = []
    for quarter in quarters:
        manifest = folder/(quarter+'.manifest.json')
        target = folder/(quarter+'.zip')
        if manifest.exists():
            saved = read_json(manifest)
            require(saved['unlock_manifest_hash'] == digest(unlock) and file_hash(target) == saved['sha256'], 'outcome cache drift')
            outputs.append(manifest)
            continue
        require(not target.exists(), 'unmanaged outcome source exists; explicit recovery required')
        url = f'https://www.sec.gov/files/dera/data/financial-statement-data-sets/{quarter}.zip'
        try:
            time.sleep(.25)
            record = download(url, target)
            record.update(dataset_quarter=quarter, source_type='SEC_FSDS', user_agent=USER_AGENT,
                          unlock_manifest_hash=digest(unlock), evaluation_outcomes_accessed=True)
            freeze_json(manifest, record)
            outputs.append(manifest)
        except (OSError, ValueError) as exc:
            failure = {'quarter': quarter, 'url': url, 'error_type': type(exc).__name__, 'error': str(exc),
                       'attempted_at': utcnow(), 'unlock_manifest_hash': digest(unlock)}
            freeze_json(folder/('failure-'+digest(failure)+'.json'), failure)
            raise
    return outputs


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--quarter', action='append', required=True)
    args = parser.parse_args()
    print([str(p) for p in acquire(Path(__file__).resolve().parents[3], args.run, args.quarter)])
