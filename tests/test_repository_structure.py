"""Validate the repository scaffold and package metadata."""

from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).parents[1]


class RepositoryStructureTests(unittest.TestCase):
    def test_adr_layout_exists(self) -> None:
        expected_directories = (
            "src/device",
            "src/device/tests",
            "src/cloud",
            "src/cloud/tests",
            "src/shared",
            "src/shared/tests",
            "infra/modules",
            "infra/environments/dev",
            "infra/environments/prod",
            "infra/scripts",
            "docs/adr",
            "docs/diagrams",
        )
        for directory in expected_directories:
            with self.subTest(directory=directory):
                self.assertTrue((ROOT / directory).is_dir())

    def test_python_package_metadata_is_valid(self) -> None:
        expected_packages = {
            "src/device/pyproject.toml": ("sparky-device", "sparky_device"),
            "src/cloud/pyproject.toml": ("sparky-cloud", "sparky_relay"),
            "src/shared/pyproject.toml": ("sparky-shared", "sparky_contracts"),
        }
        for manifest, package in expected_packages.items():
            with self.subTest(manifest=manifest):
                metadata = tomllib.loads((ROOT / manifest).read_text())
                self.assertEqual(metadata["project"]["name"], package[0])
                self.assertTrue((ROOT / manifest).parent.joinpath(package[1]).is_dir())


if __name__ == "__main__":
    unittest.main()
