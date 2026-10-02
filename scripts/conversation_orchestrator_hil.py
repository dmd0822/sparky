#!/usr/bin/env python3
"""Hardware-in-the-loop runner for Sparky's conversation orchestrator.

The script validates the device runtime path with mocked relay legs: microphone
capture, prompt composition, synthesized-audio playback, and safe cleanup. CI
uses simulator ports and a WAV fixture; the Pi run uses the real microphone and
speaker while avoiding live Azure dependencies.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
from enum import Enum
from io import BytesIO
import os
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, TextIO
import wave


ROOT = Path(__file__).resolve().parents[1]
DEVICE_SRC = ROOT / "src" / "device"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if DEVICE_SRC.exists():
    sys.path.insert(0, str(DEVICE_SRC))

from sparky_device.hardware import (  # noqa: E402
    HARDWARE_ENV_VAR,
    PIDOG_PROFILE,
    RobotPorts,
    SIMULATOR_PROFILE,
    create_ports,
)
from sparky_device.personas import load_persona_registry  # noqa: E402
from sparky_device.services import (  # noqa: E402
    CONVERSATION_STATUS_OK,
    AudioService,
    ConversationOrchestrator,
)


AUDIO_FIXTURE = ROOT / "tests" / "fixtures" / "audio" / "tone-16khz.wav"
DEFAULT_CAPTURE_CHUNKS = 3
DEFAULT_PERSONA_ID = "sunny_companion"


class Status(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(frozen=True)
class StepResult:
    number: int
    title: str
    status: Status
    message: str

    @property
    def ok(self) -> bool:
        return self.status is not Status.FAIL


@dataclass(frozen=True)
class RunResult:
    ok: bool
    message: str
    results: tuple[StepResult, ...]
    robot: RobotPorts | None = None
    service: AudioService | None = None


@dataclass
class RunContext:
    robot: RobotPorts | None = None
    service: AudioService | None = None
    orchestrator: ConversationOrchestrator | None = None
    recognizer: "MockRecognizer | None" = None
    chat: "MockChat | None" = None
    synthesizer: "MockSynthesizer | None" = None


class MockRecognizer:
    def __init__(self) -> None:
        self.calls: list[Mapping[str, Any]] = []

    def recognize(self, payload: Mapping[str, Any], headers: Mapping[str, str]) -> Mapping[str, Any]:
        self.calls.append(dict(payload))
        return {
            "transcript": "hello sparky",
            "confidence": 0.99,
            "metadata": {"latency_ms": 1, "recognition_status": "Success"},
        }


class MockChat:
    def __init__(self) -> None:
        self.calls: list[Mapping[str, Any]] = []

    def chat(self, payload: Mapping[str, Any], headers: Mapping[str, str]) -> Mapping[str, Any]:
        self.calls.append(dict(payload))
        return {"reply": "Conversation orchestrator check complete.", "metadata": {"latency_ms": 1}}


class MockSynthesizer:
    def __init__(self) -> None:
        self.calls: list[Mapping[str, Any]] = []

    def speech(self, payload: Mapping[str, Any], headers: Mapping[str, str]) -> Mapping[str, Any]:
        self.calls.append(dict(payload))
        return {
            "audio": base64.b64encode(_wav_bytes()).decode("ascii"),
            "audio_format": "wav",
            "metadata": {"latency_ms": 1},
        }


_STEP_TITLES = {
    1: "Hardware profile check",
    2: "Conversation orchestrator construction",
    3: "Complete mocked voice turn",
    4: "Prompt and persona routing",
    5: "Playback and cleanup readiness",
    6: "Clean shutdown",
}
_ALL_STEPS = tuple(range(1, 7))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run Sparky's conversation orchestrator HIL check. The cloud legs are "
            "mocked; real runs validate the PiDog microphone and speaker path."
        )
    )
    parser.add_argument("--simulate", action="store_true", help="Use simulator ports and the WAV fixture.")
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Run the non-hardware CI harness. Equivalent to --simulate.",
    )
    parser.add_argument(
        "--chunks",
        type=int,
        default=DEFAULT_CAPTURE_CHUNKS,
        help=f"Number of microphone chunks to capture (default: {DEFAULT_CAPTURE_CHUNKS}).",
    )
    parser.add_argument("--persona-id", default=DEFAULT_PERSONA_ID, help="Persona to activate for the voice turn.")
    return parser


def make_robot(*, simulate: bool) -> RobotPorts:
    if simulate:
        return create_ports(profile=SIMULATOR_PROFILE, microphone_fixture_path=AUDIO_FIXTURE)
    return create_ports()


def _result(number: int, status: Status, message: str) -> StepResult:
    return StepResult(number, _STEP_TITLES[number], status, message)


def _print_step(result: StepResult, out: TextIO) -> None:
    print(f"Step {result.number} {result.status.value}: {result.title} - {result.message}", file=out)


def _ensure_robot(ctx: RunContext, *, simulate: bool) -> RobotPorts:
    if ctx.robot is None:
        ctx.robot = make_robot(simulate=simulate)
    return ctx.robot


def _ensure_orchestrator(ctx: RunContext, *, persona_id: str) -> ConversationOrchestrator:
    if ctx.robot is None:
        raise RuntimeError("robot ports have not been created")
    if ctx.robot.microphone is None:
        raise RuntimeError("robot ports do not include a microphone")
    if ctx.robot.speaker is None:
        raise RuntimeError("robot ports do not include a speaker")
    if ctx.orchestrator is None:
        ctx.service = AudioService(ctx.robot.microphone, speaker=ctx.robot.speaker)
        ctx.recognizer = MockRecognizer()
        ctx.chat = MockChat()
        ctx.synthesizer = MockSynthesizer()
        ctx.orchestrator = ConversationOrchestrator(
            audio=ctx.service,
            recognizer=ctx.recognizer,
            chat_client=ctx.chat,
            synthesizer=ctx.synthesizer,
            persona_registry=load_persona_registry(),
            active_persona_id=persona_id,
            headers_factory=lambda: {"Authorization": "Bearer hil-mock", "x-correlation-id": "hil-conversation"},
        )
    return ctx.orchestrator


def _run_step(
    step: int,
    ctx: RunContext,
    *,
    simulate: bool,
    chunks: int,
    persona_id: str,
) -> StepResult:
    robot = _ensure_robot(ctx, simulate=simulate)
    if step == 1:
        if simulate:
            if robot.profile != SIMULATOR_PROFILE:
                return _result(1, Status.FAIL, f"create_ports() profile is {robot.profile!r}, expected simulator")
            if not AUDIO_FIXTURE.is_file():
                return _result(1, Status.FAIL, f"audio fixture missing: {AUDIO_FIXTURE}")
            return _result(1, Status.PASS, f"create_ports() profile is {robot.profile!r}; using WAV fixture")
        expected_env = os.environ.get(HARDWARE_ENV_VAR)
        if expected_env != PIDOG_PROFILE:
            return _result(
                1,
                Status.FAIL,
                f"set {HARDWARE_ENV_VAR}=pidog before the hardware run; current value is {expected_env!r}",
            )
        if robot.profile != PIDOG_PROFILE:
            return _result(1, Status.FAIL, f"profile is {robot.profile!r}, expected 'pidog'")
        return _result(1, Status.PASS, f"create_ports() profile is {robot.profile!r}")

    orchestrator = _ensure_orchestrator(ctx, persona_id=persona_id)
    if step == 2:
        return _result(2, Status.PASS, f"active_persona_id={orchestrator.state.active_persona_id}")

    if step == 3:
        result = orchestrator.run_voice_turn(chunks=chunks)
        if result.status != CONVERSATION_STATUS_OK:
            failure = "unknown failure" if result.failure is None else result.failure.message
            return _result(3, Status.FAIL, f"status={result.status} detail={failure}")
        return _result(
            3,
            Status.PASS,
            (
                f"transcript={result.transcript!r}, reply={result.reply!r}, "
                f"confidence={result.confidence:.2f}, timings={_format_timings(result.timings)}"
            ),
        )

    if step == 4:
        if ctx.chat is None or ctx.synthesizer is None or not ctx.chat.calls or not ctx.synthesizer.calls:
            return _result(4, Status.FAIL, "mock relay calls were not recorded")
        prompt_metadata = ctx.chat.calls[0].get("prompt_metadata", {})
        if not isinstance(prompt_metadata, Mapping) or prompt_metadata.get("persona_id") != persona_id:
            return _result(4, Status.FAIL, "prompt metadata did not preserve the active persona")
        if ctx.synthesizer.calls[0].get("persona_id") != persona_id:
            return _result(4, Status.FAIL, "speech payload did not carry the active persona")
        return _result(4, Status.PASS, f"persona_id={persona_id}, relay legs called through mocks")

    if step == 5:
        speaker = robot.speaker
        if speaker is None:
            return _result(5, Status.FAIL, "robot ports do not include a speaker")
        playbacks = getattr(speaker, "playbacks", None)
        if isinstance(playbacks, list) and not playbacks:
            return _result(5, Status.FAIL, "speaker recorded no playback")
        return _result(5, Status.PASS, "speech output reached the speaker port")

    if step == 6:
        return _result(6, Status.PASS, "clean shutdown is reported after cleanup")

    raise AssertionError(f"unhandled step {step}")


def run_check(
    robot: RobotPorts | None = None,
    *,
    simulate: bool = False,
    chunks: int = DEFAULT_CAPTURE_CHUNKS,
    persona_id: str = DEFAULT_PERSONA_ID,
    steps: Iterable[int] = _ALL_STEPS,
    out: TextIO = sys.stdout,
) -> RunResult:
    if chunks < 1:
        raise ValueError(f"chunks must be at least 1, got {chunks}")
    ctx = RunContext(robot=robot)
    results: list[StepResult] = []
    print(f"Sparky conversation HIL using profile: {'simulator' if simulate else 'pidog'}", file=out)
    try:
        for step in tuple(steps):
            if step == 6:
                continue
            try:
                result = _run_step(step, ctx, simulate=simulate, chunks=chunks, persona_id=persona_id)
            except Exception as error:  # noqa: BLE001 - convert step failure into summary.
                result = _result(step, Status.FAIL, f"{type(error).__name__}: {error}")
                results.append(result)
                _print_step(result, out)
                return _finish_results(results, ctx.robot, ctx.service)
            results.append(result)
            _print_step(result, out)
            if result.status is Status.FAIL:
                return _finish_results(results, ctx.robot, ctx.service)
    except KeyboardInterrupt:
        interrupted = StepResult(0, "Interrupted", Status.FAIL, "interrupted by operator")
        return RunResult(False, "Sparky conversation HIL interrupted by operator", (interrupted,), ctx.robot, ctx.service)
    return _finish_results(results, ctx.robot, ctx.service)


def _finish_results(
    results: list[StepResult],
    robot: RobotPorts | None = None,
    service: AudioService | None = None,
) -> RunResult:
    ok = all(result.ok for result in results)
    status = "PASS" if ok else "FAIL"
    return RunResult(ok, f"Sparky conversation HIL {status}", tuple(results), robot, service)


def safe_shutdown(
    robot: RobotPorts | None,
    service: AudioService | None = None,
    out: TextIO = sys.stdout,
) -> StepResult | None:
    if robot is None and service is None:
        return None
    print("Safety cleanup: stopping conversation audio and closing ports.", file=out)
    errors: list[BaseException] = []
    if service is not None:
        try:
            service.close()
        except Exception as error:  # noqa: BLE001 - report after cleanup attempt.
            errors.append(error)
    if robot is not None:
        try:
            robot.close()
        except Exception as error:  # noqa: BLE001 - report after cleanup attempt.
            errors.append(error)
    if errors:
        return _result(6, Status.FAIL, "cleanup reported " + "; ".join(f"{type(e).__name__}: {e}" for e in errors))
    return _result(6, Status.PASS, "conversation audio stopped and ports closed")


def print_summary(results: Iterable[StepResult], out: TextIO = sys.stdout) -> None:
    results = tuple(results)
    print("", file=out)
    print("Summary:", file=out)
    for result in results:
        print(f"  {result.number:>2}. {result.status.value:<4} {result.title}: {result.message}", file=out)
    failures = [result.number for result in results if result.status is Status.FAIL]
    if failures:
        print("", file=out)
        print("Triage:", file=out)
        if 1 in failures:
            print("  - Failure in step 1 is an environment/profile or fixture problem.", file=out)
        if any(step in failures for step in (2, 3, 4)):
            print("  - Failure in steps 2-4 points at orchestrator wiring or mocked relay contracts.", file=out)
        if 5 in failures:
            print("  - Failure in step 5 points at speaker playback or audio-service output.", file=out)
        if 6 in failures:
            print("  - Cleanup failure means the operator should confirm microphone/speaker processes stopped.", file=out)


def _format_timings(timings: Any) -> str:
    if timings is None:
        return "unavailable"
    values = (
        ("audio_capture", getattr(timings, "audio_capture_seconds", None)),
        ("stt", getattr(timings, "stt_seconds", None)),
        ("chat", getattr(timings, "chat_seconds", None)),
        ("tts", getattr(timings, "tts_seconds", None)),
        ("playback", getattr(timings, "playback_seconds", None)),
        ("total", getattr(timings, "total_seconds", None)),
    )
    return ", ".join(f"{name}={value:.3f}s" if value is not None else f"{name}=n/a" for name, value in values)


def main(argv: list[str] | None = None, out: TextIO = sys.stdout) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    simulate = args.simulate or args.ci
    robot: RobotPorts | None = None
    service: AudioService | None = None
    run_result = RunResult(False, "Sparky conversation HIL did not complete", ())
    shutdown_result: StepResult | None = None
    exit_code = 1
    try:
        run_result = run_check(
            None,
            simulate=simulate,
            chunks=args.chunks,
            persona_id=args.persona_id,
            out=out,
        )
        robot = run_result.robot
        service = run_result.service
        exit_code = 0 if run_result.ok else 1
    except KeyboardInterrupt:
        interrupt = StepResult(0, "Interrupted", Status.FAIL, "interrupted by operator")
        run_result = RunResult(False, "Sparky conversation HIL interrupted by operator", (interrupt,), robot, service)
        exit_code = 130
    except Exception as error:  # noqa: BLE001 - CLI reports and exits non-zero.
        failure = StepResult(0, "Unhandled error", Status.FAIL, f"{type(error).__name__}: {error}")
        run_result = RunResult(False, "Sparky conversation HIL FAIL", (failure,), robot, service)
        exit_code = 1
    finally:
        shutdown_result = safe_shutdown(robot, service, out=out)

    final_results = list(run_result.results)
    if shutdown_result is not None:
        final_results = [result for result in final_results if result.number != 6]
        final_results.append(shutdown_result)
        _print_step(shutdown_result, out)
        if shutdown_result.status is Status.FAIL:
            exit_code = 1
    print(run_result.message, file=out)
    print_summary(final_results, out=out)
    return exit_code


def _wav_bytes() -> bytes:
    output = BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 1600)
    return output.getvalue()


if __name__ == "__main__":
    raise SystemExit(main())
