# Azure configuration for Sparky

This project is designed around the Azure broker identity boundary described in `docs/architecture/decisions/ADR-0004-azure-broker-identity-boundary.md`:

- The PiDog device does not keep long-lived Azure keys.
- The device identifies itself with a per-device certificate.
- The broker runs in Azure and uses managed identity / Entra ID to access Azure Speech, Azure OpenAI, and Azure AI Content Safety.
- If your subscription does not support key-based access, use a keyless Azure identity path instead of API keys.
- Local development may use environment variables, but production should prefer managed identity and brokered calls.

## 1. Recommended Azure resources

Create the following Azure resources in the same subscription and region for the first deployment:

- Azure resource group
- Azure OpenAI resource
- Azure AI Content Safety resource
- Azure Speech resource
- Azure App Service / Container App / Azure Functions broker service that terminates device mTLS and calls the Azure services on behalf of the device

## 2. Local development template

Use the repo template at `.env.example` as the starting point:

```bash
cp .env.example .env
```

Then fill in your values for:

- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_CLIENT_ID`
- `AZURE_RESOURCE_GROUP`
- `AZURE_LOCATION`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_DEPLOYMENT`
- `AZURE_SPEECH_REGION`
- `AZURE_CONTENT_SAFETY_ENDPOINT`

Do not add key settings when your subscription is keyless. Keep `.env` out of source control. Do not commit real secrets.

## 3. Azure CLI quick setup with Entra ID authentication

```bash
az login
az account set --subscription "<subscription-id-or-name>"
az group create --name sparky-rg --location eastus

az cognitiveservices account create \
  --name sparky-openai \
  --resource-group sparky-rg \
  --location eastus \
  --kind OpenAI \
  --sku S0

az cognitiveservices account create \
  --name sparky-speech \
  --resource-group sparky-rg \
  --location eastus \
  --kind SpeechServices \
  --sku S0

az cognitiveservices account create \
  --name sparky-content-safety \
  --resource-group sparky-rg \
  --location eastus \
  --kind ContentSafety \
  --sku S0
```

Then assign the broker identity access instead of using keys:

```bash
# Example: create a managed identity for the broker app/service
az identity create --name sparky-broker-mi --resource-group sparky-rg

# Example: grant the identity Cognitive Services access
az role assignment create \
  --assignee-object-id <managed-identity-object-id> \
  --assignee-principal-type ServicePrincipal \
  --role "Cognitive Services OpenAI User" \
  --scope /subscriptions/<subscription-id>/resourceGroups/sparky-rg/providers/Microsoft.CognitiveServices/accounts/sparky-openai

az role assignment create \
  --assignee-object-id <managed-identity-object-id> \
  --assignee-principal-type ServicePrincipal \
  --role "Cognitive Services Speech User" \
  --scope /subscriptions/<subscription-id>/resourceGroups/sparky-rg/providers/Microsoft.CognitiveServices/accounts/sparky-speech

az role assignment create \
  --assignee-object-id <managed-identity-object-id> \
  --assignee-principal-type ServicePrincipal \
  --role "Cognitive Services Content Safety User" \
  --scope /subscriptions/<subscription-id>/resourceGroups/sparky-rg/providers/Microsoft.CognitiveServices/accounts/sparky-content-safety
```

If your environment uses an app registration instead of a managed identity, the same principle applies: authenticate via Entra ID and grant the app the equivalent RBAC roles; do not depend on API keys.

## 4. Deploying the model

For Azure OpenAI, create a deployment for the model the broker will use:

```bash
az cognitiveservices account deployment create \
  --name sparky-gpt-4o-mini \
  --resource-group sparky-rg \
  --account-name sparky-openai \
  --model-name gpt-4o-mini \
  --model-version "<version>" \
  --model-format OpenAI
```

If your tenant uses a different model family or version, substitute the correct values from the Azure OpenAI deployment page.

## 5. Production security model

The shipping setup should be:

- the device holds only a per-device certificate
- the broker uses Azure managed identity
- the broker owns all Azure endpoint configuration
- the broker enforces rate limits, per-turn cost tracking, and content safety checks
- the device never stores Azure keys or connection strings

This matches the design in `ADR-0004` and keeps Azure access isolated behind the broker boundary.

## 6. Minimal validation

After creation, verify:

```bash
az account show
az cognitiveservices account show --name sparky-openai --resource-group sparky-rg
az cognitiveservices account show --name sparky-speech --resource-group sparky-rg
az cognitiveservices account show --name sparky-content-safety --resource-group sparky-rg
```

If the broker is already deployed, validate the endpoint returns healthy responses from the Azure-managed service boundary, not from the Pi itself.
