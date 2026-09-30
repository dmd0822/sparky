# Device History

📌 Joined the team (2026-09-28T15:02:31-04:00): Added as Device Implementer to own `src/device/` — the Pi runtime, hardware ports, simulators, and vendor adapters.

📌 Inherited context (2026-09-28T15:02:31-04:00): The hardware abstraction layer landed in `sparky_device.hardware` (issue #5) — `ports.py`, `simulators.py`, `pidog_adapters.py`, `factory.py`, plus 85 tests in `tests/test_hardware_ports.py`. Vendor imports are lazy and validation runs before every vendor call so out-of-range commands never reach a servo. Pi setup and the hardware-in-the-loop checklist live in `docs/running-on-the-pi.md`.

📌 Team update (2026-09-28T15:18:24Z): Sparse-checkout Pi workflow gotchas — git sparse-checkout cone mode accepts directories only; passing a file path such as docs/running-on-the-pi.md fails with "fatal: ... is not a directory". Use --no-cone for file-level patterns. A sparse checkout limited to src/device supports running on the Pi, but not the repo-root test suite because tests/ imports via from src.device.sparky_device.hardware import ...
📌 HIL fix (2026-09-28T19:40:00Z): Fixed the Vilib first-frame race with a bounded capture poll and made PiDog/simulator wait_all_done(timeout) enforce timeout failures for stuck motion. Validated 173 tests plus compileall for src/device/sparky_device/hardware.

📌 HIL docs update (2026-09-28T19:55:00Z): Added a bench-ready hardware-in-the-loop procedure to docs/running-on-the-pi.md with environment setup, import/profile checks, prompted motion/sensor/board/camera validation, timeout-bounded motion waits, clean shutdown, and PR result recording. Updated the camera troubleshooting note to reflect the adapter's first-frame wait.

📌 Camera degradation fix (2026-09-28T20:10:00Z): Missing or uninitialised Vilib/Picamera2 cameras now surface as HardwareUnavailableError at lazy camera start/capture time instead of blocking port construction. HIL docs now split required PiDog imports from optional Vilib camera validation and keep the bench script running through shutdown when step 11 camera validation is unavailable.

📌 RGB style parity lesson (2026-09-28T16:26:51-04:00): A simulator that accepts a wider RGB style domain than the PiDog vendor masks real hardware defects. Shared value domains now belong in the hardware contract layer so adapters and simulators validate from the same source.

📌 RGB monochromatic hardware fix (2026-09-28T16:45:35-04:00): PiDog vendor monochromatic RGB style multiplies channels by brightness without casting back to int, so float brightness silently kills the strip thread on real hardware. The adapter now pre-scales monochromatic colours to integer channels and passes vendor brightness=1, while simulators continue recording the caller's original RGB intent.

📌 Camera contract hardening (2026-09-29T09:39:43-04:00): Made the camera port honest about Vilib's fixed 640x480 capture size, shared resolution validation between the PiDog adapter and simulator, added camera_available() for optional-camera flows, improved no-frame guidance for camera-less PiDog benches, and ensured failed Vilib starts clean up with camera_close().

📌 Motion action domain hardening (2026-09-29T09:50:26-04:00): Closed the fifth simulator-vs-vendor value-domain defect by moving PiDog motion action names into the hardware contract, sharing validation between adapter and simulator, preserving vendor-supported space forms via underscore normalisation, and rejecting typos/non-actions/eval-shaped input before any side effect.

📌 Motion service implementation (2026-09-29T10:13:04.815-04:00): Added `sparky_device.services.MotionService` for explicit stand/sit/lie/trot/forward/backward/turn/stop operations above `MotionPort`. The service rejects conflicting in-flight commands, honours stop immediately and idempotently, requires explicit stand before locomotion from seated/lying postures, and documents HIL smoke validation for issue #6.

📌 Test path portability lesson (2026-09-29T10:13:04.815-04:00): Repo tests must use `ROOT = Path(__file__).parents[1]` and `/` path joins, never OS-specific separators or CWD-relative paths — CI is ubuntu-latest.

📌 Motion HIL script lesson (2026-09-29T11:39:32.316-04:00): Operator-facing HIL checks should ship as runnable scripts under `scripts/`, not copy-paste Markdown snippets, and every hardware-moving script needs a simulator mode plus a cleanup path that safe-stops and closes ports on success, failure, or Ctrl+C.

📌 Full HIL script consolidation (2026-09-29T13:19:17.701-04:00): Folded port-level checklist steps 1-12 into `scripts/motion_service_hil.py` alongside motion-service steps 13-17, preserving lazy vendor imports, camera SKIP semantics, safe cleanup, simulator rehearsal, and adding `--steps`/`--only` for targeted reruns.

📌 Team update (2026-09-30T09:22:33.507-04:00): Sensor adapter work added a new SensorService with typed status-based readings; decisions.md now records explicit OK/UNAVAILABLE/MALFORMED semantics instead of ambiguous None, and real Pi HIL sensor smoke testing remains a follow-up risk. — decided by device


📌 Team update (2026-09-30T10:00:58.0877268-04:00): Reviewer rejection found malformed IMU data could be reported as OK; Lead owned the locked-out fix and added IMU validation in commit d87e61d with 223 tests passing.
📌 Team update (2026-09-30T09:14:16.352-04:00): PR #63 and PR #64 merged the issue #6 motion-service and HIL-script work to `main`. Durable lessons: cross-platform CI requires repo-root `/` path joins instead of Windows/CWD-relative literals, and the HIL script's SKIP-vs-FAIL distinction is load-bearing because optional camera absence must not hide required PiDog/profile failures.

📌 Team update (2026-09-30T11:10:46-04:00): Relay API surface now enforces injected Entra token validation and managed-identity downstream calls; PR #69 closes #9 — decided by Security


📌 Relay auth smoke harness (2026-09-30T11:20:01-04:00): Added `scripts/relay_auth_smoke.py` as a stdlib-only Pi harness for device-code relay sign-in, relay-audience claim inspection, authenticated `/health`, `/ai/chat`, `/ai/vision`, and `/speech/synthesize` smoke calls, structured negative-auth replay, credential-shaped env-name reporting, and CI fake mode. Added unittest coverage and updated keyless/Pi/README docs.
📌 Team update (2026-09-30T12:45:22-04:00): The relay now has a real ASGI entry point and Dockerfile, so device smoke/HIL harnesses can target the packaged relay image instead of a placeholder path — decided by lead.


📌 Team update (2026-09-30T12:45:22-04:00): Relay now returns 503 `relay_unavailable` on AI routes and an anonymous 200 on `/health` until `relayAudience` is supplied at deploy time — device-side smoke runs should expect this.

