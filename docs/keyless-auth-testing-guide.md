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

### Step 1: Configure only relay-facing values on the Pi

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
- The response is a successful relay response or a clear downstream Foundry status from the relay.

How to tell it failed:

- `401` or `403` at the relay usually means the Pi token issuer or audience does not match the relay configuration.
- A downstream authorization failure after relay validation usually means RBAC has not propagated or the relay managed identity lacks `Cognitive Services User` on the Foundry or AI Services account.
- A model-not-found or quota error is a live South Central US Foundry availability issue, not a reason to add key auth.

### Step 5: Call the relay Speech path

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
- The response is synthesized audio, a relay success envelope, or a clear downstream Speech status from the relay.

How to tell it failed:

- `401` or `403` at the relay points to Pi token issuer or audience validation.
- A downstream Speech authorization failure points to RBAC scope, RBAC propagation, endpoint, or managed identity configuration.
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

Cause: the relay identity may not have `Cognitive Services User`, the assignment may be scoped to the wrong resource, RBAC may not have propagated yet, or the relay is using the wrong downstream endpoint.

Fix: verify the role assignment scope for the relay managed identity on both resources. Wait for RBAC propagation and retry. If it still fails, capture it as a live-environment blocker rather than adding key fallback.

### Foundry model or Speech feature is unavailable

Cause: local tests cannot prove live South Central US model quota or Speech feature availability.

Fix: verify quota, model deployment, and Speech feature support in the deployed environment. If the required model or feature is unavailable in `southcentralus`, record the gap as a blocker or an explicit alternate-region decision.

### Keyless guard reports a real repository file

Cause: executable code, config, infra, or workflow YAML contains a forbidden key-based fallback marker.

Fix: remove the key-based fallback path. Markdown may name forbidden mechanisms in prose, but scanned executable surfaces must stay keyless.
