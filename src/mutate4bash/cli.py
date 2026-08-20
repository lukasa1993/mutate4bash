from __future__ import annotations

import argparse
import json
import sys
import subprocess
from pathlib import Path

from . import __version__
from .core import collect_mutations, run_baseline, run_mutations, write_manifest


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Mutation testing for Bash source.")
    value.add_argument("filters", nargs="*")
    value.add_argument("--root", type=Path, default=Path("."))
    value.add_argument("--test-command", default="bats tests")
    value.add_argument("--timeout", type=float, default=60.0)
    value.add_argument("--max-mutants", type=int)
    value.add_argument("--list", action="store_true")
    value.add_argument("--skip-baseline", action="store_true")
    value.add_argument("--manifest", type=Path, default=Path("target/mutation/mutations.json"))
    value.add_argument("--json", action="store_true", dest="json_output")
    value.add_argument("--fail-on-survivors", action="store_true")
    value.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = args.root.resolve()
    try:
        mutations = collect_mutations(root, args.filters)
        if args.list:
            payload = [mutation.to_dict() for mutation in mutations]
            print(json.dumps(payload, indent=2, sort_keys=True) if args.json_output else "\n".join(f"{m.id}\t{m.file}:{m.line}:{m.column}\t{m.original} -> {m.replacement}" for m in mutations))
            return 0
        if not args.skip_baseline:
            run_baseline(root, args.test_command, args.timeout)
        results = run_mutations(root, mutations, args.test_command, args.timeout, args.max_mutants)
        manifest = args.manifest if args.manifest.is_absolute() else root / args.manifest
        write_manifest(manifest, results)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"mutate4bash: {error}", file=sys.stderr)
        return 1
    if args.json_output:
        print(json.dumps([result.to_dict() for result in results], indent=2, sort_keys=True))
    else:
        survived = [result for result in results if result.status == "survived"]
        print(f"Mutation Report\n===============\nMutants: {len(results)}\nKilled: {len(results) - len(survived)}\nSurvived: {len(survived)}")
        for result in survived:
            mutation = result.mutation
            print(f"SURVIVED {mutation.file}:{mutation.line}:{mutation.column} {mutation.original} -> {mutation.replacement}")
    return 2 if args.fail_on_survivors and any(result.status == "survived" for result in results) else 0
