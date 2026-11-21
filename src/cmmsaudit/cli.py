"""Command line entry point."""

from __future__ import annotations

import argparse
import sys

from .audit import audit, format_report, load_rows


def main(argv: list[str] | None = None) -> int:
    """Audit a CSV file. Exit 0 if score meets --min-score, 1 if not, 2 on bad input."""
    parser = argparse.ArgumentParser(prog="cmmsaudit", description="Score CMMS work-order CSV quality.")
    parser.add_argument("csv_file")
    parser.add_argument("--min-score", type=float, default=0.0,
                        help="exit with status 1 when the overall score is below this")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)
    try:
        rows = load_rows(args.csv_file)
    except OSError as exc:
        print(f"cannot read file: {exc}", file=sys.stderr)
        return 2
    result = audit(rows)
    print(format_report(result, args.limit))
    return 0 if result.overall_score >= args.min_score else 1
