# Dual-Approval Support Package

> Draft architecture-side deliverable for GitHub issue #1.

| Field | Value |
|-------|-------|
| **Issue** | [#1](https://github.com/dmd0822/sparky/issues/1) |
| **Status** | Ready for review |
| **Owner** | @dmd0822 (provisional) |
| **Approval gate** | Dave Davis must explicitly approve this document and [docs/architecture/project-plan.md](project-plan.md) |

## Purpose

This document captures the planning and approval context for the M0 dual-approval gate so reviewers can evaluate the same evidence package without chasing the issue thread.

## Approval gate

Implementation remains blocked until Dave Davis explicitly approves both:

1. [system-architecture.md](system-architecture.md)
2. [project-plan.md](project-plan.md)

The review package also includes the decision issues [#11](https://github.com/dmd0822/sparky/issues/11) through [#20](https://github.com/dmd0822/sparky/issues/20) and the legal-review path in [issue #2](https://github.com/dmd0822/sparky/issues/2).

## Current state

- The planning package has been populated with evidence artifacts; per-UD decision files were created under `.squad/decisions/` and per-decision branches were pushed.
- Per-decision draft PRs were opened (PRs #23–#32) and a consolidated tracking PR (#33) was created and merged to `main` on 2026-09-08 to record and surface reviewer requests.
- Provisional owners on the UD issues are set to `@dmd0822`. Dave Davis explicit approval remains pending and is required by policy before merging individual decision PRs.
- The `exlibs/` tree remains read-only and is treated as evidence-only input for planning and architecture review.

## Review checklist

- [ ] Review the approval gate language and confirm the wording is explicit.
- [ ] Confirm the issue links and the per-decision issue map remain accurate.
- [ ] Confirm the current assumptions and approved-decisions record are visible to reviewers.

## Open questions

- Confirm Dave Davis's canonical GitHub handle for explicit owner assignment (currently provisional: `@dmd0822`). This is the remaining blocker for final merges.
- Confirm whether Architect & Reliability approvals should be recorded on the consolidated tracking PR (#33) or individually on each UD draft PR (#23–#32). Current automation posts reviewer requests to both the tracking PR and the individual PRs.
- Decide whether the project prefers a single-PR merge (aggregate) or individual UD-PR merges once all approvals are present; add guidance to merge-order policy if desired.
