#!/usr/bin/env python3
"""Static import guard for Milestone 1.

The adapter layer is the only place allowed to import the PiDog and robot_hat
libraries. Any other module that reaches for those packages should fail the
validation suite.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

BANNED_MODULES = {"pidog", "robot_hat", "vilib"}
ALLOWED_FILES = {"src/hardware_adapter.py"}


@dataclass(frozen=True)
class ImportViolation:
    path: str
    module: str
    line: int


def find_banned_imports(root: str | Path | None = None) -> list[ImportViolation]:
    root_path = Path(root or Path(__file__).resolve().parents[1])
    violations: list[ImportViolation] = []

    for candidate in sorted(root_path.glob("src/**/*.py")):
        rel_path = candidate.relative_to(root_path).as_posix()
        if rel_path in ALLOWED_FILES:
            continue
        violations.extend(_scan_file(candidate, rel_path))

    return violations


def _scan_file(path: Path, rel_path: str) -> list[ImportViolation]:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return []

    tree = ast.parse(source, filename=str(path))
    violations: list[ImportViolation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_name = alias.name.split(".")[0]
                if module_name in BANNED_MODULES:
                    violations.append(ImportViolation(path=rel_path, module=module_name, line=node.lineno))
        elif isinstance(node, ast.ImportFrom):
            module_name = node.module.split(".")[0] if node.module else ""
            if module_name in BANNED_MODULES:
                violations.append(ImportViolation(path=rel_path, module=module_name, line=node.lineno))
    return violations


def main() -> int:
    violations = find_banned_imports()
    if violations:
        for violation in violations:
            print(f"{violation.path}:{violation.line}: banned import {violation.module}")
        return 1
    print("No banned imports found outside the adapter layer")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
