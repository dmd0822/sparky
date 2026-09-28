# RGB style parity session — 2026-09-28T16:26:51-04:00

- Dave reported a second real-hardware PiDog signal: HIL bench step 8 crashed with `ValueError: Invalid style value.` before steps 9-12 could run.
- Device traced the immediate defect to `style="solid"` in `docs/running-on-the-pi.md`; the vendor accepts exactly `monochromatic`, `breath`, `boom`, `bark`, `speak`, and `listen`.
- Device fixed the deeper simulator/hardware parity gap by moving `RGB_STYLES` and `validate_rgb_style()` into `ports.py`, then calling the shared validator from both the PiDog adapter and simulator before any side effect.
- `solid` now fails in simulation with a `HardwareError` that names the invalid value and lists valid styles; all six vendor styles are accepted.
- The fix was verified in simulation and tests (`179 passed`) but has not yet been re-run on the real PiDog hardware.