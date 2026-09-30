# Docs History

📌 Team update (2026-09-25T11:52:57-04:00): Deployment documentation with copyable shell commands should use paired Bash / zsh and PowerShell examples, preserving Bash guidance while adding PowerShell-safe syntax for Windows maintainers — decided by Docs.

📌 Session update (2026-09-28T12:26:41-04:00): Created `docs/keyless-auth-testing-guide.md` as the procedural companion to the keyless auth spike, covering local Windows PowerShell checks, Pi Linux HIL steps, verification checklist, predictable troubleshooting, and clear boundaries for what requires a deployed South Central US environment.

📌 Team update (2026-09-28T20:10:00Z): docs/running-on-the-pi.md now has a bench-ready HIL procedure with shell setup, vendor import checks, and a simulator-exercised API script; keep future Pi docs aligned with the 12-step pass/fail contract — decided by Device.

📌 Team update (2026-09-28T16:14:06-04:00): docs/running-on-the-pi.md step 1 is now split into a REQUIRED PiDog import check and an OPTIONAL camera check, so future doc edits must preserve that distinction — decided by Device.

📌 Team update (2026-09-28T16:26:51-04:00): When a port forwards a value to a vendor API, check whether the vendor constrains that value; if so, confirm the simulator enforces the same constraint before any side effect — decided by Scribe.

📌 Team update (2026-09-28T16:45:35-04:00): HIL docs should avoid treating a completed script step as proof of hardware action when vendor work runs in background threads; preserve visible/manual confirmation language and note per-call vendor quirks where adapter workarounds exist — decided by Scribe.

📌 Team update (2026-09-29T09:50:26-04:00): docs/running-on-the-pi.md now documents the camera-optional bench pattern, Vilib's 640x480 limitation, three new camera troubleshooting rows, and a working-directory bench script output path instead of /tmp so stale copies are avoided — decided by Device.

📌 Team update (2026-09-29T09:50:26-04:00): Motion action names are now validated in the hardware contract layer before adapter or simulator side effects; docs/running-on-the-pi.md gained a valid-action list and a troubleshooting row. — decided by Device

📌 Session update (2026-09-30T14:56:49-04:00): Added README build/status badges for Code CI, Code CD, Infra CI, Infra CD, Python Validation, and Workflow Lint; squad automation workflows remain intentionally unbadged as bot plumbing.

📌 Team update (2026-09-30T14:56:49-04:00): README now carries build status badges for Code CI, Code CD, Infra CI, Infra CD, Python Validation, and Workflow Lint; bot automation workflows remain intentionally excluded — decided by docs.

### 2026-09-30: Documented shared perception contract rules
- Added ADR 0006 for issue #12 covering shared perception boundaries, ADR 0005 alignment, ownership, versioning, fixtures, and HIL validation.
- Updated `docs/ARCHITECTURE.md` so `sparky_contracts/` reflects perception DTOs, statuses, prompts, and contract versioning.
- Validated with `python -m unittest discover -s tests -p "test_docs_policy.py"` and `python -m unittest discover -s tests -p "test_repository_structure.py"`.
