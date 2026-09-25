# Squad Decisions

## Active Decisions

No decisions recorded yet.

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction

## 2026-09-25T09:38:29.971-04:00

- **Repo structure:** Monorepo with `/src` for device/cloud/shared application code, `/infra` for Bicep, `/docs` for architecture/ADRs/plan, and separate workflow definitions under `/.github/workflows`.
- **IaC choice:** Bicep, because the project is Azure-only and needs native managed identity/RBAC support without Terraform state bootstrap.
- **Keyless auth approach:** Raspberry Pi authenticates to an Entra-protected relay API using device code flow as a public client; the relay runs in Azure Container Apps with system-assigned managed identity and calls Foundry/Speech with RBAC only.
- **Milestone plan:** M1 Foundations & Keyless Platform, M2 Device Control Baseline, M3 Relay API & Vision Perception, M4 Voice Conversation Loop, M5 Agent Behavior & Orchestration, M6 Hardening, Security & Observability, M7 Release Readiness & Demo.
- **Issue count:** 28 GitHub issues created across 7 milestones.
