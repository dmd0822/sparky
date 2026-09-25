# Infrastructure

Azure Bicep modules, environment compositions, and deployment helpers belong
under this tree. Do not place application Python code here.

## Deployment target

Sparky deploys Azure resources into a single resource group:

| Setting | Convention |
| --- | --- |
| Resource group | `rg-sparky` |
| Region | South Central US (`southcentralus`) |
| Subscription | Supplied at deployment time, not committed |
| Environments | `dev` and `prod` are logical environments in the same resource group |

The subscription is wired through the `AZURE_SUBSCRIPTION_ID` GitHub repository
variable for GitHub Actions, or through the active Azure CLI subscription for
manual deployments.

Set the GitHub repository variable with:

**Bash / zsh:**
```bash
gh variable set AZURE_SUBSCRIPTION_ID --repo dmd0822/sparky --body "<subscription-id>"
```

**PowerShell:**
```powershell
gh variable set AZURE_SUBSCRIPTION_ID --repo dmd0822/sparky --body "<subscription-id>"
```

For local deployment, select the subscription before running Bicep:

**Bash / zsh:**
```bash
az account set --subscription "<subscription-id>"
az group show --name rg-sparky --output table
```

**PowerShell:**
```powershell
az account set --subscription "<subscription-id>"
az group show --name rg-sparky --output table
```

The known target resource group already exists in South Central US.

For the full GitHub Actions setup, including Entra app registration, federated
credentials, RBAC, GitHub variables, environments, and an example infra CD
workflow, see [GitHub Actions Azure deployment setup](../docs/deployment-setup.md).

## Naming convention

All resources should use environment-suffixed names because dev and prod share
one resource group:

- General pattern: `sparky-<resource>-<env>`
- Azure Container Registry: `sparkyscr<env>` or another globally unique
  alphanumeric variant
- Log Analytics workspace: `sparky-law-<env>`
- Application Insights: `sparky-appi-<env>`
- Container Apps environment: `sparky-cae-<env>`
- Relay Container App: `sparky-relay-<env>`
- Managed identity or identity-bearing app resources:
  `sparky-mi-<purpose>-<env>`
- Foundry/AI resources: `sparky-ai-<env>` and `sparky-proj-<env>` where provider
  naming rules permit them

Apply at least these tags to every resource:

```text
app=sparky
environment=<dev|prod>
```

## GitHub Actions deployment wiring

The infra workflow should authenticate with GitHub OIDC / workload identity
federation. Keep the detailed setup in
[docs/deployment-setup.md](../docs/deployment-setup.md) rather than duplicating
it here. At runtime the workflow should consume repository variables such as
`vars.AZURE_CLIENT_ID`, `vars.AZURE_TENANT_ID`, `vars.AZURE_SUBSCRIPTION_ID`,
`vars.AZURE_RESOURCE_GROUP`, and `vars.AZURE_LOCATION`.

Do not add Azure access keys, publish profiles, `AZURE_CREDENTIALS`, or
long-lived service principal secrets. The workflow should run `what-if` before
deploy and target a group-scope deployment:

**Bash / zsh:**
```bash
az deployment group what-if \
  --resource-group rg-sparky \
  --parameters infra/environments/dev/main.bicepparam

az deployment group create \
  --resource-group rg-sparky \
  --parameters infra/environments/dev/main.bicepparam
```

**PowerShell:**
```powershell
az deployment group what-if `
  --resource-group rg-sparky `
  --parameters infra/environments/dev/main.bicepparam

az deployment group create `
  --resource-group rg-sparky `
  --parameters infra/environments/dev/main.bicepparam
```

Use the matching `prod` entry point for production after environment approval.

## Regional availability notes

South Central US supports Microsoft Foundry projects and the planned GPT-4.1 /
GPT-4o-family standard model deployments for baseline chat and vision, subject to
current model quota. Azure Speech supports core STT/TTS in `southcentralus`, but
not every advanced voice feature is available there. If a later persona requires
LLM speech, MAI voices, HD voices, personal voice, voice conversion, custom voice
HD endpoints, preview voices/styles, or avatar voice sync, open an explicit
architecture decision for either an alternate feature choice or an approved
alternate-region resource.
