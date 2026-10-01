# Keyless auth testing guide

This is the procedural companion to the [keyless auth proof-of-path spike](keyless-auth-spike.md). Use it to test the Pi → relay → Foundry/Speech path without re-reading the design rationale.

The security goal is simple: the Pi receives only a relay-audience token. The relay, not the Pi, uses managed identity to obtain downstream tokens for Foundry and Speech.

## Local testing from a laptop

These checks prove the static and import-safe parts of the spike. They do not contact Azure, deploy resources, prove South Central US model quota, prove Speech feature availability, or prove real RBAC propagation.

### What you need before you start

1. A Windows PowerShell session at the repository root.
2. Python available as `python`.
3. No Pi hardware.
4. No Azure spend for the unittest, demo-manifest, keyless-guard, or device-scope guard checks.

### Step 1: Run the unittest suite

Run this in Windows PowerShell:

```powershell
python -m unittest discover -s tests
```

Expected result:

- The suite ends with `OK`.
- At the time this guide was written, the suite reports `Ran 79 tests`.

How to tell it failed:

- Any `FAILED`, `ERROR`, or traceback means the repository is not in a clean testable state.
- A failure in `tests.test_keyless_guard` means code, config, infra, or workflow YAML likely reintroduced a key-based Azure AI fallback marker.
- A failure in `tests.test_docs_policy` means a documentation policy rule was violated, such as malformed Markdown tables or incorrect GitHub Actions terminology.

### Step 2: Print the demo manifest without contacting Azure

The CLI lives under `src\cloud`, so set `PYTHONPATH` in the same PowerShell session before running `python -m`.

Run this in Windows PowerShell:

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

Expected result:

- The command exits with status `0`.
- It prints JSON with `device_code_url`, `token_url`, `relay_url`, `device_code_payload`, `hop_tokens`, `relay_payloads`, and `curl_example`.
- `device_code_payload.scope` is `api://<relay-app-id>/.default`.
- `hop_tokens.pi_to_relay.audience` is `api://<relay-app-id>`.
- `hop_tokens.relay_to_foundry.scope` and `hop_tokens.relay_to_speech.scope` are `https://cognitiveservices.azure.com/.default`.

How to tell it failed:

- `No module named sparky_relay` means `PYTHONPATH` was not set to `src\cloud` in the same shell process.
- `Configuration error: Missing required configuration values: ...` means one or more required settings were omitted.
- `Configuration error: Device-hop scope must target the relay app registration, not Azure AI.` means `SPARKY_RELAY_DEVICE_SCOPE` was set to an Azure AI audience instead of the relay app registration.
- Any output that gives the Pi a Cognitive Services or Azure AI scope is a security failure.

### Step 3: Prove the keyless guard is non-vacuous

This check deliberately creates a scratch Python file under `src\cloud\sparky_relay`, verifies that the static guard catches it, and then deletes it. Do not commit the scratch file.

Run this in Windows PowerShell:

```powershell
$probe = "src\cloud\sparky_relay\_keyless_guard_probe.py"
Set-Content -Path $probe -Value "headers = {'Ocp-Apim-Subscription-Key': configured_key}`n" -Encoding UTF8
try {
    $env:PYTHONPATH = "src\cloud"
    @'
from pathlib import Path
from sparky_relay.keyless_guard import assert_no_key_fallbacks

try:
    assert_no_key_fallbacks(Path.cwd())
except AssertionError as exc:
    print(type(exc).__name__ + ":")
    print(exc)
'@ | python -
}
finally {
    Remove-Item -Path $probe -Force
}
```

Expected result:

- The command prints `KeyFallbackPolicyError:`.
- The error includes the scratch path, line number, and `subscription-key-header`.
- The scratch file is removed by the `finally` block.

The expected finding looks like this:

```text
KeyFallbackPolicyError:
Key-based Azure AI auth fallback detected in code/config/infra:
src\cloud\sparky_relay\_keyless_guard_probe.py:1: subscription-key-header: headers = {'Ocp-Apim-Subscription-Key': configured_key}
```

How to tell it failed:

- No `KeyFallbackPolicyError` means the guard did not catch an intentional forbidden fallback and must not be trusted.
- A remaining `_keyless_guard_probe.py` file means cleanup did not run; delete it before continuing.
- A finding in any file other than the scratch file means the working tree already contains key-based fallback text and must be fixed.

### Step 4: Prove the device-scope guard rejects Azure AI audiences

Run this in Windows PowerShell:

```powershell
$env:PYTHONPATH = "src\cloud"
@'
from sparky_relay.keyless_auth import AzureRelayConfig

try:
    AzureRelayConfig(
        tenant_id="<tenant-id>",
        client_id="<pi-public-client-id>",
        relay_url="https://<relay-host>/api",
        device_scope="https://cognitiveservices.azure.com/.default",
    )
except ValueError as exc:
    print(type(exc).__name__ + ": " + str(exc))
'@ | python -
```

Expected result:

```text
ValueError: Device-hop scope must target the relay app registration, not Azure AI.
```

How to tell it failed:

- No `ValueError` means the guard accepted a forbidden Pi scope.
- A different import error usually means `PYTHONPATH` is missing.
- This check does not prove live Entra token issuance; it proves the local configuration guard rejects a dangerous audience before the Pi asks for a token.

## Pi testing with deployed relay and Azure resources

These steps are the hardware-in-the-loop pass. They require a deployed relay environment and live Azure resources. They are the only way to prove real device-code sign-in, live relay validation, managed-identity token acquisition, RBAC assignment behavior, Foundry quota, and Speech feature availability.

### What you need before you start

1. A Raspberry Pi prepared for Sparky development.
2. A deployed relay reachable at `https://<relay-host>/api`.
3. A relay API app registration with a relay-only scope such as `api://<relay-app-id>/.default`.
4. A Pi public-client app registration allowed to use device code flow. Do not configure a client secret on the Pi.
5. Relay resources deployed to `rg-sparky` in `southcentralus` using the naming convention from the spike doc.
6. The relay Container App running with a system-assigned managed identity.
7. `Cognitive Services User` assigned to the relay managed identity on both the Foundry or AI Services account and the Speech account.
8. Local operators should select the subscription with `az account set --subscription <subscription-id>`. GitHub Actions should read `AZURE_SUBSCRIPTION_ID` from the repository secret.

### Relay-side downstream configuration

Set these only on the deployed relay Container App. They are relay-side downstream settings, not Pi settings. The Pi must continue to hold only the relay-facing values from Step 1.

| Env var | Default | Purpose |
|---|---|---|
| `SPARKY_CHAT_DEPLOYMENT` | `""` | Foundry chat deployment name. Operator-supplied; chat returns `chat_not_configured` when unset. |
| `SPARKY_CHAT_API_VERSION` | `2024-10-21` | Azure OpenAI chat-completions API version. |
| `SPARKY_SPEECH_ENDPOINT` | `""` | Speech resource endpoint. Speech returns `speech_not_configured` when unset. |
| `SPARKY_SPEECH_RESOURCE_ID` | `""` | Speech resource ARM resource ID. When set, the relay wraps the managed-identity token as `Bearer aad#<resource-id>#<token>` for regional Speech resources. When unset, the relay passes through plain `Bearer <token>`, which requires a Speech resource with a custom subdomain. |
| `SPARKY_SPEECH_VOICE` | `en-US-AvaMultilingualNeural` | Text-to-speech voice. |
| `SPARKY_SPEECH_OUTPUT_FORMAT` | `riff-24khz-16bit-mono-pcm` | Text-to-speech output format. The relay's returned `audio_format` should match the configured format family; the default response reports `wav`. |

Do not copy any of these values to the Pi. If the Pi needs one of these values to complete a test, the test is no longer proving the intended keyless relay boundary.

### Primary path: run the relay-auth smoke harness

The preferred Pi validation path is the runnable harness, which automates Steps
1-5 below plus the negative-auth matrix from the architecture checklist:

```bash
export AZURE_TENANT_ID="<tenant-id>"
export AZURE_CLIENT_ID="<pi-public-client-id>"
export SPARKY_RELAY_URL="https://<relay-host>/api"
export SPARKY_RELAY_AUDIENCE="api://<relay-app-id>"
export SPARKY_RELAY_DEVICE_SCOPE="api://<relay-app-id>/.default"
python scripts/relay_auth_smoke.py
```

The script prints the device-code `user_code` and `verification_uri`, polls for
the relay-audience access token without logging it, checks the token audience,
calls `GET /health`, `POST /ai/chat`, `POST /ai/vision`, and
`POST /speech/synthesize`, then replays each endpoint with missing, malformed,
expired, Microsoft Graph-audience, and missing-grant tokens. It exits non-zero
on any failed smoke step and prints a checklist mapped back to the verification
items below.

For CI or laptop rehearsal with no Pi, no Azure, and no network calls, run:

```bash
python scripts/relay_auth_smoke.py --ci
```

The manual curl steps remain below as the fallback and as an explanation of what
the harness automates.

### Creating the two app registrations

Items 3 and 4 above are Microsoft Entra objects. Bicep does not manage them, because the `Microsoft.Graph` Bicep extension is still preview, so they are created once per tenant with the CLI and their IDs are then passed into deployments as parameters. Nothing created here is a secret: app IDs and identifier URIs are public identifiers, but they are tenant-specific, so keep the real values out of the repo.

**Bash / zsh:**

```bash
# 1. Relay API app registration.
RELAY_APP_ID=$(az ad app create \
  --display-name "sparky-relay-api" \
  --sign-in-audience AzureADMyOrg \
  --query appId --output tsv)
RELAY_OBJ_ID=$(az ad app show --id "$RELAY_APP_ID" --query id --output tsv)

# identifierUris cannot be set at create time because it embeds the appId,
# which does not exist until after creation. Patch it, and expose one scope.
SCOPE_ID=$(python3 -c "import uuid; print(uuid.uuid4())")
cat > /tmp/relay-patch.json <<JSON
{
  "identifierUris": ["api://${RELAY_APP_ID}"],
  "api": {
    "requestedAccessTokenVersion": 2,
    "oauth2PermissionScopes": [{
      "id": "${SCOPE_ID}",
      "value": "Relay.Invoke",
      "type": "User",
      "isEnabled": true,
      "adminConsentDisplayName": "Invoke the Sparky relay",
      "adminConsentDescription": "Allows the caller to invoke Sparky relay routes.",
      "userConsentDisplayName": "Invoke the Sparky relay",
      "userConsentDescription": "Allows the app to invoke Sparky relay routes."
    }]
  }
}
JSON
az rest --method PATCH \
  --url "https://graph.microsoft.com/v1.0/applications/${RELAY_OBJ_ID}" \
  --headers "Content-Type=application/json" \
  --body @/tmp/relay-patch.json

# 2. Pi public client, device code flow enabled, no secret.
PI_APP_ID=$(az ad app create \
  --display-name "sparky-pi-device" \
  --is-fallback-public-client true \
  --public-client-redirect-uris "https://login.microsoftonline.com/common/oauth2/nativeclient" \
  --query appId --output tsv)

# 3. Service principals for both apps.
az ad sp create --id "$RELAY_APP_ID"
az ad sp create --id "$PI_APP_ID"

echo "SPARKY_RELAY_AUDIENCE=api://${RELAY_APP_ID}"
echo "AZURE_CLIENT_ID=${PI_APP_ID}"
```

**PowerShell:**

```powershell
# 1. Relay API app registration.
$RelayAppId = az ad app create `
  --display-name "sparky-relay-api" `
  --sign-in-audience AzureADMyOrg `
  --query appId --output tsv
$RelayObjId = az ad app show --id $RelayAppId --query id --output tsv

$ScopeId = [guid]::NewGuid().ToString()
$Patch = @{
  identifierUris = @("api://$RelayAppId")
  api = @{
    requestedAccessTokenVersion = 2
    oauth2PermissionScopes = @(@{
      id = $ScopeId
      value = "Relay.Invoke"
      type = "User"
      isEnabled = $true
      adminConsentDisplayName = "Invoke the Sparky relay"
      adminConsentDescription = "Allows the caller to invoke Sparky relay routes."
      userConsentDisplayName = "Invoke the Sparky relay"
      userConsentDescription = "Allows the app to invoke Sparky relay routes."
    })
  }
} | ConvertTo-Json -Depth 8
# WriteAllText avoids the BOM that Out-File adds, which Graph rejects.
[System.IO.File]::WriteAllText("$env:TEMP\relay-patch.json", $Patch)
az rest --method PATCH `
  --url "https://graph.microsoft.com/v1.0/applications/$RelayObjId" `
  --headers "Content-Type=application/json" `
  --body "@$env:TEMP\relay-patch.json"

# 2. Pi public client, device code flow enabled, no secret.
$PiAppId = az ad app create `
  --display-name "sparky-pi-device" `
  --is-fallback-public-client true `
  --public-client-redirect-uris "https://login.microsoftonline.com/common/oauth2/nativeclient" `
  --query appId --output tsv

# 3. Service principals for both apps.
az ad sp create --id $RelayAppId
az ad sp create --id $PiAppId

Write-Host "SPARKY_RELAY_AUDIENCE=api://$RelayAppId"
Write-Host "AZURE_CLIENT_ID=$PiAppId"
```

Then grant the Pi client consent to call the relay scope, and **verify it actually applied**:

```bash
az ad app permission grant \
  --id "$PI_APP_ID" \
  --api "$RELAY_APP_ID" \
  --scope "Relay.Invoke"

PI_SP_ID=$(az ad sp show --id "$PI_APP_ID" --query id --output tsv)
az rest --method GET \
  --url "https://graph.microsoft.com/v1.0/servicePrincipals/${PI_SP_ID}/oauth2PermissionGrants"
```

Two CLI behaviours to watch for, both of which fail silently:

- `az ad app permission admin-consent` can exit `0` without creating a grant. Always re-read `oauth2PermissionGrants` as shown above. If the list is empty, POST the grant directly to `https://graph.microsoft.com/v1.0/oauth2PermissionGrants` with `clientId` set to the Pi service principal object ID, `resourceId` set to the relay service principal object ID, `consentType` set to `AllPrincipals`, and `scope` set to `Relay.Invoke`.
- `az ad app create --required-resource-accesses @file.json` is ignored on some CLI versions; the manifest comes back `[]`. Verify with `az ad app show --id "$PI_APP_ID" --query requiredResourceAccess`, and patch `/applications/{objectId}` if it is empty.

Record the two printed values. `SPARKY_RELAY_AUDIENCE` is passed to `infra-cd` as the `relayAudience` template parameter, and `AZURE_CLIENT_ID` is configured on the Pi in Step 1 below.

### Step 1: Configure only relay-facing values on the Pi

The smoke harness performs this preflight automatically. If running the manual
fallback, configure the same relay-facing values yourself.

Run this on the Pi in a Linux shell:

```bash
export AZURE_TENANT_ID="<tenant-id>"
export AZURE_CLIENT_ID="<pi-public-client-id>"
export SPARKY_RELAY_URL="https://<relay-host>/api"
export SPARKY_RELAY_AUDIENCE="api://<relay-app-id>"
export SPARKY_RELAY_DEVICE_SCOPE="api://<relay-app-id>/.default"
```

Expected result:

- The Pi has only tenant, public-client, relay URL, relay audience, and relay scope settings.
- No downstream Foundry or Speech scope is needed on the Pi.
- No key, token, client secret, or connection string is stored on the Pi.

How to tell it failed:

- If the Pi has any Azure AI scope, API key, subscription key, client secret, or connection string configured, stop and remove it before testing.
- If `SPARKY_RELAY_DEVICE_SCOPE` starts with `https://cognitiveservices.azure.com`, `https://ai.azure.com`, or `https://cognitive.microsoft.com`, the Pi is configured for the wrong audience.

### Step 2: Request a device code for the relay audience

The smoke harness performs this request automatically and prints the user code
and verification URI. The curl command below is the manual fallback.

Run this on the Pi in a Linux shell:

```bash
curl -sS -X POST "https://login.microsoftonline.com/${AZURE_TENANT_ID}/oauth2/v2.0/devicecode" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "client_id=${AZURE_CLIENT_ID}" \
  --data-urlencode "scope=${SPARKY_RELAY_DEVICE_SCOPE}"
```

Expected result:

- The response includes `device_code`, `user_code`, `verification_uri`, `expires_in`, `interval`, and `message`.
- The human tester can open the verification URI and enter the user code.
- The requested scope is the relay app scope, not a Cognitive Services scope.

How to tell it failed:

- `invalid_client` usually means the public-client app ID is wrong or device code flow is not allowed.
- `invalid_scope` usually means the relay scope was not exposed or the Pi app is not allowed to request it.
- Any instruction to request a Cognitive Services scope means the test is no longer validating the intended boundary.

### Step 3: Exchange the device code for a relay-audience token

The smoke harness polls this endpoint automatically and never prints the access
token. The curl command below is the manual fallback.

Use the `device_code` value returned by Step 2. Do not paste the resulting access token into logs, documentation, issue comments, or chat.

Run this on the Pi in a Linux shell:

```bash
export SPARKY_DEVICE_CODE="<device-code-from-step-2>"
curl -sS -X POST "https://login.microsoftonline.com/${AZURE_TENANT_ID}/oauth2/v2.0/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=urn:ietf:params:oauth:grant-type:device_code" \
  --data-urlencode "client_id=${AZURE_CLIENT_ID}" \
  --data-urlencode "device_code=${SPARKY_DEVICE_CODE}"
```

Expected result:

- After the human completes sign-in, the response includes an `access_token`.
- That token is for the relay app audience.
- The Pi still has no Azure AI bearer token, key, client secret, or connection string.

How to tell it failed:

- `authorization_pending` means the human has not completed browser sign-in yet; wait for the returned interval and retry.
- `expired_token` means the device code expired; repeat Step 2.
- `invalid_grant` can mean the wrong device code was used or the flow was already completed.

### Step 4: Call the relay Foundry path

The smoke harness calls this path and also checks correlation-ID echo and
response-body leakage. The curl command below is the manual fallback.

Set `SPARKY_RELAY_ACCESS_TOKEN` from the Step 3 response without writing it to disk.

Run this on the Pi in a Linux shell:

```bash
export SPARKY_RELAY_ACCESS_TOKEN="<relay-audience-access-token>"
curl -sS -X POST "${SPARKY_RELAY_URL}/ai/chat" \
  -H "Authorization: Bearer ${SPARKY_RELAY_ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{"prompt":"health check"}'
```

Expected result:

- The relay accepts the Pi token after validating issuer and audience.
- The relay calls Foundry with its managed identity.
- A live success is HTTP `200` with a JSON body containing a non-empty `reply` string and a `correlation_id` matching the request correlation ID if one was sent.
- HTTP `200` with an empty `reply` plus `status` and `metadata` means the downstream call failed and the relay degraded gracefully instead of raising. `chat_not_configured` in that metadata means `SPARKY_CHAT_DEPLOYMENT` is unset on the relay.

How to tell it failed:

- `401` or `403` at the relay usually means the Pi token issuer or audience does not match the relay configuration.
- A downstream authorization failure after relay validation usually means RBAC has not propagated or the relay managed identity lacks `Cognitive Services User` on the Foundry or AI Services account.
- A model-not-found or quota error is a live South Central US Foundry availability issue, not a reason to add key auth.

### Step 5: Call the relay Speech path

The smoke harness calls this path and also checks correlation-ID echo and
response-body leakage. The curl command below is the manual fallback.

This command reuses `SPARKY_RELAY_ACCESS_TOKEN` from Step 4. If you are starting here directly, set it from the Step 3 token response before running the command.

Run this on the Pi in a Linux shell:

```bash
curl -sS -X POST "${SPARKY_RELAY_URL}/speech/synthesize" \
  -H "Authorization: Bearer ${SPARKY_RELAY_ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{"text":"Sparky keyless speech smoke test"}'
```

Expected result:

- The relay accepts the same relay-audience Pi token.
- The relay calls Speech with its managed identity.
- A live success is HTTP `200` with a JSON body containing non-empty base64 `audio`, an `audio_format` matching `SPARKY_SPEECH_OUTPUT_FORMAT` (the default response reports `wav`), and a `correlation_id` matching the request correlation ID if one was sent.
- `speech_not_configured` means `SPARKY_SPEECH_ENDPOINT` is unset on the relay.
- To sanity-check a saved response, run `jq -r '.audio' speech-response.json | base64 -d > relay-speech.wav && test -s relay-speech.wav && wc -c relay-speech.wav`; the decoded file should be non-trivially sized.

How to tell it failed:

- `401` or `403` at the relay points to Pi token issuer or audience validation.
- A downstream Speech authorization failure points to RBAC scope, RBAC propagation, endpoint, or managed identity configuration.
- If Speech returns downstream `401` after the relay authenticated the Pi, confirm the environment's token form: set `SPARKY_SPEECH_RESOURCE_ID` for regional or non-custom-subdomain Speech resources so the relay sends `Bearer aad#<resource-id>#<token>`; leave it unset only when the Speech resource has a custom subdomain and accepts a plain `Bearer <token>`.
- A Speech feature error may reflect regional feature availability. Core STT/TTS and advanced Speech feature availability must be checked live; do not infer it from local tests.

### Step 6: Verify relay logs without exposing token values

Use the relay's configured log destination. Log only token purpose, issuer, audience, subject or app identity, operation, and downstream status. Do not log raw bearer tokens.

Expected result:

- For Pi → relay, logs show a token holder of the Raspberry Pi public client and an audience of `api://<relay-app-id>`.
- For relay → Foundry, logs show the relay system-assigned managed identity requesting `https://cognitiveservices.azure.com/.default`.
- For relay → Speech, logs show the relay system-assigned managed identity requesting `https://cognitiveservices.azure.com/.default`.
- No log entry contains an API key, subscription key, client secret, connection string, or bearer token value.

How to tell it failed:

- Any log line that shows the Pi holding a Cognitive Services or Azure AI token is a security failure.
- Any raw token value in logs is a logging bug and must be removed before another test pass.
- Any key or connection-string material in relay configuration means the environment is not keyless.

### Step 7: Confirm no key material exists on the Pi

Run this on the Pi in a Linux shell:

```bash
env | grep -E 'AZURE|SPARKY|SPEECH|OPENAI|COGNITIVE'
```

Expected result:

- You see only relay-facing Sparky and Entra public-client settings plus temporary relay-token state if you kept it in memory.
- You do not see key, token, secret, or connection-string settings for Foundry, Speech, Azure OpenAI, or Cognitive Services.

How to tell it failed:

- Any setting name or value that represents an API key, subscription key, client secret, connection string, or Azure AI bearer token must be removed from the Pi.
- If a shell history file captured token export commands, clear the token value from history before preserving the test evidence.

## Verification checklist

Tick these after a complete pass:

- [ ] `python -m unittest discover -s tests` passed locally.
- [ ] `python -m sparky_relay.keyless_auth --print-demo` printed the three-hop manifest without contacting Azure.
- [ ] The keyless guard caught the deliberate scratch-file fallback and the scratch file was removed.
- [ ] The device-scope guard rejected `https://cognitiveservices.azure.com/.default`.
- [ ] Pi device-code enrollment requested only `api://<relay-app-id>/.default` or an equivalent relay app scope.
- [ ] The Pi never received an Azure AI bearer token, API key, subscription key, client secret, or connection string.
- [ ] The relay validated the Pi token issuer and relay audience before downstream calls.
- [ ] The relay used its system-assigned managed identity for Foundry.
- [ ] The relay used its system-assigned managed identity for Speech.
- [ ] Chat returned HTTP `200` with a non-empty live `reply` and the expected `correlation_id`.
- [ ] Speech returned HTTP `200` with decodable non-empty `audio`, the expected `audio_format`, and the expected `correlation_id`.
- [ ] The Speech authorization form was confirmed for the environment: `aad#<resource-id>#<token>` when `SPARKY_SPEECH_RESOURCE_ID` is set, or plain `Bearer <token>` only for a custom-subdomain Speech resource.
- [ ] The six relay-side downstream env vars were present on the relay Container App and absent from the Pi environment.
- [ ] Relay logs showed token purpose, issuer, audience, and status only; no raw token or key material was logged.
- [ ] Foundry quota and Speech feature availability were verified in the deployed South Central US environment, or recorded as live-environment blockers.
- [ ] RBAC assignment behavior was verified in the deployed environment after propagation, or recorded as a live-environment blocker.

## Troubleshooting

### `No module named sparky_relay`

Cause: the package is under `src\cloud` locally or `src/cloud` on Linux.

Fix in Windows PowerShell:

```powershell
$env:PYTHONPATH = "src\cloud"
```

Fix in a Linux shell:

```bash
export PYTHONPATH="src/cloud"
```

### `Configuration error: Missing required configuration values: ...`

Cause: `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, or `SPARKY_RELAY_URL` was not set for the demo manifest.

Fix: set the missing value and rerun the command. Use placeholders for local no-Azure-spend manifest checks; use real deployment settings only in a secure test environment.

### `Device-hop scope must target the relay app registration, not Azure AI.`

Cause: `SPARKY_RELAY_DEVICE_SCOPE` was set to a Cognitive Services, Azure AI, or Cognitive endpoint.

Fix: set the device scope to the relay API scope, such as `api://<relay-app-id>/.default`. Keep `SPARKY_FOUNDRY_SCOPE`, `SPARKY_SPEECH_SCOPE`, or the compatibility alias `AZURE_COGNITIVE_SCOPE` only on the relay side for downstream managed-identity scopes.

### Relay returns `401` or `403`

Cause: the Pi token may have the wrong audience, wrong issuer, expired lifetime, or missing app assignment.

Fix: confirm the Pi requested `SPARKY_RELAY_DEVICE_SCOPE`, not a Cognitive Services scope. Confirm relay configuration uses the same tenant and relay audience. Re-enroll with device code if the token expired.

### Foundry or Speech returns downstream authorization errors

Cause: the relay identity may not have `Cognitive Services User` on both the Foundry or AI Services account and the Speech account, the assignment may be scoped to the wrong resource, RBAC may not have propagated yet, the relay may be using the wrong downstream endpoint, or Speech may be receiving the wrong managed-identity token form.

Fix: verify `Cognitive Services User` for the relay system-assigned managed identity on both resources. Wait several minutes for RBAC propagation and retry before changing configuration. For Speech, confirm whether this environment needs `SPARKY_SPEECH_RESOURCE_ID` set so the relay sends `Bearer aad#<resource-id>#<token>`, or unset so it sends plain `Bearer <token>` to a custom-subdomain resource. If it still fails, capture it as a live-environment blocker rather than adding key fallback.

### Foundry model or Speech feature is unavailable

Cause: local tests cannot prove live South Central US model quota or Speech feature availability.

Fix: verify quota, model deployment, and Speech feature support in the deployed environment. If the required model or feature is unavailable in `southcentralus`, record the gap as a blocker or an explicit alternate-region decision.

### Keyless guard reports a real repository file

Cause: executable code, config, infra, or workflow YAML contains a forbidden key-based fallback marker.

Fix: remove the key-based fallback path. Markdown may name forbidden mechanisms in prose, but scanned executable surfaces must stay keyless.

## Follow-up open questions

These items are tracked here because the hardware-in-the-loop guide is the canonical place to close them with live relay evidence.

- Neither the chat nor the speech downstream path has been validated against live Azure; current coverage is unit-level with injected fake transports. Close this by completing Steps 4 and 5 successfully against a deployed dev environment.
- The Speech authorization token format is conditional: `aad#<resource-id>#<token>` when `SPARKY_SPEECH_RESOURCE_ID` is set, or plain `Bearer <token>` for a custom-subdomain Speech resource. Only one form runs per environment, and neither has been exercised live. Close this by confirming which form the dev Speech resource accepts and recording it in the validation notes.
- `SPARKY_CHAT_DEPLOYMENT` is operator-supplied and not wired by infra, so a freshly deployed environment returns `chat_not_configured` until an operator sets it. Open question: should dev Bicep pin a default deployment name, or is operator-supplied correct?
- `SPARKY_CHAT_API_VERSION` defaults to `2024-10-21`; it has not been validated against what the deployed Foundry resource actually serves. Close this by confirming the deployed resource accepts that API version during the live chat validation.
