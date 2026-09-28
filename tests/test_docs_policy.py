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
README = ROOT / "README.md"
WORKFLOWS = ROOT / ".github" / "workflows"

# Names the workflows read from ``secrets.*``. Documentation that calls any of
# these a repository *variable* is wrong: a variable reference resolves to an
# empty string, and the resulting Azure login fails with an opaque error.
WORKFLOW_SECRET = re.compile(r"\$\{\{[^}]*?\bsecrets\.(AZURE_[A-Z_]+)\b")
WORKFLOW_VAR = re.compile(r"\$\{\{[^}]*?\bvars\.(AZURE_[A-Z_]+)\b")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def flatten(text: str) -> str:
    """Collapse hard wrapping so a phrase split across lines still matches."""
    return re.sub(r"\s+", " ", text)


def markdown_files() -> list[Path]:
    return sorted(path for path in DOCS.rglob("*.md") if path.is_file())


def prose_files() -> list[Path]:
    return markdown_files() + [README]


def workflow_files() -> list[Path]:
    return sorted(WORKFLOWS.glob("*.yml"))


def workflow_names(pattern: re.Pattern[str]) -> set[str]:
    names: set[str] = set()
    for path in workflow_files():
        names.update(pattern.findall(read(path)))
    return names


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


class SecretsVersusVariablesTests(unittest.TestCase):
    """Documentation must describe each Azure input with the context the
    workflows actually read it from."""

    def setUp(self) -> None:
        self.secrets = workflow_names(WORKFLOW_SECRET)
        self.variables = workflow_names(WORKFLOW_VAR)

    def test_workflows_declare_both_kinds_of_input(self) -> None:
        self.assertTrue(self.secrets, "expected at least one secrets.AZURE_* reference")
        self.assertTrue(self.variables, "expected at least one vars.AZURE_* reference")

    def test_no_name_is_both_a_secret_and_a_variable(self) -> None:
        self.assertEqual(set(), self.secrets & self.variables)

    def test_docs_never_call_a_workflow_secret_a_variable(self) -> None:
        for path in prose_files():
            text = flatten(read(path))
            for name in sorted(self.secrets):
                pattern = re.compile(rf"`{name}`[^.]{{0,80}}\bvariable\b")
                with self.subTest(doc=path.relative_to(ROOT).as_posix(), name=name):
                    self.assertIsNone(
                        pattern.search(text),
                        f"`{name}` is read from secrets.* by the workflows; "
                        "documenting it as a repository variable resolves to an "
                        "empty string at runtime",
                    )

    def test_docs_never_call_a_workflow_variable_a_secret(self) -> None:
        for path in prose_files():
            text = flatten(read(path))
            for name in sorted(self.variables):
                pattern = re.compile(rf"`{name}`[^.]{{0,80}}\bsecret\b")
                with self.subTest(doc=path.relative_to(ROOT).as_posix(), name=name):
                    self.assertIsNone(
                        pattern.search(text),
                        f"`{name}` is read from vars.* by the workflows",
                    )


if __name__ == "__main__":
    unittest.main()
