"""Acquire official SEC feature archives; never acquire evaluation outcome periods."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import time
import urllib.error
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

USER_AGENT = 'FinancialRiskAgent E5 reproducibility research siqiwang0712@gmail.com'


def download(url: str, target: Path) -> dict:
    started = datetime.now(UTC).isoformat()
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept-Encoding': 'identity'})
    temporary = target.with_suffix(target.suffix + '.partial')
    with urllib.request.urlopen(request, timeout=90) as response, temporary.open('wb') as output:
        h = hashlib.sha256()
        size = 0
        while block := response.read(1024 * 1024):
            h.update(block)
            output.write(block)
            size += len(block)
        final_url = response.url
    with zipfile.ZipFile(temporary) as archive:
        if archive.testzip() is not None:
            raise ValueError('corrupt SEC ZIP')
    temporary.rename(target)
    return {'source_url': url, 'resolved_url': final_url, 'sha256': h.hexdigest(),
            'bytes': size, 'download_timestamp': started, 'file': target.name}


def acquire(quarter: str, directory: Path) -> dict:
    if not re.fullmatch(r'20\d{2}q[1-4]', quarter) or quarter > '2025q3':
        raise ValueError('feature acquisition permits only historical quarters through 2025q3; outcomes require a separate unlock')
    directory.mkdir(parents=True, exist_ok=True)
    identity = directory / f'{quarter}.manifest.json'
    if identity.exists():
        old = json.loads(identity.read_text())
        path = directory / old['file']
        if hashlib.sha256(path.read_bytes()).hexdigest() != old['sha256']:
            raise ValueError('cached source hash drift')
        return old
    failures = []
    preferred = f'https://www.sec.gov/files/dera/data/financial-statement-data-sets/{quarter}.zip'
    alternate = f'https://www.sec.gov/Archives/edgar/full-index/{quarter[:4]}/QTR{quarter[-1]}/master.zip'
    for source_type, url, name in [('SEC_FSDS', preferred, f'{quarter}.zip'),
                                   ('SEC_EDGAR_MASTER_INDEX_ONLY', alternate, f'{quarter}-master.zip')]:
        time.sleep(.25)  # At most four new requests/second; no parallel SEC requests.
        try:
            record = download(url, directory / name)
            record.update(dataset_quarter=quarter, source_type=source_type, attempts=failures,
                          user_agent=USER_AGENT, evaluation_outcomes_accessed=False)
            with zipfile.ZipFile(directory / name) as archive:
                if source_type == 'SEC_FSDS':
                    names = {n.lower(): n for n in archive.namelist()}
                    if not {'sub.txt', 'num.txt'} <= set(names):
                        raise ValueError('SEC FSDS required tables missing')
                    sub = archive.read(names['sub.txt']).decode('utf-8-sig')
                    rows = [row for row in csv.DictReader(io.StringIO(sub), delimiter='\t') if row.get('form') == '10-K']
                    # This metadata-only universe is not a selected E5 cohort.
                    fields = ['adsh', 'cik', 'name', 'sic', 'form', 'period', 'filed', 'accepted', 'fye', 'fy', 'fp', 'prevrpt']
                    metadata = [{key: row.get(key) for key in fields} for row in rows]
                    payload = (json.dumps(metadata, sort_keys=True, separators=(',', ':')) + '\n').encode()
                    (directory / f'{quarter}.10k-submissions.json').write_bytes(payload)
                    record['submission_metadata_sha256'] = hashlib.sha256(payload).hexdigest()
                    record['original_10k_metadata_rows'] = len(metadata)
                elif not any(n.lower().endswith('master.idx') for n in archive.namelist()):
                    raise ValueError('EDGAR master index missing')
            identity.write_text(json.dumps(record, sort_keys=True, indent=2) + '\n')
            return record
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            failures.append({'url': url, 'source_type': source_type, 'error_type': type(exc).__name__,
                             'error': str(exc), 'at': datetime.now(UTC).isoformat()})
    error = {'dataset_quarter': quarter, 'status': 'ACQUISITION_FAILED', 'attempts': failures,
             'evaluation_outcomes_accessed': False}
    (directory / f'{quarter}.failure.json').write_text(json.dumps(error, indent=2) + '\n')
    raise RuntimeError(json.dumps(error))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--quarter', action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    failed = False
    for quarter in args.quarter:
        try:
            print(json.dumps(acquire(quarter, args.output)), flush=True)
        except (RuntimeError, ValueError) as exc:
            print(str(exc), flush=True)
            failed = True
    return 2 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
