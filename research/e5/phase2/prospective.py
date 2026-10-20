"""Rolling prospective enrollment under the frozen exact-clock protocol.

Only current, eligible, historically disjoint original filings may enroll. A
packet and enrollment freeze precede the one isolated generation. No outcome
request occurs here. Deadline/runtime failures stay explicit pending cases.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from pathlib import Path

from finrisk.sec_bulk import add_twelve_months

from ..execution.core import digest, freeze_json, read_json, require, timestamp, utcnow
from .acquire_sec import USER_AGENT
from .cohort import prove_exclusions
from .live_source import extract
from .precise_engine import PreciseExecution
from .precise_source import index_clock
from .sec_access import SpacedSecClient as SecClient


def enrollment_window(frozen_at):
    now = timestamp(frozen_at)
    year, month = now.year, ((now.month-1)//3+1)*3+1
    if month == 13:
        year, month = year+1, 1
    start = datetime(year, month, 1, tzinfo=UTC)
    return start, start.replace(year=start.year+1)


def collect(root: Path, cik: str, accession: str, previous: Path):
    directory = root/'research/e5/phase2/e5p-precise'
    parent = PreciseExecution(root, directory)
    protocol = parent.load('protocol')
    parent.check_protocol()
    start, stop = enrollment_window(protocol['created_at'])
    now = timestamp(utcnow())
    require(start <= now < stop, 'prospective enrollment window is not open')
    excluded, proof = prove_exclusions(root, previous)
    cik = SecClient._normalize_cik(cik)
    prior_r = root/'research/e5/phase2/e5r/cohort.json'
    if prior_r.exists():
        excluded |= {c['cik'] for c in read_json(prior_r)['payload']['cases']}
    require(cik not in excluded, 'historical/R overlap')
    observed = [p for p in (directory/'polls').glob('*.json')
                if any(c['cik'] == cik and c['accession'] == accession for c in read_json(p)['candidates'])]
    require(bool(observed), 'prospective enrollment requires a frozen official feed observation, not discretionary nomination')
    company = directory/'enrollments'/cik
    require(not company.exists(), 'one original case per company; existing attempts require explicit resume/recovery')
    cache = root/'.runtime/e5-live-source'/cik/accession
    client = SecClient(USER_AGENT, cache_dir=cache, pause_seconds=.3, max_retries=1)
    metadata = client.submissions(cik)
    require(str(metadata['cik']).zfill(10) == cik, 'cross-CIK metadata')
    sic = int(metadata.get('sic') or 0)
    require(sic and not 6000 <= sic <= 6999, 'nonfinancial original filing scope')
    recent = metadata['filings']['recent']
    require(not metadata['filings'].get('files')
            or recent['filingDate'] and min(recent['filingDate']) <= start.date().isoformat(),
            'recent metadata does not prove complete original-filing history through the enrollment window')
    require(accession in recent['accessionNumber'], 'index accession unavailable')
    i = recent['accessionNumber'].index(accession)
    require(recent['form'][i] == '10-K', 'original 10-K required')
    original_candidates = []
    for j, form in enumerate(recent['form']):
        if form != '10-K':
            continue
        filed = datetime.fromisoformat(recent['filingDate'][j]).replace(tzinfo=UTC)
        if not start-timedelta(days=7) <= filed <= stop+timedelta(days=7):
            continue
        candidate = index_clock(cik, recent['accessionNumber'][j], root/'.runtime/e5-index-clock')
        if start <= timestamp(candidate['accepted']) < stop:
            original_candidates.append((candidate['accepted'], candidate['accession']))
    require(original_candidates and min(original_candidates)[1] == accession, 'first original 10-K per CIK in the window required')
    clock = index_clock(cik, accession, root/'.runtime/e5-index-clock')
    accepted = timestamp(clock['accepted'])
    require(start <= accepted < stop and accepted <= now <= accepted+timedelta(days=1), 'filing outside frozen window or 24h deadline')
    bundle = extract(root, cik, accession, cache)
    deadline = (accepted+timedelta(days=1)).isoformat()
    require(timestamp(utcnow()) <= timestamp(deadline), 'source capture missed deadline; do not enroll or backfill')
    run = PreciseExecution(root, company)
    # Scientific choices are an exact copy of the previously frozen parent.
    run.write('protocol', protocol['payload'])
    case = {'cik': cik, 'accession': accession, 'accepted': clock['accepted'], 'sic': sic,
            'prediction_deadline': deadline, 'source_mode': 'LIVE_SEC_EXACT_INDEX_ACCESSION'}
    run.write('cohort', {'cases': [case], 'historical_nonoverlap_proof': proof,
                         'parent_prospective_protocol_hash': digest(protocol), 'rolling_case_freeze': True})
    run.write('features', {'bundles': [bundle], 'source_manifests': [], 'source_mode': 'LIVE_SEC_EXACT_INDEX_ACCESSION'})
    run.predictions()
    result = run.pre_outcome_audit()
    freeze_json(company/'prospective-prediction-complete.json', {'status': 'PREDICTION_FROZEN_WAITING_FOR_OUTCOMES',
                'case_id': bundle['packet']['case_id'], 'pre_outcome_audit_hash': digest(result),
                'outcome_window_end': add_twelve_months(accepted).isoformat(), 'outcomes_accessed': False})
    return result




def poll(root: Path, previous: Path):
    """Deterministic official feed frame; no discretionary company nomination."""
    import re
    import xml.etree.ElementTree as ET

    directory = root/'research/e5/phase2/e5p-precise'
    parent = PreciseExecution(root, directory)
    parent.check_protocol()
    protocol = parent.load('protocol')
    start, stop = enrollment_window(protocol['created_at'])
    now = timestamp(utcnow())
    require(start <= now < stop, 'prospective enrollment window is not open')
    excluded, _ = prove_exclusions(root, previous)
    client = SecClient(USER_AGENT, pause_seconds=.3, max_retries=1)
    seen, sources = {}, []
    ns = {'a': 'http://www.w3.org/2005/Atom'}
    for offset in range(0, 1000, 100):
        url = ('https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=10-K'
               f'&owner=exclude&count=100&start={offset}&output=atom')
        raw = client.get_bytes(url)
        require(b'<!DOCTYPE' not in raw.upper(), 'unexpected feed document type')
        sources.append({'url': url, 'sha256': __import__('hashlib').sha256(raw).hexdigest()})
        entries = ET.fromstring(raw).findall('a:entry', ns)
        for entry in entries:
            title = entry.findtext('a:title', default='', namespaces=ns)
            if not re.match(r'^10-K\s+-', title):
                continue
            link = entry.find('a:link', ns)
            if link is None:
                continue
            match = re.search(r'/data/(\d+)/(\d{18})/', link.attrib.get('href', ''))
            if not match:
                continue
            cik, digits = match.groups()
            cik = cik.zfill(10)
            accession = digits[:10]+'-'+digits[10:12]+'-'+digits[12:]
            if cik not in excluded:
                seen[(cik, accession)] = {'cik': cik, 'accession': accession, 'metadata_title': title}
        if len(entries) < 100:
            break
    snapshot = {'observed_at': utcnow(), 'source_frame': 'OFFICIAL_CURRENT_10K_FEED_FIRST_1000_ENTRIES_PER_POLL',
                'sources': sources, 'candidates': sorted(seen.values(), key=lambda r: (r['cik'], r['accession'])),
                'outcome_values_accessed': False}
    freeze_json(directory/'polls'/(digest(snapshot)+'.json'), snapshot)
    results = []
    for case in snapshot['candidates']:
        if (directory/'enrollments'/case['cik']).exists():
            continue
        try:
            collect(root, case['cik'], case['accession'], previous)
            results.append(case | {'status': 'PREDICTION_FROZEN'})
        except (OSError, ValueError) as exc:
            results.append(case | {'status': 'NOT_COMPLETED', 'reason': str(exc)})
    result = {'poll_hash': digest(snapshot), 'case_statuses': results, 'outcomes_accessed': False}
    freeze_json(directory/'poll-results'/(digest(result)+'.json'), result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-270', type=Path, required=True)
    args = parser.parse_args()
    print(poll(Path(__file__).resolve().parents[3], args.previous_270))
