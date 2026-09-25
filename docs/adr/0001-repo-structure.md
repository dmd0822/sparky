# ADR 0001: Monorepo structure for device, cloud, and infrastructure code

- **Status:** Accepted
- **Date:** 2026-09-25
- **Owners:** lead

## Context

The project must keep infrastructure as code separate from application code, keep architecture documentation current, and support parallel work across device, cloud, and shared contract layers.

The codebase starts empty, so the first structural decision needs to optimize for:

- clear ownership boundaries
- GitHub Actions workflow separation for infra vs code
- testability without PiDog hardware in CI
- easy onboarding for both Raspberry Pi and Azure contributors

## Decision

Use a single repository with top-level separation between source, infrastructure, and documentation:

```text
.
├── src/
│   ├── device/         # Raspberry Pi runtime, hardware adapters, behavior loop
│   ├── cloud/          # Azure-hosted relay/API services
│   └── shared/         # Contracts, schemas, reusable client libraries
├── infra/
│   ├── modules/        # Reusable Bicep modules
│   ├── environments/   # Environment compositions (dev, prod)
│   └── scripts/        # Deployment helpers
├── docs/
│   ├── adr/
│   └── diagrams/
└── .github/
    └── workflows/      # Separate infra and code pipelines
```

Within each `src/*` subproject, keep tests close to the implementation using a local `tests/` folder and an independent package manifest.

## Consequences

### Positive

- Satisfies the hard requirement to keep `/infra` separate from `/src`.
- Lets device and cloud work progress independently without forcing two repositories.
- Keeps shared contracts versioned atomically with both producers and consumers.
- Makes workflow path filters straightforward for infra-only vs code-only changes.

### Negative

- Requires explicit discipline to avoid cross-layer imports.
- Monorepo CI configuration is slightly more complex than a single-package repository.

### Follow-up

- Enforce path-based workflow triggers and CODEOWNERS later.
- Add package-level README files when implementation begins.
