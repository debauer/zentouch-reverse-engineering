#!/usr/bin/env python3
"""Build a signed CIFF archive from files in an extracted Zen Touch directory.

The directory's firmware.ciff supplies entry order and original name fields.
Payloads are read from the individual files; the archive HMAC is recomputed.
Reference: rockbox/utils/zenutils/source/{firmware_make,shared/firmware}.cpp.
"""

import argparse
import hashlib
import hmac
import struct
import sys
from pathlib import Path

import zen_keys
from extract_zen_firmware import unpack_archive


def pack_archive(files, metadata):
    if metadata["byte_order"] not in ("big", "little"):
        raise ValueError("Invalid archive byte order")
    big_endian = metadata["byte_order"] == "big"
    endian = ">" if big_endian else "<"
    entries = metadata["entries"]
    if (not entries or entries[-1]["tag_hex"] != b"NULL".hex()
            or entries[-1]["archive_offset"] != metadata["root_end"]):
        raise ValueError("Expected a single trailing NULL signature after CIFF root")
    children = bytearray()
    for entry in entries[:-1]:
        tag = bytes.fromhex(entry["tag_hex"])
        if len(tag) != 4 or tag == b"NULL" or entry["archive_offset"] >= metadata["root_end"]:
            raise ValueError("Unsupported archive entry structure")
        name_field = bytes.fromhex(entry["name_field_hex"])
        name_size = 32 if tag == b"DATA" else 24 if tag == b"EXT0" else 0
        if len(name_field) != name_size:
            raise ValueError("Invalid archive name field length")
        payload = name_field + files[entry["filename"]]
        children.extend(tag if big_endian else tag[::-1])
        children.extend(struct.pack(endian + "I", len(payload)))
        children.extend(payload)
    archive = (b"CIFF" if big_endian else b"FFIC") + struct.pack(endian + "I", len(children))
    archive += children
    digest = hmac.new(zen_keys.get("signing"), archive, hashlib.sha1).digest()
    archive += (b"NULL" if big_endian else b"LLUN") + struct.pack("<I", 20) + digest
    archive += b"\0" * (-len(archive) % 4)
    return bytes(archive)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    zen_keys.add_arguments(parser)
    parser.add_argument("directory", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args()
    zen_keys.configure(args)
    _, metadata = unpack_archive((args.directory / "firmware.ciff").read_bytes())
    files = {entry["filename"]: (args.directory / entry["filename"]).read_bytes()
             for entry in metadata["entries"] if entry["tag_hex"] != b"NULL".hex()}
    rebuilt = pack_archive(files, metadata)
    unpack_archive(rebuilt)  # Validate structure and freshly computed HMAC before writing.
    with args.output.open("xb") as output:
        output.write(rebuilt)
    print(f"Archive: {args.output} ({len(rebuilt):,d} bytes)")
    print("Archive HMAC-SHA1 verified: True")
    print(f"SHA256: {hashlib.sha256(rebuilt).hexdigest()}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, struct.error) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
