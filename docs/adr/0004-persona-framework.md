# ADR 0004: Declarative persona framework

## Status

Accepted

## Context

Sparky now needs multiple personas. A persona must affect more than model wording: it must shape voice, movement, vision/sensor reactions, sound effects, and behavior style while preserving global robot safety constraints. The first two personas should prove the framework rather than become one-off branches in the planner.

Existing constraints still apply:

- All source and runtime content belong under `/src`.
- The Pi calls Azure AI and Speech only through the keyless relay path.
- Hardware-facing code must remain testable with mocked adapters.
- README and architecture docs must stay current with meaningful changes.

## Decision

Use a **declarative-first persona framework with a constrained code extension point**.

Persona definitions will be versioned manifests under the device source tree, with shared schema and validation assets under shared source code:

```text
src/device/sparky_device/personas/       # persona manifests and optional assets
src/shared/sparky_contracts/personas/    # schema, DTOs, validators, test fixtures
```

Each manifest defines:

- persona identity, display name, version, and capabilities
- LLM system-prompt intent and behavioral rules
- TTS voice, style, rate, pitch, volume, and fallback voice
- movement profile: gait, speed, posture idioms, idle behaviors, and energy level
- reaction mappings for normalized vision/sensor events
- approved sound effects and RGB idioms
- persona-specific safety notes that may only tighten, never weaken, global safety policy

Core runtime code loads validated manifests through a persona registry. The active persona is switched at runtime by voice intent, interactive command mode, or programmatic API. Switching hot-swaps the active persona without restarting the process, but only after a safe-state transition: cancel/pause in-flight conversation, stop audio playback, stop or settle motion, clear transient reaction work, then activate the new persona. Conversation memory is persona-scoped by default.

The extension point is intentionally narrow: future code hooks may add new typed reaction handlers or effect adapters, but persona authors should normally add a new manifest and fixtures only. A third persona with no core code changes is the framework acceptance test.

## Alternatives considered

### Code-only persona plugins

Rejected. Code-only plugins maximize flexibility but make persona review harder, encourage hidden behavior branches, and raise the risk that a persona bypasses global safety or hardware limits.

### Single prompt/personality setting

Rejected. This would not exercise movement, voice, reactions, sound effects, or safety validation. It would also make starter personas superficial prompt variants.

### Cloud-hosted persona configuration only

Rejected for the first release. Cloud distribution may be useful later, but the Pi must have deterministic startup behavior, offline/degraded fallback, source-reviewed manifests, and repeatable tests.

## Consequences

- Persona authors get a simple content-first workflow.
- The registry, validator, TTS request shaping, planner, and action executor need persona-aware contracts.
- Global safety remains centralized and higher priority than persona behavior.
- Tests must cover schema validation, unsupported voice IDs, safe movement ranges, prompt ordering, reaction mappings, switching, and third-persona extensibility.
- Docs and runbooks must explain how to author, validate, switch, and troubleshoot personas.
