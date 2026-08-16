# Drazice Air53 IR protocol reference

Reverse-engineered IR protocol of the **DG11R2-01** remote control (Drazice
Air53 split-unit air conditioner, Hisense OEM). This document describes the
protocol itself; see [`../README.md`](../README.md) for how it's used in the
ESPHome configuration.

Reverse-engineered by capturing with ESPHome's `remote_receiver` component
(`dump: pronto`) and isolating one button at a time from a fixed starting
state (2+ repeat cycles per button, byte-diffed between frames). Raw
captures and the decoding tool are in [`captures/`](captures/), so every
claim below can be independently re-verified.

> The `Beo4:` / `n_sym=344` label sometimes seen in capture logs is just an
> artifact of using ESPHome's `remote.beo4` component to log button labels
> during capture — **it has nothing to do with the Bang & Olufsen Beo4
> protocol.** This is a custom pulse-distance protocol at 38 kHz.

## 1. Physical layer (timing)

| Element | Value |
|---|---|
| Carrier frequency | 38 kHz |
| Header mark / space | 9000 µs / 4500 µs |
| Bit mark (always the same) | 560 µs |
| Bit 0 / 1 → space | 560 µs / 1690 µs |
| Gap between blocks | mark 560 µs + space 8100 µs |
| End of frame | mark 560 µs + space 10100 µs |
| Repeats | none — every press is a single frame |

Bits within each byte are sent **LSB first**.

## 2. Frame structure

```
HEADER → Block A (48b=6B) → GAP → Block B (64b=8B) → GAP → Block C (56b=7B) → END
```

21 data bytes per command. Throughout this document (and the YAML config)
they're addressed as a flat `state[0..20]` array: `A` = `[0..5]`,
`B` = `[6..13]`, `C` = `[14..20]`.

## 3. Byte map

| Index | Name | Role |
|---|---|---|
| 0-1 | A0, A1 | Fixed device ID, never changes across any capture. |
| 2 | A2 | Fan speed (low 2 bits) + Sleep flag + Smart offset magnitude/sign (high nibble). |
| 3 | A3 | Mode (low nibble) + target temperature (high nibble). |
| 4 | A4 | Mostly `0x00`; `0x80` seen once (Smart activation) — see [Open questions](#open-questions). |
| 5 | A5 | Super mode flag (`0x90`/`0x00`). |
| 6 | B0 | `0x80 + current hour` (0-23) + Display backlight (dimmer) toggle bit `0x20`. |
| 7 | B1 | `(Off-timer active ? 0x80 : 0) \| current minute` (0-59) — see [important note](#b1-is-not-just-a-clock-byte) below. |
| 8 | B2 | Swing toggle bit `0x40` \| Off-timer target hour (0-23). |
| 9 | B3 | On-timer active flag `0x80`/`0x00` **or** Off-timer target minute (0-59), depending on which timer family is being addressed — see [Timers](#timers). |
| 10 | B4 | On-timer target hour (0-23). |
| 11 | B5 | On-timer target minute (0-59) \| iFeel flag `0x80`. |
| 12 | B6 | iFeel room temperature (raw byte, not BCD). |
| 13 | B7 | Checksum of block B — see [section 5](#5-block-b-checksum). |
| 14 | C0 | Quiet flag `0x04`, Economy flag `0x20`. |
| 15 | C1 | "Button family" code — see [section 6](#6-c1-button-family-codes). |
| 16 | C2 | Smart offset remainder (values beyond what fits in A2's nibble). |
| 17 | C3 | Fan half-step flag `0x40` ("nudge one step up", combines with Max/Min). |
| 18 | C4 | Power flag `0x10`. |
| 19 | C5 | Always `0x00` in every capture so far. |
| 20 | C6 | Checksum of block C — see [section 4](#4-block-c-checksum). |

## 4. Block C checksum

```
C6 = C3 + C4 + C5 + f(C0) + f(C1) + f(C2)     (mod 256)
where f(x) = 2×(x & 0x07) − x
```

`C3`, `C4`, `C5` are summed directly (whole byte). `C0`, `C1`, `C2` are
summed "inverted": their low 3 bits are added doubled, but their high 5 bits
are *subtracted* instead of added. For `C0/C1/C2 < 0x08` (high bits zero),
`f(x) = x`, so the formula collapses to a plain sum — which is why an
earlier, incomplete model only seemed to hold for `C1 ≤ 0x07`.

This single formula replaces what looked like a per-`C1` correction table
plus a separate Smart-mode correction — both were just this same `f(x)`
applied to a different byte. It also explains why a naive lookup table for
`C1=0x0C` (economy) was inconsistent: the correction actually depends on
`C0` too (bit `0x20` = economy flag), not just `C1`.

## 5. Block B checksum

```
B7 = A2 ⊕ A3 ⊕ A4 ⊕ A5 ⊕ B0 ⊕ B1 ⊕ B2 ⊕ B3 ⊕ B4 ⊕ B5 ⊕ B6
```

A plain XOR of every byte from `A2` through `B6` — i.e. everything except
`A0`/`A1` (the fixed device ID) and block C (which arrives after B in the
frame and has no effect on B7).

## 6. C1 "button family" codes

`C1` is not an independent status bit — it identifies **which group of
buttons** was pressed. Its value is the same for every option within a
group (e.g. `C1=0x06` for all 4 conventional modes, even though `A3`
changes). When implementing a function, set both the function's own
bit/field *and* its matching `C1` code.

**Important:** `C1` does **not** gate which bytes the AC actually reads —
the unit evidently processes the **entire** frame on every receive,
regardless of `C1` (confirmed via the swing bit in B2, which the AC acts on
even in frames with a completely unrelated `C1`). Any bit with pulse/edge
("send once") semantics must therefore always be cleared right after
sending — if left set, it will fire again on the next, completely
unrelated command. This affects Swing, Display Backlight and — as
described below — the Off-timer active flag.

| C1 | Function |
|---|---|
| `0x00` | Display backlight (dimmer) |
| `0x01` | Power (derived from a single uncontrolled session, not isolated separately — see [Open questions](#open-questions)) |
| `0x02` | Target temperature (absolute and Smart offset) |
| `0x03` | Sleep |
| `0x04` | Super |
| `0x05` | On-timer |
| `0x06` | Mode (cool/dry/fan only/heat) |
| `0x07` | Swing |
| `0x0B` | Quiet |
| `0x0C` | Economy |
| `0x0D` | iFeel |
| `0x11` | Fan speed |
| `0x17` | Smart (activation press only) |
| `0x1D` | Off-timer |

## 7. Confirmed functions

| Function | Location | Notes |
|---|---|---|
| **Target temperature** | high nibble of `A3` | `((temp − 16) & 0xF) << 4`. Verified 16-30 °C. |
| **Power** | bit `0x10` in `C4` | 1 = on / 0 = off. |
| **Mode** | low nibble of `A3` | `0`=Heat, `1`=Smart, `2`=Cool, `3`=Dry, `4`=Fan Only. |
| **Fan speed** | low 2 bits of `A2` + bit `0x40` in `C3` | `0`=Auto, `1`=Max, `2`=Medium, `3`=Min; the `C3` bit means "nudge one step up" (combines only with Max→Medium-High and Min→Medium-Low). 6 speeds from 3 bits, independent of mode. |
| **Quiet** | bit `0x04` in `C0` | 1 = on. **Side effect:** turning on forces fan speed to Min; turning off **restores the exact previous speed** (not hard-coded Auto — same pattern as Super). Applies in every mode where quiet actually does anything (cooling and fan-only alike); in Dry mode the physical remote sends **nothing at all** when quiet is pressed (confirmed twice independently — no IR signal is transmitted). |
| **Super** | `A5` = `0x90`/`0x00` | Turning on forces the temperature to the mode's limit (heat→30°C, cool and dry/fan-only-switched-to-cool→16°C) and fan speed mode-dependently (heat→Auto, cool→Max); turning off restores the exact previous mode+temperature+fan speed. In Dry/Fan Only, activation switches the mode to Cool. |
| **Smart — activation** | low nibble of `A3` = `1`; `C1=0x17` only for the activation press itself | The activation press has its own `C1` code; subsequent adjustments in this mode (temperature offset) use `C1=0x02`. |
| **Smart — temperature offset (−7..+7)** | high nibble of `A2` + `C2` | `magnitude = |offset|`, `sign = offset<0`. `A2 high nibble = min(magnitude,2) + (sign?4:0)` (saturates at 2/6). `C2 = 4×max(0,magnitude−2)` (carries the remainder). `A3` unchanged. Verified across the full range (15/15 points). |
| **Swing** | bit `0x40` in `B2` | **Stateless toggle, not persistent state**: the remote doesn't track "swing is on" — every press sends the same "toggle swing" pulse and the AC handles the actual louver position itself. Confirmed byte-identical across repeated presses; no distinct "off" variant exists at the byte level. **Must always be cleared right after sending** (see the C1 note above) — otherwise it re-fires on every subsequent, unrelated command. |
| **Economy** | bit `0x20` in `C0` | 1 = on / 0 = off. Same pattern as Quiet — `C1=0x0C` constant for both on and off, only the `C0` bit (and therefore the checksum) changes. No side effects on other bytes observed. |
| **iFeel** | bit `0x80` in `B5` + raw temperature in `B6` | 1 = on / 0 = off (`B5`). `B6` = room temperature as measured by the remote, a raw byte (not BCD), only set while iFeel is on (otherwise `0x00`). `C1=0x0D` constant for both on and off; `C0` unchanged. |
| **On-timer** | active flag `B3`=`0x80`/`0x00`, target hour `B4` (raw 0–23), target minute `B5` (raw 0–59) | Absolute encoding, not a relative countdown (the same target hour captured at different real times produced identical bytes). Cancelling the timer zeroes `B3`, `B4` and `B5` together. `C1=0x05` constant for both setting and cancelling. Independently confirmed by the original remote's dedicated "cancel timer" button. |
| **Off-timer** | active flag `0x80` in **`B1`** (shared byte with the current-minute clock field!), target hour `B2` (raw 0–23), target minute `B3` (raw 0–59) | See the [important note below](#b1-is-not-just-a-clock-byte) — the active flag is **not** in `B2`/`B3` as might be assumed by analogy with the on-timer; it's a separate bit stashed in the high bit of `B1`. `C1=0x1D` constant for setting and cancelling. |
| **Display backlight (dimmer)** | bit `0x20` in `B0`, `C1=0x00` | **Stateless toggle, same pattern as Swing**: repeated presses produce a byte-identical frame. The unit tracks the actual backlight state itself. **Must be cleared right after sending**, same reasoning as Swing. |
| **Sleep** | bit `0x08` in `A2`, `C1=0x03` | 1 = on / 0 = off. No side effects on other bytes (fan speed in the low 2 bits of `A2` unchanged, mode/temperature unchanged). |
| **Current time (clock)** | `B0` = `0x80 + current hour` (0-23, high bit always 1); `B1` low 7 bits = current minute (0-59) | The remote transmits its own live clock in **every** frame, regardless of `C1`. Confirmed hour-exact across 20+ captures spanning real hours 2 through 7 and 21; minute matches within −1 to −2 (ordinary clock drift between the remote and the logging PC). |

### B1 is not just a clock byte

`B1`'s high bit (`0x80`) is **not** part of the minute value and is **not**
just "always set" — it is the **off-timer active flag**, packed into the
same byte as the current-minute clock field. Confirmed directly:
`capture_15_off_timer_2012.txt` shows `B1` flipping between `0x89` (armed)
and `0x09` (cancelled) across two on/off cycles, with the low 7 bits
(minute) unchanged between them. Independently confirmed to be
off-timer-specific (not a general "some timer is running" bit):
`capture_13`/`capture_14` (on-timer active) always show this bit clear in
`B1`, and `capture_19` (dedicated "cancel timer" button) shows it clear too.

This single bit is the entire root cause of the "phantom timer" behavior
this project spent several iterations chasing: a naive implementation that
freezes `B1` at a fixed value (or gets its clock-sync math wrong) will send
this flag "stuck on" in every single frame, which the AC displays as an
active off-timer, indistinguishable from the user having actually set one.
See the ESPHome config's `transmit_ac_state` script for how this is handled
correctly (a persistent flag OR'd back into `B1` after the minute is
recomputed, on every transmission).

## 8. Data quality note

One capture (`captures/capture_10_swing_smart.txt`) had its 4th frame
corrupted by receiver noise: the Pronto header reported one extra pair than
usual, and the data contained nonsensically short intervals. A checksum
mismatch alone isn't proof of a wrong formula — always check the Pronto
header's pair count and that all durations look plausible (tens, not single
digits) before concluding anything from a failing checksum.

## Open questions

- **`C1=0x01` (power)** was derived from a single uncontrolled capture
  session rather than an isolated, repeated test like every other function.
  Power itself works reliably in practice, so this is a documentation gap,
  not a functional one.
- **`A4 = 0x80`** appeared in exactly one frame (Smart activation) — a
  single data point, meaning unconfirmed.
- **Timer set to a time already in the past today** (i.e. effectively "for
  tomorrow") is untested against the real unit. The ESPHome config assumes
  "nearest future occurrence" and handles the midnight rollover in its own
  auto-cancel logic, but whether the physical AC's own timer arithmetic
  agrees with that assumption — or whether the remote's display even
  allows setting such a time — has not been observed directly.
