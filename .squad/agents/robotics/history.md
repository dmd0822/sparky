# Project Context

- **Project:** sparky
- **Requester:** Dave Davis
- **Initialized:** 2026-08-28T13:50:31.473-04:00
- **Status:** Planning-only; implementation blocked

## Core Context

The likely environment is Python on Raspberry Pi with PiDog hardware plus Azure AI/Speech integration, but exact languages, devices, versions, and APIs are assumptions pending read-only verification.

Robotics will assess motion/sensor interfaces, physical safety, hardware abstraction, and compatibility of `exlibs/pidog`, `exlibs/robot-hat`, and `exlibs/vilib`. Findings feed Architect and must not modify application code or anything under `exlibs/`.

## Governance

No application/product code may begin until Dave Davis explicitly approves both architecture documentation and the project plan.

## Learnings

Phase 2 initialization assigned Robotics the early read-only hardware and external-library assessment.
