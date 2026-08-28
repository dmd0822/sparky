# RAI Audit Trail

> Append-only evidence log. Entries are redacted — never contains raw secrets or harmful content.

<!-- Rai appends findings below -->

## 2026-08-28T14:48:03.102-04:00 — Review: docs/architecture/ planning package

- **Scope:** docs/architecture/README.md, system-architecture.md, project-plan.md, decisions/ADR-0001..ADR-0006 (documentation-tier review: content, terminology, privacy/safety substance).
- **Verdict:** 🟡 Amber / APPROVE WITH CONDITIONS. Planning proceeds; implementation gate stays closed pending Dave Davis approval + user decisions.
- **Planning blockers:** None found.
- **Implementation blockers (require user decisions, not engineering-closable):**
  - RAI-B1 | 🟡 | No specified physical e-stop / power cutoff / mute | Blocks M5 entry | Depends on UD-03
  - RAI-B2 | 🟡 | Undefined bystander/child consent model | Blocks M4 exit / M7 entry | Depends on UD-04
  - RAI-B3 | 🟡 | Undefined retention/deletion policy | Blocks M4 exit / M7 entry | Depends on UD-07
  - RAI-B4 | 🟡 | Vilib unauthenticated `0.0.0.0:9000` Flask service present in dependency tree (system-architecture.md EV-08/EV-09) | Blocks M7 entry | Depends on UD-05
  - RAI-B5 | 🟡 | Unratified credential/broker model | Blocks M2 entry | Depends on UD-10
- **Unresolved user decisions referenced:** UD-01 through UD-10, all open, owned by Dave Davis (README.md §"Ten Unresolved User Decisions"). UD-03 and UD-09 are hard-block gates (M5, M2 respectively).
- **Advisory finding (non-blocking) — camera/Vilib closure-wording inconsistency:** README.md ADR-0005 summary and system-architecture.md (§7 diagrams, §10 table, ~lines 302/410/814) state the Vilib exposure is resolved in absolute terms ("never started", "Refuse permanently"), while system-architecture.md §12 RAI-B4 (~line 831) correctly scopes this as conditional: "permanently mitigated only if UD-05 confirms the camera is unneeded." Recommendation: qualify the absolute-sounding passages (e.g., "never started in v1, pending UD-05") to avoid implying the mitigation is already final when it is contingent on an open user decision.
- **Terminology / bias / privacy / secrets scan:** No hardcoded credentials, PII, harmful content, or non-inclusive terminology (whitelist/blacklist, master/slave, gendered/ableist terms) found in the package.
- **Files modified by this review:** none in docs/architecture, product code, or exlibs (read-only, per policy scope for documentation review).
- **Redaction:** No sensitive data encountered; nothing redacted.

## 2026-08-28T14:48:03.102-04:00 — Re-review: docs/architecture/ revised wording (post Scribe revision)

- **Scope:** `system-architecture.md`, `README.md`, `decisions/ADR-0005-privacy-defaults-camera-disabled.md` — the wording corrected by Scribe's revision only.
- **Verdict:** 🟡 Amber / APPROVE WITH CONDITIONS — confirmed, unchanged from the initial pass.
- **Finding closed:** The camera/Vilib closure-wording inconsistency (absolute-sounding "never started"/"Refuse permanently" passages vs. the correctly-conditional RAI-B4 framing) is corrected — the unauthenticated-service ban reads as unconditional, while UD-05/broader camera-privacy status is explicitly stated as still open.
- **Blockers unchanged:** RAI-B1–RAI-B5, all still open, all tracing to unresolved user decisions.
- **Files modified by this review:** none (read-only, per policy scope).
- **Redaction:** No sensitive data encountered; nothing redacted.
