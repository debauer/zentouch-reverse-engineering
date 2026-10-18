# Board Chips

One line per chip marking found on the boards (as read from the parts), then what is known
about it, how it fits the firmware analysis and the emulator, and what is open. Sources are
listed per chip; distributor and datasheet-mirror pages are marked as such.

| Marking on the board | Part | Function |
|---|---|---|
| TMS320DA255ZHH | TI TMS320DA255, ZHH package | main processor (C55x DSP) |
| 39VF400A | SST39VF400A | NOR flash, 4 Mbit (256K x 16) |
| 0424PR V54C3128164vbt7 | Mosel Vitelic V54C3128164V... | SDRAM, 128 Mbit (8M x 16) |
| p43a8 FST16211 | Fairchild FST16211 | 24-bit bus switch |
| synoptics t1005 0313 c64968-06 | Synaptics T1005 | touch pad controller |

## TMS320DA255ZHH

- TI "DA25x" audio processor family. No public datasheet: community sources say TI gave the
  documentation only under NDA; TI's site never listed the DA25x datasheets.
- The Creative Xmod uses the same marking ("TMS320 DA255ZHH"); the Rockbox wiki lists
  "DA255GHH" for the Zen Touch (GHH / ZHH are BGA package codes, PGE is the 144-pin LQFP
  variant sold by distributors).
- EE Times describes the sibling TMS320DA250 as TI's first chip with integrated USB, for
  internet audio devices. Distributor data for TMS320DA255PGE: 16-bit fixed point,
  200 MHz, 128 KB RAM, 1.65 V core (distributor listing, not a TI document).
- A wiki quote calls the DA25x "ARM processors with a C55x core". That does not match this
  firmware: Jukebox2 and FRESC are pure C55x code, no ARM code was found.

Fit with the firmware / emulator:
- The DSP/BIOS chip constant is 5509 and every resolved I/O port matches the VC5509A
  (chip ID block, I/O 0x3800..0x3804). The DA255 is therefore most likely a VC5509A derivative;
  the emulator models the VC5509A peripherals.
- The VC5509 has an on-chip USB device (TI: "USB 2.0 full-speed", 12 Mbit/s, 2001), but
  the firmware's usb0 driver talks to a controller on CE1 at data word 0x282000
  (modelled by the c55x_emulator USB stub). Which chip that is remains open.

Sources: [Xmod teardown blog](http://varunasingh.blogspot.com/2008/03/dismantling-creative-xmod.html),
[dsprelated c55x thread](https://dsprelated.com/showthread/c55x/1187-1.php),
[TMS320 (Wikipedia)](https://en.wikipedia.org/wiki/TMS320),
[Octopart TMS320DA255PGE](https://octopart.com/part/texas-instruments/TMS320DA255PGE) (distributor),
[datasheetarchive TMS320DA255](https://datasheetarchive.com/TMS320DA255-datasheet.html) (distributor list),
[Rockbox wiki CreativeZenTouch](https://www.rockbox.org/wiki/CreativeZenTouch.html),
[C5509 USB 2.0 full-speed press release](https://www.lightwaveonline.com/optical-tech/electronics/article/16659778/texas-instruments-dsp-achieves-usb-20-fullspeed-certification).

## 39VF400A

- SST (now Microchip) SST39VF400A: 4 Mbit parallel NOR flash, 256K x 16, 2.7..3.6 V,
  70 ns. Manufacturer id 0x00BF, device id 0x2780 (software ID: 0xAA @ 0x5555, 0x55 @
  0x2AAA, 0x90 @ 0x5555; exit with 0xF0). Also listed for the Zen Touch in the Rockbox
  wiki ("SST 39VF400A 70-4C-EK").
- Sector erase 2K words, block erase 32K words (SST39VF200A/400A/800A family).

Fit with the firmware / emulator:
- The firmware's flash driver accepts device ids 0x2780..0x2782;
  0x2780 is this part, so the NOR part number is identified (see
  `update_and_flash.md`).
- The default NOR layout (BOOT 0x200000, CONF 0x204000, TOC0 0x206000, PFM1 0x207000,
  RESC 0x208000 with 320 KiB) ends at word 0x230000 and fits the 256K words
  (0x200000..0x23FFFF).
- The emulator models this part (c55x_emulator `nor.py`: id 0x2780, 256K words).

Sources: SST datasheet SST39LF/VF200A/400A/800A, via mirrors
([alldatasheet](https://html.alldatasheet.com/html-pdf/132398/SST/SSY39L400704IU1/538/8/SSY39L400704IU1.html)),
[Digi-Key SST39VF400A](https://www.digikey.com/en/products/detail/microchip-technology/SST39VF400A-70-4I-MAQE/2651283).
Not checked against the current Microchip datasheet.

## 0424PR V54C3128164vbt7

- Mosel Vitelic V54C3128164V family: 128 Mbit SDRAM, 8M x 16 (the family also has x8 / x4
  parts), single 3.3 V, LVTTL, speed grades 6 / 7 / 8. The trailing "T7" most likely is
  TSOP-II package and speed grade 7 (the naming scheme has BGA and TSOP variants); not
  confirmed by an original Mosel datasheet. "0424" reads as a date code (2004, week 24).
- The Rockbox wiki lists a Samsung K4S281632F-TC75 (also 128 Mbit, 8M x 16) for the Zen
  Touch: this board uses a second source with the same organization.

Fit with the firmware / emulator:
- The main program runs from CE2 (records 7..14 at 0x400000.. words) with SDRAM timing
  set by `func_00828efd`; CE2 + CE3 together are 4M words (8 MiB) of the chip's 8M words
  (16 MiB). How the rest is reached (CE0 is also switched to the SDRAM type in some
  configurations, `func_0003176b`) is open.

Sources: [alldatasheet V54C3128164VAT7](https://www.alldatasheet.com/view_datasheet.jsp?Searchword=V54C3128164VAT7),
[datasheet4u V54C3128](https://www.datasheet4u.com/datasheet-pdf/MoselVitelicCorp/V54C3128/pdf.php?id=295942),
[datasheetarchive V54C3128164](https://datasheetarchive.com/V54C3128164-datasheet.html) (all mirrors).

## p43a8 FST16211

- Fairchild (now onsemi) FST16211: 24-bit (2 x 12) FET bus switch, 4 ohm on resistance,
  TTL control inputs, OE1 / OE2 low connects port A to port B, high isolates them;
  56-pin SSOP / TSSOP or 54-ball FBGA. Without level shifting (that is the FSTD16211).
  "p43a8" reads as a date / lot code.
- Function on this board not confirmed. 24 lines fit a 16-bit data bus plus some address /
  control lines, for example the ATA bus to the hard disk, which the firmware powers on and
  off; a bus switch would isolate the unpowered drive.

Sources: [FSTD16211 datasheet (LBL mirror)](https://glacier.lbl.gov/gtp/DOM/dataSheets/FSTD16211.pdf),
[Farnell FST16211](https://www.farnell.com/datasheets/12212.pdf),
[alldatasheet FST16211 (onsemi)](https://www.alldatasheet.net/html-pdf/1079410/ONSEMI/FST16211/1288/5/FST16211.html).

## synoptics t1005 0313 c64968-06

- Synaptics (marking reads "synoptics") T1005: touch pad controller of the Zen Touch
  vertical touch strip (Rockbox wiki; Wikipedia: Synaptics supplied the vertical "click
  wheel" of the Zen Touch, as for the iPod mini / 4G). No public datasheet found.
  "0313" reads as a date code (2003, week 13), "c64968-06" as a part / lot number.

Fit with the firmware / emulator:
- The DSP does not talk to the touch pad directly: touch events arrive as MCU event bytes
  over I2C (class 7 / 9 = scroll with speed level, detail 14 = tap), see
  the c55x_emulator `controls.py`. So the T1005 is most likely connected to the MCU, not
  to the DSP.

Sources: [Rockbox wiki CreativeZenTouch](https://www.rockbox.org/wiki/CreativeZenTouch.html),
[Synaptics (Wikipedia)](https://en.wikipedia.org/wiki/Synaptics).

## Published board for comparison

The Rockbox wiki (CreativeZenTouch page) lists the chips of an Australian Zen Touch
20 GB (made in HK, 2003/2004), main PCB front, under the LCD:

| Part | Published board | This board |
|---|---|---|
| DSP | Texas Instruments TMS320 DA255GHH (4A-44A8F3W) | TMS320DA255ZHH |
| NOR flash | SST 39VF400A 70-4C-EK (0410148-AB) | 39VF400A |
| SDRAM | Samsung 431 K4S281632F-TC75 (S2816 WQF646PBC) | Mosel Vitelic V54C3128164VBT7 (0424PR) |
| touch pad | Synaptics T1005 0423 CM2764.00 | Synaptics T1005 0313 c64968-06 |
| bus switch | not listed | FST16211 (p43a8) |
| unlabeled chip | yes, under yellow tape, next to the hard disk cable connector; the author suspects an IDE controller | not reported yet |
| LCD | label FGE-CMGG160104B-01 S0-MA01267 040832-BJ | not reported yet |
| hard disk | Hitachi Travelstar, 4200 RPM | not reported yet |

Notes:
- Same DSP die in two package codes (GHH / ZHH), same flash, same touch pad controller
  with other date / lot codes (0423 vs 0313). The SDRAM differs: Samsung on the published
  board, Mosel Vitelic here, both 128 Mbit; the Samsung part's organization was not
  confirmed from a Samsung datasheet (the 16-bit EMIF needs x16).
- LCD: "160104" in the label matches the 160 x 104 panel (manual: "160 x 104 pixel EL
  backlit display"). Nothing found for the part number itself; the controller is still only
  known by its command set (ST7571-like, L1).
- The unlabeled chip at the hard disk connector: the firmware reaches the ATA task file
  directly on CE1 (data word 0x280000), so a separate IDE controller is not needed for
  that. The USB controller the firmware uses on CE1 (data word 0x282000) is not
  identified; a USB-to-IDE capable chip next to the disk connector would fit, which is a
  guess. Its marking is the most useful thing to read on this board.

Sources: Rockbox wiki CreativeZenTouch (text provided by the user;
[page](https://www.rockbox.org/wiki/CreativeZenTouch.html)), searches for the LCD label
and K4S281632F found no datasheet.

## Test pads

Solder pads on the board, labels as printed:

| Pad | Meaning | Use |
|---|---|---|
| sda, scl | I2C bus | the bus of the MCU (address 7) and the audio codec (0x1a): a logic analyzer capture answers the MCU command / status meanings and checks the codec init |
| 3,3v, gnd | supply, ground | 3.3 V only as the JTAG adapter's target reference (VTref), not to power the player |
| tms1, tck1, tdi1, tdo1, trst1 | DSP JTAG (IEEE 1149.1) | a TI XDS emulator can halt the DSP and read memory: NOR BOOT area, internal ROM, chip id block 0x3800..0x3804 and the JTAG IDCODE, USB controller registers at CE1 0x282000 |
| emu1, emu2 | TI emulation pins | the C55x names them EMU0 / EMU1; that emu1 = EMU0 and emu2 = EMU1 is assumed (board labels count from 1), no DA255 pinout to confirm it |
| clkout1 | DSP clock output | measures the CPU clock (the emulator sees 96 MHz during MP3 playback) |

Notes before connecting (not verified on this board):
- The I/O level of the JTAG pins is assumed to be 3.3 V; measure first.
- On C55x devices EMU0 / EMU1 are sampled when TRST goes high; they must be high for normal
  emulation (low can select boundary scan). Check against the C5509A datasheet.
- Whether Code Composer Studio accepts the DA255 with a C5509A target configuration is
  unknown (the IDCODE probably differs).
- Read only: no NOR writes before a recovery path is known.

## JTAG: adapter, software, wiring

### Adapter

| Adapter | C55x | Note |
|---|---|---|
| XDS110 (TI TMDSEMU110-U) | yes: TI lists "C55x Low-power DSPs" as supported | current TI probe; price not checked (about 100 EUR from memory) |
| XDS200 | yes (TI) | more expensive, no benefit here |
| XDS100v2 | works: it is the on-board probe of TI's C5535 USB stick (a C55x) | TI no longer sells it standalone; third parties (Olimex, Blackhawk); cheap but slow |
| Segger J-Link | no | no C55x support found; CCS reaches C55x cores only through TI's XDS drivers |

A J-Link can still serve as a plain JTAG adapter for OpenOCD: scanning the chain of an
unknown TAP prints its IDCODE (also checks the wiring). No memory access or halt.
This is general OpenOCD behavior, not tried on the DA255.

### Software

- Code Composer Studio 12.x (12.8 is the last Eclipse based release). C55x support in
  CCS 20 is not confirmed: its release notes list no C55x compiler. The C55x code
  generation tools 4.4.1 are already in `build/ti-cgt-c5500-4.4.1`.
- Target configuration: start with "TMS320C5509A" and the XDS110. If CCS rejects the
  IDCODE, read it with the OpenOCD scan first.

### Wiring (TI 14-pin connector of the adapter to the pads)

| 14-pin | Signal | Pad |
|---|---|---|
| 1 | TMS | tms1 |
| 2 | TRST | trst1 |
| 3 | TDI | tdi1 |
| 4 | TDIS | gnd |
| 5 | VTRef / PD | 3,3v (reference only) |
| 6 | key | - |
| 7 | TDO | tdo1 |
| 8, 10, 12 | GND | gnd |
| 9 | RTCK (TCK return) | tck1, together with pin 11 |
| 11 | TCK | tck1 |
| 13 | EMU0 | emu1 (assumed) |
| 14 | EMU1 | emu2 (assumed) |

The XDS110 ships with an adapter to the TI 14-pin connector.

Checklist:
- Power the player from its battery or charger; pin 5 only senses the target voltage.
- Measure tck1 / tms1 against gnd first: 3.3 V I/O is expected, not documented for the
  DA255.
- TI recommends pull-ups of 2.2 to 4.7 kOhm on EMU0 / EMU1 and a 2.2 kOhm pull-down on
  TRST. They are probably fitted on the board; check them first if the connection fails.
- Short wires (below about 15 cm), start with a low TCK (about 1 MHz) in CCS.
- Read only.

What a working connection can answer: the NOR BOOT area and the decoded boot loader in RAM
the internal ROM, chip id block 0x3800..0x3804, the USB controller
registers at CE1 0x282000, real MCU and codec register states for comparison with the
emulator.

### Software options without a CCS installation on the host

| Way | Halt / read internal memory | Effort | Note |
|---|---|---|---|
| CCS 12.x on Linux, in a container or VM (Ubuntu 22.04) | yes | low | TI's Linux host support pages list C55x as supported; Arch is no validated host, Ubuntu 24.04 needs libtinfo5 by hand. A container with the XDS110 passed through keeps the host clean; memory dumps can then run headless as DSS scripts (JavaScript, deprecated in favor of "CCS Scripting", needs a 64-bit JRE) |
| own boundary-scan tool (OpenOCD or urjtag, or Python on any JTAG adapter, J-Link or XDS110) | no | medium | IEEE 1149.1 is public. With a BSDL file the pins can be driven (EXTEST): read the NOR flash over the EMIF pins, toggle I2C, check the pinout. Internal ROM / RAM and the CPU state are not reachable this way |
| own C55x debug tool (halt, memory read over the TI emulation logic) | yes | very high | the C55x emulation scan protocol is not public; it would have to be reverse engineered, e.g. by capturing the JTAG traffic of an XDS probe while CCS reads memory |

Facts behind this:
- No C55x target in OpenOCD (its documented targets are ARM, MIPS, RISC-V and others);
  an old OMAP5912 config only names the C55x TAP id. OpenOCD does support the XDS110 as a
  plain JTAG adapter, so one XDS110 serves both CCS and own tools.
- The TMS320VC5509A comes in the 179-ball GHH / ZHH BGA and the 144-pin PGE LQFP, the
  same package codes as the DA255 (ZHH on this board, GHH on the published board, PGE at
  distributors). A VC5509A BSDL file (if TI provides one; not verified) may therefore fit;
  check the IDCODE and the boundary register length against it before driving any pin
  (a wrong BSDL can damage the chip).
- What the boundary scan can add is limited: FBOOT, the NOR BOOT content, is already known
  from the update file; the stage that decodes it most likely runs from the DSP's
  internal ROM, which only the debug path can read.

Suggested way: one-time CCS 12 in an Ubuntu 22.04 container to dump the internal ROM and
RAM after boot (DSS script), everything else with own tools and the emulator.

### CCS in a Docker container

Possible; there is no official TI guide for debugging from a container, the points below
come from TI E2E threads and the OpenOCD XDS110 driver:
- Install CCS 12.x non-interactively in the image (`--mode unattended --prefix <dir>`);
  the installer loads components from software-dl.ti.com, so the build needs network
  access. Skip the installer's driver script inside the container.
- udev does not run in containers: the XDS110 rule goes on the host, for example
  `SUBSYSTEM=="usb", ATTRS{idVendor}=="0451", ATTRS{idProduct}=="bef3", MODE="0660", TAG+="uaccess"`
  (0451:bef3 is the XDS110 default configuration; check with `lsusb`), then
  `udevadm control --reload-rules && udevadm trigger`.
- Pass only the probe into the container (`--device /dev/bus/usb/BBB/DDD`), not
  `--privileged`. The bus / device number changes on replugging.
- Headless use (DSS scripts) needs no GUI forwarding; the IDE would need X11 / Wayland
  forwarding.
- Check the installer's checksum against the TI download page before building the image.

Sources: [E2E: CCS in Docker (unattended)](https://e2e.ti.com/support/tools/code-composer-studio-group/ccs/f/code-composer-studio-forum/845856/ccs-ccstudio-trying-to-install-ccs-9-1-0-in-docker-container),
[E2E: AM2434 Docker install failure](https://e2e.ti.com/support/microcontrollers/arm-based-microcontrollers-group/arm-based-microcontrollers/f/arm-based-microcontrollers-forum/1399443/am2434-code-composer-studio-docker-container-unattended-install-failure),
[E2E: DSS, Linux and Docker](https://e2e.ti.com/support/tools/code-composer-studio-group/ccs/f/code-composer-studio-forum/544573/dss-linux-and-docker-containers),
[CCS CI/CD notes (mbedded.ninja)](https://blog.mbedded.ninja/programming/integrated-development-environments-ides/code-composer-studio/cicd/),
[OpenOCD XDS110 USB ids](https://git.flow3r.garden/card10/openocd/-/commit/2ba27e2f3edd37e5dce4b2a231d2ae84c14cb59a.patch).

Sources:
[CCS v12 Linux host support](https://software-dl.ti.com/ccs/esd/documents/ccsv12_linux_host_support.html),
[CCS v10 Linux host support](https://software-dl.ti.com/ccs/esd/documents/ccsv10_linux_host_support.html),
[DSS handbook](https://software-dl.ti.com/ccs/esd/documents/users_guide/sdto_dss_handbook.html),
[TMS320VC5509A product page](https://www.ti.com/product/TMS320VC5509A),
[VC5509A packages (radiolocman, aggregator)](https://www.radiolocman.com/datasheet/data.html?di=334091),
[OpenOCD OMAP5912 config](https://git.flow3r.garden/card10/openocd/-/blob/878d0cb04370057bf04ee307625bffb2130227ce/tcl/target/omap5912.cfg),
[Lauterbach C5500 debugger](https://www.lauterbach.com/products/LA-7830).

## I2C capture plan

A logic analyzer on sda / scl / gnd (for example a cheap 24 MHz analyzer with sigrok /
PulseView and its I2C decoder) needs no change to the board. Capture:
1. Boot: codec init (address 0x1a) and the first MCU commands (address 7).
2. Key presses and touch pad movement (MCU event bytes, c55x_emulator `controls.py`).
3. USB cable in and out (MCU status bits b8 / b9).
4. Charging and battery level (MCU registers 0 / 1, c55x_emulator `mcu.py`).
5. Backlight on / off and the "Backlight Time" setting (MCU commands 20 / 21).

Export as CSV or sigrok `.sr`; the bytes can be checked against the MCU model of the
c55x_emulator.

## Suggested order

1. I2C capture (no risk, answers most MCU questions).
2. OpenOCD IDCODE scan with the J-Link (checks the JTAG chain).
3. Only then an XDS110 and CCS 12.x for memory reads.

Sources for this part:
[TI XDS110](https://software-dl.ti.com/ccs/esd/documents/xdsdebugprobes/emu_xds110.html),
[TI XDS200](https://software-dl.ti.com/ccs/esd/documents/xdsdebugprobes/emu_xds200.html),
[TI XDS100](https://software-dl.ti.com/ccs/esd/documents/xdsdebugprobes/emu_xds100.html),
[TI JTAG connectors](https://software-dl.ti.com/ccs/esd/xdsdebugprobes/emu_jtag_connectors.html),
[TI XDS target connection guide](https://software-dl.ti.com/ccs/esd/documents/xdsdebugprobes/emu_xds_target_connection_guide.html),
[iSystem TI 14-pin adapter](https://www.isystem.com/downloads/user-manuals/active-probe-adapter-ti-14-pin.html),
[Segger supported TI devices](https://www.segger.com/supported-devices/ti),
[TI: SEGGER J-Link](https://www.ti.com/tool/SEGGR-3P-J-LINK),
[Code Composer Studio (Wikipedia)](https://en.wikipedia.org/wiki/Code_Composer_Studio),
[CCS 20.1.0 release notes](https://software-dl.ti.com/ccs/esd/CCSv20/CCS_20_1_0/exports/CCS_20.1.0_ReleaseNote.htm),
[E2E: C55x in CCS 7](https://e2e.ti.com/support/tools/code-composer-studio-group/ccs/f/code-composer-studio-forum/582779/ccs-c55x-audioframework-ccs7-x-importing-c55x-audio-framework-failure),
[E2E: VC5501 CCS support](https://e2e.ti.com/support/processors-group/processors/f/processors-forum/1080519/tms320vc5501-ccs-support-for-c5000).

## Not on the list yet

Chips the firmware needs that are not identified on the boards:
- the MCU (I2C address 7: keys, touch pad, battery, power),
- the audio codec (I2C address 0x1a, TLV320AIC23 register map; AIC23 or WM8731 still open),
- the USB controller on CE1 (data word 0x282000; candidate: the unlabeled chip at the
  disk connector, see above),
- the LCD controller (ST7571-like command set, L1; panel label known from the published
  board),
- the hard disk on this board (published board: Hitachi Travelstar, 4200 RPM).
