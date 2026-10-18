"""PE firmware relocation, archive readback, and normalization regressions."""

import hashlib
import hmac
import random
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

import zen_keys
from extract_zen_firmware import locate_firmware, unpack_updater
from make_zen_update import patch_updater
from verify_zen_update import compare_normalized_archive
from zen_pe import code_references, pe_checksum, read_pe, section_named


def archive(payload):
    player = "Creative Zen Touch".encode("utf-16be").ljust(96, b"\0")
    name = "Hasset.dat".encode("utf-16be").ljust(32, b"\0")
    children = b"CINF" + struct.pack(">I", len(player)) + player
    children += b"DATA" + struct.pack(">I", len(name) + len(payload)) + name + payload
    root = b"CIFF" + struct.pack(">I", len(children)) + children
    result = root + b"NULL" + struct.pack("<I", 20) + hmac.new(zen_keys.get("signing"), root, hashlib.sha1).digest()
    return result + b"\0" * (-len(result) % 4)


def updater_fixture(firmware):
    exe = bytearray(2560)
    exe[:2] = b"MZ"
    struct.pack_into("<I", exe, 0x3C, 0x80)
    exe[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", exe, 0x84, 0x14C, 3, 0, 0, 0, 224, 0x10F)
    optional = 0x98
    struct.pack_into("<H", exe, optional, 0x10B)
    struct.pack_into("<I", exe, optional + 8, 1024)
    struct.pack_into("<III", exe, optional + 28, 0x400000, 4096, 512)
    struct.pack_into("<II", exe, optional + 56, 16384, 1024)
    struct.pack_into("<I", exe, optional + 92, 16)
    for index, (name, raw, rva, flags) in enumerate(
            ((b".text", 1024, 4096, 0x60000020), (b".rdata", 1536, 8192, 0x40000040),
             (b".data", 2048, 12288, 0xC0000040))):
        struct.pack_into("<8sIIIIIIHHI", exe, optional + 224 + index * 40,
                         name, 512, rva, 512, raw, 0, 0, 0, 0, flags)
    key = b"34d1" + b"x" * 28      # test key: the updater is searched for this prefix
    exe[1536:1536 + len(key)] = key
    mask = bytes((value - 1) | 0x80 for value in key)
    packed = zlib.compress(firmware, 9)
    encrypted = bytes(value ^ mask[index % len(mask)] for index, value in enumerate(packed))
    struct.pack_into("<I", exe, 2056, len(encrypted))
    exe[2060:2060 + len(encrypted)] = encrypted
    for offset, delta in ((1040, 0), (1060, 1), (1080, 3)):
        struct.pack_into("<I", exe, offset, 0x403008 + delta)
    return bytes(exe)


class UpdateExeTests(unittest.TestCase):
    def setUp(self):
        self.original_firmware = archive(b"original" * 4)
        self.source = updater_fixture(self.original_firmware)

    def larger_firmware(self):
        rng = random.Random(42)
        return archive(bytes(rng.getrandbits(8) for _ in range(4000)))

    def test_smaller_payload_preserves_code_and_section_count(self):
        firmware = archive(b"small")
        patched, report = patch_updater(self.source, firmware)
        self.assertEqual(report["strategy"], "replace existing payload")
        self.assertEqual(len(read_pe(patched)["sections"]), 3)
        self.assertEqual(patched[1024:1536], self.source[1024:1536])
        self.assertEqual(unpack_updater(patched)[0], firmware)

    def test_larger_payload_relocates_all_references_and_preserves_original_data(self):
        firmware = self.larger_firmware()
        patched, report = patch_updater(self.source, firmware)
        pe = read_pe(patched)
        section = section_named(pe, ".firm")
        self.assertEqual(len(pe["sections"]), 4)
        self.assertEqual(len(report["patched_code_references"]), 3)
        self.assertEqual(patched[2048:2560], self.source[2048:2560])
        self.assertFalse(code_references(patched, pe, 0x403008))
        address = pe["image_base"] + section["rva"]
        self.assertEqual([ref["address"] for ref in code_references(patched, pe, address)],
                         [address, address + 1, address + 3])
        self.assertEqual(locate_firmware(patched)["offset"], section["raw_offset"])
        self.assertEqual(unpack_updater(patched)[0], firmware)
        stored_checksum = struct.unpack_from("<I", patched, pe["checksum_offset"])[0]
        self.assertEqual(stored_checksum, pe_checksum(patched, pe["checksum_offset"]))

    def test_relocation_requires_header_space(self):
        source = bytearray(self.source)
        struct.pack_into("<I", source, 0x98 + 60, 512)
        with self.assertRaisesRegex(ValueError, "section-header space"):
            patch_updater(bytes(source), self.larger_firmware())

    def test_relocation_requires_code_references(self):
        source = bytearray(self.source)
        source[1024:1536] = b"\0" * 512
        with self.assertRaisesRegex(ValueError, "No updater code references"):
            patch_updater(bytes(source), self.larger_firmware())

    def test_bad_archive_hmac_is_rejected(self):
        firmware = bytearray(self.original_firmware)
        firmware[150] ^= 1
        with self.assertRaisesRegex(ValueError, "HMAC-SHA1"):
            patch_updater(self.source, bytes(firmware))

    def test_checksum_known_carry_and_odd_length_vector(self):
        self.assertEqual(pe_checksum(b"\0\0\0\0\xff\xff\x01\0\x02", 0), 12)
        self.assertEqual(pe_checksum(b"\x12\x34\x56\x78\xff\xff\x01\0\x02", 0), 12)

    def test_native_normalization_only_allows_up_to_three_zero_bytes(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            actual, expected = Path(directory) / "actual", Path(directory) / "expected"
            actual.write_bytes(b"archive")
            expected.write_bytes(b"archive\0\0")
            self.assertEqual(compare_normalized_archive(actual, expected)["alignment_zero_bytes_omitted"], 2)
            for suffix in (b"\0\0\0\0", b"\0x"):
                expected.write_bytes(b"archive" + suffix)
                with self.assertRaises(ValueError):
                    compare_normalized_archive(actual, expected)


if __name__ == "__main__":
    unittest.main()
