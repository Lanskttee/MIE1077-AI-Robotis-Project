"""Headless CLI demo — runs one or more LLM turns against the simulated world
and prints the tool trace. No webcam, no Pygame.

Usage::

    # Use MockLLM (no API key needed):
    HOMEMATE_USE_MOCK_LLM=1 HOMEMATE_USE_MOCK_EMOTION=1 python -m homemate.demo_cli sad "open the bedroom curtains"

    # Use real Claude (needs ANTHROPIC_API_KEY):
    python -m homemate.demo_cli sad "find me and cheer me up"
"""

from __future__ import annotations

import argparse
import json
import random
import sys

try:
    from dotenv import load_dotenv
    # override=True so an empty inherited ANTHROPIC_API_KEY doesn't shadow .env
    load_dotenv(override=True)
except ImportError:
    pass  # dotenv is optional; env vars set directly still work

from . import config  # noqa: E402
from .action.skills import Skills  # noqa: E402
from .cognition.llm_agent import MockLLM, make_agent  # noqa: E402
from .memory import MemoryStore  # noqa: E402
from .perception.emotion import MockEmotionDetector  # noqa: E402
from .world.apartment import Apartment  # noqa: E402
from .world.entities import Owner, Robot, place_in_room, random_room  # noqa: E402
from .world.iot import IoTNetwork  # noqa: E402


def build_world(seed: int = 1, owner_room: str | None = None) -> Skills:
    rng = random.Random(seed)
    apt = Apartment()
    robot = Robot(0, 0)
    owner = Owner(0, 0)
    place_in_room(robot, apt, "living_room", rng)
    place_in_room(owner, apt,
                  owner_room or random_room(apt, "living_room", rng), rng)
    iot = IoTNetwork.default()
    emo = MockEmotionDetector()
    emo.start()
    return Skills(apt, robot, owner, iot, emo)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("emotion",
                   choices=("happy", "sad", "angry", "surprised", "neutral", "tired"),
                   help="Mock emotion to inject before the turn")
    p.add_argument("message", help="What to ask the agent")
    p.add_argument("--owner-room", default=None,
                   help="Force the owner into a specific room (default: random)")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--no-memory", action="store_true",
                   help="Skip the long-term memory store for this run.")
    p.add_argument("--reset-memory", action="store_true",
                   help="Wipe the memory store before running.")
    args = p.parse_args()

    skills = build_world(seed=args.seed, owner_room=args.owner_room)
    skills.emotion.inject(args.emotion)

    memory = None if args.no_memory else MemoryStore()
    if memory and args.reset_memory:
        memory.reset()

    print(f"\nRobot starts in: {skills.robot_room()}")
    print(f"Owner is in:     {skills.owner_room()}")
    print(f"Injected emotion: {args.emotion}")
    print(f"LLM: {'MOCK' if config.USE_MOCK_LLM else config.LLM_MODEL}")
    if memory:
        prof = memory.profile()
        print(f"Memory: {memory.root}  (prior episodes: {prof.total_episodes})\n")
    else:
        print("Memory: disabled\n")

    try:
        agent = make_agent(skills, memory=memory)
    except Exception as e:
        print(f"[error] could not start real LLM: {e}\nFalling back to MockLLM.")
        agent = MockLLM(skills, memory=memory)

    result = agent.run_turn(args.message)

    print("---- TOOL TRACE ----")
    for step in result.tool_trace:
        print(f"  -> {step['name']}({json.dumps(step['input'], ensure_ascii=False)})")
        print(f"     {json.dumps(step['output'], ensure_ascii=False)[:160]}")
    print("\n---- DIALOGUE ----")
    for who, text in skills.dialogue:
        print(f"  {who}: {text}")
    print(f"\nFinal summary: {result.final_text}")
    print(f"Robot ended at: {skills.robot_room()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
