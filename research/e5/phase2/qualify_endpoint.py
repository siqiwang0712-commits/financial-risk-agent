"""Run engineering qualification of source, endpoint and stage boundaries."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from ..execution.core import file_hash, freeze_json, require, utcnow


def run(root):
    command = [sys.executable, '-m', 'pytest', '-q', 'tests/test_e5_phase2.py',
               'tests/test_e5_execution.py', 'tests/test_assurance.py']
    # The full E5/Assurance suite is separately retained in validation evidence.
    command = [c for c in command if c != 'tests/test_assurance.py']
    with tempfile.TemporaryDirectory() as directory:
        junit = Path(directory)/'results.xml'
        result = subprocess.run(command+['--junitxml='+str(junit)], cwd=root, capture_output=True, text=True)
        require(result.returncode == 0, 'endpoint and boundary engineering tests failed: '+result.stdout[-1500:])
        suite = ET.parse(junit).getroot()[0]
        require(int(suite.attrib['failures']) == 0 and int(suite.attrib['errors']) == 0, 'qualification tests failed')
        report = {'status': 'PASSED', 'qualified_at': utcnow(), 'qualification_scope': 'ENGINEERING_EXTRACTION_AND_GUARDS_NOT_EMPIRICAL_E5',
                  'adapter_sha256': file_hash(root/'research/e5/phase2/endpoint.py'),
                  'source_extractor_sha256': file_hash(root/'research/e5/phase2/sources.py'),
                  'qualification_source_sha256': file_hash(Path(__file__)),
                  'test_bindings': {p: file_hash(root/p) for p in ('tests/test_e5_phase2.py', 'tests/test_e5_execution.py')},
                  'command': command, 'junit_suite': suite.attrib,
                  'test_ids': [c.attrib['classname']+'::'+c.attrib['name'] for c in suite.findall('testcase')],
                  'outcomes_accessed': False}
    freeze_json(root/'research/e5/phase2/qualification/endpoint-qualification.json', report)
    return report


if __name__ == '__main__':
    print(run(Path(__file__).resolve().parents[3])['status'])
