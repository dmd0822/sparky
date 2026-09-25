# Production environment

Production infrastructure is composed by `main.bicep` and parameterized by
`main.bicepparam`. It has the same shape as dev, with prod-specific parameter
values, tags, names, and outputs.

## Target

- Resource group: `rg-sparky`
- Location: `southcentralus`
- Environment name: `prod`
- Subscription: supplied by the caller through `AZURE_SUBSCRIPTION_ID` in GitHub Actions or the active `az` CLI account locally

Do not commit a subscription ID into this directory.

## Resources

The prod entry point composes shared modules to create:

- `sparky-law-prod` Log Analytics workspace
- `sparky-appi-prod` workspace-based Application Insights component
- `sparky-ai-prod` AI Services account and `sparky-proj-prod` Foundry project
- `sparky-speech-prod` Speech Services account
- `sparkyscrprod` Azure Container Registry
- `sparky-cae-prod` Container Apps environment
- `sparky-relay-prod` relay Container App shell with system-assigned managed identity
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

Production deployment should use the GitHub `prod` environment approval gate or
an equivalent manual approval. See
[GitHub Actions Azure deployment setup](../../../docs/deployment-setup.md) for
authentication setup. After selecting the target subscription:

```powershell
az group show --name rg-sparky --output table

az deployment group what-if `
  --resource-group rg-sparky `
  --parameters infra/environments/prod/main.bicepparam `
  --mode Incremental

az deployment group create `
  --resource-group rg-sparky `
  --parameters infra/environments/prod/main.bicepparam `
  --mode Incremental
```

## Open risks

- Model deployments are intentionally empty until South Central US quota and exact versions are confirmed.
- Confirm Speech voice availability for personas before production voice rollout; advanced voice features have South Central US caveats.
