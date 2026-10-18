#!/usr/bin/env python3
"""Create the working directories the tools use by default, below the repository root
(or ZEN_ROOT): input/firmware (put the updater EXE here), output, build.

Usage: python3 scripts/init_dirs.py
"""
import sys

from project_paths import BUILD_DIR, FIRMWARE_INPUT_DIR, OUTPUT_DIR, PROJECT_ROOT

DIRS = (FIRMWARE_INPUT_DIR, OUTPUT_DIR, BUILD_DIR)


def main():
    for d in DIRS:
        state = "exists" if d.is_dir() else "created"
        d.mkdir(parents=True, exist_ok=True)
        print(f"{state:8} {d.relative_to(PROJECT_ROOT)}/")
    if not any(FIRMWARE_INPUT_DIR.glob("*.exe")):
        print(f"next: put the updater EXE into {FIRMWARE_INPUT_DIR.relative_to(PROJECT_ROOT)}/ "
              "(source: see docs/tools.md)", file=sys.stderr)


if __name__ == "__main__":
    main()
