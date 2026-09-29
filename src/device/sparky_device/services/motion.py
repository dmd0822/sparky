"""Service-level motion intents for Sparky.

The motion service is the application layer above
``sparky_device.hardware.ports.MotionPort``. It names behaviour-planner intents
such as ``sit`` and ``turn_left`` instead of exposing servo angles or raw vendor
strings, then validates every intent through the shared hardware-contract action
domain before anything reaches the adapter.

Conflict strategy: non-stop commands are **rejected while a prior command is in
flight**. The PiDog adapter queues motion asynchronously, so accepting another
intent before the first settles would make planner state ambiguous. Call
``wait_until_idle()`` after a command has visibly settled, or call ``stop()`` to
pre-empt immediately. ``stop()`` is never queued, is idempotent while idle, and
clears the in-flight marker even if called repeatedly. ``close()`` safe-stops
first, closes the injected port, and makes every later non-stop command fail
with :class:`HardwareError`; a post-close ``stop()`` is a safe no-op because the
service has already attempted to safe-stop.

Posture is tracked as the last accepted service posture. Locomotion requires a
standing posture, so requests such as ``sit`` followed by ``trot`` are rejected
until the planner explicitly asks for ``stand``. All public operations are
guarded by a re-entrant lock; a single ``MotionService`` instance serialises its
state transitions and adapter calls across threads.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import RLock

from ..hardware.ports import (
    HardwareError,
    MotionPort,
    validate_action_name,
    validate_speed,
)

__all__ = [
    "Gait",
    "MotionService",
    "MotionState",
    "Posture",
    "Turn",
]


class Posture(Enum):
    """Stable body poses a planner may request."""

    STANDING = "stand"
    SITTING = "sit"
    LYING = "lie"


class Gait(Enum):
    """Linear or rhythmic locomotion intents."""

    TROT = "trot"
    FORWARD = "forward"
    BACKWARD = "backward"


class Turn(Enum):
    """Turning locomotion intents."""

    LEFT = "turn_left"
    RIGHT = "turn_right"


@dataclass(frozen=True)
class MotionState:
    """Observable service state for planners and tests."""

    posture: Posture
    in_flight: bool
    active_action: str | None = None
    closed: bool = False


@dataclass(frozen=True)
class _MotionIntent:
    action: str
    steps: int
    speed: int
    posture: Posture | None = None
    requires_standing: bool = False


class MotionService:
    """Translate safe motion intents onto an injected :class:`MotionPort`."""

    def __init__(
        self,
        motion: MotionPort,
        *,
        initial_posture: Posture = Posture.STANDING,
    ) -> None:
        self._motion = motion
        self._lock = RLock()
        self._posture = initial_posture
        self._in_flight = False
        self._active_action: str | None = None
        self._closed = False

    @property
    def state(self) -> MotionState:
        """Return a consistent snapshot of the service state."""

        with self._lock:
            return MotionState(
                posture=self._posture,
                in_flight=self._in_flight,
                active_action=self._active_action,
                closed=self._closed,
            )

    def stand(self, *, speed: int = 50) -> MotionState:
        """Stand in a neutral posture."""

        return self._issue(
            _MotionIntent(
                action=Posture.STANDING.value,
                steps=1,
                speed=speed,
                posture=Posture.STANDING,
            )
        )

    def sit(self, *, speed: int = 50) -> MotionState:
        """Sit in a stable rest posture."""

        return self._issue(
            _MotionIntent(
                action=Posture.SITTING.value,
                steps=1,
                speed=speed,
                posture=Posture.SITTING,
            )
        )

    def lie(self, *, speed: int = 50) -> MotionState:
        """Lie down in a low rest posture."""

        return self._issue(
            _MotionIntent(
                action=Posture.LYING.value,
                steps=1,
                speed=speed,
                posture=Posture.LYING,
            )
        )

    def trot(self, *, steps: int = 1, speed: int = 50) -> MotionState:
        """Perform the vendor trot action from a standing posture."""

        return self._move(Gait.TROT, steps=steps, speed=speed)

    def forward(self, *, steps: int = 1, speed: int = 50) -> MotionState:
        """Walk forward from a standing posture."""

        return self._move(Gait.FORWARD, steps=steps, speed=speed)

    def backward(self, *, steps: int = 1, speed: int = 50) -> MotionState:
        """Walk backward from a standing posture."""

        return self._move(Gait.BACKWARD, steps=steps, speed=speed)

    def turn_left(self, *, steps: int = 1, speed: int = 50) -> MotionState:
        """Turn left from a standing posture."""

        return self._turn(Turn.LEFT, steps=steps, speed=speed)

    def turn_right(self, *, steps: int = 1, speed: int = 50) -> MotionState:
        """Turn right from a standing posture."""

        return self._turn(Turn.RIGHT, steps=steps, speed=speed)

    def wait_until_idle(self, timeout: float | None = None) -> MotionState:
        """Wait for the injected port to drain and mark the service idle."""

        with self._lock:
            self._ensure_open()
            if not self._in_flight:
                return self.state
            self._motion.wait_all_done(timeout=timeout)
            self._in_flight = False
            self._active_action = None
            return self.state

    def stop(self) -> MotionState:
        """Immediately stop motion; safe to call repeatedly or when idle."""

        with self._lock:
            if not self._closed:
                self._motion.stop()
            self._in_flight = False
            self._active_action = None
            return self.state

    def close(self) -> None:
        """Safe-stop and release the injected motion port. Idempotent."""

        with self._lock:
            if self._closed:
                return
            self.stop()
            self._motion.close()
            self._closed = True

    def _move(self, gait: Gait, *, steps: int, speed: int) -> MotionState:
        return self._issue(
            _MotionIntent(
                action=gait.value,
                steps=steps,
                speed=speed,
                requires_standing=True,
            )
        )

    def _turn(self, turn: Turn, *, steps: int, speed: int) -> MotionState:
        return self._issue(
            _MotionIntent(
                action=turn.value,
                steps=steps,
                speed=speed,
                requires_standing=True,
            )
        )

    def _issue(self, intent: _MotionIntent) -> MotionState:
        with self._lock:
            self._ensure_open()
            action = validate_action_name(intent.action)
            speed = validate_speed(intent.speed)
            if intent.steps < 1:
                raise HardwareError(f"steps must be at least 1, got {intent.steps}")
            if self._in_flight:
                raise HardwareError(
                    f"motion command {self._active_action!r} is still in flight; "
                    "call wait_until_idle() or stop() before issuing another command"
                )
            if intent.requires_standing and self._posture is not Posture.STANDING:
                raise HardwareError(
                    f"{action} requires posture {Posture.STANDING.name}; "
                    f"current posture is {self._posture.name}"
                )

            self._motion.do_action(action, steps=intent.steps, speed=speed)
            if intent.posture is not None:
                self._posture = intent.posture
            self._in_flight = True
            self._active_action = action
            return self.state

    def _ensure_open(self) -> None:
        if self._closed:
            raise HardwareError("motion service is closed")
