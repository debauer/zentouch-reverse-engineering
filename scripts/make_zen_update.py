#!/usr/bin/env python3
"""Put a signed Zen Touch CIFF archive into a new Windows update executable.

Uses Rockbox update_patch's .firm section/reference relocation approach when
the compressed archive does not fit the original payload slot.
"""

import argparse
import json
import struct
import sys
import zlib
from pathlib import Path

import zen_keys
from extract_zen_firmware import locate_firmware, sha256, unpack_archive, unpack_updater
from project_paths import FIRMWARE_INPUT_DIR, OUTPUT_DIR, VERIFIED_ROUNDTRIP_DIR
from zen_pe import append_firmware_section, code_references, pe_checksum, read_pe


DEFAULT_UPDATER = FIRMWARE_INPUT_DIR / "ZenTouchP4S_PCFW_LF_2_10_05.exe"
DEFAULT_FIRMWARE = VERIFIED_ROUNDTRIP_DIR / "rebuilt.ciff"


def require_touch_archive(firmware):
    _, metadata = unpack_archive(firmware)
    players = [entry.get("player") for entry in metadata["entries"]
               if entry["tag_hex"] == b"CINF".hex()]
    if players != ["Creative Zen Touch"] or not metadata["hmac_sha1_verified"]:
        raise ValueError("Expected a signed Creative Zen Touch firmware archive")
    return metadata


def patch_updater(source, firmware):
    original_firmware, original_info = unpack_updater(source)
    require_touch_archive(original_firmware)
    require_touch_archive(firmware)
    pe = read_pe(source)
    if pe["magic"] != 0x10B or pe["machine"] != 0x14C:
        raise ValueError("Only the 32-bit x86 Creative updater is supported")
    if pe["security_directory"] != (0, 0):
        raise ValueError("Input EXE has an Authenticode certificate; use the unsigned original updater")
    compressed = zlib.compress(firmware, level=9)
    mask = bytes((value - 1) | 0x80 for value in original_info["xor_key"].encode("ascii"))
    encrypted = bytes(value ^ mask[index % len(mask)] for index, value in enumerate(compressed))
    packet = struct.pack("<I", len(encrypted)) + encrypted
    location = locate_firmware(source)
    old_offset = location["offset"]
    section = location["section"]
    old_address = pe["image_base"] + section["rva"] + old_offset - section["raw_offset"]
    references = []
    if len(encrypted) <= location["size"]:
        patched = bytearray(source)
        patched[old_offset:old_offset + len(packet)] = packet
        new_offset = old_offset
        strategy = "replace existing payload"
    else:
        references = code_references(source, pe, old_address)
        if not references:
            raise ValueError("No updater code references found for firmware relocation")
        patched, new_offset, new_address = append_firmware_section(source, pe, packet)
        for reference in references:
            replacement = new_address + reference["address"] - old_address
            struct.pack_into("<I", patched, reference["file_offset"], replacement)
            reference["replacement_address"] = replacement
        if code_references(patched, read_pe(patched), old_address):
            raise ValueError("Updater code still references the old firmware size field")
        strategy = "append .firm and relocate code references"
    checksum = pe_checksum(patched, pe["checksum_offset"])
    struct.pack_into("<I", patched, pe["checksum_offset"], checksum)
    patched = bytes(patched)
    extracted, extracted_info = unpack_updater(patched)
    if extracted != firmware or extracted_info["size_field_offset"] != new_offset:
        raise ValueError("Firmware read back from patched EXE differs from requested archive")
    require_touch_archive(extracted)
    return patched, {
        "strategy": strategy,
        "source_updater_sha256": sha256(source),
        "source_updater_size": len(source),
        "output_updater_sha256": sha256(patched),
        "output_updater_size": len(patched),
        "source_firmware_sha256": sha256(original_firmware),
        "firmware_sha256": sha256(firmware),
        "firmware_size": len(firmware),
        "original_payload_size": location["size"],
        "new_payload_size": len(encrypted),
        "original_size_field_offset": old_offset,
        "new_size_field_offset": new_offset,
        "payload_section": extracted_info["payload_section"],
        "patched_code_references": references,
        "pe_checksum": checksum,
        "firmware_readback_byte_identical": True,
        "archive_hmac_sha1_verified": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    zen_keys.add_arguments(parser)
    parser.add_argument("-u", "--updater", type=Path, default=DEFAULT_UPDATER)
    parser.add_argument("-f", "--firmware", type=Path, default=DEFAULT_FIRMWARE)
    parser.add_argument("-o", "--output", type=Path,
                        help="New EXE filename; default: original name with _rebuilt.exe")
    args = parser.parse_args()
    zen_keys.configure(args)
    output = args.output or OUTPUT_DIR / "updates" / (args.updater.stem + "_rebuilt.exe")
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path = output.with_suffix(".report.json")
    readback_path = output.with_suffix(".firmware.ciff")
    for path in (output, report_path, readback_path):
        if path.exists():
            raise ValueError(f"Output already exists: {path}; choose a new -o filename")
    source, firmware = args.updater.read_bytes(), args.firmware.read_bytes()
    patched, report = patch_updater(source, firmware)
    with output.open("xb") as executable:
        executable.write(patched)
    written = output.read_bytes()
    readback, _ = unpack_updater(written)
    if written != patched or readback != firmware:
        raise ValueError("Written EXE failed readback verification")
    if args.updater.read_bytes() != source or args.firmware.read_bytes() != firmware:
        raise ValueError("An input changed during EXE construction")
    with readback_path.open("xb") as archive:
        archive.write(readback)
    report.update({"passed": True, "source": args.updater.name,
                   "firmware_input": str(args.firmware), "output": str(output),
                   "inputs_unchanged": True})
    with report_path.open("x", encoding="ascii") as report_file:
        report_file.write(json.dumps(report, indent=2) + "\n")
    print(f"UPDATE EXE BUILT: {output} ({len(patched):,d} bytes)")
    print(f"Strategy: {report['strategy']}")
    print(f"Firmware size field: 0x{report['new_size_field_offset']:x}")
    print(f"Code references relocated: {len(report['patched_code_references'])}")
    print("PASS: archive read back from EXE is byte-identical; HMAC verified")
    print(f"SHA256: {report['output_updater_sha256']}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, struct.error, zlib.error) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
