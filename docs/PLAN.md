# Delivery Plan

This plan was generated from the lead architecture pass on 2026-09-25.

## Labeling note

These planning issues intentionally use domain/type labels but **do not** carry the `squad` inbox label. They are already triaged and sequenced by the lead, so adding `squad` would create redundant re-triage noise.

## Milestones

| Milestone | Scope | Issue count |
| --- | --- | ---: |
| M1 Foundations & Keyless Platform | Scaffold the repo, establish Bicep and workflow baselines, and prove the keyless Entra-to-relay-to-Foundry path end to end. | 4 |
| M2 Device Control Baseline | Wrap the SunFounder libraries behind testable interfaces and establish reliable motion and sensor control without requiring real hardware in CI. | 4 |
| M3 Relay API & Vision Perception | Stand up the secure relay surface and connect camera capture to cloud vision understanding through typed contracts. | 4 |
| M4 Voice Conversation Loop | Connect microphone input, speech recognition, Foundry reasoning, and spoken output into a secure end-to-end conversation pipeline. | 4 |
| M5 Agent Behavior & Orchestration | Turn raw motion, sensor, voice, and vision capabilities into a coherent robot personality and decision loop. | 4 |
| M6 Hardening, Security & Observability | Add telemetry, resilience, and explicit security review so the system is supportable and trustworthy beyond demos. | 4 |
| M7 Release Readiness & Demo | Package the system for repeatable setup, validate end-to-end scenarios, finish runbooks, and make an explicit release decision. | 4 |

## M1 Foundations & Keyless Platform

Scaffold the repo, establish Bicep and workflow baselines, and prove the keyless Entra-to-relay-to-Foundry path end to end.

| Issue | Title | Labels |
| --- | --- | --- |
| [#1](https://github.com/dmd0822/sparky/issues/1) | Scaffold the monorepo structure and Python package conventions | type:chore, docs |
| [#2](https://github.com/dmd0822/sparky/issues/2) | Author baseline Bicep modules and environment entry points | type:feature, infra, cloud |
| [#3](https://github.com/dmd0822/sparky/issues/3) | Add separate GitHub Actions skeletons for infra and code delivery | type:feature, ci-cd, infra, testing |
| [#4](https://github.com/dmd0822/sparky/issues/4) | Prove the Pi-to-relay-to-Foundry keyless auth path with a spike | type:spike, security, cloud, ai, docs |

## M2 Device Control Baseline

Wrap the SunFounder libraries behind testable interfaces and establish reliable motion and sensor control without requiring real hardware in CI.

| Issue | Title | Labels |
| --- | --- | --- |
| [#5](https://github.com/dmd0822/sparky/issues/5) | Build hardware abstraction ports and simulators for PiDog vendor libraries | type:feature, device, testing |
| [#6](https://github.com/dmd0822/sparky/issues/6) | Implement motion and posture services around the `pidog` library | type:feature, device, testing |
| [#7](https://github.com/dmd0822/sparky/issues/7) | Implement sensor adapters for ultrasonic, touch, IMU, and sound direction | type:feature, device, testing |
| [#8](https://github.com/dmd0822/sparky/issues/8) | Add device-side test harness and hardware-in-the-loop smoke checklist | type:docs, device, testing, docs |

## M3 Relay API & Vision Perception

Stand up the secure relay surface and connect camera capture to cloud vision understanding through typed contracts.

| Issue | Title | Labels |
| --- | --- | --- |
| [#9](https://github.com/dmd0822/sparky/issues/9) | Build the relay API surface with Entra token validation | type:feature, cloud, security, testing |
| [#10](https://github.com/dmd0822/sparky/issues/10) | Implement camera capture and frame packaging using `vilib` | type:feature, device, ai, testing |
| [#11](https://github.com/dmd0822/sparky/issues/11) | Integrate Microsoft Foundry vision analysis behind a perception adapter | type:feature, cloud, ai, testing |
| [#12](https://github.com/dmd0822/sparky/issues/12) | Define shared perception contracts, fixtures, and sample prompts | type:docs, ai, docs, testing |

## M4 Voice Conversation Loop

Connect microphone input, speech recognition, Foundry reasoning, and spoken output into a secure end-to-end conversation pipeline.

| Issue | Title | Labels |
| --- | --- | --- |
| [#13](https://github.com/dmd0822/sparky/issues/13) | Implement microphone capture and audio buffering on the Pi | type:feature, device, testing |
| [#14](https://github.com/dmd0822/sparky/issues/14) | Integrate speech-to-text through Entra-authenticated Speech endpoints | type:feature, cloud, ai, security, testing |
| [#15](https://github.com/dmd0822/sparky/issues/15) | Integrate text-to-speech with Speech and robot-hat speaker playback | type:feature, device, cloud, ai, testing |
| [#16](https://github.com/dmd0822/sparky/issues/16) | Build the conversation orchestrator for STT, chat, and TTS | type:feature, device, cloud, ai, testing |

## M5 Agent Behavior & Orchestration

Turn raw motion, sensor, voice, and vision capabilities into a coherent robot personality and decision loop.

| Issue | Title | Labels |
| --- | --- | --- |
| [#17](https://github.com/dmd0822/sparky/issues/17) | Define system prompts, personality settings, and safety rails | type:feature, ai, docs, security |
| [#18](https://github.com/dmd0822/sparky/issues/18) | Implement the behavior planner that fuses voice, vision, and sensor inputs | type:feature, device, ai, testing |
| [#19](https://github.com/dmd0822/sparky/issues/19) | Implement action execution and interrupt arbitration | type:feature, device, testing, security |
| [#20](https://github.com/dmd0822/sparky/issues/20) | Add interactive command mode and degraded offline fallback behaviors | type:feature, device, ai, testing |

## M6 Hardening, Security & Observability

Add telemetry, resilience, and explicit security review so the system is supportable and trustworthy beyond demos.

| Issue | Title | Labels |
| --- | --- | --- |
| [#21](https://github.com/dmd0822/sparky/issues/21) | Add structured logging, tracing, and cloud telemetry | type:feature, cloud, device, testing |
| [#22](https://github.com/dmd0822/sparky/issues/22) | Add resilience controls, retries, and safe-state behavior | type:feature, device, cloud, testing, security |
| [#23](https://github.com/dmd0822/sparky/issues/23) | Perform a security review and produce a threat model remediation backlog | type:spike, security, docs, cloud, device |
| [#24](https://github.com/dmd0822/sparky/issues/24) | Measure latency, power, and runtime stability with soak testing | type:feature, device, testing, ai |

## M7 Release Readiness & Demo

Package the system for repeatable setup, validate end-to-end scenarios, finish runbooks, and make an explicit release decision.

| Issue | Title | Labels |
| --- | --- | --- |
| [#25](https://github.com/dmd0822/sparky/issues/25) | Package the Pi runtime for repeatable startup and deployment | type:feature, device, ci-cd, docs |
| [#26](https://github.com/dmd0822/sparky/issues/26) | Build the end-to-end acceptance suite and demo scenarios | type:feature, testing, device, cloud, ai |
| [#27](https://github.com/dmd0822/sparky/issues/27) | Write operator and developer runbooks plus the release checklist | type:docs, docs, security, testing |
| [#28](https://github.com/dmd0822/sparky/issues/28) | Run the release candidate bug bash and record the v1 readiness decision | type:chore, testing, docs |
