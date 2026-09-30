# ADR 0006: Shared perception contracts

## Status

Accepted

## Context

Sparky's device runtime captures camera frames on the Pi, while the relay owns
the authenticated cloud call to vision models. Both packages need a stable
request and response shape so behavior work can depend on perception results
without redefining local payloads at each hop.

ADR 0005 kept `PackagedFrame` device-local and explicitly deferred moving that
shape into `sparky_contracts` until the relay consumed the exact same object.
The relay still does not consume `PackagedFrame` directly. Its `POST /ai/vision`
wire request requires an `image` field, and the relay response schema requires
`caption`, `labels`, and `correlation_id` while the normalized perception DTO
also carries `status` and `metadata`. Shared perception contracts therefore
need to describe the relay boundary without turning the device's camera
packaging object into a cloud contract.

The contract also needs executable examples. Representative payload fixtures
for a normal scene, an ambiguous scene, and a failed scene live under
`tests/fixtures/perception/` so contract readers can see the expected JSON and
tests can keep those examples honest.

## Decision

Create a shared perception contract surface in `src/shared/sparky_contracts`.
The shared package owns:

- `PERCEPTION_CONTRACT_VERSION`, starting at `"1.0"`;
- the relay-bound perception input DTO, `PerceptionRequest`;
- response DTOs for relay-returned perception output, including
  `PerceptionResult`, `PerceptionMetadata`, and `PerceptionFailure`;
- perception status constants: `ok`, `config_error`, `downstream_error`,
  `empty_response`, `invalid_response`, `timeout`, `transport_error`, and
  `unsafe_response`;
- shared prompt constants: `DEFAULT_PERCEPTION_PROMPT`,
  `PERCEPTION_PROMPT_NORMAL_SCENE`, `PERCEPTION_PROMPT_AMBIGUOUS_SCENE`,
  `PERCEPTION_PROMPT_FAILURE_SCENE`, and the `SAMPLE_PERCEPTION_PROMPTS`
  lookup.

`PerceptionRequest` is the shared relay-bound DTO. It serializes image bytes
under the wire key `image`, matching the relay endpoint, while preserving source
metadata such as source ID, sequence, timestamp, and dimensions when the device
has them. Device code constructs a `PerceptionRequest` from a device-local
`PackagedFrame`; it does not promote `PackagedFrame` itself into the shared
package.

This extends and honors ADR 0005. `PackagedFrame` remains owned by the device
camera service because it records capture and packaging details that the relay
does not require, including byte length, packaging dimensions, resize outcome,
and device packaging detail. Promoting it now would reverse ADR 0005 without the
condition that ADR set: relay adoption of the exact `PackagedFrame` shape.

Device and cloud packages should import the shared contracts instead of
redeclaring compatible local dataclasses or ad hoc dictionaries. Device code
owns camera capture, packaging, and conversion from `PackagedFrame` into
`PerceptionRequest` through `request_from_packaged_frame()`, then parses relay
responses through `result_from_relay_response()`. Cloud relay code owns
transport, authentication, model calls, and conversion of downstream model
output into `PerceptionResult`. Changes to the shared contract surface are
owned jointly by the device and cloud maintainers, with docs updated in the same
pull request.

Versioning follows semantic contract rules around
`PERCEPTION_CONTRACT_VERSION`.

- Backward-compatible changes keep the same major version. Examples include
  adding optional fields, accepting additional metadata keys, adding new status
  constants, adding sample prompts, or adding fixtures that exercise existing
  shapes. They require round-trip tests and representative fixture coverage.
- Breaking changes require a new major version and a migration plan. Examples
  include removing or renaming fields, changing field types, changing required
  wire keys such as `image`, `caption`, `labels`, or `correlation_id`, changing
  default semantics that existing callers depend on, or making an optional
  field required. They require coordinated device and cloud updates before the
  old version is retired.

The fixtures under `tests/fixtures/perception/` are the executable examples of
version `1.0`. A normal scene should parse as a successful response, an
ambiguous scene should show low-certainty or clarifying perception output that
still uses the same DTOs, and a failed scene should parse into the failure
metadata and status fields rather than an out-of-band error shape.

Full CI cannot prove real camera capture, relay deployment configuration, and
model response parsing together. Human-in-the-loop validation for this contract
therefore follows these steps on real hardware:

1. Start the Pi with the current device package and relay configuration.
2. Capture one camera frame through the device camera service.
3. Convert the resulting `PackagedFrame` into a shared `PerceptionRequest`.
4. Send the serialized request through the relay's `POST /ai/vision` path.
5. Confirm the relay response includes `caption`, `labels`, and
   `correlation_id`.
6. Parse the response with `PerceptionResult.from_dict()`.
7. Record whether the parsed status is successful, ambiguous but valid, or a
   structured failure using the shared status constants.

## Alternatives considered

### Promote `PackagedFrame` into `sparky_contracts`

Rejected. ADR 0005 allowed this only after the relay consumed the exact
`PackagedFrame` shape. The relay still requires a narrower `image` request, so
promoting `PackagedFrame` would expose device packaging internals as a cloud
contract before both sides need them.

### Keep request and response shapes local to each package

Rejected. Local copies would let device and cloud code drift, weaken fixture
coverage, and make versioning an informal convention instead of an explicit
shared contract.

### Version only the relay endpoint

Rejected. Endpoint versioning is useful later, but issue 12 needs Python DTOs,
status constants, prompts, and fixtures that both packages can import during
normal development and CI.

## Consequences

- Device and cloud code have one shared perception vocabulary.
- `PackagedFrame` stays free to evolve with camera packaging needs without
  forcing relay contract changes.
- Relay request serialization stays aligned with the existing `image` wire key.
- Contract fixtures become the reviewable examples for normal, ambiguous, and
  failed perception outcomes.
- Breaking contract changes now need explicit versioning and coordinated
  migration instead of silent dictionary drift.
