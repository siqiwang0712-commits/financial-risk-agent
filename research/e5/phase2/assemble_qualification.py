"""Assemble the prespecified full grid from immutable execution partitions."""
from __future__ import annotations

from pathlib import Path

from ..execution.core import digest, file_hash, freeze_json, read_json, require
from .inference import specification
from .qualification import combine
from .simulation import null_cases

ORIGINAL = 'cd0ce34c2f25f4bdc27717b876a5515c22d6ac4019dcf2515ee9f1b9369d01da'


def assemble(root: Path):
    spec = specification(root)
    cases = null_cases(spec)
    original = root/'research/e5/phase2/qualification/inference'/ORIGINAL
    planned = read_json(original/'identity.json')
    require(planned['analysis_identity'] == digest(spec) and planned['cases'] == cases, 'original planned grid changed')
    reports, inputs = [], {}
    for index, case in enumerate(cases):
        if index < 5:
            path = original/f'{index:02d}.json'
            report = read_json(path)
        else:
            partitions = []
            for path in (root/'research/e5/phase2/qualification/partitions').glob('*/qualification.json'):
                candidate = read_json(path)
                if candidate['simulation_identity']['cases'] == [case]:
                    partitions.append((path, candidate))
            require(bool(partitions), 'execution partition not yet complete: '+case['name'])
            # Duplicate scheduling must agree exactly; never select a favorable run.
            require(len({digest(p[1]) for p in partitions}) == 1, 'duplicate partition results disagree')
            path, executed = sorted(partitions, key=lambda p: str(p[0]))[0]
            identity = executed['simulation_identity']
            require(identity['analysis_identity'] == digest(spec) and identity['replicates'] == 5000,
                    'partition canonical analysis/trials mismatch')
            require(identity['simulation_source_sha256'] == planned['simulation_source_sha256'], 'partition runner changed')
            partition_identity = read_json(path.parent/'identity.json')
            require(partition_identity['case'] == case and partition_identity['case_index'] == index,
                    'case scheduling identity mismatch')
            inputs[str((path.parent/'identity.json').relative_to(root))] = file_hash(path.parent/'identity.json')
            report = executed['configurations'][0]
        require(report['case'] == case and report['replicates'] == 5000, 'case/statistical scope mismatch')
        reports.append(report)
        inputs[str(path.relative_to(root))] = file_hash(path)
    require(planned['simulation_source_sha256'] == file_hash(root/'research/e5/phase2/simulation.py'), 'canonical simulation code drift')
    result = {'status': 'FAILED' if any(r['material_anti_conservatism'] for r in reports) else 'PASSED',
              'analysis_identity': digest(spec), 'analysis_specification': spec,
              'simulation_identity': planned, 'configurations': reports,
              'execution_partition_hashes': inputs, 'assembler_sha256': file_hash(Path(__file__)),
              'scheduling_note': 'First five full-grid configurations plus seven single-case partitions. Exact same inference kernel/draw count. Original sequential run preserved and stopped for scheduling only.',
              'outcomes_accessed': False}
    destination = root/'research/e5/phase2/qualification/canonical-v3-grid.json'
    freeze_json(destination, result)
    extras = list((root/'research/e5/phase2/qualification/supplement').glob('*/qualification.json'))
    require(len(extras) == 1, 'one prespecified supplementary N100 qualification required')
    return combine(root, destination, extras[0])


if __name__ == '__main__':
    result = assemble(Path(__file__).resolve().parents[3])
    print({'status': result['status'], 'trials': result['complete_grid_trials']})
