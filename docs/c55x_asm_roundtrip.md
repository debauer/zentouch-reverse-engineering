# C55x Disassemble/Reassemble Roundtrip

Date: 2026-10-08

Question: can the decrypted main program (`Jukebox2.jrm`, the 15 CODE records in
`output/code/Jukebox2_code_blocks`) be disassembled into assembler source and
reassembled into byte-identical payloads?

**Result: yes.** All 15 blocks rebuild byte-identically. The SHA256 of every
rebuilt payload matches `sha256` in `output/code/Jukebox2_code_blocks/manifest.json`
(15/15). This check was done separately from the script: the final generated
sources were reassembled in a fresh directory and hashed.

"Byte-identical" here means: parts of the source are not symbolic instructions
but `.byte` fallbacks (see below). The roundtrip proves the toolchain path and
the disassembly are lossless; it does not yet give freely editable source.

## Toolchain

| Tool | Role |
| --- | --- |
| `build/ti-cgt-c5500-4.4.1/bin/dis55` | COFF disassembler, used with `-qq -r -g` |
| `build/ti-cgt-c5500-4.4.1/bin/asm55` | **Algebraic** assembler, used with `--output_all_syms` |
| `build/ti-cgt-c5500-4.4.1/bin/lnk55` | Links `.text` at the original record address |
| `build/ti-cgt-c5500-4.4.1/bin/hex55` | `-b --romwidth=8 --memwidth=8` extracts raw bytes |
| `build/ti-cgt-c5500-4.4.1/bin/nm55` | `-a` reads per-instruction label addresses of the rebuild |

radare2 (`rasm2 -a tms320 -c c55x`) only disassembles C55x; assembling fails
with `Cannot assemble`. It is therefore not usable for the roundtrip. The TI
`dis55` output is also cleaner (absolute branch targets, consistent lengths,
fewer `invalid` decodes than the linear rasm2 export in
`output/asm/zen-touch-main.c55x.asm`).

## Usage

```sh
python3 scripts/roundtrip_c55x_asm.py \
  output/code/Jukebox2_code_blocks/block_07_00800000.bin 0x800000 \
  --work /path/to/workdir
```

Optional: `--length N` (only the first N bytes), `--max-iter N` (default 50;
blocks 08, 13, 14 need up to 21 iterations, use `--max-iter 100`).

All blocks:

```sh
mkdir -p work
find output/code/Jukebox2_code_blocks -name 'block_*.bin' | sort | \
  xargs -P 8 -I{} sh -c 'f=$(basename {} .bin); \
  python3 scripts/roundtrip_c55x_asm.py {} 0x${f##*_} --work work/$f --max-iter 100 > work/$f.log 2>&1'
```

Runtime for all 15 blocks with 8 parallel jobs: a few minutes.

Outputs in the work directory:

| File | Content |
| --- | --- |
| `wrap.asm/.out` | Raw block wrapped as `.byte` into a COFF `.text` at the record address |
| `re.asm` | Final generated assembler source (byte-identical when assembled) |
| `re.bin` | Rebuilt bytes (plus one linker padding byte, see below) |
| `raw.txt` | Instructions that had to be kept as `.byte`, with address, encoding, text |

Unit tests for source generation (no TI tools needed):

```sh
PYTHONPATH=scripts python3 -m unittest tests.test_c55x_asm_roundtrip
```

## Method

1. Wrap the raw payload as `.byte` lines into `.text`, assemble with `asm55`,
   link at the record address, verify the wrapper reproduces the payload.
2. Disassemble with `dis55 -qq -r -g` (algebraic syntax, compiler status-bit
   assumptions).
3. Validate every disassembled item against the blob: address monotonic, inside
   the block, bytes equal to the blob. Anything else, plus bytes `dis55` does not
   cover, becomes a raw `.byte` item taken from the original payload.
4. Emit source with a label `L_<addr>:` before every item. `goto`, `call`,
   `dgoto`, `dcall` targets inside the block are replaced by these labels;
   targets outside the block stay absolute (`#0x...`). Instructions whose
   original encoding is an absolute P24 `goto`/`call` (opcode `0x6a`/`0x6c`)
   keep the `#0x...` constant even for in-block targets, so `asm55` emits the
   same absolute form.
5. Assemble/link/extract. Then iterate:
   - assembler error on an instruction line: that instruction becomes raw;
     an error on a raw line or a `}` inside a repeat block makes the innermost
     enclosing `blockrepeat {` / `localrepeat {` opener raw (its `}` is dropped);
   - otherwise read rebuilt label addresses via `nm55 -a`; instructions with a
     different length become raw first, then (once the layout matches)
     instructions with the same length but different bytes;
   - stop when the rebuilt payload equals the original.

Mode directives used for the generated source:
`.mmregs`, `.cpl_on`, `.arms_on`, `.c54cm_off` (matching `dis55 -r`).

## Results

| Block | Address | Bytes | Instructions | Symbolic | Raw fallback | Raw % | asm_error | length | encoding | Iter |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 00 | `0x00000100` | 5472 | 1921 | 1317 | 604 | 31.44 | 295 | 70 | 239 | 4 |
| 01 | `0x000088e8` | 114 | 51 | 48 | 3 | 5.88 | 3 | 0 | 0 | 4 |
| 02 | `0x00010000` | 842 | 280 | 277 | 3 | 1.07 | 1 | 2 | 0 | 3 |
| 03 | `0x00012814` | 7612 | 2320 | 2110 | 210 | 9.05 | 200 | 6 | 4 | 8 |
| 04 | `0x00020000` | 12922 | 4088 | 2476 | 1612 | 39.43 | 1198 | 154 | 260 | 13 |
| 05 | `0x0003064c` | 14408 | 4574 | 4570 | 4 | 0.09 | 1 | 3 | 0 | 3 |
| 06 | `0x00039800` | 15452 | 5204 | 4920 | 284 | 5.46 | 11 | 14 | 259 | 4 |
| 07 | `0x00800000` | 218152 | 67342 | 65306 | 2036 | 3.02 | 1770 | 264 | 2 | 7 |
| 08 | `0x00840000` | 39212 | 12925 | 885 | 12040 | 93.15 | 11842 | 86 | 112 | 21 |
| 09 | `0x00860000` | 131068 | 36612 | 36569 | 43 | 0.12 | 5 | 38 | 0 | 5 |
| 10 | `0x00888080` | 106018 | 34425 | 9405 | 25020 | 72.68 | 24680 | 102 | 238 | 15 |
| 11 | `0x008c0000` | 23426 | 7635 | 7635 | 0 | 0.00 | 0 | 0 | 0 | 1 |
| 12 | `0x008e0000` | 127106 | 38761 | 32991 | 5770 | 14.89 | 3793 | 484 | 1493 | 13 |
| 13 | `0x00900000` | 126226 | 39451 | 30135 | 9316 | 23.61 | 8494 | 426 | 396 | 18 |
| 14 | `0x00920000` | 161310 | 50681 | 45743 | 4938 | 9.74 | 3953 | 223 | 762 | 19 |

"Instructions" counts items `dis55` decoded (in data regions these are data
bytes decoded as instructions). "asm_error / length / encoding" is the reason
an item was moved to raw. Before keeping absolute `goto`/`call` constants
(step 4) the total was 65,295 raw items (21.32 %), now 61,883 (20.21 %);
block 07 went from 3,504 to 2,036, block 09 from 455 to 43, block 11 from 226 to 0.

The raw percentage is a useful code/data indicator:

- mostly code: 02, 05, 06, 07, 09, 11 (below 6 %), also 03, 14
- mixed: 00, 04, 12, 13
- mostly data: 08 (93 %, consistent with the LCD/RTC driver table at
  `0x00847b00`) and 10 (73 %)

This classification is provisional; it is a statistic, not a verified code/data map.

## Findings and pitfalls

### masm55 vs. asm55

- `asm55` is the **algebraic** assembler (`AR1 = T0 - #1`), `masm55` the
  **mnemonic** one (`SUB #1,T0,AR1`). Feeding mnemonic source into `asm55`
  gives `[E0000] parse error` on every line.
- `masm55` moves data directives (`.byte`, `.field`) used inside `.text` into a
  separate subsection `.data:.text`. Raw bytes can therefore not be placed
  between instructions. `asm55` keeps `.byte` inline. This is why the roundtrip
  uses algebraic syntax (`dis55 -g`).

### Branch targets must be labels

`dis55` prints targets as absolute constants (`goto #0x800056`). Reassembled
that way, the assembler must use the absolute P24 form:
`04294d` (relative) becomes `6829800056`. With labels it selects the short
relative forms the original uses.

### Encodings the assembler does not reproduce

The original toolchain did not always pick the shortest encoding. Most common
cases in block 07 (from `raw.txt`):

| Count | Example | Cause |
| ---: | --- | --- |
| 140 | `76fffd58  T1 = #-3` | long k16 form; `asm55` picks the 2-byte form `3e35` |
| 626 / 250 / 171 | `call #0x815031`, `goto`, `return` | mostly knock-on: assembler errors in a decoded repeat context or next to raw data |

Absolute P24 calls (`6c801874  call #0x801874`; at least 2,215 raw items in
block 07 before the change, the three largest categories) are no longer a fallback: they are kept as constants (see
Method, step 4). Confirmed with `cl55`: calls to symbols outside the
compilation unit are encoded as absolute `6c...`, calls to functions in the
same section as relative `08...`, exactly the pattern in the firmware.
The long immediates (`T1 = #-3` as `76fffd58`) are not reproduced by `cl55`
4.4.1; their origin is not established.

### dis55 quirks in data regions

- Addresses can go backwards (block 08: `849926` followed by `84192e`).
- The last decoded instruction can extend past the end of the block (block 03).
- Printed bytes can disagree with the blob (block 12 at `0x8e5649`: printed
  `ff`, blob `e5`; block 14 at `0x941e27`).
- Output can contain non-UTF-8 bytes (block 04); the script reads it with
  `surrogateescape`.

All of these are handled by validating each item against the blob (step 3).

### Repeat blocks

`dis55 -g` prints `blockrepeat {` / `localrepeat {` (also as the second half of
a parallel pair, `... || blockrepeat {`) and the closing `}` on its own line.
Data decoded as `while (...) repeat` makes the following instruction illegal
(`[E0800] This instruction is illegal inside a Conditional Repeat Single loop`);
the iteration moves those to raw.

### Linker padding

`lnk55` pads `.text` with one `0x20` (NOP) byte. The rebuilt `.bin` is
therefore one byte longer than the payload; only the first `payload_size_bytes`
are compared. When repacking into the CODE container, use exactly that length.

### Silicon remarks

`asm55` emits remarks such as `[R5573]` (CPU_43), `[R5668]` (CPU_88) and
`[R5106] Not supported on C55x 1.0 silicon`. They do not change the encoding.
No `-v` silicon revision was set; the defaults of `asm55` and `dis55` were used.

## Limitations

- **Not freely editable yet.** Raw `.byte` fallbacks contain position-dependent
  encodings (relative branches). Any change that moves code invalidates them.
  Edits that keep the layout (same-length patches) are safe.
- **Per-block only.** Every block is built separately. Cross-block references
  (e.g. `call #0x013892` from block 07 into block 03) stay absolute numbers.
- **Status bits not verified.** The source uses the C compiler assumptions
  (`dis55 -r`: CPL=1, ARMS=1, C54CM=0). For the byte comparison this does not
  matter, but the *meaning* of the disassembly depends on the real CPU mode on
  the device, which has not been confirmed.
- **Linear sweep.** Decoding is linear; no control-flow-based code/data
  separation. Function boundaries are not determined.
- Only `Jukebox2.jrm` was tested. `FBOOT` and `FRESC`
  (`output/code/FRESC_decrypted_code_blocks`) were not tested.

## Development notes

Dead ends during development, kept to avoid repeating them:

1. Mnemonic syntax with `masm55`: failed because of `.data:.text` relocation of
   raw bytes.
2. Aligning rebuild and original by re-disassembling the rebuild and matching
   by instruction index: breaks as soon as a length differs (linear sweep
   desyncs). Replaced by one label per item plus `nm55 -a` (local labels only
   appear with `asm55 --output_all_syms`).
