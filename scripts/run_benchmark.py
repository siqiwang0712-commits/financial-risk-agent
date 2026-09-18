import argparse
from pathlib import Path

from finrisk.benchmark import run_manifest, write_jsonl


def main() -> None:
    """Run the synthetic smoke evaluation. Importing this module must not."""
    parser=argparse.ArgumentParser(description="Run explicitly synthetic baseline/ablation smoke evaluation")
    parser.add_argument("--manifest",default="research/synthetic_manifest.json")
    parser.add_argument("--output",default="research/results/synthetic_smoke.jsonl")
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    rows=run_manifest(root/args.manifest,root);output=root/args.output;output.parent.mkdir(parents=True,exist_ok=True);write_jsonl(rows,output)
    print(f"wrote {len(rows)} synthetic smoke rows to {output}")


if __name__ == "__main__":
    main()
