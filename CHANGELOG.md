# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased] - 2026-08-16

### Changed

- On-timer and Off-timer now directly toggle AC power once the target time
  is reached (with a short ~5s safety margin), instead of relying solely
  on the unit's own internal timer firing correctly. This makes the actual
  outcome (the AC turning on/off at the right time) independent of any
  remaining uncertainty in the timer-arming bytes, and keeps the "AC
  Power" switch in Home Assistant reflecting the real expected state with
  no extra logic needed.
- The `interval:` timer-watch component now runs every 5s instead of every
  15s, for tighter timing around the new safety margin.

### Fixed

- Off-timer could fail to arm reliably, or interfere with a concurrently
  active On-timer / iFeel, because of two shared bytes that were being
  overwritten instead of merged:
  - `B3`: On-timer's active flag (`0x80`) and Off-timer's target minute
    (low 7 bits) share this byte.
  - `B5`: On-timer's target minute (low 7 bits) and iFeel's active flag
    (`0x80`) share this byte.
  Both are now updated with OR/mask operations that preserve the other
  field's bits, matching the pattern already used for the dimmer bit in
  `B0` and the Off-timer flag in `B1`. See `docs/PROTOCOL.md` for details
  ("B3 and B5 are shared too").
