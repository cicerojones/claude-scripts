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

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def midi_to_note_name(midi_note: int) -> str:
    """Return the note name for a MIDI note number, e.g. 60 -> 'C4'."""
    octave = midi_note // 12 - 1
    return f"{NOTE_NAMES[midi_note % 12]}{octave}"


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


def print_table(
    description: str,
    cents_values: list[float],
    root_midi: int = 60,
    all_notes: bool = False,
) -> None:
    """Print a human-readable mapping table for a scale.

    Each row shows a physical key, its target pitch in cents from the root,
    the nearest whole semitone (coarse), and the remaining cents deviation (fine).
    """
    n = len(cents_values)
    period_cents = cents_values[-1]

    root_name = midi_to_note_name(root_midi)
    print(f"\nScale: {description}")
    print(f"Root:  {root_name} (MIDI {root_midi})  |  {n}-note scale, period {period_cents:.2f}¢\n")

    header = f"{'Key':<6}  {'Cents from root':>16}  {'Coarse':>12}  {'Fine':>6}"
    print(header)
    print("-" * len(header))

    num_rows = 128 if all_notes else n + 1  # +1 to include the period/closing note

    for step in range(num_rows):
        midi_note = root_midi + step
        if not (0 <= midi_note <= 127):
            break

        octave = step // n
        degree = step % n

        cents_from_root = 0.0 if degree == 0 else cents_values[degree - 1]
        total_cents = octave * period_cents + cents_from_root

        coarse_offset = round(total_cents / 100)
        fine_cents = total_cents - coarse_offset * 100.0

        # Fine expressed in Yamaha Motif units: -64..+63 spans ±100 cents (1.5625 ¢/unit).
        # Normalize to non-negative fine: borrow one coarse step when fine would be negative.
        fine_motif = max(-64, min(63, round(fine_cents / 1.5625)))
        if fine_motif < 0:
            coarse_offset -= 1
            fine_motif += 64

        coarse_midi = root_midi + coarse_offset
        coarse_name = midi_to_note_name(max(0, min(127, coarse_midi)))
        coarse_str = f"{coarse_name} ({'+' if coarse_offset >= 0 else ''}{coarse_offset})"
        fine_str = f"{'+' if fine_motif >= 0 else ''}{fine_motif}"

        period_marker = "  ← period" if (step > 0 and degree == 0) else ""

        print(
            f"{midi_to_note_name(midi_note):<6}"
            f"  {total_cents:>15.2f}¢"
            f"  {coarse_str:>12}"
            f"  {fine_str:>6}"
            f"{period_marker}"
        )

    print()


def scale_to_mts(
    description: str,
    cents_values: list[float],
    root_midi: int = 60,
    device_id: int = 0x00,
    tuning_program: int = 0,
) -> bytes:
    """Build the 408-byte MTS Bulk Tuning Dump SysEx.

    Args:
        description:    Scale description (used as the 16-byte name).
        cents_values:   N cent values from the .scl file (period is last).
        root_midi:      MIDI note number that plays the scale root (default 60 = C4).
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


def syx_to_coll_line(index: int, data: bytes) -> str:
    """Format one SysEx payload as a Max [coll] text line.

    Format:  index, b0 b1 b2 ... bN;
    Bytes are decimal integers separated by spaces.
    """
    byte_str = " ".join(str(b) for b in data)
    return f"{index}, {byte_str};"


def write_coll_file(entries: list[tuple[int, bytes, str]], coll_path: Path) -> None:
    """Write a [coll]-formatted text file.

    entries — list of (index, sysex_bytes, label) tuples.
    Each entry is a single line: index, b0 b1 ... bN;
    No comment lines — [coll] does not support them.
    """
    lines = [syx_to_coll_line(index, data) for index, data, _label in entries]
    coll_path.write_text("\n".join(lines) + "\n", encoding="ascii")
    print(f"  coll file -> {coll_path.name}  ({len(entries)} entries)")


def convert_file(
    scl_path: Path,
    syx_path: Path,
    root_midi: int = 60,
    device_id: int = 0x00,
    tuning_program: int = 0,
    write_coll: bool = False,
) -> None:
    description, cents_values = parse_scl(scl_path)
    sysex = scale_to_mts(description, cents_values, root_midi, device_id, tuning_program)
    syx_path.write_bytes(sysex)
    print(f"  {scl_path.name}  ->  {syx_path.name}  ({len(cents_values)}-note scale, period {cents_values[-1]:.2f}¢)")
    if write_coll:
        coll_path = syx_path.with_suffix(".txt")
        write_coll_file([(0, sysex, description)], coll_path)


def convert_directory(
    input_dir: Path,
    output_dir: Path,
    root_midi: int = 60,
    device_id: int = 0x00,
    write_coll: bool = False,
) -> None:
    scl_files = sorted(input_dir.glob("*.scl"))
    if not scl_files:
        print(f"No .scl files found in {input_dir}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Converting {len(scl_files)} file(s) from {input_dir} -> {output_dir}")

    errors = 0
    coll_entries: list[tuple[int, bytes, str]] = []

    for i, scl_file in enumerate(scl_files):
        syx_file = output_dir / (scl_file.stem + ".syx")
        try:
            description, cents_values = parse_scl(scl_file)
            sysex = scale_to_mts(description, cents_values, root_midi, device_id, tuning_program=i % 128)
            syx_file.write_bytes(sysex)
            print(f"  {scl_file.name}  ->  {syx_file.name}  ({len(cents_values)}-note scale, period {cents_values[-1]:.2f}¢)")
            if write_coll:
                coll_entries.append((i, sysex, description))
        except Exception as exc:
            print(f"  ERROR {scl_file.name}: {exc}")
            errors += 1

    if write_coll and coll_entries:
        write_coll_file(coll_entries, output_dir / "scales.txt")

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
  # Show mapping table for a scale (one period, root C4):
  python scl_to_minilogue.py --table myscale.scl

  # Table with all 128 MIDI notes:
  python scl_to_minilogue.py --table --all-notes myscale.scl

  # Table with a different root:
  python scl_to_minilogue.py --table --root 69 myscale.scl

  # Convert a single file (output alongside input):
  python scl_to_minilogue.py myscale.scl

  # Convert a single file to an explicit path:
  python scl_to_minilogue.py myscale.scl -o output/myscale.syx

  # Convert a whole directory of .scl files:
  python scl_to_minilogue.py scales/ -o output/

  # Convert a directory and write a Max [coll] text file (scales.txt):
  python scl_to_minilogue.py scales/ -o output/ --coll

  # Single file with [coll] sidecar:
  python scl_to_minilogue.py myscale.scl --coll
""",
    )
    parser.add_argument("input", help=".scl file or directory of .scl files")
    parser.add_argument("-o", "--output", help="Output .syx file or directory (default: alongside input)")
    parser.add_argument(
        "-t", "--table",
        action="store_true",
        help="Print a mapping table instead of writing a .syx file (single file only)",
    )
    parser.add_argument(
        "--all-notes",
        action="store_true",
        help="With --table: show all 128 MIDI notes instead of one period",
    )
    parser.add_argument(
        "--root",
        type=int,
        default=60,
        metavar="MIDI_NOTE",
        help="MIDI note number for the scale root (default: 60 = C4)",
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
    parser.add_argument(
        "--coll",
        action="store_true",
        help=(
            "Also write a Max [coll] formatted text file. "
            "Directory mode: one scales.txt containing all entries indexed by position. "
            "Single file mode: a .txt sidecar alongside the .syx."
        ),
    )

    args = parser.parse_args()
    input_p = Path(args.input)

    if args.table:
        if not input_p.is_file():
            print("Error: --table requires a single .scl file, not a directory.", file=sys.stderr)
            sys.exit(1)
        description, cents_values = parse_scl(input_p)
        print_table(description, cents_values, args.root, args.all_notes)
        return

    if input_p.is_dir():
        if args.output is None:
            print("Error: -o/--output is required when converting a directory.", file=sys.stderr)
            sys.exit(1)
        convert_directory(input_p, Path(args.output), args.root, args.device_id, args.coll)
    elif input_p.is_file():
        if args.output:
            out = Path(args.output)
            if out.is_dir():
                out = out / (input_p.stem + ".syx")
        else:
            out = input_p.with_suffix(".syx")
        convert_file(input_p, out, args.root, args.device_id, args.program, args.coll)
    else:
        print(f"Error: {args.input!r} is not a file or directory", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
