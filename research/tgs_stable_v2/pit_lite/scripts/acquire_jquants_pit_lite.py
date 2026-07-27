#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path


PIT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PIT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pit_lite.acquisition import acquire  # noqa: E402
from pit_lite.api import (  # noqa: E402
    API_KEY_ENV,
    HARD_ATTEMPT_LIMIT,
    AttemptJournal,
    SafeApiClient,
    filevault_is_active,
    frozen_acquisition_plan,
)
from pit_lite.contract import (  # noqa: E402
    CONTRACT,
    PRIVATE_ROOT,
    verify_production_files,
    verify_protected_inputs,
)
from pit_lite.manifest import build_deletion_manifest  # noqa: E402
from pit_lite.safety import (  # noqa: E402
    SafetyError,
    atomic_write_bytes,
    create_private_run,
    validate_private_tree,
)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Bounded private J-Quants acquisition for V2-R2A."
    )
    modes = value.add_mutually_exclusive_group(required=True)
    modes.add_argument("--estimate", action="store_true")
    modes.add_argument("--live", action="store_true")
    value.add_argument("--run-id")
    value.add_argument("--resume", action="store_true")
    value.add_argument(
        "--prior-attempts",
        type=int,
        default=0,
        help="API attempts already consumed by an earlier aborted run in this gate",
    )
    return value


def estimate() -> dict[str, object]:
    plan = frozen_acquisition_plan()
    return {
        "network_requests": 0,
        "environment_read": False,
        "filesystem_writes": 0,
        "plan": asdict(plan),
        "plan_sha256": plan.sha256,
        "primary": {
            "method": "four JPX sessions per all-market ranking chunk",
            "expected_attempts": 724,
            "planned_worst_case_attempts": 2757,
        },
        "deterministic_fallback": {
            "method": "one all-market request per JPX session, no rank retries",
            "trigger": "first range-without-code request receives HTTP 400/413/422 or exceeds the local response-size cap",
            "expected_attempts": 1310,
            "planned_worst_case_attempts": 2373,
        },
        "absolute_hard_attempt_limit": 3000,
    }


def install_private_cleanup_script() -> None:
    source = Path(__file__).resolve().with_name("cleanup_private_data.py")
    atomic_write_bytes(PRIVATE_ROOT.expanduser() / source.name, source.read_bytes())


@contextmanager
def private_acquisition_lock():
    lock_path = PRIVATE_ROOT.expanduser() / "acquisition.lock"
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    acquired = False
    try:
        os.fchmod(descriptor, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SafetyError(
                "another private J-Quants acquisition is already active"
            ) from exc
        acquired = True
        yield
    finally:
        if acquired:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def main() -> int:
    args = parser().parse_args()
    if args.estimate:
        print(json.dumps(estimate(), indent=2, sort_keys=True))
        return 0
    if not args.run_id:
        print("error: --run-id is required for --live", file=sys.stderr)
        return 2
    if args.prior_attempts < 0 or args.prior_attempts >= HARD_ATTEMPT_LIMIT:
        print("error: --prior-attempts must be in [0, 2999]", file=sys.stderr)
        return 2
    plan = frozen_acquisition_plan()
    fallback_worst = int(
        CONTRACT["api"]["rank_window_fallback"]["planned_worst_case_attempts"]
    )
    gate_worst = max(plan.planned_worst_case_attempts, fallback_worst)
    if args.prior_attempts + gate_worst > HARD_ATTEMPT_LIMIT:
        print(
            "error: prior attempts plus planned worst case exceed the gate limit",
            file=sys.stderr,
        )
        return 2

    # Ordering is intentional: FileVault and immutable source gates precede
    # environment access, private writes, and network.
    if not filevault_is_active():
        print("error: FileVault preflight did not return active; no API call made", file=sys.stderr)
        return 3
    verify_protected_inputs()
    verify_production_files()
    api_key = os.environ.get(API_KEY_ENV, "")
    if not api_key:
        print(
            "error: JQUANTS_API_KEY is unset; use a hidden local input/export and rerun",
            file=sys.stderr,
        )
        return 4

    existing = PRIVATE_ROOT.expanduser() / "runs" / args.run_id
    if existing.exists() and not args.resume:
        print("error: run_id already exists; pass --resume to reuse it", file=sys.stderr)
        return 5
    try:
        run_directory = create_private_run(args.run_id)
        with private_acquisition_lock():
            install_private_cleanup_script()
            validate_private_tree(PRIVATE_ROOT)
            try:
                journal = AttemptJournal(
                    run_directory / "checkpoint" / "attempts.jsonl",
                    hard_limit=HARD_ATTEMPT_LIMIT - args.prior_attempts,
                )
                client = SafeApiClient(api_key, run_directory, journal=journal)
                result = acquire(
                    client,
                    args.run_id,
                    run_directory,
                    external_prior_attempts=args.prior_attempts,
                )
            finally:
                # Keep cleanup possible after a partial run, but only while
                # holding the account-wide acquisition lock.
                build_deletion_manifest(args.run_id, run_directory)
                validate_private_tree(PRIVATE_ROOT)
    except (RuntimeError, ValueError, SafetyError) as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 6
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
