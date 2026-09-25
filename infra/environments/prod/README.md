# Production environment

Production Bicep compositions and parameters belong here.

## Target

- Resource group: `rg-sparky`
- Location: `southcentralus`
- Environment name: `prod`
- Subscription: supplied by the caller through the `AZURE_SUBSCRIPTION_ID`
  GitHub Actions repository secret or the active `az` CLI account locally

Do not commit a subscription ID into this directory.

## Naming

Use `sparky-<resource>-prod` for most resources, with provider-specific variants
where required:

- Container Apps environment: `sparky-cae-prod`
- Relay Container App: `sparky-relay-prod`
- Log Analytics: `sparky-law-prod`
- Application Insights: `sparky-appi-prod`
- Container Registry: `sparkyscrprod` or another globally unique alphanumeric
  variant
- Foundry/AI resources: `sparky-ai-prod` and `sparky-proj-prod` where provider
  naming rules permit them

All resources should be tagged with `app=sparky` and `environment=prod`.

## Manual deployment

After selecting the target subscription:

**Bash / zsh:**
```bash
az account set --subscription "<subscription-id>"
az group show --name rg-sparky --output table

az deployment group what-if \
  --resource-group rg-sparky \
  --parameters infra/environments/prod/main.bicepparam

az deployment group create \
  --resource-group rg-sparky \
  --parameters infra/environments/prod/main.bicepparam
```

**PowerShell:**
```powershell
az account set --subscription "<subscription-id>"
az group show --name rg-sparky --output table

az deployment group what-if `
  --resource-group rg-sparky `
  --parameters infra/environments/prod/main.bicepparam

az deployment group create `
  --resource-group rg-sparky `
  --parameters infra/environments/prod/main.bicepparam
```

## GitHub Actions deployment

The infra workflow should read `secrets.AZURE_SUBSCRIPTION_ID`, authenticate
with OIDC/WIF, and deploy the prod entry point to `rg-sparky` in `southcentralus`.
Production deployments should use GitHub Environment approval before running
`az deployment group create` when the repository plan supports protection rules;
otherwise, use branch protection on `main` as the deployment gate.
