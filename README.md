# HomeMate — Simulated LLM-Driven Home Companion Robot

MIE1077 (Artificial Intelligence for Robotics III) course project — University of Toronto, 2026.

HomeMate is a **fully simulated** home companion robot that integrates four cooperating modules:

| Module | Tech |
|---|---|
| **Vision (Perception)** | Real webcam + DeepFace facial-emotion recognition |
| **Cognition (LLM)** | Anthropic Claude (tool-calling loop) |
| **Planning** | A* over a grid, room sweep, LLM as high-level planner (ReAct-style) |
| **Robot Action + IoT** | Mock REST/MQTT-style IoT API + Pygame top-down rendering |

The robot lives in a 2D top-down apartment (kitchen, living room, bedroom, bathroom).
It can: search for its owner room by room, read the owner's emotion from a webcam,
hold an empathetic chat, and actuate smart-home devices (curtains, lamps, toaster,
coffee maker).

---

## Quick start (Windows)

### 1. Install Python 3.10 or newer
Download from <https://www.python.org/downloads/windows/>. During install,
check **"Add python.exe to PATH"**.

Verify:
```powershell
python --version
```

### 2. Install dependencies

From the project root:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> **Note:** `deepface` will download a few hundred MB of TensorFlow models on
> first run. This is expected. If you want a lighter install, see
> `requirements-minimal.txt` (no DeepFace — the system runs with a mock emotion
> detector that you can drive with keyboard keys 1–6).

### 3. Configure the Claude API key
1. Get a key from <https://console.anthropic.com/>.
2. Copy `.env.example` to `.env`:
   ```powershell
   copy .env.example .env
   ```
3. Open `.env` and paste your key after `ANTHROPIC_API_KEY=`.

### 4. Run the demo
```powershell
python -m homemate.main
```

You should see a 2D apartment window. The robot (blue) starts in the living
room; the owner (green) is randomly placed. Press **Enter** to give the agent
a goal in natural language, e.g. *"Find me and tell me a joke"* or
*"Open the bedroom curtains and start the toaster"*.

Keyboard shortcuts:
- `1`..`6` — manually inject an emotion (`happy`, `sad`, `angry`, `surprised`, `neutral`, `tired`) — useful when no webcam is attached.
- `w` — toggle real webcam emotion detection on/off.
- `r` — reset the scenario (re-randomize owner location).
- `Esc` — quit.

---

## Project layout

```
homemate/
├── main.py             # Pygame loop, UI, glue
├── config.py           # Constants, room sizes, palette
├── world/
│   ├── apartment.py    # Grid, rooms, walls, doors
│   ├── entities.py     # Robot, Owner
│   └── iot.py          # Mock IoT devices + REST-style API
├── perception/
│   └── emotion.py      # Webcam + DeepFace, with mock fallback
├── planning/
│   ├── navigator.py    # A* on the apartment grid
│   └── search.py       # Owner room-sweep policy
├── cognition/
│   ├── llm_agent.py    # Anthropic tool-calling loop (+ MockLLM)
│   └── tools.py        # JSON tool schemas + dispatch
└── action/
    └── skills.py       # Primitive skills the LLM can call
tests/
└── test_smoke.py       # End-to-end smoke test using MockLLM (no API key, no GUI)
```

---

## Pushing to GitHub (one-time setup)

Because the project was authored from a sandboxed environment, an orphaned
`.git/` folder may exist. Delete it first, then init fresh:

```powershell
cd C:\Users\xiche\OneDrive\Documents\Claude\Projects\MIE1077\MIE1077-AI-Robotis-Project
Remove-Item -Recurse -Force .git
git init -b main
git add .
git commit -m "Initial MVP: LLM + Vision + Planning + IoT in 2D simulator"
git remote add origin https://github.com/Alex-Xi-Chen/MIE1077-AI-Robotis-Project.git
git push -u origin main
```

After the first push you can use the normal `git add . && git commit -m "..." && git push` flow.

---

## Smoke test (no API key, no GUI)

```powershell
python -m pytest tests/ -q
```

This runs the whole pipeline with a **MockLLM** that follows a scripted scenario
and a **MockEmotion** detector. Lets you verify everything is wired correctly
before you spend Claude tokens.

---

## Roadmap (per proposal)

- **May 7 – May 28** Phase 1: 2D simulator + mock IoT + webcam + emotion — **MVP (this commit)**
- **May 29 – Jun 18** Phase 2: Claude tool loop + A* nav + "find & greet" end-to-end
- **Jun 19 – Jul 9** Phase 3: emotion-aware dialogue, memory, full IoT control, ReAct planner, 20 eval scenarios
- **Jul 10 – Jul 30** Phase 4: full evaluation + ablations + demo video + slide deck + Lecture 13 presentation
