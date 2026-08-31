# ADR-0003 — Immutable, Versioned, Modular Personas

| Field | Value |
|-------|-------|
| **Status** | 🟦 **PROPOSED** — not accepted until the dual approval gate closes |
| **Date** | 2026-08-28 |
| **Owner** | Architect |
| **Deciders** | Dave Davis (approval gate) |
| **Supersedes** | — |
| **Related** | [ADR-0002](ADR-0002-deterministic-motion-arbiter.md), [ADR-0005](ADR-0005-privacy-defaults-camera-disabled.md) |
| **Related decisions** | [UD-04](../system-architecture.md#4-user-decision-register-ud-01--ud-10) (bystanders), [UD-08](../system-architecture.md#4-user-decision-register-ud-01--ud-10) (languages, personas, disclosure) |

> **Approval gate:** This ADR describes a recommendation. It authorizes nothing. Implementation remains BLOCKED until Dave Davis explicitly approves **both** `system-architecture.md` **and** `project-plan.md`. Approval of one alone, silence, or requested revisions does not open the gate.

## Context

The persona is the product. It is what makes the device feel like a companion rather than a speaker with legs. It is also the part most likely to change frequently, be edited by non-engineers, and be reviewed for safety.

Three forces pull on the design:

1. **Personas will change often.** Prompt wording, voice, verbosity, and gesture selection are all tuning knobs. If changing them requires a code change, they will not be tuned.
2. **Personas carry safety weight.** A persona declares which gestures it may request and what content-safety strictness applies. Rai reviews personas. A review is only meaningful if what was reviewed is exactly what runs.
3. **Personas interact with concurrency.** A persona switch during an active turn could mix one persona's prompt with another's voice and a third's gesture vocabulary. That is a correctness bug that produces a confusing, potentially unsafe result.

The naive approach — a mutable persona object with fields you set at runtime — fails all three.

## Decision

**A persona is a versioned, immutable bundle of five separable concerns. It is data, not code.**

### The five facets

| Facet | Contains | Consumed by |
|-------|----------|-------------|
| **Prompt** | System prompt, style guidance, refusal style, disclosure phrasing | Broker Client, via L3 conditioning |
| **Voice** | Speech voice identifier, locale, prosody/rate/pitch adjustments | Speech Client |
| **Behavior** | Conversation policy — turn length, formality, verbosity, topic preferences, forbidden topics | Turn State Machine |
| **Motion vocabulary** | The **explicit allowlist** of named gestures this persona may request, from the adapter's supported set | Gesture Validator, feeding [ADR-0002](ADR-0002-deterministic-motion-arbiter.md) |
| **Permissions** | Capability grants — may it request motion at all, may it use the camera if ever enabled, what content-safety strictness tier applies | Enforced at L3 before any downstream call |

Separating these five is what makes the model useful rather than decorative. A "calm assistant" and an "excitable puppy" differ in all five independently: you can give the calm persona a warm voice without giving it the puppy's jumping gestures, and you can tighten the puppy's permissions without touching its prompt.

### Immutability and versioning

Every bundle carries a `persona_id` and a `version`. Once loaded, the in-memory persona object is **immutable for the life of the process**. Editing a persona means shipping a new version, never mutating a live one.

This buys three concrete things:

- **Attribution.** Every telemetry event and log line carries `persona_id@version`. When behaviour changes, we know exactly which bundle produced it.
- **Concurrency safety.** A switch cannot half-apply. The turn completes under the persona it started with, or is cancelled outright.
- **Durable review.** Rai reviews a bundle at a specific version. Immutability means that review stays valid for exactly the artifact reviewed.

### Validation, fail-closed

Bundles are validated at load time against a schema, and validation fails **closed** with a defined fallback:

| Failure | Behavior |
|---------|----------|
| Fails schema validation | Rejected. Not loaded. Startup error logged. |
| Requests a gesture not in the adapter's supported set | **Rejected at load.** A hard stop, not a runtime surprise. |
| Requests a permission not granted by device config | Rejected at load. |
| Requests an unavailable Speech voice | Loads with the configured default voice and a loud warning. Degraded, not fatal. |
| The **default** persona fails to load | The built-in **minimal safe persona** activates: neutral voice, **no motion permission**, plain refusal style, disclosure on. The device still works and is still honest. |
| **No** persona can be loaded at all | The system stays in `Inhibited` and refuses to enter `Idle`. It does not run persona-less. |

The minimal safe persona is not decoration. It is the reason a malformed persona file cannot brick the device or, worse, produce a running device with no behavioural constraints and full motion permission.

Note the asymmetry: an unavailable **voice** degrades gracefully because the failure is cosmetic; an unsupported **gesture** or an ungranted **permission** is a hard rejection because the failure is a safety boundary.

### Adding and switching

**Adding** is: drop a new versioned bundle in the persona directory, restart or trigger a registry reload. Zero core code change (FR-07). An invalid bundle is rejected without affecting the running persona.

**Switching** is: request a switch by `persona_id`; the session manager completes or cancels the current turn, releases the current persona, and applies the new one **at the next turn boundary** (FR-06). Switching never lands mid-turn.

### Disclosure is above personas

The AI-disclosure policy sits at L4 **above** the persona prompt. A persona may style the disclosure; a persona may **not** suppress it or deny that the system is an AI (PR-07). This is structural, not a prompt instruction, so no prompt text — authored or injected — can override it.

## Alternatives considered

| Alternative | Why rejected |
|-------------|--------------|
| **Persona as a single prompt string** | Collapses five independent concerns into one. You cannot give a persona a different voice without rewriting its prompt, and there is nowhere to declare a motion allowlist or a permission set — so [ADR-0002](ADR-0002-deterministic-motion-arbiter.md)'s validator has nothing to validate against. |
| **Persona as a Python class** | Makes personas code, so adding one is a code change and a deployment. Also makes them arbitrarily powerful — a persona could call anything — which destroys the permission model. |
| **Mutable persona with runtime setters** | Breaks attribution (which version produced this?), breaks concurrency safety (half-applied switches), and breaks review durability (what Rai reviewed is not what ran). |
| **Hot-swap mid-turn** | Produces turns that mix one persona's prompt with another's voice and gesture vocabulary. Confusing at best, unsafe at worst. |
| **Fail-open validation — load what parses, ignore the rest** | A persona missing its motion vocabulary would default to *something*. Every "something" here is either useless or dangerous. Fail-closed with a minimal safe fallback is the only defensible choice. |
| **No fallback — refuse to start on a bad default persona** | Tempting, and safer in one narrow sense, but it makes a typo in a config file into a bricked device. The minimal safe persona gives the same safety with a recoverable failure mode. |

## Consequences

### Positive

- Personas can be authored, reviewed, and shipped without engineering involvement.
- The motion vocabulary facet is what makes [ADR-0002](ADR-0002-deterministic-motion-arbiter.md)'s gesture validation possible at all.
- `persona_id@version` in telemetry makes behavioural regressions attributable.
- Rai's review of a bundle version stays valid indefinitely.
- A broken persona degrades to a safe, honest, motion-restricted device rather than an undefined one.

### Negative

- Schema versioning and migration become a real maintenance concern as the schema evolves (OQ-06).
- Immutability means a persona tweak requires a reload, not a live edit. Slower iteration during authoring.
- Five facets is more structure than a small persona needs, which is a real authoring cost for simple cases.

### Neutral

- The gesture-rejection metric (§13.2) becomes the natural feedback loop for persona authors: a persona whose prompt keeps requesting gestures outside its vocabulary needs its prompt or its vocabulary adjusted.

## Validation

| ID | Acceptance criterion | Milestone |
|----|---------------------|-----------|
| AC-PER-01 | A new persona is added by dropping a bundle, with zero core code change | M3 |
| AC-PER-02 | A switch takes effect at the next turn boundary, never mid-turn | M3 |
| AC-PER-03 | An invalid bundle is rejected at load and never becomes active | M3 |
| AC-PER-04 | A bundle requesting an unsupported gesture or ungranted permission is rejected **at load**, not at runtime | M3 |
| AC-PER-05 | If the default persona fails, the minimal safe persona activates; the device stays honest and motion-restricted | M3 |
| AC-PER-06 | Persona objects are immutable after load | M3 |
| AC-MOT-02 | An out-of-vocabulary gesture is rejected, telemetry emitted, reply still spoken | M3 |
| AC-RAI-01 | Disclosure cannot be suppressed by any persona prompt | M4 |

## Open items

- **UD-08** — which languages, which personas ship, and the exact disclosure wording and trigger. Sets M3-D10 and M7-D5 scope.
- **UD-04** — bystanders and children, which sets the default content-safety strictness tier. Strictest tier applies while this is open.
- **OQ-06** — the bundle schema version and migration strategy. Resolved in M3-D7.

## Constraint restated

Nothing in this ADR authorizes any modification under `exlibs/`. The gesture vocabulary is derived by **reading** PiDog's `preset_actions` (EV-18), never by editing it.
