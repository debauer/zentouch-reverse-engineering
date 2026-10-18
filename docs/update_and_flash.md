# Firmware Update Path and NOR Flash

How the main program (`Jukebox2.jrm`) applies a firmware update and what it writes where:
files on the hard disk, areas in the NOR flash, and the MCU firmware. Everything here comes
from the analysis of firmware 2.10.05:

- `update_apply_ciff` (0x8f8b72)
- driver `flash` (0x8275f1..0x82847f, 0x828bba..0x828ea2)

Nothing in this document was tested on a device.

## Overview

1. The PC sends the update as an MTP object of format 0xb802. `mtp_recv_upgrade` stores it
   as `upgrade.jrm` and checks its last 28 bytes (the `NULL` chunk with the HMAC-SHA1 over
   the rest); only then it calls
   `update_apply_ciff(path)`.
2. `update_apply_ciff` walks the chunks of the archive and writes each one to its target.
3. The archive file is deleted afterwards with `file_wipe` (clusters overwritten), whether the
   chunks succeeded or not.

## PC Updater Wrapper

The three available Creative Windows updaters were extracted without executing them:

| Updater | FBOOT size | FBOOT SHA256 | Archive HMAC |
| --- | ---: | --- | --- |
| `ZenTouchP4S_PCFW_LF_2_10_05.exe` | 21,524 | `cf2511e931e595a30be78973064de20bf473c734591a71e1b10c5fb85d590072` | verified |
| `ZenTouchP4S_PCFW_LB_2_11_01.exe` | 21,524 | `bcc72c12471c02b1509b5d8c9eebd8ef2adb9b15a10f01b7e444be1fd2df9d4b` | verified |
| `ZenTouch_PCFW_L4_1_01_03.exe` | 16,220 | `fdfc603582965ce49bd72541c8d76b1bfaefbbe7adff5c98ba1de15755872cbc` | legacy archive, no `NULL` HMAC |

The updater executable contains a compressed CIFF archive in its PE `.data` section. The
wrapper algorithm is the Rockbox-compatible loop in `rockbox/utils/zenutils/source/shared/updater.cpp`:
the embedded key is transformed with `(byte - 1) | 0x80`, XORed over the whole payload, and the
result is zlib-decompressed. It does not process `FBOOT` or `FRESC` separately. The extracted
`FBOOT` bytes are exactly the `DATA 'F'` payload later passed to the device's `flash0` writer.

This rules out the PC updater wrapper as the location of a separate FBOOT cipher/key. The
remaining candidates are a format/packing scheme in FBOOT itself or a transformation performed
by the boot ROM/bootloader after the `BOOT` NOR area is read. The updater XOR keys are not FBOOT
keys, and the archive signing key is only the CIFF/upgrade HMAC key.

### Offline FBOOT block analysis

`scripts/analyze_fboot.py` was run against the three extracted `FBOOT` images. It treats the
first `0x30` bytes and final 4 bytes as framing and analyzes the middle region:

| Image | Body bytes | Body entropy | Most common 8-byte block | Count |
| --- | ---: | ---: | --- | ---: |
| LF 2.10.05 | 21,472 | 7.534273 | `9977e7e31d1eb5d5` | 596 |
| LB 2.11.01 | 21,472 | 7.526347 | `37f136897e56d7e8` | 596 |
| L4 1.01.03 | 16,168 | 7.215020 | `8c66c613454b274b` | 596 |

All three have the same 4-byte prefix `08a50000`, are divisible into 8-byte blocks, and have
zero common 8-byte blocks between firmware versions. The repeated block is not one contiguous
padding region: the first run is 66 blocks, followed by shorter runs and later isolated
occurrences at matching positions between LF/LB. The repeated values themselves differ by
version. LF/LB have the same repeated-block position mask for all 2,684 blocks; L4 matches it
for 2,011 of its 2,021 blocks. This is consistent with a shared block-oriented layout with
version-dependent encoding or structured filler, but does not prove ECB encryption.

Decrypting the full body and the region after the leading 66-block run with all known TL/FRESC
Blowfish keys and the five existing IV layouts produces random-looking output: no recognizable
C55x vector, boot table, code, or string appears. The known-key tests therefore remain negative.
A direct scan also finds none of the known C55x addresses `0x100`, `0x039dc0` or `0x400000` in
big-endian, little-endian, or swapped-16-bit byte order. The FRESC strings contain only the
generic area name `BOOT`; neither FRESC nor the Windows updaters expose a separate FBOOT decoder
or key. The next useful evidence is therefore a NOR dump or passive boot-bus/JTAG trace; a key
search without a known cipher boundary is not justified.

The recovery image `FRESC` contains a copy of the same update parser (around 0x862268) and
its own copy of the flash driver (write function around 0x81427f). Recovery can therefore
apply a complete CIFF update by itself. How recovery mode is entered is still open.

### Recovery Mode (FRESC)

Strings and code of the decrypted FRESC image (`output/code/FRESC_decrypted_code_blocks`):

| Menu entry | Confirmation / messages | What the code does (as far as read) |
| --- | --- | --- |
| Clean Up | "Disk cleanup will be performed. Continue?", "Scan Disk...", "Cleaning..." | names the database files `fhandle.db`, `btree.db`, `attrs.db`, `list.qm`, `pm.cfg`, `pm.cbk` |
| Format All | "All data will be gone. Format all?", "Formatting..." | |
| Reload Firmware | "Firmware will be erased. Reload it via USB. Continue?", "Erasing Firmware...", "Start firmware update now!" | works on the disk file systems `minifs` and `cfs` (0x860821..0x86086a), not on the NOR; then waits for an update over USB (device name "rescue") |
| Reboot | | |

The selection of FRESC at power-up is done by the boot loader (BOOT), not by the main
program; the main program contains no code that requests recovery mode. The manual only
documents the reset hole and says to reset the player after an update (the firmware does
not restart itself).

## CIFF chunks

Every chunk starts with an 8-byte header: four-character id and size in bytes (big endian).
The file data is read two bytes per 16-bit word. Names in sub-headers are 16-bit characters.

| Chunk | Sub-header | Target |
| --- | --- | --- |
| `CIFF` | none | archive root; anything else at the start aborts (file is closed and deleted) |
| `CINF` | 96 bytes: device name | compared with "Creative Zen Touch" (ignoring case) |
| `DATA`, type `'H'` (0x48) | 32 bytes: type word, file name | file `<name>` on the disk, opened with mode "w" |
| `DATA`, type `'F'` (0x46) | 32 bytes: type word, area name (4 characters) | NOR area `<name>` through device `flash0` |
| `CODE` | 4 more bytes after the chunk header | file `jukebox2.jrm`: 12 bytes (chunk header + those 4 bytes), then the data |
| `0xA9 'T' 'L' ' '`, `CENC` | none | file `jukebox2.jrm`: 8-byte chunk header, then the data |
| `EXT0` | 24 bytes: type word, device name | only device "mcu0": MCU request 23 (`mcu_fw_update`) |
| `_PIC` | none | device "mcu0", MCU request 23 |
| other | | skipped (seek over the chunk) |

The main firmware is therefore a file on the hard disk (`jukebox2.jrm`, file system minifs),
not a NOR area.

The official update 2.10.05 (`output/extracted/ZenTouchP4S_PCFW_LF_2_10_05_extracted`)
contains, in this order: `CINF`; `DATA 'F'` BOOT (21,524 bytes) and RESC (238,944 bytes);
`0xA9 'T' 'L' ' '` (the encrypted main firmware); `DATA 'H'` jukebox2.jrs, unicjkl.nft,
splash.jbm, devicon.ico, devlogo.png; `EXT0` mcu0 (2,956 bytes); the `NULL` signature
chunk. Every official update thus rewrites the NOR areas BOOT and RESC.

### DATA 'F' in detail

1. `dev_open("flash0", 2)`; if it fails the chunk is dropped.
2. Look up the area: `flash_op1` with cmd 0 and the name built from the four characters.
3. Write: `flash_op2` with key `"8888"`, cmd 0, the looked-up entry and
   `entry.length = chunk data size`. The address, offset and reserved size come from the
   existing table entry.
4. Result 0 counts as success, anything else shows an error screen.

If the lookup fails, the entry fields other than the name are left uninitialized (stack).

### Checks the parser does not do

- A wrong `CINF` name only shows an error screen; the parser then seeks past the chunk
  once more and continues with the next header.
- Chunk sizes are not checked against the file size. `heap_alloc` is not checked for
  `DATA` and `CODE`; `file_open` of the target file is not checked.
- `_PIC` calls the device close operation even when `dev_open("mcu0")` failed.
- The only integrity protection is the HMAC check before, in `mtp_recv_upgrade`.

## NOR flash

16-bit NOR at data word address 0x200000 (CE1). The chip answers the JEDEC software ID with
manufacturer 0xbf (SST) and device 0x2780, 0x2781 or 0x2782. The part on the board is an
SST39VF400A (marking, see `hw.md`): device 0x2780, 256K words, so the chip ends at word
0x23FFFF; the default layout below ends at 0x230000. The size is read from CFI word 0x27 and
limited to 1 MiB. Commands use the
unlock sequence 0xaa @ 0x5555, 0x55 @ 0x2aaa (written as 0xaaaa / 0x5555):

| Command | Code | Notes |
| --- | --- | --- |
| Software ID | 0x90 | probe at init |
| CFI query | 0x98 | 40 words from 0x200010 |
| Exit / reset | 0xf0 | |
| Word program | 0xa0 | toggle-bit polling (DQ6) |
| Sector erase | 0x80, 0x30 | 2048 words |
| Block erase | 0x80, 0x50 | 32K words |
| Chip erase | 0x80, 0x10 | fixed 100-tick wait, no polling |

### Default layout

From the default table at data word 0x423df6 (written by `flash_format`). Addresses are
word addresses, sizes are bytes.

| Area | Address | Reserved | Use |
| --- | --- | --- | --- |
| `BOOT` | 0x200000 | 32 KiB | boot loader (`FBOOT` in the update) |
| `CONF` | 0x204000 | 16 KiB | WMDRM data (written by block 13); checked for at least 16 KiB |
| `TOC0` | 0x206000 | 8 KiB | ring of table sectors (`TSIG` header at 0x206000) |
| `PFM1` | 0x207000 | 8 KiB | settings (`settings_save_pfm1`) |
| `RESC` | 0x208000 | 320 KiB | recovery image (`FRESC` in the update) |

### Area table

The table occupies one 2048-word sector. Entry 0 is the header (`"TSIG"`, then the word
address of the ring); entries 1..n describe the areas; an entry whose name is 0xffffffff
ends the list. `flash_init` searches the chip in sector steps for `"TSIG"`.

| Word | Field | Meaning |
| --- | --- | --- |
| 0 | name | four characters, first in the high byte |
| 2 | addr | word address |
| 4 | length | bytes of data |
| 6 | alloc | bytes reserved; must be >= length |
| 8 | sum | 16-bit sum of the data words |
| 10 | off | data offset in words from addr |
| 12..15 | | reserved |

The table is log-structured: every write stores the complete table in the next sector of
the `TOC0` ring and then erases the old sector. The driver keeps `g_flash_end` (first free
word) and `g_flash_free` (free bytes) from the sum of all `alloc` fields.

### Driver operations

`flash_op1` (needs a working chip and table):

| cmd | Action |
| --- | --- |
| 0 | copy the entry for a name (result 2 if not found) |
| 1 | free bytes |

`flash_op2`:

| cmd | Action |
| --- | --- |
| 0 | write an area (see below) |
| 1 | delete an area; BOOT, CONF, TOC0, RESC and LAUN are refused (4101) |
| 2 | format: chip erase, write back the first CONF sector and the default table |
| 4096 | list all entries with computed sums, plus a sum over the used area |

Error codes: 4096 no chip, 4097 no table, 4098 bad table entry, 4099 sum mismatch after
programming, 4100 no space, 4101 refused.

### Writing an area (`flash_write`)

- The request must carry the key `"8888"` in its first long, otherwise 4101. `TOC0` cannot
  be written.
- New name: the area is appended at `g_flash_end`; `alloc` must be smaller than the free
  space.
- Existing name: if `alloc` changes, all following areas are moved sector by sector
  (`flash_shift`: copy, then erase the source). Then the old data range is erased and the
  new data is programmed at the address given in the request.
- After programming, the sum is computed again from the flash; a mismatch returns 4099.
- Finally the table is written to the next ring sector and the old one is erased.
- Name `"8888"` as well: raw mode. The whole chip is erased and the data is programmed from
  0x200000; the sum is read back and stored in the request on a mismatch. A `DATA 'F'`
  chunk named "8888" would reach this path through the update parser (not tested; the
  table lookup fails, so the expected sum comes from uninitialized stack).

### Who writes the NOR

| Caller | Area | When |
| --- | --- | --- |
| `update_apply_ciff` (0x8f8b72) | areas named by `DATA 'F'` chunks (BOOT, RESC) | firmware update |
| `settings_save_pfm1` (0x833baa) | PFM1 | saving settings; type-4 records, data offset moves by 2048 words per save (wraps within the area) |
| WMDRM (0x900268, block 13) | CONF | DRM store |

Read-only users: `settings_find_pfm1` (0x8340fb), `flash_conf_ok` (0x8754a0), WMDRM
(0x9001f3). No caller of `flash_op2` cmd 2 (format) was found among the code that opens
`flash0`; an indirect call through a device handle obtained elsewhere is not excluded.

## Consequences for own updates

- An archive with only `DATA 'H'` chunks and/or a `CODE` / `CENC` / `0xA9 'T' 'L' ' '`
  chunk writes files on the hard disk only; the NOR is not touched as long as there is no
  `DATA 'F'` chunk. Whether the device accepts an update without BOOT/RESC chunks is not
  tested.
- `DATA 'F'` BOOT replaces the boot loader. A bad image there, or a raw `"8888"` chunk,
  can make the device unbootable; recovery depends on `RESC` and on how recovery mode is
  entered (open).
- `flash_op2` cmd 2 erases the chip including BOOT and does not rewrite BOOT. Whether the
  boot sectors are hardware-protected is unknown.
- The archive must carry a valid HMAC-SHA1 trailer; `scripts/pack_zen_firmware.py` builds
  one.

