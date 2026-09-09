import unittest

from src import MotionArbiter, PersonaBundle, PersonaRegistry, validate_persona_bundle


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

    def play_gesture(self, gesture: str) -> None:
        self.gestures.append(gesture)


class M3MotionSafetyPersonaTests(unittest.TestCase):
    def test_arbiter_drops_expired_commands(self) -> None:
        adapter = FakeAdapter()
        arbiter = MotionArbiter(adapter, allowlist={"bark", "wag"}, ttl_seconds=0.05)
        arbiter.arm()

        result = arbiter.submit("bark", generation_id="g1", now=0.0)
        self.assertTrue(result["accepted"])

        arbiter.service(now=0.2)

        self.assertEqual(adapter.gestures, [])
        self.assertEqual(arbiter.rejected[-1]["reason"], "ttl_expired")

    def test_arbiter_rejects_freeform_joint_commands(self) -> None:
        adapter = FakeAdapter()
        arbiter = MotionArbiter(adapter, allowlist={"bark", "wag"})
        arbiter.arm()

        result = arbiter.submit("left_knee=90", generation_id="g2", ttl_seconds=1.0)

        self.assertFalse(result["accepted"])
        self.assertEqual(result["reason"], "not_allowed")
        self.assertEqual(adapter.gestures, [])

    def test_arbiter_has_single_authority_over_motion(self) -> None:
        adapter = FakeAdapter()
        arbiter = MotionArbiter(adapter, allowlist={"bark"}, ttl_seconds=5.0)
        arbiter.arm()

        arbiter.submit("bark", generation_id="g3", ttl_seconds=5.0)
        arbiter.service(now=0.1)

        self.assertEqual(adapter.gestures, ["bark"])
        self.assertEqual(arbiter.executed, ["bark"])

    def test_persona_registry_validates_and_switches_at_turn_boundaries(self) -> None:
        calm = PersonaBundle(
            persona_id="calm",
            version="1.0",
            prompt="calm assistant",
            voice="neutral",
            behavior={"verbosity": "short"},
            motion_vocabulary=("bark", "wag"),
            permissions={"motion": True},
        )
        playful = PersonaBundle(
            persona_id="playful",
            version="2.0",
            prompt="playful assistant",
            voice="happy",
            behavior={"verbosity": "energetic"},
            motion_vocabulary=("wag", "think"),
            permissions={"motion": True},
        )

        registry = PersonaRegistry(default_persona=calm, supported_gestures={"bark", "wag", "think"})
        registry.register(playful)

        self.assertEqual(registry.active_persona.persona_id, "calm")
        self.assertTrue(registry.can_request_motion("wag"))
        self.assertFalse(registry.can_request_motion("think"))

        with self.assertRaises(RuntimeError):
            registry.switch_persona("playful", turn_boundary=False)

        registry.switch_persona("playful", turn_boundary=True)
        self.assertEqual(registry.pending_persona_id, "playful")
        self.assertEqual(registry.apply_pending_switch().persona_id, "playful")
        self.assertEqual(registry.active_persona.persona_id, "playful")

        invalid = {"persona_id": "bad", "version": "1.0", "prompt": "oops", "motion_vocabulary": ["not_real"]}
        with self.assertRaises(ValueError):
            validate_persona_bundle(invalid, supported_gestures={"bark"})


if __name__ == "__main__":
    unittest.main()
