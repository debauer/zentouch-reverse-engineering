"""Tests run from the repository root: python3 -m unittest discover -s tests -t ."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

# dummy keys: the tests build their own archives and never need the real ones
for _name in ("ZEN_TL_KEY", "ZEN_FRESC_KEY", "ZEN_SIGNING_KEY"):
    os.environ.setdefault(_name, "test-" + _name.lower())
