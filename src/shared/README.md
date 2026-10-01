# `sparky-shared`

Shared contracts, schemas, and reusable libraries live in
`sparky_contracts/`. This package may be imported by device and cloud code,
but must not contain infrastructure deployment code.

## Perception contracts

`sparky_contracts/` currently owns the shared perception boundary between the
device package and the relay:

- `PerceptionRequest` for the relay-bound image request payload.
- `PerceptionResult`, `PerceptionMetadata`, and `PerceptionFailure` for
  normalized relay perception output.
- Sample prompt constants, including the default prompt and named normal,
  ambiguous, and failure-scene prompts.
- `PERCEPTION_CONTRACT_VERSION` for the shared contract version.

Every perception DTO round-trips through `as_dict()` and `from_dict()` so
fixtures, device helpers, and relay code can use the same JSON-friendly shape.
Representative perception fixtures live in `tests/fixtures/perception/` and
cover normal, ambiguous, and failed scenes.

For ownership, versioning rules, and the boundary with device-local camera
packaging, see
[`docs/adr/0006-shared-perception-contracts.md`](../../docs/adr/0006-shared-perception-contracts.md).
