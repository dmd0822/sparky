# Sparky

Audio animatronic dog project inspired by the SunFounder PiDog platform, with a persona-driven runtime, Azure AI-backed conversational layer, and a hardware-abstraction-first architecture.

## Project goal

Sparky is a Raspberry Pi-based companion device intended to combine:

- PiDog-compatible motion, sensing, and lighting hardware
- Azure AI for speech and language processing
- swappable, versioned personas with clean enable/disable wiring
- safe, deterministic behavior under a motion arbiter and motion safety rules
- a privacy-first, fail-closed design

## Current status

The architecture and planning work is complete, and the first implementation milestone has begun.

- Architecture and project-planning documentation are complete under `docs/architecture/`
- A read-only assessment of the supplied `exlibs` libraries has been captured
- Minimal source-code validation has begun under `src/` with a PiDog connectivity smoke test
- The project is now moving from planning into a small, incremental implementation phase

## Architecture package

The planning package includes the architecture, ADRs, risk register, and milestone plan:

- [`docs/architecture/README.md`](docs/architecture/README.md)
- [`docs/architecture/system-architecture.md`](docs/architecture/system-architecture.md)
- [`docs/architecture/project-plan.md`](docs/architecture/project-plan.md)
- [`docs/architecture/decisions/`](docs/architecture/decisions/)
- [`docs/architecture/diagrams/`](docs/architecture/diagrams/)

## Key design directions

- Use a Pi-local hardware adapter to isolate all direct access to `exlibs`
- Keep personas modular and immutable, with easy swapping between bundles
- Route Azure access through an explicit broker boundary rather than direct device-to-cloud coupling
- Default to privacy-safe behavior: no camera, no raw-audio retention, no transcript retention
- Use a single deterministic motion arbiter so the model cannot directly command actuators
- Start with push-to-talk and half-duplex operation, then extend if approved later

## Important constraints

- `exlibs` is treated as read-only evidence and not modified
- The architecture intentionally does not rely on the vendor-provided PiDog AI assistant path because the supplied library versions are mismatched with the documented runtime
- The project is not build-ready until the architecture and project plan are approved

## Repository layout

```text
.
├── docs/
│   └── architecture/
│       ├── README.md
│       ├── system-architecture.md
│       ├── project-plan.md
│       ├── decisions/
│       └── diagrams/
├── exlibs/
├── .squad/
├── README.md
└── ...
```

## Next step

Run the basic PiDog import smoke test in `src/pidog_connectivity.py` and capture any hardware or dependency issues before expanding into the hardware adapter layer.

## Source layout

```text
.
├── docs/
│   └── architecture/
│       ├── README.md
│       ├── system-architecture.md
│       ├── project-plan.md
│       ├── decisions/
│       └── diagrams/
├── exlibs/
├── src/
│   └── pidog_connectivity.py
├── .squad/
├── README.md
└── ...
```
