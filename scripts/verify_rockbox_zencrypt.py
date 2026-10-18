#!/usr/bin/env python3
"""Independently verify the firmware roundtrip using native Rockbox tools.

Requires tools built with scripts/build_rockbox_zencrypt.sh and a successful
roundtrip directory. This script uses only Python's standard library, not the
Python firmware codec, parser, or OpenSSL helpers.
"""

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from project_paths import OUTPUT_DIR, ROCKBOX_TOOLS_DIR, VERIFIED_ROUNDTRIP_DIR

TL_NAME = "0xa9544c20"  # Native firmware_extract names the non-ASCII tag this way.
RAW_NAMES = ("CINF", "FBOOT", "FRESC", "Hjukebox2.jrs", "Hunicjkl.nft",
             "Hsplash.jbm", "Hdevicon.ico", "Hdevlogo.png", "Pmcu0")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare_files(left, right, label):
    actual, expected = left.read_bytes(), right.read_bytes()
    if actual != expected:
        raise ValueError(f"Byte comparison failed: {label}\n  {left}\n  {right}")
    print(f"PASS: {label} ({len(actual):,d} bytes)")
    return {"label": label, "size": len(actual), "sha256": sha256(left),
            "byte_identical": True}


def run_tool(command, output, *, rejection_message=None):
    print("RUN: " + shlex.join([str(arg) for arg in command]))
    result = subprocess.run(command, cwd=output, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                            errors="replace", env={**os.environ, "LC_ALL": "C"})
    with (output / "commands.log").open("a", encoding="utf-8") as log:
        log.write("$ " + shlex.join([str(arg) for arg in command]) + "\n")
        log.write(result.stdout + f"\n[exit status {result.returncode}]\n\n")
    print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if rejection_message is not None:
        if result.returncode <= 0 or rejection_message not in result.stdout:
            raise RuntimeError("Native tool did not reject tampering with the expected HMAC error")
    elif result.returncode != 0:
        raise RuntimeError(f"Native tool failed with exit status {result.returncode}; see commands.log")
    return {"command": [str(arg) for arg in command], "exit_status": result.returncode}


def verify(args):
    roundtrip = args.roundtrip.resolve()
    output = args.output.resolve()
    zen_crypt, extractor = args.tool.resolve(), args.extractor.resolve()
    for tool in (zen_crypt, extractor):
        if not tool.is_file() or not os.access(tool, os.X_OK):
            raise ValueError(
                f"Native executable missing: {tool}\n"
                "Run scripts/build_rockbox_zencrypt.sh first"
            )
    source_report = json.loads((roundtrip / "report.json").read_text())
    if source_report.get("passed") is not True:
        raise ValueError("Input roundtrip does not have a successful report")
    inputs = {
        "original_archive": roundtrip / "original/firmware.ciff",
        "rebuilt_archive": roundtrip / "rebuilt.ciff",
        "reference_program": roundtrip / "original/Jukebox2.jrm",
        "python_redecoded_program": roundtrip / "reextracted/Jukebox2.jrm",
    }
    expected_hashes = {
        "original_archive": source_report["container_only"]["sha256"],
        "rebuilt_archive": source_report["rebuilt_archive"]["sha256"],
        "reference_program": source_report["main_program"]["decoded_sha256"],
        "python_redecoded_program": source_report["main_program"]["decoded_sha256"],
    }
    for name, path in inputs.items():
        if sha256(path) != expected_hashes[name]:
            raise ValueError(f"Input no longer matches roundtrip report: {path}")
    output.mkdir(parents=True, exist_ok=False)
    report = {"passed": False, "roundtrip": str(roundtrip), "checks": [],
              "commands": [], "input_sha256": expected_hashes,
              "tools": {str(tool): sha256(tool) for tool in (zen_crypt, extractor)}}
    report_path = output / "report.json"
    try:
        archives = output / "archives"
        archives.mkdir()
        directories = {name: output / name for name in ("original", "rebuilt")}
        for name, directory in directories.items():
            directory.mkdir()
            archive = archives / f"{name}.ciff"
            shutil.copyfile(inputs[f"{name}_archive"], archive)
            report["commands"].append(run_tool(
                [zen_crypt, "-v", "-k", "Zen Touch", "-i", archive], output))
            report["checks"].append({"label": f"{name} archive HMAC (BeeCrypt)", "passed": True})
            report["commands"].append(run_tool(
                [extractor, "-f", archive, "-p", str(directory) + os.sep], output))
            report["commands"].append(run_tool(
                [zen_crypt, "-d", "-m", "TL", "-k", "Zen Touch",
                 "-i", directory / TL_NAME, "-o", directory / "Jukebox2.jrm"], output))
            report["checks"].append(compare_files(
                directory / "Jukebox2.jrm", inputs["reference_program"],
                f"native-decoded {name} main firmware equals original program"))

        original, rebuilt = directories["original"], directories["rebuilt"]
        report["checks"].append(compare_files(
            rebuilt / "Jukebox2.jrm", inputs["python_redecoded_program"],
            "native and Python decoders agree on rebuilt program"))
        for name in RAW_NAMES:
            report["checks"].append(compare_files(
                rebuilt / name, original / name, f"native-extracted payload {name}"))
        report["checks"].append(compare_files(
            rebuilt / TL_NAME, roundtrip / "reextracted/TL.enc",
            "tested TL ciphertext is the one stored inside rebuilt CIFF"))

        damaged = bytearray(inputs["rebuilt_archive"].read_bytes())
        damaged[len(damaged) // 2] ^= 1
        damaged_path = archives / "tampered.ciff"
        damaged_path.write_bytes(damaged)
        report["commands"].append(run_tool(
            [zen_crypt, "-v", "-k", "Zen Touch", "-i", damaged_path], output,
            rejection_message="The NULL signature contains an incorrect digest."))
        report["checks"].append({"label": "native HMAC rejects one-bit corruption", "passed": True})
        for name, path in inputs.items():
            if sha256(path) != expected_hashes[name]:
                raise ValueError(f"Input changed during verification: {path}")
        report["passed"] = True
    except (OSError, ValueError, RuntimeError) as error:
        report["error"] = str(error)
        raise
    finally:
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    print(f"\nINDEPENDENT ROCKBOX CHECK PASSED\nReport: {report_path}")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roundtrip", type=Path, default=VERIFIED_ROUNDTRIP_DIR)
    parser.add_argument("--tool", type=Path, default=ROCKBOX_TOOLS_DIR / "zen_crypt")
    parser.add_argument("--extractor", type=Path,
                        default=ROCKBOX_TOOLS_DIR / "firmware_extract")
    parser.add_argument("-o", "--output", type=Path,
                        default=OUTPUT_DIR / "verification" / "rockbox_independent_check",
                        help="New output directory (must not already exist)")
    args = parser.parse_args()
    verify(args)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
