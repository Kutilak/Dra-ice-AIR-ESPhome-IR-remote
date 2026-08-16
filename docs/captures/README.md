# Raw IR captures

Raw ESPHome `remote_receiver` logs (`dump: pronto`) used to reverse-engineer
the protocol documented in [`../PROTOCOL.md`](../PROTOCOL.md). Kept here so
the findings in `PROTOCOL.md` are independently reproducible — each claim
there can be traced back to a specific capture and re-decoded with
[`decode.py`](decode.py).

```
py decode.py <capture_file.txt> ["label1,label2,..."]
```

Labels are only needed for files that don't already have `Beo4: n_sym=...`
lines with a button name before each frame — see the docstring in
`decode.py`.

## Capture index

| File | What it isolates |
|---|---|
| `capture_01_baseline.txt` | Large uncontrolled capture (33 commands) — first pass, established the basic byte layout and A2/A3 fields. |
| `capture_02_mode.txt` | MODE, 12× (3 cycles: cool/dry/fan only/heat). |
| `capture_03_fan_speed.txt` | Fan speed in heating mode, 2 cycles. |
| `capture_04_quiet.txt` | Quiet on/off in cooling/24°C, 3 cycles. |
| `capture_05_super.txt` | Super on/off in heating/26°C, 3 cycles. |
| `capture_06_super_dry_fan_only.txt` | Super on/off in dry and fan-only modes, 2+2 cycles. |
| `capture_07_quiet_fan_only.txt` | Quiet on/off in fan-only, 2 cycles (dry mode sends nothing). |
| `capture_08_smart.txt` | Smart mode activation + 4 relative temperature-offset adjustments. |
| `capture_09_smart_range.txt` | Full Smart offset range, −7 to +7 (15 points). |
| `capture_10_swing_smart.txt` | Swing pressed 4× in Smart mode (3 clean + 1 noisy frame). |
| `capture_11_economy.txt` | Economy on/off, 2 cycles, heating/19°C. |
| `capture_12_ifeel.txt` | iFeel on/off, 2 cycles, heating/19°C (reported room temp 26°C). |
| `capture_13_on_timer.txt` | On-timer set to 6:00, cooling/23°C/fan-min, single confirm press, real time 6:49. |
| `capture_14_on_timer_615.txt` | On-timer set to 6:15 then cancelled, 2 cycles, real time 7:00 — isolates the minute byte. |
| `capture_15_off_timer_2012.txt` | Off-timer set to 20:12 then cancelled, 2 cycles — isolates the off-timer active flag. |
| `capture_16_swing_power.txt` | Swing pressed 4× in a row + power off/on/off/on, 2+2 cycles. |
| `capture_17_dimmer.txt` | Display backlight (dimmer) button pressed 4× in a row. |
| `capture_18_sleep.txt` | Sleep on/off, 2 cycles. |
| `capture_19_original_remote_timer_off.txt` | Original remote, dedicated "cancel timer" button. |
| `capture_20_original_remote_power.txt` | Original remote, power on/off. |
| `capture_21_original_remote_power_2.txt` | Original remote, a second power command (independent confirmation). |
| `capture_22_original_remote_timer_off_corrupted.txt` | **Unusable / corrupted** — a `remote_receiver` overrun during capture produced garbage data. Kept only as a documented example of what noise looks like; do not use it as protocol evidence. |

## Data quality note

Capture 10 had its 4th frame corrupted by noise: the Pronto header reported
one extra pair (`00AD` instead of the usual `00AC`) and the data contained
nonsensically short intervals (`0026 0005`). Naturally, the checksum on such
a frame doesn't match — before concluding a new formula from a mismatching
checksum, check the pair count in the Pronto header and make sure all
durations look reasonable (tens, not single units).
