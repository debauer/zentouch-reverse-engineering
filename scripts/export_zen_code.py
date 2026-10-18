#!/usr/bin/env python3
"""Export verified CODE load-record payloads and a raw-address memory map."""

import argparse
import json
import struct
import sys
from pathlib import Path

from project_paths import OUTPUT_DIR, VERIFIED_ROUNDTRIP_DIR
from zen_code import parse_code_image


DEFAULT_IMAGE = VERIFIED_ROUNDTRIP_DIR / "original" / "Jukebox2.jrm"


def memory_map_text(metadata):
    lines = [
        "Creative Zen Touch CODE load-record map",
        f"Source SHA256: {metadata['source_sha256']}",
        f"Source bytes: {metadata['source_size_bytes']}",
        f"Blocks: {metadata['block_count']}; payload bytes: {metadata['payload_total_bytes']}",
        f"Uninterpreted header word at 0x08: 0x{metadata['header_word_0x08']['value']:08x}",
        "",
        "Addresses below are raw record fields, not verified CPU-space assignments.",
        "End = raw address + payload byte count; end is exclusive.",
        "C55x program addresses are bytes; data addresses are 16-bit words.",
        "Code/data classification and CPU-space normalization remain unresolved.",
        "Payload bytes are preserved exactly; container endianness does not select a decoder mode.",
        "",
        "Idx Raw address End (byte view) Bytes    File payload Checksum Filename",
        "--- ----------- --------------- -------- ------------ -------- ---------------------",
    ]
    for block in metadata["blocks"]:
        lines.append(f"{block['index']:3d} 0x{block['address_field']:08x}  0x{block['raw_byte_view_end_exclusive']:08x}"
                     f"      {block['payload_size_bytes']:8d} 0x{block['payload_file_offset']:08x}"
                     f"   0x{block['checksum_stored']:04x}   {block['filename']}")
    overlaps = metadata["address_map"]["raw_byte_view_overlaps"]
    lines.extend(("", f"Raw-address byte-view overlaps: {len(overlaps)}"))
    for overlap in overlaps:
        lines.append(f"  blocks {overlap['block_indices']}: "
                     f"0x{overlap['raw_byte_view_start']:08x}.."
                     f"0x{overlap['raw_byte_view_end_exclusive']:08x} (exclusive end)")
    lines.extend(("", f"Trailer: {metadata['trailer_hex'] or '(none)'}",
                  "All block checksums verified; exported bytes reconstruct the full source image."))
    return "\n".join(lines) + "\n"


def export_image(input_path, output):
    source = input_path.read_bytes()
    files, metadata = parse_code_image(source)
    output.mkdir(parents=True, exist_ok=False)
    for filename, payload in files.items():
        (output / filename).write_bytes(payload)
    rebuilt = bytes.fromhex(metadata["container_header_hex"])
    for block in metadata["blocks"]:
        rebuilt += bytes.fromhex(block["record_header_hex"])
        rebuilt += (output / block["filename"]).read_bytes()
    rebuilt += bytes.fromhex(metadata["trailer_hex"])
    if rebuilt != source:
        raise ValueError("Exported headers and payloads do not reconstruct the original image")
    if input_path.read_bytes() != source:
        raise ValueError("Source image changed during export")
    metadata.update({
        "source_name": input_path.name,
        "export_checks": {"all_block_checksums_verified": True,
                          "source_reconstruction_byte_identical": True,
                          "source_unchanged": True},
    })
    (output / "manifest.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="ascii")
    (output / "memory_map.txt").write_text(memory_map_text(metadata), encoding="ascii")
    print(f"EXPORTED: {metadata['block_count']} blocks, {metadata['payload_total_bytes']:,d} payload bytes")
    print("PASS: every block checksum verified")
    print("PASS: exported blocks and preserved headers reconstruct the source byte-for-byte")
    print(f"Raw-address byte-view overlaps: {len(metadata['address_map']['raw_byte_view_overlaps'])}")
    print(f"Manifest: {output / 'manifest.json'}")
    print(f"Memory map: {output / 'memory_map.txt'}")
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, nargs="?", default=DEFAULT_IMAGE,
                        help="Decrypted CODE image; default: original Jukebox2.jrm")
    parser.add_argument("-o", "--output", type=Path,
                        help="New output directory (must not already exist)")
    args = parser.parse_args()
    output = args.output or OUTPUT_DIR / "code" / (args.input.stem + "_code_blocks")
    export_image(args.input, output)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, struct.error) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
