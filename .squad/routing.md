# Work Routing

How to decide who handles what.

## Routing Table

| Work Type | Route To | Examples |
|-----------|----------|----------|
| Requirements, architecture, and scope | Architect | Requirements and non-goals, modular persona architecture, architecture decisions, diagrams, clean-code standards, project plan |
| Architecture and project-plan approval gate | Architect | Assemble both planning deliverables, coordinate specialist review, and block implementation until explicit user approval of both |
| PiDog hardware and motion planning | Robotics | Motion and sensor interfaces, Raspberry Pi/PiDog hardware behavior, abstraction boundaries, physical safety constraints |
| External-library compatibility assessment | Robotics → Architect | Read-only assessment of `exlibs/pidog`, `exlibs/robot-hat`, and `exlibs/vilib`; findings feed architecture and must never modify application code or `exlibs/` |
| Audio and speech planning | Speech | Microphone and playback architecture, wake/listening behavior, Azure Speech integration, latency, interruption, animatronic synchronization |
| Azure-hosted AI planning | AzureAI | Azure LLM integration, managed identity/configuration, resilience, connectivity, content safety, cloud cost and latency |
| Acceptance and reliability | Reliability | Acceptance criteria, simulation, failure modes, integration testing, hardware-in-the-loop strategy, implementation-readiness review |
| External/API claim verification | Fact Checker | Verify exlibs API claims, Azure service/API claims, assumptions, citations, versions, and counter-hypotheses |
| Responsible AI and safety review | Rai | Content safety, privacy, responsible behavior, credential handling, and safety/responsibility review |
| Architecture review | Architect | Final coherence review, cross-domain decisions, clean-code standards, and readiness recommendation |
| Test-readiness review | Reliability | Review acceptance criteria, failure coverage, simulation feasibility, integration strategy, and hardware-in-the-loop readiness |
| Work queue and backlog monitoring | Ralph | Monitor planning work, blockers, dependencies, and stalled items without authorizing implementation |
| Scope & priorities | Architect | Planning sequence, trade-offs, dependencies, and what may proceed before approval |
| Session logging | Scribe | Automatic — never needs routing |
| Decision verification | Fact Checker | Fact-check planning claims before delivery |

## Issue Routing

| Label | Action | Who |
|-------|--------|-----|
| `squad` | Triage: analyze issue, assign `squad:{member}` label | Lead |
| `squad:{name}` | Pick up issue and complete the work | Named member |

### How Issue Assignment Works

1. When a GitHub issue gets the `squad` label, the **Lead** triages it — analyzing content, assigning the right `squad:{member}` label, and commenting with triage notes.
2. When a `squad:{member}` label is applied, that member picks up the issue in their next session.
3. Members can reassign by removing their label and adding another member's label.
4. The `squad` label is the "inbox" — untriaged issues waiting for Lead review.

## Rules

1. **Planning-only hard gate** — no application/product code, implementation task, or modification under `exlibs/` may begin until the user explicitly approves both the architecture documentation and the project plan.
2. **Scribe always runs** after substantial work, always as `mode: "background"`. Never blocks.
3. **Quick facts → coordinator answers directly.** Don't spawn an agent for "what port does the server run on?"
4. **When two agents could handle it**, pick the one whose domain is the primary concern.
5. **Planning fan-out** — parallel specialist research is allowed only when scopes are independent and read-only; all findings feed Architect.
6. **Required planning reviews** — Fact Checker verifies external/API claims, Rai reviews safety/responsibility, and Reliability reviews acceptance/test readiness before the two deliverables are presented for approval.
7. **Issue-labeled work** — when a `squad:{member}` label is applied to an issue, route to that member. The Lead handles all `squad` (base label) triage.
8. **Architect review gate** — Architect integrates requirements and specialist findings into coherent architecture documentation and a project plan; neither document alone authorizes implementation.
9. **Approval semantics** — implementation becomes eligible only after the user explicitly approves both deliverables. Requested revisions return to planning status.
