# zentouch-reverse-engineering

Tools and findings for the Creative Zen Touch (Jukebox2, TI C55x DSP). It contains no
firmware, no Creative or Microsoft code and no manuals; bring your own update EXE (available from
https://github.com/brianpipa/CreativeZen/tree/main/CreativeZenTouch).

- `scripts/`: update EXE and firmware container handling (extract, pack, decrypt,
  encrypt, rebuild update, export code blocks) and the Rockbox `zencrypt` cross check.
- `tests/`: unit tests. Run with `python3 -m unittest discover -s tests -t .`.
- `python3 scripts/init_dirs.py` creates the default working directories first.
- `docs/example.md`: complete run with all commands, file names and hashes.
- `docs/tools.md`: **start here**, workflow and reference of every tool in order of use.
- `docs/`: update and flash layout, assembler round trip, hardware notes of the player.

The C55x emulator lives in its own repository (c55x_emulator).

Run the tools from the repository root. The working directories `input/`, `output/` and
`build/` live below it (or below `ZEN_ROOT`); see `scripts/project_paths.py`.
The firmware keys are not in this repo: pass them as options or via `ZEN_TL_KEY`,
`ZEN_FRESC_KEY`, `ZEN_SIGNING_KEY` (public Rockbox keys, see `docs/tools.md`, section Keys).
