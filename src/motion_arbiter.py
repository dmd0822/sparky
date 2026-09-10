#!/usr/bin/env python3
"""Deterministic motion safety and command arbitration for Sparky."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Iterable, Mapping

DEFAULT_SAFE_POSE = "idle"
DEFAULT_MOTION_ALLOWLIST: frozenset[str] = frozenset(
    {
        "idle",
        "rest",
        "alert",
        "happy",
        "sad",
        "bark",
        "nod",
        "think",
        "stretch",
        "look_left",
        "look_right",
        "wag",
        "wave",
        "shake",
        "sit",
        "stand",
        "walk",
        "run",
        "spin",
        "sniff",
        "cheer",
        "sleep",
        "yawn",
        "peek",
        "search",
        "scan",
        "startled",
        "greet",
        "dance",
        "jump",
        "tail_up",
        "tail_down",
        "head_up",
        "head_down",
    }
)


@dataclass(frozen=True)
class MotionCommand:
    generation_id: str
    gesture: str
    issued_at: float
    expires_at: float
    ttl_seconds: float
    priority: int = 0


class MotionArbiter:
    """Single-writer arbitration for actuator commands.

    The arbiter is the only component allowed to drive motion. It validates
    gestures against a static allowlist and drops any command whose TTL expires
    before execution.
    """

    def __init__(
        self,
        adapter: Any,
        *,
        allowlist: Iterable[str] | None = None,
        safe_pose: str = DEFAULT_SAFE_POSE,
        ttl_seconds: float = 1.0,
        watchdog_seconds: float = 3.0,
    ) -> None:
        self.adapter = adapter
        self.allowlist = frozenset(allowlist or DEFAULT_MOTION_ALLOWLIST)
        self.safe_pose = safe_pose
        self.default_ttl_seconds = float(ttl_seconds)
        self.watchdog_seconds = float(watchdog_seconds)
        self._armed = False
        self._latched = False
        self._last_service_time = monotonic()
        self._pending: list[MotionCommand] = []
        self._rejected: list[dict[str, Any]] = []
        self._executed: list[str] = []
        self._generation_commands: dict[str, list[MotionCommand]] = defaultdict(list)

    @property
    def armed(self) -> bool:
        return self._armed

    @property
    def latched(self) -> bool:
        return self._latched

    @property
    def pending_commands(self) -> list[MotionCommand]:
        return list(self._pending)

    @property
    def executed(self) -> list[str]:
        return list(self._executed)

    @property
    def rejected(self) -> list[dict[str, Any]]:
        return [dict(entry) for entry in self._rejected]

    @property
    def generation_commands(self) -> dict[str, list[MotionCommand]]:
        return {generation_id: list(commands) for generation_id, commands in self._generation_commands.items()}

    def arm(self) -> None:
        """Arm the arbiter after startup checks."""
        self._armed = True
        self._latched = False
        self._last_service_time = monotonic()
        self.adapter.arm()

    def disarm(self) -> None:
        self._armed = False
        self._latched = True

    def cancel_generation(self, generation_id: str) -> list[str]:
        """Drop all pending commands from the supplied generation and unwind to safe pose."""
        remaining: list[MotionCommand] = []
        cancelled: list[str] = []
        for command in self._pending:
            if command.generation_id == generation_id:
                cancelled.append(command.gesture)
                continue
            remaining.append(command)
        self._pending = remaining
        self._generation_commands.pop(generation_id, None)
        self._rejected.append(
            {
                "generation_id": generation_id,
                "reason": "cancelled",
                "gestures": cancelled,
                "timestamp": monotonic(),
            }
        )
        self.trigger_safe_pose()
        return cancelled

    def submit(
        self,
        gesture: str,
        *,
        generation_id: str = "default",
        ttl_seconds: float | None = None,
        priority: int = 0,
        now: float | None = None,
    ) -> dict[str, Any]:
        """Submit a motion command for later execution by the arbiter itself."""
        if not self._armed or self._latched:
            reason = "inhibited" if not self._armed else "latched"
            self._rejected.append({"gesture": gesture, "generation_id": generation_id, "reason": reason})
            return {"accepted": False, "reason": reason}

        if not isinstance(gesture, str) or not gesture.strip():
            self._rejected.append({"gesture": gesture, "generation_id": generation_id, "reason": "invalid"})
            return {"accepted": False, "reason": "invalid"}

        normalized = gesture.strip()
        if normalized not in self.allowlist:
            self._rejected.append({"gesture": normalized, "generation_id": generation_id, "reason": "not_allowed"})
            return {"accepted": False, "reason": "not_allowed"}

        issued_at = now if now is not None else monotonic()
        ttl = float(ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds)
        if ttl <= 0:
            self._rejected.append({"gesture": normalized, "generation_id": generation_id, "reason": "ttl_expired"})
            return {"accepted": False, "reason": "ttl_expired"}

        command = MotionCommand(
            generation_id=generation_id,
            gesture=normalized,
            issued_at=issued_at,
            expires_at=issued_at + ttl,
            ttl_seconds=ttl,
            priority=priority,
        )
        self._pending.append(command)
        self._generation_commands[generation_id].append(command)
        self._last_service_time = issued_at
        return {
            "accepted": True,
            "gesture": normalized,
            "generation_id": generation_id,
            "expires_at": command.expires_at,
        }

    def service(self, *, now: float | None = None) -> list[str]:
        """Execute the next pending command if it is still valid and within TTL."""
        if not self._armed or self._latched:
            return []

        current_time = now if now is not None else monotonic()
        self._last_service_time = current_time

        remaining: list[MotionCommand] = []
        executed: list[str] = []
        for command in self._pending:
            if command.expires_at <= current_time:
                self._rejected.append(
                    {
                        "gesture": command.gesture,
                        "generation_id": command.generation_id,
                        "reason": "ttl_expired",
                        "expires_at": command.expires_at,
                    }
                )
                continue
            remaining.append(command)

        self._pending = remaining
        if not self._pending:
            return executed

        next_command = self._pending.pop(0)
        self.adapter.play_gesture(next_command.gesture)
        self._executed.append(next_command.gesture)
        executed.append(next_command.gesture)
        return executed

    def watchdog_expired(self, *, now: float | None = None) -> bool:
        current_time = now if now is not None else monotonic()
        return current_time - self._last_service_time > self.watchdog_seconds

    def trigger_safe_pose(self) -> None:
        """Latch the arbiter into a safe, known motion state."""
        self._latched = True
        self._pending.clear()
        self.adapter.set_posture(self.safe_pose)
        self.adapter.set_head("neutral")
        if hasattr(self.adapter, "set_tail"):
            self.adapter.set_tail(0.0)

    def ensure_serviced(self, *, now: float | None = None) -> bool:
        """Return True when the watchdog forces the safe pose and latches."""
        if self.watchdog_expired(now=now):
            self.trigger_safe_pose()
            return True
        return False


def validate_motion_gesture(gesture: str, allowlist: Iterable[str] | None = None) -> bool:
    allowed = frozenset(allowlist or DEFAULT_MOTION_ALLOWLIST)
    return isinstance(gesture, str) and gesture.strip() in allowed


__all__ = [
    "DEFAULT_MOTION_ALLOWLIST",
    "DEFAULT_SAFE_POSE",
    "MotionArbiter",
    "MotionCommand",
    "validate_motion_gesture",
]
