# Deployment scripts

Infrastructure deployment and validation helpers live here. Application behavior
belongs under `src/`.

## `validate.ps1`

Run from the repository root in PowerShell:

```powershell
.\infra\scripts\validate.ps1
```

The script exits non-zero if any command fails and builds:

1. every `infra/modules/*.bicep` module,
2. `infra/environments/dev/main.bicep`,
3. `infra/environments/prod/main.bicep`,
4. `infra/environments/dev/main.bicepparam`, and
5. `infra/environments/prod/main.bicepparam`.

Run the static infra policy test separately or through CI:

```powershell
python -m unittest tests.test_infra_policy
```

Deployment commands and OIDC setup are documented in
[`docs/deployment-setup.md`](../../docs/deployment-setup.md).
