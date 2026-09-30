## 2026-09-25T16:39:28-04:00

- Fixed Container Apps environment logging to use the keyless Azure Monitor destination with diagnostic settings to Log Analytics by workspace resource ID.
- Removed Log Analytics workspace customer ID plumbing from the monitoring module and environment entry points.
- Added static infra policy coverage for the keyless Container Apps logging shape and broader forbidden list functions.
- Added pinned Python setup to Infra CI before running unittest policy checks.
- Audited baseline infra for no Azure access keys: Cognitive Services local auth disabled, ACR admin disabled, no key/list/admin credential functions, no secret-bearing outputs, and RBAC scoped to individual resources.
- Recorded private ACR image first-pull sequencing as a documented residual risk for future deployment work; current public placeholder image is not affected.

📌 Team update (2026-09-25T16:39:28-04:00): Container Apps environments must use the keyless Azure Monitor logs destination plus diagnosticSettings to route ContainerAppConsoleLogs and ContainerAppSystemLogs to Log Analytics by workspace resource ID; never reintroduce the shared-key-requiring log-analytics destination — decided by Security.


## 2026-09-28T11:25:49-04:00

- Corrected issue #4 keyless-auth spike so the Pi device-code flow can only request a relay-audience scope; Azure AI / Cognitive Services scopes now belong exclusively to relay managed-identity hops.
- Added deterministic claim-validation and managed-identity token acquisition helpers plus failure-path tests for missing config, wrong audience, wrong issuer, and token acquisition failures.
- Added a keyless-guard scanner and static tests that fail if key-based Azure AI fallback markers reappear in executable code, config, workflows, or Bicep.
- Updated the spike doc with token-per-hop proof, Pi enrollment, ruled-out key/secret paths, Speech Entra auth SDK/REST finding, South Central US deployment target, smoke commands, and HIL validation steps.
- Validation: `python -m unittest discover -s tests -v` passed; CLI smoke manifest with `python -m sparky_relay.keyless_auth --print-demo` passed with placeholder env values.

### 2026-09-30T11:02:33-04:00 — Relay API Entra validation implementation
- Implemented issue #9 relay auth/API surface as a stdlib-only core with injected token-verifier, managed-identity credential, downstream client, rate-limiter, and policy ports.
- Added explicit validation for issuer, tenant, relay audience (including Graph rejection), expiry/nbf, and required role/scope/enrolled-device claim.
- Added unit, integration, and contract tests for endpoint and auth success/failure paths, including no credential-material leakage and no caller-token forwarding downstream.
- Updated README and architecture docs with endpoints, validation chain, HIL relay-auth steps, and follow-up risks.
