"""Shared filesystem layout for the Creative Zen Touch tools.

All paths hang off PROJECT_ROOT, the repository root: ZEN_ROOT if set, else the current
directory. Run the tools from the repository root (`python3 scripts/NAME.py`).
"""

import os
import sys
from pathlib import Path


def _root():
    env = os.environ.get("ZEN_ROOT")
    if env:
        return Path(env).resolve()
    here = Path.cwd().resolve()
    if not (here / "scripts").is_dir():
        sys.exit(f"run from the repository root (no scripts/ in {here}) or set ZEN_ROOT")
    return here


PROJECT_ROOT = _root()
FIRMWARE_INPUT_DIR = PROJECT_ROOT / "input" / "firmware"
OUTPUT_DIR = PROJECT_ROOT / "output"
BUILD_DIR = PROJECT_ROOT / "build"

VERIFIED_ROUNDTRIP_DIR = (
    OUTPUT_DIR / "roundtrip" / "ZenTouchP4S_PCFW_LF_2_10_05_roundtrip_verified"
)
ROCKBOX_TOOLS_DIR = BUILD_DIR / "rockbox-tools"
