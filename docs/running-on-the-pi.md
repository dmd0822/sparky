# Running Sparky code on the Raspberry Pi

This guide covers getting the device runtime onto a PiDog and executing it
against real hardware. Everything in `sparky_device.hardware` runs on a laptop
or a CI runner too — see [Running without a Pi](#running-without-a-pi) — so
reach for the Pi only when you need to validate actual motion, audio, camera,
or sensors.

## Hardware and OS prerequisites

| Requirement | Value |
| --- | --- |
| Board | Raspberry Pi 4B or 5 (the PiDog kit ships with a Pi 4B tray) |
| OS | Raspberry Pi OS (64-bit), Bookworm or newer |
| Python | 3.11 or newer (Bookworm ships 3.11) |
| Add-on board | SunFounder Robot HAT, seated and powered |
| Power | Battery pack charged and switched on — USB power alone will not drive servos |

Enable the buses the Robot HAT needs, then reboot:

```bash
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_spi 0
sudo reboot
```

## Install the SunFounder libraries

The vendor libraries are installed system-wide because `robot_hat` compiles
against the Pi's GPIO stack. Run these once per device:

```bash
sudo apt update
sudo apt install -y git python3-pip python3-venv python3-dev \
  libopencv-dev python3-opencv portaudio19-dev

cd ~
git clone https://github.com/sunfounder/robot-hat.git -b v2.0
cd robot-hat && sudo python3 setup.py install && cd ~

git clone https://github.com/sunfounder/vilib.git -b picamera2
cd vilib && sudo python3 install.py && cd ~

git clone https://github.com/sunfounder/pidog.git
cd pidog && sudo python3 setup.py install && cd ~

sudo bash ~/pidog/i2samp.sh   # enables the speaker; reboots when finished
```

Confirm the libraries import before going further:

```bash
python3 -c "import pidog, robot_hat, vilib; print('vendor libraries OK')"
```

## Get the repository onto the Pi

```bash
git clone https://github.com/dmd0822/sparky.git
cd sparky
```

For Pi deployments where disk usage matters, you can clone only the device
package and docs instead:

```bash
git clone --filter=blob:none --sparse https://github.com/dmd0822/sparky.git
cd sparky
git sparse-checkout set src/device docs
```

This sparse checkout is about 0.3 MB versus the full repo, and `src/device/` is
self-contained for running on the Pi. Cone mode is the default with `--sparse`
and accepts directories only, so the command includes all of `docs` rather than
only this file; use `--no-cone` if you need file-level patterns. Top-level files
such as `README.md`, `LICENSE`, and `.gitignore` still appear in cone mode. If
you do not want the docs on the Pi, `src/device` alone is the true minimum.

Use a full clone when you want to run the repo-root test suite. The tests in
`tests/` import through the full tree, so a sparse checkout of `src/device`
supports running device code but not the repo-root tests.

Because the SunFounder packages are installed into the system interpreter, run
device code with the system Python rather than an isolated virtual environment.
If you prefer a virtual environment, create it with
`python3 -m venv --system-site-packages .venv` so the vendor packages remain
visible.

## Run device code

The package is not published yet, so put `src/device` on the import path and
select the hardware profile explicitly:

```bash
cd ~/sparky
export PYTHONPATH="$PWD/src/device"
export SPARKY_HARDWARE=pidog
python3 -c "
from sparky_device.hardware import create_ports

with create_ports() as robot:
    print('profile:', robot.profile)
    robot.motion.do_action('sit', speed=60)
    robot.motion.wait_all_done()
    print('distance (cm):', robot.sensors.read_distance_cm())
"
```

`create_ports()` returns a `RobotPorts` bundle with four members — `motion`,
`board`, `camera`, and `sensors`. Using it as a context manager guarantees the
servos are safe-stopped and every port released, even if your code raises.

### Choosing a hardware profile

`SPARKY_HARDWARE` selects the implementation behind the ports.

| Value | Behaviour |
| --- | --- |
| `pidog` | Always use the SunFounder libraries. Fails loudly if they are missing. |
| `simulator` | Always use the recording fakes. No hardware touched. |
| `auto` | Use the vendor libraries when importable, otherwise fall back to the simulators. This is the default. |

On the Pi, set `SPARKY_HARDWARE=pidog` explicitly. `auto` would silently fall
back to the simulators if a vendor import broke, and a robot that quietly does
nothing is harder to debug than one that raises `HardwareUnavailableError`.

### Safety while testing motion

- Put the dog on a stand or hold it so the legs are clear of the ground before
  running gaits for the first time.
- Keep the battery switch within reach.
- `robot.motion.stop()` drops queued motion and holds the current pose. Closing
  the bundle calls it for you.

## Hardware-in-the-loop validation checklist

CI cannot exercise real hardware, so run this checklist on a Pi before closing
a milestone that touches the device runtime. Record the result in the pull
request.

| # | Check | Expected result |
| --- | --- | --- |
| 1 | `python3 -c "import pidog, robot_hat, vilib"` | Imports cleanly |
| 2 | `create_ports()` with `SPARKY_HARDWARE=pidog` | `robot.profile` is `pidog` |
| 3 | `robot.motion.do_action("sit")` then `wait_all_done()` | Dog sits, motion settles |
| 4 | `robot.motion.move_head(yaw=30)` | Head turns, no servo buzzing at the limit |
| 5 | `robot.motion.stop()` mid-gait | Motion halts immediately, pose is held |
| 6 | `robot.sensors.read_distance_cm()` with a hand 20 cm ahead | Value near 20; `None` when the echo fails |
| 7 | `robot.sensors.read_touch()` while touching each pad | `LEFT`, `RIGHT`, then `BOTH` |
| 8 | `robot.sensors.read_imu()` while tilting the dog | Acceleration axes change |
| 9 | `robot.board.play_sound("single_bark_1")` | Audible through the speaker |
| 10 | `robot.board.set_rgb(...)` then `clear_rgb()` | Strip lights, then goes dark |
| 11 | `robot.camera.start()` then `capture()` | Returns a non-empty JPEG `Frame` |
| 12 | Exit the `with` block | Servos safe-stopped, camera stopped, strip off |

A failure in steps 1–2 is an environment problem. A failure in steps 3–12 with
the equivalent simulator test passing points at the adapter layer in
`sparky_device/hardware/pidog_adapters.py`.

## Running without a Pi

Every port has a simulator, so the full test suite runs on any machine:

```bash
python -m unittest discover -s tests
```

To drive the simulators from your own script:

```bash
PYTHONPATH=src/device SPARKY_HARDWARE=simulator python -c "
from sparky_device.hardware import create_ports

with create_ports() as robot:
    robot.motion.do_action('sit')
    print(robot.motion.commands)
"
```

The simulators record what was asked of them and enforce the same servo and
speed limits as the adapters, so a command the simulator rejects would also be
rejected on the robot.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `HardwareUnavailableError: the 'pidog' package is not installed` | Vendor libraries missing, or you are in a virtual environment created without `--system-site-packages` |
| `HardwareUnavailableError: could not initialise the PiDog board` | I2C disabled, Robot HAT unseated, or battery off |
| Servos twitch but the dog does not move | Battery low or powered through USB only |
| `robot.sensors.read_distance_cm()` always returns `None` | Ultrasonic cable unseated; the adapter maps the vendor's negative error sentinel to `None` |
| No audio | `i2samp.sh` was not run, or the Pi was not rebooted afterwards |
| Camera `capture()` raises "vilib has not produced a frame yet" | `start()` was called but the pipeline needs a moment; retry after a short sleep |

## Related documents

- [Architecture](ARCHITECTURE.md) — the ports and adapters seam, and the wider testing strategy
- [Plan](PLAN.md) — milestone sequencing for the device runtime
