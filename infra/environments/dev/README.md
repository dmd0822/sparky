# Development environment

Development Bicep compositions and parameters belong here.

## Target

- Resource group: `rg-sparky`
- Location: `southcentralus`
- Environment name: `dev`
- Subscription: supplied by the caller through `AZURE_SUBSCRIPTION_ID` in GitHub
  Actions or the active `az` CLI account locally

Do not commit a subscription ID into this directory.

## Naming

Use `sparky-<resource>-dev` for most resources, with provider-specific variants
where required:

- Container Apps environment: `sparky-cae-dev`
- Relay Container App: `sparky-relay-dev`
- Log Analytics: `sparky-law-dev`
- Application Insights: `sparky-appi-dev`
- Container Registry: `sparkyscrdev` or another globally unique alphanumeric
  variant
- Foundry/AI resources: `sparky-ai-dev` and `sparky-proj-dev` where provider
  naming rules permit them

All resources should be tagged with `app=sparky` and `environment=dev`.

## Manual deployment

After selecting the target subscription:

```powershell
az account set --subscription "<subscription-id>"
az group show --name rg-sparky --output table

az deployment group what-if `
  --resource-group rg-sparky `
  --parameters infra/environments/dev/main.bicepparam

az deployment group create `
  --resource-group rg-sparky `
  --parameters infra/environments/dev/main.bicepparam
```

## GitHub Actions deployment

The infra workflow should read `vars.AZURE_SUBSCRIPTION_ID`, authenticate with
OIDC/WIF, and deploy the dev entry point to `rg-sparky` in `southcentralus`.
Dev deployments can run automatically from `main` once the infra CD workflow is
implemented.
