# GitHub Actions Azure deployment setup

Audience: maintainers wiring Sparky's GitHub Actions to Azure. This guide sets up **keyless** deployment authentication from GitHub Actions to Azure with Microsoft Entra workload identity federation (OIDC). It does not use client secrets, publish profiles, storage keys, or an `AZURE_CREDENTIALS` JSON secret.

Sparky's infrastructure and code delivery workflows stay separate. Use this guide as the Azure authentication and infrastructure deployment spec for the future `infra-cd.yml`; keep container image/application rollout in a separate code workflow.

## 1. Prerequisites

You need:

- Azure CLI installed and signed in: `az login`.
- Permission in Microsoft Entra ID to create an app registration and service principal. Depending on tenant policy, this may require Application Developer, Cloud Application Administrator, or equivalent.
- Owner, User Access Administrator, Role Based Access Control Administrator, or equivalent rights on the target scope to assign Azure RBAC roles.
- Existing resource group: `rg-sparky`.
- Target region: South Central US (`southcentralus`).
- Optional: GitHub CLI (`gh`) authenticated to `dmd0822/sparky` for repository variables and issue comments.

Do not paste the real subscription ID into repo files. Use the `AZURE_SUBSCRIPTION_ID` GitHub repository variable and local shell variables only.

## 2. Create the Entra application and service principal

Use the secret-free path: create the app registration, then create its service principal. Do **not** use the default `az ad sp create-for-rbac` output as a GitHub secret because that command commonly creates and prints a password credential unless carefully constrained.

Run these commands from Azure Cloud Shell or any shell with Azure CLI:

```bash
az login
az account set --subscription "<your-subscription-id>"

APP_DISPLAY_NAME="sparky-github-deploy"
APP_ID=$(az ad app create \
  --display-name "$APP_DISPLAY_NAME" \
  --query appId \
  --output tsv)

APP_OBJECT_ID=$(az ad app show \
  --id "$APP_ID" \
  --query id \
  --output tsv)

SP_OBJECT_ID=$(az ad sp create \
  --id "$APP_ID" \
  --query id \
  --output tsv)

TENANT_ID=$(az account show --query tenantId --output tsv)

printf 'AZURE_CLIENT_ID=%s\nAZURE_TENANT_ID=%s\nSERVICE_PRINCIPAL_OBJECT_ID=%s\n' \
  "$APP_ID" "$TENANT_ID" "$SP_OBJECT_ID"
```

Keep the printed IDs handy for GitHub variables and role assignments. These IDs are not passwords, but still avoid hardcoding them in committed workflow files.

## 3. Configure federated credentials

A federated credential tells Entra ID which GitHub OIDC token subjects are allowed to exchange short-lived tokens for this service principal.

Common constants:

| Field | Value |
| --- | --- |
| Issuer | `https://token.actions.githubusercontent.com` |
| Audience | `api://AzureADTokenExchange` |
| Repository | `dmd0822/sparky` |

### Recommended Sparky credentials

Create separate credentials for each trust boundary you need. Environment-based credentials are recommended for deploy jobs because Sparky already has `dev` and `prod` GitHub Environments.

```bash
cat > github-dev-federated-credential.json <<'JSON'
{
  "name": "github-env-dev",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:dmd0822/sparky:environment:dev",
  "audiences": ["api://AzureADTokenExchange"],
  "description": "Sparky dev environment deployments from GitHub Actions"
}
JSON

az ad app federated-credential create \
  --id "$APP_OBJECT_ID" \
  --parameters @github-dev-federated-credential.json

cat > github-prod-federated-credential.json <<'JSON'
{
  "name": "github-env-prod",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:dmd0822/sparky:environment:prod",
  "audiences": ["api://AzureADTokenExchange"],
  "description": "Sparky prod environment deployments from GitHub Actions"
}
JSON

az ad app federated-credential create \
  --id "$APP_OBJECT_ID" \
  --parameters @github-prod-federated-credential.json
```

Add either or both of these only if the workflow will use them:

```bash
cat > github-main-federated-credential.json <<'JSON'
{
  "name": "github-main-branch",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:dmd0822/sparky:ref:refs/heads/main",
  "audiences": ["api://AzureADTokenExchange"],
  "description": "Sparky main branch automation from GitHub Actions"
}
JSON

az ad app federated-credential create \
  --id "$APP_OBJECT_ID" \
  --parameters @github-main-federated-credential.json

cat > github-pr-federated-credential.json <<'JSON'
{
  "name": "github-pull-request",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:dmd0822/sparky:pull_request",
  "audiences": ["api://AzureADTokenExchange"],
  "description": "Sparky pull request what-if validation from GitHub Actions"
}
JSON

az ad app federated-credential create \
  --id "$APP_OBJECT_ID" \
  --parameters @github-pr-federated-credential.json
```

Clean up local credential JSON files when you are done if you do not want to keep them in your shell directory. They contain no secrets, but they are setup artifacts.

### Which subject should I use?

| Subject | Matches | Use when |
| --- | --- | --- |
| `repo:dmd0822/sparky:environment:dev` | Jobs that declare `environment: dev` | Dev deployments or dev what-if jobs protected by the GitHub Environment. |
| `repo:dmd0822/sparky:environment:prod` | Jobs that declare `environment: prod` | Production deployments with required reviewers. |
| `repo:dmd0822/sparky:ref:refs/heads/main` | Jobs from `main` that do **not** declare an environment and are not pull-request events | Branch-scoped automation such as main-only validation. |
| `repo:dmd0822/sparky:pull_request` | Pull request jobs that do **not** declare an environment | PR what-if validation before merge. |

Important: GitHub's default `sub` claim changes depending on job context. If a job declares an `environment`, the subject is environment-based; a PR job without an environment uses `pull_request`; a normal branch job without an environment uses `ref:refs/heads/<branch>`. Subject mismatches are the most common OIDC setup failure.

## 4. Assign Azure RBAC at resource-group scope

Prefer the narrowest scope that supports the deployment. For Sparky that is the `rg-sparky` resource group, not the whole subscription.

```bash
AZURE_SUBSCRIPTION_ID="<your-subscription-id>"
RESOURCE_GROUP="rg-sparky"
RG_SCOPE="/subscriptions/${AZURE_SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}"

az role assignment create \
  --assignee-object-id "$SP_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Contributor" \
  --scope "$RG_SCOPE"
```

`Contributor` is needed for group-scope Bicep deployments that create and update Azure resources.

Sparky's Bicep is expected to create role assignments for the relay's managed identity so it can call Foundry and Speech with RBAC. A principal that creates role assignments also needs `Microsoft.Authorization/roleAssignments/write`. `Contributor` does **not** include that permission. Add a scoped RBAC role only if the Bicep deployment creates role assignments:

```bash
az role assignment create \
  --assignee-object-id "$SP_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Role Based Access Control Administrator" \
  --scope "$RG_SCOPE"
```

If that role is unavailable in your tenant, use `User Access Administrator` at the same resource-group scope. Avoid subscription-wide assignment unless the deployment truly needs subscription-scope changes.

## 5. Set GitHub repository variables

Use GitHub Actions variables for non-secret deployment identifiers. OIDC means there is no password to store. These values are not credentials by themselves, though storing them as secrets is acceptable if your team prefers not to display IDs in the Actions settings UI.

```bash
gh variable set AZURE_CLIENT_ID --repo dmd0822/sparky --body "<azure-client-id>"
gh variable set AZURE_TENANT_ID --repo dmd0822/sparky --body "<azure-tenant-id>"
gh variable set AZURE_SUBSCRIPTION_ID --repo dmd0822/sparky --body "<your-subscription-id>"
gh variable set AZURE_RESOURCE_GROUP --repo dmd0822/sparky --body "rg-sparky"
gh variable set AZURE_LOCATION --repo dmd0822/sparky --body "southcentralus"
```

Do not create `AZURE_CREDENTIALS`, do not store a client secret, and do not use publish profiles.

## 6. Create GitHub Environments

Create `dev` and `prod` in **Settings → Environments**.

Recommended settings:

- `dev`: no required reviewers, or lightweight reviewer rules if desired.
- `prod`: required reviewers and any deployment branch restrictions the team wants.

With GitHub CLI, create the environment records:

```bash
gh api --method PUT repos/dmd0822/sparky/environments/dev
gh api --method PUT repos/dmd0822/sparky/environments/prod
```

Configure production protection rules in the GitHub UI unless you already have a standard API payload for reviewers. The environment names must exactly match the federated credential subjects (`dev` and `prod`). A workflow job that says `environment: production` will not match `repo:dmd0822/sparky:environment:prod`.

## 7. Example infrastructure deployment workflow

Do not add this file as part of this documentation change. Issue #3 owns the live workflow skeletons. When implemented, keep the infrastructure workflow separate from code CI/CD, for example:

- `.github/workflows/infra-ci.yml` for Bicep build/lint/PR checks.
- `.github/workflows/infra-cd.yml` for Azure resource deployment.
- `.github/workflows/code-ci.yml` and `.github/workflows/code-cd.yml` for Python/container/device delivery.

Example `infra-cd.yml`:

```yaml
name: Infra CD

on:
  pull_request:
    branches: [main]
    paths:
      - "infra/**"
      - ".github/workflows/infra-cd.yml"
  push:
    branches: [main]
    paths:
      - "infra/**"
      - ".github/workflows/infra-cd.yml"
  workflow_dispatch:
    inputs:
      environment:
        description: "Environment to deploy"
        required: true
        default: "dev"
        type: choice
        options:
          - dev
          - prod

permissions:
  contents: read
  id-token: write

concurrency:
  group: infra-${{ github.event_name == 'workflow_dispatch' && inputs.environment || github.event_name }}
  cancel-in-progress: false

jobs:
  pr-what-if:
    name: PR what-if (dev)
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Azure login with OIDC
        uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

      - name: Verify Azure context
        run: |
          az account show --query "{tenantId:tenantId, subscriptionId:id, name:name}" --output table
          az group show --name "${{ vars.AZURE_RESOURCE_GROUP || 'rg-sparky' }}" --output table

      - name: What-if dev deployment
        run: |
          az deployment group what-if \
            --resource-group "${{ vars.AZURE_RESOURCE_GROUP || 'rg-sparky' }}" \
            --parameters infra/environments/dev/main.bicepparam

  deploy-dev:
    name: Deploy dev
    if: github.event_name == 'push' || (github.event_name == 'workflow_dispatch' && inputs.environment == 'dev')
    runs-on: ubuntu-latest
    environment: dev
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Azure login with OIDC
        uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

      - name: Verify Azure context
        run: |
          az account show --query "{tenantId:tenantId, subscriptionId:id, name:name}" --output table
          az group show --name "${{ vars.AZURE_RESOURCE_GROUP || 'rg-sparky' }}" --output table

      - name: Deploy dev infrastructure
        run: |
          az deployment group create \
            --resource-group "${{ vars.AZURE_RESOURCE_GROUP || 'rg-sparky' }}" \
            --parameters infra/environments/dev/main.bicepparam

  deploy-prod:
    name: Deploy prod
    if: github.event_name == 'workflow_dispatch' && inputs.environment == 'prod'
    runs-on: ubuntu-latest
    environment: prod
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Azure login with OIDC
        uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

      - name: Verify Azure context
        run: |
          az account show --query "{tenantId:tenantId, subscriptionId:id, name:name}" --output table
          az group show --name "${{ vars.AZURE_RESOURCE_GROUP || 'rg-sparky' }}" --output table

      - name: Deploy prod infrastructure
        run: |
          az deployment group create \
            --resource-group "${{ vars.AZURE_RESOURCE_GROUP || 'rg-sparky' }}" \
            --parameters infra/environments/prod/main.bicepparam
```

`permissions.id-token: write` is mandatory because `azure/login@v2` must request a GitHub OIDC token for Entra ID. The login step intentionally uses `client-id`, `tenant-id`, and `subscription-id`; it must not use `creds:`.

The PR job does not declare an environment so it can match the `repo:dmd0822/sparky:pull_request` federated credential. The deploy jobs declare `environment: dev` or `environment: prod`, so they match the environment federated credentials and can use GitHub Environment approvals.
The example passes native `.bicepparam` files directly through `--parameters`; those files should include their `using` statement for the matching Bicep entry point.

The existing live `python-validation.yml` pins actions by commit SHA. When issue #3 creates the real infra workflow, consider pinning `actions/checkout` and `azure/login` to immutable SHAs as part of the normal supply-chain hardening pass.

## 8. Verify the setup

A successful run should show:

1. `Azure login with OIDC` succeeds without a `creds:` input and without any secret named `AZURE_CREDENTIALS`.
2. `az account show` reports the expected tenant and subscription.
3. `az group show --name rg-sparky` finds the target resource group.
4. PR runs produce a `what-if` result for `infra/environments/dev/main.bicep`.
5. Main branch or approved manual runs create a successful group-scope deployment in `rg-sparky`.

You can also inspect Entra sign-in logs for the service principal to confirm token exchange is coming from GitHub Actions rather than a password credential.

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `AADSTS70021: No matching federated identity record found` | The GitHub OIDC `sub`, `issuer`, or `audience` does not match a federated credential. | Check whether the job uses `environment`, `pull_request`, or a branch ref. Add the matching subject exactly. |
| `azure/login` says it cannot get an ID token | Missing workflow permission. | Add `permissions: id-token: write` at workflow or job level. |
| Token exchange fails with audience errors | Federated credential audience differs from the action's audience. | Use `api://AzureADTokenExchange` for Azure public cloud unless intentionally targeting another cloud. |
| PR what-if fails with `AADSTS70021` after adding `environment: dev` | Environment jobs use `repo:...:environment:dev`, not `repo:...:pull_request`. | Either remove `environment` from the PR job or add an environment-scoped credential and accept environment approvals on PRs. |
| Deployment fails with authorization errors immediately after role assignment | RBAC propagation delay. | Wait a few minutes and rerun. Confirm role assignment scope is `rg-sparky`. |
| Bicep deployment fails creating role assignments | Deployment principal has `Contributor` but not role-assignment permission. | Add `Role Based Access Control Administrator` or `User Access Administrator` at resource-group scope. |
| Workflow deploys to the wrong subscription | Wrong `AZURE_SUBSCRIPTION_ID` variable or stale local Azure CLI context. | Check repository variable value, environment variable overrides, and the `az account show` verification step. |
| Prod job never starts | GitHub Environment protection is waiting for approval. | Approve the deployment in the Actions run or adjust environment protection rules. |

## 10. Security notes

- No Azure access keys, client secrets, publish profiles, or long-lived credential blobs are required.
- Federated credentials are scoped to exact GitHub subjects and can be removed independently when a branch, environment, or repository is retired.
- Keep RBAC at `rg-sparky` scope unless a future deployment explicitly requires a broader scope.
- Prefer environment-scoped credentials for deployments and require reviewers for `prod`.
- If the repository is transferred, renamed, or opts into immutable OIDC subject claims, update the Entra federated credential subjects before relying on deployments.
- Periodically review app registration federated credentials and remove unused subjects.
