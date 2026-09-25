# Keyless auth proof-of-path spike

This spike proves the intended Microsoft Entra keyless flow used by the Sparky relay and Microsoft Foundry resources.

## End-to-end flow

1. A device or client obtains a Microsoft Entra token for the app registration configured in Azure.
2. The token is sent to the relay, which validates the `aud` and `iss` claims and checks the expected Azure resource scope.
3. The relay exchanges the user/device token for a managed-identity token scoped to `https://cognitiveservices.azure.com`.
4. The relay calls Azure AI / Foundry services without human credentials or stored client secrets.

## Required Azure configuration

Set the following environment variables before running the relay or demonstrating the flow:

```bash
export AZURE_TENANT_ID="<tenant-guid>"
export AZURE_CLIENT_ID="<app-registration-client-id>"
export SPARKY_RELAY_URL="https://<relay-host>/api"
export AZURE_COGNITIVE_SCOPE="https://cognitiveservices.azure.com/.default"
export AZURE_TOKEN_AUDIENCE="api://AzureADTokenExchange"
```

## Proof-of-path sequence

```bash
python -m sparky_relay.keyless_auth --print-demo
```

This produces the device-code and relay payload that document the expected exchange flow without contacting Azure.

## Example relay request

```bash
curl -X POST "${SPARKY_RELAY_URL}/token" \
  -H "Authorization: Bearer <entra-token>" \
  -H "Content-Type: application/json" \
  --data '{
    "resource": "https://cognitiveservices.azure.com",
    "scope": "https://cognitiveservices.azure.com/.default",
    "audience": "api://AzureADTokenExchange"
  }'
```

The relay is expected to validate the incoming access token before minting or forwarding a managed-identity access token to the Azure AI resource.

## Validation gates

- `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `SPARKY_RELAY_URL` must be present.
- The relay must reject tokens whose resource or audience do not match the configured Azure platform contract.
- The relay should log the token purpose, issuer, and audience for auditability.
- Production deployments should keep Azure credentials out of the repository and prefer GitHub OIDC + managed identity.
