"""Device persona manifest registry."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from src.shared.sparky_contracts.personas import PersonaManifest


PERSONA_MANIFEST_GLOB = "*.json"


def default_manifest_dir() -> Path:
    """Return the package directory containing built-in persona manifests."""

    return Path(__file__).parent


def load_persona_manifest(path: Path | str) -> PersonaManifest:
    """Load and validate a persona manifest from JSON."""

    manifest_path = Path(path)
    payload = json.loads(
        manifest_path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_json_keys,
    )
    if not isinstance(payload, Mapping):
        raise ValueError("Persona manifest JSON must be an object.")
    return PersonaManifest.from_dict(payload)


def load_persona_registry(directory: Path | str | None = None) -> dict[str, PersonaManifest]:
    """Load all persona manifests from a directory, keyed by persona id."""

    root = Path(directory) if directory is not None else default_manifest_dir()
    registry: dict[str, PersonaManifest] = {}
    for path in sorted(root.glob(PERSONA_MANIFEST_GLOB)):
        manifest = load_persona_manifest(path)
        if manifest.persona_id in registry:
            raise ValueError(f"Duplicate persona id: {manifest.persona_id}")
        registry[manifest.persona_id] = manifest
    return registry


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError("Persona manifest JSON contains duplicate keys.")
        payload[key] = value
    return payload


__all__ = [
    "PERSONA_MANIFEST_GLOB",
    "default_manifest_dir",
    "load_persona_manifest",
    "load_persona_registry",
]
