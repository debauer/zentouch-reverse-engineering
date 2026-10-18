#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Based on zenutils, Copyright 2007 Rasmus Ry.
"""Decrypt Zen Touch TL/FRESC entries using the installed OpenSSL libcrypto.

Reference: Rockbox utils/zenutils/source/{zen_crypt/main.cpp,shared/cenc.cpp}.
Only extraction/decryption is implemented; output files must be new.
"""

import argparse
import ctypes
import ctypes.util
import hashlib
import struct
import sys
from pathlib import Path

import zen_keys
from zen_cenc import decode_cenc
from zen_code import validate_code




class BlowfishKey(ctypes.Structure):
    _fields_ = [("p", ctypes.c_uint32 * 18), ("s", ctypes.c_uint32 * 1024)]


def _crypt_blowfish(data, key, iv, encrypt):
    if not data or len(data) % 8:
        raise ValueError("Blowfish input must be a nonempty multiple of 8 bytes")
    library = ctypes.util.find_library("crypto")
    if library is None:
        raise RuntimeError("OpenSSL libcrypto is required for Blowfish decryption")
    crypto = ctypes.CDLL(library)
    if not hasattr(crypto, "BF_set_key") or not hasattr(crypto, "BF_cbc_encrypt"):
        raise RuntimeError("Installed libcrypto does not expose the Blowfish API")
    crypto.BF_set_key.argtypes = [ctypes.POINTER(BlowfishKey), ctypes.c_int,
                                 ctypes.c_void_p]
    crypto.BF_set_key.restype = None
    crypto.BF_cbc_encrypt.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long,
                                     ctypes.POINTER(BlowfishKey), ctypes.c_void_p,
                                     ctypes.c_int]
    crypto.BF_cbc_encrypt.restype = None
    schedule = BlowfishKey()
    key_buffer = ctypes.create_string_buffer(key)
    input_buffer = ctypes.create_string_buffer(data, len(data))
    output_buffer = ctypes.create_string_buffer(len(data))
    iv_buffer = ctypes.create_string_buffer(iv, 8)
    crypto.BF_set_key(ctypes.byref(schedule), len(key), key_buffer)
    crypto.BF_cbc_encrypt(input_buffer, output_buffer, len(data),
                         ctypes.byref(schedule), iv_buffer, int(encrypt))
    return output_buffer.raw


def decrypt_blowfish(data, key, iv):
    return _crypt_blowfish(data, key, iv, False)


def encrypt_blowfish(data, key, iv):
    return _crypt_blowfish(data, key, iv, True)


def decrypt_entry(data, mode):
    if mode == "FRESC":
        decoded = decrypt_blowfish(data, zen_keys.get("fresc"), struct.pack(">II", len(data), 0))
    else:
        packed = decrypt_blowfish(data, zen_keys.get("tl"), struct.pack(">II", 0, len(data)))
        expected_size = struct.unpack_from(">I", packed)[0]
        if not 0 < expected_size <= len(data) * 3:
            raise ValueError("Invalid decoded length; wrong key or byte order")
        decoded = decode_cenc(packed[4:], expected_size)
    validate_code(decoded)
    return decoded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    zen_keys.add_arguments(parser)
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("-m", "--mode", choices=("TL", "FRESC"), default="TL")
    args = parser.parse_args()
    zen_keys.configure(args)
    decoded = decrypt_entry(args.input.read_bytes(), args.mode)
    info = validate_code(decoded)
    with args.output.open("xb") as output:
        output.write(decoded)
    print(f"Decrypted: {args.output} ({len(decoded):,d} bytes)")
    print("Program HMAC-SHA1: " + ("verified" if info["hmac_sha1_verified"] else "absent"))
    print(f"SHA256: {hashlib.sha256(decoded).hexdigest()}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, IndexError, struct.error) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
