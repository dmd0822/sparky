"""Static checks for the device HIL smoke checklist."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).parents[1]
CHECKLIST = ROOT / "docs" / "running-on-the-pi.md"


def read_checklist() -> str:
    return CHECKLIST.read_text(encoding="utf-8")


def flatten(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def table_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "---" in stripped:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        rows.append(cells)
    return rows


class HilChecklistPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = read_checklist()
        self.flat = flatten(self.text).lower()

    def test_checklist_covers_motion_sensor_and_audio_domains(self) -> None:
        for phrase in (
            "motion",
            "sensor",
            "audio",
            "speaker",
            "microphone array",
            "pass criteria",
            "fail criteria",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.flat)

    def test_checklist_declares_required_fixtures_expected_outputs_and_safety(self) -> None:
        for phrase in (
            "required fixtures and safety setup",
            "dog elevated on a stand",
            "battery switch reachable",
            "expected output",
            "milestone acceptance",
            "python scripts/motion_service_hil.py --ci",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.flat)

    def test_each_smoke_step_has_pass_and_fail_criteria(self) -> None:
        rows = table_rows(self.text)
        smoke_rows = [
            row
            for row in rows
            if row and row[0].isdigit() and 1 <= int(row[0]) <= 18
        ]
        self.assertEqual(18, len(smoke_rows))
        for row in smoke_rows:
            with self.subTest(step=row[0]):
                self.assertGreaterEqual(len(row), 6)
                self.assertTrue(row[-2].lower().startswith("pass"))
                self.assertTrue(row[-1].lower().startswith(("fail", "camera-only")))


if __name__ == "__main__":
    unittest.main()
