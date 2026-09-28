"""Static policy checks for Azure infrastructure templates."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).parents[1]
INFRA = ROOT / "infra"
BICEP_FILES = tuple(sorted(INFRA.rglob("*.bicep")))
ENV_ENTRYPOINTS = (
    INFRA / "environments" / "dev" / "main.bicep",
    INFRA / "environments" / "prod" / "main.bicep",
)


class InfraPolicyTests(unittest.TestCase):
    def test_no_key_or_secret_list_functions_are_used(self) -> None:
        forbidden = re.compile(r"\blist(?:Keys|Secrets|ConnectionStrings|AdminCredentials)\s*\(", re.IGNORECASE)
        for path in BICEP_FILES:
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIsNone(forbidden.search(path.read_text()))

    def test_container_app_environment_uses_keyless_azure_monitor_logs(self) -> None:
        path = INFRA / "modules" / "container-app-environment.bicep"
        content = path.read_text()
        self.assertIn("destination: 'azure-monitor'", content)
        self.assertIn("Microsoft.Insights/diagnosticSettings", content)
        self.assertIn("ContainerAppConsoleLogs", content)
        self.assertIn("ContainerAppSystemLogs", content)
        self.assertNotIn("destination: 'log-analytics'", content)
        self.assertNotIn("sharedKey", content)

    def test_outputs_do_not_emit_secret_material(self) -> None:
        suspicious = re.compile(
            r"^\s*output\s+\w*(?:key|secret|connection|string|password|credential)\w*\s+|"
            r"^\s*output\s+\w+\s+\w+\s*=.*(?:key|secret|connectionString|instrumentationKey|password|credential)",
            re.IGNORECASE | re.MULTILINE,
        )
        for path in BICEP_FILES:
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIsNone(suspicious.search(path.read_text()))

    def test_acr_admin_user_is_disabled(self) -> None:
        acr_module = INFRA / "modules" / "container-registry.bicep"
        self.assertIn("adminUserEnabled: false", acr_module.read_text())

    def test_cognitive_services_local_auth_is_disabled(self) -> None:
        for relative in ("modules/ai-services.bicep", "modules/speech.bicep"):
            path = INFRA / relative
            with self.subTest(path=relative):
                self.assertIn("disableLocalAuth: true", path.read_text())

    def test_no_hard_coded_subscription_guids_under_infra(self) -> None:
        guid = re.compile(
            r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
        )
        allowed_role_definition_ids = {
            "a97b65f3-24c7-4388-baec-2e87135dc908",
            "7f951dda-4ed3-4680-a7ca-43fe172d538d",
        }
        for path in tuple(sorted(INFRA.rglob("*"))):
            if not path.is_file():
                continue
            matches = set(guid.findall(path.read_text())) - allowed_role_definition_ids
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertEqual(matches, set())

    def test_environment_entrypoints_are_resource_group_scoped(self) -> None:
        for path in ENV_ENTRYPOINTS:
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIn("targetScope = 'resourceGroup'", path.read_text())


def flatten(path: Path) -> str:
    """Collapse whitespace so patterns survive Bicep's multi-line formatting."""
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


class DeploymentCorrectnessTests(unittest.TestCase):
    """Guards for two failures observed in infra-cd run 36434053500."""

    def test_ai_services_account_declares_a_project_child(self) -> None:
        # If this stops being true the guard below is vacuous, so assert it first.
        self.assertRegex(
            flatten(INFRA / "modules" / "ai-services.bicep"),
            r"resource\s+\w+\s+'Microsoft\.CognitiveServices/accounts/projects@",
        )

    def test_ai_services_account_enables_project_management(self) -> None:
        # Without this the child project fails with:
        # "Project can only created under AIServices Kind account with
        #  allowProjectManagement set to true."
        self.assertRegex(
            flatten(INFRA / "modules" / "ai-services.bicep"),
            r"allowProjectManagement:\s*true",
        )

    def test_relay_module_omits_registries_without_a_login_server(self) -> None:
        self.assertRegex(
            flatten(INFRA / "modules" / "relay-container-app.bicep"),
            r"registries:\s*empty\(acrLoginServer\)\s*\?\s*\[\]",
        )

    def test_relay_registry_is_gated_on_the_image_origin(self) -> None:
        # The relay's system identity does not exist until the relay module runs,
        # so its AcrPull grant necessarily lands afterwards. Declaring the registry
        # on the baseline public-image deployment makes the first revision wait on
        # a credential that cannot yet work; it expires ~16 minutes later with
        # "Failed to provision revision ... Operation expired."
        for path in ENV_ENTRYPOINTS:
            with self.subTest(path=path.relative_to(ROOT)):
                body = flatten(path)
                self.assertNotRegex(body, r"acrLoginServer:\s*acr\.outputs\.loginServer\b")
                self.assertRegex(body, r"acrLoginServer:\s*startsWith\(relayImage,")


if __name__ == "__main__":
    unittest.main()
