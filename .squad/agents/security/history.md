## 2026-09-25T16:39:28-04:00

- Fixed Container Apps environment logging to use the keyless Azure Monitor destination with diagnostic settings to Log Analytics by workspace resource ID.
- Removed Log Analytics workspace customer ID plumbing from the monitoring module and environment entry points.
- Added static infra policy coverage for the keyless Container Apps logging shape and broader forbidden list functions.
- Added pinned Python setup to Infra CI before running unittest policy checks.
- Audited baseline infra for no Azure access keys: Cognitive Services local auth disabled, ACR admin disabled, no key/list/admin credential functions, no secret-bearing outputs, and RBAC scoped to individual resources.
- Recorded private ACR image first-pull sequencing as a documented residual risk for future deployment work; current public placeholder image is not affected.

📌 Team update (2026-09-25T16:39:28-04:00): Container Apps environments must use the keyless Azure Monitor logs destination plus diagnosticSettings to route ContainerAppConsoleLogs and ContainerAppSystemLogs to Log Analytics by workspace resource ID; never reintroduce the shared-key-requiring log-analytics destination — decided by Security.

