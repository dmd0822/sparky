# ADR-0002 — Deterministic Motion Arbiter, and No Direct LLM Actuator Access

| Field | Value |
|-------|-------|
| **Status** | 🟦 **PROPOSED** — not accepted until the dual approval gate closes |
| **Date** | 2026-08-28 |
| **Owner** | Architect, with Robotics |
| **Deciders** | Dave Davis (approval gate) |
| **Supersedes** | — |
| **Related** | [ADR-0001](ADR-0001-pi-local-hardware-adapter.md), [ADR-0003](ADR-0003-immutable-versioned-personas.md), [ADR-0006](ADR-0006-push-to-talk-half-duplex.md) |
| **Related decisions** | [UD-02](../system-architecture.md#4-unresolved-user-decision-register-ud-01--ud-10) (stationary vs walking), [UD-03](../system-architecture.md#4-unresolved-user-decision-register-ud-01--ud-10) (physical e-stop) |

> **Approval gate:** This ADR describes a recommendation. It authorizes nothing. Implementation remains BLOCKED until Dave Davis explicitly approves **both** `system-architecture.md` **and** `project-plan.md`. Approval of one alone, silence, or requested revisions does not open the gate.

## Context

This device has twelve torque-bearing servos (EV-11) and operates near people. Two independent facts make an explicit safety component mandatory.

**First, `exlibs` provides no safety model.** Read-only assessment found:

| Evidence | Observation |
|----------|-------------|
| EV-14 | Motion runs in three independent daemon threads (`legs`, `head`, `tail`) consuming three separate **unbounded** buffers under three separate locks (`pidog.py:358-430`). |
| EV-13 | Head angles are clamped (`pidog.py:407-410`), but the leg and tail threads apply **no** equivalent clamp. |
| EV-15 | `legs_stop` / `head_stop` / `tail_stop` clear a buffer and then busy-wait until it drains (`pidog.py:513-531`, `:940-967`). |
| — | There is no command time-to-live, no cancellation token, no watchdog, no startup inhibit, and no single writer. |

A queued action in an unbounded buffer with no TTL executes whenever the thread reaches it — thirty seconds later, after the conversation has moved on, in a context nobody intended. And `body_stop()`'s busy-wait drain is a poor primitive to build an emergency response on, because it waits for the very buffer you are trying to escape.

**Second, a language model is a fundamentally unsuitable source of actuator commands.** It is non-deterministic, it is subject to prompt injection from anything a user says, it has no model of the device's physical state, and its output cannot be exhaustively tested. A model that can emit joint angles is a model that can emit a pose that topples the device or crushes a finger, and no amount of prompt engineering makes that safe.

## Decision

**One deterministic motion arbiter holds sole authority to write actuators. The language model has no actuator access, direct or indirect.**

### Sole authority

Exactly one component — the arbiter — calls the hardware adapter's motion operations (SR-05). This is verified by static analysis in CI, not by convention (AC-SAF-05).

### Semantic commands only

The arbiter accepts **named** gestures and postures from a **static allowlist** derived from PiDog's `preset_actions` vocabulary (EV-18 — roughly 26 curated behaviours such as `bark`, `nod`, `think`, `stretch`, `alert`). It does not accept joint angles from any caller in the AI path (SR-06).

The model's contribution to motion is at most a **gesture name**. That name is validated at L3 against the active persona's declared motion vocabulary ([ADR-0003](ADR-0003-immutable-versioned-personas.md)) before it ever reaches the arbiter. A name that is not in the persona's vocabulary is rejected, telemetry is emitted, and **the device still speaks the reply** — it simply does not move. A rejected gesture is an observability event, not a user-visible failure.

So the worst a fully compromised or hallucinating model can do to the physical device is: request a gesture the persona already permits, or request nothing.

### Mechanisms

| Mechanism | Behavior | Requirement |
|-----------|----------|-------------|
| **TTL** | Every command carries a time-to-live. A command whose TTL expires before execution is dropped and counted, never executed late. | SR-03 |
| **Cancellation** | Commands carry a generation ID. Cancelling a generation removes all its pending commands and unwinds in-flight motion to neutral. This is what binds motion cancellation to speech cancellation on barge-in ([ADR-0006](ADR-0006-push-to-talk-half-duplex.md)). | FR-08 |
| **Watchdog** | The arbiter must be serviced within a bounded interval. If it is not, the watchdog drives the safe pose and latches. | SR-04 |
| **Startup inhibit** | The arbiter starts inhibited and refuses all commands until explicitly armed after self-test. `Inhibited` is the only post-boot state. | SR-02, ST-01 |
| **Priority** | Safety commands preempt everything. Expressive gestures are lowest priority and are **dropped, not queued**, under contention. | §10.2 |
| **Determinism** | Given the same command sequence and the same clock, the arbiter produces the same actuator sequence. This is what makes it exhaustively testable in simulation. | AC-SAF-07 |
| **Fail-safe** | Any unhandled exception in the motion path drives the safe pose and latches. Recovery requires explicit operator reset — never automatic. | SR-07, ST-03 |

The arbiter maintains its own command state and drives the adapter to a known safe pose directly. It does **not** use PiDog's busy-wait `body_stop()` (EV-15) as its emergency primitive.

### Independent latched e-stop

The e-stop is **independent of software** (SR-01). It is not an arbiter feature, not a state the software chooses to enter, and not a signal a hung process can swallow. It is a latched physical cutoff. Software observes and reports it; software cannot clear it. Clearing requires an explicit operator action at the device.

⚠️ **Blocked by UD-03.** Specification, sourcing, and wiring are unresolved. **Hardware-in-the-loop testing does not begin without it** — this is a hard M5 entry gate.

## Alternatives considered

| Alternative | Why rejected |
|-------------|--------------|
| **Let the model emit joint angles, validated against ranges** | Range validation does not make a non-deterministic, injectable, physically-unaware source safe. A sequence of individually in-range angles can still topple the device or trap a finger. Untestable in principle. |
| **Let the model emit angles, with a human-approval step** | Destroys the interaction entirely and does not scale past a demo. |
| **Use PiDog's threads and buffers directly, adding a stop call** | The buffers are unbounded with no TTL (EV-14), leg and tail are unclamped (EV-13), and `body_stop()` is a busy-wait drain (EV-15). Adding a stop call on top of that is not a safety model. |
| **Multiple writers with a mutex** | A mutex serializes writes but does not arbitrate intent. Two components both "correctly" holding the lock can still produce an incoherent motion sequence. Single authority is the only property that makes the sequence reasonable about. |
| **Software-only e-stop** | A hung process cannot execute its own e-stop. This is the single case an e-stop most needs to cover. |
| **Automatic recovery from a latched fault** | A fault that recovers itself is a fault that recurs unobserved. REL-C6 explicitly treats watchdog trips as defects, not tuning parameters. |

## Consequences

### Positive

- The physical safety surface is one small, deterministic, exhaustively-testable component instead of a property distributed across the whole system.
- The worst-case behaviour of a compromised or hallucinating model is bounded to the persona's already-approved gesture set.
- Barge-in cancellation of speech and motion is a single mechanism (generation IDs) rather than cross-subsystem coordination.
- Determinism makes M3's exhaustive simulation sweep meaningful.

### Negative

- Expressiveness is bounded by the allowlist. The model cannot invent a new gesture, ever. This is a real product cost and it is accepted deliberately.
- Adding a gesture requires adapter support, allowlist entry, simulation validation, and hardware validation. That is slow by design.
- The arbiter is a single point of failure for all motion — which is why the watchdog, fail-safe, and independent e-stop exist around it.

### Neutral

- The gesture-rejection rate becomes a useful signal: a persona whose prompt keeps asking for gestures it does not have is a persona that needs its prompt fixed.

## Validation

| ID | Acceptance criterion | Milestone |
|----|---------------------|-----------|
| AC-MOT-01 | A free-form joint-angle command from any AI path is rejected; only allowlisted semantic commands execute | M3 |
| AC-MOT-02 | An out-of-vocabulary gesture is rejected, telemetry emitted, reply still spoken | M3 |
| AC-SAF-02 | The arbiter refuses all commands before arming | M3 |
| AC-SAF-03 | An expired-TTL command is dropped and counted, never executed late | M3 |
| AC-SAF-04 / -04-HW | Watchdog expiry drives the safe pose and latches — in simulation **and** on hardware | M3, M5 |
| AC-SAF-05 | Static analysis proves exactly one actuator writer | M3 |
| AC-SAF-06 / -06-HW | Unhandled motion-path exception drives the safe pose and latches — sim **and** hardware | M3, M5 |
| AC-SAF-07 / -07-HW | The safe pose is reachable from every commanded pose without topple — sim **and** hardware | M3, M5 |
| AC-SAF-01 | Physical e-stop cuts motion regardless of software state, including with the process hung; software cannot clear it | M5 |
| AC-FLOOR-02 | The e-stop remains effective during unrestrained motion | M6 |

## Open items

- **UD-03** — physical e-stop, cutoff, and mute. **Hard block on M5.** Without it, no hardware-in-the-loop testing is authorized. Rai blocker RAI-B1.
- **UD-02** — stationary vs walking. Walking substantially expands the safety envelope, the topple analysis, and the M6 floor requirements.
- **OQ-02** — the concrete safe-pose definition, and whether it differs between stationary and walking.
- **AS-07** — that the safe pose is reachable from every commanded pose. A safety assumption, validated in M3 simulation and again on M5 hardware.

## Constraint restated

Nothing in this ADR authorizes any modification under `exlibs/`. The arbiter works around `exlibs` limitations by wrapping them via [ADR-0001](ADR-0001-pi-local-hardware-adapter.md), never by patching them.
