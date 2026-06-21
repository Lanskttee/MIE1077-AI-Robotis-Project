"""CLI: batch-run all built-in demo scripts offline.

Examples::

    python -m homemate.demo_runner
    python -m homemate.demo_runner --only tired_coffee,wind_down
    python -m homemate.demo_runner --json out/demo_scripts.jsonl
"""

from __future__ import annotations

import argparse
import sys

from .runner import DemoBatchRunner, dump_jsonl, format_table, summarize


def main() -> int:
    p = argparse.ArgumentParser(description="Batch-run HomeMate demo scripts (MockLLM).")
    p.add_argument("--only", default=None,
                   help="Comma-separated script ids (default: all).")
    p.add_argument("--memory", action="store_true",
                   help="Enable long-term memory during runs.")
    p.add_argument("--json", default=None, metavar="PATH",
                   help="Write per-script JSONL results.")
    p.add_argument("--verbose", action="store_true",
                   help="Print failing check details.")
    args = p.parse_args()

    ids = None
    if args.only:
        ids = [x.strip() for x in args.only.split(",") if x.strip()]

    runner = DemoBatchRunner(use_memory=args.memory)
    results = runner.run_many(ids)
    print(format_table(results))

    if args.verbose:
        print("\nFailing checks:")
        for r in results:
            if r.ok and not r.error:
                continue
            print(f"\n  {r.script_id}:")
            if r.error:
                print(f"    ERROR: {r.error}")
            for c in r.checks:
                if not c.ok:
                    print(f"    - {c.name}: {c.note}")

    if args.json:
        dump_jsonl(results, args.json)
        print(f"\nWrote JSONL -> {args.json}")

    s = summarize(results)
    return 0 if s["scripts"]["passed"] == s["scripts"]["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
