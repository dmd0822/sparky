"""Static policy checks for the infra and code delivery GitHub Actions workflows.

These tests encode the CI/CD contract from docs/ARCHITECTURE.md and
docs/deployment-setup.md:

* infra and code pipelines stay separate and are driven by path filters,
* deployment jobs authenticate with GitHub OIDC / workload identity federation
  only, never with long-lived Azure credentials,
* infra deployments always run ``what-if`` before ``az deployment group create``,
* promotion boundaries are expressed with GitHub Environments.
"""

from fnmatch import fnmatch
from pathlib import Path
import re
import unittest

import yaml


ROOT = Path(__file__).parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

INFRA_CI = WORKFLOWS / "infra-ci.yml"
INFRA_CD = WORKFLOWS / "infra-cd.yml"
CODE_CI = WORKFLOWS / "code-ci.yml"
CODE_CD = WORKFLOWS / "code-cd.yml"
WORKFLOW_LINT = WORKFLOWS / "workflow-lint.yml"

DELIVERY_WORKFLOWS = (INFRA_CI, INFRA_CD, CODE_CI, CODE_CD)
INFRA_WORKFLOWS = (INFRA_CI, INFRA_CD)
CODE_WORKFLOWS = (CODE_CI, CODE_CD)
DEPLOYMENT_WORKFLOWS = (INFRA_CD, CODE_CD)

# ``on`` is parsed by PyYAML 1.1 semantics as the boolean True.
ON_KEY = True


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load(path: Path) -> dict:
    return yaml.safe_load(read(path))


def trigger_paths(workflow: dict) -> list[str]:
    paths: list[str] = []
    triggers = workflow.get(ON_KEY) or workflow.get("on") or {}
    for trigger in triggers.values():
        if isinstance(trigger, dict):
            paths.extend(trigger.get("paths", []))
    return paths


def jobs_with_azure_login(workflow: dict) -> dict:
    matching = {}
    for name, job in workflow.get("jobs", {}).items():
        for step in job.get("steps", []):
            if str(step.get("uses", "")).startswith("azure/login@"):
                matching[name] = job
                break
    return matching


def step_texts(workflow: dict) -> list[str]:
    return [
        step["run"]
        for job in workflow.get("jobs", {}).values()
        for step in job.get("steps", [])
        if isinstance(step.get("run"), str)
    ]


class WorkflowSyntaxTests(unittest.TestCase):
    def test_all_workflows_parse_as_yaml(self) -> None:
        for path in sorted(WORKFLOWS.glob("*.yml")):
            with self.subTest(path=path.name):
                self.assertIsInstance(load(path), dict)

    def test_delivery_workflows_exist_with_expected_names(self) -> None:
        expected = {
            INFRA_CI: "Infra CI",
            INFRA_CD: "Infra CD",
            CODE_CI: "Code CI",
            CODE_CD: "Code CD",
        }
        for path, name in expected.items():
            with self.subTest(path=path.name):
                self.assertTrue(path.is_file())
                self.assertEqual(load(path)["name"], name)

    def test_every_job_declares_a_runner(self) -> None:
        for path in DELIVERY_WORKFLOWS:
            for name, job in load(path)["jobs"].items():
                with self.subTest(path=path.name, job=name):
                    self.assertIn("runs-on", job)


class TriggerSeparationTests(unittest.TestCase):
    def test_infra_workflows_are_not_triggered_by_application_code(self) -> None:
        for path in INFRA_WORKFLOWS:
            with self.subTest(path=path.name):
                own = f".github/workflows/{path.name}"
                for pattern in trigger_paths(load(path)):
                    if pattern == own:
                        continue
                    self.assertFalse(pattern.startswith("src/"), pattern)

    def test_code_workflows_are_not_triggered_by_infrastructure(self) -> None:
        for path in CODE_WORKFLOWS:
            with self.subTest(path=path.name):
                for pattern in trigger_paths(load(path)):
                    self.assertFalse(pattern.startswith("infra/"), pattern)
                    for infra in INFRA_WORKFLOWS:
                        self.assertFalse(
                            fnmatch(f".github/workflows/{infra.name}", pattern),
                            f"{path.name} is triggered by {infra.name} via {pattern!r}",
                        )

    def test_infra_workflows_are_not_triggered_by_code_workflows(self) -> None:
        for path in INFRA_WORKFLOWS:
            with self.subTest(path=path.name):
                for pattern in trigger_paths(load(path)):
                    for code in CODE_WORKFLOWS:
                        self.assertFalse(
                            fnmatch(f".github/workflows/{code.name}", pattern),
                            f"{path.name} is triggered by {code.name} via {pattern!r}",
                        )

    def test_delivery_workflows_do_not_watch_every_workflow_file(self) -> None:
        for path in DELIVERY_WORKFLOWS:
            with self.subTest(path=path.name):
                for pattern in trigger_paths(load(path)):
                    self.assertNotEqual(
                        pattern,
                        ".github/workflows/**",
                        f"{path.name} watches every workflow file, which leaks "
                        "changes across the infra/code boundary",
                    )

    def test_every_delivery_workflow_is_watched_by_a_ci_workflow(self) -> None:
        watched = [
            pattern
            for ci in (INFRA_CI, CODE_CI)
            for pattern in trigger_paths(load(ci))
        ]
        for path in DELIVERY_WORKFLOWS:
            target = f".github/workflows/{path.name}"
            with self.subTest(path=path.name):
                self.assertTrue(
                    any(fnmatch(target, pattern) for pattern in watched),
                    f"{path.name} is not covered by any CI path filter, so edits "
                    "to it would run no validation",
                )

    def test_ci_workflows_run_on_pull_requests(self) -> None:
        for path in (INFRA_CI, CODE_CI):
            with self.subTest(path=path.name):
                triggers = load(path)[ON_KEY]
                self.assertIn("pull_request", triggers)

    def test_cd_workflows_are_manually_dispatchable(self) -> None:
        for path in DEPLOYMENT_WORKFLOWS:
            with self.subTest(path=path.name):
                triggers = load(path)[ON_KEY]
                self.assertIn("workflow_dispatch", triggers)

    def test_infra_cd_is_manual_only(self) -> None:
        triggers = load(INFRA_CD)[ON_KEY]
        self.assertEqual(set(triggers), {"workflow_dispatch"})

    def test_workflows_running_python_tests_install_their_dependencies(self) -> None:
        for path in sorted(WORKFLOWS.glob("*.yml")):
            workflow = load(path)
            for job_name, job in workflow.get("jobs", {}).items():
                runs = [
                    step["run"]
                    for step in job.get("steps", [])
                    if isinstance(step.get("run"), str)
                ]
                joined = "\n".join(runs)
                if "unittest" not in joined:
                    continue
                with self.subTest(workflow=path.name, job=job_name):
                    self.assertIn(
                        "tests/requirements.txt",
                        joined,
                        f"{path.name} job '{job_name}' runs unittest but never installs "
                        "tests/requirements.txt, so the tests fail on a clean runner",
                    )


class KeylessAuthTests(unittest.TestCase):
    def test_no_long_lived_azure_credentials_are_referenced(self) -> None:
        forbidden = re.compile(
            r"AZURE_CREDENTIALS|publish-profile|publishProfile|AZURE_CLIENT_SECRET"
            r"|ACR_PASSWORD|REGISTRY_PASSWORD|STORAGE_ACCOUNT_KEY|azureSubscription",
            re.IGNORECASE,
        )
        for path in DELIVERY_WORKFLOWS:
            with self.subTest(path=path.name):
                self.assertIsNone(forbidden.search(read(path)))

    def test_registry_admin_credentials_are_never_used(self) -> None:
        forbidden = re.compile(r"acr credential show|admin-enabled\s+true", re.IGNORECASE)
        for path in DELIVERY_WORKFLOWS:
            with self.subTest(path=path.name):
                self.assertIsNone(forbidden.search(read(path)))

    def test_azure_login_jobs_request_an_oidc_token(self) -> None:
        for path in DEPLOYMENT_WORKFLOWS:
            workflow = load(path)
            for name, job in jobs_with_azure_login(workflow).items():
                with self.subTest(path=path.name, job=name):
                    self.assertEqual(job.get("permissions", {}).get("id-token"), "write")

    def test_azure_login_uses_federated_identifiers_only(self) -> None:
        for path in DEPLOYMENT_WORKFLOWS:
            workflow = load(path)
            for name, job in jobs_with_azure_login(workflow).items():
                for step in job["steps"]:
                    if not str(step.get("uses", "")).startswith("azure/login@"):
                        continue
                    with self.subTest(path=path.name, job=name):
                        login = step.get("with", {})
                        self.assertEqual(
                            set(login), {"client-id", "tenant-id", "subscription-id"}
                        )
                        self.assertNotIn("creds", login)

    def test_subscription_id_is_never_hardcoded(self) -> None:
        guid = re.compile(
            r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
        )
        for path in DELIVERY_WORKFLOWS:
            with self.subTest(path=path.name):
                self.assertEqual(guid.findall(read(path)), [])


class InfraDeploymentTests(unittest.TestCase):
    def test_what_if_runs_before_create(self) -> None:
        runs = step_texts(load(INFRA_CD))
        what_if = next(i for i, run in enumerate(runs) if "deployment group what-if" in run)
        create = next(i for i, run in enumerate(runs) if "deployment group create" in run)
        self.assertLess(what_if, create)

    def test_deployment_commands_supply_template_and_parameters(self) -> None:
        for run in step_texts(load(INFRA_CD)):
            if "deployment group what-if" not in run and "deployment group create" not in run:
                continue
            with self.subTest(run=run.splitlines()[0]):
                self.assertIn("--template-file", run)
                self.assertIn("--parameters", run)
                self.assertIn("--resource-group", run)

    def test_deployments_use_incremental_mode(self) -> None:
        content = read(INFRA_CD)
        self.assertIn("--mode Incremental", content)
        self.assertNotIn("--mode Complete", content)

    def test_deploy_job_is_gated_by_a_github_environment(self) -> None:
        for name, job in load(INFRA_CD)["jobs"].items():
            with self.subTest(job=name):
                self.assertIn("environment", job)

    def test_environment_input_offers_dev_and_prod(self) -> None:
        dispatch = load(INFRA_CD)[ON_KEY]["workflow_dispatch"]
        options = dispatch["inputs"]["environment"]["options"]
        self.assertEqual(options, ["dev", "prod"])


class CodeDeliveryTests(unittest.TestCase):
    def test_azure_touching_jobs_are_gated_by_a_github_environment(self) -> None:
        workflow = load(CODE_CD)
        for name, job in jobs_with_azure_login(workflow).items():
            with self.subTest(job=name):
                self.assertIn("environment", job)

    def test_code_cd_does_not_deploy_infrastructure(self) -> None:
        content = read(CODE_CD)
        self.assertNotIn("az deployment group create", content)
        self.assertNotIn("infra/environments", content)

    def test_registry_auth_goes_through_entra(self) -> None:
        self.assertTrue(
            any("az acr login" in run for run in step_texts(load(CODE_CD))),
            "code-cd.yml must authenticate to ACR with `az acr login`",
        )

    def test_delivery_is_validated_before_publish(self) -> None:
        jobs = load(CODE_CD)["jobs"]
        self.assertIn("validate", jobs)
        self.assertIn("validate", jobs["publish"]["needs"])
        self.assertIn("publish", jobs["deploy"]["needs"])


class WorkflowLintTests(unittest.TestCase):
    """Every workflow file is linted by actionlint on pull requests."""

    def test_lint_workflow_exists(self) -> None:
        self.assertTrue(
            WORKFLOW_LINT.is_file(),
            "workflow-lint.yml must exist so workflow YAML is linted in CI",
        )

    def test_lint_workflow_runs_actionlint(self) -> None:
        self.assertTrue(
            any("actionlint" in run for run in step_texts(load(WORKFLOW_LINT))),
            "workflow-lint.yml must invoke actionlint",
        )

    def test_lint_workflow_watches_every_workflow_file(self) -> None:
        patterns = trigger_paths(load(WORKFLOW_LINT))
        for path in sorted(WORKFLOWS.glob("*.yml")):
            target = f".github/workflows/{path.name}"
            with self.subTest(path=path.name):
                self.assertTrue(
                    any(fnmatch(target, pattern) for pattern in patterns),
                    f"{path.name} is not linted by workflow-lint.yml",
                )

    def test_lint_workflow_runs_on_pull_requests(self) -> None:
        self.assertIn("pull_request", load(WORKFLOW_LINT)[ON_KEY])

    def test_actionlint_download_is_pinned_and_checksummed(self) -> None:
        body = read(WORKFLOW_LINT)
        self.assertRegex(
            body,
            r"ACTIONLINT_VERSION:\s*\"\d+\.\d+\.\d+\"",
            "actionlint must be pinned to an exact version",
        )
        self.assertRegex(
            body,
            r"ACTIONLINT_SHA256:\s*\"[0-9a-f]{64}\"",
            "the actionlint download must be verified against a pinned SHA-256",
        )
        self.assertIn(
            "sha256sum --check",
            body,
            "the actionlint archive checksum must actually be verified",
        )


if __name__ == "__main__":
    unittest.main()
