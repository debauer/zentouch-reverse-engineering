#!/usr/bin/env python3
"""Run an unchanged Zen Touch firmware roundtrip entirely under Linux.

Rebuilds both the CIFF container and the encrypted main program, reads the
results back, compares actual bytes, and checks archive HMACs.
"""

import argparse
import json
import struct
import sys
import zlib
from pathlib import Path

import zen_keys
from decrypt_zen_touch import decrypt_entry, validate_code
from encrypt_zen_touch import encrypt_entry
from extract_zen_firmware import sha256, unpack_archive, unpack_updater
from project_paths import OUTPUT_DIR
from pack_zen_firmware import pack_archive


def require_equal(actual, expected, label):
    if actual != expected:
        raise ValueError(f"Byte comparison failed: {label}")


def save_bundle(directory, firmware, files, metadata):
    directory.mkdir()
    (directory / "firmware.ciff").write_bytes(firmware)
    for name, payload in files.items():
        (directory / name).write_bytes(payload)
    (directory / "manifest.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="ascii")


def run_roundtrip(updater, output):
    source = updater.read_bytes()
    firmware, updater_info = unpack_updater(source)
    files, metadata = unpack_archive(firmware)
    if not metadata["hmac_sha1_verified"]:
        raise ValueError("Expected a signed source archive")
    output.mkdir(parents=True, exist_ok=False)
    original = output / "original"
    save_bundle(original, firmware, files, metadata)

    # Rebuild from extracted files, including exact original name fields.
    stored_files = {name: (original / name).read_bytes() for name in files}
    _, stored_metadata = unpack_archive((original / "firmware.ciff").read_bytes())
    container_only = pack_archive(stored_files, stored_metadata)
    container_path = output / "container-only.ciff"
    container_path.write_bytes(container_only)
    container_only = container_path.read_bytes()
    require_equal(container_only, firmware, "container-only archive")
    unpack_archive(container_only)
    print("PASS: container-only rebuild is byte-identical to original CIFF")

    main = decrypt_entry(stored_files["TL.enc"], "TL")
    (original / "Jukebox2.jrm").write_bytes(main)
    rebuilt_main = encrypt_entry((original / "Jukebox2.jrm").read_bytes())
    decoded_main = decrypt_entry(rebuilt_main, "TL")
    require_equal(decoded_main, main, "main firmware after encoding/encryption")
    print(f"PASS: main firmware decode/encode/encrypt/decrypt ({len(main):,d} bytes)")

    rescue = decrypt_entry(stored_files["FRESC"], "FRESC")
    (original / "FRESC.decrypted.bin").write_bytes(rescue)
    rebuilt_rescue = encrypt_entry((original / "FRESC.decrypted.bin").read_bytes(), "FRESC")
    require_equal(rebuilt_rescue, stored_files["FRESC"], "re-encrypted recovery firmware")
    print("PASS: recovery firmware re-encryption is byte-identical")

    repacked_files = {**stored_files, "TL.enc": rebuilt_main, "FRESC": rebuilt_rescue}
    rebuilt_archive = pack_archive(repacked_files, stored_metadata)
    rebuilt_path = output / "rebuilt.ciff"
    rebuilt_path.write_bytes(rebuilt_archive)
    checked_archive = rebuilt_path.read_bytes()
    checked_files, checked_metadata = unpack_archive(checked_archive)
    original_structure = [(entry["tag_hex"], entry["filename"], entry["name_field_hex"])
                          for entry in metadata["entries"]]
    checked_structure = [(entry["tag_hex"], entry["filename"], entry["name_field_hex"])
                         for entry in checked_metadata["entries"]]
    require_equal(checked_structure, original_structure, "entry order, tags and name fields")
    if not checked_metadata["hmac_sha1_verified"]:
        raise ValueError("Rebuilt archive HMAC was not verified")

    checked_main = decrypt_entry(checked_files["TL.enc"], "TL")
    checked_rescue = decrypt_entry(checked_files["FRESC"], "FRESC")
    require_equal(checked_main, main, "main firmware from rebuilt archive")
    require_equal(checked_rescue, rescue, "recovery firmware from rebuilt archive")
    comparisons = []
    for entry in metadata["entries"]:
        name = entry["filename"]
        if name == "NULL.bin":
            continue  # The archive's MAC is freshly computed and separately verified.
        expected = main if name == "TL.enc" else stored_files[name]
        actual = checked_main if name == "TL.enc" else checked_files[name]
        require_equal(actual, expected, name)
        comparisons.append({
            "filename": name,
            "comparison": "decoded CODE image" if name == "TL.enc" else "raw entry content",
            "size": len(actual),
            "original_sha256": sha256(expected),
            "rebuilt_sha256": sha256(actual),
            "byte_identical": True,
        })
    print(f"PASS: all {len(comparisons)} payloads are byte-identical; archive HMAC verified")

    # A damaged payload must fail authentication, even if CIFF structure is intact.
    rescue_entry = next(entry for entry in checked_metadata["entries"]
                        if entry["filename"] == "FRESC")
    damaged = bytearray(checked_archive)
    damaged[rescue_entry["content_offset"] + 64] ^= 1
    try:
        unpack_archive(bytes(damaged))
    except ValueError as error:
        if "HMAC-SHA1 signature does not match" not in str(error):
            raise
    else:
        raise ValueError("HMAC verification accepted a damaged payload")
    print("PASS: one-bit payload corruption is rejected by HMAC verification")

    checked_directory = output / "reextracted"
    save_bundle(checked_directory, checked_archive, checked_files, checked_metadata)
    (checked_directory / "Jukebox2.jrm").write_bytes(checked_main)
    (checked_directory / "FRESC.decrypted.bin").write_bytes(checked_rescue)
    require_equal(updater.read_bytes(), source, "original updater after roundtrip")
    report = {
        "passed": True,
        "source": updater.name,
        "source_sha256": sha256(source),
        "source_unchanged": True,
        "updater_payload": updater_info,
        "container_only": {
            "byte_identical": True,
            "size": len(container_only),
            "sha256": sha256(container_only),
            "hmac_sha1_verified": True,
        },
        "main_program": {
            "decoded_size": len(main),
            "decoded_sha256": sha256(main),
            "decoded_byte_identical": True,
            "original_encrypted_size": len(stored_files["TL.enc"]),
            "rebuilt_encrypted_size": len(rebuilt_main),
            "ciphertext_byte_identical": rebuilt_main == stored_files["TL.enc"],
            "code_container": validate_code(main),
        },
        "recovery_program": {
            "decoded_size": len(rescue),
            "decoded_sha256": sha256(rescue),
            "decoded_byte_identical": True,
            "ciphertext_byte_identical": True,
        },
        "rebuilt_archive": {
            "size": len(checked_archive),
            "sha256": sha256(checked_archive),
            "byte_identical_to_original": checked_archive == firmware,
            "hmac_sha1_verified": checked_metadata["hmac_sha1_verified"],
            "hmac_tamper_rejected": True,
            "payload_comparisons": comparisons,
        },
    }
    report_path = output / "report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    print(f"\nROUNDTRIP PASSED. Report: {report_path}")
    print(f"Rebuilt archive: {rebuilt_path} ({len(checked_archive):,d} bytes)")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    zen_keys.add_arguments(parser)
    parser.add_argument("updater", type=Path)
    parser.add_argument("-o", "--output", type=Path,
                        help="New output directory (must not already exist)")
    args = parser.parse_args()
    zen_keys.configure(args)
    output = args.output or OUTPUT_DIR / "roundtrip" / (args.updater.stem + "_roundtrip")
    run_roundtrip(args.updater, output)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError, struct.error, zlib.error) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
