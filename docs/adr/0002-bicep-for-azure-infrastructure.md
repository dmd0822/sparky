# ADR 0002: Use Bicep for Azure infrastructure as code

- **Status:** Accepted
- **Date:** 2026-09-25
- **Owners:** lead

## Context

This project is Azure-only and must provision Microsoft Foundry, Azure Container Apps, managed identities, RBAC assignments, monitoring, and supporting resources entirely by code where possible.

The team needs an IaC tool that:

- models Azure-first resources quickly
- handles RBAC and managed identity wiring cleanly
- integrates well with GitHub Actions
- is easy to review in a small repository with no existing Terraform estate

## Decision

Use **Bicep** as the primary IaC tool under `infra/`.

## Why Bicep

- Native Azure support and day-one coverage for Azure resource types.
- Lower operational overhead than Terraform for an Azure-only system.
- First-class support for ARM scopes, role assignments, managed identities, and deployment validation.
- No separate state backend to bootstrap for the initial milestones.
- Straightforward CI using `az bicep build`, `az deployment what-if`, and environment-scoped deployments.

## Consequences

### Positive

- Faster delivery for an Azure-specific architecture.
- Fewer moving parts during early platform setup.
- Easier review of RBAC and identity bindings in the same language as the target platform.

### Negative

- Less portable if the project ever expands beyond Azure.
- Requires contributors to learn Azure deployment idioms rather than generic multi-cloud patterns.

## Alternatives considered

### Terraform

Rejected for the initial build because the project is not multi-cloud, the team would need to introduce state management immediately, and the primary resources are Azure-native.

## Follow-up

- Organize reusable modules under `infra/modules`.
- Use separate environment entry points under `infra/environments/dev` and `infra/environments/prod`.
