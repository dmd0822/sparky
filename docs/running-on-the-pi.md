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

Confirm the PiDog libraries import before going further:

```bash
python3 -c "import pidog, robot_hat; print('PiDog vendor libraries OK')"
```

The camera library is optional for the rest of the bench. Check it separately:

```bash
python3 -c "import vilib; print('Vilib camera library OK')"
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

Before energising the servos, complete the bench setup from
[Safety while testing motion](#safety-while-testing-motion): dog supported with
legs clear, battery switched on, and the battery switch within reach. Keep one
hand free for the operator prompts below; the script pauses before each physical
sensor action.

From the repository root on the Pi, set the shell up for real hardware:

```bash
cd ~/sparky
export PYTHONPATH="$PWD/src/device"
export SPARKY_HARDWARE=pidog
```

Run the required PiDog import check first. If this fails, stop and fix the Pi
environment before continuing; motion, board, and sensors depend on these
packages.

```bash
python3 -c "import pidog, robot_hat; print('required PiDog imports OK')"
```

Then run the optional camera import check. A Vilib failure only costs step 11;
continue with the rest of the checklist if the PiDog check passed. Vilib's
Picamera2 path constructs the camera while importing the module, so a missing
or unseated camera can raise `RuntimeError` from this import instead of a plain
`ImportError`.

```bash
python3 -c "import vilib; print('optional camera import OK')"
```

Then run the bench procedure. It executes checklist steps 2-12 in order and
prints the values you need to compare with the table.

```bash
cat > /tmp/sparky_hil_check.py <<'PY'
import os
import time

from sparky_device.hardware import HardwareError, RgbColor, TouchState, create_ports


def pause(message):
    input(f"\n{message}\nPress Enter when ready...")


def require_touch(label, expected, actual):
    print(f"{label}: {actual.name}")
    if actual is not expected:
        print(f"  Expected {expected.name}; repeat this step before passing it.")


with create_ports() as robot:
    print(f"Step 2 profile: {robot.profile}")
    if os.environ.get("SPARKY_HARDWARE") == "pidog" and robot.profile != "pidog":
        raise SystemExit("SPARKY_HARDWARE=pidog did not create the pidog profile")

    pause("Step 3: confirm the dog is supported with legs clear, then sit.")
    robot.motion.do_action("sit", steps=1, speed=50)
    robot.motion.wait_all_done(timeout=10)
    print("Step 3 complete: sit command settled.")

    pause("Step 4: watch the head turn right about 30 degrees.")
    robot.motion.move_head(yaw=30, speed=50)
    robot.motion.wait_all_done(timeout=5)
    print("Step 4 complete: head command settled.")

    pause("Step 5: the dog will start a slow forward gait; press Enter, then be ready for stop.")
    robot.motion.do_action("forward", steps=5, speed=30)
    time.sleep(0.5)
    robot.motion.stop()
    robot.motion.wait_all_done(timeout=3)
    print("Step 5 complete: stop requested and motion drained.")

    pause("Step 6: place your hand about 20 cm in front of the ultrasonic sensor.")
    print(f"Step 6 distance_cm: {robot.sensors.read_distance_cm()}")

    pause("Step 7a: touch only the left touch pad.")
    require_touch("Step 7a left pad", TouchState.LEFT, robot.sensors.read_touch())
    pause("Step 7b: touch only the right touch pad.")
    require_touch("Step 7b right pad", TouchState.RIGHT, robot.sensors.read_touch())
    pause("Step 7c: touch both pads at the same time.")
    require_touch("Step 7c both pads", TouchState.BOTH, robot.sensors.read_touch())

    pause("Step 8: hold the dog level for the baseline IMU sample.")
    level = robot.sensors.read_imu()
    print(f"Step 8 level acceleration: {level.acceleration}")
    pause("Step 8: tilt the dog gently for the second IMU sample.")
    tilted = robot.sensors.read_imu()
    print(f"Step 8 tilted acceleration: {tilted.acceleration}")

    pause("Step 9: listen for the bark sound.")
    robot.board.play_sound("single_bark_1", volume=80)
    print("Step 9 complete: sound command sent.")

    pause("Step 10: watch the RGB strip turn blue.")
    robot.board.set_rgb(style="solid", color=RgbColor(0, 64, 255), brightness=0.5, speed=50)
    time.sleep(1)
    robot.board.clear_rgb()
    print("Step 10 complete: RGB cleared.")

    pause("Step 11: uncover the camera and capture one frame.")
    try:
        robot.camera.start(width=640, height=480)
        frame = robot.camera.capture()
        print(
            f"Step 11 PASS frame: {frame.width}x{frame.height} {frame.format}, "
            f"{len(frame.data)} bytes, sequence {frame.sequence}"
        )
    except HardwareError as error:
        print(f"Step 11 SKIP camera unavailable: {error}")

print("\nStep 12 complete: exited the context manager; shutdown ran.")
PY

python3 /tmp/sparky_hil_check.py
```

Use the table below as the pass/fail contract while the script runs. Record the
overall result, any failed step numbers, and the observed values in the pull
request.

| # | Check | Expected result |
| --- | --- | --- |
| 1 | `python3 -c "import pidog, robot_hat"` | Required PiDog imports cleanly; optional `vilib` failure only skips step 11 |
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

A failure in required step 1 or step 2 is an environment problem. A failure in
optional camera import or step 11 means only camera validation is blocked. A
failure in steps 3–10 or 12 with the equivalent simulator test passing points at the adapter layer in
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
| Camera `capture()` raises "vilib has not produced a frame yet" | The camera pipeline never produced a usable frame within the adapter's startup wait; check the camera ribbon, enablement, and Vilib/Picamera2 installation |

## Related documents

- [Architecture](ARCHITECTURE.md) — the ports and adapters seam, and the wider testing strategy
- [Plan](PLAN.md) — milestone sequencing for the device runtime
