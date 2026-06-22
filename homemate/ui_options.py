"""CLI options for the Pygame demo — kept import-light so tests can parse argv
without initialising pygame or touching the network stack.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from .config import EMOTIONS


@dataclass(frozen=True)
class MainOptions:
    """Runtime knobs for :class:`homemate.main.App`."""

    seed: int = 7
    owner_room: str | None = None
    emotion: str | None = None
    mock_llm: bool = False
    mock_emotion: bool = False
    freeze_owner: bool = False
    script: str | None = None
    auto_run: bool = False
    auto_message: str | None = None
    load_snapshot: str | None = None
    snapshot_path: str = "data/scenarios/last_snapshot.json"
    record_session: bool = True
    replay_session: str | None = None
    session_title: str | None = None
    replan_demo: bool = False


def parse_main_args(argv: list[str] | None = None) -> MainOptions:
    """Parse ``python -m homemate.main`` flags."""
    from .demo_scripts import script_ids

    p = argparse.ArgumentParser(
        description="HomeMate Pygame demo (offline-friendly with --offline).",
    )
    p.add_argument(
        "--seed", type=int, default=7,
        help="RNG seed for owner placement on reset (default: 7).",
    )
    p.add_argument(
        "--owner-room",
        choices=("living_room", "kitchen", "bedroom", "bathroom"),
        default=None,
        help="Pin the owner to a room instead of randomising.",
    )
    p.add_argument(
        "--emotion",
        choices=EMOTIONS,
        default=None,
        help="Pre-inject a mock emotion before the first request.",
    )
    p.add_argument(
        "--mock-llm", action="store_true",
        help="Force the deterministic MockLLM (no Anthropic API calls).",
    )
    p.add_argument(
        "--mock-emotion", action="store_true",
        help="Force keyboard-injectable mock emotions (skip webcam).",
    )
    p.add_argument(
        "--freeze-owner", action="store_true",
        help="Disable owner wandering (keeps the layout stable for demos).",
    )
    p.add_argument(
        "--offline", action="store_true",
        help="Shorthand for --mock-llm --mock-emotion --freeze-owner.",
    )
    p.add_argument(
        "--script",
        choices=script_ids(),
        default=None,
        help="Load a built-in demo script (implies offline-friendly settings).",
    )
    p.add_argument(
        "--auto-run", action="store_true",
        help="With --script, send the script message automatically after startup.",
    )
    p.add_argument(
        "--load-snapshot", default=None, metavar="PATH",
        help="Restore robot/owner/IoT state from a JSON snapshot on startup.",
    )
    p.add_argument(
        "--replan-demo", action="store_true",
        help="Mock LLM/emotion, owner CAN wander, auto-send coffee request "
             "(for testing dynamic replanning — do NOT use --offline).",
    )
    p.add_argument(
        "--list-scripts", action="store_true",
        help="Print available demo scripts and exit.",
    )
    p.add_argument(
        "--no-record", action="store_true",
        help="Disable automatic session recording to data/sessions/.",
    )
    p.add_argument(
        "--replay-session", default=None, metavar="ID_OR_PATH",
        help="Load a recorded session and enter replay mode.",
    )
    p.add_argument(
        "--list-sessions", action="store_true",
        help="Print recorded sessions and exit.",
    )
    p.add_argument(
        "--session-title", default=None,
        help="Custom title for the session file created on startup.",
    )
    args = p.parse_args(argv)

    if args.list_scripts:
        from .demo_scripts import DEMO_SCRIPTS
        for s in DEMO_SCRIPTS.values():
            print(f"{s.id:16}  {s.title}")
            print(f"{'':16}  {s.description}")
            print(f"{'':16}  message: {s.message!r}")
            print()
        raise SystemExit(0)

    if getattr(args, "list_sessions", False):
        from .session import SessionStore
        store = SessionStore()
        rows = store.list_sessions()
        if not rows:
            print("No sessions found under data/sessions/")
        for row in rows:
            print(f"{row['session_id']:<32}  turns={row['turns']}  {row['title']}")
        raise SystemExit(0)

    offline = args.offline
    if args.replan_demo:
        return MainOptions(
            seed=7,
            owner_room="bedroom",
            emotion="tired",
            mock_llm=True,
            mock_emotion=True,
            freeze_owner=False,
            auto_run=True,
            auto_message="I'm tired. Brew some coffee.",
            record_session=not args.no_record,
            replay_session=args.replay_session,
            session_title=args.session_title or "Replan demo",
            replan_demo=True,
        )
    opts = MainOptions(
        seed=args.seed,
        owner_room=args.owner_room,
        emotion=args.emotion,
        mock_llm=args.mock_llm or offline or bool(args.script),
        mock_emotion=args.mock_emotion or offline or bool(args.script),
        freeze_owner=args.freeze_owner or offline or bool(args.script),
        auto_run=args.auto_run,
        load_snapshot=args.load_snapshot,
        record_session=not args.no_record,
        replay_session=args.replay_session,
        session_title=args.session_title,
    )
    if args.script:
        from .demo_scripts import apply_script
        opts = apply_script(opts, args.script)
    return opts
