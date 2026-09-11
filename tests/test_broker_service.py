from __future__ import annotations

from src.broker.app import build_health_payload, build_turn_response


def test_health_payload_reports_status() -> None:
    payload = build_health_payload()

    assert payload["status"] == "ok"
    assert payload["service"] == "sparky-broker"
    assert payload["environment"] in {"development", "test"}


def test_turn_payload_includes_generation_and_checks() -> None:
    payload = build_turn_response({"generation_id": "abc123", "transcript": "hello", "persona": "calm"})

    assert payload["status"] == "accepted"
    assert payload["generation_id"] == "abc123"
    assert payload["persona"] == "calm"
    assert "content-safety gate" in payload["checks"]
