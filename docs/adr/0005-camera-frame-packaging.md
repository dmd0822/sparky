# ADR 0005: Camera frame packaging above the hardware port

## Status

Accepted

## Context

Sparky needs still frames from the Pi camera for relay vision requests. The
SunFounder `vilib` stack fixes capture at 640x480, and the repository's CI
environment has no robot, no `vilib`, no OpenCV, no NumPy, and no Pillow.

The existing camera port already exposes the honest hardware capability:
`CameraPort.start(width=640, height=480)` accepts only the native `vilib`
resolution and rejects every other size before the vendor library is touched.
Vision upload code still needs a stable JSON-friendly shape with frame bytes,
source dimensions, packaged dimensions, sequence, timestamp, and source ID.

## Decision

Keep resizing and relay packaging **above** `CameraPort`.

`sparky_device.services.CameraService` owns the start/capture/stop lifecycle and
turns port failures into explicit `ok`, `unavailable`, or `malformed` statuses.
It packages captured frames into `PackagedFrame`, whose dictionary form base64
encodes image bytes and records both source and actual packaged dimensions.

When callers request target dimensions, the service lazily attempts an optional
Pillow resize. If Pillow is not installed, or if fixture bytes cannot be decoded
by the optional image stack, packaging preserves the original frame bytes and
records the native dimensions and detail message. CI therefore exercises the
same packaging path without adding a hard image-processing dependency.

Disk-backed fixture replay lives in `sparky_device.hardware.simulators` because
it is a hardware-port implementation detail: tests inject a fixture directory
and receive normal `Frame` objects through the same `CameraPort` protocol.

The frame-packaging shape remains device-local for now. The relay already has a
vision request surface, but no shared Python caller contract has been adopted by
both packages yet. Promoting `PackagedFrame` into `sparky_contracts` should wait
until the relay endpoint consumes this exact shape.

## Alternatives considered

### Ask `CameraPort` for target upload dimensions

Rejected. That would make the simulator accept resolutions `vilib` cannot
honour and would hide real hardware defects until Pi testing.

### Add Pillow, OpenCV, or NumPy as a required dependency

Rejected. CI and off-robot development deliberately run without those packages,
and the hardware adapter already keeps OpenCV lazy behind the `vilib` boundary.

### Put `PackagedFrame` in `sparky_contracts` immediately

Rejected for this issue. The shape is designed to be relay-friendly, but no
relay-side implementation imports it yet. Keeping it device-local avoids
premature shared-contract churn while the endpoint contract is still evolving.

## Consequences

- Hardware ports stay honest about native camera capability.
- Device planners receive status-bearing capture results instead of raw port
  exceptions.
- CI can replay camera fixtures from disk and exercise frame packaging without
  camera hardware or image libraries.
- Target dimensions are best-effort until an approved image dependency is
  installed on the Pi; metadata always reports the dimensions actually sent.
- A future relay integration may promote the package shape into shared
  contracts once both sides consume it.
