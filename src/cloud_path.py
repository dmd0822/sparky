#!/usr/bin/env python3
"""Cloud-path scaffolding for Milestone 2.

This module provides a lightweight broker orchestration layer that is
intentionally testable without Azure credentials. It models the critical
Milestone 2 concerns: explicit timeouts, per-stage cost and latency
measurement, content-safety checkpoints, and late-response discard.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class BrokerConfig:
    """Configuration for the local broker orchestration layer."""

    stt_timeout_ms: int = 5_000
    model_timeout_ms: int = 10_000
    tts_timeout_ms: int = 5_000
    safety_timeout_ms: int = 2_000
    circuit_breaker_failure_threshold: int = 3
    circuit_breaker_reset_seconds: int = 60
    stt_cost_usd: float = 0.0015
    safety_cost_usd: float = 0.0008
    model_cost_usd: float = 0.0065
    tts_cost_usd: float = 0.0010


@dataclass
class StageOutcome:
    """Represents a completed or failed stage in a broker turn."""

    stage: str
    ok: bool
    result: Any = None
    error: str | None = None
    blocked: bool = False
    latency_ms: int = 0
    cost_usd: float = 0.0
    timed_out: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "ok": self.ok,
            "blocked": self.blocked,
            "timed_out": self.timed_out,
            "latency_ms": self.latency_ms,
            "cost_usd": self.cost_usd,
            "result": self.result,
            "error": self.error,
        }


@dataclass(frozen=True)
class CloudTurnRequest:
    """A single broker turn request."""

    audio_ref: str
    transcript: str
    persona: str
    voice: str
    generation_id: str | None = None


@dataclass
class TurnSession:
    """Mutable execution state for an in-flight broker turn."""

    request: CloudTurnRequest
    invalidated: bool = False

    @property
    def generation_id(self) -> str:
        return self.request.generation_id or "default"


class CloudTransport(Protocol):
    """A transport that can execute the broker stages."""

    def transcribe(self, audio_ref: str, *, timeout_ms: int) -> StageOutcome:
        """Return a transcript for a user utterance."""

    def check_content_safety(self, text: str, *, timeout_ms: int) -> StageOutcome:
        """Return a safety evaluation for the text."""

    def generate_reply(self, prompt: str, persona: str, *, timeout_ms: int) -> StageOutcome:
        """Return an LLM reply for the persona-conditioned prompt."""

    def synthesize(self, text: str, voice: str, *, timeout_ms: int) -> StageOutcome:
        """Return an audio synthesis outcome for the reply."""


class StubCloudTransport:
    """Deterministic in-memory transport used by local tests."""

    def __init__(self, *, fail_stt: bool = False, fail_model: bool = False, block_safety: bool = False) -> None:
        self.fail_stt = fail_stt
        self.fail_model = fail_model
        self.block_safety = block_safety
        self.calls: list[tuple[str, Any]] = []

    def transcribe(self, audio_ref: str, *, timeout_ms: int) -> StageOutcome:
        self.calls.append(("stt", audio_ref))
        if self.fail_stt:
            return StageOutcome(
                stage="stt",
                ok=False,
                error="stt timeout",
                timed_out=True,
                latency_ms=timeout_ms,
                cost_usd=0.0,
            )
        return StageOutcome(
            stage="stt",
            ok=True,
            result={"transcript": "hello from stub"},
            latency_ms=120,
            cost_usd=0.0015,
        )

    def check_content_safety(self, text: str, *, timeout_ms: int) -> StageOutcome:
        self.calls.append(("safety", text))
        if self.block_safety:
            return StageOutcome(
                stage="safety",
                ok=True,
                blocked=True,
                result="refusal",
                latency_ms=10,
                cost_usd=0.0008,
            )
        return StageOutcome(
            stage="safety",
            ok=True,
            result="safe",
            latency_ms=10,
            cost_usd=0.0008,
        )

    def generate_reply(self, prompt: str, persona: str, *, timeout_ms: int) -> StageOutcome:
        self.calls.append(("model", f"{persona}:{prompt}"))
        if self.fail_model:
            return StageOutcome(
                stage="model",
                ok=False,
                error="model timeout",
                timed_out=True,
                latency_ms=timeout_ms,
                cost_usd=0.0,
            )
        return StageOutcome(
            stage="model",
            ok=True,
            result=f"[{persona}] {prompt}",
            latency_ms=220,
            cost_usd=0.0065,
        )

    def synthesize(self, text: str, voice: str, *, timeout_ms: int) -> StageOutcome:
        self.calls.append(("tts", f"{voice}:{text}"))
        return StageOutcome(
            stage="tts",
            ok=True,
            result=f"audio:{text}",
            latency_ms=180,
            cost_usd=0.0010,
        )


@dataclass
class TurnMeasurementReport:
    """Aggregated metrics for a single executed broker turn."""

    generation_id: str
    status: str
    stages: list[StageOutcome] = field(default_factory=list)
    total_latency_ms: int = 0
    total_cost_usd: float = 0.0
    discarded: bool = False
    circuit_open: bool = False
    reply_text: str | None = None
    transcript: str | None = None
    voice: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "generation_id": self.generation_id,
            "status": self.status,
            "discarded": self.discarded,
            "circuit_open": self.circuit_open,
            "total_latency_ms": self.total_latency_ms,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "reply_text": self.reply_text,
            "transcript": self.transcript,
            "voice": self.voice,
            "notes": self.notes,
            "stages": [stage.to_dict() for stage in self.stages],
        }


class CircuitBreaker:
    """Simple stateful breaker for cloud-stage failures."""

    def __init__(self, threshold: int, reset_seconds: int) -> None:
        self.threshold = threshold
        self.reset_seconds = reset_seconds
        self._consecutive_failures = 0
        self._opened_at: float | None = None

    def allow_request(self) -> bool:
        if self._opened_at is not None:
            if (self._opened_at + self.reset_seconds) <= self._current_time():
                self._opened_at = None
                self._consecutive_failures = 0
                return True
            return False
        return True

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.threshold:
            self._opened_at = self._current_time()

    def is_open(self) -> bool:
        return self._opened_at is not None and (self._opened_at + self.reset_seconds) > self._current_time()

    @staticmethod
    def _current_time() -> float:
        import time

        return time.time()


class CloudBroker:
    """Orchestrates a persona-conditioned turn through cloud stages."""

    def __init__(self, config: BrokerConfig | None = None, transport: CloudTransport | None = None) -> None:
        self.config = config or BrokerConfig()
        self.transport = transport or StubCloudTransport()
        self._breaker = CircuitBreaker(
            threshold=self.config.circuit_breaker_failure_threshold,
            reset_seconds=self.config.circuit_breaker_reset_seconds,
        )
        self._sessions: dict[str, TurnSession] = {}

    def start_turn(self, request: CloudTurnRequest) -> TurnSession:
        if request.generation_id is None:
            request = CloudTurnRequest(
                audio_ref=request.audio_ref,
                transcript=request.transcript,
                persona=request.persona,
                voice=request.voice,
                generation_id=str(uuid.uuid4()),
            )
        session = TurnSession(request=request)
        self._sessions[session.generation_id] = session
        return session

    def invalidate_generation(self, generation_id: str) -> bool:
        session = self._sessions.get(generation_id)
        if session is None:
            return False
        session.invalidated = True
        return True

    def run_turn(self, session: TurnSession) -> TurnMeasurementReport:
        report = TurnMeasurementReport(
            generation_id=session.generation_id,
            status="running",
            transcript=session.request.transcript,
            voice=session.request.voice,
        )

        if not self._breaker.allow_request():
            report.status = "circuit_open"
            report.circuit_open = True
            report.notes = "circuit breaker open"
            return report

        if session.invalidated:
            report.status = "discarded"
            report.discarded = True
            report.notes = "generation invalidated before execution"
            return report

        stt_outcome = self._execute_stage(
            session,
            "stt",
            lambda: self.transport.transcribe(audio_ref=session.request.audio_ref, timeout_ms=self.config.stt_timeout_ms),
            timeout_ms=self.config.stt_timeout_ms,
        )
        report.stages.append(stt_outcome)
        report.total_latency_ms += stt_outcome.latency_ms
        report.total_cost_usd += stt_outcome.cost_usd
        if not stt_outcome.ok or session.invalidated:
            self._breaker.record_failure()
            report.status = "failed" if not stt_outcome.ok else "discarded"
            report.discarded = session.invalidated
            report.notes = stt_outcome.error or "transcription failed"
            return report

        safety_outcome = self._execute_stage(
            session,
            "safety",
            lambda: self.transport.check_content_safety(report.transcript or session.request.transcript, timeout_ms=self.config.safety_timeout_ms),
            timeout_ms=self.config.safety_timeout_ms,
        )
        report.stages.append(safety_outcome)
        report.total_latency_ms += safety_outcome.latency_ms
        report.total_cost_usd += safety_outcome.cost_usd
        if safety_outcome.blocked or session.invalidated:
            self._breaker.record_success()
            report.status = "blocked" if safety_outcome.blocked else "discarded"
            report.discarded = session.invalidated
            report.notes = "content safety blocked the turn" if safety_outcome.blocked else "generation invalidated"
            return report

        model_outcome = self._execute_stage(
            session,
            "model",
            lambda: self.transport.generate_reply(
                prompt=session.request.transcript,
                persona=session.request.persona,
                timeout_ms=self.config.model_timeout_ms,
            ),
            timeout_ms=self.config.model_timeout_ms,
        )
        report.stages.append(model_outcome)
        report.total_latency_ms += model_outcome.latency_ms
        report.total_cost_usd += model_outcome.cost_usd
        if not model_outcome.ok or session.invalidated:
            self._breaker.record_failure()
            report.status = "failed" if not model_outcome.ok else "discarded"
            report.discarded = session.invalidated
            report.notes = model_outcome.error or "model generation failed"
            return report

        tts_outcome = self._execute_stage(
            session,
            "tts",
            lambda: self.transport.synthesize(text=str(model_outcome.result), voice=session.request.voice, timeout_ms=self.config.tts_timeout_ms),
            timeout_ms=self.config.tts_timeout_ms,
        )
        report.stages.append(tts_outcome)
        report.total_latency_ms += tts_outcome.latency_ms
        report.total_cost_usd += tts_outcome.cost_usd
        if not tts_outcome.ok or session.invalidated:
            self._breaker.record_failure()
            report.status = "failed" if not tts_outcome.ok else "discarded"
            report.discarded = session.invalidated
            report.notes = tts_outcome.error or "speech synthesis failed"
            return report

        self._breaker.record_success()
        report.status = "completed"
        report.reply_text = str(model_outcome.result)
        report.transcript = str(stt_outcome.result.get("transcript") if isinstance(stt_outcome.result, dict) else stt_outcome.result)
        report.notes = "turn completed"
        return report

    def _execute_stage(self, session: TurnSession, stage: str, stage_runner: Any, *, timeout_ms: int) -> StageOutcome:
        if session.invalidated:
            return StageOutcome(stage=stage, ok=False, blocked=True, result=None, error="generation invalidated", latency_ms=0, cost_usd=0.0)
        try:
            outcome = stage_runner()
            if isinstance(outcome, StageOutcome):
                return outcome
            return StageOutcome(stage=stage, ok=True, result=outcome, latency_ms=0, cost_usd=0.0)
        except TimeoutError:
            return StageOutcome(stage=stage, ok=False, error="timeout", timed_out=True, latency_ms=timeout_ms, cost_usd=0.0)
        except Exception as exc:  # pragma: no cover - exercised in unit tests via stub failures
            return StageOutcome(stage=stage, ok=False, error=str(exc), latency_ms=timeout_ms, cost_usd=0.0)
