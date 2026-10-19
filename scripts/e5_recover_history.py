"""Hash every reachable historical Git blob without interpreting outcomes.

Read-only. A no-match result does not prove absence from remote/unreachable history.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def scan(root: Path, expected_sha256: str) -> dict:
    listing = subprocess.check_output(['git', 'rev-list', '--objects', '--all'], cwd=root, text=True)
    objects = {line.split(' ', 1)[0]: line.split(' ', 1)[1] if ' ' in line else ''
               for line in listing.splitlines()}
    process = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=root,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    count = size = 0
    matches = []
    try:
        for object_id, path in objects.items():
            process.stdin.write((object_id + '\n').encode())
            process.stdin.flush()
            header = process.stdout.readline().decode().split()
            if len(header) != 3:
                raise RuntimeError('missing/corrupt Git object: ' + object_id)
            length = int(header[2])
            body = process.stdout.read(length)
            if len(body) != length or process.stdout.read(1) != b'\n':
                raise RuntimeError('truncated Git object: ' + object_id)
            if header[1] == 'blob':
                count += 1
                size += length
                if hashlib.sha256(body).hexdigest() == expected_sha256:
                    matches.append({'git_object': object_id, 'path': path})
        process.stdin.close()
        if process.wait():
            raise RuntimeError('git cat-file failed')
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait()
    return {'objects': len(objects), 'blobs_hashed': count, 'bytes_hashed': size,
            'expected_sha256': expected_sha256, 'exact_matches': matches,
            'scope': 'all locally reachable refs; not remote/unreachable object recovery'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(scan(args.root, 'd73b371ccb026f556387cf6ff8ba204a4fde0664dcd780f099f12aa005e36603'), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
