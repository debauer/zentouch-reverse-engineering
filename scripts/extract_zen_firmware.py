#!/usr/bin/env python3
"""Extract a Creative updater's firmware without executing the Windows EXE.

Format reference: Rockbox utils/zenutils/source/shared/{updater,firmware}.cpp
https://github.com/Rockbox/rockbox/tree/master/utils/zenutils
"""

import argparse
import hashlib
import hmac
import json
import re
import struct
import sys
import zlib
from pathlib import Path

import zen_keys
from project_paths import OUTPUT_DIR
from zen_pe import code_references, read_pe, section_named




def sha256(data):
    return hashlib.sha256(data).hexdigest()


def verify_signature(data, offset):
    expected = hmac.new(zen_keys.get("signing"), data[:offset], hashlib.sha1).digest()
    if not hmac.compare_digest(expected, data[offset + 8:offset + 28]):
        raise ValueError("Zen Touch HMAC-SHA1 signature does not match")


def data_section(exe):
    section = section_named(read_pe(exe), ".data")
    return section["raw_offset"], section["raw_size"]


def locate_firmware(exe):
    pe = read_pe(exe)
    if any(section["name"] == ".firm" for section in pe["sections"]):
        section = section_named(pe, ".firm")
        offset = section["raw_offset"]
        address = pe["image_base"] + section["rva"]
        if not code_references(exe, pe, address):
            raise ValueError("Updater code does not reference the .firm size field")
    else:
        section = section_named(pe, ".data")
        for relative in range(0, min(0x108, section["raw_size"] - 7), 4):
            offset = section["raw_offset"] + relative
            size = struct.unpack_from("<I", exe, offset)[0]
            if size and all(exe[offset + 4:offset + 8]):
                break
        else:
            raise ValueError("No firmware payload found at start of .data")
    if offset + 4 > section["raw_offset"] + section["raw_size"]:
        raise ValueError("Truncated firmware size field")
    size = struct.unpack_from("<I", exe, offset)[0]
    if not size or offset + 4 + size > section["raw_offset"] + section["raw_size"]:
        raise ValueError("Firmware payload extends beyond its PE section")
    return {"section": section, "offset": offset, "size": size}


def unpack_updater(exe):
    match = re.search(rb"(?:34d1|TbnCboEbn)[\x20-\x7e]*\x00", exe)
    if match is None:
        raise ValueError("No Creative XOR key found")
    key = match.group()[:-1]
    location = locate_firmware(exe)
    offset, size = location["offset"], location["size"]
    mask = bytes((byte - 1) | 0x80 for byte in key)
    encrypted = exe[offset + 4:offset + 4 + size]
    compressed = bytes(byte ^ mask[i % len(mask)]
                       for i, byte in enumerate(encrypted))
    inflater = zlib.decompressobj()
    firmware = inflater.decompress(compressed) + inflater.flush()
    if not inflater.eof:
        raise ValueError("Incomplete zlib stream")
    return firmware, {
        "xor_key": key.decode("ascii"),
        "xor_key_offset": match.start(),
        "size_field_offset": offset,
        "payload_offset": offset + 4,
        "payload_size": size,
        "payload_section": location["section"]["name"],
        "zlib_trailing_bytes_hex": inflater.unused_data.hex(),
    }


def unpack_archive(firmware):
    magic = firmware[:4]
    if len(firmware) < 8 or magic not in (b"CIFF", b"FFIC"):
        raise ValueError("Not a Creative CIFF archive")
    big_endian = magic == b"CIFF"
    endian = ">" if big_endian else "<"
    encoding = "utf-16be" if big_endian else "utf-16le"
    root_end = 8 + struct.unpack_from(endian + "I", firmware, 4)[0]
    if root_end > len(firmware):
        raise ValueError("Truncated CIFF root")
    files = {}
    entries = []
    offset = 8
    signed = False
    while offset + 8 <= len(firmware):
        raw_tag = firmware[offset:offset + 4]
        tag = raw_tag if big_endian else raw_tag[::-1]
        size_endian = "<" if tag == b"NULL" else endian
        size = struct.unpack_from(size_endian + "I", firmware, offset + 4)[0]
        end = offset + 8 + size
        if end > len(firmware) or (offset < root_end < end):
            raise ValueError("CIFF entry exceeds its container")
        body = firmware[offset + 8:end]
        name_size = 32 if tag == b"DATA" else 24 if tag == b"EXT0" else 0
        if len(body) < name_size:
            raise ValueError("Truncated CIFF entry name")
        if name_size:
            filename = body[:name_size].decode(encoding).split("\0", 1)[0]
        elif tag == b"\xa9TL ":
            filename = "TL.enc"
        elif re.fullmatch(rb"[A-Z0-9]{4}", tag):
            filename = tag.decode("ascii") + ".bin"
        else:
            filename = "tag_" + tag.hex() + ".bin"
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", filename) or filename in (".", ".."):
            raise ValueError(f"Unsafe entry filename: {filename!r}")
        if filename in files or filename in ("firmware.ciff", "manifest.json"):
            raise ValueError(f"Duplicate or reserved filename: {filename}")
        content = body[name_size:]
        files[filename] = content
        entry = {
            "tag_hex": tag.hex(),
            "archive_offset": offset,
            "entry_size": size,
            "content_offset": offset + 8 + name_size,
            "name_field_hex": body[:name_size].hex(),
            "filename": filename,
            "size": len(content),
            "sha256": sha256(content),
        }
        if tag == b"CINF":
            entry["player"] = content.decode(encoding).rstrip("\0")
        if tag == b"NULL":
            if size != 20:
                raise ValueError("Unexpected HMAC-SHA1 signature length")
            verify_signature(firmware, offset)
            signed = True
        entries.append(entry)
        offset = end
    padding = firmware[offset:]
    if offset < root_end or len(padding) > 3 or any(padding):
        raise ValueError("Unexpected bytes at end of CIFF archive")
    return files, {
        "byte_order": "big" if big_endian else "little",
        "root_end": root_end,
        "padding_hex": padding.hex(),
        "hmac_sha1_verified": signed,
        "entries": entries,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    zen_keys.add_arguments(parser)
    parser.add_argument("updater", type=Path)
    parser.add_argument("-o", "--output", type=Path,
                        help="New output directory (must not already exist)")
    args = parser.parse_args()
    zen_keys.configure(args)
    output = args.output or OUTPUT_DIR / "extracted" / (args.updater.stem + "_extracted")
    exe = args.updater.read_bytes()
    firmware, updater_info = unpack_updater(exe)
    files, archive_info = unpack_archive(firmware)
    manifest = {
        "source": args.updater.name,
        "source_size": len(exe),
        "source_sha256": sha256(exe),
        "firmware_size": len(firmware),
        "firmware_sha256": sha256(firmware),
        **updater_info,
        **archive_info,
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / "firmware.ciff").write_bytes(firmware)
    for filename, content in files.items():
        (output / filename).write_bytes(content)
        print(f"{filename:24} {len(content):10,d} bytes")
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="ascii")
    print(f"\nFirmware archive: {output / 'firmware.ciff'} ({len(firmware):,d} bytes)")
    print(f"XOR key: {manifest['xor_key']}")
    print(f"Size field at 0x{manifest['size_field_offset']:x}; "
          f"payload at 0x{manifest['payload_offset']:x}")
    print(f"Archive HMAC-SHA1 verified: {manifest['hmac_sha1_verified']}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, struct.error, zlib.error) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
