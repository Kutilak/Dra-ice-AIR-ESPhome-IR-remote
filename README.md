# Drazice Air53 → ESPHome

An ESPHome-based, IR-blaster replacement for the **DG11R2-01** remote
control (Drazice Air53 split-unit air conditioner, Hisense OEM), reverse
engineered from scratch and exposed to Home Assistant as a full set of
entities plus one native `climate` thermostat card.

No vendor SDK, no recorded-and-replayed IR codes — every function is
built from a fully decoded protocol (checksums included), so any
combination of settings can be sent, not just the exact button presses
that were originally captured. See [`docs/PROTOCOL.md`](docs/PROTOCOL.md)
for the full protocol writeup and [`docs/captures/`](docs/captures/) for
the raw data it was derived from.

## Features

- Native Home Assistant **thermostat card** (`climate` entity): mode,
  target temperature, fan speed, swing — the controls most people want in
  one place.
- Every other remote function as its own entity, independently usable:
  Power, Quiet, Super, Economy, Sleep, iFeel (with room-temperature input),
  On-timer, Off-timer (both with auto-clearing switches once the target
  time passes), Swing toggle, Display backlight toggle, Mode, Fan speed,
  Target temperature, Smart mode temperature offset.
- The `climate` entity is a thin wrapper around the individual entities —
  it calls the exact same code path, nothing is duplicated.
- IR receiver stays active at runtime, so you can keep capturing/verifying
  traffic without reflashing.

## Hardware

- Any ESP8266 (this config targets a Wemos D1 Mini) or ESP32 board.
- An IR LED on the transmit GPIO, normally through a transistor driver for
  range (a bare LED on a GPIO works for close-range testing only).
- An IR receiver module (e.g. TSOP38238) on the receive GPIO — only needed
  for capturing/debugging, not for normal operation.
- Default pins in [`esphome/drazice-air53.yaml`](esphome/drazice-air53.yaml):
  `GPIO4` = transmitter, `GPIO5` = receiver. Change to match your wiring.

## Setup

1. Copy the secrets template and fill in your own values:
   ```bash
   cp esphome/secrets.yaml.example esphome/secrets.yaml
   ```
   Generate your own encryption key rather than reusing any example value:
   ```bash
   python -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"
   ```
2. Adjust the GPIO pins in `drazice-air53.yaml` if your wiring differs.
3. Flash with the ESPHome CLI or dashboard:
   ```bash
   esphome run esphome/drazice-air53.yaml
   ```
4. The device auto-discovers into Home Assistant via the native API. Add
   the `climate.drazice_air_conditioner` entity to a Lovelace thermostat
   card, and/or expose the individual entities as needed.

This config depends on Home Assistant's `time:` platform (`homeassistant`)
to keep the AC's internal clock field valid on every transmission — see
[`docs/PROTOCOL.md`](docs/PROTOCOL.md) for why that matters (a stale/wrong
clock value causes the unit to display a phantom timer warning). No
additional Home Assistant configuration is required for this — the API
connection already provides it.

## Project layout

```
.
├── README.md                      ← this file
├── docs/
│   ├── PROTOCOL.md                ← full protocol reference (frame layout, checksums, byte map)
│   └── captures/                  ← raw IR captures + decode.py, so every claim in PROTOCOL.md is reproducible
└── esphome/
    ├── drazice-air53.yaml         ← main ESPHome config
    ├── secrets.yaml.example       ← copy to secrets.yaml and fill in
    └── components/
        └── drazice_climate/       ← local external component for the `climate` entity
            ├── __init__.py
            ├── climate.py
            └── drazice_climate.h
```

## Known limitations

- The `C1=0x01` (power) family code was derived from a single uncontrolled
  capture rather than an isolated test like every other function. Power
  itself is implemented and works reliably — this is a documentation gap,
  not a functional one.
- Setting a timer to a time already in the past today (i.e. effectively
  "tomorrow") hasn't been verified against the real unit; the ESPHome
  side assumes "nearest future occurrence" and handles the midnight
  rollover in its own logic, but the AC's own behavior in that exact case
  is unconfirmed.

See [`docs/PROTOCOL.md`](docs/PROTOCOL.md#open-questions) for details.
