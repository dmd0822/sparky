# `sparky-cloud`

The Azure relay/API package lives in `sparky_relay/`. Cloud application code
belongs here; Azure resource definitions remain under `infra/`.

`sparky_relay.foundry_vision` contains the stdlib-only perception adapter for
`POST /ai/vision`. It accepts relay-managed bearer headers from the dispatcher,
uses an injected transport for Foundry chat-completions vision calls, and
returns normalized perception payloads for the device contract.
