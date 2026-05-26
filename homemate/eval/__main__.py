"""CLI entry point for the evaluation suite.

Examples::

    # baseline (MockLLM, planner ON, memory ON, emotion injected)
    python -m homemate.eval

    # ablations
    python -m homemate.eval --no-planner
    python -m homemate.eval --no-memory
    python -m homemate.eval --no-emotion

    # use real Claude (requires ANTHROPIC_API_KEY in .env)
    python -m homemate.eval --use-llm

    # dump per-scenario JSON for the write-up
    python -m homemate.eval --json out/eval_baseline.jsonl
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

from .runner import EvalRunner, dump_jsonl, format_table, summarize
from .scenarios import SCENARIOS


def main() -> int:
    p = argparse.ArgumentParser(description="Run the HomeMate 20-scenario eval.")
    p.add_argument("--no-planner", action="store_true",
                   help="Ablation: disable the ReAct planner (uses MockLLM's legacy keyword path).")
    p.add_argument("--no-memory", action="store_true",
                   help="Ablation: run without the long-term memory store.")
    p.add_argument("--no-emotion", action="store_true",
                   help="Ablation: do not inject the scenario emotion (read_emotion will fail).")
    p.add_argument("--use-llm", action="store_true",
                   help="Use real Claude (LLMAgent) instead of MockLLM. Requires API key.")
    p.add_argument("--only", default=None,
                   help="Comma-separated list of scenario ids to run (default: all 20).")
    p.add_argument("--tag", default=None,
                   help="Run only scenarios with this tag.")
    p.add_argument("--json", default=None,
                   help="Write per-scenario JSONL results to this path.")
    p.add_argument("--verbose", action="store_true",
                   help="Print failing criterion details inline.")
    args = p.parse_args()

    scenarios = list(SCENARIOS)
    if args.only:
        wanted = {x.strip() for x in args.only.split(",")}
        scenarios = [s for s in scenarios if s.id in wanted]
    if args.tag:
        scenarios = [s for s in scenarios if args.tag in s.tags]

    if not scenarios:
        print("No scenarios match the filter.")
        return 2

    runner = EvalRunner(
        planner=not args.no_planner,
        memory=not args.no_memory,
        inject_emotion=not args.no_emotion,
        use_llm=args.use_llm,
    )

    label = "MockLLM" if not args.use_llm else "Claude"
    flags = []
    if args.no_planner:  flags.append("no_planner")
    if args.no_memory:   flags.append("no_memory")
    if args.no_emotion:  flags.append("no_emotion")
    flag_str = ",".join(flags) if flags else "baseline"

    print(f"Config: agent={label}  flags={flag_str}  scenarios={len(scenarios)}\n")

    results = runner.run_many(scenarios)
    print(format_table(results))

    if args.verbose:
        print("\nFailing criteria details:")
        for r in results:
            failing = [c for c in r.criteria if not c.ok]
            if failing or r.error:
                print(f"\n  {r.scenario_id}:")
                if r.error:
                    print(f"    ERROR: {r.error}")
                for c in failing:
                    print(f"    - {c.name}: {c.note}")

    if args.json:
        dump_jsonl(results, Path(args.json))
        print(f"\nWrote per-scenario JSON to {args.json}")

    s = summarize(results)
    return 0 if s["scenarios"]["passed"] == s["scenarios"]["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
