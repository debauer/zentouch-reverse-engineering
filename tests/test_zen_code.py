"""CODE record checksum, malformed-container, and exact-export regressions."""

import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

from export_zen_code import export_image
from zen_code import code_word_checksum, parse_code_image


def image_fixture(records, trailer=b""):
    body = b"".join(struct.pack(">III", address, len(payload), code_word_checksum(payload)) + payload
                    for address, payload in records)
    return b"CODE" + struct.pack(">II", len(body) + 4, 0x12345678) + body + trailer


class CodeImageTests(unittest.TestCase):
    def test_checksum_vectors_and_carry(self):
        self.assertEqual(code_word_checksum(bytes.fromhex("1234abcd")), 0xBE01)
        self.assertEqual(code_word_checksum(bytes.fromhex("ffff0002")), 1)
        with self.assertRaisesRegex(ValueError, "16-bit word"):
            code_word_checksum(b"\x01")

    def test_records_preserve_order_addresses_and_unknown_header(self):
        source = image_fixture([(0x800000, b"\x12\x34"), (0x100, b"\xab\xcd\x00\x02")])
        files, metadata = parse_code_image(source)
        self.assertEqual([block["address_field"] for block in metadata["blocks"]], [0x800000, 0x100])
        self.assertEqual([block["payload_file_offset"] for block in metadata["blocks"]], [24, 38])
        self.assertEqual(metadata["header_word_0x08"],
                         {"value": 0x12345678, "interpretation": "not established"})
        self.assertEqual(files["block_01_00000100.bin"], b"\xab\xcd\x00\x02")
        self.assertFalse(metadata["address_map"]["cpu_mapping_verified"])

    def test_checksum_corruption_and_upper_bits_are_rejected(self):
        source = bytearray(image_fixture([(0x100, b"\x12\x34")]))
        source[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            parse_code_image(bytes(source))
        source = bytearray(image_fixture([(0x100, b"\x12\x34")]))
        struct.pack_into(">I", source, 20, 0x11234)
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            parse_code_image(bytes(source))

    def test_truncated_headers_and_payloads_are_rejected(self):
        source = image_fixture([(0x100, b"\x12\x34")])
        with self.assertRaisesRegex(ValueError, "exceeds available data"):
            parse_code_image(source[:-1])
        partial = b"CODE" + struct.pack(">II", 9, 0) + b"abcde"
        with self.assertRaisesRegex(ValueError, "record header"):
            parse_code_image(partial)
        oversized = bytearray(source)
        struct.pack_into(">I", oversized, 16, 16)
        with self.assertRaisesRegex(ValueError, "extends beyond"):
            parse_code_image(bytes(oversized))

    def test_odd_payload_length_is_rejected(self):
        source = b"CODE" + struct.pack(">II", 19, 0) + struct.pack(">III", 0x100, 3, 0) + b"abc"
        with self.assertRaisesRegex(ValueError, "16-bit word"):
            parse_code_image(source)

    def test_empty_container_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "any load records"):
            parse_code_image(b"CODE" + struct.pack(">II", 4, 0))

    def test_overlap_is_reported_without_reordering_load_records(self):
        _, metadata = parse_code_image(image_fixture([(0x100, b"abcd"), (0x102, b"efgh")]))
        self.assertEqual(metadata["address_map"]["raw_byte_view_overlaps"],
                         [{"block_indices": [0, 1], "raw_byte_view_start": 0x102,
                           "raw_byte_view_end_exclusive": 0x104}])

    def test_exact_export_preserves_headers_payloads_and_flash_padding(self):
        source = image_fixture([(0x100, b"\x12\x34"), (0x800000, b"abcd")], b"\xff" * 4)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            input_path, output = Path(directory) / "input.jrm", Path(directory) / "export"
            input_path.write_bytes(source)
            metadata = export_image(input_path, output)
            saved = json.loads((output / "manifest.json").read_text())
            rebuilt = bytes.fromhex(saved["container_header_hex"])
            for block in saved["blocks"]:
                payload = (output / block["filename"]).read_bytes()
                self.assertEqual(hashlib.sha256(payload).hexdigest(), block["sha256"])
                rebuilt += bytes.fromhex(block["record_header_hex"]) + payload
            rebuilt += bytes.fromhex(saved["trailer_hex"])
            self.assertEqual(rebuilt, source)
            self.assertEqual(metadata["trailer_hex"], "ffffffff")
            self.assertEqual(input_path.read_bytes(), source)
            self.assertIn("not verified CPU-space assignments", (output / "memory_map.txt").read_text())
            with self.assertRaises(FileExistsError):
                export_image(input_path, output)


if __name__ == "__main__":
    unittest.main()
