# HomeMate

Simulated home companion robot. MIE1077 (Artificial Intelligence for
Robotics III) course project, University of Toronto, 2026.

The robot lives in a 2D top-down apartment (living room, kitchen, bedroom,
bathroom). It searches for the owner room by room, reads the owner's
facial emotion from the webcam, holds a short empathetic exchange, and
actuates simulated smart-home devices. The pipeline is: OpenCV webcam ->
DeepFace emotion classifier -> Anthropic Claude tool-calling loop -> A*
navigation -> mock IoT.

## Architecture

| Module     | Implementation                                                  |
|------------|-----------------------------------------------------------------|
| Perception | OpenCV webcam capture, DeepFace facial-emotion classifier       |
| Cognition  | Anthropic Claude tool-use loop; deterministic `MockLLM` fallback |
| Planning   | A* on the apartment grid; time-of-day priors for owner search   |
| Action     | 8 primitive skills exposed as JSON tool schemas                 |
| Memory     | Append-only JSONL of episodes + profile rollup in the prompt    |
| UI         | Pygame top-down view, dialogue panel, status bar, input field   |

## Demo

![HomeMate](docs/images/pygame_demo.gif)

The view is a 24 × 16 tile apartment split into four rooms (living
room, kitchen, bedroom, bathroom) separated by walls and doors. The
blue circle is the robot, the green square is the owner. IoT devices
sit in fixed slots inside each room: curtains (`C-X` closed / `C-O`
open), lamps (`L-` off / `L+` on), a kitchen toaster with a `T%`
progress label, and a coffee maker with a cup counter (`K0`, `K1`…).
The right-hand panel logs the dialogue, and the top bar shows the
robot's current room, the owner's detected emotion, and a status
string.

The recorded scenario runs the full four-module pipeline once:

1. **Establishing shot.** Robot in the living room, owner in the
   bedroom. Top bar reads `robot: living_room`, emotion `neutral`.
2. **User request.** `you: I'm tired. Brew some coffee.` appears in
   the dialogue panel; the status bar shifts to `Sending to LLM…`.
3. **Find the owner.** The planning module runs A\* over the grid
   from the robot's current tile to a walkable tile in the bedroom.
   The robot then animates one tile per frame across the living room,
   through the corridor door, and into the bedroom.
4. **Read emotion.** With the robot and the owner in the same room,
   the perception module is polled. The GIF uses the mock detector
   (`tired`, 0.95 confidence); the live Pygame demo substitutes the
   real DeepFace + webcam path. The top bar updates accordingly.
5. **Empathetic reply.** The cognition module emits a `speak` tool
   call shaped by the detected emotion: `robot: You look tired. Let
   me start the coffee.`
6. **Cross to the kitchen.** A second A\* search routes the robot from
   the bedroom to the coffee maker tile in the kitchen; the path is
   again animated tile-by-tile.
7. **Actuate the IoT.** `set_device(coffee.kitchen, brew)` flips the
   device into its brewing state. The coffee maker's colour deepens
   and its progress ticks forward each frame; the cup counter
   increments when a brew cycle finishes.
8. **Close out.** Two short follow-up lines (`Brewing. Rest up.` →
   `Coffee is ready.`) close the dialogue.

Together, those eight steps exercise every module in the architecture
table above: perception (emotion read), cognition (tool selection and
language), planning (two A\* searches), and action (navigation +
IoT actuation), with the world and UI updating each frame. The GIF
runs the deterministic `MockLLM` so the scene is byte-reproducible;
swapping in real Claude requires only an `ANTHROPIC_API_KEY` and
changes no other code path.

Regenerate the demo assets from the current code:

```powershell
python -m homemate.scripts.gif_demo    # animated GIF
python -m homemate.scripts.snapshot    # single-frame PNG
```

## Setup

Python 3.10 or newer. Python 3.12 is recommended on Windows: at the time
of writing, `pygame`, `tensorflow`, and `deepface` do not yet publish
wheels for 3.14.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Then paste your Anthropic API key into `.env`. Get one at
<https://console.anthropic.com/>.

`requirements-minimal.txt` skips DeepFace and TensorFlow. Use it if you
only need the mock emotion path (keys `1`-`6` instead of the real
webcam). DeepFace downloads a few hundred MB of model weights on first
webcam read.

Windows path-length note: TensorFlow ships some deeply nested files. If
you see `OSError [Errno 2]` during install, enable long-path support
once:

```powershell
# elevated PowerShell
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
    -Name LongPathsEnabled -Value 1 -Type DWord
```

## Running

```powershell
python -m homemate.main                    # Pygame UI
python -m homemate.demo_cli sad "find me"  # headless one-turn run
python -m pytest tests/ -q                 # smoke + memory tests
```

Pygame key bindings:

| Key      | Action                                                   |
|----------|----------------------------------------------------------|
| `Enter`  | Open input field; press again to send                    |
| `1`-`6`  | Inject a mock emotion (`happy`, `sad`, `angry`, `surprised`, `neutral`, `tired`) |
| `w`      | Toggle the real webcam emotion detector                  |
| `r`      | Reset the scenario (re-randomise the owner location)     |
| `Esc`    | Quit                                                     |

Environment flags:

| Variable                      | Effect                                              |
|-------------------------------|-----------------------------------------------------|
| `ANTHROPIC_API_KEY`           | Required for the real Claude path                   |
| `HOMEMATE_MODEL`              | Defaults to `claude-sonnet-4-6`                     |
| `HOMEMATE_USE_MOCK_LLM=1`     | Use the deterministic mock agent                    |
| `HOMEMATE_USE_MOCK_EMOTION=1` | Skip the webcam, use keyboard-injected emotion      |
| `HOMEMATE_MEMORY_DIR`         | Override the memory directory (default `data/memory/`) |

`demo_cli` also accepts `--no-memory` and `--reset-memory`.

## Layout

```
homemate/
  main.py             Pygame loop and UI
  config.py           Grid, palette, runtime flags
  world/              Apartment, robot/owner entities, mock IoT network
  perception/         Webcam + DeepFace; mock fallback
  planning/           A*; time-of-day room search policy
  cognition/          Claude tool-calling loop; JSON tool schemas
  action/             Primitive skills exposed to the LLM
  memory/             JSONL episode log + profile rollup
  scripts/            live_check.py, snapshot.py, gif_demo.py
tests/
  test_smoke.py       End-to-end MockLLM run
  test_memory.py      Memory module unit tests
```

## Roadmap

| Window          | Phase                                              | Status                                                    |
|-----------------|----------------------------------------------------|-----------------------------------------------------------|
| May 7 - May 28  | 2D simulator, mock IoT, webcam emotion             | done                                                      |
| May 29 - Jun 18 | Claude tool loop, A* navigation, find-and-greet    | done; `live_check` confirms the API path                  |
| Jun 19 - Jul 9  | Memory, ReAct planner, 20-scenario eval suite      | memory done; planner and eval suite in progress           |
| Jul 10 - Jul 30 | Full evaluation, ablations, demo video, slide deck | pending                                                   |
