"""JSON-backed session store — one file per demo session.

Layout::

    data/sessions/
        20260609_153045_tired_coffee.json
        index.json          # lightweight listing cache (optional, rebuilt on list)

Each session file holds metadata plus an append-only list of :class:`TurnRecord`
entries. World snapshots reuse the schema from :mod:`homemate.world_snapshot`.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

SESSION_VERSION = 1


def default_sessions_dir() -> Path:
    env = os.environ.get("HOMEMATE_SESSIONS_DIR", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    pkg_root = Path(__file__).resolve().parents[2]
    return pkg_root / "data" / "sessions"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s[:48] or "session"


@dataclass
class TurnRecord:
    """One agent turn with full before/after world state."""
    timestamp: str
    user_message: str
    world_before: dict[str, Any]
    world_after: dict[str, Any]
    tool_trace: list[dict[str, Any]] = field(default_factory=list)
    spoken: list[str] = field(default_factory=list)
    final_text: str = ""
    emotion_label: str | None = None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "TurnRecord":
        return cls(
            timestamp=d.get("timestamp", ""),
            user_message=d.get("user_message", ""),
            world_before=dict(d.get("world_before", {})),
            world_after=dict(d.get("world_after", {})),
            tool_trace=list(d.get("tool_trace", [])),
            spoken=list(d.get("spoken", [])),
            final_text=d.get("final_text", ""),
            emotion_label=d.get("emotion_label"),
        )


@dataclass
class SessionRecord:
    """A full demo session (metadata + ordered turns)."""
    session_id: str
    created_at: str
    title: str
    script: str | None = None
    opts: dict[str, Any] = field(default_factory=dict)
    turns: list[TurnRecord] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "version": SESSION_VERSION,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "title": self.title,
            "script": self.script,
            "opts": self.opts,
            "turns": [t.to_json() for t in self.turns],
        }

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "SessionRecord":
        if d.get("version") != SESSION_VERSION:
            raise ValueError(f"unsupported session version: {d.get('version')!r}")
        return cls(
            session_id=d.get("session_id", ""),
            created_at=d.get("created_at", ""),
            title=d.get("title", ""),
            script=d.get("script"),
            opts=dict(d.get("opts", {})),
            turns=[TurnRecord.from_json(t) for t in d.get("turns", [])],
        )


class SessionStore:
    """Create, append, list, and load session files."""

    def __init__(self, root: Path | str | None = None,
                 *, now: Callable[[], str] = _utcnow_iso) -> None:
        self.root = Path(root) if root is not None else default_sessions_dir()
        self.now = now
        self.root.mkdir(parents=True, exist_ok=True)
        self._active: SessionRecord | None = None

    # --- lifecycle ---

    def start_session(self, *, title: str, script: str | None = None,
                      opts: dict[str, Any] | None = None) -> SessionRecord:
        ts = self.now()
        stamp = ts.replace("-", "").replace(":", "").replace("T", "_").split("Z")[0]
        suffix = f"_{script}" if script else ""
        session_id = f"{stamp}{suffix}"
        rec = SessionRecord(
            session_id=session_id,
            created_at=ts,
            title=title,
            script=script,
            opts=dict(opts or {}),
        )
        self._active = rec
        self._save(rec)
        return rec

    @property
    def active(self) -> SessionRecord | None:
        return self._active

    def append_turn(self, turn: TurnRecord) -> None:
        if self._active is None:
            raise RuntimeError("no active session — call start_session first")
        if not turn.timestamp:
            turn.timestamp = self.now()
        self._active.turns.append(turn)
        self._save(self._active)

    # --- load / list ---

    def path_for(self, session_id: str) -> Path:
        return self.root / f"{session_id}.json"

    def load(self, session_id_or_path: str) -> SessionRecord:
        p = Path(session_id_or_path)
        if not p.suffix:
            p = self.path_for(session_id_or_path)
        if not p.exists():
            raise FileNotFoundError(f"session not found: {p}")
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"invalid session JSON in {p}: {e}") from e
        return SessionRecord.from_json(data)

    def list_sessions(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for p in sorted(self.root.glob("*.json"), reverse=True):
            if p.name == "index.json":
                continue
            try:
                rec = SessionRecord.from_json(json.loads(p.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, ValueError, OSError):
                continue
            out.append({
                "session_id": rec.session_id,
                "title": rec.title,
                "created_at": rec.created_at,
                "turns": len(rec.turns),
                "script": rec.script,
                "path": str(p),
            })
        return out

    def export_session(self, session_id: str, dest: Path | str) -> Path:
        rec = self.load(session_id)
        p = Path(dest)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rec.to_json(), indent=2, ensure_ascii=False), encoding="utf-8")
        return p

    # --- internal ---

    def _save(self, rec: SessionRecord) -> None:
        path = self.path_for(rec.session_id)
        path.write_text(
            json.dumps(rec.to_json(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
