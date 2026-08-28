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
