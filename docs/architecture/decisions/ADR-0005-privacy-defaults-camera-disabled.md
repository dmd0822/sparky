# ADR-0005 — Privacy Defaults and Camera Disabled

| Field | Value |
|-------|-------|
| **Status** | 🟦 **PROPOSED** — not accepted until the dual approval gate closes |
| **Date** | 2026-08-28 |
| **Owner** | Architect, with Rai |
| **Deciders** | Dave Davis (approval gate) |
| **Supersedes** | — |
| **Related** | [ADR-0001](ADR-0001-pi-local-hardware-adapter.md), [ADR-0003](ADR-0003-immutable-versioned-personas.md), [ADR-0006](ADR-0006-push-to-talk-half-duplex.md) |
| **Related decisions** | [UD-04](../system-architecture.md#4-unresolved-user-decision-register-ud-01--ud-10) (bystanders), [UD-05](../system-architecture.md#4-unresolved-user-decision-register-ud-01--ud-10) (camera need), [UD-07](../system-architecture.md#4-unresolved-user-decision-register-ud-01--ud-10) (retention and memory) |

> **Approval gate:** This ADR describes a recommendation. It authorizes nothing. Implementation remains BLOCKED until Dave Davis explicitly approves **both** `system-architecture.md` **and** `project-plan.md`. Approval of one alone, silence, or requested revisions does not open the gate.

## Context

This is a microphone and a camera in a room where people live. That framing, rather than "a robot dog", is the correct starting point for the privacy design.

Three facts drive this decision.

**Fact 1 — the bundled vision library exposes an unauthenticated camera stream to the entire local network.**

| Evidence | Observation |
|----------|-------------|
| EV-08 | `exlibs/vilib/vilib/vilib.py:176` — `app.run(host='0.0.0.0', port=9000, threaded=True, debug=False)`. Bound to **all** interfaces. |
| EV-09 | The routes `/`, `/mjpg`, `/mjpg.jpg`, `/mjpg.png`, `/qrcode`, `/qrcode.png` (`vilib.py:64,95,112,120,128,156`) carry **no** authentication or authorization decorator of any kind. |
| EV-10 | `vilib.py:58` sets `FLASK_DEBUG` to `development` at module import time. |
| EV-20 | Vilib imports Flask and OpenCV at import time despite declaring no dependencies, so this service arrives implicitly. |

Anyone on the same network segment — a guest on the Wi-Fi, a compromised IoT device, a neighbour on an open network — can open a browser and watch the camera. There is no credential to get wrong and no log of who watched.

**Fact 2 — bystanders cannot consent.** A companion device in a home is heard by people who never agreed to interact with it: family members, guests, children, a delivery driver at the door. Any retention default other than "none" makes the device a recording device for people who did not opt in.

**Fact 3 — three of the relevant decisions are unresolved.** UD-04 (bystanders and children), UD-05 (is the camera needed at all), and UD-07 (retention, deletion, memory) are all open. A design that assumes permissive answers to open questions is a design that has to be retracted.

## Decision

**Privacy-preserving defaults, with the camera disabled and the Vilib web service never started.**

### The defaults

| Default | Value | Requirement |
|---------|-------|-------------|
| Raw audio retention | **None** | PR-01 |
| Transcript retention | **None** | PR-02 |
| Camera | **Disabled** | PR-03, FR-13 |
| Vilib Flask web service | **Never started** | PR-04 |
| Cross-session memory | **None** | UD-07 assumption |
| Transcript, audio, or credential in logs | **Never at default level** | PR-05 |
| AI disclosure | **On** | FR-12, PR-07 |
| Content-safety strictness | **Strictest tier** while UD-04 is open | PR-06 |

These are defaults in the strong sense: they hold unless a user decision explicitly changes them, and changing any of them requires a Rai re-review.

### Camera exclusion is structural, not configurational

The camera is not merely "off by default in config". For v1:

- The hardware adapter **never** starts the Vilib Flask service (HA-04).
- The Vilib detection modules — face, hands, pose, objects, colour, QR — are excluded from v1 entirely.
- **NG-02** excludes person identification, face recognition, and biometric matching as a product goal, not just as a v1 scope cut.
- **NG-08** excludes emotional-state inference and affect classification of the user.
- A CI import guard prevents any module from importing `vilib` (HA-01).
- A runtime assertion verifies nothing is listening on port 9000 during a full run (AC-PRIV-03).

Four independent controls, because a single config flag is exactly the kind of thing that gets flipped for a demo and never flipped back.

### Data lifecycle

Audio exists as a PCM buffer in memory for the duration of a request and is discarded. Transcript text exists in memory for the duration of the session and is discarded at session end. Neither is written to disk at any point (§7.4). Telemetry carries generation IDs, `persona_id@version`, and per-stage durations — and explicitly excludes audio, transcript, reply text, user identifiers, and credentials (§13.1).

That split is the whole design: enough to debug latency and behaviour, not enough to reconstruct what anyone said.

### Enabling the camera later

If UD-05 determines the camera is needed, enabling it requires **all** of:

1. An explicit user decision recorded against UD-05.
2. A Rai re-review with a new privacy assessment.
3. A visible physical indicator whenever the camera is active.
4. **Never** the Vilib Flask web service — that exposure is refused permanently regardless of UD-05.
5. A defined retention answer under UD-07 covering image data.

Point 4 is not conditional. Even with a camera, an unauthenticated MJPEG stream on `0.0.0.0:9000` is not acceptable.

## Alternatives considered

| Alternative | Why rejected |
|-------------|--------------|
| **Enable the camera, use Vilib as shipped** | EV-08, EV-09, EV-10. An unauthenticated camera stream on all interfaces, with Flask in development mode. This is a privacy breach available to anyone on the network. |
| **Enable the camera, but bind Vilib to localhost** | Requires modifying `exlibs`, which is **forbidden**. Even if it did not, it leaves the unauthenticated routes and development-mode Flask intact for anything with local access. |
| **Enable the camera, wrap Vilib but never call `display()`** | Relies on no code path ever calling it, including examples, future contributors, and dependencies. Too fragile a guarantee for this exposure. |
| **Retain transcripts for quality improvement** | Bystanders cannot consent (UD-04). No retention or deletion policy exists (UD-07, PR-10). Rai blocker RAI-B3. |
| **Retain audio for debugging** | Same consent problem, with a strictly larger exposure. Per-stage latency telemetry gives us the debugging value without the recordings. |
| **Cross-session memory for a better companion experience** | A genuinely attractive product feature, and squarely blocked by UD-07. It needs a storage design, an encryption design, a deletion mechanism, and a retention policy — none of which exist. NG-10. |
| **Permissive defaults, tighten later** | Backwards. Permissive defaults ship, get depended upon, and are then hard to withdraw. Restrictive defaults can be relaxed by an explicit, reviewed decision. |

## Consequences

### Positive

- The device cannot be turned into a network-accessible camera by accident, and four independent controls would all have to fail for it to happen.
- No recordings exist to be breached, subpoenaed, or leaked.
- Bystanders who never consented are not recorded.
- The defaults are defensible to a non-technical person in one sentence: it does not record, and the camera is off.

### Negative

- No vision features in v1: no face tracking, no gesture recognition, no object following. For a companion robot this is a real expressiveness loss and it is accepted deliberately.
- No cross-session memory means the device does not remember you between sessions. This is the single largest product cost of this ADR.
- Debugging a behavioural complaint is harder without transcripts. Per-stage telemetry and gesture-rejection metrics partially compensate; they do not fully replace it.

### Neutral

- If UD-05 and UD-07 come back permissive, this ADR does not have to be reversed wholesale — it defines the specific gates each relaxation must pass.

## Validation

| ID | Acceptance criterion | Milestone |
|----|---------------------|-----------|
| AC-PRIV-03 | No process listens on port 9000 at any point during a full run | M1 |
| AC-HAL-03 | CI fails if any module outside the adapter imports `vilib` | M1 |
| AC-PRIV-01 | After a full session, no audio file and no transcript exists on disk | M4 |
| AC-PRIV-04 | Default-level logs contain no transcript, audio, or credential | M4 |
| AC-PRIV-02 | The camera is disabled by default; with default config the camera hardware is never initialized | M7 |
| AC-PRIV-05 | Across the full soak, no audio, transcript, or credential is written to disk | M7 |
| AC-RAI-03 | Rai blockers closed with evidence, or explicitly accepted in writing by Dave Davis | M7 |

## Open items

- **UD-05** — is the camera needed at all? Until answered, it stays off and Vilib stays excluded. Gates M7 entry.
- **UD-04** — children, guests, bystanders. Sets the consent model and content-safety strictness. Rai blocker RAI-B2. Gates M4 exit and M7 entry.
- **UD-07** — retention, deletion, memory. No retention feature may be built without it (PR-10). Rai blocker RAI-B3. Gates M4 exit and M7 entry.
- **RAI-B4** — the unauthenticated Vilib service in the dependency tree. The ban on this specific service is **unconditional** and does not depend on UD-05 (see "Enabling the camera later," point 4, above). If UD-05 confirms a camera is needed, that requires a separately designed, authenticated camera path — not this service. The broader camera-privacy question stays open until UD-05 is resolved and, if needed, that separate design is reviewed.
- **R-03** — the risk that a dependency or example accidentally starts the Vilib service.

## Constraint restated

Nothing in this ADR authorizes any modification under `exlibs/`. Vilib's unauthenticated service is neutralized by **never invoking it**, and by CI guards and a runtime port assertion that prove it was never invoked — never by patching Vilib.
