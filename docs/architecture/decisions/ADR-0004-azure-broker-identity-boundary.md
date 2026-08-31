# ADR-0004 — Azure Broker and Identity Boundary

| Field | Value |
|-------|-------|
| **Status** | 🟦 **PROPOSED** — not accepted until the dual approval gate closes |
| **Date** | 2026-08-28 |
| **Owner** | Architect, with AzureAI |
| **Deciders** | Dave Davis (approval gate) |
| **Supersedes** | — |
| **Related** | [ADR-0001](ADR-0001-pi-local-hardware-adapter.md), [ADR-0005](ADR-0005-privacy-defaults-camera-disabled.md) |
| **Related decisions** | [UD-09](../system-architecture.md#4-user-decision-register-ud-01--ud-10) (budget, regions, tenant, latency), [UD-10](../system-architecture.md#4-user-decision-register-ud-01--ud-10) (broker mandatory vs direct Speech) |

> **Approval gate:** This ADR describes a recommendation. It authorizes nothing. Implementation remains BLOCKED until Dave Davis explicitly approves **both** `system-architecture.md` **and** `project-plan.md`. Approval of one alone, silence, or requested revisions does not open the gate.

## Context

The device is a physically accessible object that may sit in a home. Anyone who picks it up has its filesystem. Any long-lived credential stored on it is compromised from the moment of physical access, and — critically — a shared credential compromised on one device compromises every device.

The device needs three cloud capabilities: speech-to-text, a language model, and content safety. The obvious approach is to put credentials on the device and call Azure directly. That approach has four specific failures:

| Failure | Consequence |
|---------|-------------|
| Credential on device | Physical access yields cloud access. If the credential is shared, one compromise is a fleet compromise. |
| No revocation granularity | Revoking a shared key kills every device. There is no way to isolate one bad device. |
| No rate limiting per device | A malfunctioning or hostile device can consume the whole quota. |
| No cost attribution | Azure bills the subscription; nothing tells you which device spent it. |

There is also a coupling problem: a device that knows the model endpoint, the API version, and the deployment name has all of that baked into its firmware. Changing the model or the region becomes a fleet update.

Separately, the read-only assessment found that PiDog ships its own AI path (`pidog.llm`, `pidog.stt`, `pidog.voice_assistant`, EV-05) which is broken against the supplied robot-hat (EV-06, EV-07). Even if it worked, it would be an uncontrolled second cloud path with its own credential handling, outside our identity boundary and outside our content-safety checkpoints. [ADR-0001](ADR-0001-pi-local-hardware-adapter.md) bans it (HA-03).

## Decision

**A Sparky Azure Broker is the secure default and the only Azure endpoint the device knows.**

### The boundary

| Property | Device | Broker |
|----------|--------|--------|
| Credential held | **Exactly one** — a per-device X.509 client certificate | Azure managed identity |
| Transport | mTLS to the broker | Managed-identity calls within Azure |
| Knows the model endpoint | ❌ No | ✅ Yes |
| Knows the Speech key | ❌ No — there is no key on the device | ✅ Via managed identity |
| Knows the deployment or API version | ❌ No | ✅ Yes |
| Individually revocable | ✅ Yes, per device | Azure RBAC |
| Rate-limitable per device | ✅ At the broker | — |
| Cost-attributable per device | ✅ At the broker | — |

The device holds **no** model key, **no** Speech key, **no** subscription key, and **no** connection string. It holds a certificate that identifies it and nothing else (PR-08, PR-09).

### What the broker does

- Terminates mTLS and authenticates the device certificate.
- Applies per-device rate limiting and quota.
- Calls Azure Speech, the Azure-hosted language model, and Azure Content Safety using its **managed identity**.
- Enforces the dual content-safety checkpoint — on the transcript before the model, and on the reply before synthesis (PR-06).
- Emits per-device, per-subsystem cost and latency telemetry (NFR-04).
- Is the single place model, deployment, API version, or region can change without touching a device.

### The direct-Speech experiment

🧪 **EXPERIMENT — explicitly not a shipping path.** A direct device-to-Speech flow using short-lived tokens issued by the broker is retained as a time-boxed evaluation, on the hypothesis that removing a network hop from the latency-critical audio path measurably improves first-syllable latency.

| Field | Value |
|-------|-------|
| Hypothesis | Direct Speech streaming measurably reduces first-syllable latency versus brokered audio |
| Success criterion | A measured, reproducible improvement large enough to change perceived responsiveness |
| Abandon criterion | No material improvement; **or** any requirement to hold a credential on the device beyond a short-lived scoped token; **or** complexity that compromises the per-device revocation story |
| Time box | Set in M2; abandoned by default if inconclusive |
| Gate | 🔒 **Blocked by UD-10.** Does not start until the user rules on whether the broker is mandatory. |
| Default after the approved UD-10 decision | Broker-only. The experiment does not run. |

The language-model path is **broker-only regardless of UD-10**. The experiment concerns Speech alone, because Speech is the only latency-critical leg and the only one where a short-lived scoped token is a coherent proposition.

### What is deliberately not asserted

⛔ Model selection, SDK version, API version, region, quota, throughput, latency, and cost are **not asserted anywhere in this package** (NA-01 to NA-05). They are blocked by **UD-09** and measured in M2. No provisioning proceeds and no latency target is published before then.

## Alternatives considered

| Alternative | Why rejected |
|-------------|--------------|
| **Keys on the device, direct to Azure** | Physical access yields cloud access. Shared keys make one compromise a fleet compromise. No per-device revocation, rate limiting, or cost attribution. Bakes the model endpoint into the device. |
| **Per-device Azure identities, direct to Azure** | Better on revocation, but still puts a cloud-scoped credential on a physically accessible device, still bakes endpoints into firmware, and still gives no central rate-limiting or cost-attribution point. |
| **Broker for the model, keys on device for Speech** | Reintroduces the exact failure the broker exists to prevent, for the sake of one hop. If latency truly demands it, the short-lived-token experiment is the disciplined version of this idea. |
| **PiDog's built-in `robot_hat.llm` / `voice_assistant` path** | Broken against the supplied robot-hat (EV-07). Even working, it is an uncontrolled second cloud path outside our identity boundary and outside our content-safety checkpoints. Banned by [ADR-0001](ADR-0001-pi-local-hardware-adapter.md) HA-03. |
| **VPN or private link only, with keys on device** | Protects the network path but not the device. Physical access still yields the key. Also does not provide per-device attribution. |
| **No broker; accept the risk for a single device** | The design cost of the broker is paid once and it is what makes a second device safe. Building the insecure version first guarantees rebuilding it later. |

## Consequences

### Positive

- Physical compromise of one device yields one revocable certificate and nothing else.
- Per-device rate limiting bounds the blast radius of a malfunctioning device.
- Per-device, per-subsystem cost attribution (§13.3) exists naturally — a direct-to-Azure device gives no attribution point at all.
- Model, deployment, API version, and region change at the broker, never on the device.
- Content safety is enforced in one place that the device cannot bypass.

### Negative

- The broker is new infrastructure to build, deploy, secure, and operate.
- It adds a network hop, which is a real latency cost — the very cost the direct-Speech experiment is designed to measure honestly rather than assume away.
- Certificate enrolment, rotation, and revocation is genuine operational work (AS-06), and it depends on the approved tenant and regional policy captured under UD-09.
- The broker is a single point of failure for all cloud capability, which is why the degraded-mode design (§9.3, FR-09) is a first-class requirement and not an afterthought.

### Neutral

- The broker is the natural place to add fleet features later, without that being a goal now (NG-05).

## Validation

| ID | Acceptance criterion | Milestone |
|----|---------------------|-----------|
| AC-SEC-01 | The device filesystem contains no long-lived cloud credential; only the device certificate | M2 |
| AC-SEC-02 | Revoking one device certificate blocks that device and no other | M2 |
| AC-SEC-03 | The device cannot reach the model or Speech endpoints directly | M2 |
| AC-RAI-02 | Content safety runs on both input and output; blocks yield a persona-voiced refusal | M2 |
| AC-COST-01 | Cost per turn is attributable to STT, model, TTS, and safety | M2 |
| AC-CLOUD-01 | Every cloud call has an explicit timeout; no unbounded wait in the turn path | M2 |
| AC-CLOUD-02 | A late response for an invalidated generation is discarded and never spoken | M2 |
| AC-M2-02 | No latency, quota, or cost figure in any project document is unsourced | M2 |
| AC-PRIV-05 | Across the full soak, no credential is written to disk | M7 |

## Open items

- **UD-09** — Azure budget, regions, tenant, subscription, and latency expectations. 🔒 **Hard block on M2 entry.** No provisioning without it.
- **UD-10** — is the broker mandatory, or is the direct-Speech path an approved evaluation track? Default while open: broker-only, experiment does not run.
- **AS-05** — that Azure is reachable with acceptable latency. Measured in M2-D7, **not assumed**.
- **AS-06** — that per-device X.509 enrolment is operationally achievable in the target tenant.
- **RAI-B5** — Rai's credential blocker, closing at M2 with the identity boundary implemented and verified.

## Constraint restated

Nothing in this ADR authorizes any modification under `exlibs/`. PiDog's own cloud path is refused by reading it and declining to import it, never by editing it.
