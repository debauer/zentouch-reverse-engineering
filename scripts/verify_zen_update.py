#!/usr/bin/env python3
"""Verify a generated update EXE with original Rockbox extraction/crypto tools.

The .firm size-field offset is passed explicitly to native update_extract:
its automatic search only inspects .data, which retains the original archive.
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from extract_zen_firmware import locate_firmware
from project_paths import OUTPUT_DIR, ROCKBOX_TOOLS_DIR, VERIFIED_ROUNDTRIP_DIR
from verify_rockbox_zencrypt import RAW_NAMES, TL_NAME, compare_files, run_tool, sha256


def compare_normalized_archive(actual, expected):
    actual_data, expected_data = actual.read_bytes(), expected.read_bytes()
    removed = len(expected_data) - len(actual_data)
    # Native update_extract writes the parsed CIFF again, dropping alignment zeros.
    if not (0 <= removed <= 3 and expected_data == actual_data + b"\0" * removed):
        raise ValueError("Archive extracted from EXE differs from requested firmware")
    print(f"PASS: native EXE extraction matches requested archive ({removed} alignment bytes omitted)")
    return {"byte_identical_after_alignment_normalization": True,
            "alignment_zero_bytes_omitted": removed}


def verify(args):
    updater, firmware, output = args.updater.resolve(), args.firmware.resolve(), args.output.resolve()
    tools = {name: args.tools_dir.resolve() / name
             for name in ("update_extract", "firmware_extract", "zen_crypt")}
    for tool in tools.values():
        if not tool.is_file() or not os.access(tool, os.X_OK):
            raise ValueError(
                f"Native executable missing: {tool}\n"
                "Re-run bash scripts/build_rockbox_zencrypt.sh"
            )
    inputs = {"updater": sha256(updater), "firmware": sha256(firmware)}
    location = locate_firmware(updater.read_bytes())
    output.mkdir(parents=True, exist_ok=False)
    report = {"passed": False, "inputs": inputs, "checks": [], "commands": [],
              "size_field_offset": location["offset"],
              "tools": {name: sha256(tool) for name, tool in tools.items()}}
    try:
        copied_exe, native_archive = output / "updater.exe", output / "from_exe.ciff"
        expected_archive = output / "expected.ciff"
        shutil.copyfile(updater, copied_exe)
        shutil.copyfile(firmware, expected_archive)
        report["commands"].append(run_tool(
            [tools["update_extract"], "-u", copied_exe, "-f", native_archive,
             "-o", hex(location["offset"]), "-V"], output))
        for name, archive in (("expected", expected_archive), ("from_exe", native_archive)):
            report["commands"].append(run_tool(
                [tools["zen_crypt"], "-v", "-k", "Zen Touch", "-i", archive], output))
            report["checks"].append({"label": f"{name} HMAC verified by BeeCrypt", "passed": True})
            directory = output / name
            directory.mkdir()
            report["commands"].append(run_tool(
                [tools["firmware_extract"], "-f", archive, "-p", str(directory) + os.sep], output))
            report["commands"].append(run_tool(
                [tools["zen_crypt"], "-d", "-m", "TL", "-k", "Zen Touch",
                 "-i", directory / TL_NAME, "-o", directory / "Jukebox2.jrm"], output))
        report["archive_comparison"] = compare_normalized_archive(native_archive, expected_archive)
        for name in (*RAW_NAMES, TL_NAME, "Jukebox2.jrm"):
            report["checks"].append(compare_files(
                output / "from_exe" / name, output / "expected" / name,
                f"native-extracted {name} from EXE equals input firmware"))
        if sha256(updater) != inputs["updater"] or sha256(firmware) != inputs["firmware"]:
            raise ValueError("Input changed during native EXE verification")
        report["passed"] = True
    except (OSError, ValueError, RuntimeError) as error:
        report["error"] = str(error)
        raise
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    print(f"\nNATIVE UPDATE EXE CHECK PASSED\nReport: {output / 'report.json'}")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-u", "--updater", type=Path,
                        default=OUTPUT_DIR / "updates" / "ZenTouchP4S_PCFW_LF_2_10_05_rebuilt.exe")
    parser.add_argument("-f", "--firmware", type=Path,
                        default=VERIFIED_ROUNDTRIP_DIR / "rebuilt.ciff")
    parser.add_argument("--tools-dir", type=Path, default=ROCKBOX_TOOLS_DIR)
    parser.add_argument("-o", "--output", type=Path,
                        default=OUTPUT_DIR / "verification" / "update_exe_native_check",
                        help="New verification directory (must not already exist)")
    verify(parser.parse_args())


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
