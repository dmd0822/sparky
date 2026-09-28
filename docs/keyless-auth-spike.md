# Keyless auth proof-of-path spike

This spike proves the Pi-to-relay-to-Foundry/Speech path for GitHub issue #4. The security property is: **the Pi never receives Azure AI bearer tokens, API keys, or connection strings**. The Pi authenticates only to the relay; the relay uses its managed identity and RBAC for Azure AI resources.

## Three-hop token model

| Hop | Identity holding credential | Credential type | Audience | Scope | Must never be |
| --- | --- | --- | --- | --- | --- |
| 1. Pi to relay | Raspberry Pi public client | Microsoft Entra device-code access token | Relay app registration, for example `api://<relay-app-id>` | `api://<relay-app-id>/.default` or delegated `api://<relay-app-id>/user_impersonation` | Azure AI bearer token, subscription key, client secret, or connection string |
| 2. Relay to Foundry | Relay Container App system-assigned managed identity | Managed identity access token | `https://cognitiveservices.azure.com` | `https://cognitiveservices.azure.com/.default` | User/device token, API key, or connection string |
| 3. Relay to Speech | Relay Container App system-assigned managed identity | Managed identity access token | `https://cognitiveservices.azure.com` | `https://cognitiveservices.azure.com/.default` | User/device token, API key, or connection string |

The helper module now enforces this split with `SPARKY_RELAY_DEVICE_SCOPE`, `SPARKY_FOUNDRY_SCOPE`, and `SPARKY_SPEECH_SCOPE`. It raises if the device-hop scope resolves to an Azure AI or Cognitive Services audience.

## Raspberry Pi enrollment steps

1. Register or reuse the relay API app registration in the Sparky tenant.
2. Expose a relay-only API scope such as `api://<relay-app-id>/.default` or a delegated scope such as `api://<relay-app-id>/user_impersonation`.
3. Register the Pi application as a public client that is allowed to use device code flow for the relay API scope. Do not create a client secret for the Pi.
4. Configure the Pi with only these non-secret values: `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `SPARKY_RELAY_URL`, and `SPARKY_RELAY_DEVICE_SCOPE`.
5. The user completes device-code sign-in. The resulting Pi token is a relay-audience token only.
6. The Pi sends that relay token to the relay. The relay validates issuer and audience before calling Azure AI resources with managed identity.

## Relay configuration

Set these environment variables for the local smoke manifest or relay runtime:

```bash
export AZURE_TENANT_ID="<tenant-id>"
export AZURE_CLIENT_ID="<pi-public-client-id>"
export SPARKY_RELAY_URL="https://<relay-host>/api"
export SPARKY_RELAY_AUDIENCE="api://<relay-app-id>"
export SPARKY_RELAY_DEVICE_SCOPE="api://<relay-app-id>/.default"
export SPARKY_FOUNDRY_SCOPE="https://cognitiveservices.azure.com/.default"
export SPARKY_SPEECH_SCOPE="https://cognitiveservices.azure.com/.default"
```

```powershell
$env:AZURE_TENANT_ID = "<tenant-id>"
$env:AZURE_CLIENT_ID = "<pi-public-client-id>"
$env:SPARKY_RELAY_URL = "https://<relay-host>/api"
$env:SPARKY_RELAY_AUDIENCE = "api://<relay-app-id>"
$env:SPARKY_RELAY_DEVICE_SCOPE = "api://<relay-app-id>/.default"
$env:SPARKY_FOUNDRY_SCOPE = "https://cognitiveservices.azure.com/.default"
$env:SPARKY_SPEECH_SCOPE = "https://cognitiveservices.azure.com/.default"
```

`AZURE_COGNITIVE_SCOPE` remains accepted only as a compatibility alias for the two downstream managed-identity scopes. It is never used as the device-code scope.

## Infrastructure evidence

The infra side is already complete and is treated as evidence, not reworked here:

- `infra/modules/ai-services.bicep` sets `disableLocalAuth: true` on the AI Services account.
- `infra/modules/speech.bicep` sets `disableLocalAuth: true` on the Speech account.
- `infra/modules/rbac.bicep` assigns the relay managed identity the `Cognitive Services User` role definition `a97b65f3-24c7-4388-baec-2e87135dc908` scoped separately to the AI Services account and the Speech account.

## Speech Microsoft Entra auth finding

Current Microsoft Learn guidance for Speech Entra authentication was checked during this correction. The current SDK guidance for Python, C#, Java, and C++ prefers constructing Speech configuration with a `TokenCredential` and the Speech custom-domain endpoint. The same page still documents the resource-ID token wrapper for REST or legacy authorization-token paths: `aad#<speech-resource-id>#<aad-access-token>`.

Implication for Sparky: the relay should use SDK-native `TokenCredential` when the chosen Speech SDK path supports it. If a selected Speech SDK feature or endpoint only accepts the authorization-token property, the relay must wrap its managed-identity Entra token as `aad#<speech-resource-id>#<aad-access-token>`. If any required Foundry or Speech call cannot run without key-based auth, that is a blocking finding and must not be hidden behind a fallback.

## Explicitly ruled out

| Ruled-out path | Why it is rejected |
| --- | --- |
| Pi requests `https://cognitiveservices.azure.com/.default` directly | This gives the Pi an Azure AI bearer token and bypasses the relay security boundary. |
| Speech or Foundry subscription keys | Keys are long-lived shared credentials and local auth is disabled in Bicep. |
| Connection strings for runtime Azure AI access | Connection strings are secret material and create an untracked fallback path. |
| Pi client secret | The Pi is a public client; storing a secret on device hardware is not defensible. |
| Speech STS key-to-token exchange | It starts with a Speech resource key and violates the no-key baseline. |

## Negative-case key fallback verification

`src/cloud/sparky_relay/keyless_guard.py` scans executable code, config, workflows, and Bicep surfaces for key-based fallback markers including subscription-key headers, subscription-key properties, Speech key environment variables, Azure OpenAI key environment variables, generic API-key variables, `listKeys(`, account-key connection strings, and connection-string assignments. Markdown prose is intentionally not scanned so the design can name forbidden mechanisms in this ruled-out section.

Run the guard through unittest:

```powershell
python -m unittest tests.test_keyless_guard -v
```

The full repository validation command also runs this guard.

## Deployment target and naming

| Setting | Required value |
| --- | --- |
| Resource group | `rg-sparky` |
| Region | South Central US, `southcentralus` |
| Subscription in GitHub Actions | `AZURE_SUBSCRIPTION_ID` repository secret consumed by the workflow |
| Subscription locally | Active CLI context selected by `az account set --subscription <subscription-id>` |
| General naming | `sparky-<resource>-<env>` |
| ACR-style constrained naming | `sparkyscr<env>` |

Do not commit a subscription GUID into sample code, Bicep parameters, workflow YAML, or docs. `tests/test_infra_policy.py::test_no_hard_coded_subscription_guids_under_infra` enforces the infra half of this rule.

## South Central US quota and feature gaps

Expected South Central US caveats remain:

- Foundry model deployment availability and capacity are quota-sensitive. Verify the exact model family, version, deployment type, and capacity immediately before deployment.
- Core Azure Speech STT/TTS is expected in South Central US, but advanced Speech features may be unavailable there. The architecture decision already calls out gaps such as LLM speech, MAI voices, HD voices, Azure OpenAI voices, personal voice, voice conversion, custom voice HD endpoints, preview voices/styles, and avatar voice sync.
- If the required demo model or Speech feature is not available in South Central US, record it as a blocking or alternate-region decision before adding any fallback.

## Reproducible smoke test

The helper is import-safe and does not contact Azure when printing the demo manifest.

```powershell
$env:PYTHONPATH = "src\cloud"
$env:AZURE_TENANT_ID = "<tenant-id>"
$env:AZURE_CLIENT_ID = "<pi-public-client-id>"
$env:SPARKY_RELAY_URL = "https://<relay-host>/api"
$env:SPARKY_RELAY_AUDIENCE = "api://<relay-app-id>"
$env:SPARKY_RELAY_DEVICE_SCOPE = "api://<relay-app-id>/.default"
$env:SPARKY_FOUNDRY_SCOPE = "https://cognitiveservices.azure.com/.default"
$env:SPARKY_SPEECH_SCOPE = "https://cognitiveservices.azure.com/.default"
python -m sparky_relay.keyless_auth --print-demo
```

Hardware or cloud smoke sequence:

1. Select the subscription locally with `az account set --subscription <subscription-id>` or use the `AZURE_SUBSCRIPTION_ID` repository secret in Actions.
2. Deploy the relay, AI Services account, and Speech account into `rg-sparky` in `southcentralus` with environment-suffixed names.
3. Confirm local auth is disabled on both AI resources and that the relay principal has `Cognitive Services User` scoped to each resource.
4. On the Pi, run device-code sign-in for `SPARKY_RELAY_DEVICE_SCOPE` only.
5. Call `POST /ai/chat` on the relay with the relay-audience token and verify the relay completes one Foundry call with managed identity.
6. Call `POST /speech/synthesize` on the relay with the same relay-audience token and verify the relay completes one Speech call with managed identity.
7. Inspect relay logs for token purpose, issuer, and audience only. Do not log token values.
8. Run the unittest suite before and after the smoke test:

```powershell
python -m unittest discover -s tests -v
```

## Hardware-in-the-loop validation

Full Pi validation is not appropriate for CI because it requires interactive device-code login, a physical Pi, audio hardware, and live Azure quota. The reproducible manual HIL pass should capture:

- Pi hostname or asset tag, without secrets or personal data.
- Relay URL and environment name.
- Device-code token audience showing the relay app registration, not Azure AI.
- Foundry smoke response status through the relay.
- Speech smoke response status or synthesized audio artifact through the relay.
- Confirmation that no subscription key, API key, client secret, or connection string was configured on the Pi.

## Blocking findings and open risks

- Blocking findings: none in the static spike. The current Microsoft docs provide keyless Speech SDK and REST/legacy token paths, and the infra disables local auth for AI and Speech.
- Open risk: the concrete Foundry model deployment and Speech feature set still need live South Central US quota validation immediately before deployment.
- Open risk: production relay code must perform full JWT signature validation against Entra signing keys. The spike helper only decodes unsigned claims for deterministic unit tests.
- Open risk: if a later Speech or Foundry SDK surface requires subscription-key auth for a required feature, that is a blocking finding, not an exception path.
