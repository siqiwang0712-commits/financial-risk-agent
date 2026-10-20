"""Resumable E5 execution entrypoint; failed scientific gates never become success."""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

from .execution.core import (
    digest,
    file_hash,
    freeze_json,
    read_json,
    require,
    utcnow,
    verify_files,
)
from .execution.development import utility
from .execution.qualification import qualify_s0

ROOT = Path(__file__).resolve().parents[2]
EXECUTION = ROOT / 'research/e5/execution'
QUALIFICATION = ROOT / 'research/e5/qualification'


def git(*arguments):
    return subprocess.check_output(['git', *arguments], cwd=ROOT, text=True).strip()


def code_identity():
    paths = sorted((ROOT / 'research/e5/execution').glob('*.py')) + [Path(__file__)]
    return {str(p.relative_to(ROOT)): file_hash(p) for p in paths}


def checkpoint(stage: str, state: str, *, inputs: dict, outputs: dict,
               failure_reason: str | None = None, started_at: str | None = None):
    """Append immutable stage evidence and atomically update the derived index."""
    record = {'stage': stage, 'state': state, 'started_at': started_at or utcnow(),
              'completed_at': utcnow(), 'input_hashes': inputs, 'output_hashes': outputs,
              'code_commit': git('rev-parse', 'HEAD'),
              'validation_result': 'PASS' if state == 'COMPLETE' else 'BLOCKED',
              'failure_reason': failure_reason}
    name = digest(record)
    freeze_json(EXECUTION / 'checkpoints' / f'{name}.json', record)
    index_path = EXECUTION / 'RUN_STATE.json'
    index = read_json(index_path) if index_path.exists() else {
        'schema_version': 1, 'studies': {'E5-R': 'DRAFT', 'E5-P': 'DRAFT'},
        'stages': {}, 'outcomes_accessed': False}
    for old in index['stages'].values():
        old_path = EXECUTION / 'checkpoints' / f"{old['checkpoint']}.json"
        require(old_path.is_file() and digest(read_json(old_path)) == old['checkpoint'],
                'checkpoint history mutated')
    record['checkpoint'] = name
    index['stages'][stage] = record
    index['updated_at'] = utcnow()
    fd, temporary = tempfile.mkstemp(dir=EXECUTION, prefix='.state-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(index, stream, sort_keys=True, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, index_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return record


def blockers() -> list[dict]:
    return [
        {'id': 'P01/P02', 'gate': 'MODEL_QUALIFIED',
         'reason': 'No qualified evidence-independent Agent producer or matched historical development score corpus; no study calibration/authorization policy can be honestly certified.'},
        {'id': 'P04', 'gate': 'FEATURE_PACKETS_FROZEN',
         'reason': 'New immutable point-in-time SEC source data are unavailable locally; direct authoritative SEC request failed with Operation not permitted.'},
        {'id': 'C01', 'gate': 'COHORT_FROZEN',
         'reason': 'Exact previous_270 absent from locally reachable history; no independently checkable containing-superset proof. Remote artifact recovery is incomplete.'},
        {'id': 'INFERENCE', 'gate': 'PROTOCOL_FROZEN',
         'reason': 'Synthetic engine tests and null grid do not establish the complete required joint-power/type-I qualification or all comparator-dependence scenarios.'},
        {'id': 'ISOLATION', 'gate': 'OUTCOMES_UNLOCKED',
         'reason': 'No independent operational outcome isolation or genuine blinded adjudication process has been established. Filesystem path guards alone are insufficient.'},
    ]


def qualify() -> dict:
    started = utcnow()
    require(git('branch', '--show-current') == 'E5-experiment', 'wrong branch')
    identity = code_identity()
    # Code producing immutable qualifications must already be checkpointed in Git.
    for name in identity:
        require(not git('status', '--porcelain', '--', name), 'commit qualification code first: ' + name)
    values = utility(ROOT)
    s0 = qualify_s0(ROOT)
    runtime = {'python': sys.version, 'os': platform.platform(), 'architecture': platform.machine(),
               'git_commit': git('rev-parse', 'HEAD'), 'git_tree': git('rev-parse', 'HEAD^{tree}'),
               'requirements_lock_sha256': file_hash(ROOT / 'requirements.lock')}
    import numpy
    import scipy
    import sklearn
    runtime.update(numpy=numpy.__version__, scipy=scipy.__version__, sklearn=sklearn.__version__)
    # Stable qualification outputs resume without changing their original timestamps/commit.
    output = {}
    for name, payload in [('utility_rule.json', values), ('s0_replay.json', s0)]:
        path = QUALIFICATION / name
        output[str(path.relative_to(ROOT))] = freeze_json(path, payload)
    ident_path = QUALIFICATION / 'execution_qualification_identity.json'
    if ident_path.exists():
        saved = read_json(ident_path)
        require(saved['code_hashes'] == identity, 'qualification code drift: new identity required')
        verify_files(ROOT, saved['output_hashes'])
    else:
        saved = {'created_at': started, 'code_hashes': identity, 'runtime': runtime,
                 'output_hashes': output, 'e5_outcomes_used': False,
                 'scope': 'Historical S0 replay and mechanical S1 utility only; not arm/protocol qualification'}
        freeze_json(ident_path, saved)
    output[str(ident_path.relative_to(ROOT))] = file_hash(ident_path)
    checkpoint('historical_development_qualification', 'COMPLETE', inputs=identity,
               outputs=output, started_at=started)
    return {'status': 'PARTIAL_QUALIFICATION_COMPLETE', 'S0': s0,
            'utility': {k: v for k, v in values.items() if k != 'rows'}, 'remaining': blockers()}


def audit() -> dict:
    identity = read_json(EXECUTION / 'mandate_identity.json')
    require(file_hash(EXECUTION / 'E5_EXECUTION_MANDATE.md') == identity['mandate_sha256'],
            'mandate byte identity mismatch')
    baseline = read_json(EXECUTION / 'BASELINE_AUDIT.json')
    verify_files(ROOT, baseline['file_inventory'])
    qi = QUALIFICATION / 'execution_qualification_identity.json'
    if qi.exists():
        value = read_json(qi)
        verify_files(ROOT, value['code_hashes'])
        verify_files(ROOT, value['output_hashes'])
    require(not (ROOT / 'research/e5/e5r/outcomes').exists(), 'unexpected E5-R outcome path')
    return {'integrity': 'PASS', 'historical_files_verified': len(baseline['file_inventory']),
            'outcomes_accessed_by_this_execution': False, 'pre_outcome_freeze_barrier': 'BLOCKED',
            'remaining': blockers()}


def main(argv=None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments and arguments[0] == 'phase2':
        from .phase2.precise_stage import main as phase2_main
        return phase2_main(arguments[1:])
    from .phase2.precise_cli import main as active_main
    return active_main(arguments)


if __name__ == '__main__':
    raise SystemExit(main())
