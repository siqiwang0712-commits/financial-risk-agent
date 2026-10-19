"""Verify adopted release bytes and historical identities; creates no freeze."""
try:
    from .governance import verify_identities
except ImportError:
    from governance import verify_identities

if __name__ == '__main__':
    verify_identities()
    print('Candidate release binding and immutable historical identities: PASS; protocol freeze NOT_EXECUTED')
