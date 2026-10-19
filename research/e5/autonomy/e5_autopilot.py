"""Read-only design orchestrator: Autopilot != ScientificAuthority."""
import argparse
import json

try:
    from .governance import verify_identities, verify_state
except ImportError:
    from governance import verify_identities, verify_state

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='verify design and historical integrity, never run E5')
    parser.parse_args()
    verify_identities()
    print(json.dumps({'governance_integrity': 'PASS', **verify_state()}, sort_keys=True))
