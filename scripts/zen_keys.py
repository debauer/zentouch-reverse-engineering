"""Firmware keys. They are not part of this repository: pass them as options or set the
environment variables. The values are the public ones of the Rockbox source tree
(utils/zenutils/source/zen_crypt/main.cpp, see docs/tools.md, section Keys).

    ZEN_TL_KEY       main program (TL.enc), Blowfish   (Rockbox: tl_zt_key)
    ZEN_FRESC_KEY    recovery program (FRESC), Blowfish (Rockbox: fresc_key_v1)
    ZEN_SIGNING_KEY  archive HMAC-SHA1 (NULL chunk)    (Rockbox: null_key_v1)

Give the string without the terminating NUL; it is appended (the firmware uses strlen + 1).
"""

import os

NAMES = {"tl": ("ZEN_TL_KEY", "--tl-key"), "fresc": ("ZEN_FRESC_KEY", "--fresc-key"),
         "signing": ("ZEN_SIGNING_KEY", "--signing-key")}
_given = {}


def add_arguments(parser):
    for name, (env, option) in NAMES.items():
        parser.add_argument(option, metavar="KEY", help=f"{name} key (default: ${env})")


def configure(args):
    """Remember the keys given as options (they win over the environment)."""
    for name, (_, option) in NAMES.items():
        value = getattr(args, option[2:].replace("-", "_"))
        if value is not None:
            _given[name] = value


def get(name):
    """-> key bytes with the terminating NUL; SystemExit with a hint if the key is unset."""
    env, option = NAMES[name]
    value = _given.get(name) or os.environ.get(env)
    if not value:
        raise SystemExit(f"{name} key missing: set {env} or pass {option} "
                         "(public Rockbox key, see docs/tools.md)")
    return value.encode("latin-1") + b"\0"
