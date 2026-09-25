# Bicep modules

Reusable Azure Bicep modules live here. Environment entry points compose these
modules; they should not duplicate resource declarations.

## Module inventory

| Module | Concern | Key outputs |
| --- | --- | --- |
| `monitoring.bicep` | Log Analytics workspace and workspace-based Application Insights | workspace name/resource ID/customer ID, App Insights name/resource ID |
| `ai-services.bicep` | Microsoft Foundry / AI Services account, Foundry project, optional model deployment placeholders | account name/resource ID/endpoint, project name/resource ID |
| `speech.bicep` | Speech Services account for STT/TTS | account name/resource ID/endpoint |
| `container-registry.bicep` | Azure Container Registry | registry name/resource ID/login server |
| `container-app-environment.bicep` | Container Apps managed environment | environment name/resource ID/default domain |
| `relay-container-app.bicep` | Relay app shell with system-assigned managed identity and external ingress | app name/resource ID/FQDN/principal ID |
| `rbac.bicep` | Scoped role assignments for relay managed identity | role assignment resource IDs |

## Security requirements

- Do not use workspace keys, Azure AI keys, ACR admin credentials, or other static secrets.
- Keep Cognitive Services `disableLocalAuth: true` and ACR `adminUserEnabled: false`.
- Role assignments must be deterministic and scoped to the specific target resource.
- Do not add outputs for keys, secrets, connection strings, instrumentation keys, passwords, or admin credentials.

`tests/test_infra_policy.py` enforces these rules as text-level policy checks.

## Model deployments

`ai-services.bicep` accepts a `modelDeployments` array, but both environment
parameter files intentionally keep it empty for M1. Add chat/vision deployments
only after confirming regional quota, deployment type, and exact model versions
for South Central US.
