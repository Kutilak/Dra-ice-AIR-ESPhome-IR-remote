"""
Decoder for Drazice Air53 (DG11R2-01 / Hisense OEM) air conditioner IR
packets, captured with the ESPHome `remote_receiver` component
(`dump: pronto`).

Usage:
    py decode.py <log_file.txt> [labels]

    <log_file.txt>  - required, path to a capture file
    [labels]        - optional, only needed for logs WITHOUT "Beo4: n_sym=..."
                       lines (see below) - a comma-separated list of button
                       names, in the same order the buttons were pressed,
                       e.g.:
                         py decode.py capture_02_mode.txt "cooling,dry,fan only,heating,cooling,dry,fan only,heating"

What the script does:
  1. Splits the log into individual captured frames. Two log formats are
     supported:
       a) Logs with "Beo4: n_sym=344,<label>" lines before each frame
          (label = button name) - this is what the log looks like when
          the `remote.beo4` debug component was active during capture.
       b) Logs without labels - just raw "remote.pronto:239" lines back to
          back (e.g. when capturing several button presses in quick
          succession). In this case a new frame is detected by the fact
          that Pronto data always starts with the "0000" token (a real
          mark/space duration is never zero). Labels for each frame can be
          supplied as the second argument, see above.
  2. Joins consecutive "remote.pronto:239" lines into one list of hex
     tokens (Pronto raw format).
  3. Converts the timing into bits (pulse-distance, LSB first within each
     byte) and the bits into 3 byte blocks: A (6B), B (8B), C (7B) - see
     docs/PROTOCOL.md.
  4. Prints a hex dump of all blocks + a basic block-C checksum spot check.

Note: the checksum check below is a simple heuristic (plain byte sum), not
the full verified formula documented in PROTOCOL.md - it's only meant as a
quick sanity indicator while capturing, not as protocol-accurate
validation. Use the diff between consecutive frames (printed at the end)
to see exactly what a given button press changed.

When adding new captures: save the new log as another
"capture_NN_description.txt" in this folder and run this script on it.
"""
import re
import sys
import os

default_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "capture_01_baseline.txt")
path = sys.argv[1] if len(sys.argv) > 1 else default_path
manual_labels = [s.strip() for s in sys.argv[2].split(',')] if len(sys.argv) > 2 else None

lines = open(path, encoding='utf-8').read().splitlines()

HEX4 = re.compile(r'[0-9A-Fa-f]{4}')
label_re = re.compile(r'Beo4: n_sym=344,(.*)$')
data_re = re.compile(r'remote\.pronto:239\]: (.*)$')


def clean_tokens(payload):
    payload = payload.strip().rstrip(',')
    toks = payload.split()
    clean = []
    for t in toks:
        if HEX4.fullmatch(t):
            clean.append(t)
        else:
            break
    return clean


def parse_labeled(lines):
    """Format A: split on 'Beo4: n_sym=344,<label>' lines."""
    blocks = []
    cur_label = None
    cur_tokens = []
    for line in lines:
        m = label_re.search(line)
        if m and '[D]' in line:
            if cur_label is not None:
                blocks.append((cur_label, cur_tokens))
            cur_label = m.group(1).strip()
            cur_tokens = []
            continue
        m2 = data_re.search(line)
        if m2:
            cur_tokens.extend(clean_tokens(m2.group(1)))
    if cur_label is not None:
        blocks.append((cur_label, cur_tokens))
    return blocks


def parse_by_header(lines, labels=None):
    """Format B: no labels - a new frame starts wherever a data line's
    FIRST token is '0000' (the Pronto header always starts a fresh line in
    the log; the '0000' token also appears mid-header as a repeat count,
    so frames can't be split on any '0000' occurrence in the data, only on
    a line's first token)."""
    frames = []
    cur = []
    for line in lines:
        m2 = data_re.search(line)
        if not m2:
            continue
        toks = clean_tokens(m2.group(1))
        if not toks:
            continue
        if toks[0] == '0000' and cur:
            frames.append(cur)
            cur = []
        cur.extend(toks)
    if cur:
        frames.append(cur)

    blocks = []
    for i, toks in enumerate(frames):
        if labels and i < len(labels):
            label = labels[i]
        else:
            label = f"frame_{i + 1:02d}"
        blocks.append((label, toks))
    return blocks


def bits_to_bytes_lsb(bits):
    out = []
    n = len(bits) // 8
    for i in range(n):
        b = 0
        for j in range(8):
            b |= (bits[i * 8 + j] << j)
        out.append(b)
    return out


def decode_block(toks):
    vals = [int(t, 16) for t in toks]
    body = vals[4:]  # skip Pronto header (0000, freq_code, pairs_once, pairs_repeat)
    pairs = list(zip(body[0::2], body[1::2]))
    segs = []
    cur_bits = []
    for i, (m, s) in enumerate(pairs):
        if i == 0:
            continue  # AGC header pair, not data
        if s > 100:
            segs.append(cur_bits)
            cur_bits = []
            continue
        bit = 1 if s > 35 else 0
        cur_bits.append(bit)
    segs.append(cur_bits)
    return segs


blocks = parse_labeled(lines)
if not blocks:
    blocks = parse_by_header(lines, manual_labels)

print(f"File: {path}")
print(f"Found {len(blocks)} captured commands:\n")

decoded = []
for label, toks in blocks:
    if len(toks) < 8:
        print(f"{label!r}: TOO LITTLE DATA ({len(toks)} tokens), skipped")
        continue
    segs = decode_block(toks)
    A = bits_to_bytes_lsb(segs[0]) if len(segs) > 0 else []
    B = bits_to_bytes_lsb(segs[1]) if len(segs) > 1 else []
    C = bits_to_bytes_lsb(segs[2]) if len(segs) > 2 else []
    decoded.append((label, A, B, C))

    Ahex = ' '.join(f'{b:02X}' for b in A)
    Bhex = ' '.join(f'{b:02X}' for b in B)
    Chex = ' '.join(f'{b:02X}' for b in C)

    checksum_note = ""
    if len(C) == 7:
        calc = sum(C[:6]) & 0xFF
        checksum_note = "OK" if calc == C[6] else f"MISMATCH (computed {calc:02X})"

    print(f"{label}")
    print(f"  A[{len(A)}]: {Ahex}")
    print(f"  B[{len(B)}]: {Bhex}")
    print(f"  C[{len(C)}]: {Chex}   checksum: {checksum_note}")
    print()

# Diff between consecutive frames - useful for controlled captures
# (one button = one difference).
if len(decoded) > 1:
    print("=" * 70)
    print("Diff between consecutive frames (only changed bytes, A/B/C joined):")
    print("=" * 70)
    prev = None
    for label, A, B, C in decoded:
        cur = A + B + C
        if prev is not None and len(prev[1]) == len(cur):
            diffs = [f"[{i}] {prev[1][i]:02X}->{cur[i]:02X}" for i in range(len(cur)) if prev[1][i] != cur[i]]
            print(f"{prev[0]!r} -> {label!r}: {', '.join(diffs) if diffs else '(no difference)'}")
        prev = (label, cur)
