# Lead History

📌 Team update (2026-09-25T11:52:57-04:00): Deployment documentation with copyable shell commands should use paired Bash / zsh and PowerShell examples so Windows maintainers do not hit Bash-only syntax — decided by Docs.

📌 Team update (2026-09-25T16:39:28-04:00): Container Apps environments must use the keyless Azure Monitor logs destination plus diagnosticSettings to route ContainerAppConsoleLogs and ContainerAppSystemLogs to Log Analytics by workspace resource ID; never reintroduce the shared-key-requiring log-analytics destination — decided by Security.


📌 2026-09-30T09:55:45-04:00: Fixed issue #7 malformed-IMU gap in the service layer rather than `ImuReading` so invalid vendor/simulator axis values now become `ReadingStatus.MALFORMED` without broadening the shared hardware-contract blast radius.

📌 Team update (2026-09-30T11:10:46-04:00): Relay API surface now enforces injected Entra token validation and managed-identity downstream calls; PR #69 closes #9 — decided by Security


📌 2026-09-30T12:45:22-04:00: Added a FastAPI/uvicorn hosting adapter and container image for the relay while keeping the stdlib relay core framework-neutral. Kept Container Apps target port at 80 and enabled non-root binding in the image so code-cd can update only the image without an infra targetPort rollout.
📌 Team update (2026-09-30T12:45:22-04:00): The relay now has a real ASGI entry point and Dockerfile; PR #70 carries the verified FastAPI adapter, container image packaging, and port-80 Container Apps alignment — decided by lead.

📌 2026-09-30T12:45:22-04:00: Made relay startup tolerant so /health responds without configuration and AI routes return structured 503 responses with correlation IDs until deploy-time Entra settings are supplied.
📌 2026-09-30T12:45:22-04:00: Corrected the unauthenticated ASGI health bypass semantics so it now reports `authenticated: false` while the post-auth relay health handler remains authenticated.

📌 Team update (2026-09-30T12:45:22-04:00): Relay now returns 503 `relay_unavailable` on AI routes and an anonymous 200 on `/health` until `relayAudience` is supplied at deploy time — device-side smoke runs should expect this.


📌 2026-09-30T15:33:55-04:00: Implemented issue #12 code-side shared perception contracts without promoting `PackagedFrame`: added the shared `PerceptionRequest`, round-trip DTO parsing, perception fixtures, cloud adapter aliasing to shared prompts, and device bridge helpers that build requests from packaged frames and parse relay responses.

📌 2026-09-30T16:01:16-04:00: Fixed the Code CI import regression by adding repo-local shared-contract fallback path resolution at the device and cloud perception package boundaries. Verified unittest discovery, motion HIL CI smoke, relay-auth CI smoke, and compileall all pass.

📌 Team update (2026-09-30T16:11:05-04:00): Device and cloud perception modules now use the three-tier shared-contract import cascade: installed `sparky_contracts` package, repo-root `src.shared.sparky_contracts`, then a path-discovering local `src/shared` helper. This is required because script entry points put the script directory, not the repo root, on `sys.path`. — decided by Lead

📌 Team update (2026-10-01T09:46:28.545-04:00): Infra CD Dev automation was recommended, security-reviewed, and implemented with Dev-only workflow_run guardrails; roster has a capability gap for CI/CD workflow authoring, so implementation routed to reviewer.

📌 Team update (2026-10-01T10:15:16.0716551-04:00): The advisory design for automated Dev Infra CD deployment shipped in PR #80 via commit 877eb24, using `workflow_run` gated on successful Infra CI runs from `main`. — decided by coordinator

📌 2026-10-01T11:16:09.2889365-04:00: Implemented relay-side Speech-to-text for issue #14 with a stdlib REST adapter, Entra managed-identity Speech authorization, base64-audio JSON relay contract, normalized transcript/confidence metadata, and mocked plus fixture-backed tests. Chose REST over Speech SDK to preserve the relay core's no-new-dependency boundary while documenting the SDK/custom-domain path for future streaming work.

📌 2026-10-02T11:19:35.2650726-04:00: Diagnosed the relay 404 page not found as three independent faults, not the single infra-cd revert loop in the brief. (A) infra-cd redeployed the quickstart image pinned in main.bicepparam because no workflow ever passed a `relayImage` override. (B) code-cd DID flip the image, but revision `sparky-relay-dev--0000013` hit `ActivationFailed` with `ModuleNotFoundError: No module named 'sparky_contracts'` — the `az acr build` context was `src/cloud`, which cannot reach `src/shared` — so Container Apps kept serving the last healthy revision, the Go quickstart. (C) `relayUrl` advertises `/api` and ACA ingress does not strip prefixes, but the ASGI app registered bare paths only. Lesson: a green deploy workflow proves the control plane accepted a revision, not that the revision runs; always gate on `runningState`/`healthState`. Second lesson: the three-tier shared-contract import cascade masks packaging bugs in-repo and only fails in the container, so verify packaging with a clean install, not a repo-root run.

📌 2026-10-02T11:19:35.2650726-04:00: Fixed all three — infra-cd now resolves the live image read-only and passes it back as a parameter override plus `relayAudience` from `vars.SPARKY_RELAY_AUDIENCE`; the Dockerfile builds from `src/` and installs both `shared` and `cloud`; `asgi.py` includes its APIRouter twice (bare and `/api`) with a `relay_path()` normaliser because FastAPI `root_path` does not work behind ACA ingress. Also converted code-cd's three silent-green `exit 0` no-ops to `::error::` + `exit 1` and added a post-deploy revision health gate. `relayAudience` cannot live in a bicepparam: three policy tests (no `relayAudience` string in bicepparams, no un-allow-listed GUIDs under `infra/`, no GUIDs in delivery workflows) collectively force it to a GitHub Actions variable. Pinned the infra↔app URL contract with `tests/test_relay_path_contract.py`, which parses the `relayUrl` suffix from every environment's main.bicep. 385 tests pass.
