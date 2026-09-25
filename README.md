# Sparky

Sparky is an AI-powered robot dog built on the [SunFounder PiDog](https://docs.sunfounder.com/projects/pidog/en/latest/) platform and augmented with Azure AI services through Microsoft Foundry.

## Vendor platform references

- SunFounder PiDog docs: <https://docs.sunfounder.com/projects/pidog/en/latest/>
- `robot-hat`: <https://github.com/sunfounder/robot-hat>
- `vilib`: <https://github.com/sunfounder/vilib>
- `pidog`: <https://github.com/sunfounder/pidog>

## Architecture

- Architecture overview: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Architecture decisions: [docs/adr/](docs/adr/)
- Delivery plan: [docs/PLAN.md](docs/PLAN.md)

## What this project will contain

Sparky is planned as a monorepo with separate areas for source code, infrastructure, and documentation:

```text
src/                 Application code only
  device/            Raspberry Pi runtime and hardware adapters
  cloud/             Azure-hosted relay/API services
  shared/            Shared contracts and reusable libraries
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
- README and architecture docs updated alongside meaningful changes

## Getting started

Implementation has not started yet. The current branch establishes the architecture and delivery plan.

For next steps:

1. Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
2. Review the accepted ADRs in [docs/adr/](docs/adr/).
3. Work from the milestone issues summarized in [docs/PLAN.md](docs/PLAN.md).