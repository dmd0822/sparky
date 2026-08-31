# Decision Record — Dual Approval Planning Gate

> Record for the issue #1 planning gate.

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Related issue** | [#1](https://github.com/dmd0822/sparky/issues/1) |
| **Decision owner** | Architect |

## Context

The planning package for Sparky requires explicit approval from Dave Davis before implementation may begin. The approval gate covers both the architecture document and the project-plan document, while the user decisions are now recorded as approved and the remaining gate is explicit document approval.

## Decision

The repository will track the dual-approval gate through a dedicated support package and review artifacts so that the required reviewers and review outputs are visible from the repo and the issue thread.

## Consequences

- The issue checklist now has concrete review artifacts to complete.
- The decision issues remain visible and linkable from the review package.
- The `exlibs/` tree remains read-only and is treated as evidence-only input for planning and review.
