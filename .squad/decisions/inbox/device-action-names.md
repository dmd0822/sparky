### 2026-09-29: Motion action names are a shared contract domain
**By:** Device
**What:** PiDog motion action names now live in the hardware contract layer as a fixed allow-list, with one shared validator used by both the PiDog adapter and the simulator. Space-separated caller input is normalised to underscores, but typos, wrong case, non-action helper methods, and eval-shaped strings are rejected before any side effect.
**Why:** This is the fifth instance of the same defect class: the simulator accepted a value domain that the vendor could not honour. The shared-validator pattern keeps simulator and hardware parity, makes failures loud, and closes the vendor val() injection surface by never forwarding unchecked action names.
