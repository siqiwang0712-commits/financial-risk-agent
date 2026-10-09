"""Check candidate OCI source/version identity and the API privilege surface."""
from __future__ import annotations

import argparse
import json
import subprocess


def verify_metadata(image: dict, version: str, revision: str) -> None:
    config = image.get('Config', {})
    labels = config.get('Labels') or {}
    if (labels.get('org.opencontainers.image.version') != version.removeprefix('v')
            or labels.get('org.opencontainers.image.revision') != revision):
        raise ValueError('candidate OCI source/version identity mismatch')
    user = (config.get('User') or '').split(':', 1)[0]
    if not user or user == 'root' or (user.isdigit() and int(user) == 0):
        raise ValueError('candidate runtime must use an unprivileged user')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--docker-bin', default='docker')
    parser.add_argument('--api', action='store_true')
    args = parser.parse_args()
    images = json.loads(subprocess.check_output([args.docker_bin, 'image', 'inspect', args.image], text=True))
    if len(images) != 1:
        raise SystemExit('candidate image inspection must resolve exactly one image')
    verify_metadata(images[0], args.version, args.revision)
    if args.api:
        # Read-only inspection inside the exact candidate; no mount or server.
        subprocess.run([args.docker_bin, 'run', '--rm', '--user', '0', '--entrypoint', 'sh', args.image,
                        '-ec', ('test ! -e /usr/bin/mount; test ! -e /usr/bin/umount; '
                        'find / -xdev -type f -perm /6000 -print -quit > /tmp/finrisk-privilege-check; '
                        'test ! -s /tmp/finrisk-privilege-check')], check=True)
    print('Candidate OCI source/version and runtime privilege checks: PASS')


if __name__ == '__main__':
    main()
