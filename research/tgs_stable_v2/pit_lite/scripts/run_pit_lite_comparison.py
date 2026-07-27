#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


PIT_ROOT = Path(__file__).resolve().parents[1]
V2_ROOT = PIT_ROOT.parent
for source in (PIT_ROOT / "src", V2_ROOT / "src"):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

from pit_lite.contract import PRIVATE_ROOT  # noqa: E402
from pit_lite.manifest import build_deletion_manifest  # noqa: E402
from pit_lite.pipeline import run_comparison  # noqa: E402
from pit_lite.safety import (  # noqa: E402
    SafetyError,
    assert_private_path,
    validate_private_tree,
)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Run the frozen aggregate-only PIT-lite comparison."
    )
    value.add_argument("--run-id", required=True)
    return value


def main() -> int:
    args = parser().parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{7,79}", args.run_id):
        print("error: unsafe run_id", file=sys.stderr)
        return 2
    run_directory = PRIVATE_ROOT.expanduser() / "runs" / args.run_id
    try:
        validate_private_tree(PRIVATE_ROOT)
        assert_private_path(run_directory)
        if not run_directory.is_dir():
            raise SafetyError("run_id does not exist in the approved private root")
        try:
            result = run_comparison(args.run_id, run_directory)
        finally:
            # Keep a crash-safe exact deletion manifest after any private writes.
            build_deletion_manifest(args.run_id, run_directory)
        validate_private_tree(PRIVATE_ROOT)
    except (RuntimeError, ValueError, SafetyError) as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
