"""Static policy checks for the documentation under ``docs/``.

GitHub Actions issues this repository's OIDC tokens with immutable subject
claims (``repo:<owner>@<owner-id>/<repo>@<repo-id>:<context>``), which is the
default for every github.com repository created on or after 2026-07-15. Entra
ID rejects any assertion whose subject does not match a federated credential
exactly, so a legacy-format subject in the setup docs produces federated
credentials that can never authenticate.

These tests fail if a legacy-format subject reappears in the documentation.
"""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).parents[1]
DOCS = ROOT / "docs"

OWNER_ID = "176645"
REPO_ID = "1387525209"
IMMUTABLE_PREFIX = f"repo:dmd0822@{OWNER_ID}/sparky@{REPO_ID}:"

# A federated credential subject of the form ``repo:<owner>/<repo>:`` where
# neither segment carries an ``@<id>`` suffix. The immutable form contains
# ``@`` in both segments and therefore does not match.
LEGACY_SUBJECT = re.compile(r"repo:[\w.-]+/[\w.-]+:")

DEPLOYMENT_SETUP = DOCS / "deployment-setup.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def markdown_files() -> list[Path]:
    return sorted(path for path in DOCS.rglob("*.md") if path.is_file())


class LegacyOidcSubjectTests(unittest.TestCase):
    def test_docs_directory_has_markdown_files(self) -> None:
        self.assertTrue(markdown_files(), "expected markdown files under docs/")

    def test_no_legacy_format_oidc_subject_in_docs(self) -> None:
        for path in markdown_files():
            with self.subTest(doc=path.relative_to(ROOT).as_posix()):
                matches = sorted(set(LEGACY_SUBJECT.findall(read(path))))
                self.assertEqual(
                    [],
                    matches,
                    "legacy-format OIDC subject(s) found; this repository requires "
                    f"the immutable form '{IMMUTABLE_PREFIX}...'",
                )

    def test_immutable_subject_regex_accepts_immutable_form(self) -> None:
        for context in ("environment:dev", "environment:prod", "ref:refs/heads/main", "pull_request"):
            with self.subTest(context=context):
                self.assertIsNone(LEGACY_SUBJECT.search(IMMUTABLE_PREFIX + context))

    def test_immutable_subject_regex_rejects_legacy_form(self) -> None:
        for context in ("environment:dev", "environment:prod", "ref:refs/heads/main", "pull_request"):
            with self.subTest(context=context):
                self.assertIsNotNone(LEGACY_SUBJECT.search(f"repo:dmd0822/sparky:{context}"))


class DeploymentSetupSubjectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = read(DEPLOYMENT_SETUP)

    def test_documents_every_immutable_subject(self) -> None:
        for context in ("environment:dev", "environment:prod", "ref:refs/heads/main", "pull_request"):
            with self.subTest(context=context):
                self.assertIn(IMMUTABLE_PREFIX + context, self.text)

    def test_explains_how_to_rederive_the_ids(self) -> None:
        self.assertIn("gh api repos/dmd0822/sparky", self.text)

    def test_troubleshooting_covers_immutable_subject_rejection(self) -> None:
        self.assertIn("AADSTS700213", self.text)


if __name__ == "__main__":
    unittest.main()
