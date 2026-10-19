"""Fail closed unless the newest ordinary CI run for this source passed all jobs."""
from __future__ import annotations

import argparse
import json
import subprocess
import time

REPOSITORY = 'siqiwang0712-commits/financial-risk-agent'
REQUIRED_JOBS = {'backend (3.11)', 'backend (3.12)', 'frontend', 'docker-smoke'}


def checked_run(runs: list[dict], commit: str) -> dict:
    candidates = [run for run in runs if run.get('head_sha') == commit
                  and run.get('event') == 'push'
                  and run.get('path') == '.github/workflows/ci.yml'
                  and run.get('head_repository', {}).get('full_name') == REPOSITORY]
    if not candidates:
        raise ValueError('no ordinary CI run for the exact release source')
    return max(candidates, key=lambda run: run['id'])


def verify_completed(run: dict, jobs: list[dict]) -> None:
    if run.get('status') != 'completed' or run.get('conclusion') != 'success':
        raise ValueError('newest source CI has not succeeded')
    if ({job.get('name') for job in jobs} != REQUIRED_JOBS or len(jobs) != len(REQUIRED_JOBS)
            or any(job.get('status') != 'completed' or job.get('conclusion') != 'success' for job in jobs)):
        raise ValueError('required CI jobs must all complete successfully')


def api(path: str) -> list[dict]:
    # gh uses the runner's scoped GITHUB_TOKEN; no credentials enter URLs/logs.
    output = subprocess.check_output(['gh', 'api', '--paginate', '--jq', '@json', path], text=True)
    return [json.loads(line) for line in output.splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    if len(args.commit) != 40 or any(c not in '0123456789abcdef' for c in args.commit):
        raise SystemExit('release source must be an exact SHA')
    deadline = time.monotonic() + 25 * 60
    while True:
        runs = [r for page in api(f'repos/{REPOSITORY}/actions/workflows/ci.yml/runs?head_sha={args.commit}&event=push&per_page=100')
                for r in page['workflow_runs']]
        run = checked_run(runs, args.commit)
        if run['status'] == 'completed':
            jobs = [job for page in api(f'repos/{REPOSITORY}/actions/runs/{run["id"]}/jobs?filter=latest&per_page=100') for job in page['jobs']]
            verify_completed(run, jobs)
            print(f'Exact-source ordinary CI passed: run {run["id"]}, source {args.commit}')
            return
        if time.monotonic() >= deadline:
            raise SystemExit('ordinary CI did not complete within the release admission budget')
        time.sleep(15)


if __name__ == '__main__':
    main()
