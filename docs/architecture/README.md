# Sparky — Architecture and Planning Package

> Planning documentation for a persona-driven robotic companion on PiDog-class Raspberry Pi hardware with Azure-hosted AI and Azure Speech.

| Field | Value |
|-------|-------|
| **Project** | sparky |
| **Requested by** | Dave Davis |
| **Package owner** | Architect (Lead & Software Architect) |
| **Package status** | **DRAFT — AWAITING APPROVAL** |
| **Implementation gate** | 🔒 **BLOCKED** |
| **Last updated** | 2026-08-28 |

---

## 🔒 Implementation Gate

**No application or product code may be written.** Implementation is BLOCKED until **Dave Davis explicitly approves BOTH**:

1. [`system-architecture.md`](system-architecture.md) — ❌ **not approved**
2. [`project-plan.md`](project-plan.md) — ❌ **not approved**

| Event | Gate result |
|-------|-------------|
| Approval of `system-architecture.md` alone | 🔒 Still blocked |
| Approval of `project-plan.md` alone | 🔒 Still blocked |
| Silence, no response, or lapsed time | 🔒 Still blocked |
| "Looks good, but change X" / requested revisions | 🔒 Still blocked — returns to planning |
| Approval by anyone other than Dave Davis | 🔒 Still blocked |
| **Explicit approval of both documents by Dave Davis** | 🔓 **Open** — M1 may start, subject to per-milestone entry gates |

Opening the gate authorizes **M1 only**. Every milestone has its own entry gate, and several are independently blocked by unresolved user decisions. See [project-plan.md §0](project-plan.md#0-dual-approval-gate).

### Hard constraint — `exlibs` is read-only

Nothing in this package authorizes any modification to `exlibs/pidog`, `exlibs/robot-hat`, or `exlibs/vilib` — during planning, during implementation, or ever. All findings about those libraries come from reading them.

---

## Package Contents

| Document | Purpose | Status |
|----------|---------|--------|
| [`README.md`](README.md) | This index — package contents, review status, approval gate | Current |
| [`system-architecture.md`](system-architecture.md) | Goals and non-goals, requirements, UX, assumptions, read-only `exlibs` assessment, architecture and diagrams, persona architecture, Azure approach, hardware abstraction and motion safety, audio and concurrency, privacy and RAI, observability and cost, risks, implementation readiness | ❌ Awaiting approval |
| [`project-plan.md`](project-plan.md) | Phases M0–M7, dependencies, owners, deliverables, acceptance criteria, traceability matrix, test/HIL progression, risks, evidence, dual approval gate | ❌ Awaiting approval |
| [`decisions/`](decisions/) | Six architecture decision records | 🟦 All proposed |

### Architecture Decision Records

Every ADR in `decisions/` is indexed here.

| ADR | Title | Status | Summary |
|-----|-------|--------|---------|
| [ADR-0001](decisions/ADR-0001-pi-local-hardware-adapter.md) | Pi-Local Hardware Adapter | 🟦 Proposed | All `exlibs` access goes through one adapter. No module outside it imports `pidog`, `robot_hat`, or `vilib`. Semantic operations only. Pi and simulator implementations are interchangeable. Contains the robot-hat `2.3.6`-vs-`2.5.x` skew in one place. |
| [ADR-0002](decisions/ADR-0002-deterministic-motion-arbiter.md) | Deterministic Motion Arbiter, and No Direct LLM Actuator Access | 🟦 Proposed | One component holds sole actuator authority. Semantic allowlisted commands with TTL, cancellation, watchdog, startup inhibit, and an independent latched e-stop. The language model never commands actuators. |
| [ADR-0003](decisions/ADR-0003-immutable-versioned-personas.md) | Immutable, Versioned, Modular Personas | 🟦 Proposed | A persona is a versioned immutable data bundle of five separable facets — prompt, voice, behavior, motion vocabulary, permissions. Fail-closed validation with a minimal safe fallback. Add by dropping a bundle; switch at turn boundaries. |
| [ADR-0004](decisions/ADR-0004-azure-broker-identity-boundary.md) | Azure Broker and Identity Boundary | 🟦 Proposed | The broker is the secure default and the only Azure endpoint the device knows. Per-device mTLS/X.509 to the broker; managed identity within Azure. Direct short-lived-token Speech remains a labelled experiment, not a shipping path. |
| [ADR-0005](decisions/ADR-0005-privacy-defaults-camera-disabled.md) | Privacy Defaults and Camera Disabled | 🟦 Proposed | No raw-audio retention, no transcript retention, camera disabled, and the Vilib unauthenticated `0.0.0.0:9000` service never started. Four independent controls, not one config flag. |
| [ADR-0006](decisions/ADR-0006-push-to-talk-half-duplex.md) | Push-to-Talk and Half-Duplex for the First Release | 🟦 Proposed | Push/touch-to-talk, half-duplex, microphone open only in `Listening`. Generation IDs cancel speech, linked motion, and late cloud responses on barge-in. Wake word and full duplex are deferred, not foreclosed. |

---

## Diagrams

All five required diagrams are in [`system-architecture.md`](system-architecture.md), as Mermaid:

| Diagram | Type | Location |
|---------|------|----------|
| System context | `flowchart LR` | [§7.2](system-architecture.md#72-system-context-diagram) |
| Components | `flowchart TB` | [§7.3](system-architecture.md#73-component-diagram) |
| End-to-end audio/LLM/persona/motion data flow | `flowchart LR` | [§7.4](system-architecture.md#74-end-to-end-data-flow) |
| Key interaction and barge-in sequence | `sequenceDiagram` | [§7.5](system-architecture.md#75-key-interaction-and-barge-in-sequence) |
| Runtime state transitions | `stateDiagram-v2` | [§7.6](system-architecture.md#76-runtime-state-transitions) |

Supporting diagrams: persona load and fallback ([§8.4](system-architecture.md#84-adding-and-switching-personas)), phase overview and dependency graph ([project-plan §3](project-plan.md#3-phase-overview), [§5](project-plan.md#5-dependencies)), test progression ([project-plan §7](project-plan.md#7-test-and-hil-progression)).

---

## ⚠️ Ten Unresolved User Decisions

**All ten are open and owned by Dave Davis.** Full detail, including the interim planning assumption used for each, is in [system-architecture.md §4](system-architecture.md#4-unresolved-user-decision-register-ud-01--ud-10). Milestone blocking is in [project-plan.md §1](project-plan.md#1-decision-register-reference).

| # | Decision | Blocks | Referenced in |
|---|----------|--------|---------------|
| **UD-01** | **Exact hardware** — Pi model, board revision, mic, speaker, power | M1 exit, M5 entry | [ADR-0001](decisions/ADR-0001-pi-local-hardware-adapter.md) |
| **UD-02** | **Stationary vs walking v1** | M3 scope, M6 entry | [ADR-0001](decisions/ADR-0001-pi-local-hardware-adapter.md), [ADR-0002](decisions/ADR-0002-deterministic-motion-arbiter.md) |
| **UD-03** | **Physical e-stop / power cutoff / mute** | 🔒 **M5 entry — hard block** | [ADR-0002](decisions/ADR-0002-deterministic-motion-arbiter.md), [ADR-0006](decisions/ADR-0006-push-to-talk-half-duplex.md) |
| **UD-04** | **Children, guests, bystanders** | M4 exit, M7 entry | [ADR-0003](decisions/ADR-0003-immutable-versioned-personas.md), [ADR-0005](decisions/ADR-0005-privacy-defaults-camera-disabled.md) |
| **UD-05** | **Camera need** | M7 entry | [ADR-0005](decisions/ADR-0005-privacy-defaults-camera-disabled.md) |
| **UD-06** | **Offline behavior** | M4 scope | [ADR-0006](decisions/ADR-0006-push-to-talk-half-duplex.md) |
| **UD-07** | **Retention, deletion, memory** | M4 exit, M7 entry | [ADR-0005](decisions/ADR-0005-privacy-defaults-camera-disabled.md) |
| **UD-08** | **Languages, personas, disclosure** | M3 scope, M4 exit, M7 | [ADR-0003](decisions/ADR-0003-immutable-versioned-personas.md), [ADR-0006](decisions/ADR-0006-push-to-talk-half-duplex.md) |
| **UD-09** | **Azure budget, regions, tenant, subscription, latency** | 🔒 **M2 entry — hard block** | [ADR-0004](decisions/ADR-0004-azure-broker-identity-boundary.md), [ADR-0006](decisions/ADR-0006-push-to-talk-half-duplex.md) |
| **UD-10** | **Broker mandatory vs direct Speech evaluation** | M2 scope | [ADR-0004](decisions/ADR-0004-azure-broker-identity-boundary.md) |

> **The two most expensive to leave open:** UD-09 blocks M2 entry outright, and UD-03 blocks M5 entry outright. M1–M4 can complete without UD-03, at which point the project stalls at a wall it could have seen coming.

---

## Review Status

| Reviewer | Status | Detail |
|----------|--------|--------|
| **Fact Checker** | ✅ **APPROVE (advisory)** | 21 evidence items (EV-01 to EV-21) verified against `exlibs` with file and line citations. EV-20's citation defect (the OpenCV import is at `vilib.py:21`, not `:70`; the Flask import citation at `:25` was already correct) was corrected in the package and confirmed applied at re-review. **Open validation items:** runtime compatibility on Bookworm 64-bit / Python 3.11, Azure SDK and API versions, quotas, and end-to-end latency. See [system-architecture.md §5.2](system-architecture.md#52-verified-facts-from-read-only-exlibs-assessment) and [project-plan.md §8.1](project-plan.md#81-fact-checker-position). |
| **Rai** | 🟡 **AMBER — APPROVE WITH CONDITIONS** | No planning blockers. Five implementation blockers remain: RAI-B1 no specified physical e-stop (UD-03), RAI-B2 undefined bystander/child model (UD-04), RAI-B3 undefined retention policy (UD-07), RAI-B4 Vilib unauthenticated service in the dependency tree (UD-05), RAI-B5 unratified credential model (UD-10). Three of five are user decisions that engineering cannot close. Revised camera/Vilib closure wording confirmed at re-review; verdict and blockers unchanged. See [system-architecture.md §12.2](system-architecture.md#122-rai-status). |
| **Reliability** | ✅ **APPROVE WITH CONDITIONS** | Initial review rejected the package specifically for unsupported, pre-asserted reviewer provenance — a provenance-integrity defect, not a technical one. Reliability's own assessment found the underlying test-readiness content (acceptance criteria, simulation/HIL strategy, failure-mode coverage) sound on the merits. Provenance was corrected, and a genuine Reliability re-review of the corrected package returned APPROVE WITH CONDITIONS REL-C1 to REL-C6, now confirmed and embedded in the plan. See [project-plan.md §8.3](project-plan.md#83-reliability-position). |
| **Architect** | ✅ Package assembled and coherence-reviewed | Owns integration, interfaces, ADRs, and the readiness recommendation. |
| **Dave Davis** | ❌ **Approval not given for either document** | The gate. |

---

## Evidence Discipline

Every claim in this package carries one of five labels. This is what lets a reader tell a fact from a plan from a guess.

| Label | Meaning | Where |
|-------|---------|-------|
| ✅ **VERIFIED** | Directly observed in `exlibs` with a file and line citation | [§5.2](system-architecture.md#52-verified-facts-from-read-only-exlibs-assessment) — EV-01 to EV-21 |
| 🟦 **RECOMMENDATION** | An architecture choice with an ADR | [decisions/](decisions/) |
| 🟨 **ASSUMPTION** | Believed, load-bearing, unverified — each with a validation milestone | [§5.3](system-architecture.md#53-load-bearing-assumptions) — AS-01 to AS-09 |
| 🧪 **EXPERIMENT** | Deliberately unproven, time-boxed, with an abandon criterion | [§9.2](system-architecture.md#92-the-direct-speech-experiment) |
| ⛔ **NOT ASSERTED** | Something a reader might expect us to promise, which we deliberately do not | [§5.4](system-architecture.md#54-deliberately-not-asserted) — NA-01 to NA-07 |

**Deliberately not asserted anywhere in this package:** any Azure latency figure, quota, throughput guarantee, regional availability guarantee, cost figure, SDK or API version, or any claim that the supplied libraries run on Raspberry Pi OS Bookworm 64-bit with Python 3.11. Bookworm/3.11 is an **initial validation target**, not established compatibility. Each of these becomes a measured number at a named milestone.

---

## Reading Order

**For approval:** this README → [system-architecture.md §0 and §4](system-architecture.md#0-approval-gate--read-first) → [project-plan.md §0 and §1](project-plan.md#0-dual-approval-gate) → the six ADRs.

**For engineering context:** [system-architecture.md §6](system-architecture.md#6-read-only-exlibs-assessment) (`exlibs` assessment) → [§7](system-architecture.md#7-architecture) (architecture and diagrams) → the ADRs → [project-plan.md §4](project-plan.md#4-milestones) (milestones) → [§6](project-plan.md#6-requirements-traceability-matrix) (traceability).

**For safety and privacy review:** [system-architecture.md §10](system-architecture.md#10-hardware-abstraction-and-motion-safety) → [§12](system-architecture.md#12-privacy-and-responsible-ai) → [ADR-0002](decisions/ADR-0002-deterministic-motion-arbiter.md) → [ADR-0005](decisions/ADR-0005-privacy-defaults-camera-disabled.md) → [project-plan.md §7](project-plan.md#7-test-and-hil-progression).

---

## What Happens Next

1. **Dave Davis reviews** both documents and the six ADRs.
2. **Dave Davis resolves** as many of UD-01 to UD-10 as possible. UD-09 and UD-03 are the highest-value.
3. **Dave Davis explicitly approves both documents**, or requests revisions — which returns the package to planning with the gate still closed.
4. On dual approval, **M1 begins**: platform validation and the hardware adapter. Not M2 (blocked by UD-09), not M5 (blocked by UD-03).

---

**Status: DRAFT — AWAITING APPROVAL. Implementation is BLOCKED until Dave Davis explicitly approves BOTH `system-architecture.md` AND `project-plan.md`.**
