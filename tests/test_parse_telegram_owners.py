import os
import unittest
import importlib.util
from web3 import constants


def load_read_config_module():
    root = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(root, "src", "config", "read_config.py")
    spec = importlib.util.spec_from_file_location("read_config", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


class TestParseTelegramOwners(unittest.TestCase):
    def setUp(self):
        self.rc = load_read_config_module()

    def test_empty_string(self):
        """Test parsing empty string returns empty dictionary"""
        result = self.rc._parse_telegram_owners("")
        self.assertEqual(result, {})

    def test_none_input(self):
        """Test parsing None input returns empty dictionary"""
        result = self.rc._parse_telegram_owners(None)
        self.assertEqual(result, {})

    def test_whitespace_only(self):
        """Test parsing whitespace-only string returns empty dictionary"""
        result = self.rc._parse_telegram_owners("   ")
        self.assertEqual(result, {})

    def test_single_nickname_with_at_symbol(self):
        """Test parsing single nickname with @ symbol"""
        result = self.rc._parse_telegram_owners("@josh")
        expected = {"josh": constants.ADDRESS_ZERO}
        self.assertEqual(result, expected)

    def test_single_nickname_without_at_symbol(self):
        """Test parsing single nickname without @ symbol"""
        result = self.rc._parse_telegram_owners("josh")
        expected = {"josh": constants.ADDRESS_ZERO}
        self.assertEqual(result, expected)

    def test_multiple_nicknames_with_at_symbols(self):
        """Test parsing multiple nicknames with @ symbols"""
        result = self.rc._parse_telegram_owners("@josh,@anna,@dexter")
        expected = {
            "josh": constants.ADDRESS_ZERO,
            "anna": constants.ADDRESS_ZERO,
            "dexter": constants.ADDRESS_ZERO,
        }
        self.assertEqual(result, expected)

    def test_multiple_nicknames_without_at_symbols(self):
        """Test parsing multiple nicknames without @ symbols"""
        result = self.rc._parse_telegram_owners("josh,anna,dexter")
        expected = {
            "josh": constants.ADDRESS_ZERO,
            "anna": constants.ADDRESS_ZERO,
            "dexter": constants.ADDRESS_ZERO,
        }
        self.assertEqual(result, expected)

    def test_mixed_nicknames_with_and_without_at_symbols(self):
        """Test parsing mixed nicknames with and without @ symbols"""
        result = self.rc._parse_telegram_owners("@josh,anna,@dexter")
        expected = {
            "josh": constants.ADDRESS_ZERO,
            "anna": constants.ADDRESS_ZERO,
            "dexter": constants.ADDRESS_ZERO,
        }
        self.assertEqual(result, expected)

    def test_single_nickname_with_address(self):
        """Test parsing single nickname with address"""
        result = self.rc._parse_telegram_owners(
            "@josh:0x1234567890abcdef1234567890abcdef12345678"
        )
        expected = {"josh": "0x1234567890abcdef1234567890abcdef12345678"}
        self.assertEqual(result, expected)

    def test_multiple_nicknames_with_addresses(self):
        """Test parsing multiple nicknames with addresses"""
        result = self.rc._parse_telegram_owners(
            "@josh:0x1234567890abcdef1234567890abcdef12345678,@anna:0xabcdef1234567890abcdef1234567890abcdef12"
        )
        expected = {
            "josh": "0x1234567890abcdef1234567890abcdef12345678",
            "anna": "0xabcdef1234567890abcdef1234567890abcdef12",
        }
        self.assertEqual(result, expected)

    def test_mixed_nicknames_with_and_without_addresses(self):
        """Test parsing mixed nicknames with and without addresses"""
        result = self.rc._parse_telegram_owners(
            "@josh:0x1234567890abcdef1234567890abcdef12345678,@anna,@dexter:0xabcdef1234567890abcdef1234567890abcdef12"
        )
        expected = {
            "josh": "0x1234567890abcdef1234567890abcdef12345678",
            "anna": constants.ADDRESS_ZERO,
            "dexter": "0xabcdef1234567890abcdef1234567890abcdef12",
        }
        self.assertEqual(result, expected)

    def test_nicknames_with_extra_whitespace(self):
        """Test parsing nicknames with extra whitespace"""
        result = self.rc._parse_telegram_owners("  @josh  ,  @anna  ,  @dexter  ")
        expected = {
            "josh": constants.ADDRESS_ZERO,
            "anna": constants.ADDRESS_ZERO,
            "dexter": constants.ADDRESS_ZERO,
        }
        self.assertEqual(result, expected)

    def test_nicknames_with_addresses_and_whitespace(self):
        """Test parsing nicknames with addresses and extra whitespace"""
        result = self.rc._parse_telegram_owners(
            "  @josh : 0x1234567890abcdef1234567890abcdef12345678  ,  @anna : 0xabcdef1234567890abcdef1234567890abcdef12  "
        )
        expected = {
            "josh": "0x1234567890abcdef1234567890abcdef12345678",
            "anna": "0xabcdef1234567890abcdef1234567890abcdef12",
        }
        self.assertEqual(result, expected)

    def test_empty_entries_are_filtered_out(self):
        """Test that empty entries (extra commas) are filtered out"""
        result = self.rc._parse_telegram_owners("@josh,,@anna,,,@dexter")
        expected = {
            "josh": constants.ADDRESS_ZERO,
            "anna": constants.ADDRESS_ZERO,
            "dexter": constants.ADDRESS_ZERO,
        }
        self.assertEqual(result, expected)

    def test_nickname_with_colon_in_address(self):
        """Test parsing nickname where address contains colon (edge case)"""
        # This tests the split(":", 1) behavior - only split on first colon
        result = self.rc._parse_telegram_owners("@josh:0x1234:extra:colons")
        expected = {"josh": "0x1234:extra:colons"}
        self.assertEqual(result, expected)

    def test_nickname_without_at_symbol_with_address(self):
        """Test parsing nickname without @ symbol but with address"""
        result = self.rc._parse_telegram_owners(
            "josh:0x1234567890abcdef1234567890abcdef12345678"
        )
        expected = {"josh": "0x1234567890abcdef1234567890abcdef12345678"}
        self.assertEqual(result, expected)

    def test_at_symbol_stripping_consistency(self):
        """Test that @ symbols are consistently stripped from nicknames"""
        result1 = self.rc._parse_telegram_owners("@josh")
        result2 = self.rc._parse_telegram_owners("josh")
        result3 = self.rc._parse_telegram_owners(
            "@josh:0x1234567890abcdef1234567890abcdef12345678"
        )
        result4 = self.rc._parse_telegram_owners(
            "josh:0x1234567890abcdef1234567890abcdef12345678"
        )

        # All should have the same key "josh" (without @)
        self.assertIn("josh", result1)
        self.assertIn("josh", result2)
        self.assertIn("josh", result3)
        self.assertIn("josh", result4)

        # None should have "@josh" as a key
        self.assertNotIn("@josh", result1)
        self.assertNotIn("@josh", result2)
        self.assertNotIn("@josh", result3)
        self.assertNotIn("@josh", result4)

    def test_real_ethereum_addresses(self):
        """Test parsing with real Ethereum addresses"""
        result = self.rc._parse_telegram_owners(
            "@alice:0x742d35Cc6635C0532925a3b8D4f25749d6d8f0C4,@bob:0x8ba1f109551bD432803012645Hac136c8c8b2e0"
        )
        expected = {
            "alice": "0x742d35Cc6635C0532925a3b8D4f25749d6d8f0C4",
            "bob": "0x8ba1f109551bD432803012645Hac136c8c8b2e0",
        }
        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
