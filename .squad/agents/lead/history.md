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
