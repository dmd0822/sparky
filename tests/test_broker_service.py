from __future__ import annotations

from src.broker.app import build_health_payload, build_turn_response, is_broker_ready


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


def test_broker_readiness_tracks_managed_identity(monkeypatch) -> None:
    monkeypatch.setenv("USE_MANAGED_IDENTITY", "true")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.delenv("AZURE_SPEECH_REGION", raising=False)
    monkeypatch.setenv("AZURE_CONTENT_SAFETY_ENDPOINT", "https://example.cognitiveservices.azure.com")

    payload = build_health_payload()

    assert payload["managed_identity"] is True
    assert payload["ready"] is True
    assert is_broker_ready() is True


def test_broker_rejects_unready_server_config(monkeypatch) -> None:
    monkeypatch.setenv("USE_MANAGED_IDENTITY", "false")
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_SPEECH_REGION", raising=False)
    monkeypatch.delenv("AZURE_CONTENT_SAFETY_ENDPOINT", raising=False)

    payload = build_turn_response({"generation_id": "abc123", "transcript": "hello", "persona": "calm"})

    assert payload["managed_identity"] is False
    assert is_broker_ready() is False
    assert "fail-closed broker guard" in payload["checks"]
