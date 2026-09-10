#!/usr/bin/env python3
"""End-to-end simulated conversation flow for Milestone 4."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .cloud_path import BrokerConfig, CloudBroker, CloudTurnRequest, StubCloudTransport, TurnMeasurementReport, TurnSession
from .motion_arbiter import MotionArbiter
from .persona import PersonaBundle, PersonaRegistry, minimal_safe_persona


@dataclass
class ConversationTurn:
    """Mutable state for a single simulated conversation turn."""

    generation_id: str
    request: CloudTurnRequest
    session: TurnSession
    persona: PersonaBundle
    report: TurnMeasurementReport | None = None
    motion_gesture: str | None = None
    cancelled: bool = False
    cancelled_motion: list[str] = field(default_factory=list)


class ConversationSimulator:
    """Composable broker + persona + motion runtime for simulator-first testing."""

    def __init__(
        self,
        *,
        broker: CloudBroker | None = None,
        arbiter: MotionArbiter | None = None,
        registry: PersonaRegistry | None = None,
        config: BrokerConfig | None = None,
        transport: Any | None = None,
    ) -> None:
        self.config = config or BrokerConfig()
        self.broker = broker or CloudBroker(config=self.config, transport=transport or StubCloudTransport())
        self.arbiter = arbiter or MotionArbiter(adapter=type("AdapterStub", (), {"arm": lambda self: None, "set_posture": lambda self, posture: None, "set_head": lambda self, head: None, "play_gesture": lambda self, gesture: None})())
        self.registry = registry or PersonaRegistry(default_persona=minimal_safe_persona())
        self._turns: dict[str, ConversationTurn] = {}

    def resolve_persona(self, persona: str | PersonaBundle | None) -> PersonaBundle:
        if persona is None:
            return self.registry.active_persona
        if isinstance(persona, PersonaBundle):
            return self.registry.register(persona)
        if persona in self.registry._bundles:
            return self.registry._bundles[persona]
        if not persona.strip():
            return self.registry.active_persona
        if self.registry.active_persona.persona_id == persona:
            return self.registry.active_persona
        bundle = PersonaBundle(
            persona_id=persona,
            version="1.0",
            prompt=f"You are the {persona} persona.",
            voice="neutral",
            behavior={"verbosity": "brief"},
            motion_vocabulary=("wag", "nod") if persona != "minimal_safe" else (),
            permissions={"motion": True},
            disclosure="I am an AI companion.",
        )
        self.registry.register(bundle)
        return bundle

    def start_turn(
        self,
        request: CloudTurnRequest | None = None,
        *,
        audio_ref: str = "clip.wav",
        transcript: str = "hello",
        persona: str | PersonaBundle | None = None,
        voice: str = "echo",
        generation_id: str | None = None,
    ) -> ConversationTurn:
        if request is None:
            request = CloudTurnRequest(
                audio_ref=audio_ref,
                transcript=transcript,
                persona=self.resolve_persona(persona).persona_id,
                voice=voice,
                generation_id=generation_id,
            )
        session = self.broker.start_turn(request)
        persona_bundle = self.resolve_persona(session.request.persona)
        turn = ConversationTurn(
            generation_id=session.generation_id,
            request=session.request,
            session=session,
            persona=persona_bundle,
            motion_gesture=self._choose_motion_gesture(persona_bundle),
        )
        self._turns[turn.generation_id] = turn
        return turn

    def _choose_motion_gesture(self, persona: PersonaBundle) -> str | None:
        if not persona.permissions.get("motion", False):
            return None
        motion_vocabulary = tuple(persona.motion_vocabulary or ("wag",))
        for candidate in motion_vocabulary:
            if candidate in self.arbiter.allowlist:
                return candidate
        return None

    def run_turn(self, turn: ConversationTurn | TurnSession | str) -> TurnMeasurementReport:
        if isinstance(turn, str):
            turn = self._turns.get(turn)
            if turn is None:
                raise KeyError(f"unknown generation: {turn}")
        elif isinstance(turn, TurnSession):
            turn = self._turns.get(turn.generation_id)
            if turn is None:
                raise KeyError(f"unknown generation: {turn.generation_id}")

        if turn is None:  # pragma: no cover - sanity guard
            raise KeyError("turn not found")

        report = self.broker.run_turn(turn.session)
        turn.report = report
        if turn.cancelled or turn.session.invalidated:
            report.discarded = True
            report.status = "discarded"
            report.notes = "generation invalidated by barge-in"
            return report

        if report.status == "completed" and turn.motion_gesture is not None:
            accepted = self.arbiter.submit(turn.motion_gesture, generation_id=turn.generation_id, ttl_seconds=1.0)
            if accepted.get("accepted"):
                self.arbiter.service()
                report.notes = f"turn completed with motion {turn.motion_gesture}"
            else:
                report.notes = f"motion rejected: {accepted.get('reason')}"

        return report

    def barge_in(self, generation_id: str) -> bool:
        turn = self._turns.get(generation_id)
        if turn is None:
            return False
        turn.cancelled = True
        self.broker.invalidate_generation(generation_id)
        turn.cancelled_motion = self.arbiter.cancel_generation(generation_id)
        if turn.report is not None:
            turn.report.status = "discarded"
            turn.report.discarded = True
            turn.report.notes = "generation invalidated by barge-in"
        else:
            turn.report = TurnMeasurementReport(
                generation_id=generation_id,
                status="discarded",
                discarded=True,
                notes="generation invalidated by barge-in",
            )
        return True

    def cancel_generation(self, generation_id: str) -> bool:
        return self.barge_in(generation_id)

    def invalidate_generation(self, generation_id: str) -> bool:
        return self.barge_in(generation_id)

    def simulate_turn(
        self,
        *,
        audio_ref: str = "clip.wav",
        transcript: str = "hello",
        persona: str | PersonaBundle | None = None,
        voice: str = "echo",
        generation_id: str | None = None,
    ) -> TurnMeasurementReport:
        turn = self.start_turn(
            audio_ref=audio_ref,
            transcript=transcript,
            persona=persona,
            voice=voice,
            generation_id=generation_id,
        )
        return self.run_turn(turn)


__all__ = [
    "ConversationSimulator",
    "ConversationTurn",
]
