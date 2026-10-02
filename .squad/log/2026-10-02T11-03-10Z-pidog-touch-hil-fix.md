# PiDog touch HIL fix — 2026-10-02T11:03:10Z

Device corrected the PiDog motion-service HIL touch-pad expectation. Current SunFounder DualTouch hardware cannot report simultaneous two-pad contact, so step 7 now validates LEFT then RIGHT instead of BOTH. `TouchState.BOTH` remains available for simulator and forward-compatible firmware behavior.

Validation passed in simulation, unittest discovery, and compileall. Dave still needs to re-run the touch-pad step on real PiDog hardware. Camera skip remains environmental and out of scope.
