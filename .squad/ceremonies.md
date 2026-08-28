# Ceremonies

> Team meetings that happen before or after work. Each squad configures their own.

## Architecture & Project Plan Approval

| Field | Value |
|-------|-------|
| **Trigger** | Phase 2 initialization complete |
| **When** | before any application/product implementation |
| **Condition** | Architecture documentation or project plan is unapproved |
| **Facilitator** | Architect |
| **Participants** | Architect, Robotics, Speech, AzureAI, Reliability, Fact Checker, Rai |
| **Time budget** | comprehensive |
| **Enabled** | ✅ yes — blocking |

**Workflow:**
1. Architect defines requirements, non-goals, assumptions, open questions, architecture boundaries, and planning constraints.
2. Robotics performs read-only compatibility/API assessment of `exlibs/pidog`, `exlibs/robot-hat`, and `exlibs/vilib`; Speech, AzureAI, and Reliability produce planning assessments in their domains.
3. All specialist findings feed Architect. No assessment may modify application/product code or anything under `exlibs/`.
4. Architect assembles the architecture documentation and project plan.
5. Fact Checker verifies external/API claims; Rai reviews safety, responsibility, privacy, and content-safety concerns; Reliability reviews acceptance criteria and test readiness.
6. Architect resolves review findings and presents both deliverables to the user.
7. Only explicit user approval of both deliverables opens the implementation gate. Approval of one, silence, or a request for revisions leaves implementation blocked.

**Required architecture and plan coverage:**
- Requirements and non-goals
- Read-only exlibs compatibility/API assessment
- Architecture decisions
- System-context, component, data-flow, sequence, and state diagrams
- Persona extension and switching model
- Azure AI and Azure Speech integration plans
- Hardware safety and hardware-abstraction strategy
- Risks, assumptions, and open questions
- Phased milestones and dependencies
- Acceptance criteria
- Testing and reliability strategy, including simulation, integration, and hardware-in-the-loop planning
- Implementation-readiness checklist

---

## Design Review

| Field | Value |
|-------|-------|
| **Trigger** | auto |
| **When** | before |
| **Condition** | multi-agent task involving 2+ agents modifying shared systems |
| **Facilitator** | lead |
| **Participants** | all-relevant |
| **Time budget** | focused |
| **Enabled** | ✅ yes |

**Agenda:**
1. Review the task and requirements
2. Agree on interfaces and contracts between components
3. Identify risks and edge cases
4. Assign action items

---

## Retrospective

| Field | Value |
|-------|-------|
| **Trigger** | auto |
| **When** | after |
| **Condition** | build failure, test failure, or reviewer rejection |
| **Facilitator** | lead |
| **Participants** | all-involved |
| **Time budget** | focused |
| **Enabled** | ✅ yes |

**Agenda:**
1. What happened? (facts only)
2. Root cause analysis
3. What should change?
4. Action items for next iteration


---

## Retrospective with Enforcement

| Field | Value |
|-------|-------|
| **Trigger** | auto |
| **When** | weekly |
| **Condition** | No *retrospective* log in .squad/log/ within the last 7 days |
| **Facilitator** | lead |
| **Participants** | all |
| **Time budget** | focused |
| **Enabled** | yes |
| **Enforcement skill** | retro-enforcement |

**Agenda:**
1. What shipped this week? (closed issues, merged PRs)
2. What did not ship? (open issues, blockers)
3. Root cause on any failures
4. Action items -- each MUST become a GitHub Issue labeled retro-action

**Coordinator integration:**
At round start, call Test-RetroOverdue (see skill retro-enforcement). If overdue, run this ceremony before the work queue.

**Why GitHub Issues, not markdown:**
Production data: 0% completion across 6 retros using markdown checklists, 100% after switching to GitHub Issues.
