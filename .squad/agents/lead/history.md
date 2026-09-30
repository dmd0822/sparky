# Lead History

📌 Team update (2026-09-25T11:52:57-04:00): Deployment documentation with copyable shell commands should use paired Bash / zsh and PowerShell examples so Windows maintainers do not hit Bash-only syntax — decided by Docs.

📌 Team update (2026-09-25T16:39:28-04:00): Container Apps environments must use the keyless Azure Monitor logs destination plus diagnosticSettings to route ContainerAppConsoleLogs and ContainerAppSystemLogs to Log Analytics by workspace resource ID; never reintroduce the shared-key-requiring log-analytics destination — decided by Security.


📌 2026-09-30T09:55:45-04:00: Fixed issue #7 malformed-IMU gap in the service layer rather than `ImuReading` so invalid vendor/simulator axis values now become `ReadingStatus.MALFORMED` without broadening the shared hardware-contract blast radius.

📌 Team update (2026-09-30T11:10:46-04:00): Relay API surface now enforces injected Entra token validation and managed-identity downstream calls; PR #69 closes #9 — decided by Security

