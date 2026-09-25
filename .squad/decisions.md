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

## 2026-09-25T09:38:29.971-04:00

- **Security review verdict:** 🟡 The architecture and ADR 0003 are directionally sound for a keyless design (Pi authenticates only to the relay; relay uses managed identity to reach Foundry/Speech), but issues #2, #3, #4, #9, and #23 need explicit acceptance criteria for disabling local/key-based auth, enforcing GitHub OIDC/WIF-only deployment auth, proving no fallback key paths, tightening relay token/app-role validation, and threat-modeling token/logging/device-loss risks.
