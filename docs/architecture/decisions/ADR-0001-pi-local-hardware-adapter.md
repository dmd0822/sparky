# ADR-0001 — Pi-Local Hardware Adapter

| Field | Value |
|-------|-------|
| **Status** | 🟦 **PROPOSED** — not accepted until the dual approval gate closes |
| **Date** | 2026-08-28 |
| **Owner** | Architect, with Robotics |
| **Deciders** | Dave Davis (approval gate) |
| **Supersedes** | — |
| **Related** | [ADR-0002](ADR-0002-deterministic-motion-arbiter.md), [ADR-0005](ADR-0005-privacy-defaults-camera-disabled.md) |
| **Related decisions** | [UD-01](../system-architecture.md#4-user-decision-register-ud-01--ud-10) (exact hardware), [UD-02](../system-architecture.md#4-user-decision-register-ud-01--ud-10) (stationary vs walking) |

> **Approval gate:** This ADR describes a recommendation. It authorizes nothing. Implementation remains BLOCKED until Dave Davis explicitly approves **both** `system-architecture.md` **and** `project-plan.md`. Approval of one alone, silence, or requested revisions does not open the gate.

## Context

The project depends on three bundled SunFounder libraries under `exlibs/`, which are **read-only and must never be modified**. Read-only assessment produced four facts that make direct dependency untenable:

| Evidence | Fact |
|----------|------|
| EV-02, EV-04 | The supplied robot-hat is `2.3.6`, but PiDog's own README instructs installing branch `2.5.x` (`exlibs/pidog/README.md:42`). |
| EV-05, EV-06 | PiDog's `llm.py`, `stt.py`, and `voice_assistant.py` import `robot_hat.llm`, `robot_hat.stt`, and `robot_hat.voice_assistant`, none of which exist in the supplied `robot_hat` package. |
| EV-07 | Consequently, importing those PiDog modules against the supplied robot-hat fails at import time. Guaranteed, not hypothetical. |
| EV-19, EV-20 | All three libraries declare **no** runtime dependencies, yet Vilib imports Flask and OpenCV at module import and PiDog imports NumPy. The real dependency graph is implicit. |

On top of that, Raspberry Pi OS Bookworm 64-bit with Python 3.11 is an **initial validation target, not established compatibility** (AS-01). We do not know that the supplied libraries run there.

If product code imports `pidog` and `robot_hat` freely, then every one of these problems — a version skew we did not choose, missing modules, an implicit dependency graph, and an unvalidated runtime — is spread across the entire codebase. Every module becomes a place where the skew can bite.

## Decision

**All access to `exlibs` goes through a single Pi-local hardware adapter.** No component outside the adapter implementation may import `pidog`, `robot_hat`, or `vilib`.

The adapter's contract:

| Rule | Statement |
|------|-----------|
| HA-01 | No module outside the adapter implementation imports `pidog`, `robot_hat`, or `vilib`. Enforced by a CI import guard. |
| HA-02 | The adapter exposes **semantic** operations only — `perform_gesture(name)`, `set_posture(name)`, `read_distance()`, `read_touch()`, `read_imu()`, `set_indicator(state)`, `go_safe_pose()`, `read_battery()`. Joint angles are not part of the caller-facing surface. |
| HA-03 | The adapter **never** imports `pidog.llm`, `pidog.stt`, `pidog.tts`, or `pidog.voice_assistant`. These are broken against the supplied robot-hat (EV-07) and duplicate our Azure path with an uncontrolled vendor path. Enforced by a CI ban check. |
| HA-04 | The adapter **never** starts the Vilib Flask service (EV-08, EV-09). See [ADR-0005](ADR-0005-privacy-defaults-camera-disabled.md). |
| HA-05 | At least two implementations exist and are freely interchangeable: `PiAdapter` (wraps `exlibs/pidog`) and `SimulatorAdapter`. |
| HA-06 | The adapter clamps **leg and tail** commands. PiDog clamps head angles (EV-12, `pidog.py:407-410`) but applies no equivalent clamp in the leg or tail threads (EV-13). We do not inherit that asymmetry. |
| HA-07 | The adapter reports the underlying library versions at startup and **refuses to arm** if they differ from the pinned, validated set. |
| HA-08 | The adapter owns the lifecycle of PiDog's daemon threads and its separate sensory `multiprocessing.Process` (EV-14, EV-16). Nothing outside the adapter touches them. |

`PiAdapter` is the only place in the entire system where the `2.3.6`-vs-`2.5.x` question has to be reasoned about. That containment is the whole point of this decision.

## Alternatives considered

| Alternative | Why rejected |
|-------------|--------------|
| **Import `pidog` directly wherever convenient** | Spreads the version skew, the missing-module hazard, and the unvalidated runtime across every module. Makes the simulator impossible. Makes the CI guards meaningless. |
| **Fork or patch `exlibs` to fix the version skew** | **Forbidden.** `exlibs` is read-only by explicit constraint. Also creates a permanent maintenance burden on someone else's library. |
| **Use PiDog's built-in AI path (`llm`, `stt`, `voice_assistant`)** | Broken against the supplied robot-hat (EV-07). Couples us to a vendor AI stack we do not control, do not review, and cannot secure. Bypasses our entire identity boundary ([ADR-0004](ADR-0004-azure-broker-identity-boundary.md)) and our content-safety checkpoints. |
| **A thin passthrough adapter exposing joint angles** | Defeats [ADR-0002](ADR-0002-deterministic-motion-arbiter.md). If callers can write angles, the arbiter is not the single authority and the safety model collapses. |
| **Simulator only, deferring the Pi implementation** | The runtime compatibility question (AS-01) is the highest-value unknown in the project. Deferring it means discovering a platform problem at M5 instead of M1. |

## Consequences

### Positive

- The version skew, the missing modules, the implicit dependency graph, and the unvalidated runtime are contained in one reviewable component.
- The simulator becomes trivially possible, which is what makes NFR-06 (test without hardware) and the entire M3 simulation stage achievable.
- The banned-import CI guard turns a subtle coupling risk into a build failure.
- Swapping the hardware substrate later — a different board, a different chassis — is a single-component change.

### Negative

- An extra abstraction layer with real maintenance cost.
- The semantic-only surface means some `exlibs` capability is deliberately unreachable. If a future need requires it, the adapter interface must be extended rather than bypassed — and that friction is intentional.
- Two implementations must be kept in step, and simulator fidelity is itself an assumption (AS-08).

### Neutral

- The adapter is where the GPLv3 boundary question (EV-21, §6.3) is most concentrated, which is convenient for the legal review flagged as R-12.

## Validation

| ID | Acceptance criterion | Milestone |
|----|---------------------|-----------|
| AC-HAL-01 | `PiAdapter` and `SimulatorAdapter` are substitutable with no caller change | M1 |
| AC-HAL-02 | No joint-angle API is reachable by callers | M1 |
| AC-HAL-03 | CI fails on any `pidog`/`robot_hat`/`vilib` import outside the adapter | M1 |
| AC-HAL-04 | CI fails on any import of the banned PiDog AI wrapper modules | M1 |
| AC-HAL-05 | Leg and tail commands are clamped | M1 |
| AC-HAL-06 | The adapter refuses to arm on a library version mismatch | M1 |
| AC-TEST-01 | Core tests run with no Pi and no Azure account | M1 |

## Open items

- **OQ-01** — pin robot-hat to `2.3.6` or `2.5.x`. Resolved in M1-D2.
- **AS-01** — runtime compatibility on Bookworm 64-bit / Python 3.11. Answered by M1-D1. **Not assumed true.**
- **UD-01** — exact hardware. Without it, M1 validates a guess.
- **UD-02** — stationary vs walking, which sets the adapter's gesture surface.

## Constraint restated

Nothing in this ADR authorizes any modification under `exlibs/`. That tree is read-only during planning and during implementation, permanently.
