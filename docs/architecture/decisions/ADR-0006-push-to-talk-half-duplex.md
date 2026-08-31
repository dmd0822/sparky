# ADR-0006 — Push-to-Talk and Half-Duplex for the First Release

| Field | Value |
|-------|-------|
| **Status** | 🟦 **PROPOSED** — not accepted until the dual approval gate closes |
| **Date** | 2026-08-28 |
| **Owner** | Architect, with Speech |
| **Deciders** | Dave Davis (approval gate) |
| **Supersedes** | — |
| **Related** | [ADR-0002](ADR-0002-deterministic-motion-arbiter.md), [ADR-0005](ADR-0005-privacy-defaults-camera-disabled.md) |
| **Related decisions** | [UD-03](../system-architecture.md#4-user-decision-register-ud-01--ud-10) (mute control), [UD-06](../system-architecture.md#4-user-decision-register-ud-01--ud-10) (offline behavior), [UD-08](../system-architecture.md#4-user-decision-register-ud-01--ud-10) (languages, disclosure), [UD-09](../system-architecture.md#4-user-decision-register-ud-01--ud-10) (latency) |

> **Approval gate:** This ADR describes a recommendation. It authorizes nothing. Implementation remains BLOCKED until Dave Davis explicitly approves **both** `system-architecture.md` **and** `project-plan.md`. Approval of one alone, silence, or requested revisions does not open the gate.

## Context

The obvious design for a conversational companion is always-on wake-word listening with full-duplex speech. It is also the design that bundles together the four hardest problems in the system and asks us to solve them all before anything works.

**Always-on listening costs:**
- A microphone that is always open, which is a privacy posture we cannot justify while the approved UD-04 posture remains in force.
- Wake-word false accepts, which mean the device starts listening — and possibly talking — when nobody addressed it.
- Wake-word false rejects, which make the device feel broken in exactly the moments a user is trying hardest to use it.
- A wake-word engine to select, tune, and validate, on hardware whose runtime compatibility is itself unvalidated (AS-01).

**Full-duplex costs:**
- Acoustic echo cancellation, so the device does not hear and transcribe its own speaker output. On a small chassis with the microphone near the speaker, this is genuinely hard.
- Concurrent capture and playback on a Pi audio stack that we have not yet validated (AS-04, OQ-03).
- Turn-taking arbitration — deciding when an overlapping utterance is an interruption versus a backchannel.

Meanwhile, none of the latency characteristics are known. Azure Speech and model latency from this device on this network are **unmeasured** (NA-01), and blocked by UD-09. Designing a full-duplex turn-taking policy against unmeasured latency is designing against a guess.

We also already have a suitable physical trigger. PiDog exposes dual capacitive touch sensors (EV-17, `pidog.py:235` — `DualTouch('D2', 'D3')`), so a touch-to-talk control needs no additional hardware.

## Decision

**The first release is push/touch-to-talk and half-duplex.**

### Push/touch-to-talk

Capture begins only on an explicit user trigger — a button or PiDog's capacitive touch (FR-01). Not on a wake word. Not on ambient sound. Not on a timer.

### Half-duplex by construction

The microphone is open **only** in the `Listening` state (ST-06). This is enforced by the turn state machine, not by convention. There is no code path in which capture and playback are concurrent, so there is nothing for echo cancellation to correct.

### Barge-in via generation IDs

Half-duplex does not mean uninterruptible. Pressing the talk control during `Speaking` or `Thinking` performs a full interruption:

| Step | Action |
|------|--------|
| 1 | Talk control pressed during `Speaking` or `Thinking`. |
| 2 | A new generation ID is issued; the previous one is invalidated **atomically**. |
| 3 | Playback stops; the synthesis buffer is discarded. |
| 4 | All arbiter commands tagged with the old generation are cancelled; in-flight motion unwinds to neutral ([ADR-0002](ADR-0002-deterministic-motion-arbiter.md)). |
| 5 | Capture starts for the new generation. |
| 6 | Any late cloud response for the old generation is **discarded on arrival**. |

The generation ID is the single mechanism binding speech and motion cancellation together (FR-08). Without it, the speech and motion subsystems would need to coordinate directly — precisely the coupling this architecture avoids — and step 6 would not exist at all.

Step 6 deserves emphasis: it prevents the failure where a slow Azure reply for an abandoned turn arrives after the user has started a new one, and the device speaks the wrong answer over the new question while performing the wrong gesture. This is the defect the whole mechanism exists to prevent.

### What this buys us structurally

| Problem | Status under this decision |
|---------|---------------------------|
| Acoustic echo cancellation | **Eliminated.** Capture and playback are never concurrent. |
| Wake-word false accept | **Eliminated.** There is no wake word. |
| Wake-word false reject | **Eliminated.** |
| Always-open microphone privacy posture | **Eliminated.** The mic opens only in `Listening`. |
| Turn-taking arbitration | **Reduced** to one unambiguous rule: the talk control wins. |

Four hard problems removed by one scoping decision, and the removal is structural rather than a matter of care.

### Deferral, not abandonment

Wake word (NG-03) and full duplex (NG-04) are explicit non-goals **for the first release**. Nothing in this architecture forecloses them:

- The state machine gains states; it is not rewritten.
- Generation-ID cancellation is exactly the mechanism full-duplex barge-in needs.
- The persona model, arbiter, adapter, and broker are all unaffected.

The right time to revisit is after M2 gives us measured latency (M2-D7) and M5 gives us measured real-hardware latency (M5-D6). Then a full-duplex design can be made against numbers instead of hopes.

## Alternatives considered

| Alternative | Why rejected |
|-------------|--------------|
| **Always-on wake word, half-duplex** | Removes the physical trigger's privacy benefit and adds wake-word false accept/reject, while retaining most of the complexity. The worst trade in the set: real cost, little gain. |
| **Always-on wake word, full duplex** | Adds every problem at once — echo cancellation, false accepts, concurrent audio on an unvalidated stack, turn-taking — before a single turn has been proven to work end to end. |
| **Push-to-talk, full duplex** | Full duplex without a wake word is largely pointless: the user must already touch the device to speak, so there is no overlap to handle. Pays the echo-cancellation cost for almost no benefit. |
| **Voice-activity detection instead of a trigger** | An always-open microphone with extra steps. Same privacy posture problem, plus VAD false triggers on television, conversation, and household noise. |
| **No barge-in — let each reply finish** | Makes a long or wrong reply unbearable, and is the single most common complaint about voice assistants. Barge-in is not optional; it is why the generation-ID design exists. |
| **Barge-in for speech only, letting motion finish** | Produces a device that stops talking but keeps performing the gesture for the abandoned turn. Uncanny, and confusing about what state the device is in. Motion and speech must cancel together. |

## Consequences

### Positive

- Four hard problems are removed structurally rather than mitigated.
- The privacy posture is simple and explainable: the microphone opens only when you touch it.
- Interruption still works, and works completely — speech, motion, and late responses.
- The physical trigger already exists on the hardware (EV-17); no new components are needed.
- Latency requirements are relaxed, because the user knows the device is thinking and is not waiting for it to notice them.

### Negative

- The user must touch the device to speak. For a companion robot this is a genuine loss of magic and it is accepted deliberately.
- No hands-free operation, which excludes some legitimate use cases.
- The device cannot respond to being addressed naturally from across the room.
- If UD-06's offline answer or user feedback later demands hands-free, this decision must be revisited — with the benefit of measured latency, which is the point.

### Neutral

- The `Listening`-only microphone rule (ST-06) is the kind of invariant that is easy to state, easy to test, and easy to verify in review.

## Validation

| ID | Acceptance criterion | Milestone |
|----|---------------------|-----------|
| AC-AUD-01 | Capture starts only on an explicit trigger; the mic is never open outside `Listening` | M4 |
| AC-AUD-04 | A complete turn runs end to end in simulation | M4 |
| AC-AUD-05 | Barge-in stops playback **and** cancels the linked motion generation; motion unwinds to neutral | M4 |
| AC-AUD-06 | An NFR-02 barge-in stop-latency target is set from measurement | M4 |
| AC-CLOUD-02 | A late response for an invalidated generation is discarded and never spoken | M2 |
| AC-STATE-01 | Every state transition is exercised; no undefined transition exists | M3 |
| AC-M2-01 | An NFR-01 latency target is set from M2 measurement, not from vendor claims | M2 |
| AC-HIL-02 | Real-hardware latency is measured and any divergence from M2 is explained | M5 |

## Open items

- **UD-03** — is there a physical mute control? It would complement the talk control and strengthen the privacy story. Part of the e-stop/cutoff/mute question.
- **UD-06** — offline behavior. Determines what the talk control does while `Degraded`.
- **UD-08** — languages and disclosure, which affect the Speech locale and the session-start interaction.
- **UD-09** — latency expectations. Unmeasured today; the basis on which wake word and full duplex would be reconsidered.
- **AS-04** — that audio devices are selectable and stable under the Pi audio stack. **Not assumed.** Validated in M2, with OQ-03 selecting ALSA, PulseAudio, or PipeWire.
- **OQ-04** — streaming versus batch synthesis for first-syllable latency.

## Constraint restated

Nothing in this ADR authorizes any modification under `exlibs/`. The capacitive touch trigger is used by **reading** PiDog's `DualTouch` through the hardware adapter ([ADR-0001](ADR-0001-pi-local-hardware-adapter.md)), never by editing it.
