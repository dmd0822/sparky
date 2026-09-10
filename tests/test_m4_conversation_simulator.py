import unittest

from src import (
    BrokerConfig,
    CloudBroker,
    CloudTurnRequest,
    ConversationSimulator,
    HardwareAdapterBase,
    MotionArbiter,
    PersonaBundle,
    PersonaRegistry,
    PiAdapter,
    SimulatorAdapter,
    StubCloudTransport,
)


class FakeAdapter:
    def __init__(self) -> None:
        self.armed = False
        self.posture = "idle"
        self.head = "neutral"
        self.gestures: list[str] = []

    def arm(self) -> None:
        self.armed = True

    def set_posture(self, posture: str) -> None:
        self.posture = posture

    def set_head(self, heading: str) -> None:
        self.head = heading

    def set_tail(self, tail: float) -> None:
        self.tail = tail

    def play_gesture(self, gesture: str) -> None:
        self.gestures.append(gesture)


class M4ConversationSimulatorTests(unittest.TestCase):
    def test_public_runtime_types_are_exported_at_package_root(self) -> None:
        self.assertIsNotNone(BrokerConfig)
        self.assertIsNotNone(CloudBroker)
        self.assertIsNotNone(CloudTurnRequest)
        self.assertIsNotNone(HardwareAdapterBase)
        self.assertIsNotNone(PiAdapter)
        self.assertIsNotNone(SimulatorAdapter)
        self.assertIsNotNone(StubCloudTransport)

    def test_end_to_end_simulated_turn_uses_generation_scoped_motion(self) -> None:
        adapter = FakeAdapter()
        arbiter = MotionArbiter(adapter, allowlist={"wag", "nod"}, ttl_seconds=1.0)
        arbiter.arm()

        registry = PersonaRegistry(
            default_persona=PersonaBundle(
                persona_id="calm",
                version="1.0",
                prompt="calm assistant",
                voice="neutral",
                behavior={"verbosity": "brief"},
                motion_vocabulary=("wag", "nod"),
                permissions={"motion": True},
            ),
            supported_gestures={"wag", "nod"},
        )
        simulator = ConversationSimulator(
            broker=CloudBroker(config=BrokerConfig(), transport=StubCloudTransport()),
            arbiter=arbiter,
            registry=registry,
        )

        turn = simulator.start_turn(audio_ref="clip.wav", transcript="hello", persona="calm", voice="echo")
        report = simulator.run_turn(turn)

        self.assertEqual(report.status, "completed")
        self.assertEqual(turn.motion_gesture, "wag")
        self.assertEqual(adapter.gestures, ["wag"])
        self.assertEqual(report.reply_text, "[calm] hello from stub")

    def test_barge_in_cancels_broker_and_motion_generation(self) -> None:
        adapter = FakeAdapter()
        arbiter = MotionArbiter(adapter, allowlist={"wag", "nod"}, ttl_seconds=5.0)
        arbiter.arm()

        registry = PersonaRegistry(
            default_persona=PersonaBundle(
                persona_id="playful",
                version="1.0",
                prompt="playful assistant",
                voice="happy",
                behavior={"verbosity": "energetic"},
                motion_vocabulary=("wag", "nod"),
                permissions={"motion": True},
            ),
            supported_gestures={"wag", "nod"},
        )
        simulator = ConversationSimulator(
            broker=CloudBroker(config=BrokerConfig(), transport=StubCloudTransport()),
            arbiter=arbiter,
            registry=registry,
        )

        turn = simulator.start_turn(audio_ref="clip.wav", transcript="hello", persona="playful", voice="echo")
        simulator.arbiter.submit("wag", generation_id=turn.generation_id, ttl_seconds=5.0)
        cancelled = simulator.barge_in(turn.generation_id)

        self.assertTrue(cancelled)
        self.assertTrue(turn.cancelled)
        self.assertEqual(turn.cancelled_motion, ["wag"])
        self.assertTrue(simulator.broker._sessions[turn.generation_id].invalidated)
        self.assertEqual(simulator.arbiter.generation_commands, {})

        report = simulator.run_turn(turn)
        self.assertEqual(report.status, "discarded")
        self.assertTrue(report.discarded)


if __name__ == "__main__":
    unittest.main()
