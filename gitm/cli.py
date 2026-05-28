"""``gitm`` command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gitm",
        description="Behavioral compiler and intervention runtime.",
    )
    p.add_argument("--version", action="store_true", help="Print version and exit.")
    sub = p.add_subparsers(dest="cmd")

    run = sub.add_parser("run", help="Run the autonomous optimization loop.")
    run.add_argument("--workload", required=True, help="Workload identifier, e.g. vllm-decode.")
    run.add_argument("--budget", default="24h", help="Wall-clock budget, e.g. 24h.")
    run.add_argument(
        "--target",
        default="15%",
        help="Target improvement fraction (15%% or 0.15).",
    )
    run.add_argument("--data-root", default=None, help="Override $GITM_DATA_ROOT.")
    run.add_argument("--report", type=Path, default=None, help="Write report markdown here.")

    replay = sub.add_parser("replay", help="Counterfactual replay of an intervention on a trace.")
    replay.add_argument("trace", type=Path, help="Captured trace file.")
    replay.add_argument("--intervention", type=Path, required=True, help="Intervention spec YAML.")

    apply_cmd = sub.add_parser("apply", help="Apply an intervention spec to the live workload.")
    apply_cmd.add_argument("--intervention", type=Path, required=True)

    sub.add_parser("doctor", help="Probe environment, GPUs, and data root layout.")

    return p


def _parse_target(s: str) -> float:
    s = s.strip()
    if s.endswith("%"):
        return float(s[:-1]) / 100.0
    return float(s)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.version:
        from gitm import __version__

        print(__version__)
        return 0

    if args.cmd is None:
        _parser().print_help()
        return 0

    if args.cmd == "run":
        from gitm import optimize

        result = optimize(
            workload=args.workload,
            budget=args.budget,
            target=_parse_target(args.target),
            data_root=args.data_root,
        )
        if args.report is not None:
            args.report.write_text(result.get("report_md", ""))
        else:
            print(json.dumps(result.get("summary", {}), indent=2))
        return 0

    if args.cmd == "replay":
        from gitm.optimizer.replay import predict_delta_from_files

        delta = predict_delta_from_files(args.trace, args.intervention)
        print(json.dumps({"predicted_delta": delta}, indent=2))
        return 0

    if args.cmd == "apply":
        from gitm.optimizer.apply import apply_intervention_from_file

        result = apply_intervention_from_file(args.intervention)
        print(json.dumps(result, indent=2))
        return 0

    if args.cmd == "doctor":
        from gitm.doctor import doctor

        report = doctor()
        print(json.dumps(report, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
