#!/usr/bin/env python3
"""Convert Scala .scl files to Korg Minilogue MTS SysEx format (408 bytes).

Output is a standard MIDI Tuning Standard Bulk Tuning Dump, which the
Minilogue accepts as a User Scale. Send via MIDI SysEx to the Minilogue
while it is on the User Scale menu parameter.

Format:
  F0 7E nn 08 01 tt [16-byte name] [128 notes * 3 bytes] [checksum] F7
  = 408 bytes total

Each note encodes a pitch as:
  xx = base semitone (0-127 MIDI note number)
  yy = high 7 bits of 14-bit fractional semitone
  zz = low 7 bits of 14-bit fractional semitone
  resolution = 100 / 16384 ≈ 0.0061 cents
"""

import math
import sys
from pathlib import Path


def parse_scl(filepath: Path) -> tuple[str, list[float]]:
    """Parse a Scala .scl file.

    Returns (description, cents_values) where cents_values has N entries:
    the N-1 intermediate intervals plus the period (usually 1200 cents).
    The implicit root (0 cents / 1/1) is NOT included in this list.
    """
    text = filepath.read_text(encoding="utf-8", errors="replace")
    data_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("!")
    ]

    if len(data_lines) < 2:
        raise ValueError(f"Too few data lines in {filepath}")

    description = data_lines[0]

    try:
        num_notes = int(data_lines[1])
    except ValueError:
        raise ValueError(f"Invalid note count in {filepath}: {data_lines[1]!r}")

    if len(data_lines) < 2 + num_notes:
        raise ValueError(
            f"Expected {num_notes} pitch values in {filepath}, "
            f"found {len(data_lines) - 2}"
        )

    cents_values: list[float] = []
    for i in range(num_notes):
        token = data_lines[2 + i].split()[0]
        if "/" in token:
            num_s, den_s = token.split("/", 1)
            ratio = float(num_s) / float(den_s)
            cents = 1200.0 * math.log2(ratio)
        elif "." in token:
            cents = float(token)
        else:
            # Plain integer treated as ratio N/1
            cents = 1200.0 * math.log2(float(token))
        cents_values.append(cents)

    return description, cents_values


def _pitch_to_mts_bytes(semitone_float: float) -> tuple[int, int, int]:
    """Encode a pitch (as a fractional MIDI note number) into 3 MTS bytes."""
    semitone_float = max(0.0, min(127.9994, semitone_float))
    xx = int(semitone_float)
    frac = semitone_float - xx
    frac_14 = min(16383, round(frac * 16384))
    yy = (frac_14 >> 7) & 0x7F
    zz = frac_14 & 0x7F
    return xx, yy, zz


def scale_to_mts(
    description: str,
    cents_values: list[float],
    root_midi: int = 69,
    device_id: int = 0x00,
    tuning_program: int = 0,
) -> bytes:
    """Build the 408-byte MTS Bulk Tuning Dump SysEx.

    Args:
        description:    Scale description (used as the 16-byte name).
        cents_values:   N cent values from the .scl file (period is last).
        root_midi:      MIDI note number that plays the scale root (default 69 = A4).
        device_id:      SysEx device ID byte (default 0x00 = all devices).
        tuning_program: Tuning program slot 0-127 (default 0).

    Returns:
        408-byte bytes object ready to write as .syx.
    """
    n = len(cents_values)
    period_cents = cents_values[-1]  # usually 1200.0

    # Build tuning for all 128 MIDI notes.
    # Python's floor division handles negative offsets naturally:
    #   offset = midi - root
    #   octave = offset // n   (floors toward -inf)
    #   degree = offset % n    (always 0..n-1)
    freq_bytes = bytearray()
    for midi_note in range(128):
        offset = midi_note - root_midi
        octave = offset // n
        degree = offset % n  # 0 = root, 1..n-1 = scale steps

        if degree == 0:
            cents_from_root = 0.0
        else:
            cents_from_root = cents_values[degree - 1]

        total_cents = octave * period_cents + cents_from_root
        # Express the target pitch as a fractional MIDI note number.
        semitone_float = root_midi + total_cents / 100.0
        xx, yy, zz = _pitch_to_mts_bytes(semitone_float)
        freq_bytes.extend([xx, yy, zz])

    assert len(freq_bytes) == 384

    # 16-byte name: ASCII, padded with spaces, truncated if longer.
    name = description.encode("ascii", errors="replace")[:16].ljust(16, b" ")

    tt = tuning_program & 0x7F
    nn = device_id & 0x7F

    # Checksum: XOR of [nn, 08, 01, tt, name(16), freq(384)] & 0x7F
    checksum_payload = bytes([nn, 0x08, 0x01, tt]) + name + bytes(freq_bytes)
    checksum = 0
    for b in checksum_payload:
        checksum ^= b
    checksum &= 0x7F

    sysex = (
        bytes([0xF0, 0x7E, nn, 0x08, 0x01, tt])
        + name
        + bytes(freq_bytes)
        + bytes([checksum, 0xF7])
    )

    assert len(sysex) == 408, f"BUG: expected 408 bytes, got {len(sysex)}"
    return sysex


def convert_file(
    scl_path: Path,
    syx_path: Path,
    root_midi: int = 69,
    device_id: int = 0x00,
    tuning_program: int = 0,
) -> None:
    description, cents_values = parse_scl(scl_path)
    sysex = scale_to_mts(description, cents_values, root_midi, device_id, tuning_program)
    syx_path.write_bytes(sysex)
    print(f"  {scl_path.name}  ->  {syx_path.name}  ({len(cents_values)}-note scale, period {cents_values[-1]:.2f}¢)")


def convert_directory(
    input_dir: Path,
    output_dir: Path,
    root_midi: int = 69,
    device_id: int = 0x00,
) -> None:
    scl_files = sorted(input_dir.glob("*.scl"))
    if not scl_files:
        print(f"No .scl files found in {input_dir}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Converting {len(scl_files)} file(s) from {input_dir} -> {output_dir}")

    errors = 0
    for i, scl_file in enumerate(scl_files):
        syx_file = output_dir / (scl_file.stem + ".syx")
        try:
            convert_file(scl_file, syx_file, root_midi, device_id, tuning_program=i % 128)
        except Exception as exc:
            print(f"  ERROR {scl_file.name}: {exc}")
            errors += 1

    if errors:
        print(f"\n{errors} file(s) failed.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert Scala .scl files to Korg Minilogue MTS SysEx (.syx)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single file, output alongside input:
  python scl_to_minilogue.py myscale.scl

  # Single file, explicit output path:
  python scl_to_minilogue.py myscale.scl -o output/myscale.syx

  # Whole directory of .scl files -> output/ folder:
  python scl_to_minilogue.py scales/ -o output/

  # Root note C4 (MIDI 60) instead of A4 (69):
  python scl_to_minilogue.py scales/ -o output/ --root 60
""",
    )
    parser.add_argument("input", help=".scl file or directory of .scl files")
    parser.add_argument("-o", "--output", help="Output .syx file or directory (default: alongside input)")
    parser.add_argument(
        "--root",
        type=int,
        default=69,
        metavar="MIDI_NOTE",
        help="MIDI note number for the scale root (default: 69 = A4). "
             "Common values: 60=C4, 69=A4",
    )
    parser.add_argument(
        "--device-id",
        type=lambda x: int(x, 0),
        default=0x00,
        metavar="ID",
        help="SysEx device ID byte, hex OK (default: 0x00 = all devices)",
    )
    parser.add_argument(
        "--program",
        type=int,
        default=0,
        metavar="N",
        help="Tuning program number 0-127 for single-file conversion (default: 0)",
    )

    args = parser.parse_args()
    input_p = Path(args.input)

    if input_p.is_dir():
        out = Path(args.output) if args.output else input_p
        convert_directory(input_p, out, args.root, args.device_id)
    elif input_p.is_file():
        if args.output:
            out = Path(args.output)
            if out.is_dir():
                out = out / (input_p.stem + ".syx")
        else:
            out = input_p.with_suffix(".syx")
        convert_file(input_p, out, args.root, args.device_id, args.program)
    else:
        print(f"Error: {args.input!r} is not a file or directory", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
