# Squad Decisions

## Active Decisions

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction

## 2026-09-25T09:38:29.971-04:00

- **Repo structure:** Monorepo with `/src` for device/cloud/shared application code, `/infra` for Bicep, `/docs` for architecture/ADRs/plan, and separate workflow definitions under `/.github/workflows`.
- **IaC choice:** Bicep, because the project is Azure-only and needs native managed identity/RBAC support without Terraform state bootstrap.
- **Keyless auth approach:** Raspberry Pi authenticates to an Entra-protected relay API using device code flow as a public client; the relay runs in Azure Container Apps with system-assigned managed identity and calls Foundry/Speech with RBAC only.
- **Milestone plan:** M1 Foundations & Keyless Platform, M2 Device Control Baseline, M3 Relay API & Vision Perception, M4 Voice Conversation Loop, M5 Agent Behavior & Orchestration, M6 Hardening, Security & Observability, M7 Release Readiness & Demo.
- **Issue count:** 28 GitHub issues created across 7 milestones.

## 2026-09-25T09:38:29.971-04:00

- **Security review verdict:** 🟡 The architecture and ADR 0003 are directionally sound for a keyless design (Pi authenticates only to the relay; relay uses managed identity to reach Foundry/Speech), but issues #2, #3, #4, #9, and #23 need explicit acceptance criteria for disabling local/key-based auth, enforcing GitHub OIDC/WIF-only deployment auth, proving no fallback key paths, tightening relay token/app-role validation, and threat-modeling token/logging/device-loss risks.


## 2026-09-25T10:18:06.056-04:00

- **Persona framework:** Sparky will use a declarative-first persona framework with manifests under `src/device/sparky_device/personas/` and shared schema/validation under `src/shared/sparky_contracts/personas/`. Core code loads personas through a registry; normal third-persona additions must require only a new manifest plus tests/fixtures.
- **Persona controls:** A persona controls LLM prompt intent, TTS voice/prosody, movement profile, vision/sensor reaction mappings, sound/RGB idioms, and safety notes. Persona safety may tighten but never override global safety, authentication, privacy, or motion constraints.
- **Switching:** Persona switching is a runtime hot-swap through voice intent, command mode, or programmatic API after a safe-state transition that cancels/settles in-flight conversation, TTS, motion, and transient reactions. Conversation memory is persona-scoped by default and switches are logged/telemetried.
- **Starter personas:** Sunny Companion (warm companion; gentle voice and relaxed movement) and Sentinel Scout (alert non-aggressive scout; crisp voice, patrol movement, inspection reactions).
- **New issues:** #30 schema/validation, #31 loader/registry/default, #32 runtime switching/safe-state, #33 persona-aware TTS, #34 movement profiles/reactions, #35 LLM prompt composition/safety, #36 starter manifests, #37 third-persona release acceptance.

## 2026-09-25T11:05:56.219-04:00

- **Deployment target:** Sparky Azure resources target the existing `rg-sparky` resource group in South Central US (`southcentralus`).
- **Subscription handling:** The concrete subscription is treated as deployment configuration. GitHub Actions must read it from the `AZURE_SUBSCRIPTION_ID` repository variable, and local operators must select it with `az account set`; it should not be committed into Bicep, parameter files, workflows, or general docs as a hardcoded value.
- **Environment model:** Dev and prod are logical environments in the same resource group, separated by Bicep parameters, GitHub Environments, tags, outputs, and resource names.
- **Naming convention:** Use `sparky-<resource>-<env>` where provider rules allow it; use provider-specific variants such as `sparkyscr<env>` for globally unique alphanumeric ACR names. Tag resources with `app=sparky` and `environment=<env>`.
- **Regional caveats:** Foundry projects and baseline GPT-4.1/GPT-4o-family standard model deployments are documented as available in South Central US, subject to current quota. Azure Speech supports core STT/TTS there, but advanced features such as LLM speech, MAI voices, HD voices, Azure OpenAI voices, personal voice, voice conversion, custom voice HD endpoints, preview voices/styles, and avatar voice sync are not available there in the referenced Speech region matrix; later work must choose standard neural/custom voices in-region or record a separate alternate-region decision.

## 2026-09-25T11:30:11.945-04:00

- **GitHub Actions Azure deployment setup:** Deployment documentation now specifies keyless GitHub Actions authentication through Microsoft Entra workload identity federation. The documented approach uses a secret-free app registration/service principal, federated credentials for `dev`, `prod`, `main`, and PR subjects as needed, repository variables for non-secret IDs, GitHub Environments for dev/prod approvals, and resource-group-scoped RBAC for `rg-sparky` with an additional RBAC administrator role only when Bicep creates role assignments.

### 2026-09-25: Use paired Bash and PowerShell command blocks in deployment docs
**By:** Docs
**What:** Deployment documentation that contains copyable shell commands should provide paired **Bash / zsh** and **PowerShell** fenced blocks instead of assuming one shell.
**Why:** Sparky maintainers run setup from both Unix-like shells and Windows PowerShell. Bash assignments, `$VAR` expansion, trailing `\` continuations, heredocs, and Unix utilities do not execute in PowerShell, so future deployment docs need explicit shell-specific variants while preserving the Bash experience.

### 2026-09-25: GitHub Actions Azure IDs are secrets, deployment settings are variables
**By:** Docs
**What:** Store `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, and `AZURE_SUBSCRIPTION_ID` as GitHub repository secrets. Store `AZURE_RESOURCE_GROUP` and `AZURE_LOCATION` as GitHub repository variables. Workflow YAML must read the three IDs from `secrets.*` and the resource settings from `vars.*`.
**Why:** OIDC does not require secret material, and the client and tenant IDs are public identifiers while the subscription ID is only mildly sensitive. Keeping the three IDs as secrets is still a defensible defense-in-depth choice that masks the subscription ID in logs and keeps it out of committed files. The trade-off is harder debugging because secrets are masked and unavailable to forked pull-request workflows.

### 2026-09-25T20-55-52: Model deployments remain parameterized and telemetry secrets stay out of infra outputs
**By:** lead
**What:** Model deployments remain parameterized and telemetry secrets stay out of infra outputs
**References:** GitHub issue #2, infra/modules/ai-services.bicep, infra/modules/monitoring.bicep, docs/adr/0003-keyless-edge-auth-pattern.md
**Why:** ### 2026-09-25: Parameterize Foundry deployments and avoid telemetry secret outputs
**By:** lead
**What:** Baseline Bicep keeps chat and vision model deployments behind an empty-by-default `modelDeployments` array, and Application Insights outputs are limited to name and resource ID rather than connection strings or instrumentation keys.
**Why:** South Central US model capacity, deployment type, and exact versions must be confirmed immediately before deployment; committing guesses would create brittle IaC. Telemetry connection strings and keys would violate the keyless baseline, so relay telemetry configuration must be resolved via managed identity-aware runtime configuration or out-of-band app settings.

### 2026-09-25T16:39:28-04:00: Use Azure Monitor diagnostics for Container Apps logs
**By:** Security
**What:** Container Apps managed environments must use `appLogsConfiguration.destination = 'azure-monitor'` plus diagnostic settings to route console and system logs to Log Analytics by workspace resource ID. Do not use the `log-analytics` destination because it requires a workspace shared key.
**Why:** The project has a hard no-Azure-access-keys policy; retrieving or supplying the Log Analytics shared key would create a key-based fallback path.

### 2026-09-25T16:39:28-04:00: Document private ACR first-pull sequencing risk
**By:** Security
**What:** The baseline keeps the relay Container App on a public placeholder image and documents that future private ACR images need pre-granted AcrPull or a two-phase identity/RBAC deployment. No `dependsOn` was added because the current role assignment needs the app's system-assigned principal ID, so making the app depend on that assignment would create a cycle.
**Why:** The current baseline is safe for the public image, but private-image cutover must avoid an identity/RBAC propagation race without broadening permissions or adding key fallback.

### 2026-09-28T12:26:41-04:00: Treat redacted Authorization output as unknown
**By:** Scribe
**What:** The agent harness redacts values that appear after the `Authorization:` header name, and likely other credential-shaped patterns, in tool output such as file views and grep results.
**Why:** On 2026-09-28 this caused a false-positive defect report and a wasted revision cycle. An agent fixed a file that was already correct, then reported success for a change it had not made.
**How to handle it:** Before reporting or fixing any suspected credential or header defect, verify the raw bytes by base64-encoding the line, checking its length, or otherwise transforming the content so it does not match the redaction pattern. Treat a string of asterisks in tool output as unknown, not as literal content.

### 2026-09-28: Split keyless auth scopes by hop
**By:** security
**What:** The keyless-auth spike uses `SPARKY_RELAY_DEVICE_SCOPE` for Pi-to-relay device-code auth and `SPARKY_FOUNDRY_SCOPE` / `SPARKY_SPEECH_SCOPE` for relay managed-identity calls. `AZURE_COGNITIVE_SCOPE` is retained only as a compatibility alias for downstream relay scopes and must never drive the device-code request.
**Why:** A single scope can accidentally hand the Pi an Azure AI bearer token. Separate env vars make the token boundary explicit and let tests reject Azure AI audiences on the device hop.

### 2026-09-28T19:40:00Z: Bound HIL camera capture and motion waits
**By:** Device
**What:** Vilib camera capture now waits briefly for the first asynchronous frame before failing, and PiDog/simulator motion waits now enforce explicit timeouts.
**Why:** The HIL checklist calls camera start then capture back-to-back and calls wait_all_done with safety expectations; the adapters must avoid spurious camera failures and must not block indefinitely around powered motion.

### 2026-09-28T16:14:06-04:00: Missing peripherals skip hardware-in-the-loop benches
**By:** Scribe
**What:** A missing or failed peripheral must degrade to a reported SKIP, never abort the hardware-in-the-loop bench and never be silently passed. Vendor libraries may raise non-ImportError exceptions at import time (vilib constructs Picamera2 in its class body), so adapter loaders must convert any vendor failure into HardwareUnavailableError with actionable recovery steps. Lazy vendor imports in adapter constructors are load-bearing: they are what allows a robot missing one peripheral to keep using every other port.
**Why:** The first real PiDog hardware signal showed that a camera-less robot can still exercise motion, board, and sensor ports when vendor imports remain lazy and vendor failures are normalized into recoverable hardware-unavailable errors.

### 2026-09-28T16:45:35-04:00: Treat vendor background-thread calls and per-style RGB quirks as adapter contracts
**By:** Scribe
**What:** PiDog RGB adapter code must treat vendor calls that dispatch work to background threads as having no reliable synchronous failure signal. Bench steps that print "complete" are not proof that hardware acted. Adapter workarounds must encode per-call vendor quirks instead of assuming uniform behavior across a vendor API, and each workaround needs an inline comment explaining why it exists.
**Why:** The third consecutive real-hardware defect missed by simulator-based tests was silent: `pidog` swallowed a ws2812/SPI type error inside `_rgb_strip_thread`, so the HIL bench reported step 10 complete while the strip stayed dark. The vendor library was also internally inconsistent: five of six RGB styles cast scaled channel values to `int`, but `monochromatic()` did not, causing any float brightness — including the default `1.0` — to send float RGB values that the driver rejects.
**References:** PR #60, commit `0152ecc`, `src/device/sparky_device/pidog_adapters.py`, `tests/test_hardware_ports.py`, `docs/running-on-the-pi.md`

### 2026-09-29T09:50:26-04:00: Constrained vendor value domains belong in hardware contracts (consolidated)
**By:** Scribe, Device
**What:** Constrained PiDog vendor value domains belong in the hardware contract layer (`ports.py`), shared by both hardware adapters and simulators, and must be validated before any hardware or simulator side effect. This pattern now covers five confirmed parity failures: RGB style handling, RGB brightness/channel coercion, camera resolution, camera import/peripheral availability, and motion action names. Motion action names are now enforced through the shared `MOTION_ACTIONS` allow-list and `validate_action_name`, with space-separated caller input normalized to underscores and invalid names rejected loudly.
**Why:** A simulator with a wider value domain than the vendor does not merely miss bugs; it manufactures false confidence and invalidates the runbook triage rule that `simulator passes + hardware fails` implicates only the adapter. The vendor `do_action` implementation catches bare `Exception`, so bad action names can never raise to callers and instead fail silently. The vendor also resolves action names through `eval()`, so the contract-layer allow-list closes an injection hole before user input reaches the vendor call.
**References:** PR #62, commit `e8bef6a`, `src/device/sparky_device/hardware/ports.py`, `src/device/sparky_device/hardware/pidog_adapters.py`, `src/device/sparky_device/hardware/simulators.py`, `tests/test_hardware_ports.py`, `docs/running-on-the-pi.md`

#### Source inbox entries

#### 2026-09-29: Motion action names are a shared contract domain
**By:** Device
**What:** PiDog motion action names now live in the hardware contract layer as a fixed allow-list, with one shared validator used by both the PiDog adapter and the simulator. Space-separated caller input is normalised to underscores, but typos, wrong case, non-action helper methods, and eval-shaped strings are rejected before any side effect.
**Why:** This is the fifth instance of the same defect class: the simulator accepted a value domain that the vendor could not honour. The shared-validator pattern keeps simulator and hardware parity, makes failures loud, and closes the vendor `eval()` injection surface by never forwarding unchecked action names.

### 2026-09-29: Full HIL checklist belongs in one runnable script
**By:** Device
**What:** `scripts/motion_service_hil.py` now owns checklist steps 1-17, with `--steps`/`--only` for targeted reruns. Required PiDog import/profile failures are FAIL, optional Vilib/camera unavailability is SKIP, and cleanup always safe-stops motion, stops the camera, clears RGB, and closes ports.
**Why:** Operators should not copy Python heredocs from docs, and camera-less benches must still validate motion, sensors, board, and service behavior without losing the triage signal for adapter vs environment failures.

### 2026-09-29: Ship motion-service HIL as a root scripts helper
**By:** Device
**What:** The motion-service hardware-in-the-loop smoke check now ships as `scripts/motion_service_hil.py`, outside `tests/`, with `--simulate` for laptop rehearsal and a `try/finally`-style cleanup path that safe-stops and closes ports on success, failure, or Ctrl+C.
**Why:** The repo had no existing script/tool convention, and a root `scripts/` directory is the clearest operator-facing location. Keeping it out of `tests/` prevents unittest discovery from trying to run hardware moves, while the simulate mode keeps the script itself verifiable in CI and development.

### 2026-09-29: Motion service rejects conflicting in-flight commands
**By:** device
**What:** `MotionService` accepts one non-stop motion intent at a time. While a command is in flight, later non-stop commands raise `HardwareError` instead of being queued. Callers must either `wait_until_idle()` before the next intent or call `stop()`, which pre-empts immediately and is idempotent. Locomotion also requires the tracked posture to be standing; planners must explicitly request `stand()` after `sit()` or `lie()` before walking, trotting, or turning.
**Why:** The PiDog motion adapter queues work asynchronously, so accepting multiple planner intents without a settled state would make posture and command ownership ambiguous. Rejecting conflicts keeps behavior planners deterministic, makes unsafe overlaps observable, and preserves `stop()` as the one always-honoured emergency command.

### 2026-09-30: Sensor readings use explicit status semantics instead of ambiguous None
**By:** device
**What:** `SensorService` wraps `SensorPort` and returns timestamped, typed, frozen reading value objects carrying an explicit status: `OK` with a value for a valid reading, `OK` with `None` for a valid "no echo / no sound this tick" condition (not a fault), `UNAVAILABLE` for missing or unhealthy hardware, and `MALFORMED` for invalid data shape from the port. The service catches every port exception (`HardwareError`, `HardwareUnavailableError`, and arbitrary vendor errors) and maps it to a status so nothing escapes into the device loop.
**Why:** The pre-existing `SensorPort` had inconsistent failure semantics: `read_distance_cm()` and `read_sound_direction()` returned `None`, ambiguously representing either "no reading" or "hardware dead", while `read_imu()` raised `HardwareError`. Behavior loops consuming that surface would either crash or be unable to distinguish valid empty readings from faults. Vision and behavior work depend on a normalized sensor surface.

### 2026-09-30T09:55:45-04:00: Validate malformed IMU axes in SensorService
**By:** lead
**What:** Malformed IMU axis values are validated in `SensorService` before returning an OK reading, while `ImuReading.__post_init__` remains limited to structural axis-count validation.
**Why:** This fixes issue #7's service-level malformed-data requirement with the smallest safe blast radius. Moving the rule into the shared hardware value object would change behavior for every adapter and simulator construction site, while the service already owns normalizing inconsistent port failures into explicit `ReadingStatus` values.


### 2026-09-30: SensorService IMU malformed-data coverage gap
**By:** reviewer
**What:** Issue #7 gap analysis found SensorService treats any `ImuReading` instance as OK without validating that acceleration/gyro axes are numeric and finite. The existing malformed IMU test covers a `HardwareError` raised by the port, not an invalid `ImuReading` value object.
**Why:** The issue explicitly requires malformed sensor data paths. Distance, touch, and sound malformed values are detected directly by SensorService, but IMU malformed value-object content can still be logged/planned as an OK reading. Add service-side IMU axis validation and a representative malformed-IMU fixture before closing the issue.



### 2026-09-30: Use stdlib relay core with injected auth and downstream ports
**By:** Security
**What:** The relay API surface is implemented as a framework-agnostic, stdlib-only core with dataclass request/response types, an injected Entra token-verifier port, and an injected managed-identity credential/downstream-client port. Optional web framework adapters must stay thin and separate from the core.
**Why:** CI installs only test-only dependencies, so the relay cannot require FastAPI, PyJWT, or Azure SDK imports during unittest discovery or compileall. The injected-port design also makes the security boundary testable: signature verification is isolated, issuer/tenant/audience/lifetime/grant checks are deterministic, and downstream calls can prove they use relay-managed credentials instead of forwarding caller bearer tokens.
