#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Based on zenutils, Copyright 2007 Rasmus Ry.
"""Encode and encrypt a Zen Touch CODE image; uses the installed libcrypto."""

import argparse
import hashlib
import struct
import sys
from pathlib import Path

import zen_keys
from decrypt_zen_touch import encrypt_blowfish, validate_code
from zen_cenc import encode_cenc


def encrypt_entry(decoded, mode="TL"):
    validate_code(decoded)
    if mode == "FRESC":
        return encrypt_blowfish(decoded, zen_keys.get("fresc"), struct.pack(">II", len(decoded), 0))
    if mode != "TL":
        raise ValueError("Unsupported entry encryption mode")
    packed = struct.pack(">I", len(decoded)) + encode_cenc(decoded)
    packed += b"\0" * (-len(packed) % 8)
    return encrypt_blowfish(packed, zen_keys.get("tl"), struct.pack(">II", 0, len(packed)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    zen_keys.add_arguments(parser)
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("-m", "--mode", choices=("TL", "FRESC"), default="TL")
    args = parser.parse_args()
    zen_keys.configure(args)
    encrypted = encrypt_entry(args.input.read_bytes(), args.mode)
    with args.output.open("xb") as output:
        output.write(encrypted)
    print(f"Encrypted: {args.output} ({len(encrypted):,d} bytes)")
    print(f"SHA256: {hashlib.sha256(encrypted).hexdigest()}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, struct.error) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
