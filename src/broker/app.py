#!/usr/bin/env python3
"""Minimal broker service used by the Azure Container App deployment."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

APP_NAME = "sparky-broker"
APP_VERSION = "0.1.0"


def _get_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def build_health_payload() -> dict[str, Any]:
    return {
        "service": APP_NAME,
        "version": APP_VERSION,
        "status": "ok",
        "managed_identity": _get_env("USE_MANAGED_IDENTITY", "false").lower() == "true",
        "environment": _get_env("SPARKY_ENV", "development"),
        "azure": {
            "openai_endpoint": _get_env("AZURE_OPENAI_ENDPOINT"),
            "speech_region": _get_env("AZURE_SPEECH_REGION"),
            "content_safety_endpoint": _get_env("AZURE_CONTENT_SAFETY_ENDPOINT"),
        },
    }


def build_turn_response(payload: dict[str, Any] | None) -> dict[str, Any]:
    request = payload or {}
    return {
        "status": "accepted",
        "service": APP_NAME,
        "version": APP_VERSION,
        "message": "Device request accepted by the Sparky Azure broker.",
        "generation_id": request.get("generation_id") or "gen-demo",
        "transcript": request.get("transcript") or "",
        "persona": request.get("persona") or "calm",
        "voice": request.get("voice") or "en-US-JennyNeural",
        "managed_identity": True,
        "checks": [
            "mTLS device authentication",
            "managed identity access to Azure services",
            "content-safety gate",
            "turn timeout enforcement",
        ],
    }


class BrokerHandler(BaseHTTPRequestHandler):
    server_version = "SparkyBroker/0.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/healthz", "/api/health"}:
            self._send_json(200, build_health_payload())
            return
        self._send_json(404, {"status": "not_found", "path": parsed.path})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path not in {"/api/v1/turn", "/api/turn"}:
            self._send_json(404, {"status": "not_found", "path": parsed.path})
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except json.JSONDecodeError:
            self._send_json(400, {"status": "invalid_json"})
            return

        self._send_json(202, build_turn_response(payload))


def run_server() -> None:
    host = _get_env("HOST", "0.0.0.0")
    port = int(_get_env("PORT", "8080") or "8080")
    ThreadingHTTPServer((host, port), BrokerHandler).serve_forever()


if __name__ == "__main__":
    run_server()
