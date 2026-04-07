#!/usr/bin/env python3
"""Read a field from a deployment artifact after applying any local overlay."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "sim"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SIM))

from darwin_sim.sdk.deployments import load_deployment_data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deployment-file", required=True)
    parser.add_argument("--default", default=None)
    parser.add_argument("field")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _, data, _, _ = load_deployment_data(deployment_file=args.deployment_file)

    cursor = data
    for part in args.field.split("."):
        if not isinstance(cursor, dict) or part not in cursor:
            if args.default is not None:
                print(args.default)
                return 0
            raise SystemExit(f"missing deployment field: {args.field}")
        cursor = cursor[part]

    if isinstance(cursor, (dict, list)):
        print(json.dumps(cursor))
    else:
        print(cursor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
