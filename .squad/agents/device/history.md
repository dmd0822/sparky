# Device History

📌 Joined the team (2026-09-28T15:02:31-04:00): Added as Device Implementer to own `src/device/` — the Pi runtime, hardware ports, simulators, and vendor adapters.

📌 Inherited context (2026-09-28T15:02:31-04:00): The hardware abstraction layer landed in `sparky_device.hardware` (issue #5) — `ports.py`, `simulators.py`, `pidog_adapters.py`, `factory.py`, plus 85 tests in `tests/test_hardware_ports.py`. Vendor imports are lazy and validation runs before every vendor call so out-of-range commands never reach a servo. Pi setup and the hardware-in-the-loop checklist live in `docs/running-on-the-pi.md`.

📌 Team update (2026-09-28T15:18:24Z): Sparse-checkout Pi workflow gotchas — git sparse-checkout cone mode accepts directories only; passing a file path such as docs/running-on-the-pi.md fails with "fatal: ... is not a directory". Use --no-cone for file-level patterns. A sparse checkout limited to src/device supports running on the Pi, but not the repo-root test suite because tests/ imports via from src.device.sparky_device.hardware import ...
📌 HIL fix (2026-09-28T19:40:00Z): Fixed the Vilib first-frame race with a bounded capture poll and made PiDog/simulator wait_all_done(timeout) enforce timeout failures for stuck motion. Validated 173 tests plus compileall for src/device/sparky_device/hardware.

📌 HIL docs update (2026-09-28T19:55:00Z): Added a bench-ready hardware-in-the-loop procedure to docs/running-on-the-pi.md with environment setup, import/profile checks, prompted motion/sensor/board/camera validation, timeout-bounded motion waits, clean shutdown, and PR result recording. Updated the camera troubleshooting note to reflect the adapter's first-frame wait.

📌 Camera degradation fix (2026-09-28T20:10:00Z): Missing or uninitialised Vilib/Picamera2 cameras now surface as HardwareUnavailableError at lazy camera start/capture time instead of blocking port construction. HIL docs now split required PiDog imports from optional Vilib camera validation and keep the bench script running through shutdown when step 11 camera validation is unavailable.
