"""Device-side voice turn orchestration for microphone, chat, and speech."""

from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path
import sys
import time
from typing import Any, Mapping, Protocol
import wave


def _add_local_shared_contracts_to_path() -> None:
    """Expose repo-local shared contracts when only ``src/device`` is on path."""

    for parent in Path(__file__).resolve().parents:
        shared_package = parent / "src" / "shared" / "sparky_contracts" / "__init__.py"
        if shared_package.exists():
            shared_src = str(shared_package.parent.parent)
            if shared_src not in sys.path:
                sys.path.insert(0, shared_src)
            return


try:  # pragma: no cover - installed package path.
<<<<<<< HEAD
=======
    from sparky_contracts import ConversationTurnTimings
>>>>>>> main
    from sparky_contracts.personas import (
        DEFAULT_GLOBAL_SAFETY_SEGMENTS,
        PersonaManifest,
        PersonaRuntimeState,
        PersonaScopedMemoryStore,
        compose_prompt,
        persona_voice_settings,
        switch_persona,
    )
except ImportError:  # pragma: no cover - repo-root test path.
    try:
<<<<<<< HEAD
=======
        from src.shared.sparky_contracts import ConversationTurnTimings
>>>>>>> main
        from src.shared.sparky_contracts.personas import (
            DEFAULT_GLOBAL_SAFETY_SEGMENTS,
            PersonaManifest,
            PersonaRuntimeState,
            PersonaScopedMemoryStore,
            compose_prompt,
            persona_voice_settings,
            switch_persona,
        )
    except ImportError:  # pragma: no cover - script path outside repo root.
        _add_local_shared_contracts_to_path()
<<<<<<< HEAD
=======
        from sparky_contracts import ConversationTurnTimings
>>>>>>> main
        from sparky_contracts.personas import (
            DEFAULT_GLOBAL_SAFETY_SEGMENTS,
            PersonaManifest,
            PersonaRuntimeState,
            PersonaScopedMemoryStore,
            compose_prompt,
            persona_voice_settings,
            switch_persona,
        )

from ..hardware.ports import HardwareError, HardwareUnavailableError
from .audio import AudioBuffer, AudioService, AudioStatus


CONVERSATION_PHASE_IDLE = "idle"
CONVERSATION_PHASE_LISTENING = "listening"
CONVERSATION_PHASE_TRANSCRIBING = "transcribing"
CONVERSATION_PHASE_THINKING = "thinking"
CONVERSATION_PHASE_SPEAKING = "speaking"
CONVERSATION_PHASE_FAILED = "failed"

CONVERSATION_STATUS_OK = "ok"
CONVERSATION_STATUS_AUDIO_FAILED = "audio_failed"
CONVERSATION_STATUS_STT_FAILED = "stt_failed"
CONVERSATION_STATUS_CHAT_FAILED = "chat_failed"
CONVERSATION_STATUS_TTS_FAILED = "tts_failed"
CONVERSATION_STATUS_PERSONA_FAILED = "persona_failed"

DEFAULT_TURN_CHUNKS = 3


class SpeechRecognizer(Protocol):
    """Relay STT seam used by the conversation orchestrator."""

    def recognize(self, payload: Mapping[str, Any], headers: Mapping[str, str]) -> Mapping[str, Any]:
        """Return a structured STT response mapping."""


class ChatClient(Protocol):
    """Relay chat seam used by the conversation orchestrator."""

    def chat(self, payload: Mapping[str, Any], headers: Mapping[str, str]) -> Mapping[str, Any]:
        """Return a structured chat response mapping."""


class SpeechSynthesizer(Protocol):
    """Relay TTS seam used by the conversation orchestrator."""

    def speech(self, payload: Mapping[str, Any], headers: Mapping[str, str]) -> Mapping[str, Any]:
        """Return a structured speech-synthesis response mapping."""


@dataclass(frozen=True)
class ConversationFailure:
    """Failure details for a normalized voice turn."""

    code: str
    message: str
    leg: str
    status_code: int | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ConversationFailure":
        if not isinstance(payload, Mapping):
            raise ValueError("ConversationFailure payload must be a mapping.")
        return cls(
            code=_required_string(payload.get("code"), "code"),
            message=_required_string(payload.get("message"), "message"),
            leg=_required_string(payload.get("leg"), "leg"),
            status_code=_optional_int(payload.get("status_code")),
        )

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "leg": self.leg,
        }
        if self.status_code is not None:
            payload["status_code"] = self.status_code
        return payload


@dataclass(frozen=True)
class ConversationTurnResult:
    """Stable result shape for one complete voice turn."""

    status: str
    persona_id: str
    transcript: str = ""
    reply: str = ""
    confidence: float = 0.0
    prompt_metadata: Mapping[str, Any] | None = None
    stt_metadata: Mapping[str, Any] | None = None
    chat_metadata: Mapping[str, Any] | None = None
    tts_metadata: Mapping[str, Any] | None = None
    playback: Mapping[str, Any] | None = None
    failure: ConversationFailure | None = None
<<<<<<< HEAD
=======
    timings: ConversationTurnTimings | None = None
>>>>>>> main

    @classmethod
    def ok(
        cls,
        *,
        persona_id: str,
        transcript: str,
        reply: str,
        confidence: float,
        prompt_metadata: Mapping[str, Any],
        stt_metadata: Mapping[str, Any],
        chat_metadata: Mapping[str, Any],
        tts_metadata: Mapping[str, Any],
        playback: Mapping[str, Any],
<<<<<<< HEAD
=======
        timings: ConversationTurnTimings | None = None,
>>>>>>> main
    ) -> "ConversationTurnResult":
        return cls(
            status=CONVERSATION_STATUS_OK,
            persona_id=persona_id,
            transcript=transcript,
            reply=reply,
            confidence=confidence,
            prompt_metadata=dict(prompt_metadata),
            stt_metadata=dict(stt_metadata),
            chat_metadata=dict(chat_metadata),
            tts_metadata=dict(tts_metadata),
            playback=dict(playback),
<<<<<<< HEAD
        )

    @classmethod
    def failure(
=======
            timings=timings,
        )

    @classmethod
    def failed(
>>>>>>> main
        cls,
        *,
        status: str,
        persona_id: str,
        leg: str,
        code: str,
        message: str,
        status_code: int | None = None,
        transcript: str = "",
        reply: str = "",
        confidence: float = 0.0,
        prompt_metadata: Mapping[str, Any] | None = None,
        stt_metadata: Mapping[str, Any] | None = None,
        chat_metadata: Mapping[str, Any] | None = None,
        tts_metadata: Mapping[str, Any] | None = None,
<<<<<<< HEAD
=======
        timings: ConversationTurnTimings | None = None,
>>>>>>> main
    ) -> "ConversationTurnResult":
        return cls(
            status=status,
            persona_id=persona_id,
            transcript=transcript,
            reply=reply,
            confidence=confidence,
            prompt_metadata=dict(prompt_metadata or {}),
            stt_metadata=dict(stt_metadata or {}),
            chat_metadata=dict(chat_metadata or {}),
            tts_metadata=dict(tts_metadata or {}),
            failure=ConversationFailure(
                code=code,
                message=message,
                leg=leg,
                status_code=status_code,
            ),
<<<<<<< HEAD
=======
            timings=timings,
>>>>>>> main
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ConversationTurnResult":
        if not isinstance(payload, Mapping):
            raise ValueError("ConversationTurnResult payload must be a mapping.")
        failure = payload.get("failure")
<<<<<<< HEAD
=======
        timings = payload.get("timings")
>>>>>>> main
        return cls(
            status=_required_string(payload.get("status"), "status"),
            persona_id=_required_string(payload.get("persona_id"), "persona_id"),
            transcript=_optional_string(payload.get("transcript")) or "",
            reply=_optional_string(payload.get("reply")) or "",
            confidence=_optional_float(payload.get("confidence")) or 0.0,
            prompt_metadata=_optional_mapping(payload.get("prompt_metadata")),
            stt_metadata=_optional_mapping(payload.get("stt_metadata")),
            chat_metadata=_optional_mapping(payload.get("chat_metadata")),
            tts_metadata=_optional_mapping(payload.get("tts_metadata")),
            playback=_optional_mapping(payload.get("playback")),
            failure=ConversationFailure.from_dict(failure) if isinstance(failure, Mapping) else None,
<<<<<<< HEAD
=======
            timings=ConversationTurnTimings.from_dict(timings) if isinstance(timings, Mapping) else None,
>>>>>>> main
        )

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "persona_id": self.persona_id,
            "transcript": self.transcript,
            "reply": self.reply,
            "confidence": self.confidence,
            "prompt_metadata": dict(self.prompt_metadata or {}),
            "stt_metadata": dict(self.stt_metadata or {}),
            "chat_metadata": dict(self.chat_metadata or {}),
            "tts_metadata": dict(self.tts_metadata or {}),
            "playback": dict(self.playback or {}),
        }
        if self.failure is not None:
            payload["failure"] = self.failure.as_dict()
<<<<<<< HEAD
=======
        if self.timings is not None:
            payload["timings"] = self.timings.as_dict()
>>>>>>> main
        return payload


@dataclass(frozen=True)
class ConversationState:
    """Explicit, testable runtime state for conversation orchestration."""

    persona: PersonaRuntimeState
    phase: str = CONVERSATION_PHASE_IDLE
    last_turn: ConversationTurnResult | None = None
    degraded: bool = False

    @property
    def active_persona_id(self) -> str:
        return self.persona.active_persona_id

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ConversationState":
        if not isinstance(payload, Mapping):
            raise ValueError("ConversationState payload must be a mapping.")
        persona = payload.get("persona")
        last_turn = payload.get("last_turn")
        return cls(
            persona=PersonaRuntimeState.from_dict(persona)
            if isinstance(persona, Mapping)
            else PersonaRuntimeState(
                active_persona_id=_required_string(payload.get("active_persona_id"), "active_persona_id")
            ),
            phase=_required_string(payload.get("phase"), "phase"),
            last_turn=ConversationTurnResult.from_dict(last_turn) if isinstance(last_turn, Mapping) else None,
            degraded=bool(payload.get("degraded", False)),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "active_persona_id": self.active_persona_id,
            "persona": self.persona.as_dict(),
            "phase": self.phase,
            "degraded": self.degraded,
            "last_turn": None if self.last_turn is None else self.last_turn.as_dict(),
        }


class ConversationOrchestrator:
    """Run one voice turn across audio capture, STT, chat, TTS, and playback."""

    def __init__(
        self,
        *,
        audio: AudioService,
        recognizer: SpeechRecognizer,
        chat_client: ChatClient,
        synthesizer: SpeechSynthesizer,
        persona_registry: Mapping[str, PersonaManifest],
        active_persona_id: str,
        headers_factory: Callable[[], Mapping[str, str]] | None = None,
<<<<<<< HEAD
=======
        clock: Callable[[], float] | None = None,
>>>>>>> main
        memory: PersonaScopedMemoryStore | None = None,
        global_safety_rules: tuple[str, ...] = DEFAULT_GLOBAL_SAFETY_SEGMENTS,
    ) -> None:
        if active_persona_id not in persona_registry:
            raise ValueError(f"active persona {active_persona_id!r} is not registered")
        self._audio = audio
        self._recognizer = recognizer
        self._chat_client = chat_client
        self._synthesizer = synthesizer
        self._persona_registry = dict(persona_registry)
        self._headers_factory = headers_factory or (lambda: {})
<<<<<<< HEAD
=======
        self._clock = clock or time.perf_counter
>>>>>>> main
        self._memory = memory or PersonaScopedMemoryStore()
        self._global_safety_rules = tuple(global_safety_rules)
        self._state = ConversationState(
            persona=PersonaRuntimeState(active_persona_id=active_persona_id),
        )

    @property
    def state(self) -> ConversationState:
        """Return the latest immutable conversation state."""

        return self._state

    def switch_persona(self, target_persona_id: str) -> ConversationState:
        """Switch active persona through the shared safe-state transition."""

        if target_persona_id not in self._persona_registry:
<<<<<<< HEAD
            result = ConversationTurnResult.failure(
=======
            result = ConversationTurnResult.failed(
>>>>>>> main
                status=CONVERSATION_STATUS_PERSONA_FAILED,
                persona_id=self._state.active_persona_id,
                leg="persona",
                code="persona_not_registered",
                message=f"persona {target_persona_id!r} is not registered",
            )
            self._state = ConversationState(
                persona=self._state.persona,
                phase=CONVERSATION_PHASE_FAILED,
                last_turn=result,
                degraded=True,
            )
            return self._state
        switched = switch_persona(self._state.persona, target_persona_id)
        self._state = ConversationState(
            persona=switched.state,
            phase=CONVERSATION_PHASE_IDLE,
            last_turn=self._state.last_turn,
            degraded=False,
        )
        return self._state

    def run_voice_turn(self, *, chunks: int = DEFAULT_TURN_CHUNKS) -> ConversationTurnResult:
        """Capture audio, transcribe, prompt, synthesize, and play one turn."""

        if chunks < 1:
            raise ValueError(f"chunks must be at least 1, got {chunks}")
        persona_id = self._state.active_persona_id
<<<<<<< HEAD
        try:
            buffer = self._capture_audio(chunks=chunks)
            stt_response = self._transcribe(buffer)
=======
        turn_started = self._clock()
        timing_values: dict[str, float] = {}
        try:
            buffer = self._measure_leg(
                timing_values,
                "audio_capture_seconds",
                lambda: self._capture_audio(chunks=chunks),
            )
            stt_response = self._measure_leg(timing_values, "stt_seconds", lambda: self._transcribe(buffer))
>>>>>>> main
            transcript = _response_text(stt_response, "transcript")
            if _is_failure_response(stt_response) or not transcript:
                return self._fail_from_response(
                    status=CONVERSATION_STATUS_STT_FAILED,
                    leg="stt",
                    persona_id=persona_id,
                    response=stt_response,
                    default_code="empty_transcript",
                    default_message="Speech recognition returned no transcript.",
<<<<<<< HEAD
=======
                    timings=self._timings(timing_values, turn_started),
>>>>>>> main
                )

            composed = compose_prompt(
                persona=self._persona_registry[persona_id],
                user_turn=transcript,
                global_safety_rules=self._global_safety_rules,
                memory=self._memory,
            )
            self._state = replace(self._state, phase=CONVERSATION_PHASE_THINKING)
<<<<<<< HEAD
            chat_response = self._chat_client.chat(
                {
                    "system": composed.system,
                    "prompt": transcript,
                    "persona_id": persona_id,
                    "prompt_metadata": composed.metadata.as_dict(),
                },
                self._headers(),
=======
            chat_response = self._measure_leg(
                timing_values,
                "chat_seconds",
                lambda: self._chat_client.chat(
                    {
                        "system": composed.system,
                        "prompt": transcript,
                        "persona_id": persona_id,
                        "prompt_metadata": composed.metadata.as_dict(),
                    },
                    self._headers(),
                ),
>>>>>>> main
            )
            reply = _response_text(chat_response, "reply")
            if _is_failure_response(chat_response) or not reply:
                return self._fail_from_response(
                    status=CONVERSATION_STATUS_CHAT_FAILED,
                    leg="chat",
                    persona_id=persona_id,
                    response=chat_response,
                    default_code="empty_reply",
                    default_message="Chat returned no reply.",
                    transcript=transcript,
                    confidence=_response_float(stt_response, "confidence"),
                    prompt_metadata=composed.metadata.as_dict(),
                    stt_metadata=_metadata(stt_response),
<<<<<<< HEAD
=======
                    timings=self._timings(timing_values, turn_started),
>>>>>>> main
                )

            self._state = replace(self._state, phase=CONVERSATION_PHASE_SPEAKING)
            voice = persona_voice_settings(self._persona_registry[persona_id])
<<<<<<< HEAD
            tts_response = self._synthesizer.speech(
                {
                    "text": reply,
                    "persona_id": persona_id,
                    "voice": {
                        "name": voice.name,
                        "rate": voice.rate,
                        "pitch": voice.pitch,
                        "volume": voice.volume,
                    },
                },
                self._headers(),
=======
            tts_response = self._measure_leg(
                timing_values,
                "tts_seconds",
                lambda: self._synthesizer.speech(
                    {
                        "text": reply,
                        "persona_id": persona_id,
                        "voice": {
                            "name": voice.name,
                            "rate": voice.rate,
                            "pitch": voice.pitch,
                            "volume": voice.volume,
                        },
                    },
                    self._headers(),
                ),
>>>>>>> main
            )
            if _is_failure_response(tts_response) or not _response_text(tts_response, "audio"):
                return self._fail_from_response(
                    status=CONVERSATION_STATUS_TTS_FAILED,
                    leg="tts",
                    persona_id=persona_id,
                    response=tts_response,
                    default_code="empty_audio",
                    default_message="Speech synthesis returned no playable audio.",
                    transcript=transcript,
                    reply=reply,
                    confidence=_response_float(stt_response, "confidence"),
                    prompt_metadata=composed.metadata.as_dict(),
                    stt_metadata=_metadata(stt_response),
                    chat_metadata=_metadata(chat_response),
<<<<<<< HEAD
                )
            try:
                playback = self._audio.speak(dict(tts_response))
=======
                    timings=self._timings(timing_values, turn_started),
                )
            try:
                playback = self._measure_leg(
                    timing_values,
                    "playback_seconds",
                    lambda: self._audio.speak(dict(tts_response)),
                )
>>>>>>> main
            except (HardwareError, HardwareUnavailableError, TypeError, ValueError) as error:
                return self._fail(
                    status=CONVERSATION_STATUS_TTS_FAILED,
                    persona_id=persona_id,
                    leg="tts",
                    code=type(error).__name__,
                    message=str(error),
                    transcript=transcript,
                    reply=reply,
                    confidence=_response_float(stt_response, "confidence"),
                    prompt_metadata=composed.metadata.as_dict(),
                    stt_metadata=_metadata(stt_response),
                    chat_metadata=_metadata(chat_response),
                    tts_metadata=_metadata(tts_response),
<<<<<<< HEAD
                )

=======
                    timings=self._timings(timing_values, turn_started),
                )

            timings = self._timings(timing_values, turn_started)
>>>>>>> main
            result = ConversationTurnResult.ok(
                persona_id=persona_id,
                transcript=transcript,
                reply=reply,
                confidence=_response_float(stt_response, "confidence"),
                prompt_metadata=composed.metadata.as_dict(),
                stt_metadata=_metadata(stt_response),
                chat_metadata=_metadata(chat_response),
                tts_metadata=_metadata(tts_response),
                playback=playback.as_dict(),
<<<<<<< HEAD
=======
                timings=timings,
>>>>>>> main
            )
            self._memory.append(persona_id, "user", transcript)
            self._memory.append(persona_id, "assistant", reply)
            self._state = ConversationState(
                persona=replace(self._state.persona, conversation_paused=False, audio_playing=False),
                phase=CONVERSATION_PHASE_IDLE,
                last_turn=result,
                degraded=False,
            )
            return result
        except Exception as error:  # noqa: BLE001 - runtime faults become recoverable status.
            return self._fail(
                status=CONVERSATION_STATUS_AUDIO_FAILED,
                persona_id=persona_id,
                leg="audio",
                code=type(error).__name__,
                message=str(error),
<<<<<<< HEAD
=======
                timings=self._timings(timing_values, turn_started),
>>>>>>> main
            )
        finally:
            self._safe_stop_audio()

    def _capture_audio(self, *, chunks: int) -> AudioBuffer:
        self._state = replace(self._state, phase=CONVERSATION_PHASE_LISTENING)
        start_state = self._audio.start()
        if start_state.status is not AudioStatus.OK:
            raise RuntimeError(start_state.detail or f"audio start failed: {start_state.status.value}")
        for index in range(chunks):
            capture = self._audio.capture_chunk()
            if capture.status is not AudioStatus.OK:
                detail = capture.detail or f"capture {index + 1}/{chunks} failed: {capture.status.value}"
                raise RuntimeError(detail)
        flush = self._audio.flush()
        if flush.status is not AudioStatus.OK or flush.audio is None:
            raise RuntimeError(flush.detail or f"audio flush failed: {flush.status.value}")
        self._audio.stop()
        return flush.audio

    def _transcribe(self, audio: AudioBuffer) -> Mapping[str, Any]:
        self._state = replace(self._state, phase=CONVERSATION_PHASE_TRANSCRIBING)
        wav_bytes = _wav_bytes(audio)
        return self._recognizer.recognize(
            {
                "audio": base64.b64encode(wav_bytes).decode("ascii"),
                "audio_format": "wav",
                "source": {
                    "source_id": audio.source_id,
                    "timestamp": audio.timestamp,
                    "chunk_count": audio.chunk_count,
                    "duration_seconds": audio.duration_seconds,
                },
            },
            self._headers(),
        )

    def _headers(self) -> Mapping[str, str]:
        return dict(self._headers_factory())

<<<<<<< HEAD
=======
    def _measure_leg(
        self,
        timing_values: dict[str, float],
        field_name: str,
        action: Callable[[], Any],
    ) -> Any:
        started = self._clock()
        try:
            return action()
        finally:
            timing_values[field_name] = self._clock() - started

    def _timings(self, timing_values: Mapping[str, float], turn_started: float) -> ConversationTurnTimings:
        return ConversationTurnTimings(
            audio_capture_seconds=timing_values.get("audio_capture_seconds"),
            stt_seconds=timing_values.get("stt_seconds"),
            chat_seconds=timing_values.get("chat_seconds"),
            tts_seconds=timing_values.get("tts_seconds"),
            playback_seconds=timing_values.get("playback_seconds"),
            total_seconds=self._clock() - turn_started,
        )

>>>>>>> main
    def _fail_from_response(
        self,
        *,
        status: str,
        leg: str,
        persona_id: str,
        response: Mapping[str, Any],
        default_code: str,
        default_message: str,
        transcript: str = "",
        reply: str = "",
        confidence: float = 0.0,
        prompt_metadata: Mapping[str, Any] | None = None,
        stt_metadata: Mapping[str, Any] | None = None,
        chat_metadata: Mapping[str, Any] | None = None,
<<<<<<< HEAD
=======
        timings: ConversationTurnTimings | None = None,
>>>>>>> main
    ) -> ConversationTurnResult:
        failure = _failure_payload(response)
        return self._fail(
            status=status,
            persona_id=persona_id,
            leg=leg,
            code=_optional_string(failure.get("code")) or _optional_string(response.get("status")) or default_code,
            message=_optional_string(failure.get("message")) or default_message,
            status_code=_optional_int(_metadata(response).get("status_code")),
            transcript=transcript,
            reply=reply,
            confidence=confidence,
            prompt_metadata=prompt_metadata,
            stt_metadata=stt_metadata,
            chat_metadata=chat_metadata,
            tts_metadata=_metadata(response) if leg == "tts" else None,
<<<<<<< HEAD
=======
            timings=timings,
>>>>>>> main
        )

    def _fail(
        self,
        *,
        status: str,
        persona_id: str,
        leg: str,
        code: str,
        message: str,
        status_code: int | None = None,
        transcript: str = "",
        reply: str = "",
        confidence: float = 0.0,
        prompt_metadata: Mapping[str, Any] | None = None,
        stt_metadata: Mapping[str, Any] | None = None,
        chat_metadata: Mapping[str, Any] | None = None,
        tts_metadata: Mapping[str, Any] | None = None,
<<<<<<< HEAD
    ) -> ConversationTurnResult:
        result = ConversationTurnResult.failure(
=======
        timings: ConversationTurnTimings | None = None,
    ) -> ConversationTurnResult:
        result = ConversationTurnResult.failed(
>>>>>>> main
            status=status,
            persona_id=persona_id,
            leg=leg,
            code=code,
            message=message,
            status_code=status_code,
            transcript=transcript,
            reply=reply,
            confidence=confidence,
            prompt_metadata=prompt_metadata,
            stt_metadata=stt_metadata,
            chat_metadata=chat_metadata,
            tts_metadata=tts_metadata,
<<<<<<< HEAD
=======
            timings=timings,
>>>>>>> main
        )
        self._state = ConversationState(
            persona=replace(self._state.persona, conversation_paused=False, audio_playing=False),
            phase=CONVERSATION_PHASE_FAILED,
            last_turn=result,
            degraded=True,
        )
        return result

    def _safe_stop_audio(self) -> None:
        try:
            self._audio.stop()
        except Exception:
            pass


def _wav_bytes(audio: AudioBuffer) -> bytes:
    output = BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(audio.channels)
        wav.setsampwidth(audio.sample_width)
        wav.setframerate(audio.sample_rate)
        wav.writeframes(audio.audio_bytes)
    return output.getvalue()


def _is_failure_response(response: Mapping[str, Any]) -> bool:
    metadata = _metadata(response)
    return bool(response.get("status") or metadata.get("failure"))


def _metadata(response: Mapping[str, Any]) -> dict[str, Any]:
    value = response.get("metadata")
    return dict(value) if isinstance(value, Mapping) else {}


def _failure_payload(response: Mapping[str, Any]) -> dict[str, Any]:
    value = _metadata(response).get("failure")
    return dict(value) if isinstance(value, Mapping) else {}


def _response_text(response: Mapping[str, Any], field: str) -> str:
    return _optional_string(response.get(field)) or ""


def _response_float(response: Mapping[str, Any], field: str) -> float:
    return _optional_float(response.get(field)) or 0.0


def _optional_mapping(value: Any) -> Mapping[str, Any] | None:
    return dict(value) if isinstance(value, Mapping) else None


def _optional_string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _required_string(value: Any, field_name: str) -> str:
    text = _optional_string(value)
    if text is None:
        raise ValueError(f"{field_name} must be a non-empty string.")
    return text


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


__all__ = [
    "CONVERSATION_PHASE_FAILED",
    "CONVERSATION_PHASE_IDLE",
    "CONVERSATION_PHASE_LISTENING",
    "CONVERSATION_PHASE_SPEAKING",
    "CONVERSATION_PHASE_THINKING",
    "CONVERSATION_PHASE_TRANSCRIBING",
    "CONVERSATION_STATUS_AUDIO_FAILED",
    "CONVERSATION_STATUS_CHAT_FAILED",
    "CONVERSATION_STATUS_OK",
    "CONVERSATION_STATUS_PERSONA_FAILED",
    "CONVERSATION_STATUS_STT_FAILED",
    "CONVERSATION_STATUS_TTS_FAILED",
    "DEFAULT_TURN_CHUNKS",
    "ChatClient",
    "ConversationFailure",
    "ConversationOrchestrator",
    "ConversationState",
<<<<<<< HEAD
=======
    "ConversationTurnTimings",
>>>>>>> main
    "ConversationTurnResult",
    "SpeechRecognizer",
    "SpeechSynthesizer",
]
