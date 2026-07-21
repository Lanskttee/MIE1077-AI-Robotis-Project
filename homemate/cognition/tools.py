"""Anthropic-style tool schemas + dispatcher.

The tool schemas are written in the JSON-schema dialect that Claude's
tool-use API expects (see https://docs.claude.com/en/docs/build-with-claude/tool-use).

``dispatch_tool`` maps a (name, input) pair onto the corresponding ``Skills``
method.
"""

from __future__ import annotations

from typing import Any

from ..action.skills import Skills


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "navigate_to_room",
        "description": "Move the robot to the centre of the named room. "
                       "Returns whether the owner is visible there.",
        "input_schema": {
            "type": "object",
            "properties": {
                "room": {
                    "type": "string",
                    "enum": ["living_room", "kitchen", "bedroom", "bathroom"],
                    "description": "Which room to go to.",
                },
            },
            "required": ["room"],
        },
    },
    {
        "name": "navigate_to_device",
        "description": "Move the robot near a specific IoT device. Useful before "
                       "actuating something where physical co-location matters.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string"},
            },
            "required": ["device_id"],
        },
    },
    {
        "name": "find_owner",
        "description": "Sweep rooms in time-of-day priority until the owner is found. "
                       "Use this when you don't know where the owner is.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "look_around",
        "description": "Report the robot's current room, whether the owner is here, "
                       "and which IoT devices are in this room.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_emotion",
        "description": "Read the owner's facial emotion from the webcam. "
                       "Only works when the robot is in the same room as the owner.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "speak",
        "description": "Say something out loud to the owner. Keep it short and "
                       "natural. Use the owner's detected emotion to shape tone.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The line to speak."},
            },
            "required": ["text"],
        },
    },
    {
        "name": "list_devices",
        "description": "List all IoT devices in the apartment with their current state.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "scan_room",
        "description": "Perform a systematic boustrophedon sweep of a room to "
                       "locate the owner. Use when you are in or suspect a room "
                       "but cannot see the owner at the centre.",
        "input_schema": {
            "type": "object",
            "properties": {
                "room": {
                    "type": "string",
                    "enum": ["living_room", "kitchen", "bedroom", "bathroom"],
                },
            },
            "required": ["room"],
        },
    },
    {
        "name": "clean_room",
        "description": "Systematically clean/tidy a room by performing a full "
                       "boustrophedon sweep. Use when the owner asks to clean, "
                       "tidy, vacuum, or sweep a room.",
        "input_schema": {
            "type": "object",
            "properties": {
                "room": {
                    "type": "string",
                    "enum": ["living_room", "kitchen", "bedroom", "bathroom"],
                    "description": "Which room to clean.",
                },
            },
            "required": ["room"],
        },
    },
    {
        "name": "get_robot_state",
        "description": "Return the robot pose, navigation mode, motion odometry, "
                       "occupancy map stats, path tracker, and probabilistic "
                       "belief over the owner's room.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "plan_device_route",
        "description": "Compute an optimized visit order for multiple IoT devices "
                       "using costmap distances and TSP heuristics (nearest-neighbor "
                       "+ 2-opt). Does not move the robot.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Device IDs to visit, e.g. ['coffee.kitchen', 'lamp.bedroom'].",
                },
            },
            "required": ["device_ids"],
        },
    },
    {
        "name": "visit_devices",
        "description": "Navigate along an optimized multi-device tour. Call before "
                       "actuating each device with set_device.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["device_ids"],
        },
    },
    {
        "name": "explore_frontier",
        "description": "Active mapping: navigate toward unknown map frontiers to "
                       "expand coverage. May locate the owner.",
        "input_schema": {
            "type": "object",
            "properties": {
                "max_hops": {
                    "type": "integer",
                    "description": "Max frontier targets to visit (default 3).",
                },
            },
        },
    },
    {
        "name": "make_plan",
        "description": "Generate a high-level plan (ordered sub-goals like "
                       "find_owner, sense_emotion, speak, actuate) for the "
                       "user's current request. Useful as a first step on "
                       "multi-step requests — read the plan, then carry it out "
                       "using the other tools. Calling this does NOT execute "
                       "any actions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_message": {
                    "type": "string",
                    "description": "The user request, restated in your own words if useful.",
                },
            },
            "required": ["user_message"],
        },
    },
    {
        "name": "pickup_item",
        "description": "Pick up a ready item (e.g. brewed coffee, finished toast) from "
                       "a device and add it to the robot's inventory. Only works when "
                       "the item is ready (coffee cups > 0, toast progress = 100%).",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string",
                              "description": "Device to pick up from, e.g. 'coffee.kitchen'"},
            },
            "required": ["device_id"],
        },
    },
    {
        "name": "deliver_item",
        "description": "Navigate to the owner and hand over everything the robot is "
                       "carrying. Use after pickup_item to complete a delivery.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "set_device",
        "description": "Actuate an IoT device. Supported (device_id, action) pairs: "
                       "curtain.* -> open|close|toggle; "
                       "lamp.* -> on|off|toggle|set_brightness(brightness:0..1); "
                       "toaster.kitchen -> start(level?:1..5)|stop|set_level(level:1..5); "
                       "coffee.kitchen -> brew|stop; "
                       "thermostat.* -> set_target(target_c:10..32)|set_mode(mode:heat|cool|auto|off)|off; "
                       "tv.* -> on|off|toggle|set_channel(channel:news|movies|music|sports|kids)|set_volume(volume:0..1); "
                       "speaker.* -> play(playlist?:calm|rain|jazz|pop|focus)|stop|set_playlist(playlist:...)|set_volume(volume:0..1); "
                       "fan.* -> on|off|toggle|set_speed(speed:1..3); "
                       "lock.* -> lock|unlock|toggle.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string"},
                "action":    {"type": "string"},
                "kwargs":    {
                    "type": "object",
                    "description": "Action arguments such as {'brightness': 0.5} or {'level': 4}.",
                    "additionalProperties": True,
                },
            },
            "required": ["device_id", "action"],
        },
    },
]


def dispatch_tool(skills: Skills, name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """Call the right Skills method, normalising the kwargs payload."""
    try:
        if name == "navigate_to_room":
            return skills.navigate_to_room(tool_input["room"])
        if name == "navigate_to_device":
            return skills.navigate_to_device(tool_input["device_id"])
        if name == "find_owner":
            return skills.find_owner()
        if name == "look_around":
            return skills.look_around()
        if name == "read_emotion":
            return skills.read_emotion()
        if name == "speak":
            return skills.speak(tool_input.get("text", ""))
        if name == "list_devices":
            return skills.list_devices()
        if name == "scan_room":
            return skills.scan_room(tool_input["room"])
        if name == "clean_room":
            return skills.clean_room(tool_input["room"])
        if name == "get_robot_state":
            return skills.get_robot_state()
        if name == "plan_device_route":
            return skills.plan_device_route(tool_input.get("device_ids") or [])
        if name == "visit_devices":
            return skills.visit_devices(tool_input.get("device_ids") or [])
        if name == "explore_frontier":
            return skills.explore_frontier(int(tool_input.get("max_hops") or 3))
        if name == "make_plan":
            # Lazy import: avoids cognition <-> planning cycle at module load.
            from ..planning.react import ReActPlanner
            plan = ReActPlanner().plan(tool_input.get("user_message", ""), skills=skills)
            return {"ok": True, "plan": plan.to_json()}
        if name == "pickup_item":
            return skills.pickup_item(tool_input["device_id"])
        if name == "deliver_item":
            return skills.deliver_item()
        if name == "set_device":
            kwargs = tool_input.get("kwargs") or {}
            return skills.set_device(tool_input["device_id"], tool_input["action"], **kwargs)
        return {"ok": False, "error": f"unknown tool {name!r}"}
    except KeyError as e:
        return {"ok": False, "error": f"missing argument: {e.args[0]}"}
    except Exception as e:  # pragma: no cover — defensive
        return {"ok": False, "error": f"tool crashed: {type(e).__name__}: {e}"}
