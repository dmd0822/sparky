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
- M0 issue-tracking work for the dual-approval gate is now being documented in `docs/architecture/m0-issue-1-tracking.md`
- Minimal source-code validation has begun under `src/` with a PiDog connectivity smoke test
- The project is now moving from planning into a small, incremental implementation phase

## Architecture package

The planning package includes the architecture, ADRs, risk register, and milestone plan:

- [`docs/architecture/README.md`](docs/architecture/README.md)
- [`docs/architecture/system-architecture.md`](docs/architecture/system-architecture.md)
- [`docs/architecture/project-plan.md`](docs/architecture/project-plan.md)
- [`docs/architecture/m0-issue-1-tracking.md`](docs/architecture/m0-issue-1-tracking.md)
- [`docs/architecture/dual-approval.md`](docs/architecture/dual-approval.md)
- [`docs/project-plan/dual-approval.md`](docs/project-plan/dual-approval.md)
- [`docs/architecture/decisions/`](docs/architecture/decisions/)
- [`docs/architecture/diagrams/`](docs/architecture/diagrams/)

## Key design directions

- Use a Pi-local hardware adapter to isolate direct access to the robot runtime
- Keep personas modular and immutable, with easy swapping between bundles
- Route Azure access through an explicit broker boundary rather than direct device-to-cloud coupling
- Default to privacy-safe behavior: no camera, no raw-audio retention, no transcript retention
- Use a single deterministic motion arbiter so the model cannot directly command actuators
- Start with push-to-talk and half-duplex operation, then extend if approved later

## Important constraints

- The PiDog runtime should use the standard SunFounder packages installed on the robot itself
- The architecture intentionally keeps the model, persona, and motion logic separate from direct hardware control
- The project is moving into incremental implementation after the architecture and project plan were defined

## Running on the PiDog

From the PiDog terminal, clone or sync this repository onto the robot, then run the smoke test directly against the installed PiDog packages:

```bash
cd ~
git clone <your-repo-url> sparky
cd sparky
python3 src/pidog_connectivity.py
python3 src/pidog_connectivity.py --init
```

The `--init` mode performs a quick PiDog startup check and plays a short bark sound (`single_bark_1`) to confirm the audio stack is working.

If the PiDog Python packages are installed using the standard SunFounder setup, the import pattern should match the official PiDog examples:

```python
from pidog import Pidog
from robot_hat import Servo, Motors
```

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
├── src/
│   └── pidog_connectivity.py
├── .squad/
├── README.md
└── ...
```

## Next step

Run the PiDog import smoke test in `src/pidog_connectivity.py` on the PiDog itself and capture any hardware-specific issues before expanding into the hardware adapter layer.
