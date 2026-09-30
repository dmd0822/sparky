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

## Motion service

`sparky_device.services.MotionService` is the planner-facing layer above
`MotionPort`. It exposes explicit operations instead of raw action strings,
rejects conflicting non-stop commands while motion is in flight, always lets
`stop()` pre-empt immediately, and requires an explicit `stand()` before
locomotion from `sit` or `lie`.

```python
from sparky_device.hardware import create_ports
from sparky_device.services import MotionService

with create_ports() as robot:
    motion = MotionService(robot.motion)
    motion.sit()
    motion.wait_until_idle(timeout=10)
    motion.stand()
    motion.wait_until_idle(timeout=10)
    motion.forward(steps=3, speed=35)
    motion.stop()
```

| Module | Purpose |
| --- | --- |
| `services/motion.py` | Service-level posture and locomotion commands with conflict handling |
| `services/sensors.py` | Timestamped sensor snapshots with explicit unavailable and malformed statuses |

## Sensor service

`sparky_device.services.SensorService` is the planner-facing layer above
`SensorPort`. It reads ultrasonic distance, dual touch, IMU, and sound
direction into one timestamped snapshot for each device-loop tick. Sensor
timeouts such as an invalid ultrasonic echo or no detected sound are represented
as `ReadingStatus.OK` with a `None` value and a detail message; missing hardware
or malformed port output becomes an explicit status instead of an exception.

```python
from sparky_device.hardware import create_ports
from sparky_device.services import ReadingStatus, SensorService

with create_ports() as robot:
    sensors = SensorService(robot.sensors)
    snapshot = sensors.read_snapshot()
    if snapshot.distance.status is ReadingStatus.OK:
        print(snapshot.distance.distance_cm)
    else:
        print(snapshot.distance.as_dict())
```

Set `SPARKY_HARDWARE` to `pidog`, `simulator`, or `auto` (the default) to choose
the implementation. Vendor imports are lazy, so this package imports cleanly on
a machine with no robot attached.

See [docs/running-on-the-pi.md](../../docs/running-on-the-pi.md) for installing
the vendor libraries and running against real hardware.
