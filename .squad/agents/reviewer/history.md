### 2026-09-28T12:26:41-04:00 — Keyless auth testing guide rejection revision

- Reviewed the docs-auth testing guide after rejecting the docs-authored artifact under reviewer lockout; docs remains locked out for this revision cycle.
- **Correction (2026-09-28T12:26:41-04:00):** The coordinator's rejection premise was based on a misread caused by harness output redaction. The docs-authored guide at `1bf70cf` already had the correct Pi-side Foundry and Speech relay curl headers: both the `Bearer ` scheme and the exported relay access-token variable were already present. The guide's curl headers were never malformed and were not changed by the reviewer diff.
- The reviewer's real contribution was adding the missing `Bearer ` scheme prefix to the demo-manifest placeholder headers in `src/cloud/sparky_relay/keyless_auth.py`, adding matching assertions in `tests/test_keyless_auth_spike.py`, and inserting the Step 5 clarification that the Speech relay call reuses the `SPARKY_RELAY_ACCESS_TOKEN` exported in Step 4.
- **Durable lesson:** `Authorization:` header values are redacted in tool output. Never conclude a header is malformed from what is printed; decode or transform the raw bytes first, such as base64-encoding the line before printing, before reporting a defect or fixing it.
- Verified the guide against `keyless_auth.py`, `keyless_guard.py`, and `docs/keyless-auth-spike.md`; no additional guide structure changes were needed.

📌 Team update (2026-09-28T16:26:51-04:00): When a port forwards a value to a vendor API, check whether the vendor constrains that value; if so, confirm the simulator enforces the same constraint before any side effect — decided by Scribe.

📌 Team update (2026-09-28T16:45:35-04:00): Vendor calls that dispatch to background threads may swallow exceptions, so a bench step reporting COMPLETE is not evidence hardware acted; review adapters for per-call vendor quirks and require comments explaining those workarounds — decided by Scribe.

📌 Team update (2026-09-29T09:50:26-04:00): Motion action names are now validated in the hardware contract layer before adapter or simulator side effects; docs/running-on-the-pi.md gained a valid-action list and a troubleshooting row. — decided by Device

📌 Team update (2026-09-30T10:00:58.0877268-04:00): Reviewer rejection found malformed IMU data could be reported as OK; Lead owned the locked-out fix and added IMU validation in commit d87e61d with 223 tests passing.

📌 Team update (2026-09-30T11:10:46-04:00): Relay API surface now enforces injected Entra token validation and managed-identity downstream calls; PR #69 closes #9 — decided by Security


### 2026-09-30T15:39:31-04:00 — Issue 12 perception contract review

- Reconciled ADR 0006 and architecture wording against the implemented `sparky_contracts` perception surface: `PerceptionRequest`, `PerceptionResult`, metadata/failure DTOs, prompt constants, fixtures, and device/cloud helpers.
- Verified ADR 0005 remains honored: `PackagedFrame` stays device-local, with `request_from_packaged_frame()` bridging to the shared relay contract.
- Required validation passed: `python -m unittest discover -s tests` (287 tests) and `python -m compileall -q src tests`.

📌 Team update (2026-10-01T09:46:28.545-04:00): Infra CD Dev automation was recommended, security-reviewed, and implemented with Dev-only workflow_run guardrails; roster has a capability gap for CI/CD workflow authoring, so implementation routed to reviewer.

📌 Team update (2026-10-01T10:15:16.0716551-04:00): Infra CD pass 2 exposed a workflow-validation pitfall — local Python YAML parsing can resolve anchors/aliases and produce a false green even when GitHub Actions policy should reject the workflow. Use raw-text policy tests for workflow anchors, aliases, and merge keys; YAML-level validation alone cannot certify Actions workflows. — decided by reviewer/coordinator
