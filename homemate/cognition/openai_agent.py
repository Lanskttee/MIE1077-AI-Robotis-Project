"""GPT-4o-mini agent using OpenAI tool-calling.

Drop-in replacement for LLMAgent. Uses the same tools, system prompt, and
dispatch path — only the API call format differs (OpenAI vs Anthropic).
"""
from __future__ import annotations

import json
from typing import Any

from ..action.skills import Skills
from ..memory import MemoryStore, build_episode_from_turn
from .llm_agent import SYSTEM_PROMPT, TurnResult
from .tools import TOOL_SCHEMAS, dispatch_tool


def _anthropic_to_openai_tools(schemas: list[dict]) -> list[dict]:
    """Convert Anthropic input_schema format → OpenAI function format."""
    return [
        {
            "type": "function",
            "function": {
                "name": s["name"],
                "description": s.get("description", ""),
                "parameters": s.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for s in schemas
    ]


OPENAI_TOOLS = _anthropic_to_openai_tools(TOOL_SCHEMAS)


class OpenAIAgent:
    def __init__(self, skills: Skills, *, model: str = "gpt-4o-mini",
                 api_key: str, max_iters: int = 12,
                 memory: MemoryStore | None = None) -> None:
        from openai import OpenAI
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set.")
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.skills = skills
        self.max_iters = max_iters
        self.memory = memory
        self.history: list[dict[str, Any]] = []

    def run_turn(self, user_message: str) -> TurnResult:
        room_start = self.skills.robot_room()
        self.history.append({"role": "user", "content": user_message})
        result = self._run_loop()
        self._record(user_message, room_start, result)
        return result

    def _world_brief(self) -> str:
        s = self.skills
        return json.dumps({
            "robot_room": s.robot_room(),
            "owner_found_this_episode": s.owner_found,
            "devices": [
                {"id": d.device_id, "room": d.room, "kind": d.kind, "state": d.state}
                for d in s.iot.list()
            ],
        }, indent=2)

    def _build_system(self) -> str:
        parts = [SYSTEM_PROMPT, "\n\nCurrent world snapshot:\n", self._world_brief()]
        if self.memory:
            brief = self.memory.memory_brief()
            if brief:
                parts.append("\n\nWhat you remember about this owner:\n")
                parts.append(brief)
        return "".join(parts)

    def _run_loop(self) -> TurnResult:
        result = TurnResult()
        for _ in range(self.max_iters):
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": self._build_system()}] + self.history,
                tools=OPENAI_TOOLS,
                tool_choice="auto",
                max_tokens=1024,
            )
            msg = resp.choices[0].message
            tool_calls = msg.tool_calls or []

            # Append assistant turn to history
            assistant_entry: dict[str, Any] = {
                "role": "assistant",
                "content": msg.content or "",
            }
            if tool_calls:
                assistant_entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ]
            self.history.append(assistant_entry)

            if msg.content and msg.content.strip():
                result.final_text = msg.content.strip()

            if not tool_calls:
                return result

            # Execute tools and feed results back
            for tc in tool_calls:
                name = tc.function.name
                try:
                    inp = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, ValueError):
                    inp = {}
                out = dispatch_tool(self.skills, name, inp)
                result.tool_trace.append({"name": name, "input": inp, "output": out})
                if name == "speak" and out.get("ok"):
                    result.spoken.append(out["spoken"])
                self.history.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(out, ensure_ascii=False),
                })

            if resp.choices[0].finish_reason != "tool_calls":
                return result

        return result

    def _record(self, user_message: str, room_start: str | None,
                result: TurnResult) -> None:
        if not self.memory:
            return
        ep = build_episode_from_turn(
            user_message=user_message,
            robot_room_start=room_start,
            robot_room_end=self.skills.robot_room(),
            owner_room=self.skills.owner_room() if self.skills.owner_found else None,
            tool_trace=result.tool_trace,
            spoken=result.spoken,
            final_text=result.final_text,
        )
        self.memory.record_episode(ep)
