"""Perception contract helpers at the device/cloud boundary.

Camera packaging stays intentionally device-local: it records capture details
that the relay does not consume as a wire contract. These helpers bridge that
device value object into the narrower shared perception request and parse relay
responses back into the shared result DTO so planners can depend on one stable
shape.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Mapping

from .camera import PackagedFrame


def _add_local_shared_contracts_to_path() -> None:
    """Expose the repo-local shared package when callers run outside repo root."""

    for parent in Path(__file__).resolve().parents:
        shared_package = parent / "src" / "shared" / "sparky_contracts" / "__init__.py"
        if shared_package.exists():
            shared_src = str(shared_package.parent.parent)
            if shared_src not in sys.path:
                sys.path.insert(0, shared_src)
            return


try:  # pragma: no cover - installed package path.
    from sparky_contracts import (
        DEFAULT_PERCEPTION_IMAGE_MEDIA_TYPE,
        DEFAULT_PERCEPTION_PROMPT,
        PerceptionRequest,
        PerceptionResult,
    )
except ImportError:  # pragma: no cover - repo-root test path.
    try:
        from src.shared.sparky_contracts import (
            DEFAULT_PERCEPTION_IMAGE_MEDIA_TYPE,
            DEFAULT_PERCEPTION_PROMPT,
            PerceptionRequest,
            PerceptionResult,
        )
    except ImportError:  # pragma: no cover - script path outside repo root.
        _add_local_shared_contracts_to_path()
        from sparky_contracts import (
            DEFAULT_PERCEPTION_IMAGE_MEDIA_TYPE,
            DEFAULT_PERCEPTION_PROMPT,
            PerceptionRequest,
            PerceptionResult,
        )


def request_from_packaged_frame(
    frame: PackagedFrame,
    *,
    prompt: str | None = DEFAULT_PERCEPTION_PROMPT,
    media_type: str = DEFAULT_PERCEPTION_IMAGE_MEDIA_TYPE,
    correlation_id: str | None = None,
) -> PerceptionRequest:
    """Build the shared perception request from a device-packaged frame."""

    frame_payload = frame.as_dict()
    return PerceptionRequest(
        image_base64=str(frame_payload["image_base64"]),
        prompt=prompt,
        media_type=media_type,
        correlation_id=correlation_id,
        source_id=frame.source_id,
        sequence=frame.sequence,
        timestamp=frame.timestamp,
        source_width=frame.source_width,
        source_height=frame.source_height,
    )


def result_from_relay_response(payload: Mapping[str, Any]) -> PerceptionResult:
    """Parse a relay response payload into the shared perception result DTO."""

    return PerceptionResult.from_dict(payload)


__all__ = [
    "request_from_packaged_frame",
    "result_from_relay_response",
]
