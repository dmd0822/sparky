# `sparky-device`

The Raspberry Pi application package lives in `sparky_device/`. Hardware-facing
code belongs here and must use ports/adapters so unit tests do not require
PiDog hardware. Keep device tests in `tests/` beside this package.

## Hardware ports

`sparky_device.hardware` is the boundary between application code and the
SunFounder libraries. Import from the package, never from `pidog`, `robot_hat`,
or `vilib` directly:

```python
from sparky_device.hardware import create_ports

with create_ports() as robot:
    robot.motion.do_action("sit", speed=60)
    robot.motion.wait_all_done()
    print(robot.sensors.read_distance_cm())
```

| Module | Purpose |
| --- | --- |
| `ports.py` | Protocols, value objects, and the `RobotPorts` bundle |
| `simulators.py` | Recording fakes for tests and off-robot development |
| `pidog_adapters.py` | Vendor adapters; the only module that imports SunFounder packages |
| `factory.py` | `create_ports()` and the `SPARKY_HARDWARE` profile switch |

Set `SPARKY_HARDWARE` to `pidog`, `simulator`, or `auto` (the default) to choose
the implementation. Vendor imports are lazy, so this package imports cleanly on
a machine with no robot attached.

See [docs/running-on-the-pi.md](../../docs/running-on-the-pi.md) for installing
the vendor libraries and running against real hardware.
