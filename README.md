# Sparky

Sparky is an AI-powered robot dog built on the [SunFounder PiDog](https://docs.sunfounder.com/projects/pidog/en/latest/) platform and augmented with Azure AI services through Microsoft Foundry. Sparky is designed for multiple runtime-switchable personas so the same robot can act, sound, move, and react differently while preserving global safety rules.

## Vendor platform references

- SunFounder PiDog docs: <https://docs.sunfounder.com/projects/pidog/en/latest/>
- `robot-hat`: <https://github.com/sunfounder/robot-hat>
- `vilib`: <https://github.com/sunfounder/vilib>
- `pidog`: <https://github.com/sunfounder/pidog>

## Architecture

- Architecture overview: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Architecture decisions: [docs/adr/](docs/adr/)
- Persona design: [docs/personas.md](docs/personas.md) and [ADR 0004](docs/adr/0004-persona-framework.md)
- Delivery plan: [docs/PLAN.md](docs/PLAN.md)
- Running device code on the robot: [docs/running-on-the-pi.md](docs/running-on-the-pi.md)
- Azure deployment conventions: [infra/README.md](infra/README.md)

## What this project will contain

Sparky is planned as a monorepo with separate areas for source code, infrastructure, and documentation:

```text
src/                 Application code only
  device/            Raspberry Pi runtime and hardware adapters
  cloud/             Azure-hosted relay/API services
  shared/            Shared contracts, persona schemas, and reusable libraries
infra/               Bicep infrastructure as code only
docs/                Architecture docs, ADRs, plans, diagrams
.github/workflows/   Separate infra and code CI/CD workflows
```

## Guiding constraints

- No Azure access keys in code, config, or secrets stores for runtime access
- Azure authentication via Microsoft Entra ID / Managed Identity
- IaC separated from source code
- Infra and application pipelines kept separate
- Tests required for all code changes
- Persona manifests are declarative, validated, and subordinate to global safety constraints
- README and architecture docs updated alongside meaningful changes

## Getting started

M1 is underway: the monorepo scaffold, Bicep infrastructure modules, and the
CI/CD workflow skeletons have landed on `main`. Infrastructure is deployed with
the manual `infra-cd.yml` workflow; application delivery runs through
`code-cd.yml` once a service produces a container image.

### Azure deployment target

Sparky's Azure resources are planned for the `rg-sparky` resource group in South
Central US (`southcentralus`). The subscription is not committed to the repo;
set it for automation with the `AZURE_SUBSCRIPTION_ID` GitHub repository
secret, or select it locally with `az account set --subscription
"<subscription-id>"`. See [infra/README.md](infra/README.md) for Bicep naming
and manual deployment commands, and [docs/deployment-setup.md](docs/deployment-setup.md)
for the keyless GitHub Actions OIDC setup guide.

### Package and test conventions

Each planned Python subproject is an independent package with its own
`pyproject.toml`:

- `src/device` → `sparky-device` / `sparky_device`
- `src/cloud` → `sparky-cloud` / `sparky_relay`
- `src/shared` → `sparky-shared` / `sparky_contracts`

Keep repository tests in the root `tests/` directory so CI can run one stdlib
`unittest` discovery command. Deterministic fixtures belong under
`tests/fixtures/`; do not commit credentials, hardware captures, or generated
build output. Generated artifacts must stay in ignored directories such as
`build/`, `dist/`, or `.coverage/`.

Run the scaffold validation with:

```powershell
python -m unittest discover -s tests
```

Compile and keyless-auth policy checks are also CI-compatible:

```powershell
python -m compileall -q src tests
$env:PYTHONPATH = "src/cloud"
python -m sparky_relay.keyless_guard
```

### Relay API surface

The cloud package includes a framework-agnostic relay core that can be adapted
to FastAPI/ASGI without importing web framework dependencies in CI. The
authenticated endpoints are:

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Minimal authenticated health response with no configuration details. |
| `POST` | `/ai/chat` | Chat request shaped for Foundry. |
| `POST` | `/ai/vision` | Vision request shaped for Foundry. |
| `POST` | `/speech/synthesize` | Speech synthesis request shaped for Speech. |

Relay token validation checks the Entra signature through an injected verifier,
then issuer, tenant, relay audience, lifetime, and the required app role/scope
or enrolled-device claim. Tokens minted for Microsoft Graph or any other API
are rejected. Foundry and Speech calls use the relay's managed identity; the
caller bearer token is never forwarded.

Required runtime configuration:

- `AZURE_TENANT_ID`
- `AZURE_CLIENT_ID`
- `SPARKY_RELAY_URL`
- `SPARKY_RELAY_AUDIENCE`
- `SPARKY_RELAY_DEVICE_SCOPE`
- `SPARKY_FOUNDRY_SCOPE`
- `SPARKY_SPEECH_SCOPE`

Deployment adapters should additionally configure the relay-required app role,
scope, or enrolled-device claim used by `RelayAuthConfig`.

Relay-auth smoke validation for the Pi is automated by the stdlib harness:

```powershell
python scripts\relay_auth_smoke.py --ci
python scripts\relay_auth_smoke.py
```

Use `--ci` for the no-network fake run; omit it on the Raspberry Pi after
exporting the Entra public-client and relay settings.

### Device hardware access

Device code never imports `pidog`, `robot_hat`, or `vilib` directly. It talks to
the ports in `sparky_device.hardware`, which are backed either by the SunFounder
libraries on a real robot or by recording simulators everywhere else. Select the
backing implementation with the `SPARKY_HARDWARE` environment variable
(`pidog`, `simulator`, or `auto`):

```powershell
$env:PYTHONPATH = "src/device"
$env:SPARKY_HARDWARE = "simulator"
python -c "from sparky_device.hardware import create_ports; print(create_ports().profile)"
```

Because the simulators are the default off-robot, the test suite runs on any
machine without PiDog hardware attached. See
[docs/running-on-the-pi.md](docs/running-on-the-pi.md) for installing the vendor
libraries, running against real hardware, and the hardware-in-the-loop
validation checklist. The CI-runnable device smoke harness is the same checklist
entry point in simulator mode:

```powershell
python scripts\motion_service_hil.py --ci
```

Planner-facing device services live in `sparky_device.services`. `MotionService`
normalizes movement intents, `SensorService` returns status-bearing sensor
snapshots, and `CameraService` owns camera start/capture/stop while packaging
frames for relay submission. Camera packaging records source dimensions,
packaged dimensions, sequence, monotonic timestamp, and source ID; optional
resizing is best-effort and falls back to the native bytes when no image stack is
installed.

For next steps:

1. Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
2. Review the accepted ADRs in [docs/adr/](docs/adr/).
3. Work from the milestone issues summarized in [docs/PLAN.md](docs/PLAN.md).