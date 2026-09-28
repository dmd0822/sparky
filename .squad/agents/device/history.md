# Device History

📌 Joined the team (2026-09-28T15:02:31-04:00): Added as Device Implementer to own `src/device/` — the Pi runtime, hardware ports, simulators, and vendor adapters.

📌 Inherited context (2026-09-28T15:02:31-04:00): The hardware abstraction layer landed in `sparky_device.hardware` (issue #5) — `ports.py`, `simulators.py`, `pidog_adapters.py`, `factory.py`, plus 85 tests in `tests/test_hardware_ports.py`. Vendor imports are lazy and validation runs before every vendor call so out-of-range commands never reach a servo. Pi setup and the hardware-in-the-loop checklist live in `docs/running-on-the-pi.md`.
