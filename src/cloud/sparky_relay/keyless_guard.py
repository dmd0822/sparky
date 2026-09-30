"""Static scanner for key-based Azure AI authentication fallbacks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable


@dataclass(frozen=True)
class KeyFallbackFinding:
    """A forbidden key-based auth fallback found in a scanned file."""

    path: Path
    line_number: int
    pattern_name: str
    line: str


# This module lives under ``src/``, which it scans, so a literal pattern here
# would match itself and make the repo-wide guard fail against its own source.
# Each pattern is therefore split across a concatenation. Do not "simplify"
# these into single literals -- doing so breaks the guard with a confusing
# self-referential failure.
_PATTERN_SPECS: tuple[tuple[str, str], ...] = (
    ("subscription-key-header", "Ocp-Apim-" + "Subscription-Key"),
    ("subscription-key-property", r"\bsubscription" + r"Key\b"),
    ("speech-key-env", r"\bSPEECH_" + r"KEY\b"),
    ("azure-openai-key-env", r"\bAZURE_OPENAI_API_" + r"KEY\b"),
    ("generic-api-credential", r"\bapi[_-]?" + r"key\b"),
    ("list-keys-function", r"\blist" + r"Keys\s*\("),
    ("account-key-connection", "Account" + r"Key\s*="),
    ("connection-string", "Connection" + r"String\s*="),
)

FORBIDDEN_KEY_FALLBACKS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(pattern, re.IGNORECASE)) for name, pattern in _PATTERN_SPECS
)

SCANNED_SUFFIXES = {
    ".bicep",
    ".json",
    ".py",
    ".ps1",
    ".sh",
    ".toml",
    ".yaml",
    ".yml",
}

SCANNED_DIRECTORIES = (
    Path("src"),
    Path("infra"),
    Path(".github") / "workflows",
)

ROOT_CONFIG_FILES = {
    "pyproject.toml",
    "package.json",
    "package-lock.json",
}


class KeyFallbackPolicyError(AssertionError):
    """Raised when key-based auth fallback text appears in code/config/infra."""


def iter_scanned_files(root: Path) -> Iterable[Path]:
    """Yield deterministic code/config/infra files that must stay keyless."""

    for directory in SCANNED_DIRECTORIES:
        base = root / directory
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.suffix.lower() in SCANNED_SUFFIXES:
                yield path

    for name in sorted(ROOT_CONFIG_FILES):
        path = root / name
        if path.is_file():
            yield path


def scan_text(path: Path, text: str) -> list[KeyFallbackFinding]:
    """Scan text and return forbidden key fallback findings."""

    findings: list[KeyFallbackFinding] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for name, pattern in FORBIDDEN_KEY_FALLBACKS:
            if pattern.search(line):
                findings.append(
                    KeyFallbackFinding(
                        path=path,
                        line_number=number,
                        pattern_name=name,
                        line=line.strip(),
                    )
                )
    return findings


def find_key_fallbacks(root: Path) -> list[KeyFallbackFinding]:
    """Walk the repository's executable surfaces and find key fallbacks."""

    findings: list[KeyFallbackFinding] = []
    for path in iter_scanned_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        findings.extend(scan_text(path.relative_to(root), text))
    return findings


def assert_no_key_fallbacks(root: Path) -> None:
    """Raise loudly when key-based Azure AI auth reappears."""

    findings = find_key_fallbacks(root)
    if not findings:
        return

    details = "\n".join(
        f"{finding.path}:{finding.line_number}: {finding.pattern_name}: {finding.line}"
        for finding in findings
    )
    raise KeyFallbackPolicyError(
        "Key-based Azure AI auth fallback detected in code/config/infra:\n" + details
    )


def _main() -> int:
    try:
        assert_no_key_fallbacks(Path.cwd())
    except KeyFallbackPolicyError as exc:
        print(str(exc))
        return 1
    print("No key-based Azure AI auth fallback detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
