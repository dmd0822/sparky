import unittest

from src.cloud_path import BrokerConfig, CloudBroker, CloudTurnRequest, StubCloudTransport


class CloudPathTests(unittest.TestCase):
    def test_turn_reports_total_cost_and_latency(self) -> None:
        broker = CloudBroker(config=BrokerConfig(), transport=StubCloudTransport())
        session = broker.start_turn(
            CloudTurnRequest(audio_ref="clip.wav", transcript="hello", persona="spark", voice="echo")
        )

        report = broker.run_turn(session)

        self.assertEqual(report.status, "completed")
        self.assertEqual(len(report.stages), 4)
        self.assertEqual(report.reply_text, "[spark] hello")
        self.assertEqual(report.transcript, "hello from stub")
        self.assertEqual(report.total_latency_ms, 120 + 10 + 220 + 180)
        self.assertAlmostEqual(report.total_cost_usd, 0.0098, places=6)

    def test_invalidated_generation_is_discarded(self) -> None:
        broker = CloudBroker(config=BrokerConfig(), transport=StubCloudTransport())
        session = broker.start_turn(
            CloudTurnRequest(audio_ref="clip.wav", transcript="hello", persona="spark", voice="echo")
        )
        broker.invalidate_generation(session.generation_id)

        report = broker.run_turn(session)

        self.assertTrue(report.discarded)
        self.assertEqual(report.status, "discarded")
        self.assertEqual(report.stages, [])

    def test_circuit_breaker_opens_after_failures(self) -> None:
        broker = CloudBroker(config=BrokerConfig(circuit_breaker_failure_threshold=2), transport=StubCloudTransport(fail_stt=True))
        first = broker.start_turn(CloudTurnRequest(audio_ref="clip.wav", transcript="hello", persona="spark", voice="echo"))
        second = broker.start_turn(CloudTurnRequest(audio_ref="clip.wav", transcript="world", persona="spark", voice="echo"))
        third = broker.start_turn(CloudTurnRequest(audio_ref="clip.wav", transcript="again", persona="spark", voice="echo"))

        first_report = broker.run_turn(first)
        second_report = broker.run_turn(second)
        third_report = broker.run_turn(third)

        self.assertEqual(first_report.status, "failed")
        self.assertEqual(second_report.status, "failed")
        self.assertEqual(third_report.status, "circuit_open")
        self.assertTrue(third_report.circuit_open)

    def test_safety_blocked_turn_is_reported(self) -> None:
        broker = CloudBroker(config=BrokerConfig(), transport=StubCloudTransport(block_safety=True))
        session = broker.start_turn(
            CloudTurnRequest(audio_ref="clip.wav", transcript="bomb", persona="spark", voice="echo")
        )

        report = broker.run_turn(session)

        self.assertEqual(report.status, "blocked")
        self.assertTrue(report.stages[0].ok)
        self.assertTrue(report.stages[1].blocked)


if __name__ == "__main__":
    unittest.main()
