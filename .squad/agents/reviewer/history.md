
### 2026-09-28T12:26:41-04:00 — Keyless auth testing guide rejection revision

- Reviewed the docs-auth testing guide after rejecting the docs-authored artifact under reviewer lockout; docs remains locked out for this revision cycle.
- Corrected the Pi-side Foundry and Speech relay curl examples so they use the exported relay access-token variable instead of a literal redacted Authorization header.
- Clarified that the Speech step reuses the token exported in the Foundry step, and updated the demo manifest/test expectation so generated relay examples include a Bearer authorization placeholder.
- Verified the guide against `keyless_auth.py`, `keyless_guard.py`, and `docs/keyless-auth-spike.md`; no additional guide structure changes were needed.
