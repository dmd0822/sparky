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
  libopencv-dev python3-opencv portaudio19-dev alsa-utils

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
git sparse-checkout set src/device docs scripts
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

`create_ports()` returns a `RobotPorts` bundle with five members — `motion`,
`board`, `camera`, `microphone`, and `sensors`. Using it as a context manager guarantees the
servos are safe-stopped and every port released, even if your code raises.

The camera is optional. Code that can use images should ask the port first and
skip camera work when no module is attached:

```python
from sparky_device.hardware import create_ports

with create_ports("pidog") as robot:
    if robot.camera.camera_available():
        robot.camera.start(width=640, height=480)
        frame = robot.camera.capture()
        print(f"captured {frame.width}x{frame.height}")
        robot.camera.stop()
    else:
        print("camera unavailable; continuing without vision")
```

SunFounder Vilib fixes capture at 640x480. The Sparky camera port rejects any
other requested resolution before touching the vendor library so simulator runs
cannot accept a shape that the real PiDog cannot deliver.

Valid motion action names are constrained to the SunFounder PiDog actions the
vendor library can actually honour. Use the canonical underscore form when
possible; space-separated forms such as `wag tail` are accepted and normalised
to `wag_tail` before the adapter touches the vendor object.

`stand`, `sit`, `lie`, `lie_with_hands_out`, `half_sit`, `forward`,
`backward`, `turn_left`, `turn_right`, `trot`, `stretch`, `push_up`,
`doze_off`, `nod_lethargy`, `shake_head`, `tilting_head_left`,
`tilting_head_right`, `tilting_head`, `head_bark`, `wag_tail`,
`head_up_down`

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

CI cannot exercise real servos, sensors, or speakers, so every milestone that
changes `src/device/`, motion/sensor/audio behavior, or the hardware adapters
must include one of these acceptance records before it is closed:

- the simulator harness output from `python scripts/motion_service_hil.py --ci`;
- a real PiDog run of `python scripts/motion_service_hil.py`; and
- for relay-auth milestones, `python scripts/relay_auth_smoke.py --ci` plus a
  Pi run of `python scripts/relay_auth_smoke.py` against the deployed relay; and
- notes for any SKIP/FAIL result, including whether the milestone accepts the
  risk or needs follow-up work.

The same entry point serves both CI and the real-dog bench. `--ci` forces the
`simulator` profile, answers prompts automatically, skips vendor imports, and
exits non-zero on any failed smoke step. The real Pi run uses the `pidog`
profile and pauses before each motion or manual sensor/audio action.

### Required fixtures and safety setup

| Item | Required state | Fail/stop condition |
| --- | --- | --- |
| PiDog posture | Dog elevated on a stand or held so all legs clear the surface before gait steps | Stop immediately if a leg can catch the bench or floor |
| E-stop path | Battery switch reachable and operator has one hand free at every prompt | Stop if the switch is blocked or the operator must leave the bench |
| Power | Robot HAT seated; battery charged and switched on; USB alone is not enough for servos | Stop on brownout, repeated servo resets, or audible low-power chatter |
| Area | Clear 1 m around the dog before forward gait steps | Stop if the robot can collide with a person, cable, or fixture |
| Sensor fixtures | Hand or flat target at about 20 cm for ultrasonic; access to left/right touch pads; dog can be held level and tilted; short clap/sound near microphone array | Mark the affected sensor step FAIL if the fixture is unavailable |
| Audio fixture | Speaker enabled with `i2samp.sh` and rebooted; room quiet enough to hear `single_bark_1` | Mark audio FAIL if the command reports success but no sound is heard |
| Camera fixture | Optional Pi camera attached and visible to `rpicam-hello --list-cameras` when validating vision | Camera-only SKIP is acceptable for non-vision milestones; document it |

From the repository root on the Pi, set the shell up for real hardware:

```bash
cd ~/sparky
export PYTHONPATH="$PWD/src/device"
export SPARKY_HARDWARE=pidog
```

Rehearse the complete checklist off-robot first. This is the CI harness command
and should pass on a laptop or GitHub-hosted runner with no PiDog libraries
installed:

```bash
python scripts/motion_service_hil.py --ci
```

Then run the same checklist against the PiDog from the repository root on the
Pi:

```bash
python scripts/motion_service_hil.py
```

Use `--steps`/`--only` to rerun a subset after a fix, for example `--steps 11`
for camera only, `--steps 6-8,18` for sensors, or `--steps 13-17` for the
motion-service checks. Any normal exit, failure, or Ctrl+C attempts to stop
motion, stop the camera, clear RGB, and close the ports before reporting PASS or
FAIL.

For relay-auth validation on the Pi, use the separate smoke harness after
exporting the Entra public-client and relay values documented in
[keyless-auth-testing-guide.md](keyless-auth-testing-guide.md):

```bash
python scripts/relay_auth_smoke.py
```

For CI or laptop rehearsal, the same harness has a no-network fake mode:

```bash
python scripts/relay_auth_smoke.py --ci
```

That harness performs device-code sign-in, proves the Pi token audience is the
relay app registration, checks correlation-ID echo on `/health`, `/ai/chat`,
`/ai/vision`, and `/speech/synthesize`, and runs the negative authentication
matrix before printing the keyless-auth verification checklist.

### Port, sensor, and audio smoke contract

Record each step's PASS/FAIL/SKIP status, observed output, and any safety notes
in the milestone pull request. A failed required step blocks milestone
acceptance unless the PR explicitly scopes out that hardware area and records a
follow-up risk.

| # | Domain | Fixture / action | Expected output | Pass criteria | Fail criteria |
| --- | --- | --- | --- | --- | --- |
| 1 | Environment | Import `pidog` and `robot_hat`; optionally import `vilib` | Required imports load; camera import may be unavailable | PASS when required imports load; optional `vilib` failure is reported so step 11 can SKIP | FAIL when `pidog` or `robot_hat` cannot import |
| 2 | Environment | `SPARKY_HARDWARE=pidog`; call `create_ports()` | `robot.profile` is `pidog` | PASS when the real profile is selected | FAIL when the profile is missing, `simulator`, or `auto` fallback |
| 3 | Motion | Dog supported; run `robot.motion.do_action("sit")` then `wait_all_done()` | Dog sits and motion settles | PASS when motion settles without limit chatter | FAIL on exception, unsafe movement, or unsettled servo |
| 4 | Motion | Dog supported; run `robot.motion.move_head(yaw=30)` | Head turns right about 30 degrees | PASS when head moves smoothly and stops | FAIL on no movement, wrong direction, or buzzing at limit |
| 5 | Motion | Clear area; start slow `forward`, then call `stop()` | Forward gait starts, then halts and holds pose | PASS when stop pre-empts motion within the script timeout | FAIL when gait continues, robot falls, or stop raises |
| 6 | Sensor | Hand or flat target about 20 cm in front of ultrasonic sensor | Numeric `distance_cm` near the target distance | PASS when a plausible numeric distance is printed | FAIL when the reading is `None`, implausible, or raises |
| 7 | Sensor | Touch left pad, right pad, then both pads at prompts | `LEFT`, `RIGHT`, then `BOTH` | PASS when all three states match the prompted fixture | FAIL on wrong state, no state change, or exception |
| 8 | Sensor | Hold dog level, then gently tilt it | Two IMU acceleration tuples with changed axes | PASS when acceleration changes after tilt | FAIL when values do not change or are malformed |
| 9 | Audio | Speaker enabled; listen for `single_bark_1` | Audible bark from the speaker | PASS when the command returns and the operator hears the bark | FAIL when silent, distorted by setup, or raises |
| 10 | Board | Watch RGB strip during blue monochromatic command | Strip turns blue, then clears | PASS when LEDs light and clear | FAIL when command is silent, wrong color, or not cleared |
| 11 | Camera | Optional camera attached and uncovered; for vision milestones also call `CameraService.capture_frame()` | One 640x480 frame with non-empty bytes and packaged metadata containing source and packaged dimensions, sequence, timestamp, and source ID | PASS when a frame is captured and the packaged result reports status `ok` with honest dimensions; SKIP when no camera is attached for a non-vision milestone | FAIL when a required camera milestone cannot capture or package a frame |
| 12 | Safety | Let the script exit or interrupt it | Cleanup reports ports closed; motion stopped; camera stopped; RGB cleared | PASS when cleanup reports success | FAIL when cleanup reports any close/stop error |
| 18 | Sensor / audio input | Make a short sound near the microphone array | Numeric `sound_direction` in degrees | PASS when a direction is printed | FAIL when no sound is detected or the sensor raises |

Triage rule: failures in steps 1-2 are Pi environment/profile problems. Failures
in steps 3-10, 12, or 18 with `--ci` passing point at
`sparky_device/hardware/pidog_adapters.py` or the physical wiring. A camera-only
SKIP blocks only vision milestones.

### Motion service checks

Steps 13-17 in the same `scripts/motion_service_hil.py` run validate the
planner-facing API above the raw motion port: commands reject conflicts instead
of queueing behind active motion, `stop()` pre-empts immediately and is safe
when repeated, and locomotion from `sit` or `lie` is rejected until an explicit
`stand` request succeeds. The real-hardware run uses the same safety prompts and
cleanup path as the port-level checks above.

| # | Domain | Fixture / action | Expected output | Pass criteria | Fail criteria |
| --- | --- | --- | --- | --- | --- |
| 13 | Motion service | Dog supported; call `MotionService.sit()` then `wait_until_idle()` | Dog sits and service state settles | PASS when state is idle/sitting and no exception escapes | FAIL on unsafe motion, timeout, or exception |
| 14 | Motion service | While posture is sitting, call `MotionService.trot()` | `HardwareError` rejecting sit-to-trot | PASS when no new motion starts and the error is reported | FAIL when trot is accepted from sitting |
| 15 | Motion service | Clear area; call `stand()`, then `forward()` | Dog stands, then starts a slow forward gait | PASS when stand settles and forward is issued | FAIL on unsafe posture, timeout, or exception |
| 16 | Motion service | While forward is in flight, call `turn_left()` | `HardwareError` rejecting a conflicting turn | PASS when turn is rejected and not queued | FAIL when conflicting motion is accepted |
| 17 | Motion service | Call `MotionService.stop()` twice | Motion halts; second stop is a no-op | PASS when both stops complete and state is safe | FAIL when stop raises or motion continues |

### Sensor service checks

After the script's raw sensor steps pass, run this service-level smoke check on
the Pi to verify the planner-facing normalization layer sees the same hardware
without letting sensor faults escape the device loop:

```bash
python - <<'PY'
from sparky_device.hardware import create_ports
from sparky_device.services import SensorService

with create_ports("pidog") as robot:
    service = SensorService(robot.sensors)
    input("Place a hand near the ultrasonic sensor, then press Enter.")
    print(service.read_distance().as_dict())
    for label in ("left pad", "right pad", "both pads"):
        input(f"Touch {label}, then press Enter.")
        print(service.read_touch().as_dict())
    input("Hold the dog level, then press Enter.")
    print(service.read_imu().as_dict())
    input("Make a sound near the microphone array, then press Enter.")
    print(service.read_sound_direction().as_dict())
PY
```

Use the same physical actions from steps 6-8 and 18 while running the snippet.

| Check | Expected result | Pass criteria | Fail criteria |
| --- | --- | --- | --- |
| Ultrasonic timeout or hand distance | `distance.status` is `ok`; `distance_cm` is a number when an echo lands, or `None` with a detail message when this tick has no echo | PASS when the dictionary prints and status semantics are explicit | FAIL if the snippet crashes or status/value is malformed |
| Touch pad state | `touch.status` is `ok`; `touch` is one of `none`, `left`, `right`, or `both` | PASS when prompted touches map to expected states | FAIL on crash, malformed state, or no state change |
| IMU sample | `imu.status` is `ok`; `acceleration` and `gyro` each contain three numeric axes | PASS when numeric axes print | FAIL on crash, malformed axes, or unavailable hardware without explanation |
| Sound direction | `sound_direction.status` is `ok`; `direction_degrees` is numeric when sound is detected, or `None` with a detail message when no sound is detected | PASS when the service reports explicit ok/no-sound semantics | FAIL if the snippet crashes or returns malformed data |
| Missing or unhealthy hardware | A status of `unavailable` or `malformed` appears in the printed dictionary; the snippet does not crash | PASS when failures are represented as statuses | FAIL when a vendor exception escapes the service |

### Microphone capture service check

For speech-input milestones, run the simulator-backed unit tests first so the
committed WAV fixtures prove replay and normalization without a robot:

```bash
python -m unittest tests.test_audio_service
```

Then validate the planner-facing microphone boundary on the Pi. This captures
three normalized chunks, flushes the bounded buffer, and prints the STT-ready
PCM shape. Keep the room quiet except for a short sound near the microphone
array after the snippet starts.

```bash
python - <<'PY'
from sparky_device.hardware import create_ports
from sparky_device.services import AudioService

with create_ports("pidog") as robot:
    service = AudioService(robot.microphone, source_id="sparky-pi-microphone")
    print(service.start().as_dict())
    for _ in range(3):
        print(service.capture_chunk().as_dict())
    print(service.flush().as_dict())
    print(service.stop().as_dict())
PY
```

Pass criteria: `start.status` is `ok`, each capture reports status `ok`, chunks
are normalized to 16000 Hz, mono, 16-bit PCM, and the flush contains bounded
non-empty audio bytes with an accurate `chunk_count` and `duration_seconds`.
Fail criteria: the snippet crashes, busy-device errors escape instead of
returning `malformed`, missing-device errors escape instead of returning
`unavailable`, or flushed audio is empty while the microphone was expected to
capture sound. Record any accepted SKIP/FAIL as a milestone acceptance risk.

### Camera service check

For camera or vision milestones, run step 11 and then validate the
planner-facing packaging boundary. The service still starts the real `vilib`
camera at 640x480; any smaller upload target is applied above the port and may
fall back to original bytes when optional image dependencies are absent.

```bash
python - <<'PY'
from sparky_device.hardware import create_ports
from sparky_device.services import CameraService

with create_ports("pidog") as robot:
    service = CameraService(robot.camera, source_id="sparky-pi-camera")
    print(service.start().as_dict())
    result = service.capture_frame()
    print(result.as_dict())
    print(service.stop().as_dict())
PY
```

Pass criteria: `start.status` is `ok`, `capture.status` is `ok`, the packaged
frame has non-empty base64 image data, `source_width`/`source_height` are
640x480, `packaged_width`/`packaged_height` match the bytes actually submitted,
and `source_id` identifies the Pi camera. Fail criteria: a required camera
milestone returns `unavailable` or `malformed`, the snippet crashes, dimensions
are inconsistent with the frame, or cleanup cannot stop the camera.

For vision relay milestones, use the captured `frame.image` value from the
packaged result as the body for `POST /ai/vision` after the relay-auth smoke
harness has proven sign-in. The response should keep the same correlation ID and
include top-level `caption`, `labels`, `status`, and `metadata`. Treat
`timeout`, `downstream_error`, `invalid_response`, `empty_response`, or
`unsafe_response` statuses as explicit relay/perception failures to record in
the milestone notes rather than as camera packaging failures.

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
| `robot.motion.do_action(...)` raises `HardwareError`, or an older script silently ignored an action | The action name is not one of the supported PiDog actions, has the wrong case, or names a non-action helper such as `set_height`; use one of the documented valid action names |
| `_rgb_strip_thread Exception: Third argument must be a list of at least one, but not more than 32 integers` | Float RGB values reached the LED driver; current adapters pre-scale monochromatic brightness to integer channels before calling the vendor strip |
| Camera `capture()` raises "vilib has not produced a frame yet" | Vilib starts asynchronously and no frame arrived; this usually means no camera is attached or the ribbon cable is loose. Run `rpicam-hello --list-cameras` on the Raspberry Pi to confirm |
| `camera_available()` returns `False` or `rpicam-hello --list-cameras` says `No cameras available!` | No camera module is attached or detected. Continue without vision, or attach/seat the camera module and reboot before rerunning step 11 |
| `robot.camera.start(width=..., height=...)` rejects a non-640x480 resolution | Vilib fixes capture at 640x480; request that native size and resize frames in application code if needed |

## Related documents

- [Architecture](ARCHITECTURE.md) — the ports and adapters seam, and the wider testing strategy
- [Plan](PLAN.md) — milestone sequencing for the device runtime
