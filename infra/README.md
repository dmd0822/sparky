# Infrastructure

Azure Bicep modules, environment compositions, and deployment helpers live under
this tree. Application Python code belongs under `src/`.

## What exists now

- `modules/monitoring.bicep` — Log Analytics workspace and workspace-based Application Insights.
- `modules/ai-services.bicep` — Microsoft Foundry / Azure AI Services account, Foundry project child resource, and optional model deployment placeholders.
- `modules/speech.bicep` — Speech Services account with custom subdomain support for Entra auth.
- `modules/container-registry.bicep` — Azure Container Registry with admin user disabled.
- `modules/container-app-environment.bicep` — Container Apps managed environment wired to the Log Analytics workspace without workspace-key retrieval.
- `modules/relay-container-app.bicep` — externally reachable relay Container App shell with system-assigned managed identity.
- `modules/rbac.bicep` — least-privilege role assignments scoped to the AI account, Speech account, and ACR.
- `environments/dev/main.bicep` and `environments/prod/main.bicep` — resource-group-scope entry points that compose modules only.
- `environments/*/main.bicepparam` — logical-environment parameter files.
- `scripts/validate.ps1` — local validation helper that builds every module, both entry points, and both parameter files.

## Deployment target

Sparky deploys Azure resources into a single resource group:

| Setting | Convention |
| --- | --- |
| Resource group | `rg-sparky` |
| Region | South Central US (`southcentralus`) |
| Subscription | Supplied at deployment time, not committed |
| Environments | `dev` and `prod` are logical environments in the same resource group |

The subscription is supplied through the `AZURE_SUBSCRIPTION_ID` GitHub
repository secret for GitHub Actions, or through the active Azure CLI
subscription for local deployments. Do not commit subscription IDs to Bicep,
parameter files, workflow YAML, or docs.

For the full GitHub Actions OIDC / workload identity federation setup, see
[GitHub Actions Azure deployment setup](../docs/deployment-setup.md).

## Naming convention

All resources use environment-suffixed names because dev and prod share one
resource group:

| Resource | Pattern |
| --- | --- |
| Log Analytics workspace | `sparky-law-<env>` |
| Application Insights | `sparky-appi-<env>` |
| Container Apps environment | `sparky-cae-<env>` |
| Relay Container App | `sparky-relay-<env>` |
| Azure Container Registry | `sparkyscr<env>` by default; override if global uniqueness requires it |
| Foundry / AI Services account | `sparky-ai-<env>` |
| Foundry project | `sparky-proj-<env>` |
| Speech resource | `sparky-speech-<env>` |

Every resource receives at least these tags:

```text
app=sparky
environment=<dev|prod>
```

## Security posture

The baseline templates are keyless by design:

- Cognitive Services accounts set `disableLocalAuth: true` and explicit public network access.
- ACR sets `adminUserEnabled: false`.
- The relay Container App uses a system-assigned managed identity.
- RBAC grants the relay identity `Cognitive Services User` only on the AI and Speech accounts, and `AcrPull` only on the ACR.
- Outputs intentionally exclude keys, connection strings, instrumentation keys, passwords, and admin credentials. Application Insights outputs are limited to name and resource ID; runtime telemetry settings should be supplied via managed identity-aware app configuration or out-of-band app settings.
- The static test in `tests/test_infra_policy.py` mechanically guards the no-key/no-secret constraints.

## Local validation

From the repo root in PowerShell:

```powershell
.\infra\scripts\validate.ps1
python -m unittest tests.test_infra_policy
```

The script runs the same Bicep build set as infra CI: every module, both
environment entry points, and both `.bicepparam` files.

## Deployment

Select the subscription locally before deploying:

```powershell
az account set --subscription "<subscription-id>"
az group show --name rg-sparky --output table
```

Preview and deploy dev:

```powershell
az deployment group what-if `
  --resource-group rg-sparky `
  --parameters infra/environments/dev/main.bicepparam `
  --mode Incremental

az deployment group create `
  --resource-group rg-sparky `
  --parameters infra/environments/dev/main.bicepparam `
  --mode Incremental
```

Use `infra/environments/prod/main.bicepparam` for production after the GitHub
Environment approval gate. GitHub Actions deployment remains manual-only through
`.github/workflows/infra-cd.yml` and always runs `what-if` before `create`.

## Open risks and follow-ups

- Confirm South Central US model quota, deployment type, and exact chat/vision model versions immediately before adding entries to `modelDeployments`.
- Confirm Speech voice availability for later personas; advanced voice features have documented South Central US caveats.
- The Container Apps environment avoids workspace-key retrieval to honor the no-key policy. Validate first deployment with `az deployment group what-if` and Azure Monitor log flow before relying on production diagnostics.
