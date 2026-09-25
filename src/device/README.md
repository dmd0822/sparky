# `sparky-device`

The Raspberry Pi application package lives in `sparky_device/`. Hardware-facing
code belongs here and must use ports/adapters so unit tests do not require
PiDog hardware. Keep device tests in `tests/` beside this package.
