# Squad Decisions

## Active Decisions

No decisions recorded yet.

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction

### 2026-08-28T13:50:31.473-04:00: Approved descriptive Squad roster
**By:** Dave Davis
**What:** Phase 2 initializes Architect, Robotics, Speech, AzureAI, and Reliability as the project agents, with Scribe, Ralph, Rai, and Fact Checker as always-on built-ins. Names use the descriptive universe.
**Why:** The approved roster covers architecture leadership, robotics hardware, speech/audio, Azure-hosted AI, and reliability while retaining Squad's persistent governance roles.

### 2026-08-28T13:50:31.473-04:00: Architecture and project plan are hard implementation gates
**By:** Dave Davis
**What:** No application/product code may begin until the user explicitly approves both the architecture documentation and the project plan. Approval of only one deliverable does not authorize implementation.
**Why:** The project requires an agreed modular architecture, safety boundaries, integration strategy, acceptance criteria, and phased plan before implementation risk is accepted.

### 2026-08-28T13:50:31.473-04:00: External-library assessment is read-only
**By:** Dave Davis
**What:** Assessment of `exlibs/pidog`, `exlibs/robot-hat`, and `exlibs/vilib` is limited to read-only compatibility and API analysis. The assessment must not modify application/product code or any files under `exlibs/`.
**Why:** Architecture planning needs evidence from the bundled libraries without creating implementation changes or altering external dependencies.

### 2026-08-28T13:50:31.473-04:00: Planning deliverables and review chain
**By:** Architect
**What:** Specialist assessments feed Architect, who assembles architecture documentation and the project plan. Planning must cover requirements/non-goals; exlibs compatibility; architecture decisions; system-context, component, data-flow, sequence, and state diagrams; persona extension/switching; Azure AI and Speech; hardware safety/abstraction; risks/assumptions/open questions; milestones/dependencies; acceptance criteria; testing/reliability; and implementation readiness. Fact Checker verifies external/API claims, Rai reviews safety/responsibility, and Reliability reviews acceptance/test readiness before user approval.
**Why:** A single integration owner and explicit independent review stages make the final approval package coherent, evidence-based, safe, and testable.

### 2026-08-28: PiDog planning package written; implementation still gated on dual approval
**By:** Architect
**What:** The complete architecture and planning package is written to `docs/architecture/` — `README.md`, `system-architecture.md`, `project-plan.md`, and six ADRs under `docs/architecture/decisions/` (Pi-local hardware adapter; deterministic motion arbiter with no direct LLM actuator access; immutable/versioned modular personas; Azure broker and identity boundary; privacy defaults with camera disabled; push-to-talk half-duplex first release). All six ADRs are PROPOSED, not accepted. Implementation remains BLOCKED until Dave Davis explicitly approves BOTH `system-architecture.md` AND `project-plan.md`; approval of one alone, silence, or requested revisions does not open the gate. Ten unresolved user decisions (UD-01 to UD-10) are recorded as a numbered register cross-referenced from README, architecture, plan, and the relevant ADRs, and each blocking milestone carries its own entry gate so that approval alone cannot start blocked work.
**Why:** The ceremony requires a single integrated package with evidence, diagrams, acceptance criteria, and an explicit gate before implementation risk is accepted. Separating verified evidence from recommendations, assumptions, and experiments keeps the approval decision honest, and per-milestone gates keep the ten open decisions visible rather than silently assumed.

### 2026-08-28T14:48:03.102-04:00: Planning package revised for reviewer-provenance integrity; pending Reliability re-review
**By:** Scribe (independently assigned revision owner; Architect locked out of this revision)
**What:** Reliability's initial review of `docs/architecture/` returned REJECT, specifically for unsupported, pre-asserted reviewer provenance — the package had asserted reviewer sign-off/approval status not genuinely earned through the actual review process — while finding the underlying technical planning content sound on the merits. The package has been revised to replace pre-asserted claims with the actual persisted verdicts: Fact Checker ✅ APPROVE (advisory), with an EV-20 citation correction (`vilib.py:21` for the OpenCV import, not `:70`) and runtime/SDK/quota/latency still listed as open validation items; Rai 🟡 Amber / APPROVE WITH CONDITIONS, no planning blocker, five implementation blockers remain; Reliability's status is now recorded as revised and **pending genuine re-review**, not approved. Vilib/camera wording was also corrected so the ban on the unauthenticated Flask/MJPEG service reads as unconditional, while camera need (UD-05) is stated as leading only to a possible, separately designed authenticated camera path — the broader camera-privacy question is not marked resolved. No technical architecture, ADR content, milestone plan, diagrams, or the ten-item decision register were altered; no application/product code or `exlibs` files were touched.
**Why:** Provenance integrity is a precondition for a valid approval package — reviewer sign-off must reflect reviews that actually occurred. Correcting the claims without touching the underlying technical content preserves the work already reviewed as sound while making the package honest about what has, and has not, been genuinely re-reviewed.

### 2026-08-28T14:48:03.102-04:00: Planning package review chain complete; implementation remains gated on Dave Davis's dual approval alone
**By:** Scribe (finalization; no reviewer authored this entry for their own verdict)
**What:** All three re-reviews of the provenance-corrected `docs/architecture/` package have returned genuine final verdicts: Fact Checker ✅ APPROVE (advisory, unchanged — EV-20 citation correction confirmed applied); Rai 🟡 Amber / APPROVE WITH CONDITIONS (confirmed unchanged — no planning blocker, five implementation blockers RAI-B1–RAI-B5 remain, all tracing to unresolved user decisions); Reliability ✅ APPROVE WITH CONDITIONS REL-C1–REL-C6 (a genuinely earned approval, superseding its earlier provenance-only REJECT). `README.md`, `system-architecture.md`, and `project-plan.md` were updated to remove all remaining "pending Reliability re-review" language and reflect these three outcomes; no technical recommendation, diagram, ADR decision, milestone, or UD-01–UD-10 entry was altered.
**Why:** With all reviewer verdicts genuinely earned and persisted, the review chain established at project start is now complete. This does not change the implementation gate: per the standing dual-approval decision above, implementation remains BLOCKED until Dave Davis explicitly approves both `system-architecture.md` and `project-plan.md` — a review-complete package is a precondition for that approval, not a substitute for it.

### 2026-08-28T14:48:03.102-04:00: exlibs assessment findings that constrain the architecture
**By:** Architect
**What:** Read-only assessment established, with file citations: supplied versions are pidog 1.3.13, robot-hat 2.3.6, vilib 0.3.18; PiDog's README directs installing robot-hat branch 2.5.x; PiDog's `llm.py`, `stt.py`, and `voice_assistant.py` import `robot_hat.llm`, `robot_hat.stt`, and `robot_hat.voice_assistant`, none of which exist in the supplied robot_hat tree, so those imports fail; vilib binds an unauthenticated Flask MJPEG service to `0.0.0.0:9000` and sets Flask debug mode at import; PiDog clamps head angles but not leg or tail angles, runs three unbounded daemon-thread motion buffers, and implements `body_stop()` as a busy-wait drain. Consequently the architecture routes all exlibs access through one adapter, bans the PiDog AI wrapper modules outright, never starts the vilib web service, and supplies its own motion safety model.
**Why:** These are the concrete, evidenced reasons for ADR-0001, ADR-0002, and ADR-0005. Recording them prevents the constraints from being rediscovered or relaxed later without seeing the original evidence. Raspberry Pi OS Bookworm 64-bit with Python 3.11 remains an initial validation target rather than established compatibility, and no Azure latency, quota, or cost figure is asserted anywhere in the package.
