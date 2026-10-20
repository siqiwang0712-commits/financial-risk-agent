"""Feature-only numerical prediction worker and enforced Docker boundary.

No host volume, Docker socket, network, runtime credential, or outcome archive is
passed to the worker. Its image contains only code and already-excluded historical
development artifacts. The parent wrapper still freezes exactly one proposal.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from ..execution.core import canonical, digest, file_hash, require, validate_features
from .study import CalibratedStudyProducer


def call(image_id, feature, expected_identity):
    require(re.fullmatch(r'sha256:[0-9a-f]{64}', image_id) is not None, 'immutable prediction image ID required')
    create = ['docker', 'create', '--interactive', '--network', 'none', '--read-only',
              '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
              '--pids-limit', '64', '--memory', '1g', '--cpus', '1',
              '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m', image_id]
    made = subprocess.run(create, capture_output=True, text=True, check=True)
    container = made.stdout.strip()
    require(re.fullmatch(r'[0-9a-f]{64}', container) is not None, 'invalid Docker container identity')
    try:
        config = json.loads(subprocess.check_output(['docker', 'inspect', container], text=True))[0]
        host = config['HostConfig']
        require(config['Image'] == image_id and host['NetworkMode'] == 'none' and host['ReadonlyRootfs'], 'prediction boundary not enforced')
        require(not host.get('Binds') and not host.get('VolumesFrom')
                and all(m.get('Type') == 'tmpfs' and m.get('Destination') == '/tmp' and not m.get('Source')
                        for m in config.get('Mounts', [])), 'host source/outcome volumes forbidden')
        require('ALL' in host['CapDrop'] and 'no-new-privileges:true' in host['SecurityOpt'], 'prediction privileges not dropped')
        result = subprocess.run(['docker', 'start', '--attach', '--interactive', container],
                                input=canonical(feature), capture_output=True, check=True)
        returned = json.loads(result.stdout)
        require(returned['producer_identity'] == expected_identity and returned['input_hash'] == digest(feature), 'isolated producer/input drift')
        state = json.loads(subprocess.check_output(['docker', 'inspect', container], text=True))[0]['State']
        require(state['ExitCode'] == 0 and state['Status'] == 'exited', 'isolated prediction failed')
        receipt = {'image_id': image_id, 'container_id': container, 'input_hash': digest(feature),
                   'network_mode': host['NetworkMode'], 'read_only_rootfs': host['ReadonlyRootfs'],
                   'host_binds': host.get('Binds'), 'host_mounts': config.get('Mounts'),
                   'cap_drop': host['CapDrop'], 'security_opt': host['SecurityOpt'],
                   'exit_code': state['ExitCode'], 'worker_output_hash': digest(returned),
                   'operational_boundary': 'FEATURE_ONLY_STDIN_NO_NETWORK_NO_HOST_VOLUMES'}
        return returned['result'], receipt
    finally:
        subprocess.run(['docker', 'rm', '--force', container], capture_output=True, check=False)


def worker():
    root = Path(__file__).resolve().parents[3]
    feature = json.load(sys.stdin)
    producer = CalibratedStudyProducer(root)
    validate_features(feature, schema_hash=digest(producer.raw.schema), code_hash=file_hash(root/'research/e5/phase2/sources.py'))
    result = producer(feature)
    print(json.dumps({'producer_identity': producer.identity, 'input_hash': digest(feature), 'result': result}, sort_keys=True))


if __name__ == '__main__':
    worker()
