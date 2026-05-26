# Project context for Claude Code

This file primes a fresh Claude Code session with everything it needs to keep
working on this project. Read it first.

## What this is

**HomeMate** — a simulated home companion robot, submitted as the MIE1077
(Artificial Intelligence for Robotics III) course project at the University of
Toronto, Lecture 13 presentation on **July 30, 2026**.

Single author: Alex (xichenharbin@gmail.com).
GitHub: <https://github.com/Alex-Xi-Chen/MIE1077-AI-Robotis-Project>.

The deliverable is **simulation only** — no physical robot. The output for
the course is:

1. A working live Pygame demo,
2. A 3–5 min recorded demo video covering ~3 scripted scenarios,
3. A slide deck for the July 30 presentation,
4. A short write-up with quantitative evaluation tables (20 scenarios).

The full proposal lives one folder up at `../ECE1724_Home_Companion_Robot_Proposal.tex`
(the filename is historical — the course is MIE1077, the template was reused).

## Architecture (four-module: LLM + Vision + Planning + Robot Action)

| Module        | Where                                | Tech                                                   |
| ------------- | ------------------------------------ | ------------------------------------------------------ |
| Cognition     | `homemate/cognition/`                | Anthropic Claude tool-calling loop; `MockLLM` fallback (planner-backed by default) |
| Vision        | `homemate/perception/emotion.py`     | Real webcam (OpenCV) + DeepFace; `MockEmotion` fallback |
| Planning      | `homemate/planning/`                 | A* on grid + room-sweep policy + ReAct goal decomposer (`react.py`) |
| Robot Action  | `homemate/action/skills.py`          | Primitive skills exposed as JSON tools                 |
| Memory        | `homemate/memory/`                   | JSON-on-disk episodes + profile rollup; brief injected into the system prompt |
| World / UI    | `homemate/world/`, `homemate/main.py`| Pygame top-down apartment, mock IoT (REST-style), 11 devices across 4 rooms |
| Evaluation    | `homemate/eval/`                     | 20-scenario suite + ablation runner + JSONL/table output |

### Design decisions (don't re-litigate without reason)

- **Physical fidelity is intentionally low** (2D top-down) so the demo reads
  clearly on a projector. Avatar-face emotion in 3D simulators is a known
  failure mode; we deliberately decoupled affective input by using the real
  webcam of the presenter as the "owner's face."
- **All heavy deps are lazy-loaded** (`anthropic`, `cv2`, `deepface`) so the
  smoke tests and `MockLLM` path run with stdlib only.
- **LLM treats navigation as instantaneous.** Skills mutate `robot.x/y`
  immediately and stash the A* path in `Skills.pending_path`; the Pygame loop
  animates that path one tile per `ROBOT_STEP_FRAMES` frames. This keeps the
  agent logic simple and the rendering smooth.
- **Tool dispatch is a single function** (`cognition/tools.py::dispatch_tool`)
  so MockLLM and Claude share the same execution path — anything that works
  in tests works live.
- **Mocks everywhere**: `MockLLM`, `MockEmotionDetector`. Anything that costs
  money, needs hardware, or needs network has a deterministic stand-in.

## Current status

**Phase 1 — complete** (initial MVP commit):

- 2D simulator with 4 rooms, walls, doors, A* navigation
- Mock IoT with curtains, lamps, toaster, coffee maker (animated)
- Webcam + DeepFace emotion path + keyboard-driven mock emotion
- Claude tool-calling loop with 8 tools
- Pygame UI with dialogue panel, status bar, input field
- Headless CLI demo (`homemate/demo_cli.py`)

**Phase 2 — code complete, awaiting live API key**:

- `homemate/scripts/live_check.py` — one tiny Anthropic ping for connectivity
  smoke. Run `python -m homemate.scripts.live_check` once your key is in `.env`.
- `LLMAgent` audited; tool-calling loop, history shape, and `stop_reason`
  handling all correct.
- `dotenv` import is now optional everywhere (works fine when env vars are
  set directly).

**Phase 3 — complete**:

- **Long-term memory** (already shipped earlier): `homemate/memory/` —
  JSON-on-disk store of episodes + profile rollup, brief injected into the
  LLM system prompt. Configurable via `HOMEMATE_MEMORY_DIR`.
- **ReAct-style planner** (`homemate/planning/react.py`): a deterministic,
  stdlib-only decomposer that turns a free-text request into ordered
  sub-goals (`find_owner` → `sense_emotion` → `speak` → `goto_device` +
  `actuate` per device). `PlanExecutor` runs a plan via the same
  `dispatch_tool` path the LLM uses. Exposed to Claude as the `make_plan`
  tool — the LLM can call it to "think before acting" on multi-step
  requests. `MockLLM` uses it by default; pass `use_planner=False` for
  ablations.
- **Full IoT coverage** (`homemate/world/iot.py`): 11 devices across 4
  rooms, 9 device kinds — curtains, lamps, toaster, coffee maker,
  thermostat, TV, speaker, fan, front-door lock. Each renders with a
  custom Pygame widget in `main.py::_draw_device`.
- **20-scenario evaluation suite** (`homemate/eval/`): scenarios, criteria
  builders, runner with ablation flags, CLI entry point. Baseline result:
  20/20 scenarios, 109/109 criteria with MockLLM + planner. Run with
  `python -m homemate.eval` (see flags below).

End-to-end MockLLM smoke verified: 3-action request "Set the thermostat to
24 degrees, brew coffee, and dim the bedroom lamp" → 9 tool calls →
thermostat target=24, coffee brewing, lamp brightness=0.3. Empathy line
selected from detected `sad` emotion.

Tests: **55 pass** (16 original + 14 planner + 10 IoT + 15 eval).

## Roadmap (the rest of the proposal)

Aligned with the MIE1077 lecture schedule:

- **May 29 – Jun 18 (Lectures 5–7) — Phase 2 (code done; needs API key)**
  - ~~Wire Claude live (the code is ready; just need an `ANTHROPIC_API_KEY`)~~ ✓
    code path audited; `live_check.py` ready
  - Polish UI: smoother path animation, IoT progress bars, owner walk
  - End-to-end "find & greet" works with the real model (run `live_check.py`
    first, then `python -m homemate.main`)
- **Jun 19 – Jul 9 (Lectures 8–10) — Phase 3 (complete)**
  - ~~Long-term memory (JSON or vector store; summarise into each prompt)~~ ✓
    JSON store shipped (`homemate/memory/`)
  - ~~ReAct-style high-level planner (multi-step goal decomposition)~~ ✓
    `homemate/planning/react.py` + `make_plan` tool
  - ~~Full IoT control coverage~~ ✓ 11 devices, 9 kinds, all rooms covered
  - ~~**20-scenario evaluation suite** (the deliverable)~~ ✓
    `homemate/eval/`; baseline 20/20, no-emotion ablation 8/20
- **Jul 10 – Jul 30 (Lectures 11–13) — Phase 4**
  - Run the eval suite + ablations (no-emotion, no-LLM-planner, no-memory)
  - Record the 3–5 min demo video
  - Slide deck
  - Final report + Lecture 13 presentation

When a session asks "what's next", the answer is the next bullet in this
roadmap.

## Code conventions

- Python 3.10+ (uses PEP 604 `X | Y` type unions, dataclass `field()`, etc.).
- `from __future__ import annotations` at the top of every module.
- Type-annotate everything new; keep `Any` for genuinely dynamic JSON.
- Skills return JSON-friendly dicts with `{"ok": bool, ...}` shape.
- All randomness goes through an explicit `random.Random` for reproducibility
  in tests.
- No emojis in code or commit messages.
- Tests are pytest-compatible but written so they also run as plain functions
  (the sandbox doesn't have pytest — see `tests/test_smoke.py` for the
  fallback runner pattern).

## How to run things

```powershell
# Setup (one time)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # then put your API key in .env

# Tests
python -m pytest tests/ -q

# Headless CLI (no GUI, no API key needed if HOMEMATE_USE_MOCK_LLM=1)
$env:HOMEMATE_USE_MOCK_LLM="1"; $env:HOMEMATE_USE_MOCK_EMOTION="1"
python -m homemate.demo_cli sad "find me and brew coffee"

# Pygame demo
python -m homemate.main

# 20-scenario eval (baseline)
python -m homemate.eval

# Ablations (for the write-up tables)
python -m homemate.eval --no-planner
python -m homemate.eval --no-memory
python -m homemate.eval --no-emotion

# Real-Claude eval (needs ANTHROPIC_API_KEY in .env)
python -m homemate.eval --use-llm

# Dump per-scenario JSONL for inclusion in the report
python -m homemate.eval --json out/eval_baseline.jsonl
```

Env flags:

| Var                        | Effect                                                     |
| -------------------------- | ---------------------------------------------------------- |
| `ANTHROPIC_API_KEY`        | Required to use real Claude                                |
| `HOMEMATE_MODEL`           | Defaults to `claude-sonnet-4-6`                            |
| `HOMEMATE_USE_MOCK_LLM=1`  | Use the deterministic `MockLLM` (no API calls)             |
| `HOMEMATE_USE_MOCK_EMOTION=1` | Skip webcam/DeepFace, use keyboard-injected mock emotion |
| `HOMEMATE_MEMORY_DIR`      | Memory store dir (default: `<project>/data/memory/`)       |

## Key bindings in the Pygame UI

- `Enter` open input box; type a request, `Enter` again to send
- `1`..`6` inject mock emotion (happy/sad/angry/surprised/neutral/tired)
- `w` toggle real webcam emotion detection on/off
- `r` reset scenario (new random owner location)
- `Esc` quit

## How to make changes

Most changes hit one of three places:

- **A new tool / skill** → add the schema to `cognition/tools.py::TOOL_SCHEMAS`,
  add the dispatch branch in `dispatch_tool`, implement the method on
  `action/skills.py::Skills`. Update the MockLLM if the tool should be part of
  the scripted offline path.
- **A new IoT device** → subclass `IoTDevice` in `world/iot.py`, override
  `actions()` / `apply()`, and register it in `IoTNetwork.default()`. Add a
  rendering case in `main.py::App._draw_device` if you want a custom widget.
- **A new evaluation scenario** → append a `Scenario(...)` to the
  `SCENARIOS` list in `homemate/eval/scenarios.py`. The `assert len == 20`
  at the bottom guards the count — bump it if you intentionally grow the
  suite. Compose `criteria` from the builders in `homemate/eval/criteria.py`.
- **A new planner step kind** → add a `PlanStep(kind=...)` branch in
  `ReActPlanner.plan` and a matching dispatch case in
  `PlanExecutor._step_to_call`. The planner is the single source of truth
  for keyword routing — update `KIND_KEYWORDS` and `action_for` there, not
  in `MockLLM`.
- **Memory shape changes** → edit `Episode` / `Profile` in
  `homemate/memory/store.py`. If you add a field, update `from_json` so old
  on-disk records still load. The brief consumed by the LLM is built in
  `MemoryStore.memory_brief()` — keep it short (< ~300 chars) so it doesn't
  bloat every prompt.

## Things to avoid

- Don't import `pygame`, `anthropic`, `cv2`, or `deepface` at module top
  level outside `main.py` — it breaks the headless smoke tests.
- Don't rename `MockLLM` / `MockEmotionDetector` — `tests/test_smoke.py`
  depends on them.
- Don't bake the Anthropic API key into source. It only ever comes from
  `.env` or the environment.
- Don't touch the broken `.git/` folder that came from an earlier sandboxed
  attempt — delete it cleanly with `Remove-Item -Recurse -Force .git`, then
  `git init` fresh (instructions also in `README.md`).
