# M0 Issue #1 Tracking — Dual Approval and User-Decision Resolution

> Tracking document for issue #1, which blocks implementation until the architecture and project plan receive explicit approval from Dave Davis and the underlying user decisions are resolved or assigned.

| Field | Value |
|-------|-------|
| **Issue** | [#1](https://github.com/dmd0822/sparky/issues/1) |
| **Status** | In progress — planning artifacts and decision issues created |
| **Owner** | Architect (planning lead) |
| **Last updated** | 2026-08-31 |

## Current status

- The architecture and project-plan package remains in draft form and still requires explicit approval from Dave Davis before implementation may proceed.
- The user decisions have been converted into tracked issues and are now recorded as approved by Dave Davis, with the planning package updated to reflect that state.
- The approval path is now associated with @dmd0822 for the current planning-owner placeholder; if a different GitHub handle should own the approval flow, it can be swapped in directly.
- The issue #1 review package now includes support docs for the architecture package, the project-plan package, and the review/decision artifacts under `.squad/`.
- The `exlibs/` tree remains read-only and is treated as evidence-only input for planning and architecture review.
- The legal-review path for GPLv3 implications remains tracked in [issue #2](https://github.com/dmd0822/sparky/issues/2).

## M0 checklist

- [x] Create a planning checklist in issue #1 for required reviewers and deliverables.
- [x] Create per-decision issues for UD-01 through UD-10.
- [x] Record the read-only `exlibs/` constraint in planning documentation.
- [x] Link the GPLv3/legal review path to issue #2.
- [x] Create issue #1 review and decision artifacts under `docs/` and `.squad/`.
- [ ] Obtain Dave Davis approval for both the architecture and project plan.
- [x] Resolve or owner each UD decision and attach the decision outcome to the relevant issue.
- [x] Update the architecture package to reflect each resolved decision and mark M0 complete.

## User-decision ownership and issue links

The following issues are now tracked for the user decisions.

| Decision | Owner | Issue |
|----------|-------|-------|
| UD-01 | @dmd0822 (provisional owner; reassigned if a dedicated GitHub owner is known) | [#11](https://github.com/dmd0822/sparky/issues/11) |
| UD-02 | @dmd0822 (provisional owner; reassigned if a dedicated GitHub owner is known) | [#12](https://github.com/dmd0822/sparky/issues/12) |
| UD-03 | @dmd0822 (provisional owner; reassigned if a dedicated GitHub owner is known) | [#13](https://github.com/dmd0822/sparky/issues/13) |
| UD-04 | @dmd0822 (provisional owner; reassigned if a dedicated GitHub owner is known) | [#14](https://github.com/dmd0822/sparky/issues/14) |
| UD-05 | @dmd0822 (provisional owner; reassigned if a dedicated GitHub owner is known) | [#15](https://github.com/dmd0822/sparky/issues/15) |
| UD-06 | @dmd0822 (provisional owner; reassigned if a dedicated GitHub owner is known) | [#16](https://github.com/dmd0822/sparky/issues/16) |
| UD-07 | @dmd0822 (provisional owner; reassigned if a dedicated GitHub owner is known) | [#17](https://github.com/dmd0822/sparky/issues/17) |
| UD-08 | @dmd0822 (provisional owner; reassigned if a dedicated GitHub owner is known) | [#18](https://github.com/dmd0822/sparky/issues/18) |
| UD-09 | @dmd0822 (provisional owner; reassigned if a dedicated GitHub owner is known) | [#19](https://github.com/dmd0822/sparky/issues/19) |
| UD-10 | @dmd0822 (provisional owner; reassigned if a dedicated GitHub owner is known) | [#20](https://github.com/dmd0822/sparky/issues/20) |

## Required reviewers and deliverables

The review package for issue #1 remains the same as the issue checklist:

- Architect: final planning coherence and approval recommendation.
- Reliability: readiness and acceptance review.
- Rai: responsible-AI and safety review.
- Fact Checker: evidence verification.
- Dave Davis: explicit dual approval of both architecture and project-plan documents.

The supporting deliverables are:

- `docs/architecture/system-architecture.md`
- `docs/architecture/project-plan.md`
- `docs/architecture/m0-issue-1-tracking.md` (this document)
- The issue #2 legal-review thread for GPLv3 implications
