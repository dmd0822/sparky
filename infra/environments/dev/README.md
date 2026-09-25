# Development environment

Development infrastructure is composed by `main.bicep` and parameterized by
`main.bicepparam`.

## Target

- Resource group: `rg-sparky`
- Location: `southcentralus`
- Environment name: `dev`
- Subscription: supplied by the caller through `AZURE_SUBSCRIPTION_ID` in GitHub Actions or the active `az` CLI account locally

Do not commit a subscription ID into this directory.

## Resources

The dev entry point composes shared modules to create:

- `sparky-law-dev` Log Analytics workspace
- `sparky-appi-dev` workspace-based Application Insights component
- `sparky-ai-dev` AI Services account and `sparky-proj-dev` Foundry project
- `sparky-speech-dev` Speech Services account
- `sparkyscrdev` Azure Container Registry
- `sparky-cae-dev` Container Apps environment
- `sparky-relay-dev` relay Container App shell with system-assigned managed identity
- Scoped RBAC assignments for AI, Speech, and ACR access

## Outputs

The entry point outputs the names/resource IDs/endpoints needed by later code CD:
ACR login server, relay app name/resource ID/FQDN/principal ID, Container Apps
environment details, AI Services and Speech endpoints, Foundry project details,
and monitoring resource names/resource IDs. It does not output keys or connection
strings.

## Validate

```powershell
.\infra\scripts\validate.ps1
```

## Manual deployment

See [GitHub Actions Azure deployment setup](../../../docs/deployment-setup.md)
for authentication setup. After selecting the target subscription:

```powershell
az group show --name rg-sparky --output table

az deployment group what-if `
  --resource-group rg-sparky `
  --parameters infra/environments/dev/main.bicepparam `
  --mode Incremental

az deployment group create `
  --resource-group rg-sparky `
  --parameters infra/environments/dev/main.bicepparam `
  --mode Incremental
```

## Open risks

- Model deployments are intentionally empty until South Central US quota and exact versions are confirmed.
- Validate Azure Monitor log flow after first deployment because the template avoids workspace-key retrieval by policy.
