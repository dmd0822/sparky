# Device History

📌 Joined the team (2026-09-28T15:02:31-04:00): Added as Device Implementer to own `src/device/` — the Pi runtime, hardware ports, simulators, and vendor adapters.

📌 Inherited context (2026-09-28T15:02:31-04:00): The hardware abstraction layer landed in `sparky_device.hardware` (issue #5) — `ports.py`, `simulators.py`, `pidog_adapters.py`, `factory.py`, plus 85 tests in `tests/test_hardware_ports.py`. Vendor imports are lazy and validation runs before every vendor call so out-of-range commands never reach a servo. Pi setup and the hardware-in-the-loop checklist live in `docs/running-on-the-pi.md`.

📌 Team update (2026-09-28T15:18:24Z): Sparse-checkout Pi workflow gotchas — git sparse-checkout cone mode accepts directories only; passing a file path such as docs/running-on-the-pi.md fails with "fatal: ... is not a directory". Use --no-cone for file-level patterns. A sparse checkout limited to src/device supports running on the Pi, but not the repo-root test suite because tests/ imports via from src.device.sparky_device.hardware import ...