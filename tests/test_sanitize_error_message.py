import unittest
import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from web3_scripts.oracle_script import _sanitize_error_message


class TestSanitizeErrorMessage(unittest.TestCase):

    def test_single_rpc_masked(self):
        msg = "Failed on https://src.example/KEY1 while reading"
        result = _sanitize_error_message(msg, "https://src.example/KEY1", "")
        self.assertNotIn("KEY1", result)
        self.assertIn("[SOURCE_RPC_MASKED]", result)

    def test_comma_separated_single_leaked_endpoint(self):
        # A real error mentions only the endpoint that actually failed.
        source_rpc = "https://src1.example/KEY1, https://src2.example/KEY2"
        msg = "Connection error to https://src2.example/KEY2"
        result = _sanitize_error_message(msg, source_rpc, "")
        self.assertNotIn("KEY2", result)
        self.assertIn("[SOURCE_RPC_MASKED]", result)

    def test_source_and_target_both_masked(self):
        source_rpc = "https://src.example/SKEY"
        target_rpc = "https://tgt1.example/TKEY1,https://tgt2.example/TKEY2"
        msg = "src https://src.example/SKEY and target https://tgt2.example/TKEY2"
        result = _sanitize_error_message(msg, source_rpc, target_rpc)
        self.assertNotIn("SKEY", result)
        self.assertNotIn("TKEY2", result)
        self.assertIn("[SOURCE_RPC_MASKED]", result)
        self.assertIn("[TARGET_RPC_MASKED]", result)

    def test_no_match_left_unchanged(self):
        msg = "Some unrelated error"
        result = _sanitize_error_message(
            msg, "https://src.example/KEY1", "https://tgt.example/KEY2"
        )
        self.assertEqual(msg, result)


if __name__ == "__main__":
    unittest.main()
