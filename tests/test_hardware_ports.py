"""Unit tests for the device hardware abstraction layer.

These exercise the ports, the simulators, and the PiDog adapters without any
vendor library installed. The adapter tests drive recording doubles that stand
in for ``pidog.Pidog`` and ``vilib.Vilib``, which is what lets the same
assertions run on a GitHub-hosted runner and on the robot.
"""

from __future__ import annotations

import builtins
import threading
import time
import unittest

from src.device.sparky_device.hardware import (
    DEFAULT_LIMITS,
    HARDWARE_ENV_VAR,
    PIDOG_PROFILE,
    SIMULATOR_PROFILE,
    BoardPort,
    CameraPort,
    Frame,
    HardwareError,
    HardwareUnavailableError,
    ImuReading,
    MotionLimits,
    MotionPort,
    PidogBoardAdapter,
    PidogMotionAdapter,
    PidogSensorAdapter,
    RgbColor,
    RGB_STYLES,
    RobotPorts,
    SensorPort,
    ServoRange,
    SimulatedBoard,
    SimulatedCamera,
    SimulatedMotion,
    SimulatedSensors,
    TouchState,
    VilibCameraAdapter,
    build_pidog_ports,
    build_simulated_ports,
    create_ports,
    resolve_profile,
    solid_frame,
)


class FakeRgbStrip:
    def __init__(self) -> None:
        self.modes: list[dict] = []
        self.close_count = 0

    def set_mode(self, **kwargs) -> None:
        self.modes.append(kwargs)

    def close(self) -> None:
        self.close_count += 1


class FakeDualTouch:
    def __init__(self, value: str = "N") -> None:
        self.value = value

    def read(self) -> str:
        return self.value


class FakeEars:
    def __init__(self, *, detected: bool = False, bearing: float = 0.0) -> None:
        self.detected = detected
        self.bearing = bearing

    def isdetected(self) -> bool:
        return self.detected

    def read(self) -> float:
        return self.bearing


class FakeMusic:
    def __init__(self) -> None:
        self.volumes: list[int] = []

    def music_set_volume(self, volume: int) -> None:
        self.volumes.append(volume)


class FakePidog:
    """Records vendor-level calls so adapter translation can be asserted."""

    def __init__(self, *, distance: float = 42.0, touch: str = "N") -> None:
        self.calls: list[tuple] = []
        self.rgb_strip = FakeRgbStrip()
        self.dual_touch = FakeDualTouch(touch)
        self.ears = FakeEars()
        self.music = FakeMusic()
        self.accData = [0.0, 0.0, 1.0]
        self.gyroData = [0.1, 0.2, 0.3]
        self._distance = distance

    def do_action(self, action, step_count=1, speed=50):
        self.calls.append(("do_action", action, step_count, speed))

    def legs_move(self, angles, speed=50):
        self.calls.append(("legs_move", angles, speed))

    def head_move(self, angles, speed=50):
        self.calls.append(("head_move", angles, speed))

    def tail_move(self, angles, speed=50):
        self.calls.append(("tail_move", angles, speed))

    def wait_all_done(self):
        self.calls.append(("wait_all_done",))

    def body_stop(self):
        self.calls.append(("body_stop",))

    def close(self):
        self.calls.append(("close",))

    def speak(self, name, volume):
        self.calls.append(("speak", name, volume))

    def read_distance(self):
        return self._distance


class ExplodingPort:
    """A port whose every shutdown step fails, for close() aggregation tests."""

    def __init__(self, label: str) -> None:
        self.label = label

    def __getattr__(self, name: str):
        def boom(*_args, **_kwargs):
            raise RuntimeError(f"{self.label}.{name} failed")

        return boom


class ServoRangeTests(unittest.TestCase):
    def test_rejects_inverted_bounds(self) -> None:
        with self.assertRaises(ValueError):
            ServoRange(10.0, -10.0)

    def test_contains_is_inclusive(self) -> None:
        servo_range = ServoRange(-90.0, 90.0)
        self.assertTrue(servo_range.contains(-90.0))
        self.assertTrue(servo_range.contains(90.0))
        self.assertFalse(servo_range.contains(90.1))

    def test_clamp_pins_to_bounds(self) -> None:
        servo_range = ServoRange(0.0, 100.0)
        self.assertEqual(servo_range.clamp(-5.0), 0.0)
        self.assertEqual(servo_range.clamp(500.0), 100.0)
        self.assertEqual(servo_range.clamp(25.0), 25.0)


class RgbColorTests(unittest.TestCase):
    def test_round_trips_through_hex(self) -> None:
        color = RgbColor.from_hex("#1A2B3C")
        self.assertEqual(color.as_tuple(), (0x1A, 0x2B, 0x3C))
        self.assertEqual(color.as_hex(), "#1A2B3C")

    def test_accepts_hex_without_hash(self) -> None:
        self.assertEqual(RgbColor.from_hex("FF0000").as_tuple(), (255, 0, 0))

    def test_rejects_short_hex(self) -> None:
        with self.assertRaises(ValueError):
            RgbColor.from_hex("#FFF")

    def test_rejects_out_of_range_channel(self) -> None:
        with self.assertRaises(ValueError):
            RgbColor(256, 0, 0)

    def test_rejects_bool_channel(self) -> None:
        # bool is an int subclass; a True here is almost certainly a bug.
        with self.assertRaises(ValueError):
            RgbColor(True, 0, 0)


class FrameTests(unittest.TestCase):
    def test_rejects_empty_payload(self) -> None:
        with self.assertRaises(ValueError):
            Frame(data=b"", width=4, height=4)

    def test_rejects_non_positive_dimensions(self) -> None:
        with self.assertRaises(ValueError):
            Frame(data=b"x", width=0, height=4)


class ImuReadingTests(unittest.TestCase):
    def test_requires_three_axes(self) -> None:
        with self.assertRaises(ValueError):
            ImuReading(acceleration=(0.0, 0.0), gyro=(0.0, 0.0, 0.0))


class TouchStateTests(unittest.TestCase):
    def test_maps_every_vendor_code(self) -> None:
        cases = {
            "N": TouchState.NONE,
            "L": TouchState.LEFT,
            "LS": TouchState.LEFT,
            "R": TouchState.RIGHT,
            "RS": TouchState.RIGHT,
            "B": TouchState.BOTH,
            "LR": TouchState.BOTH,
        }
        for code, expected in cases.items():
            with self.subTest(code=code):
                self.assertIs(TouchState.from_vendor(code), expected)

    def test_normalises_case_and_whitespace(self) -> None:
        self.assertIs(TouchState.from_vendor(" ls "), TouchState.LEFT)

    def test_unknown_and_missing_codes_read_as_none(self) -> None:
        self.assertIs(TouchState.from_vendor(None), TouchState.NONE)
        self.assertIs(TouchState.from_vendor(""), TouchState.NONE)
        self.assertIs(TouchState.from_vendor("???"), TouchState.NONE)


class ProtocolConformanceTests(unittest.TestCase):
    """Every implementation must structurally satisfy its port."""

    def test_simulators_satisfy_ports(self) -> None:
        self.assertIsInstance(SimulatedMotion(), MotionPort)
        self.assertIsInstance(SimulatedBoard(), BoardPort)
        self.assertIsInstance(SimulatedCamera(), CameraPort)
        self.assertIsInstance(SimulatedSensors(), SensorPort)

    def test_adapters_satisfy_ports(self) -> None:
        dog = FakePidog()
        self.assertIsInstance(PidogMotionAdapter(dog), MotionPort)
        self.assertIsInstance(PidogBoardAdapter(dog), BoardPort)
        self.assertIsInstance(VilibCameraAdapter(object()), CameraPort)
        self.assertIsInstance(PidogSensorAdapter(dog), SensorPort)


class SimulatedMotionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.motion = SimulatedMotion()

    def test_records_named_action(self) -> None:
        self.motion.do_action("sit", steps=3, speed=80)
        command = self.motion.commands[0]
        self.assertEqual(command.kind, "action")
        self.assertEqual(command.name, "sit")
        self.assertEqual(command.steps, 3)
        self.assertEqual(command.speed, 80)
        self.assertEqual(self.motion.actions(), ["sit"])

    def test_rejects_blank_action(self) -> None:
        with self.assertRaises(HardwareError):
            self.motion.do_action("   ")

    def test_rejects_zero_steps(self) -> None:
        with self.assertRaises(HardwareError):
            self.motion.do_action("sit", steps=0)

    def test_rejects_out_of_range_speed(self) -> None:
        with self.assertRaises(HardwareError):
            self.motion.do_action("sit", speed=150)

    def test_records_leg_angles(self) -> None:
        self.motion.move_legs([0, 10, 20, 30, 40, 50, 60, 70])
        self.assertEqual(
            self.motion.commands[0].angles,
            (0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0),
        )

    def test_rejects_wrong_leg_count(self) -> None:
        with self.assertRaises(HardwareError) as ctx:
            self.motion.move_legs([0, 0, 0])
        self.assertIn("8 angle(s)", str(ctx.exception))

    def test_rejects_unsafe_leg_angle(self) -> None:
        with self.assertRaises(HardwareError):
            self.motion.move_legs([0, 0, 0, 0, 0, 0, 0, 900])

    def test_rejects_unsafe_head_angle(self) -> None:
        with self.assertRaises(HardwareError):
            self.motion.move_head(yaw=200.0)

    def test_tighter_limits_are_enforced(self) -> None:
        motion = SimulatedMotion(limits=MotionLimits(head=ServoRange(-10.0, 10.0)))
        motion.move_head(yaw=9.0)
        with self.assertRaises(HardwareError):
            motion.move_head(yaw=45.0)

    def test_stop_clears_queue_and_counts(self) -> None:
        self.motion.do_action("forward")
        self.motion.stop()
        self.assertEqual(self.motion.commands, [])
        self.assertEqual(self.motion.stop_count, 1)

    def test_commands_rejected_after_close(self) -> None:
        self.motion.close()
        with self.assertRaises(HardwareError):
            self.motion.do_action("sit")

    def test_close_is_idempotent(self) -> None:
        self.motion.close()
        self.motion.close()
        self.assertTrue(self.motion.closed)

    def test_wait_all_done_times_out_when_simulated_motion_never_settles(self) -> None:
        motion = SimulatedMotion(settle_after=None)
        motion.do_action("forward")

        with self.assertRaises(HardwareError) as ctx:
            motion.wait_all_done(timeout=0.001)

        self.assertIn("0.001 seconds", str(ctx.exception))

    def test_wait_all_done_returns_when_simulated_motion_settles(self) -> None:
        motion = SimulatedMotion(settle_after=0.001)
        motion.do_action("forward")

        motion.wait_all_done(timeout=0.1)

        self.assertEqual(motion.wait_count, 1)


class SimulatedBoardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.board = SimulatedBoard()

    def test_records_sound(self) -> None:
        self.board.play_sound("bark", volume=60)
        self.assertEqual(self.board.sounds[0].name, "bark")
        self.assertEqual(self.board.sounds[0].volume, 60)

    def test_rejects_blank_sound_name(self) -> None:
        with self.assertRaises(HardwareError):
            self.board.play_sound("")

    def test_rejects_out_of_range_volume(self) -> None:
        with self.assertRaises(HardwareError):
            self.board.set_volume(101)

    def test_records_rgb_and_clear(self) -> None:
        self.board.set_rgb(style="breath", color=RgbColor(0, 255, 0), brightness=0.5)
        self.assertEqual(self.board.rgb_commands[0].style, "breath")
        self.board.clear_rgb()
        self.assertEqual(self.board.rgb_cleared, 1)

    def test_rejects_out_of_range_brightness(self) -> None:
        with self.assertRaises(HardwareError):
            self.board.set_rgb(style="breath", color=RgbColor(0, 0, 0), brightness=2.0)

    def test_rejects_invalid_rgb_style(self) -> None:
        with self.assertRaisesRegex(HardwareError, "solid.*monochromatic"):
            self.board.set_rgb(style="solid", color=RgbColor(0, 0, 0))

    def test_accepts_every_canonical_rgb_style(self) -> None:
        for style in RGB_STYLES:
            with self.subTest(style=style):
                self.board.set_rgb(style=style, color=RgbColor(0, 255, 0))
                self.assertEqual(self.board.rgb_commands[-1].style, style)

    def test_output_rejected_after_close(self) -> None:
        self.board.close()
        with self.assertRaises(HardwareError):
            self.board.play_sound("bark")


class SimulatedCameraTests(unittest.TestCase):
    def test_capture_before_start_fails(self) -> None:
        with self.assertRaises(HardwareError):
            SimulatedCamera().capture()

    def test_replays_frames_cyclically(self) -> None:
        frames = [solid_frame(sequence=1), solid_frame(sequence=2)]
        camera = SimulatedCamera(frames)
        camera.start()
        self.assertEqual(
            [camera.capture().sequence for _ in range(3)],
            [1, 2, 1],
        )

    def test_start_and_stop_are_idempotent(self) -> None:
        camera = SimulatedCamera()
        camera.start()
        camera.start()
        self.assertEqual(camera.start_count, 1)
        self.assertTrue(camera.is_running())
        camera.stop()
        camera.stop()
        self.assertEqual(camera.stop_count, 1)
        self.assertFalse(camera.is_running())

    def test_rejects_non_positive_dimensions(self) -> None:
        with self.assertRaises(HardwareError):
            SimulatedCamera().start(width=0, height=480)

    def test_requires_at_least_one_frame(self) -> None:
        with self.assertRaises(ValueError):
            SimulatedCamera([])


class SimulatedSensorsTests(unittest.TestCase):
    def test_defaults_are_usable(self) -> None:
        sensors = SimulatedSensors()
        self.assertEqual(sensors.read_distance_cm(), 50.0)
        self.assertIs(sensors.read_touch(), TouchState.NONE)
        self.assertEqual(sensors.read_imu().acceleration, (0.0, 0.0, 1.0))
        self.assertIsNone(sensors.read_sound_direction())

    def test_scripted_values_advance_then_hold(self) -> None:
        sensors = SimulatedSensors(distances=[10.0, 20.0, 30.0])
        self.assertEqual(
            [sensors.read_distance_cm() for _ in range(4)],
            [10.0, 20.0, 30.0, 30.0],
        )

    def test_feed_replaces_the_script(self) -> None:
        sensors = SimulatedSensors()
        sensors.feed_touches([TouchState.LEFT, TouchState.BOTH])
        self.assertIs(sensors.read_touch(), TouchState.LEFT)
        self.assertIs(sensors.read_touch(), TouchState.BOTH)

    def test_records_which_sensors_were_read(self) -> None:
        sensors = SimulatedSensors()
        sensors.read_distance_cm()
        sensors.read_imu()
        self.assertEqual(sensors.reads, ["distance", "imu"])


class RobotPortsTests(unittest.TestCase):
    def test_close_safe_stops_before_releasing(self) -> None:
        ports = build_simulated_ports()
        ports.camera.start()
        ports.close()
        self.assertEqual(ports.motion.stop_count, 1)
        self.assertTrue(ports.motion.closed)
        self.assertTrue(ports.board.closed)
        self.assertFalse(ports.camera.is_running())
        self.assertEqual(ports.board.rgb_cleared, 1)

    def test_close_is_idempotent(self) -> None:
        ports = build_simulated_ports()
        ports.close()
        ports.close()
        self.assertEqual(ports.motion.stop_count, 1)

    def test_close_runs_every_step_even_when_one_fails(self) -> None:
        motion = SimulatedMotion()
        board = SimulatedBoard()
        ports = RobotPorts(
            motion=motion,
            board=board,
            camera=ExplodingPort("camera"),
            sensors=SimulatedSensors(),
            profile="test",
        )
        with self.assertRaises(HardwareError) as ctx:
            ports.close()
        # The camera blew up, but the servos were still stopped and released.
        self.assertIn("camera.stop failed", str(ctx.exception))
        self.assertEqual(motion.stop_count, 1)
        self.assertTrue(motion.closed)
        self.assertTrue(board.closed)

    def test_aggregates_multiple_failures(self) -> None:
        ports = RobotPorts(
            motion=ExplodingPort("motion"),
            board=ExplodingPort("board"),
            camera=ExplodingPort("camera"),
            sensors=SimulatedSensors(),
            profile="test",
        )
        with self.assertRaises(HardwareError) as ctx:
            ports.close()
        message = str(ctx.exception)
        for expected in ("motion.stop", "camera.stop", "board.clear_rgb"):
            self.assertIn(expected, message)

    def test_context_manager_closes(self) -> None:
        with build_simulated_ports() as ports:
            ports.motion.do_action("sit")
        self.assertTrue(ports.closed)

    def test_simulated_bundle_reports_its_profile(self) -> None:
        self.assertEqual(build_simulated_ports().profile, SIMULATOR_PROFILE)


class PidogMotionAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dog = FakePidog()
        self.motion = PidogMotionAdapter(self.dog)

    def test_translates_do_action(self) -> None:
        self.motion.do_action("forward", steps=2, speed=70)
        self.assertEqual(self.dog.calls[0], ("do_action", "forward", 2, 70))

    def test_translates_leg_move_to_vendor_shape(self) -> None:
        angles = [0, 10, 20, 30, 40, 50, 60, 70]
        self.motion.move_legs(angles, speed=30)
        name, payload, speed = self.dog.calls[0]
        self.assertEqual(name, "legs_move")
        # The vendor expects a list of frames, each frame a list of angles.
        self.assertEqual(payload, [[float(a) for a in angles]])
        self.assertEqual(speed, 30)

    def test_translates_head_move(self) -> None:
        self.motion.move_head(yaw=1.0, roll=2.0, pitch=3.0)
        name, payload, _speed = self.dog.calls[0]
        self.assertEqual(name, "head_move")
        self.assertEqual(payload, [[1.0, 2.0, 3.0]])

    def test_translates_tail_move(self) -> None:
        self.motion.move_tail(15.0)
        name, payload, _speed = self.dog.calls[0]
        self.assertEqual(name, "tail_move")
        self.assertEqual(payload, [[15.0]])

    def test_validates_before_touching_the_vendor(self) -> None:
        with self.assertRaises(HardwareError):
            self.motion.move_legs([0, 0, 0, 0, 0, 0, 0, 900])
        self.assertEqual(self.dog.calls, [])

    def test_rejects_unsafe_speed_before_touching_the_vendor(self) -> None:
        with self.assertRaises(HardwareError):
            self.motion.do_action("forward", speed=999)
        self.assertEqual(self.dog.calls, [])

    def test_stop_and_wait_map_to_vendor_calls(self) -> None:
        self.motion.wait_all_done()
        self.motion.stop()
        self.assertEqual(
            self.dog.calls, [("wait_all_done",), ("body_stop",)]
        )

    def test_wait_all_done_timeout_stops_and_raises(self) -> None:
        release = threading.Event()

        def blocking_wait() -> None:
            self.dog.calls.append(("wait_all_done",))
            release.wait()

        self.dog.wait_all_done = blocking_wait

        with self.assertRaises(HardwareError) as ctx:
            self.motion.wait_all_done(timeout=0.01)

        self.assertIn("0.01 seconds", str(ctx.exception))
        self.assertEqual(
            self.dog.calls, [("wait_all_done",), ("body_stop",)]
        )
        release.set()

    def test_wait_all_done_returns_when_motion_settles_in_time(self) -> None:
        def settling_wait() -> None:
            self.dog.calls.append(("wait_all_done",))
            time.sleep(0.001)

        self.dog.wait_all_done = settling_wait

        self.motion.wait_all_done(timeout=0.1)

        self.assertEqual(self.dog.calls, [("wait_all_done",)])

    def test_close_is_idempotent(self) -> None:
        self.motion.close()
        self.motion.close()
        self.assertEqual(self.dog.calls.count(("close",)), 1)


class PidogBoardAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dog = FakePidog()
        self.board = PidogBoardAdapter(self.dog)

    def test_play_sound_maps_to_speak(self) -> None:
        self.board.play_sound("bark", volume=40)
        self.assertEqual(self.dog.calls[0], ("speak", "bark", 40))

    def test_rejects_invalid_volume(self) -> None:
        with self.assertRaises(HardwareError):
            self.board.play_sound("bark", volume=-1)
        self.assertEqual(self.dog.calls, [])

    def test_set_volume_forwards_to_music(self) -> None:
        self.board.set_volume(55)
        self.assertEqual(self.dog.music.volumes, [55])

    def test_set_volume_tolerates_missing_music(self) -> None:
        dog = FakePidog()
        del dog.music
        PidogBoardAdapter(dog).set_volume(20)

    def test_set_rgb_passes_hex_colour(self) -> None:
        self.board.set_rgb(style="boom", color=RgbColor(255, 0, 0), brightness=0.8)
        mode = self.dog.rgb_strip.modes[0]
        self.assertEqual(mode["style"], "boom")
        self.assertEqual(mode["color"], "#FF0000")
        self.assertEqual(mode["brightness"], 0.8)

    def test_set_rgb_rejects_invalid_style_before_vendor_call(self) -> None:
        with self.assertRaisesRegex(HardwareError, "solid.*monochromatic"):
            self.board.set_rgb(style="solid", color=RgbColor(0, 64, 255))
        self.assertEqual(self.dog.rgb_strip.modes, [])

    def test_set_rgb_accepts_every_canonical_style(self) -> None:
        for style in RGB_STYLES:
            with self.subTest(style=style):
                self.board.set_rgb(style=style, color=RgbColor(255, 0, 0))
                self.assertEqual(self.dog.rgb_strip.modes[-1]["style"], style)

    def test_clear_rgb_closes_the_strip(self) -> None:
        self.board.clear_rgb()
        self.assertEqual(self.dog.rgb_strip.close_count, 1)


class PidogSensorAdapterTests(unittest.TestCase):
    def test_reads_distance(self) -> None:
        sensors = PidogSensorAdapter(FakePidog(distance=17.5))
        self.assertEqual(sensors.read_distance_cm(), 17.5)

    def test_negative_distance_sentinel_becomes_none(self) -> None:
        # SunFounder reports -1/-2 when the ultrasonic echo times out.
        for sentinel in (-1.0, -2.0):
            with self.subTest(sentinel=sentinel):
                sensors = PidogSensorAdapter(FakePidog(distance=sentinel))
                self.assertIsNone(sensors.read_distance_cm())

    def test_reads_touch_through_normaliser(self) -> None:
        sensors = PidogSensorAdapter(FakePidog(touch="RS"))
        self.assertIs(sensors.read_touch(), TouchState.RIGHT)

    def test_reads_imu(self) -> None:
        reading = PidogSensorAdapter(FakePidog()).read_imu()
        self.assertEqual(reading.acceleration, (0.0, 0.0, 1.0))
        self.assertEqual(reading.gyro, (0.1, 0.2, 0.3))

    def test_rejects_malformed_imu(self) -> None:
        dog = FakePidog()
        dog.accData = [0.0, 0.0]
        with self.assertRaises(HardwareError):
            PidogSensorAdapter(dog).read_imu()

    def test_sound_direction_is_none_when_nothing_detected(self) -> None:
        self.assertIsNone(PidogSensorAdapter(FakePidog()).read_sound_direction())

    def test_sound_direction_returns_bearing(self) -> None:
        dog = FakePidog()
        dog.ears = FakeEars(detected=True, bearing=135.0)
        self.assertEqual(PidogSensorAdapter(dog).read_sound_direction(), 135.0)


class FakeVilib:
    def __init__(self, img=None, frames=None) -> None:
        self._img = img
        self._frames = list(frames) if frames is not None else None
        self.started = 0
        self.closed = 0

    @property
    def img(self):
        if self._frames:
            value = self._frames.pop(0)
            if value is not None:
                self._img = value
            return value
        return self._img

    @img.setter
    def img(self, value):
        self._img = value

    def camera_start(self, vflip=False, hflip=False):
        self.started += 1

    def camera_close(self):
        self.closed += 1


class VilibCameraAdapterTests(unittest.TestCase):
    def test_start_stop_lifecycle_is_idempotent(self) -> None:
        vilib = FakeVilib()
        camera = VilibCameraAdapter(vilib)
        camera.start()
        camera.start()
        self.assertEqual(vilib.started, 1)
        self.assertTrue(camera.is_running())
        camera.stop()
        camera.stop()
        self.assertEqual(vilib.closed, 1)
        self.assertFalse(camera.is_running())

    def test_capture_before_start_fails(self) -> None:
        with self.assertRaises(HardwareError):
            VilibCameraAdapter(FakeVilib()).capture()

    def test_capture_waits_for_delayed_first_frame(self) -> None:
        from src.device.sparky_device.hardware import pidog_adapters

        frame = object()
        camera = VilibCameraAdapter(
            FakeVilib(frames=[None, None, frame]),
            first_frame_timeout=0.1,
            frame_poll_interval=0.001,
        )
        camera.start()
        original_encode = pidog_adapters._encode_jpeg
        pidog_adapters._encode_jpeg = lambda image: (b"jpeg", 2, 1)
        try:
            captured = camera.capture()
        finally:
            pidog_adapters._encode_jpeg = original_encode

        self.assertEqual(captured.data, b"jpeg")
        self.assertEqual(captured.sequence, 1)

    def test_capture_without_a_frame_fails(self) -> None:
        camera = VilibCameraAdapter(
            FakeVilib(img=None),
            first_frame_timeout=0.001,
            frame_poll_interval=0.001,
        )
        camera.start()
        with self.assertRaises(HardwareError):
            camera.capture()

    def test_rejects_non_positive_dimensions(self) -> None:
        with self.assertRaises(HardwareError):
            VilibCameraAdapter(FakeVilib()).start(width=640, height=-1)


class VendorLoaderTests(unittest.TestCase):
    """The vendor libraries are absent in CI; the errors must be actionable."""

    def test_load_pidog_explains_how_to_recover(self) -> None:
        from src.device.sparky_device.hardware import pidog_adapters

        if pidog_adapters.vendor_libraries_available():
            self.skipTest("vendor libraries are installed on this host")
        with self.assertRaises(HardwareUnavailableError) as ctx:
            pidog_adapters.load_pidog()
        message = str(ctx.exception)
        self.assertIn("pidog", message)
        self.assertIn("SPARKY_HARDWARE=simulator", message)

    def test_load_vilib_explains_how_to_recover(self) -> None:
        from src.device.sparky_device.hardware import pidog_adapters

        original_import = builtins.__import__

        def fail_vilib_import(name, *args, **kwargs):
            if name == "vilib":
                raise ImportError("no vilib")
            return original_import(name, *args, **kwargs)

        builtins.__import__ = fail_vilib_import
        try:
            with self.assertRaises(HardwareUnavailableError) as ctx:
                pidog_adapters.load_vilib()
        finally:
            builtins.__import__ = original_import

        message = str(ctx.exception)
        self.assertIn("vilib", message)
        self.assertIn("not installed", message)
        self.assertIn("SPARKY_HARDWARE=simulator", message)
        self.assertIsInstance(ctx.exception.__cause__, ImportError)

    def test_load_vilib_wraps_camera_initialisation_failure(self) -> None:
        from src.device.sparky_device.hardware import pidog_adapters

        original_import = builtins.__import__

        def fail_vilib_import(name, *args, **kwargs):
            if name == "vilib":
                raise RuntimeError("No camera number 0 found")
            return original_import(name, *args, **kwargs)

        builtins.__import__ = fail_vilib_import
        try:
            with self.assertRaises(HardwareUnavailableError) as ctx:
                pidog_adapters.load_vilib()
        finally:
            builtins.__import__ = original_import

        message = str(ctx.exception)
        self.assertIn("installed but could not initialise", message)
        self.assertIn("camera ribbon", message)
        self.assertIn("rpicam-hello --list-cameras", message)
        self.assertIsInstance(ctx.exception.__cause__, RuntimeError)


class FactoryTests(unittest.TestCase):
    def test_explicit_profile_wins_over_environment(self) -> None:
        env = {HARDWARE_ENV_VAR: PIDOG_PROFILE}
        self.assertEqual(
            resolve_profile(SIMULATOR_PROFILE, env=env), SIMULATOR_PROFILE
        )

    def test_environment_selects_the_profile(self) -> None:
        env = {HARDWARE_ENV_VAR: "SIMULATOR"}
        self.assertEqual(resolve_profile(env=env), SIMULATOR_PROFILE)

    def test_unknown_profile_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            resolve_profile("robotdog")
        self.assertIn("robotdog", str(ctx.exception))

    def test_auto_resolves_to_a_concrete_profile(self) -> None:
        resolved = resolve_profile("auto", env={})
        self.assertIn(resolved, (SIMULATOR_PROFILE, PIDOG_PROFILE))

    def test_auto_falls_back_to_simulator_without_vendor_libraries(self) -> None:
        from src.device.sparky_device.hardware import factory

        if factory.vendor_libraries_available():
            self.skipTest("vendor libraries are installed on this host")
        self.assertEqual(resolve_profile("auto", env={}), SIMULATOR_PROFILE)

    def test_create_ports_builds_a_simulated_bundle(self) -> None:
        ports = create_ports(SIMULATOR_PROFILE)
        self.assertEqual(ports.profile, SIMULATOR_PROFILE)
        self.assertIsInstance(ports.motion, SimulatedMotion)
        ports.close()

    def test_create_ports_honours_custom_limits(self) -> None:
        limits = MotionLimits(tail=ServoRange(-5.0, 5.0))
        ports = create_ports(SIMULATOR_PROFILE, limits=limits)
        with self.assertRaises(HardwareError):
            ports.motion.move_tail(45.0)
        ports.close()

    def test_default_limits_are_the_conservative_envelope(self) -> None:
        self.assertEqual(DEFAULT_LIMITS.speed.maximum, 100.0)
        self.assertEqual(DEFAULT_LIMITS.leg.minimum, -90.0)


class PidogBundleTests(unittest.TestCase):
    def test_build_pidog_ports_accepts_injected_vendors(self) -> None:
        dog = FakePidog()
        ports = build_pidog_ports(dog=dog, vilib=FakeVilib())
        self.assertEqual(ports.profile, PIDOG_PROFILE)
        ports.motion.do_action("sit")
        self.assertEqual(dog.calls[0], ("do_action", "sit", 1, 50))
        ports.close()
        self.assertIn(("body_stop",), dog.calls)
        self.assertIn(("close",), dog.calls)

    def test_build_pidog_ports_keeps_non_camera_ports_usable_without_camera(self) -> None:
        dog = FakePidog()
        original_import = builtins.__import__
        ports: RobotPorts | None = None

        def fail_vilib_import(name, *args, **kwargs):
            if name == "vilib":
                raise RuntimeError("No camera number 0 found")
            return original_import(name, *args, **kwargs)

        builtins.__import__ = fail_vilib_import
        try:
            ports = build_pidog_ports(dog=dog)
            ports.motion.do_action("sit", speed=40)
            ports.board.set_volume(25)
            distance = ports.sensors.read_distance_cm()
            with self.assertRaises(HardwareUnavailableError):
                ports.camera.start()
        finally:
            builtins.__import__ = original_import
            if ports is not None:
                ports.close()

        assert ports is not None
        self.assertEqual(ports.profile, PIDOG_PROFILE)
        self.assertEqual(dog.calls[0], ("do_action", "sit", 1, 40))
        self.assertEqual(dog.music.volumes, [25])
        self.assertEqual(distance, 42.0)


if __name__ == "__main__":
    unittest.main()
