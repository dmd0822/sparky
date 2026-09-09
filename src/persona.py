#!/usr/bin/env python3
"""Immutable persona bundles and registry logic for Sparky."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .motion_arbiter import DEFAULT_MOTION_ALLOWLIST

DEFAULT_PERSONA_ID = "minimal_safe"
DEFAULT_VOICE = "neutral"


@dataclass(frozen=True)
class PersonaBundle:
    persona_id: str
    version: str
    prompt: str
    voice: str
    behavior: dict[str, Any] = field(default_factory=dict)
    motion_vocabulary: tuple[str, ...] = ()
    permissions: dict[str, Any] = field(default_factory=dict)
    disclosure: str = "I am a robot companion."

    def as_dict(self) -> dict[str, Any]:
        return {
            "persona_id": self.persona_id,
            "version": self.version,
            "prompt": self.prompt,
            "voice": self.voice,
            "behavior": dict(self.behavior),
            "motion_vocabulary": list(self.motion_vocabulary),
            "permissions": dict(self.permissions),
            "disclosure": self.disclosure,
        }


def minimal_safe_persona() -> PersonaBundle:
    return PersonaBundle(
        persona_id=DEFAULT_PERSONA_ID,
        version="1.0",
        prompt="You are the safe, honest fallback persona. Refuse unsafe activity and keep responses brief.",
        voice=DEFAULT_VOICE,
        behavior={"verbosity": "brief", "turn_length": "short", "formality": "neutral"},
        motion_vocabulary=(),
        permissions={"motion": False, "camera": False, "content_safety_tier": "strict"},
        disclosure="I am an AI companion.",
    )


def validate_persona_bundle(
    bundle: PersonaBundle | Mapping[str, Any],
    *,
    supported_gestures: Iterable[str] | None = None,
) -> PersonaBundle:
    """Validate and normalize a persona bundle, failing closed on invalid motion data."""
    if isinstance(bundle, PersonaBundle):
        normalized = bundle
    else:
        if not isinstance(bundle, Mapping):
            raise ValueError("persona bundle must be a mapping or PersonaBundle")
        normalized = PersonaBundle(
            persona_id=str(bundle.get("persona_id", "")).strip(),
            version=str(bundle.get("version", "")).strip(),
            prompt=str(bundle.get("prompt", "")).strip(),
            voice=str(bundle.get("voice", DEFAULT_VOICE)).strip() or DEFAULT_VOICE,
            behavior=dict(bundle.get("behavior", {}) or {}),
            motion_vocabulary=tuple(
                str(item).strip()
                for item in (bundle.get("motion_vocabulary", ()) or ())
                if str(item).strip()
            ),
            permissions=dict(bundle.get("permissions", {}) or {}),
            disclosure=str(bundle.get("disclosure", "I am an AI companion.")),
        )

    if not normalized.persona_id:
        raise ValueError("persona_id is required")
    if not normalized.version:
        raise ValueError("version is required")
    if not normalized.prompt:
        raise ValueError("prompt is required")

    allowed_gestures = frozenset(supported_gestures or DEFAULT_MOTION_ALLOWLIST)
    invalid_gestures = [gesture for gesture in normalized.motion_vocabulary if gesture not in allowed_gestures]
    if invalid_gestures:
        raise ValueError(f"unsupported motion gesture(s): {invalid_gestures}")

    if "motion" in normalized.permissions and normalized.permissions["motion"] is False:
        pass

    return normalized


def load_persona_file(path: str | Path, *, supported_gestures: Iterable[str] | None = None) -> PersonaBundle:
    return PersonaRegistry.load_persona_file(path, supported_gestures=supported_gestures)


def load_persona_directory(directory: str | Path, *, supported_gestures: Iterable[str] | None = None) -> dict[str, PersonaBundle]:
    registry = PersonaRegistry(supported_gestures=supported_gestures)
    return registry.load_directory(directory)


class PersonaRegistry:
    """Runtime registry for immutable persona bundles."""

    def __init__(
        self,
        *,
        supported_gestures: Iterable[str] | None = None,
        default_persona: PersonaBundle | Mapping[str, Any] | None = None,
        persona_directory: str | Path | None = None,
    ) -> None:
        self.supported_gestures = frozenset(supported_gestures or DEFAULT_MOTION_ALLOWLIST)
        self._bundles: dict[str, PersonaBundle] = {}
        self._active_persona_id: str | None = None
        self._pending_persona_id: str | None = None

        if default_persona is None:
            default_persona = minimal_safe_persona()
        self.register(default_persona)
        self._active_persona_id = self._bundles[default_persona.persona_id if isinstance(default_persona, PersonaBundle) else default_persona["persona_id"]].persona_id

        if persona_directory is not None:
            self.load_directory(persona_directory)

    @staticmethod
    def _load_mapping_from_path(path: str | Path) -> Mapping[str, Any]:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"persona file not found: {file_path}")
        if file_path.suffix.lower() in {".json"}:
            with file_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        elif file_path.suffix.lower() in {".yaml", ".yml"}:
            try:
                import yaml  # type: ignore
            except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
                raise RuntimeError("YAML persona files require PyYAML to be installed") from exc
            with file_path.open("r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle)
        else:
            raise ValueError(f"unsupported persona file format: {file_path.suffix or '<unknown>'}")
        if data is None:
            raise ValueError(f"persona file was empty: {file_path}")
        if not isinstance(data, Mapping):
            raise ValueError(f"persona file must contain an object: {file_path}")
        return data

    @classmethod
    def load_persona_file(cls, path: str | Path, *, supported_gestures: Iterable[str] | None = None) -> PersonaBundle:
        data = cls._load_mapping_from_path(path)
        return validate_persona_bundle(data, supported_gestures=supported_gestures or DEFAULT_MOTION_ALLOWLIST)

    @classmethod
    def from_directory(
        cls,
        directory: str | Path,
        *,
        supported_gestures: Iterable[str] | None = None,
        default_persona: PersonaBundle | Mapping[str, Any] | None = None,
    ) -> "PersonaRegistry":
        registry = cls(supported_gestures=supported_gestures, default_persona=default_persona)
        registry.load_directory(directory)
        return registry

    def load_directory(self, directory: str | Path) -> dict[str, PersonaBundle]:
        directory_path = Path(directory)
        if not directory_path.exists():
            return {}
        loaded: dict[str, PersonaBundle] = {}
        for path in sorted(directory_path.iterdir()):
            if path.is_dir():
                continue
            if path.suffix.lower() not in {".json", ".yaml", ".yml"}:
                continue
            try:
                bundle = self.load_persona_file(path, supported_gestures=self.supported_gestures)
            except (FileNotFoundError, OSError, ValueError, TypeError, RuntimeError):
                continue
            self.register(bundle)
            loaded[bundle.persona_id] = bundle
        return loaded

    def register_file(self, path: str | Path, *, replace: bool = False) -> PersonaBundle:
        bundle = self.load_persona_file(path, supported_gestures=self.supported_gestures)
        if bundle.persona_id in self._bundles and not replace:
            return self._bundles[bundle.persona_id]
        self.register(bundle)
        return bundle

    @property
    def active_persona(self) -> PersonaBundle:
        if self._active_persona_id is None:
            raise RuntimeError("no active persona")
        return self._bundles[self._active_persona_id]

    @property
    def pending_persona_id(self) -> str | None:
        return self._pending_persona_id

    def register(self, bundle: PersonaBundle | Mapping[str, Any]) -> PersonaBundle:
        validated = validate_persona_bundle(bundle, supported_gestures=self.supported_gestures)
        self._bundles[validated.persona_id] = validated
        if self._active_persona_id is None:
            self._active_persona_id = validated.persona_id
        return validated

    def switch_persona(self, persona_id: str, *, turn_boundary: bool = True) -> PersonaBundle:
        if not turn_boundary:
            raise RuntimeError("persona switches must occur at a turn boundary")
        if persona_id not in self._bundles:
            raise KeyError(f"unknown persona: {persona_id}")
        self._pending_persona_id = persona_id
        return self._bundles[persona_id]

    def apply_pending_switch(self) -> PersonaBundle:
        if self._pending_persona_id is None:
            return self.active_persona
        self._active_persona_id = self._pending_persona_id
        pending = self._pending_persona_id
        self._pending_persona_id = None
        return self._bundles[pending]

    def can_request_motion(self, gesture: str) -> bool:
        return gesture in set(self.active_persona.motion_vocabulary)

    def requires_turn_boundary(self) -> bool:
        return self._pending_persona_id is not None


__all__ = [
    "DEFAULT_PERSONA_ID",
    "DEFAULT_VOICE",
    "PersonaBundle",
    "PersonaRegistry",
    "load_persona_directory",
    "load_persona_file",
    "minimal_safe_persona",
    "validate_persona_bundle",
]
