"""Exit 0 for truthful design state; --require-ready exits 2 for BLOCKED."""
import argparse
import json

try:
    from .governance import verify_state
except ImportError:
    from governance import verify_state

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-ready', action='store_true')
    args = parser.parse_args()
    result = verify_state()
    print(json.dumps({'governance_integrity': 'PASS', **result}, sort_keys=True))
    raise SystemExit(2 if args.require_ready and result['status'] != 'READY_TO_FREEZE' else 0)
