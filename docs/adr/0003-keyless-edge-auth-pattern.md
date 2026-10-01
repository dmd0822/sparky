# ADR 0003: Use an Azure relay service with Managed Identity for keyless AI access

- **Status:** Accepted
- **Date:** 2026-09-25
- **Owners:** lead

## Context

The Raspberry Pi device must use Azure AI capabilities for chat, speech, and vision without storing API keys, connection strings, or long-lived client secrets.

The Pi cannot use a system-assigned managed identity the way Azure compute can. A direct device-to-Foundry design would either:

- require interactive user sign-in directly to Azure AI endpoints,
- require a certificate or secret managed on the device, or
- expose Azure AI endpoints and policy enforcement directly to the edge.

The architecture also needs centralized policy enforcement, observability, and rate limiting.

## Decision

Use a **device-to-relay-to-Foundry** pattern:

1. The Raspberry Pi runs a device application that authenticates to a custom backend API using **Microsoft Entra ID device code flow** as a **public client**.
2. The backend API runs in **Azure Container Apps** with a **system-assigned managed identity**.
3. The backend uses that managed identity to call Microsoft Foundry and Speech endpoints with RBAC (`Cognitive Services User`) and no API keys.
4. The Pi never stores a client secret or Azure AI key; it only stores public client configuration and the local token cache managed by the Microsoft identity library.

## Why this pattern

- Meets the “no access keys on Azure resources” requirement.
- Avoids long-lived service credentials on the Pi.
- Centralizes prompt policy, request shaping, retries, quotas, logging, and safety filters.
- Allows the project to evolve without redeploying Azure endpoint details to every device.

## Consequences

### Positive

- Strongest production posture for a hobby/edge device without trusted cloud identity.
- Clean separation between device logic and cloud policy.
- Easier audit and RBAC management.

### Negative

- Adds a backend hop and some latency.
- Requires a one-time human sign-in or operational enrollment step on the Pi.
- Autonomous unattended bootstrapping is harder than a key-based direct call.

## Rejected alternatives

### Direct Pi-to-Foundry with API keys

Rejected because it violates the project constraints.

### Direct Pi-to-Foundry with confidential client secret

Rejected because the Pi would have to hold a long-lived secret.

### Direct Pi-to-Foundry with certificate credentials

Rejected for the baseline because certificate issuance, secure storage, and rotation on a consumer Raspberry Pi are more complex than the project needs initially.

## Follow-up

- Implement backend audience/app role checks for enrolled devices.
- Revisit certificate-backed workload identity only if unattended fleet-scale enrollment becomes necessary.

## Downstream call path

The device presents only its relay-audience Entra token to the relay. After
validating that token, the relay acquires a separate managed-identity token for
`https://cognitiveservices.azure.com/.default` and uses that token for each
service hop: Foundry chat/vision via chat completions, and Speech synthesis via
the Speech endpoint. The caller token is never forwarded downstream.
