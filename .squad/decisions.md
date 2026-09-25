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


## 2026-09-25T10:18:06.056-04:00

- **Persona framework:** Sparky will use a declarative-first persona framework with manifests under `src/device/sparky_device/personas/` and shared schema/validation under `src/shared/sparky_contracts/personas/`. Core code loads personas through a registry; normal third-persona additions must require only a new manifest plus tests/fixtures.
- **Persona controls:** A persona controls LLM prompt intent, TTS voice/prosody, movement profile, vision/sensor reaction mappings, sound/RGB idioms, and safety notes. Persona safety may tighten but never override global safety, authentication, privacy, or motion constraints.
- **Switching:** Persona switching is a runtime hot-swap through voice intent, command mode, or programmatic API after a safe-state transition that cancels/settles in-flight conversation, TTS, motion, and transient reactions. Conversation memory is persona-scoped by default and switches are logged/telemetried.
- **Starter personas:** Sunny Companion (warm companion; gentle voice and relaxed movement) and Sentinel Scout (alert non-aggressive scout; crisp voice, patrol movement, inspection reactions).
- **New issues:** #30 schema/validation, #31 loader/registry/default, #32 runtime switching/safe-state, #33 persona-aware TTS, #34 movement profiles/reactions, #35 LLM prompt composition/safety, #36 starter manifests, #37 third-persona release acceptance.

## 2026-09-25T11:05:56.219-04:00

- **Deployment target:** Sparky Azure resources target the existing `rg-sparky` resource group in South Central US (`southcentralus`).
- **Subscription handling:** The concrete subscription is treated as deployment configuration. GitHub Actions must read it from the `AZURE_SUBSCRIPTION_ID` repository variable, and local operators must select it with `az account set`; it should not be committed into Bicep, parameter files, workflows, or general docs as a hardcoded value.
- **Environment model:** Dev and prod are logical environments in the same resource group, separated by Bicep parameters, GitHub Environments, tags, outputs, and resource names.
- **Naming convention:** Use `sparky-<resource>-<env>` where provider rules allow it; use provider-specific variants such as `sparkyscr<env>` for globally unique alphanumeric ACR names. Tag resources with `app=sparky` and `environment=<env>`.
- **Regional caveats:** Foundry projects and baseline GPT-4.1/GPT-4o-family standard model deployments are documented as available in South Central US, subject to current quota. Azure Speech supports core STT/TTS there, but advanced features such as LLM speech, MAI voices, HD voices, Azure OpenAI voices, personal voice, voice conversion, custom voice HD endpoints, preview voices/styles, and avatar voice sync are not available there in the referenced Speech region matrix; later work must choose standard neural/custom voices in-region or record a separate alternate-region decision.

## 2026-09-25T11:30:11.945-04:00

- **GitHub Actions Azure deployment setup:** Deployment documentation now specifies keyless GitHub Actions authentication through Microsoft Entra workload identity federation. The documented approach uses a secret-free app registration/service principal, federated credentials for `dev`, `prod`, `main`, and PR subjects as needed, repository variables for non-secret IDs, GitHub Environments for dev/prod approvals, and resource-group-scoped RBAC for `rg-sparky` with an additional RBAC administrator role only when Bicep creates role assignments.
