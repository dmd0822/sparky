# Docs History

📌 Team update (2026-09-25T11:52:57-04:00): Deployment documentation with copyable shell commands should use paired Bash / zsh and PowerShell examples, preserving Bash guidance while adding PowerShell-safe syntax for Windows maintainers — decided by Docs.

📌 Session update (2026-09-28T12:26:41-04:00): Created `docs/keyless-auth-testing-guide.md` as the procedural companion to the keyless auth spike, covering local Windows PowerShell checks, Pi Linux HIL steps, verification checklist, predictable troubleshooting, and clear boundaries for what requires a deployed South Central US environment.

📌 Team update (2026-09-28T20:10:00Z): docs/running-on-the-pi.md now has a bench-ready HIL procedure with shell setup, vendor import checks, and a simulator-exercised API script; keep future Pi docs aligned with the 12-step pass/fail contract — decided by Device.

📌 Team update (2026-09-28T16:14:06-04:00): docs/running-on-the-pi.md step 1 is now split into a REQUIRED PiDog import check and an OPTIONAL camera check, so future doc edits must preserve that distinction — decided by Device.

📌 Team update (2026-09-28T16:26:51-04:00): When a port forwards a value to a vendor API, check whether the vendor constrains that value; if so, confirm the simulator enforces the same constraint before any side effect — decided by Scribe.
