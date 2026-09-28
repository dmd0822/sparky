# Camera optional degradation — 2026-09-28T16:14:06-04:00

- **Asked:** Make a missing PiDog camera degrade gracefully instead of aborting the hardware-in-the-loop bench.
- **Shipped:** Device updated `pidog_adapters.py` so vendor import/runtime failures become `HardwareUnavailableError`; added regression coverage; updated `docs/running-on-the-pi.md` so step 1 has a REQUIRED PiDog import check and an OPTIONAL camera check.
- **Verified:** Commit 3d80d1e passed the full suite (175 passed). Coordinator reproduced a `RuntimeError: No camera number 0 found` vilib import failure locally and confirmed the bench reports SKIP for camera while continuing to the next step.
- **Still unverified on hardware:** Dave still needs to rerun the updated bench on the actual PiDog without a camera attached.
- **Scribe health:** decisions.md measured 10818 bytes, so no decision archival ran; decision inbox processed 0 files; no agent histories exceeded 15360 bytes, so 0 histories were summarized.
