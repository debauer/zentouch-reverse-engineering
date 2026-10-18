# Tools: workflow and reference

All tools are in `scripts/`, run with Python 3 and need no firmware from this repo: you
provide the updater EXE (for example `ZenTouchP4S_PCFW_LF_2_10_05.exe`). Run them from the repository root: `python3 scripts/NAME.py ...`. Every output directory
must be new; a tool never overwrites. All default paths hang off the repository root
(`ZEN_ROOT` overrides it): `input/firmware/` for updaters, `output/` for results, `build/`
for tool builds; see `scripts/project_paths.py`.

Requirements: Python 3, OpenSSL `libcrypto` (Blowfish, loaded with ctypes). Only the
optional cross check needs cmake, make, a C/C++ compiler and a Rockbox source tree.

## Setup

    python3 scripts/init_dirs.py

Creates `input/firmware/`, `output/` and `build/` below the repository root (existing
directories are left alone). In the private main repo, `sh scripts/init_workspace.sh` also
fetches the submodules and creates `tmp/`.

## Keys

The keys are not part of this repo. Pass them as options (`--tl-key`, `--fresc-key`,
`--signing-key`) or set the environment variables. They are the public keys of the Rockbox
source tree (<https://github.com/Rockbox/rockbox>), file
`utils/zenutils/source/zen_crypt/main.cpp`; use the entries of "Zen Touch":

| Variable | Option | Rockbox name | Used for |
| --- | --- | --- | --- |
| `ZEN_TL_KEY` | `--tl-key` | `tl_zt_key` | `TL.enc` (main program), Blowfish |
| `ZEN_FRESC_KEY` | `--fresc-key` | `fresc_key_v1` | `FRESC` (recovery program), Blowfish |
| `ZEN_SIGNING_KEY` | `--signing-key` | `null_key_v1` | archive HMAC-SHA1 (`NULL` chunk) |

Give the string without the terminating NUL; the tools append it. Options win over the
environment. A missing key stops the tool with a message naming the variable.
Tools that need keys: `extract_zen_firmware`, `roundtrip_zen_touch`, `decrypt_zen_touch`,
`encrypt_zen_touch`, `pack_zen_firmware`, `make_zen_update`.

## Getting the updater files

The firmware files are not part of this repo. You can get them from
<https://github.com/brianpipa/CreativeZen/tree/main/CreativeZenTouch>. Put the updater EXE into `input/firmware/` (the default location of the tools) or
pass its path on the command line. Compare the FBOOT size and SHA-256 with the table in
`update_and_flash.md` before relying on results.

## What is inside an updater

The EXE carries a compressed, signed CIFF archive (the firmware). The archive holds the
boot loader `FBOOT`, the encrypted main program `TL.enc` (decrypts to `Jukebox2.jrm`),
the recovery program `FRESC`, the MCU firmware `Pmcu0`, resources (`H*` files) and a
`NULL` chunk with the HMAC-SHA1 over the rest. See `update_and_flash.md` for the layout.

## Order of use

    extract -> (roundtrip) -> decrypt -> export code      reading and analysis
    decrypt -> [your change] -> encrypt -> pack -> make update -> verify      rebuilding

### Reading and analysis

1. `extract_zen_firmware.py UPDATER.exe [-o DIR]`
   Pulls the CIFF archive out of the EXE without running it (it parses the PE sections and
   undoes the XOR/compression) and unpacks it. Writes every entry as a file (`TL.enc`,
   `FBOOT`, `FRESC`, `Pmcu0`, `H*`, `CINF.bin`, `NULL.bin`), `firmware.ciff` (the archive)
   and `manifest.json` (entry order, name fields, XOR key, location of the size field).
   Start here. Default output: `output/extracted/<updater>_extracted`.

2. `roundtrip_zen_touch.py UPDATER.exe [-o DIR]`
   Self test of the whole chain. Extracts, decrypts `TL.enc` and `FRESC`, encrypts them
   again, repacks the archive, and checks that every byte and every HMAC matches the
   source. Writes `original/` (decrypted `Jukebox2.jrm`, `FRESC.decrypted.bin` and the
   other entries), `reextracted/`, `rebuilt.ciff` and `report.json` ("passed"). Run it
   once per updater: if it passes, the codecs and keys are right for that version. It
   also is the easiest way to get `Jukebox2.jrm`.

3. `decrypt_zen_touch.py INPUT -o OUTPUT [-m TL|FRESC]`
   Decrypts one entry: Blowfish with the entry key, then (for `TL`) the CENC
   decompression; validates the CODE image. `-m TL` for `TL.enc` (default), `-m FRESC` for
   `FRESC`. Use it on a file from step 1 when you do not need the full roundtrip.

4. `export_zen_code.py [JUKEBOX2.jrm] [-o DIR]`
   Splits a decrypted CODE image into its load records (`block_NN_<address>.bin`), checks
   the record checksums and writes `manifest.json` and `memory_map.txt`. The blocks are
   the input for disassembly (see `c55x_asm_roundtrip.md`) and for the c55x_emulator.
   Default input: the roundtrip's `original/Jukebox2.jrm`.

### Rebuilding an update (experimental)

Nothing here was tested on a device. A wrong update can make the player unbootable; the
recovery path is not fully understood (see `update_and_flash.md`).

5. Change the decrypted `Jukebox2.jrm` (your own tool; the CODE header and record
   checksums must stay consistent).

6. `encrypt_zen_touch.py JUKEBOX2.jrm -o TL.enc [-m TL|FRESC]`
   Inverse of step 3: validates the CODE image, CENC-encodes and Blowfish-encrypts it.

7. `pack_zen_firmware.py DIR -o OUT.ciff`
   Builds a signed CIFF archive from a directory like the one from step 1 (put your new
   `TL.enc` there). `firmware.ciff` in that directory only supplies the entry order and
   name fields; payloads come from the individual files and the archive HMAC is
   recomputed.

8. `make_zen_update.py -u UPDATER.exe -f OUT.ciff -o NEW.exe`
   Inserts the archive into a copy of the original updater EXE. If the compressed archive
   is larger than the original slot, the EXE gets a new `.firm` section and the references
   are relocated (the method of Rockbox `update_patch`). Defaults: updater
   `input/firmware/ZenTouchP4S_PCFW_LF_2_10_05.exe`, archive from the verified roundtrip.

### Verification

9. `build_rockbox_zencrypt.sh [BUILD_DIR]`
   Builds the native reference tools of Rockbox `zenutils` (`zen_crypt`,
   `firmware_extract`, `update_extract`) from a Rockbox source tree (`ROCKBOX_ROOT`,
   default `<project root>/rockbox`; `CC`, `CXX`, `JOBS` optional). Output default:
   `build/rockbox-tools`. Needs cmake and make.

10. `verify_rockbox_zencrypt.py [--roundtrip DIR] [--tool PATH] [--extractor PATH]`
    Independent check of a roundtrip directory against the native Rockbox tools, using
    only the Python standard library for the comparison. Run after steps 2 and 9.

11. `verify_zen_update.py [-u UPDATER.exe] [-f OUT.ciff] [--tools-dir DIR] [-o DIR]`
    Extracts a generated update EXE with the native `update_extract` and `zen_crypt` and
    compares it with the archive you intended to ship. Run it on every EXE from step 8
    before using it.

## Library modules

- `zen_cenc.py`: CENC compression codec (port of Rockbox `cenc.cpp`).
- `zen_code.py`: CODE image containers and their load records with checksums.
- `zen_pe.py`: PE section handling for extraction from and insertion into the updater EXE.
- `project_paths.py`: input, output and build directories.

## Typical sessions

Read only (analysis):

    python3 scripts/roundtrip_zen_touch.py input/firmware/ZenTouchP4S_PCFW_LF_2_10_05.exe
    python3 scripts/export_zen_code.py

Rebuild an unchanged update and check it:

    bash scripts/build_rockbox_zencrypt.sh
    python3 scripts/make_zen_update.py
    python3 scripts/verify_zen_update.py

## License

The codecs and keys follow Rockbox `zenutils` (GPL-2.0-or-later, Rasmus Ry); the files
carrying an SPDX header are GPL-2.0-or-later and the rest of the tools should be treated as derived
from it.
