"""Check failure detection in the external native-tool verification driver."""

import sys
import tempfile
import unittest
from pathlib import Path

from verify_rockbox_zencrypt import compare_files, run_tool


class NativeVerificationTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.scratch.cleanup)
        self.directory = Path(self.scratch.name)

    def test_native_command_failure_is_not_accepted(self):
        with self.assertRaisesRegex(RuntimeError, "exit status 7"):
            run_tool([sys.executable, "-c", "raise SystemExit(7)"], self.directory)
        self.assertIn("[exit status 7]", (self.directory / "commands.log").read_text())

    def test_wrong_hmac_error_is_not_a_successful_tamper_test(self):
        with self.assertRaisesRegex(RuntimeError, "expected HMAC error"):
            run_tool([sys.executable, "-c", "print('file missing'); raise SystemExit(8)"],
                     self.directory, rejection_message="incorrect digest")

    def test_accepting_corruption_is_detected(self):
        with self.assertRaisesRegex(RuntimeError, "expected HMAC error"):
            run_tool([sys.executable, "-c", "print('verified')"], self.directory,
                     rejection_message="incorrect digest")

    def test_byte_mismatch_is_detected(self):
        actual, expected = self.directory / "actual", self.directory / "expected"
        actual.write_bytes(b"CODEwrong")
        expected.write_bytes(b"CODEright")
        with self.assertRaisesRegex(ValueError, "Byte comparison failed"):
            compare_files(actual, expected, "native decoder output")


if __name__ == "__main__":
    unittest.main()
