"""Format vectors, codec boundary cases, and archive authentication regressions."""

import hashlib
import hmac
import struct
import unittest

from decrypt_zen_touch import decrypt_blowfish, encrypt_blowfish, validate_code
import zen_keys
from extract_zen_firmware import unpack_archive
from pack_zen_firmware import pack_archive
from zen_cenc import decode_cenc, encode_cenc


class CencTests(unittest.TestCase):
    def test_known_opcode_vectors(self):
        vectors = [
            (b"\x62\x00\x28\x48\x68", b"ABC"),
            (b"\x00\x01AB", b"ABABAB"),
            (b"\xc1\x06", b"\x81" * 3),
            (b"\x80\x01\x0c", b"\x81" * 67),
        ]
        for encoded, decoded in vectors:
            with self.subTest(encoded=encoded):
                self.assertEqual(decode_cenc(encoded, len(decoded)), decoded)
        self.assertEqual(encode_cenc(b"ABC"), vectors[0][0])
        self.assertEqual(encode_cenc(b"\x81" * 3), vectors[2][0])
        self.assertEqual(encode_cenc(b"\x81" * 67), vectors[3][0])

    def test_run_and_literal_boundaries(self):
        for length in (2, 0x41, 0x42, 0x4041, 0x4042, 0x8083):
            for value in (0, 0x81, 255):
                source = bytes([value]) * length
                with self.subTest(run_length=length, value=value):
                    self.assertEqual(decode_cenc(encode_cenc(source), length), source)
        pattern = bytes(range(256))
        for length in (1, 32, 33, 0x2020, 0x2021, 0x4040, 0x4041):
            source = (pattern * ((length + 255) // 256))[:length]
            with self.subTest(literal_length=length):
                self.assertEqual(decode_cenc(encode_cenc(source), length), source)

    def test_alignment_between_runs_and_literals(self):
        source = b"A" * 3 + b"BCDE" + b"F" * 66 + b"GHI" + b"J" * 2 + b"K"
        self.assertEqual(decode_cenc(encode_cenc(source), len(source)), source)

    def test_malformed_streams_are_rejected(self):
        for stream, size in ((b"\xc0", 2), (b"\x80\x00", 66),
                             (b"\x62\x00\x28", 3), (b"\xc1\x06", 2),
                             (b"\xc1\x06\xff", 3)):
            with self.subTest(stream=stream, size=size):
                with self.assertRaises(ValueError):
                    decode_cenc(stream, size)


class CryptoTests(unittest.TestCase):
    def test_published_blowfish_zero_vector(self):
        # Published Blowfish ECB vector; one CBC block with a zero IV is identical.
        plaintext = b"\0" * 8
        ciphertext = bytes.fromhex("4ef997456198dd78")
        self.assertEqual(encrypt_blowfish(plaintext, plaintext, plaintext), ciphertext)
        self.assertEqual(decrypt_blowfish(ciphertext, plaintext, plaintext), plaintext)

    def test_code_without_inner_signature_is_valid(self):
        image = b"CODE" + struct.pack(">I", 4) + b"data"
        self.assertFalse(validate_code(image)["hmac_sha1_verified"])
        with self.assertRaises(ValueError):
            validate_code(image[:4] + struct.pack(">I", 5) + image[8:])

    def test_rescue_flash_padding_is_preserved(self):
        image = b"CODE" + struct.pack(">I", 4) + b"data"
        self.assertEqual(validate_code(image + b"\xff" * 4)["padding_hex"], "ffffffff")
        with self.assertRaises(ValueError):
            validate_code(image + b"\xff\x00\xff\x00")


class ArchiveTests(unittest.TestCase):
    def original_archive(self):
        # Bytes after the terminating name NUL are preserved as part of the field.
        name = "FRESC\0suffix".encode("utf-16be").ljust(32, b"\0")
        content = name + b"original payload"
        child = b"DATA" + struct.pack(">I", len(content)) + content
        root = b"CIFF" + struct.pack(">I", len(child)) + child
        digest = hmac.new(zen_keys.get("signing"), root, hashlib.sha1).digest()
        archive = root + b"NULL" + struct.pack("<I", 20) + digest
        return archive + b"\0" * (-len(archive) % 4)

    def test_container_rebuild_preserves_bytes(self):
        original = self.original_archive()
        files, metadata = unpack_archive(original)
        self.assertEqual(pack_archive(files, metadata), original)

    def test_changed_payload_updates_lengths_and_hmac(self):
        files, metadata = unpack_archive(self.original_archive())
        files["FRESC"] = b"a different, longer payload"
        rebuilt = pack_archive(files, metadata)
        checked, checked_metadata = unpack_archive(rebuilt)
        self.assertEqual(checked["FRESC"], files["FRESC"])
        self.assertTrue(checked_metadata["hmac_sha1_verified"])
        damaged = bytearray(rebuilt)
        damaged[checked_metadata["entries"][0]["content_offset"]] ^= 1
        with self.assertRaisesRegex(ValueError, "HMAC-SHA1 signature does not match"):
            unpack_archive(bytes(damaged))


if __name__ == "__main__":
    unittest.main()
