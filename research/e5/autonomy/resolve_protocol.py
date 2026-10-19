"""Print a candidate design resolution; never freeze or execute E5."""
import json

try:
    from .governance import resolve
except ImportError:
    from governance import resolve

if __name__ == '__main__':
    print(json.dumps(resolve(), indent=2, sort_keys=True))
