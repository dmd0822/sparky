# Squad Team

> sparky

## Coordinator

| Name | Role | Notes |
|------|------|-------|
| Squad | Coordinator | Routes work, enforces handoffs and reviewer gates. |

## Members

| Name | Role | Charter | Status |
|------|------|---------|--------|
| Architect | Lead & Software Architect | [agents/architect/charter.md](agents/architect/charter.md) | Active — planning lead and approval gate |
| Robotics | Embedded Robotics Engineer | [agents/robotics/charter.md](agents/robotics/charter.md) | Active — planning and read-only assessment |
| Speech | Audio & Speech Engineer | [agents/speech/charter.md](agents/speech/charter.md) | Active — planning |
| AzureAI | Azure AI Engineer | [agents/azureai/charter.md](agents/azureai/charter.md) | Active — planning |
| Reliability | Test & Reliability Engineer | [agents/reliability/charter.md](agents/reliability/charter.md) | Active — planning and readiness review |
| Scribe | Session Logger, Memory Manager & Decision Merger | [agents/scribe/charter.md](agents/scribe/charter.md) | Always on — silent |
| Ralph | Work Queue & Backlog Monitor | [agents/ralph/charter.md](agents/ralph/charter.md) | Always on — monitor |
| Rai | Responsible AI Reviewer | [agents/Rai/charter.md](agents/Rai/charter.md) | Always on — background |
| Fact Checker | Verification & Devil's Advocate | [agents/fact-checker/charter.md](agents/fact-checker/charter.md) | Always on — verifier |


## Coding Agent

<!-- copilot-auto-assign: false -->

| Name | Role | Charter | Status |
|------|------|---------|--------|
| @copilot | Coding Agent | — | 🤖 Coding Agent |

### Capabilities

**🟢 Good fit — auto-route when enabled:**
- Bug fixes with clear reproduction steps
- Test coverage (adding missing tests, fixing flaky tests)
- Lint/format fixes and code style cleanup
- Dependency updates and version bumps
- Small isolated features with clear specs
- Boilerplate/scaffolding generation
- Documentation fixes and README updates

**🟡 Needs review — route to @copilot but flag for squad member PR review:**
- Medium features with clear specs and acceptance criteria
- Refactoring with existing test coverage
- API endpoint additions following established patterns
- Migration scripts with well-defined schemas

**🔴 Not suitable — route to squad member instead:**
- Architecture decisions and system design
- Multi-system integration requiring coordination
- Ambiguous requirements needing clarification
- Security-critical changes (auth, encryption, access control)
- Performance-critical paths requiring benchmarking
- Changes requiring cross-team discussion

## Project Context

- **Project:** sparky
- **Created:** 2026-08-28
- **Requested by:** Dave Davis
- **Naming universe:** descriptive
- **Purpose:** Plan a modular persona-driven robotic companion integrating PiDog-class Raspberry Pi hardware behavior with Azure-hosted AI and speech capabilities.
- **Current phase:** Phase 2 initialization and planning only. Likely Python, Raspberry Pi/PiDog, Azure AI, and Azure Speech details are assumptions until the architecture assessment verifies them.
- **Hard planning gate:** No application or product implementation may begin until Dave Davis explicitly approves both the architecture documentation and the project plan.
- **External library constraint:** Assessment of `exlibs/pidog`, `exlibs/robot-hat`, and `exlibs/vilib` is read-only; application code and external-library repositories must not be modified during assessment.
