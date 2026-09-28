# GitHub Actions Azure deployment setup

Audience: maintainers wiring Sparky's GitHub Actions to Azure. This guide sets up **keyless** deployment authentication from GitHub Actions to Azure with Microsoft Entra workload identity federation (OIDC). It does not use client secrets, publish profiles, storage keys, or an `AZURE_CREDENTIALS` JSON secret.

Sparky's infrastructure and code delivery workflows stay separate. Use this guide as the Azure authentication and infrastructure deployment spec for the future `infra-cd.yml`; keep container image/application rollout in a separate code workflow.

## Shell conventions

Shell command examples are provided in paired **Bash / zsh** and **PowerShell** blocks. Use the block that matches your shell verbatim; PowerShell users should not run the Bash variable assignments (`NAME=value`), `$NAME` expansions, or trailing `\` line continuations.

## 1. Prerequisites

You need:

- Azure CLI installed and signed in: `az login`.
- Permission in Microsoft Entra ID to create an app registration and service principal. Depending on tenant policy, this may require Application Developer, Cloud Application Administrator, or equivalent.
- Owner, User Access Administrator, Role Based Access Control Administrator, or equivalent rights on the target scope to assign Azure RBAC roles.
- Existing resource group: `rg-sparky`.
- Target region: South Central US (`southcentralus`).
- Optional: GitHub CLI (`gh`) authenticated to `dmd0822/sparky` for repository secrets, variables, and issue comments.

Do not paste the real subscription ID into repo files. Use the `AZURE_SUBSCRIPTION_ID` GitHub repository secret and local shell variables only.

## 2. Create the Entra application and service principal

Use the secret-free path: create the app registration, then create its service principal. Do **not** use the default `az ad sp create-for-rbac` output as a GitHub secret because that command commonly creates and prints a password credential unless carefully constrained.

Run these commands from Azure Cloud Shell, Bash/zsh, or PowerShell with Azure CLI:

**Bash / zsh:**
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

**PowerShell:**
```powershell
az login
az account set --subscription "<your-subscription-id>"

$AppDisplayName = "sparky-github-deploy"
$AppId = az ad app create --display-name $AppDisplayName --query appId --output tsv
$AppId = $AppId.Trim()

$AppObjectId = az ad app show --id $AppId --query id --output tsv
$AppObjectId = $AppObjectId.Trim()

$SpObjectId = az ad sp create --id $AppId --query id --output tsv
$SpObjectId = $SpObjectId.Trim()

$TenantId = az account show --query tenantId --output tsv
$TenantId = $TenantId.Trim()

"AZURE_CLIENT_ID=$AppId"
"AZURE_TENANT_ID=$TenantId"
"SERVICE_PRINCIPAL_OBJECT_ID=$SpObjectId"
```

Keep the printed IDs handy for GitHub secrets and role assignments. These IDs are not passwords, but still avoid hardcoding them in committed workflow files. The Azure CLI `--query ... --output tsv` commands above should each return one value; PowerShell examples trim the captured text so copied IDs do not include an accidental trailing newline.

## 3. Configure federated credentials

A federated credential tells Entra ID which GitHub OIDC token subjects are allowed to exchange short-lived tokens for this service principal.

Common constants:

| Field | Value |
| --- | --- |
| Issuer | `https://token.actions.githubusercontent.com` |
| Audience | `api://AzureADTokenExchange` |
| Repository | `dmd0822/sparky` |
| Subject prefix | `repo:dmd0822@176645/sparky@1387525209:` |

### Subject format: immutable OIDC claims

GitHub Actions issues this repository's OIDC tokens with **immutable subject claims**. The `sub` claim embeds numeric IDs that are never reused:

```
repo:<OWNER>@<OWNER_ID>/<REPO>@<REPO_ID>:<context>
```

For Sparky that resolves to the prefix `repo:dmd0822@176645/sparky@1387525209:`, where `176645` is the owner ID for `dmd0822` and `1387525209` is the repository ID for `sparky`. The trailing `<context>` is still the usual `environment:<name>`, `ref:refs/heads/<branch>`, or `pull_request` segment.

Immutable subjects are the default for every github.com repository created on or after 2026-07-15. Sparky was created after that date, so it is opted in and the legacy `repo:<owner>/<repo>:<context>` format is **not** an alternative here — Entra ID rejects tokens whose subject does not match a federated credential exactly.

Re-derive the IDs at any time:

```bash
gh api repos/dmd0822/sparky --jq '{owner_id: .owner.id, repo_id: .id}'
```

If this app registration is ever pointed at a different repository — or the repository is recreated — re-run that command and update every federated credential subject with the new IDs. Renaming the owner or repository does **not** change the IDs, which is the point of the immutable format.

See [Immutable subject claims for GitHub Actions workload identity federation](https://learn.microsoft.com/en-us/entra/workload-id/workload-identities-github-immutable-subjects) for the full specification.

### Recommended Sparky credentials

Create separate credentials for each trust boundary you need. Environment-based credentials are recommended for deploy jobs because Sparky already has `dev` and `prod` GitHub Environments.

If this app registration already has federated credentials, the `create` commands below fail because the names are taken. Skip to [Updating credentials that already exist](#updating-credentials-that-already-exist).

**Bash / zsh:**
```bash
cat > github-dev-federated-credential.json <<'JSON'
{
  "name": "github-env-dev",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:dmd0822@176645/sparky@1387525209:environment:dev",
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
  "subject": "repo:dmd0822@176645/sparky@1387525209:environment:prod",
  "audiences": ["api://AzureADTokenExchange"],
  "description": "Sparky prod environment deployments from GitHub Actions"
}
JSON

az ad app federated-credential create \
  --id "$APP_OBJECT_ID" \
  --parameters @github-prod-federated-credential.json
```

**PowerShell:**
```powershell
$DevFederatedCredentialJson = @'
{
  "name": "github-env-dev",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:dmd0822@176645/sparky@1387525209:environment:dev",
  "audiences": ["api://AzureADTokenExchange"],
  "description": "Sparky dev environment deployments from GitHub Actions"
}
'@
$DevFederatedCredentialJson | Set-Content -Path "github-dev-federated-credential.json"

az ad app federated-credential create `
  --id $AppObjectId `
  --parameters "@github-dev-federated-credential.json"

$ProdFederatedCredentialJson = @'
{
  "name": "github-env-prod",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:dmd0822@176645/sparky@1387525209:environment:prod",
  "audiences": ["api://AzureADTokenExchange"],
  "description": "Sparky prod environment deployments from GitHub Actions"
}
'@
$ProdFederatedCredentialJson | Set-Content -Path "github-prod-federated-credential.json"

az ad app federated-credential create `
  --id $AppObjectId `
  --parameters "@github-prod-federated-credential.json"
```

Add either or both of these only if the workflow will use them:

**Bash / zsh:**
```bash
cat > github-main-federated-credential.json <<'JSON'
{
  "name": "github-main-branch",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:dmd0822@176645/sparky@1387525209:ref:refs/heads/main",
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
  "subject": "repo:dmd0822@176645/sparky@1387525209:pull_request",
  "audiences": ["api://AzureADTokenExchange"],
  "description": "Sparky pull request what-if validation from GitHub Actions"
}
JSON

az ad app federated-credential create \
  --id "$APP_OBJECT_ID" \
  --parameters @github-pr-federated-credential.json
```

**PowerShell:**
```powershell
$MainFederatedCredentialJson = @'
{
  "name": "github-main-branch",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:dmd0822@176645/sparky@1387525209:ref:refs/heads/main",
  "audiences": ["api://AzureADTokenExchange"],
  "description": "Sparky main branch automation from GitHub Actions"
}
'@
$MainFederatedCredentialJson | Set-Content -Path "github-main-federated-credential.json"

az ad app federated-credential create `
  --id $AppObjectId `
  --parameters "@github-main-federated-credential.json"

$PrFederatedCredentialJson = @'
{
  "name": "github-pull-request",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:dmd0822@176645/sparky@1387525209:pull_request",
  "audiences": ["api://AzureADTokenExchange"],
  "description": "Sparky pull request what-if validation from GitHub Actions"
}
'@
$PrFederatedCredentialJson | Set-Content -Path "github-pr-federated-credential.json"

az ad app federated-credential create `
  --id $AppObjectId `
  --parameters "@github-pr-federated-credential.json"
```

Clean up local credential JSON files when you are done if you do not want to keep them in your shell directory. They contain no secrets, but they are setup artifacts.

**Bash / zsh:**
```bash
rm -f github-*-federated-credential.json
```

**PowerShell:**
```powershell
Remove-Item -Path "github-*-federated-credential.json" -ErrorAction SilentlyContinue
```

### Updating credentials that already exist

The `create` commands above are for a first-time setup. If the app registration already has federated credentials — for example after a repository migration, or when correcting subjects that still use the legacy `repo:<owner>/<repo>:<context>` format — `create` fails because the credential names are already taken.

Use `update` instead. It patches the credential in place, so the credential name and its object ID are preserved and nothing that references them has to change. Prefer this over delete-and-recreate.

First, see what is actually there:

**Bash / zsh:**
```bash
az ad app federated-credential list \
  --id "$AppObjectId" \
  --query "[].{name:name, subject:subject, issuer:issuer}" \
  --output table
```

**PowerShell:**
```powershell
az ad app federated-credential list `
  --id $AppObjectId `
  --query "[].{name:name, subject:subject, issuer:issuer}" `
  --output table
```

Then update any credential whose subject is wrong. `--federated-credential-id` accepts either the credential name or its object ID:

**Bash / zsh:**
```bash
cat > update-env-dev.json <<'JSON'
{
  "name": "github-env-dev",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:dmd0822@176645/sparky@1387525209:environment:dev",
  "audiences": ["api://AzureADTokenExchange"],
  "description": "Sparky dev environment deployments from GitHub Actions"
}
JSON

az ad app federated-credential update \
  --id "$AppObjectId" \
  --federated-credential-id "github-env-dev" \
  --parameters "@update-env-dev.json"
```

**PowerShell:**
```powershell
$UpdateEnvDevJson = @'
{
  "name": "github-env-dev",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:dmd0822@176645/sparky@1387525209:environment:dev",
  "audiences": ["api://AzureADTokenExchange"],
  "description": "Sparky dev environment deployments from GitHub Actions"
}
'@
$UpdateEnvDevJson | Set-Content -Path "update-env-dev.json"

az ad app federated-credential update `
  --id $AppObjectId `
  --federated-credential-id "github-env-dev" `
  --parameters "@update-env-dev.json"
```

Repeat for `github-env-prod`, `github-main-branch`, and `github-pull-request`, changing only the `name`, `subject`, and `description` each time. Always pass the JSON through a file rather than inlining it — quoting rules differ between shells, and on Windows `cmd.exe` mangles inline JSON.

Re-run the `list` command afterwards and confirm every subject carries the immutable prefix.

Only fall back to deleting when a credential is genuinely obsolete — a trust boundary you no longer use, or a name you want to retire:

**Bash / zsh:**
```bash
az ad app federated-credential delete \
  --id "$AppObjectId" \
  --federated-credential-id "github-old-credential"
```

**PowerShell:**
```powershell
az ad app federated-credential delete `
  --id $AppObjectId `
  --federated-credential-id "github-old-credential"
```

Deleting a credential takes effect immediately. Any workflow whose token matched only that subject starts failing its `azure/login` step with `AADSTS700213` on the very next run, so delete before you recreate, not after.

You can do all of this in the portal instead: **Microsoft Entra ID → App registrations → your app → Certificates & secrets → Federated credentials**. Select a credential to edit its subject, or use the delete control on the row.

### Which subject should I use?

| Subject | Matches | Use when |
| --- | --- | --- |
| `repo:dmd0822@176645/sparky@1387525209:environment:dev` | Jobs that declare `environment: dev` | Dev deployments or dev what-if jobs protected by the GitHub Environment. |
| `repo:dmd0822@176645/sparky@1387525209:environment:prod` | Jobs that declare `environment: prod` | Production deployments with required reviewers. |
| `repo:dmd0822@176645/sparky@1387525209:ref:refs/heads/main` | Jobs from `main` that do **not** declare an environment and are not pull-request events | Branch-scoped automation such as main-only validation. |
| `repo:dmd0822@176645/sparky@1387525209:pull_request` | Pull request jobs that do **not** declare an environment | PR what-if validation before merge. |

Important: GitHub's default `sub` claim changes depending on job context. If a job declares an `environment`, the subject is environment-based; a PR job without an environment uses `pull_request`; a normal branch job without an environment uses `ref:refs/heads/<branch>`. Subject mismatches are the most common OIDC setup failure.

## 4. Assign Azure RBAC at resource-group scope

Prefer the narrowest scope that supports the deployment. For Sparky that is the `rg-sparky` resource group, not the whole subscription.

**Bash / zsh:**
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

**PowerShell:**
```powershell
$AzureSubscriptionId = "<your-subscription-id>"
$ResourceGroup = "rg-sparky"
$RgScope = "/subscriptions/$AzureSubscriptionId/resourceGroups/$ResourceGroup"

az role assignment create `
  --assignee-object-id $SpObjectId `
  --assignee-principal-type ServicePrincipal `
  --role "Contributor" `
  --scope $RgScope
```

`Contributor` is needed for group-scope Bicep deployments that create and update Azure resources.

Sparky's Bicep is expected to create role assignments for the relay's managed identity so it can call Foundry and Speech with RBAC. A principal that creates role assignments also needs `Microsoft.Authorization/roleAssignments/write`. `Contributor` does **not** include that permission. Add a scoped RBAC role only if the Bicep deployment creates role assignments:

**Bash / zsh:**
```bash
az role assignment create \
  --assignee-object-id "$SP_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Role Based Access Control Administrator" \
  --scope "$RG_SCOPE"
```

**PowerShell:**
```powershell
az role assignment create `
  --assignee-object-id $SpObjectId `
  --assignee-principal-type ServicePrincipal `
  --role "Role Based Access Control Administrator" `
  --scope $RgScope
```

If that role is unavailable in your tenant, use `User Access Administrator` at the same resource-group scope. Avoid subscription-wide assignment unless the deployment truly needs subscription-scope changes.

## 5. Set GitHub repository secrets and variables

Use GitHub Actions secrets for the three Azure IDs and variables for non-sensitive deployment settings. OIDC means there is no secret material or long-lived password to store: the client ID and tenant ID are public identifiers, and the subscription ID is only mildly sensitive. Storing the IDs as secrets is a defensible defense-in-depth choice that keeps the subscription ID out of logs and matches Sparky's rule that it must not appear in the repo.

Trade-off: secret values are masked in workflow logs, which can make authentication failures harder to debug. Repository secrets are also not exposed to workflows triggered by `pull_request` from forks. Keep the split explicit: **the three Azure IDs are secrets; resource group and location are variables.**

The commands below prompt for the live IDs instead of using angle-bracket placeholders. Do not include quotes or brackets when pasting values at the prompt.

**Bash / zsh:**
```bash
read -r -p "Azure client ID: " AZURE_CLIENT_ID
read -r -p "Azure tenant ID: " AZURE_TENANT_ID
read -r -p "Azure subscription ID: " AZURE_SUBSCRIPTION_ID

gh secret set AZURE_CLIENT_ID --repo dmd0822/sparky --body "$AZURE_CLIENT_ID"
gh secret set AZURE_TENANT_ID --repo dmd0822/sparky --body "$AZURE_TENANT_ID"
gh secret set AZURE_SUBSCRIPTION_ID --repo dmd0822/sparky --body "$AZURE_SUBSCRIPTION_ID"
gh variable set AZURE_RESOURCE_GROUP --repo dmd0822/sparky --body "rg-sparky"
gh variable set AZURE_LOCATION --repo dmd0822/sparky --body "southcentralus"
```

**PowerShell:**
```powershell
$AzureClientId = Read-Host "Azure client ID"
$AzureTenantId = Read-Host "Azure tenant ID"
$AzureSubscriptionId = Read-Host "Azure subscription ID"

gh secret set AZURE_CLIENT_ID --repo dmd0822/sparky --body "$AzureClientId"
gh secret set AZURE_TENANT_ID --repo dmd0822/sparky --body "$AzureTenantId"
gh secret set AZURE_SUBSCRIPTION_ID --repo dmd0822/sparky --body "$AzureSubscriptionId"
gh variable set AZURE_RESOURCE_GROUP --repo dmd0822/sparky --body "rg-sparky"
gh variable set AZURE_LOCATION --repo dmd0822/sparky --body "southcentralus"
```

Do not create `AZURE_CREDENTIALS`, do not store a client secret, and do not use publish profiles.

## 6. Create GitHub Environments

The `dev` and `prod` GitHub Environments already exist in `dmd0822/sparky`.

Recommended settings:

- `dev`: no required reviewers, or lightweight reviewer rules if desired.
- `prod`: required reviewers and any deployment branch restrictions the team wants.

With GitHub CLI, create the environment records:

**Bash / zsh:**
```bash
gh api --method PUT repos/dmd0822/sparky/environments/dev
gh api --method PUT repos/dmd0822/sparky/environments/prod
```

**PowerShell:**
```powershell
gh api --method PUT repos/dmd0822/sparky/environments/dev
gh api --method PUT repos/dmd0822/sparky/environments/prod
```

Configure production protection rules in the GitHub UI unless you already have a standard API payload for reviewers. The environment names must exactly match the federated credential subjects (`dev` and `prod`). A workflow job that says `environment: production` will not match `repo:dmd0822@176645/sparky@1387525209:environment:prod`.

Known constraint: GitHub Environment protection rules such as required reviewers and wait timers require GitHub Pro for a private User-owned repository. `dmd0822/sparky` is private under a User account and no paid plan is currently detected, so `prod` approval gates may not be available. That is not a blocker for OIDC; use branch protection on `main` as the deployment gate until environment protection becomes available.

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
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

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
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

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
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

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

The PR job does not declare an environment so it can match the `repo:dmd0822@176645/sparky@1387525209:pull_request` federated credential. The deploy jobs declare `environment: dev` or `environment: prod`, so they match the environment federated credentials and can use GitHub Environment approvals.
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
| `AADSTS70021` / `AADSTS700213: No matching federated identity record found for presented assertion subject` | Most likely the federated credential was created with a legacy-format subject (no `@<owner-id>` / `@<repo-id>` segments) while this repository issues immutable subjects (`repo:dmd0822@176645/sparky@1387525209:...`). Otherwise the `sub` context, `issuer`, or `audience` does not match. | Copy the subject quoted verbatim from the error message. If the credential already exists, patch it in place with `az ad app federated-credential update` (see [Updating credentials that already exist](#updating-credentials-that-already-exist)) rather than recreating it. Confirm the immutable prefix, then check whether the job uses `environment`, `pull_request`, or a branch ref. |
| `azure/login` says it cannot get an ID token | Missing workflow permission. | Add `permissions: id-token: write` at workflow or job level. |
| Token exchange fails with audience errors | Federated credential audience differs from the action's audience. | Use `api://AzureADTokenExchange` for Azure public cloud unless intentionally targeting another cloud. |
| PR what-if fails with `AADSTS70021` after adding `environment: dev` | Environment jobs use `repo:...:environment:dev`, not `repo:...:pull_request`. | Either remove `environment` from the PR job or add an environment-scoped credential and accept environment approvals on PRs. |
| Deployment fails with authorization errors immediately after role assignment | RBAC propagation delay. | Wait a few minutes and rerun. Confirm role assignment scope is `rg-sparky`. |
| Bicep deployment fails creating role assignments | Deployment principal has `Contributor` but not role-assignment permission. | Add `Role Based Access Control Administrator` or `User Access Administrator` at resource-group scope. |
| `azure/login` fails with an unhelpful authentication error and the login step shows an empty or malformed `client-id` | Workflow references the wrong GitHub context: for example `vars.AZURE_CLIENT_ID` for a value stored as a secret, or `secrets.AZURE_RESOURCE_GROUP` for a value stored as a variable. GitHub resolves the wrong context to an empty string without warning. | Use `secrets.AZURE_CLIENT_ID`, `secrets.AZURE_TENANT_ID`, and `secrets.AZURE_SUBSCRIPTION_ID`; use `vars.AZURE_RESOURCE_GROUP` and `vars.AZURE_LOCATION`. |
| Workflow deploys to the wrong subscription | Wrong `AZURE_SUBSCRIPTION_ID` secret or stale local Azure CLI context. | Check repository secret value, environment variable overrides, and the `az account show` verification step. |
| Prod job never starts | GitHub Environment protection is waiting for approval, or protection rules are unavailable on the current plan. | Approve the deployment if the gate exists. If required reviewers/wait timers are unavailable for this private User-owned repository, use branch protection on `main` as the gate. |

## 10. Security notes

- No Azure access keys, client secrets, publish profiles, or long-lived credential blobs are required.
- Federated credentials are scoped to exact GitHub subjects and can be removed independently when a branch, environment, or repository is retired.
- Keep RBAC at `rg-sparky` scope unless a future deployment explicitly requires a broader scope.
- Prefer environment-scoped credentials for deployments and require reviewers for `prod`.
- This repository uses immutable OIDC subject claims, so federated credential subjects must carry the `@<owner-id>` and `@<repo-id>` segments. Renaming or transferring the repository does not change those IDs, but pointing the app registration at a different repository does — re-derive the IDs and update every subject before relying on deployments.
- Periodically review app registration federated credentials and remove unused subjects.
