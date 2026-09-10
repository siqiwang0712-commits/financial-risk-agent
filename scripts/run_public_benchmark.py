import argparse
from pathlib import Path

from finrisk.research_eval import (
    run_public_benchmark,
    run_robustness_checks,
    write_results,
    write_robustness,
)

ROOT = Path(__file__).resolve().parents[1]
FROZEN_PUBLIC_V1 = (ROOT / "research/results/public_v1").resolve()


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay the public pilot without mutating v0.3.0")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "research/results/v0.3.1/public_pilot_replay",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    if output == FROZEN_PUBLIC_V1:
        raise SystemExit("research/results/public_v1 is the immutable v0.3.0 snapshot")

    manifest = ROOT / "research/benchmark/public_company_observations.json"
    rows, summary, ablations = run_public_benchmark(manifest, ROOT)
    write_results(rows, summary, ablations, output)
    write_robustness(run_robustness_checks(manifest, ROOT), output)
    print(summary)


if __name__ == "__main__":
    main()
