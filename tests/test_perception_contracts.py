"""Tests for shared perception DTOs, fixtures, and package consumers."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from src.cloud.sparky_relay.relay_api import REQUEST_SCHEMAS, RESPONSE_SCHEMAS
from src.device.sparky_device.services import (
    PackagedFrame,
    request_from_packaged_frame,
    result_from_relay_response,
)
from src.shared.sparky_contracts import (
    DEFAULT_PERCEPTION_IMAGE_MEDIA_TYPE,
    DEFAULT_PERCEPTION_PROMPT,
    PERCEPTION_PROMPT_AMBIGUOUS_SCENE,
    PERCEPTION_PROMPT_FAILURE_SCENE,
    PERCEPTION_PROMPT_NORMAL_SCENE,
    PERCEPTION_STATUS_OK,
    PERCEPTION_STATUS_TIMEOUT,
    SAMPLE_PERCEPTION_PROMPTS,
    PerceptionFailure,
    PerceptionMetadata,
    PerceptionRequest,
    PerceptionResult,
)


ROOT = Path(__file__).parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "perception"


class PerceptionContractRoundTripTests(unittest.TestCase):
    def test_request_round_trips_with_source_metadata(self) -> None:
        request = PerceptionRequest(
            image_base64="ZmFrZS1qcGc=",
            prompt=None,
            media_type="image/jpeg",
            correlation_id="cid-request",
            source_id="front-camera",
            sequence=7,
            timestamp=123.5,
            source_width=640,
            source_height=480,
        )

        self.assertEqual(PerceptionRequest.from_dict(request.as_dict()), request)
        self.assertEqual(request.as_dict()["image"], "ZmFrZS1qcGc=")
        self.assertEqual(request.as_dict()["prompt"], DEFAULT_PERCEPTION_PROMPT)
        self.assertEqual(request.as_dict()["media_type"], DEFAULT_PERCEPTION_IMAGE_MEDIA_TYPE)

    def test_failure_round_trips(self) -> None:
        failure = PerceptionFailure(
            code="downstream_status",
            message="Foundry vision returned a non-success status.",
            status_code=503,
        )

        self.assertEqual(PerceptionFailure.from_dict(failure.as_dict()), failure)

    def test_metadata_round_trips(self) -> None:
        metadata = PerceptionMetadata(
            latency_ms=125,
            token_usage={"prompt": 3, "completion": 4, "total": 7},
            model="gpt-4.1-mini",
            deployment="sparky-vision",
            failure=PerceptionFailure("timeout", "request timed out"),
        )

        self.assertEqual(PerceptionMetadata.from_dict(metadata.as_dict()), metadata)

    def test_result_round_trips_ok_and_failure_variants(self) -> None:
        ok = PerceptionResult.ok(
            caption="A robot dog on a workbench.",
            labels=["robot dog", "workbench"],
            latency_ms=98,
            token_usage={"prompt": 12, "completion": 8, "total": 20},
            model="gpt-4.1-mini",
            deployment="sparky-vision",
        )
        failed = PerceptionResult.failure(
            status=PERCEPTION_STATUS_TIMEOUT,
            code="timeout",
            message="Foundry vision request timed out.",
            latency_ms=20_000,
            deployment="sparky-vision",
        )

        self.assertEqual(PerceptionResult.from_dict(ok.as_dict()), ok)
        self.assertEqual(PerceptionResult.from_dict(failed.as_dict()), failed)
        self.assertIsInstance(PerceptionResult.from_dict(ok.as_dict()).labels, tuple)

    def test_device_helpers_reference_shared_contracts(self) -> None:
        frame = PackagedFrame(
            image_bytes=b"abc",
            source_width=640,
            source_height=480,
            packaged_width=640,
            packaged_height=480,
            format="jpeg",
            sequence=9,
            timestamp=456.25,
            source_id="front-camera",
        )

        request = request_from_packaged_frame(frame, correlation_id="cid-device")
        result = result_from_relay_response(
            PerceptionResult.ok(
                caption="A robot dog.",
                labels=("robot dog",),
                latency_ms=1,
                token_usage={},
                model="",
                deployment="sparky-vision",
            ).as_dict()
        )

        self.assertIsInstance(request, PerceptionRequest)
        self.assertEqual(request.as_dict()["image"], "YWJj")
        self.assertEqual(request.source_id, "front-camera")
        self.assertIsInstance(result, PerceptionResult)
        self.assertEqual(result.labels, ("robot dog",))


class PerceptionFixtureTests(unittest.TestCase):
    def test_sample_prompt_constants_cover_named_fixtures(self) -> None:
        self.assertEqual(SAMPLE_PERCEPTION_PROMPTS["normal_scene"], PERCEPTION_PROMPT_NORMAL_SCENE)
        self.assertEqual(
            SAMPLE_PERCEPTION_PROMPTS["ambiguous_scene"],
            PERCEPTION_PROMPT_AMBIGUOUS_SCENE,
        )
        self.assertEqual(SAMPLE_PERCEPTION_PROMPTS["failed_scene"], PERCEPTION_PROMPT_FAILURE_SCENE)

    def test_fixtures_parse_round_trip_and_satisfy_relay_schemas(self) -> None:
        scenes: set[str] = set()
        for fixture_path in sorted(FIXTURE_DIR.glob("*.json")):
            with self.subTest(fixture=fixture_path.name):
                payload = json.loads(fixture_path.read_text(encoding="utf-8"))
                scenes.add(payload["scene"])

                self.assertIn(payload["sample_prompt"], SAMPLE_PERCEPTION_PROMPTS)
                request_payload = payload["request"]
                response_payload = payload["response"]

                request = PerceptionRequest.from_dict(request_payload)
                response = PerceptionResult.from_dict(response_payload)

                self.assertEqual(request.as_dict(), request_payload)
                self.assertEqual(response.as_dict(), response_payload)
                self.assert_required_keys(request_payload, REQUEST_SCHEMAS["vision"]["required"])
                self.assert_required_keys(response_payload, RESPONSE_SCHEMAS["vision"]["required"])

                if payload["scene"] == "failed":
                    self.assertNotEqual(response.status, PERCEPTION_STATUS_OK)
                    self.assertIsNotNone(response.metadata.failure)
                if payload["scene"] == "ambiguous":
                    self.assertLessEqual(len(response.labels), 2)
                    self.assertIn("uncertain", response.caption.lower())

        self.assertEqual(scenes, {"normal", "ambiguous", "failed"})

    def assert_required_keys(self, payload: dict[str, object], required: list[str]) -> None:
        for key in required:
            self.assertIn(key, payload)


if __name__ == "__main__":
    unittest.main()
